"""
Script to create Azure AI Search index
"""

import os
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    SearchFieldDataType
)
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def create_search_index():
    """Create the search index with vector search capabilities"""
    
    # Initialize the index client
    index_client = SearchIndexClient(
        endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY"))
    )
    
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")
    
    # Define the index schema
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True
        ),
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", 1536)),
            vector_search_profile_name="my-vector-profile"
        ),
        SimpleField(
            name="metadata",
            type=SearchFieldDataType.String,
            filterable=True
        )
    ]
    
    # Configure vector search
    vector_search = VectorSearch(
        profiles=[
            VectorSearchProfile(
                name="my-vector-profile",
                algorithm_configuration_name="my-hnsw-config"
            )
        ],
        algorithms=[
            HnswAlgorithmConfiguration(name="my-hnsw-config")
        ]
    )
    
    # Create the index
    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search
    )
    
    try:
        result = index_client.create_or_update_index(index)
        print(f"✓ Index '{result.name}' created successfully!")
        return result
    except Exception as e:
        print(f"✗ Error creating index: {e}")
        raise


if __name__ == "__main__":
    create_search_index()
