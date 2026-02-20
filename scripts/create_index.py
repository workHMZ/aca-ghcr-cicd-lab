"""
Script to create Azure AI Search index with vector search support.
Uses 384-dimensional vectors (matching sentence-transformers all-MiniLM-L6-v2).

ベクトル検索をサポートする Azure AI Search インデックスを作成するスクリプト。
384次元のベクトルを使用します（sentence-transformers all-MiniLM-L6-v2 と一致）。
"""

import os
import sys
# Add parent directory to sys.path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SearchableField, SimpleField, VectorSearch,
    VectorSearchProfile, HnswAlgorithmConfiguration
)
from app.embed import get_dimension

load_dotenv(override=True)

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
api_key = os.environ["AZURE_SEARCH_API_KEY"]


def create_index():
    """Create Azure AI Search index with hybrid search (vector + keyword) support. / ハイブリッド検索（ベクトル + キーワード）をサポートする Azure AI Search インデックスを作成します。"""
    client = SearchIndexClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key)
    )
    dim = get_dimension()  # 384 for all-MiniLM-L6-v2

    # Define fields
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="zh-Hans.microsoft"  # Chinese analyzer - interview bonus!
        ),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dim,  # Must be 384
            vector_search_profile_name="my-vector-profile"
        ),
        SearchableField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True
        ),
        SimpleField(
            name="createdAt",
            type=SearchFieldDataType.String
        )
    ]

    # Configure vector search algorithm (HNSW)
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="my-hnsw-config",
                kind="hnsw"
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="my-vector-profile",
                algorithm_configuration_name="my-hnsw-config"
            )
        ]
    )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search
    )

    print(f"Creating index '{index_name}' with dimension {dim}...")
    client.create_or_update_index(index)
    print("✅ Index created successfully!")


if __name__ == "__main__":
    create_index()
