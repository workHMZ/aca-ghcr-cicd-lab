#!/usr/bin/env python3
"""Chunk local documents and idempotently ingest them into the v3 index."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from pypdf import PdfReader

from app import embed as embedding
from app.chunking import (
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    chunk_text,
)

DEFAULT_INDEX_NAME = "ragdocs-v3"
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    source: str
    page_number: int
    chunk_index: int
    content: str
    token_count: int
    created_at: str


@dataclass(slots=True)
class IngestionStats:
    files: int = 0
    pages: int = 0
    empty_pages: int = 0
    chunks: int = 0
    embedded: int = 0
    uploaded: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _default_index_name() -> str:
    # Never ingest into a legacy AZURE_SEARCH_INDEX_NAME by accident.
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V3", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def _call_optional(name: str) -> Any | None:
    function = getattr(embedding, name, None)
    return function() if callable(function) else None


def _get_model_object() -> Any:
    getter = getattr(embedding, "_get_model", None)
    if not callable(getter):
        raise RuntimeError("app.embed must expose get_tokenizer()")
    return getter()


def _embedding_metadata() -> tuple[str, str, Any, int]:
    model_name = _call_optional("get_model_name")
    model_revision = _call_optional("get_model_revision")
    tokenizer = _call_optional("get_tokenizer")

    model_object: Any | None = None
    if tokenizer is None or not model_name:
        model_object = _get_model_object()
    if tokenizer is None:
        tokenizer = getattr(model_object, "tokenizer", None)
    if tokenizer is None:
        raise RuntimeError("The embedding model does not expose a tokenizer")

    if not model_name:
        model_name = (
            os.getenv("EMBEDDING_MODEL")
            or os.getenv("EMBEDDING_MODEL_NAME")
            or getattr(tokenizer, "name_or_path", None)
            or "unknown"
        )
    if not model_revision:
        model_revision = os.getenv("EMBEDDING_MODEL_REVISION") or "unversioned"

    dimension = int(embedding.get_dimension())
    if dimension <= 0:
        raise RuntimeError("Embedding dimension must be greater than zero")
    return str(model_name), str(model_revision), tokenizer, dimension


def _embed_passages(texts: Sequence[str], model_name: str) -> list[list[float]]:
    embed_batch = embedding.embed_batch
    parameters = inspect.signature(embed_batch).parameters

    if "input_type" in parameters:
        raw_vectors = embed_batch(list(texts), input_type="passage")
    else:
        embedding_inputs = list(texts)
        if "e5" in model_name.lower():
            embedding_inputs = [f"passage: {text}" for text in embedding_inputs]
        raw_vectors = embed_batch(embedding_inputs)

    if hasattr(raw_vectors, "tolist"):
        raw_vectors = raw_vectors.tolist()
    return [[float(value) for value in vector] for vector in raw_vectors]


def _batched[T](values: Iterable[T], batch_size: int) -> Iterator[list[T]]:
    batch: list[T] = []
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _iter_source_pages(path: Path) -> Iterator[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            yield page_number, page.extract_text() or ""
        return

    yield 1, path.read_text(encoding="utf-8")


def _source_timestamp(path: Path) -> str:
    value = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _stable_document_id(source: str, page_number: int, chunk_index: int) -> str:
    identity = f"v3\0{source}\0{page_number}\0{chunk_index}".encode()
    return hashlib.sha256(identity).hexdigest()


def _source_document_prefix(source: str) -> str:
    """Stable source namespace used to remove stale chunks after a re-ingest."""

    return hashlib.sha256(f"v3\0{source}\0".encode()).hexdigest()[:16]


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _iter_records(
    data_dir: Path,
    tokenizer: Any,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
    stats: IngestionStats,
) -> Iterator[ChunkRecord]:
    paths = sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    print(f"Found {len(paths)} supported files in {data_dir}")

    for path in paths:
        stats.files += 1
        source = path.relative_to(data_dir).as_posix()
        created_at = _source_timestamp(path)
        print(f"Chunking {source}...")

        for page_number, page_text in _iter_source_pages(path):
            stats.pages += 1
            if not page_text.strip():
                stats.empty_pages += 1
                continue

            page_chunks = chunk_text(
                page_text,
                tokenizer,
                max_tokens=chunk_tokens,
                overlap_tokens=overlap_tokens,
            )
            if not page_chunks:
                stats.empty_pages += 1
                continue

            for chunk_index, chunk in enumerate(page_chunks):
                stats.chunks += 1
                yield ChunkRecord(
                    source=source,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    content=chunk.text,
                    token_count=chunk.token_count,
                    created_at=created_at,
                )


def _document_from_record(
    record: ChunkRecord,
    vector: Sequence[float],
    *,
    model_name: str,
    model_revision: str,
) -> dict[str, Any]:
    return {
        "id": _stable_document_id(record.source, record.page_number, record.chunk_index),
        "content": record.content,
        "contentVector": list(vector),
        "source": record.source,
        "sourceId": _source_document_prefix(record.source),
        "pageNumber": record.page_number,
        "chunkIndex": record.chunk_index,
        "contentHash": _content_hash(record.content),
        "embeddingModel": model_name,
        "embeddingRevision": model_revision,
        "createdAt": record.created_at,
    }


def _result_value(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _upload_batch(
    client: SearchClient,
    documents: Sequence[dict[str, Any]],
    stats: IngestionStats,
) -> None:
    results = list(client.merge_or_upload_documents(documents=list(documents)))
    if len(results) != len(documents):
        stats.failed += len(documents)
        raise RuntimeError(f"Azure returned {len(results)} indexing results for {len(documents)} documents")

    failures = [result for result in results if not bool(_result_value(result, "succeeded", False))]
    stats.uploaded += len(results) - len(failures)
    stats.failed += len(failures)
    if failures:
        details = "; ".join(
            f"{_result_value(result, 'key', '<unknown>')}: "
            f"{_result_value(result, 'error_message', 'unknown indexing error')}"
            for result in failures[:10]
        )
        raise RuntimeError(f"{len(failures)} documents failed to index: {details}")


def _delete_stale_source_chunks(
    client: SearchClient,
    *,
    source: str,
    active_ids: set[str],
    stats: IngestionStats,
) -> None:
    source_id = _source_document_prefix(source)
    results = client.search(
        search_text="*",
        filter=f"sourceId eq '{source_id}'",
        select=["id"],
    )
    stale_ids = [str(result["id"]) for result in results if str(result["id"]) not in active_ids]
    if not stale_ids:
        return
    for stale_batch in _batched(stale_ids, 1000):
        delete_results = list(client.delete_documents(documents=[{"id": value} for value in stale_batch]))
        if len(delete_results) != len(stale_batch):
            stats.failed += len(stale_batch)
            raise RuntimeError(f"Azure returned incomplete stale-delete results for {source}")
        failures = [
            result for result in delete_results if not bool(_result_value(result, "succeeded", False))
        ]
        stats.failed += len(failures)
        if failures:
            raise RuntimeError(f"Failed to delete {len(failures)} stale chunks for {source}")


def ingest(
    *,
    client: SearchClient,
    data_dir: Path,
    model_name: str,
    model_revision: str,
    tokenizer: Any,
    dimension: int,
    chunk_tokens: int,
    overlap_tokens: int,
    embedding_batch_size: int,
    upload_batch_size: int,
) -> IngestionStats:
    stats = IngestionStats()
    started_at = time.monotonic()
    pending_uploads: list[dict[str, Any]] = []
    active_ids_by_source: dict[str, set[str]] = {}

    records = _iter_records(
        data_dir,
        tokenizer,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
        stats=stats,
    )
    for record_batch in _batched(records, embedding_batch_size):
        for record in record_batch:
            active_ids_by_source.setdefault(record.source, set()).add(
                _stable_document_id(record.source, record.page_number, record.chunk_index)
            )
        vectors = _embed_passages([record.content for record in record_batch], model_name)
        if len(vectors) != len(record_batch):
            stats.failed += len(record_batch)
            raise RuntimeError(
                f"Embedding model returned {len(vectors)} vectors for {len(record_batch)} chunks"
            )
        for record, vector in zip(record_batch, vectors, strict=True):
            if len(vector) != dimension:
                stats.failed += 1
                raise RuntimeError(
                    f"Embedding dimension mismatch for {record.source} page {record.page_number}: "
                    f"expected {dimension}, got {len(vector)}"
                )
            pending_uploads.append(
                _document_from_record(
                    record,
                    vector,
                    model_name=model_name,
                    model_revision=model_revision,
                )
            )
        stats.embedded += len(vectors)

        while len(pending_uploads) >= upload_batch_size:
            batch = pending_uploads[:upload_batch_size]
            del pending_uploads[:upload_batch_size]
            _upload_batch(client, batch, stats)
            print(f"Uploaded {stats.uploaded}/{stats.chunks} chunks...")

    if pending_uploads:
        _upload_batch(client, pending_uploads, stats)

    # Synchronize each source namespace so shortened/changed files cannot leave
    # stale tail chunks in an existing v3 index.
    for source, active_ids in active_ids_by_source.items():
        _delete_stale_source_chunks(client, source=source, active_ids=active_ids, stats=stats)

    stats.elapsed_seconds = round(time.monotonic() - started_at, 3)
    return stats


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument(
        "--index-name",
        default=None,
        help="Target index (default: AZURE_SEARCH_INDEX_NAME_V3 or ragdocs-v3)",
    )
    parser.add_argument("--chunk-tokens", type=_positive_int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--overlap-tokens", type=_non_negative_int, default=DEFAULT_OVERLAP_TOKENS)
    parser.add_argument("--embedding-batch-size", type=_positive_int, default=32)
    parser.add_argument("--upload-batch-size", type=_positive_int, default=100)
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = _parse_args()
    if args.overlap_tokens >= args.chunk_tokens:
        raise RuntimeError("--overlap-tokens must be smaller than --chunk-tokens")
    if args.upload_batch_size > 1000:
        raise RuntimeError("--upload-batch-size cannot exceed Azure AI Search's 1000-document limit")

    data_dir = args.data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise RuntimeError(f"Data directory does not exist: {data_dir}")

    index_name = (args.index_name or _default_index_name()).strip()
    model_name, model_revision, tokenizer, dimension = _embedding_metadata()
    print(
        json.dumps(
            {
                "index": index_name,
                "model": model_name,
                "revision": model_revision,
                "dimension": dimension,
                "chunk_tokens": args.chunk_tokens,
                "overlap_tokens": args.overlap_tokens,
            },
            ensure_ascii=False,
        )
    )

    client = SearchClient(
        endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
        index_name=index_name,
        credential=AzureKeyCredential(_required_env("AZURE_SEARCH_API_KEY")),
    )
    stats = ingest(
        client=client,
        data_dir=data_dir,
        model_name=model_name,
        model_revision=model_revision,
        tokenizer=tokenizer,
        dimension=dimension,
        chunk_tokens=args.chunk_tokens,
        overlap_tokens=args.overlap_tokens,
        embedding_batch_size=args.embedding_batch_size,
        upload_batch_size=args.upload_batch_size,
    )
    print(json.dumps({"status": "complete", **asdict(stats)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
