"""Chunk local documents and idempotently ingest them into the v4 index."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
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
    DEFAULT_MIN_CHUNK_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    chunk_document,
    detect_toc_pages,
)
from scripts.create_index import LANGUAGE_FIELDS

DEFAULT_INDEX_NAME = "ragdocs-v4"
ID_NAMESPACE = "v4"
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    source: str
    chunk_index: int
    content: str
    title: str | None
    page_start: int
    page_end: int
    token_count: int
    created_at: str
    embedding_text: str


@dataclass(slots=True)
class IngestionStats:
    files: int = 0
    pages: int = 0
    toc_pages: int = 0
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
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V4", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def _embedding_metadata() -> tuple[str, str, str, Any, int]:
    dimension = int(embedding.get_dimension())
    if dimension <= 0:
        raise RuntimeError("Embedding dimension must be greater than zero")
    return (
        embedding.get_model_name(),
        embedding.get_model_revision(),
        embedding.get_embedding_variant(),
        embedding.get_tokenizer(),
        dimension,
    )


def _embed_passages(texts: Sequence[str]) -> list[list[float]]:
    return embedding.embed_passages(list(texts))


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


def _stable_document_id(source: str, chunk_index: int) -> str:
    identity = f"{ID_NAMESPACE}\0{source}\0{chunk_index}".encode()
    return hashlib.sha256(identity).hexdigest()


def _source_document_prefix(source: str) -> str:
    """Stable source namespace used to remove stale chunks after a re-ingest."""

    return hashlib.sha256(f"{ID_NAMESPACE}\0{source}\0".encode()).hexdigest()[:16]


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def select_source_files(data_dir: Path, patterns: Sequence[str] | None = None) -> list[Path]:
    """Return supported regular files under ``data_dir`` matching any glob."""

    selected: list[Path] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = path.relative_to(data_dir).as_posix()
        if patterns and not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            continue
        selected.append(path)
    return selected


def _iter_records(
    data_dir: Path,
    tokenizer: Any,
    *,
    patterns: Sequence[str] | None,
    chunk_tokens: int,
    min_chunk_tokens: int,
    overlap_tokens: int,
    stats: IngestionStats,
) -> Iterator[ChunkRecord]:
    paths = select_source_files(data_dir, patterns)
    print(f"Selected {len(paths)} files in {data_dir}:")
    for path in paths:
        print(f"  - {path.relative_to(data_dir).as_posix()}")

    for path in paths:
        stats.files += 1
        source = path.relative_to(data_dir).as_posix()
        created_at = _source_timestamp(path)
        pages = list(_iter_source_pages(path))
        stats.pages += len(pages)
        chunks = chunk_document(
            pages,
            tokenizer,
            max_tokens=chunk_tokens,
            min_tokens=min(min_chunk_tokens, chunk_tokens),
            overlap_tokens=overlap_tokens,
        )
        toc_pages = detect_toc_pages(pages)
        stats.toc_pages += len(toc_pages)
        print(f"Chunked {source}: {len(pages)} pages ({len(toc_pages)} TOC skipped) -> {len(chunks)} chunks")
        for chunk_index, chunk in enumerate(chunks):
            stats.chunks += 1
            yield ChunkRecord(
                source=source,
                chunk_index=chunk_index,
                content=chunk.text,
                title=chunk.title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                token_count=chunk.token_count,
                created_at=created_at,
                embedding_text=chunk.embedding_text(),
            )


def _document_from_record(
    record: ChunkRecord,
    vector: Sequence[float],
    *,
    model_name: str,
    model_revision: str,
    model_variant: str,
) -> dict[str, Any]:
    return {
        "id": _stable_document_id(record.source, record.chunk_index),
        "content": record.content,
        **dict.fromkeys(LANGUAGE_FIELDS, record.content),
        "title": record.title,
        "contentVector": list(vector),
        "source": record.source,
        "sourceId": _source_document_prefix(record.source),
        "pageNumber": record.page_start,
        "pageEnd": record.page_end,
        "chunkIndex": record.chunk_index,
        "contentHash": _content_hash(record.content),
        "embeddingModel": model_name,
        "embeddingRevision": model_revision,
        "embeddingVariant": model_variant,
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
    model_variant: str,
    tokenizer: Any,
    dimension: int,
    chunk_tokens: int,
    min_chunk_tokens: int,
    overlap_tokens: int,
    embedding_batch_size: int,
    upload_batch_size: int,
    patterns: Sequence[str] | None = None,
) -> IngestionStats:
    stats = IngestionStats()
    started_at = time.monotonic()
    pending_uploads: list[dict[str, Any]] = []
    active_ids_by_source: dict[str, set[str]] = {}

    records = _iter_records(
        data_dir,
        tokenizer,
        patterns=patterns,
        chunk_tokens=chunk_tokens,
        min_chunk_tokens=min_chunk_tokens,
        overlap_tokens=overlap_tokens,
        stats=stats,
    )
    for record_batch in _batched(records, embedding_batch_size):
        for record in record_batch:
            active_ids_by_source.setdefault(record.source, set()).add(
                _stable_document_id(record.source, record.chunk_index)
            )
        # The heading path is embedded with the chunk so continuation chunks
        # of a long answer still match questions about their section.
        vectors = _embed_passages([record.embedding_text for record in record_batch])
        if len(vectors) != len(record_batch):
            stats.failed += len(record_batch)
            raise RuntimeError(
                f"Embedding model returned {len(vectors)} vectors for {len(record_batch)} chunks"
            )
        for record, vector in zip(record_batch, vectors, strict=True):
            if len(vector) != dimension:
                stats.failed += 1
                raise RuntimeError(
                    f"Embedding dimension mismatch for {record.source} chunk {record.chunk_index}: "
                    f"expected {dimension}, got {len(vector)}"
                )
            pending_uploads.append(
                _document_from_record(
                    record,
                    vector,
                    model_name=model_name,
                    model_revision=model_revision,
                    model_variant=model_variant,
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
    # stale tail chunks in an existing index.
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
        "--glob",
        dest="patterns",
        action="append",
        help=(
            "Only ingest files whose path relative to --data-dir matches this glob; "
            "repeatable (default: every .pdf/.md/.txt file). The index is served by a "
            "public API, so never point it at private notes."
        ),
    )
    parser.add_argument(
        "--index-name",
        default=None,
        help="Target index (default: AZURE_SEARCH_INDEX_NAME_V4 or ragdocs-v4)",
    )
    parser.add_argument("--chunk-tokens", type=_positive_int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--min-chunk-tokens", type=_positive_int, default=DEFAULT_MIN_CHUNK_TOKENS)
    parser.add_argument("--overlap-tokens", type=_non_negative_int, default=DEFAULT_OVERLAP_TOKENS)
    parser.add_argument("--embedding-batch-size", type=_positive_int, default=32)
    parser.add_argument("--upload-batch-size", type=_positive_int, default=100)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and report statistics without embedding or uploading",
    )
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
    model_name, model_revision, model_variant, tokenizer, dimension = _embedding_metadata()
    print(
        json.dumps(
            {
                "index": index_name,
                "model": model_name,
                "revision": model_revision,
                "variant": model_variant,
                "dimension": dimension,
                "chunk_tokens": args.chunk_tokens,
                "min_chunk_tokens": args.min_chunk_tokens,
                "overlap_tokens": args.overlap_tokens,
            },
            ensure_ascii=False,
        )
    )

    if args.dry_run:
        stats = IngestionStats()
        records = list(
            _iter_records(
                data_dir,
                tokenizer,
                patterns=args.patterns,
                chunk_tokens=args.chunk_tokens,
                min_chunk_tokens=args.min_chunk_tokens,
                overlap_tokens=args.overlap_tokens,
                stats=stats,
            )
        )
        tokens = [record.token_count for record in records]
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    **asdict(stats),
                    "avg_chunk_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
                },
                ensure_ascii=False,
            )
        )
        return 0

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
        model_variant=model_variant,
        tokenizer=tokenizer,
        dimension=dimension,
        chunk_tokens=args.chunk_tokens,
        min_chunk_tokens=args.min_chunk_tokens,
        overlap_tokens=args.overlap_tokens,
        embedding_batch_size=args.embedding_batch_size,
        upload_batch_size=args.upload_batch_size,
        patterns=args.patterns,
    )
    print(json.dumps({"status": "complete", **asdict(stats)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
