#!/usr/bin/env python3
"""Create the versioned Azure AI Search index used by the v3 corpus.

The command never updates or replaces an existing index by default. Passing
``--delete-existing`` is required before an index with the same name is
deleted and recreated.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from dotenv import load_dotenv

from app.embed import get_dimension

DEFAULT_INDEX_NAME = "ragdocs-v3"
HNSW_CONFIG_NAME = "hnsw-cosine"
VECTOR_PROFILE_NAME = "hnsw-cosine-profile"
SEMANTIC_CONFIGURATION_NAME = "rag-semantic"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _default_index_name() -> str:
    # Intentionally do not fall back to the legacy AZURE_SEARCH_INDEX_NAME.
    return os.getenv("AZURE_SEARCH_INDEX_NAME_V3", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME


def build_index(index_name: str, dimension: int) -> SearchIndex:
    """Build the multilingual hybrid-search schema without making API calls."""

    if dimension <= 0:
        raise ValueError("Embedding dimension must be greater than zero")

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="standard.lucene",
        ),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=dimension,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
        SearchableField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
            analyzer_name="standard.lucene",
        ),
        SimpleField(
            name="sourceId",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="pageNumber",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="chunkIndex",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="contentHash",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="embeddingModel",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="embeddingRevision",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="createdAt",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            sortable=True,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name=HNSW_CONFIG_NAME,
                parameters=HnswParameters(
                    metric="cosine",
                    m=4,
                    ef_construction=400,
                    ef_search=500,
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name=HNSW_CONFIG_NAME,
            )
        ],
    )
    semantic_search = SemanticSearch(
        default_configuration_name=SEMANTIC_CONFIGURATION_NAME,
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIGURATION_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="source")],
                ),
            )
        ],
    )
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def _index_exists(client: Any, index_name: str) -> bool:
    try:
        client.get_index(index_name)
    except ResourceNotFoundError:
        return False
    return True


def create_index(
    *,
    endpoint: str,
    api_key: str,
    index_name: str,
    dimension: int,
    delete_existing: bool = False,
) -> None:
    """Create a new index, optionally recreating an explicitly named index."""

    client = SearchIndexClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
    exists = _index_exists(client, index_name)

    if exists and not delete_existing:
        raise RuntimeError(
            f"Index '{index_name}' already exists; refusing to overwrite it. "
            "Choose a new versioned name or pass --delete-existing explicitly."
        )
    if exists:
        print(f"Deleting existing index '{index_name}' (--delete-existing was supplied)...")
        client.delete_index(index_name)

    index = build_index(index_name, dimension)
    print(f"Creating index '{index_name}' (dimension={dimension}, metric=cosine)...")
    client.create_index(index)
    print(f"Index '{index_name}' created successfully.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index-name",
        default=None,
        help="Target index (default: AZURE_SEARCH_INDEX_NAME_V3 or ragdocs-v3)",
    )
    parser.add_argument(
        "--delete-existing",
        action="store_true",
        help="Explicitly allow deletion and recreation when the target already exists",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = _parse_args()
    index_name = (args.index_name or _default_index_name()).strip()
    if not index_name:
        raise RuntimeError("Index name cannot be empty")

    create_index(
        endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
        api_key=_required_env("AZURE_SEARCH_API_KEY"),
        index_name=index_name,
        dimension=get_dimension(),
        delete_existing=args.delete_existing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
