#!/usr/bin/env python3
"""Evaluate retrieval against a labelled local fixture or Azure AI Search.

Local mode performs real model inference over ``eval/corpus.jsonl`` and makes
no Azure calls. The bundled fixture is intentionally small and synthetic: its
metrics validate retrieval behaviour and model comparisons, not production
RAG quality.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INDEX_NAME = "ragdocs-v3"
DEFAULT_GOLDEN_PATH = PROJECT_ROOT / "eval" / "golden.jsonl"
DEFAULT_CORPUS_PATH = PROJECT_ROOT / "eval" / "corpus.jsonl"
DEFAULT_E5_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
SEMANTIC_CONFIGURATION_NAME = "rag-semantic"


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    query_id: str
    query: str
    expected_id: str
    expected_source: str
    language: str


@dataclass(frozen=True, slots=True)
class CorpusPassage:
    passage_id: str
    content: str
    source: str
    language: str


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object in {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"Fixture is empty: {path}")
    return rows


def _required_string(row: dict[str, Any], field: str, *, location: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} requires a non-empty string field '{field}'")
    return value.strip()


def load_golden(path: Path) -> list[GoldenQuery]:
    queries: list[GoldenQuery] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(_load_jsonl(path), start=1):
        location = f"{path}:{index}"
        query_id = _required_string(row, "id", location=location)
        if query_id in seen_ids:
            raise ValueError(f"Duplicate golden id '{query_id}' in {path}")
        seen_ids.add(query_id)
        queries.append(
            GoldenQuery(
                query_id=query_id,
                query=_required_string(row, "query", location=location),
                expected_id=_required_string(row, "expected_id", location=location),
                expected_source=_required_string(row, "expected_source", location=location),
                language=_required_string(row, "language", location=location).lower(),
            )
        )
    return queries


def load_corpus(path: Path) -> list[CorpusPassage]:
    passages: list[CorpusPassage] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(_load_jsonl(path), start=1):
        location = f"{path}:{index}"
        passage_id = _required_string(row, "id", location=location)
        if passage_id in seen_ids:
            raise ValueError(f"Duplicate corpus id '{passage_id}' in {path}")
        seen_ids.add(passage_id)
        passages.append(
            CorpusPassage(
                passage_id=passage_id,
                content=_required_string(row, "content", location=location),
                source=_required_string(row, "source", location=location),
                language=_required_string(row, "language", location=location).lower(),
            )
        )
    return passages


def _prefix_for_model(text: str, model_name: str, input_type: str) -> str:
    if "e5" in model_name.lower():
        return f"{input_type}: {text}"
    return text


def _load_model(model_name: str, revision: str | None) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is required for retrieval evaluation") from exc

    kwargs: dict[str, Any] = {}
    if revision:
        kwargs["revision"] = revision
    return SentenceTransformer(model_name, **kwargs)


def _encode(model: Any, texts: Sequence[str], *, batch_size: int) -> Any:
    return model.encode(
        list(texts),
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def _local_rankings(
    *,
    model: Any,
    model_name: str,
    queries: Sequence[GoldenQuery],
    corpus: Sequence[CorpusPassage],
    batch_size: int,
) -> list[list[dict[str, Any]]]:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for local retrieval evaluation") from exc

    passage_inputs = [_prefix_for_model(passage.content, model_name, "passage") for passage in corpus]
    query_inputs = [_prefix_for_model(query.query, model_name, "query") for query in queries]
    passage_vectors = _encode(model, passage_inputs, batch_size=batch_size)
    query_vectors = _encode(model, query_inputs, batch_size=batch_size)
    scores = np.matmul(query_vectors, passage_vectors.T)

    rankings: list[list[dict[str, Any]]] = []
    for row in scores:
        order = np.argsort(-row, kind="stable")
        rankings.append(
            [
                {
                    "id": corpus[int(position)].passage_id,
                    "source": corpus[int(position)].source,
                    "score": float(row[int(position)]),
                }
                for position in order
            ]
        )
    return rankings


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _default_index_name() -> str:
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V3", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def _azure_rankings(
    *,
    model: Any,
    model_name: str,
    queries: Sequence[GoldenQuery],
    index_name: str,
    retrieval_depth: int,
    batch_size: int,
) -> list[list[dict[str, Any]]]:
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.models import VectorizedQuery
    except ImportError as exc:
        raise RuntimeError("Azure evaluation requires the Azure Search SDK and python-dotenv") from exc

    client = SearchClient(
        endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
        index_name=index_name,
        credential=AzureKeyCredential(_required_env("AZURE_SEARCH_API_KEY")),
    )
    query_inputs = [_prefix_for_model(query.query, model_name, "query") for query in queries]
    query_vectors = _encode(model, query_inputs, batch_size=batch_size)

    rankings: list[list[dict[str, Any]]] = []
    for query, vector in zip(queries, query_vectors, strict=True):
        vector_query = VectorizedQuery(
            vector=[float(value) for value in vector],
            k_nearest_neighbors=retrieval_depth,
            fields="contentVector",
            exhaustive=False,
        )
        results = client.search(
            search_text=query.query,
            vector_queries=[vector_query],
            top=retrieval_depth,
            select=["id", "source", "embeddingModel", "embeddingRevision"],
            query_type="semantic",
            semantic_configuration_name=SEMANTIC_CONFIGURATION_NAME,
        )
        rankings.append(
            [
                {
                    "id": str(result.get("id", "")),
                    "source": str(result.get("source", "")),
                    "embedding_model": str(result.get("embeddingModel", "")),
                    "embedding_revision": str(result.get("embeddingRevision", "")),
                    "score": float(result.get("@search.score", 0.0)),
                }
                for result in results
            ]
        )
    return rankings


def _metrics_for_ranks(ranks: Sequence[int | None], cutoffs: Sequence[int]) -> dict[str, float]:
    count = len(ranks)
    if count == 0:
        raise ValueError("Cannot calculate metrics for zero queries")
    metrics = {
        f"recall@{cutoff}": round(
            sum(1 for rank in ranks if rank is not None and rank <= cutoff) / count,
            6,
        )
        for cutoff in cutoffs
    }
    metrics["mrr"] = round(
        sum(0.0 if rank is None else 1.0 / rank for rank in ranks) / count,
        6,
    )
    return metrics


def score_rankings(
    queries: Sequence[GoldenQuery],
    rankings: Sequence[Sequence[dict[str, Any]]],
    *,
    cutoffs: Sequence[int],
    match_field: str,
) -> dict[str, Any]:
    if len(queries) != len(rankings):
        raise ValueError("Ranking count does not match query count")

    per_query: list[dict[str, Any]] = []
    ranks: list[int | None] = []
    ranks_by_language: dict[str, list[int | None]] = {}

    for query, ranking in zip(queries, rankings, strict=True):
        expected = query.expected_id if match_field == "id" else query.expected_source
        rank = next(
            (
                position
                for position, item in enumerate(ranking, start=1)
                if str(item.get(match_field, "")) == expected
            ),
            None,
        )
        ranks.append(rank)
        ranks_by_language.setdefault(query.language, []).append(rank)
        per_query.append(
            {
                "id": query.query_id,
                "language": query.language,
                "expected": expected,
                "rank": rank,
                "top3": [
                    {
                        "id": item.get("id"),
                        "source": item.get("source"),
                        "score": round(float(item.get("score", 0.0)), 6),
                    }
                    for item in ranking[:3]
                ],
            }
        )

    return {
        "overall": _metrics_for_ranks(ranks, cutoffs),
        "by_language": {
            language: {
                "queries": len(language_ranks),
                **_metrics_for_ranks(language_ranks, cutoffs),
            }
            for language, language_ranks in sorted(ranks_by_language.items())
        },
        "queries": per_query,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local", "azure"), default="local")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Sentence Transformers model; repeat to compare models",
    )
    parser.add_argument(
        "--revision",
        dest="revisions",
        action="append",
        help="Pinned model revision corresponding to each --model",
    )
    parser.add_argument("--batch-size", type=_positive_int, default=32)
    parser.add_argument("--index-name", default=None)
    parser.add_argument("--azure-top", type=_positive_int, default=50)
    return parser.parse_args()


def _model_specs(args: argparse.Namespace) -> list[tuple[str, str | None]]:
    using_configured_model = not args.models
    models = args.models or [os.getenv("EMBEDDING_MODEL", DEFAULT_E5_MODEL)]
    revisions = args.revisions or (
        [os.getenv("EMBEDDING_MODEL_REVISION") or DEFAULT_E5_REVISION] if using_configured_model else []
    )
    if revisions and len(revisions) != len(models):
        raise ValueError("Repeat --revision once for every --model, or omit all revisions")
    if not revisions:
        revisions = [None] * len(models)
    return list(zip(models, revisions, strict=True))


def _comparison(results: Sequence[dict[str, Any]]) -> dict[str, float] | None:
    if len(results) != 2:
        return None
    baseline = results[0]["metrics"]["overall"]
    candidate = results[1]["metrics"]["overall"]
    return {
        metric: round(float(candidate[metric]) - float(baseline[metric]), 6)
        for metric in ("recall@1", "recall@3", "mrr")
    }


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    args = _parse_args()
    queries = load_golden(args.golden.expanduser().resolve())
    cutoffs = (1, 3)
    corpus: list[CorpusPassage] | None = None
    if args.backend == "local":
        corpus = load_corpus(args.corpus.expanduser().resolve())
        corpus_ids = {passage.passage_id for passage in corpus}
        missing = sorted({query.expected_id for query in queries} - corpus_ids)
        if missing:
            raise ValueError(f"Golden expected_id values missing from corpus: {missing}")

    model_results: list[dict[str, Any]] = []
    for model_name, revision in _model_specs(args):
        if args.backend == "azure" and (model_name != DEFAULT_E5_MODEL or revision != DEFAULT_E5_REVISION):
            raise ValueError(
                "Azure evaluation must use the model/revision that built ragdocs-v3; "
                "create a separate index to evaluate another embedding space"
            )
        model = _load_model(model_name, revision)
        if args.backend == "local":
            assert corpus is not None
            rankings = _local_rankings(
                model=model,
                model_name=model_name,
                queries=queries,
                corpus=corpus,
                batch_size=args.batch_size,
            )
            match_field = "id"
        else:
            rankings = _azure_rankings(
                model=model,
                model_name=model_name,
                queries=queries,
                index_name=(args.index_name or _default_index_name()).strip(),
                retrieval_depth=max(args.azure_top, max(cutoffs)),
                batch_size=args.batch_size,
            )
            if any(
                item.get("embedding_model") != model_name or item.get("embedding_revision") != revision
                for ranking in rankings
                for item in ranking
            ):
                raise RuntimeError(
                    "Azure index contains embedding metadata that does not match the evaluator"
                )
            # Azure ingestion hashes IDs. The default labelled Azure smoke is
            # therefore source-level; use a dedicated evaluator for page/chunk
            # relevance judgements instead of pretending fixture IDs match.
            match_field = "source"

        model_results.append(
            {
                "model": model_name,
                "requested_revision": revision,
                "match_field": match_field,
                "metrics": score_rankings(
                    queries,
                    rankings,
                    cutoffs=cutoffs,
                    match_field=match_field,
                ),
            }
        )

    report: dict[str, Any] = {
        "backend": args.backend,
        "dataset": str(args.golden),
        "dataset_kind": "synthetic_fixture" if args.backend == "local" else "labelled_azure_queries",
        "warning": (
            "Synthetic fixture metrics are reproducible model-comparison evidence, "
            "not production RAG quality."
            if args.backend == "local"
            else f"MRR is truncated at the top {args.azure_top} Azure results."
        ),
        "query_count": len(queries),
        "corpus_count": len(corpus) if corpus is not None else None,
        "models": model_results,
    }
    comparison = _comparison(model_results)
    if comparison is not None:
        report["candidate_minus_baseline"] = comparison

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
