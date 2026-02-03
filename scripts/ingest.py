"""
Script to ingest documents into Azure AI Search
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
import sys

# Add parent directory to path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.embed import EmbeddingService

# Load environment variables
load_dotenv()


def load_documents(data_dir: str = "data") -> List[Dict[str, Any]]:
    """
    Load documents from data directory
    
    Args:
        data_dir: Directory containing document files
    
    Returns:
        List of document dictionaries
    """
    documents = []
    data_path = Path(__file__).parent.parent / data_dir
    
    if not data_path.exists():
        print(f"⚠ Data directory '{data_path}' does not exist")
        return documents
    
    # Process all text and JSON files
    for file_path in data_path.glob("**/*"):
        if file_path.is_file() and file_path.suffix in [".txt", ".json", ".md"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
                documents.append({
                    "title": file_path.stem,
                    "content": content,
                    "metadata": json.dumps({
                        "filename": file_path.name,
                        "path": str(file_path.relative_to(data_path))
                    })
                })
    
    return documents


def ingest_documents(documents: List[Dict[str, Any]]):
    """
    Ingest documents into Azure AI Search with embeddings
    
    Args:
        documents: List of document dictionaries
    """
    if not documents:
        print("⚠ No documents to ingest")
        return
    
    # Initialize services
    embedding_service = EmbeddingService()
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY"))
    )
    
    print(f"Processing {len(documents)} documents...")
    
    # Prepare documents with embeddings
    indexed_documents = []
    for i, doc in enumerate(documents, 1):
        print(f"  [{i}/{len(documents)}] Embedding: {doc['title']}")
        
        # Generate embedding for content
        embedding = embedding_service.embed_text(doc["content"])
        
        indexed_documents.append({
            "id": str(i),
            "title": doc["title"],
            "content": doc["content"],
            "content_vector": embedding,
            "metadata": doc.get("metadata", "{}")
        })
    
    # Upload documents to search index
    print(f"\nUploading {len(indexed_documents)} documents to search index...")
    try:
        result = search_client.upload_documents(documents=indexed_documents)
        succeeded = sum(1 for r in result if r.succeeded)
        print(f"✓ Successfully indexed {succeeded}/{len(indexed_documents)} documents")
    except Exception as e:
        print(f"✗ Error uploading documents: {e}")
        raise


def main():
    """Main ingestion workflow"""
    print("=== Document Ingestion Script ===\n")
    
    # Load documents
    print("Loading documents from data directory...")
    documents = load_documents()
    print(f"✓ Loaded {len(documents)} documents\n")
    
    # Ingest documents
    if documents:
        ingest_documents(documents)
    else:
        print("⚠ No documents found. Please add files to the 'data/' directory.")


if __name__ == "__main__":
    main()
