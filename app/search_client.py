"""
Azure AI Search client factory for document retrieval.
Simplified version without Azure OpenAI dependency.
"""

import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient


def get_search_client() -> SearchClient:
    """
    Create and return an Azure AI Search client.
    
    Required environment variables:
    - AZURE_SEARCH_ENDPOINT: Azure Search service endpoint
    - AZURE_SEARCH_INDEX_NAME: Name of the search index
    - AZURE_SEARCH_API_KEY: API key for authentication
    
    Returns:
        Configured SearchClient instance
    """
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]
    
    return SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(api_key)
    )
