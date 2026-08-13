"""Reusable Azure AI Search client factory."""

from functools import lru_cache

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from app.config import settings


@lru_cache(maxsize=1)
def get_search_client() -> SearchClient:
    """Create the process-wide synchronous Search client lazily."""

    endpoint = settings.azure_search_endpoint
    api_key = settings.azure_search_api_key
    if not endpoint or not api_key:
        raise RuntimeError("Azure AI Search is not configured")
    return SearchClient(
        endpoint=endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(api_key),
    )


def search_is_configured() -> bool:
    """Return whether all credentials required to construct a client exist."""

    return bool(settings.azure_search_endpoint and settings.azure_search_api_key)
