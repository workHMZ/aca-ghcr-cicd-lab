"""
Azure AI Search client factory for document retrieval.
Simplified version without Azure OpenAI dependency.

ドキュメント検索のための Azure AI Search クライアントファクトリ。
Azure OpenAI への依存関係のない簡易バージョンです。
"""

import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient


def get_search_client() -> SearchClient:
    """
    Create and return an Azure AI Search client.
    Azure AI Search クライアントを作成して返します。
    
    Required environment variables (必須環境変数):
    - AZURE_SEARCH_ENDPOINT: Azure Search service endpoint
    - AZURE_SEARCH_INDEX_NAME: Name of the search index
    - AZURE_SEARCH_API_KEY: API key for authentication
    
    Returns:
        Configured SearchClient instance (設定済みの SearchClient インスタンス)
    """
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]
    
    return SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(api_key)
    )
