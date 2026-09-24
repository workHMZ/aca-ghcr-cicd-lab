from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import evaluate_retrieval as evaluator

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_bundled_golden_files_load() -> None:
    fixture = evaluator.load_golden(PROJECT_ROOT / "eval" / "golden.jsonl")
    corpus = evaluator.load_golden(PROJECT_ROOT / "eval" / "golden_corpus.jsonl")

    assert all(query.expected_id for query in fixture)
    assert len(corpus) >= 50
    assert {query.language for query in corpus} == {"en", "ja", "zh"}
    assert all(query.relevant_pages and query.expected_source for query in corpus)


def test_load_golden_rejects_bad_page_labels(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "golden.jsonl",
        [{"id": "q", "language": "en", "query": "x", "source": "a.pdf", "relevant_pages": []}],
    )
    with pytest.raises(ValueError, match="relevant_pages"):
        evaluator.load_golden(path)


def test_load_golden_rejects_duplicate_ids(tmp_path: Path) -> None:
    row = {"id": "q", "language": "en", "query": "x", "expected_id": "p", "expected_source": "s"}
    with pytest.raises(ValueError, match="Duplicate"):
        evaluator.load_golden(_write(tmp_path / "golden.jsonl", [row, row]))


def test_page_matching_uses_the_chunk_page_range() -> None:
    query = evaluator.GoldenQuery(
        query_id="q", query="x", language="zh", expected_source="book.pdf", relevant_pages=(43,)
    )
    spanning = {"source": "book.pdf", "page_start": 42, "page_end": 44}
    elsewhere = {"source": "book.pdf", "page_start": 45, "page_end": None}
    other_source = {"source": "other.pdf", "page_start": 43, "page_end": 43}

    assert evaluator._is_relevant(query, spanning, "page")
    assert not evaluator._is_relevant(query, elsewhere, "page")
    assert not evaluator._is_relevant(query, other_source, "page")
    assert evaluator._is_relevant(query, other_source | {"source": "book.pdf"}, "source")


def test_score_rankings_reports_recall_and_truncated_mrr() -> None:
    queries = [
        evaluator.GoldenQuery(query_id="a", query="x", language="en", expected_id="p1", expected_source="s"),
        evaluator.GoldenQuery(query_id="b", query="y", language="ja", expected_id="p2", expected_source="s"),
    ]
    rankings = [
        [{"id": "p1", "source": "s", "score": 1.0}],
        [{"id": f"n{i}", "source": "s", "score": 0.1} for i in range(11)] + [{"id": "p2", "source": "s"}],
    ]

    result = evaluator.score_rankings(queries, rankings, cutoffs=(1, 3), match_field="id")

    assert result["overall"] == {"recall@1": 0.5, "recall@3": 0.5, "mrr": 0.5}
    assert result["by_language"]["ja"]["mrr"] == 0.0


def test_reranker_calibration_summarises_floors() -> None:
    query = evaluator.GoldenQuery(
        query_id="q", query="x", language="zh", expected_source="book.pdf", relevant_pages=(1,)
    )
    ranking = [
        {"source": "book.pdf", "page_start": 1, "page_end": 1, "reranker_score": 2.5},
        {"source": "book.pdf", "page_start": 9, "page_end": 9, "reranker_score": 1.2},
    ]

    report = evaluator._reranker_calibration([query], [ranking], "page", floors=(1.5,), top_k=5)

    assert report["relevant_min"] == 2.5
    assert report["floor_1.5"] == {"relevant_kept": 1.0, "other_dropped": 1.0}


def test_model_specs_pair_revisions_with_models() -> None:
    args = evaluator._parse_args(["--model", "a", "--revision", "r1", "--model", "b", "--revision", "r2"])
    assert evaluator._model_specs(args) == [("a", "r1"), ("b", "r2")]

    mismatched = evaluator._parse_args(["--model", "a", "--model", "b", "--revision", "r1"])
    with pytest.raises(ValueError, match="Repeat --revision"):
        evaluator._model_specs(mismatched)


def test_only_the_pinned_e5_uses_the_production_encoder() -> None:
    assert evaluator._is_production_model(evaluator.DEFAULT_E5_MODEL, evaluator.DEFAULT_E5_REVISION)
    assert evaluator._is_production_model(evaluator.DEFAULT_E5_MODEL, None)
    assert not evaluator._is_production_model("sentence-transformers/all-MiniLM-L6-v2", None)
