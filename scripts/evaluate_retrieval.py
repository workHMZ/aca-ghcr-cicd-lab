#!/usr/bin/env python3
"""Evaluate retrieval against a labelled local fixture or Azure AI Search.

Two golden formats are supported:

* ``eval/golden.jsonl`` + ``eval/corpus.jsonl`` (``--backend local``): a small
  synthetic fixture for fast, offline model comparisons. Rankings match on
  passage ``expected_id``.
* ``eval/golden_corpus.jsonl`` (``--backend azure``): labelled questions about
  the real ingested corpus. A result is relevant when its ``source`` matches
  and its ``pageNumber..pageEnd`` range covers one of ``relevant_pages``.

Local mode embeds the pinned E5 model through the production ONNX encoder
(``app.embed``); other models use sentence-transformers as baselines.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INDEX_NAME = "ragdocs-v4"
DEFAULT_GOLDEN_PATH = PROJECT_ROOT / "eval" / "golden.jsonl"
DEFAULT_CORPUS_PATH = PROJECT_ROOT / "eval" / "corpus.jsonl"
DEFAULT_E5_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
SEMANTIC_CONFIGURATION_NAME = "rag-semantic"
AZURE_MODES = ("semantic", "hybrid", "vector", "bm25")
CUTOFFS = (1, 3, 5)
MRR_DEPTH = 10


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    query_id: str
    query: str
    language: str
    expected_id: str | None = None
    expected_source: str | None = None
    relevant_pages: tuple[int, ...] = field(default_factory=tuple)


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


def _required_string(row: dict[str, Any], field_name: str, *, location: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} requires a non-empty string field '{field_name}'")
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
        pages = row.get("relevant_pages")
        if pages is not None:
            if not isinstance(pages, list) or not pages or not all(isinstance(p, int) for p in pages):
                raise ValueError(f"{location} requires a non-empty integer list 'relevant_pages'")
            queries.append(
                GoldenQuery(
                    query_id=query_id,
                    query=_required_string(row, "query", location=location),
                    language=_required_string(row, "language", location=location).lower(),
                    expected_source=_required_string(row, "source", location=location),
                    relevant_pages=tuple(sorted(set(pages))),
                )
            )
            continue
        queries.append(
            GoldenQuery(
                query_id=query_id,
                query=_required_string(row, "query", location=location),
                language=_required_string(row, "language", location=location).lower(),
                expected_id=_required_string(row, "expected_id", location=location),
                expected_source=_required_string(row, "expected_source", location=location),
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


def _is_production_model(model_name: str, revision: str | None) -> bool:
    return model_name == DEFAULT_E5_MODEL and revision in (None, DEFAULT_E5_REVISION)


class _ProductionEncoder:
    """The serving ONNX encoder; it applies the E5 prefixes itself."""

    def encode_queries(self, texts: Sequence[str]) -> Any:
        from app import embed

        return [embed.embed_query(text) for text in texts]

    def encode_passages(self, texts: Sequence[str]) -> Any:
        from app import embed

        return embed.embed_passages(list(texts))


class _SentenceTransformerEncoder:
    def __init__(self, model_name: str, revision: str | None, batch_size: int) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is required for baseline models") from exc
        kwargs: dict[str, Any] = {}
        if revision:
            kwargs["revision"] = revision
        self._model = SentenceTransformer(model_name, **kwargs)
        self._name = model_name
        self._batch_size = batch_size

    def _encode(self, texts: Sequence[str], input_type: str) -> Any:
        return self._model.encode(
            [_prefix_for_model(text, self._name, input_type) for text in texts],
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    def encode_queries(self, texts: Sequence[str]) -> Any:
        return self._encode(texts, "query")

    def encode_passages(self, texts: Sequence[str]) -> Any:
        return self._encode(texts, "passage")


def _encoder(model_name: str, revision: str | None, batch_size: int) -> Any:
    if _is_production_model(model_name, revision):
        return _ProductionEncoder()
    return _SentenceTransformerEncoder(model_name, revision, batch_size)


def _local_rankings(
    *,
    encoder: Any,
    queries: Sequence[GoldenQuery],
    corpus: Sequence[CorpusPassage],
) -> list[list[dict[str, Any]]]:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for local retrieval evaluation") from exc

    passage_vectors = np.asarray(encoder.encode_passages([passage.content for passage in corpus]))
    query_vectors = np.asarray(encoder.encode_queries([query.query for query in queries]))
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
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V4", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def _azure_rankings(
    *,
    queries: Sequence[GoldenQuery],
    index_name: str,
    mode: str,
    retrieval_depth: int,
    search_fields: Sequence[str] | None,
) -> list[list[dict[str, Any]]]:
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.models import VectorizedQuery
    except ImportError as exc:
        raise RuntimeError("Azure evaluation requires the Azure Search SDK") from exc

    from app import embed

    client = SearchClient(
        endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
        index_name=index_name,
        credential=AzureKeyCredential(_required_env("AZURE_SEARCH_API_KEY")),
    )
    expected_metadata = (embed.get_model_name(), embed.get_model_revision(), embed.get_embedding_variant())
    rankings: list[list[dict[str, Any]]] = []
    for query in queries:
        options: dict[str, Any] = {
            "top": retrieval_depth,
            "select": [
                "id",
                "source",
                "pageNumber",
                "pageEnd",
                "embeddingModel",
                "embeddingRevision",
                "embeddingVariant",
            ],
        }
        if mode != "vector":
            options["search_text"] = query.query
            if search_fields:
                options["search_fields"] = list(search_fields)
        if mode != "bm25":
            options["vector_queries"] = [
                VectorizedQuery(
                    vector=embed.embed_query(query.query),
                    k_nearest_neighbors=max(retrieval_depth, 50),
                    fields="contentVector",
                    exhaustive=False,
                )
            ]
        if mode == "semantic":
            # Fail loudly: a silently skipped reranker would corrupt the metric.
            options.update(
                query_type="semantic",
                semantic_configuration_name=SEMANTIC_CONFIGURATION_NAME,
                semantic_error_mode="fail",
            )
        ranking: list[dict[str, Any]] = []
        for result in client.search(**options):
            metadata = (
                result.get("embeddingModel"),
                result.get("embeddingRevision"),
                result.get("embeddingVariant"),
            )
            if metadata != expected_metadata:
                raise RuntimeError("Azure index embedding metadata does not match the evaluator")
            ranking.append(
                {
                    "id": str(result.get("id", "")),
                    "source": str(result.get("source", "")),
                    "page_start": result.get("pageNumber"),
                    "page_end": result.get("pageEnd") or result.get("pageNumber"),
                    "score": float(result.get("@search.score") or 0.0),
                    "reranker_score": result.get("@search.reranker_score"),
                }
            )
        rankings.append(ranking)
    return rankings


def _is_relevant(query: GoldenQuery, item: dict[str, Any], match_field: str) -> bool:
    if match_field == "id":
        return str(item.get("id", "")) == query.expected_id
    if str(item.get("source", "")) != query.expected_source:
        return False
    if match_field == "source":
        return True
    start, end = item.get("page_start"), item.get("page_end")
    if start is None:
        return False
    return any(int(start) <= page <= int(end or start) for page in query.relevant_pages)


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
        sum(0.0 if rank is None or rank > MRR_DEPTH else 1.0 / rank for rank in ranks) / count,
        6,
    )
    return metrics


def _reranker_calibration(
    queries: Sequence[GoldenQuery],
    rankings: Sequence[Sequence[dict[str, Any]]],
    match_field: str,
    floors: Sequence[float],
    top_k: int,
) -> dict[str, Any]:
    """Show what a context floor would keep/drop within the served top_k."""

    relevant: list[float] = []
    other: list[float] = []
    for query, ranking in zip(queries, rankings, strict=True):
        for item in ranking[:top_k]:
            score = item.get("reranker_score")
            if score is not None:
                (relevant if _is_relevant(query, item, match_field) else other).append(float(score))
    if not relevant:
        return {}
    report: dict[str, Any] = {
        "top_k": top_k,
        "relevant_median": round(statistics.median(relevant), 3),
        "relevant_min": round(min(relevant), 3),
        "other_median": round(statistics.median(other), 3) if other else None,
    }
    for floor in floors:
        report[f"floor_{floor:g}"] = {
            "relevant_kept": round(sum(1 for s in relevant if s >= floor) / len(relevant), 3),
            "other_dropped": round(sum(1 for s in other if s < floor) / len(other), 3) if other else None,
        }
    return report


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
        rank = next(
            (
                position
                for position, item in enumerate(ranking, start=1)
                if _is_relevant(query, item, match_field)
            ),
            None,
        )
        ranks.append(rank)
        ranks_by_language.setdefault(query.language, []).append(rank)
        per_query.append(
            {
                "id": query.query_id,
                "language": query.language,
                "expected": query.expected_id if match_field == "id" else query.expected_source,
                "rank": rank,
                "top3": [
                    {
                        key: (round(float(value), 6) if key == "score" else value)
                        for key, value in item.items()
                        if key in ("id", "source", "score", "page_start", "page_end")
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


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backend", choices=("local", "azure"), default="local")
    parser.add_argument("--golden", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Local backend: embedding model; repeat to compare models",
    )
    parser.add_argument(
        "--revision",
        dest="revisions",
        action="append",
        help="Pinned model revision corresponding to each --model",
    )
    parser.add_argument(
        "--mode",
        dest="modes",
        action="append",
        choices=AZURE_MODES,
        help="Azure backend: retrieval mode; repeat for an ablation (default: semantic)",
    )
    parser.add_argument(
        "--search-field",
        dest="search_fields",
        action="append",
        help="Azure backend: restrict lexical matching to these fields (default: all searchable)",
    )
    parser.add_argument("--batch-size", type=_positive_int, default=32)
    parser.add_argument("--index-name", default=None)
    parser.add_argument("--azure-top", type=_positive_int, default=10)
    parser.add_argument("--top-k", type=_positive_int, default=5, help="Served contexts for calibration")
    parser.add_argument("--details", action="store_true", help="Include per-query rankings")
    return parser.parse_args(argv)


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


def _strip_details(metrics: dict[str, Any], keep: bool) -> dict[str, Any]:
    return metrics if keep else {key: value for key, value in metrics.items() if key != "queries"}


def _run_local(args: argparse.Namespace, queries: list[GoldenQuery]) -> dict[str, Any]:
    if any(query.expected_id is None for query in queries):
        raise ValueError("The local backend needs a passage-level golden file (expected_id)")
    corpus = load_corpus(args.corpus.expanduser().resolve())
    missing = sorted({query.expected_id for query in queries} - {passage.passage_id for passage in corpus})
    if missing:
        raise ValueError(f"Golden expected_id values missing from corpus: {missing}")

    model_results: list[dict[str, Any]] = []
    for model_name, revision in _model_specs(args):
        encoder = _encoder(model_name, revision, args.batch_size)
        rankings = _local_rankings(encoder=encoder, queries=queries, corpus=corpus)
        model_results.append(
            {
                "model": model_name,
                "requested_revision": revision,
                "runtime": "onnx (app.embed)" if _is_production_model(model_name, revision) else "torch",
                "match_field": "id",
                "metrics": _strip_details(
                    score_rankings(queries, rankings, cutoffs=CUTOFFS, match_field="id"),
                    True,
                ),
            }
        )
    report: dict[str, Any] = {
        "backend": "local",
        "dataset": str(args.golden),
        "dataset_kind": "synthetic_fixture",
        "warning": (
            "Synthetic fixture metrics are reproducible model-comparison evidence, "
            "not production RAG quality."
        ),
        "query_count": len(queries),
        "corpus_count": len(corpus),
        "models": model_results,
    }
    comparison = _comparison(model_results)
    if comparison is not None:
        report["candidate_minus_baseline"] = comparison
    return report


def _run_azure(args: argparse.Namespace, queries: list[GoldenQuery]) -> dict[str, Any]:
    if args.models:
        raise ValueError("The Azure backend always uses the served embedding model; omit --model")
    match_field = "page" if all(query.relevant_pages for query in queries) else "source"
    index_name = (args.index_name or _default_index_name()).strip()
    modes: dict[str, Any] = {}
    for mode in args.modes or ["semantic"]:
        rankings = _azure_rankings(
            queries=queries,
            index_name=index_name,
            mode=mode,
            retrieval_depth=max(args.azure_top, max(CUTOFFS)),
            search_fields=args.search_fields,
        )
        result = _strip_details(
            score_rankings(queries, rankings, cutoffs=CUTOFFS, match_field=match_field),
            args.details,
        )
        if mode == "semantic":
            result["reranker_calibration"] = _reranker_calibration(
                queries, rankings, match_field, floors=(0.5, 1.0, 1.5, 2.0), top_k=args.top_k
            )
        modes[mode] = result
    return {
        "backend": "azure",
        "index": index_name,
        "dataset": str(args.golden),
        "dataset_kind": "labelled_corpus_queries",
        "match_field": match_field,
        "search_fields": args.search_fields or "all searchable",
        "warning": f"MRR is truncated at rank {MRR_DEPTH}.",
        "query_count": len(queries),
        "modes": modes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    args = _parse_args(argv)
    if args.golden is None:
        args.golden = (
            PROJECT_ROOT / "eval" / "golden_corpus.jsonl" if args.backend == "azure" else DEFAULT_GOLDEN_PATH
        )
    queries = load_golden(args.golden.expanduser().resolve())
    report = _run_local(args, queries) if args.backend == "local" else _run_azure(args, queries)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
