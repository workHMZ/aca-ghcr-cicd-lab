"""
Script to clear all documents from Azure AI Search index.
Run this before re-ingesting to ensure clean state.
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

load_dotenv(override=True)

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
api_key = os.environ["AZURE_SEARCH_API_KEY"]


def clear_index():
    """Delete all documents from the index."""
    client = SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(api_key)
    )
    
    print(f"Clearing all documents from index '{index_name}'...")
    
    # Get all document IDs
    results = client.search(search_text="*", select=["id"], top=1000)
    doc_ids = [{"id": doc["id"]} for doc in results]
    
    if not doc_ids:
        print("⚠️ Index is already empty.")
        return
    
    print(f"Found {len(doc_ids)} documents to delete...")
    
    # Delete in batches
    batch_size = 100
    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i:i+batch_size]
        client.delete_documents(documents=batch)
        print(f"  Deleted batch {i//batch_size + 1} ({len(batch)} docs)")
    
    print("✅ Index cleared successfully!")


if __name__ == "__main__":
    clear_index()
