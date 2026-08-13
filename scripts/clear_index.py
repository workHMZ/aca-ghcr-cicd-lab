#!/usr/bin/env python3
"""Delete every document from an explicitly confirmed v3 search index."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterator, Sequence
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

DEFAULT_INDEX_NAME = "ragdocs-v3"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _default_index_name() -> str:
    # Never clear a legacy AZURE_SEARCH_INDEX_NAME by accident.
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V3", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def _batched[T](values: Sequence[T], batch_size: int) -> Iterator[Sequence[T]]:
    for offset in range(0, len(values), batch_size):
        yield values[offset : offset + batch_size]


def _result_value(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _collect_document_ids(client: SearchClient) -> tuple[list[dict[str, str]], int]:
    """Read every key using the SDK's continuation-token pagination."""

    ids: list[dict[str, str]] = []
    page_count = 0
    results = client.search(search_text="*", select=["id"])
    for page in results.by_page():
        page_count += 1
        for document in page:
            document_id = str(document["id"])
            if not document_id:
                raise RuntimeError("Search returned a document with an empty id")
            ids.append({"id": document_id})
    return ids, page_count


def clear_index(client: SearchClient, *, batch_size: int = 100) -> dict[str, int]:
    """Delete all indexed documents in checked batches."""

    document_ids, pages = _collect_document_ids(client)
    deleted = 0
    failed = 0
    batches = 0

    for batch in _batched(document_ids, batch_size):
        batches += 1
        results = list(client.delete_documents(documents=list(batch)))
        if len(results) != len(batch):
            failed += len(batch)
            raise RuntimeError(
                f"Azure returned {len(results)} delete results for a batch of {len(batch)} documents"
            )

        failures = [result for result in results if not bool(_result_value(result, "succeeded", False))]
        deleted += len(results) - len(failures)
        failed += len(failures)
        if failures:
            details = "; ".join(
                f"{_result_value(result, 'key', '<unknown>')}: "
                f"{_result_value(result, 'error_message', 'unknown delete error')}"
                for result in failures[:10]
            )
            raise RuntimeError(f"{len(failures)} documents failed to delete: {details}")
        print(f"Deleted batch {batches} ({len(batch)} documents)")

    return {
        "search_pages": pages,
        "found": len(document_ids),
        "batches": batches,
        "deleted": deleted,
        "failed": failed,
    }


def _positive_batch_size(value: str) -> int:
    parsed = int(value)
    if parsed <= 0 or parsed > 1000:
        raise argparse.ArgumentTypeError("batch size must be between 1 and 1000")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index-name",
        default=None,
        help="Target index (default: AZURE_SEARCH_INDEX_NAME_V3 or ragdocs-v3)",
    )
    parser.add_argument("--batch-size", type=_positive_batch_size, default=100)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive deletion of every document in the target index",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = _parse_args()
    index_name = (args.index_name or _default_index_name()).strip()
    if not args.yes:
        raise RuntimeError(f"Refusing to clear index '{index_name}' without explicit --yes confirmation")

    print(f"Clearing every document from index '{index_name}'...")
    client = SearchClient(
        endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
        index_name=index_name,
        credential=AzureKeyCredential(_required_env("AZURE_SEARCH_API_KEY")),
    )
    stats = clear_index(client, batch_size=args.batch_size)
    print(json.dumps({"index": index_name, **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
