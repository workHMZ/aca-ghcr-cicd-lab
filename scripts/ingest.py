"""
Script to ingest documents (PDF/MD) into Azure AI Search.
Reads files from data/ directory, chunks them, and uploads with embeddings.
"""

import os
import sys
import glob
from uuid import uuid4
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from pypdf import PdfReader
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from app.embed import embed_text

load_dotenv(override=True)

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
api_key = os.environ["AZURE_SEARCH_API_KEY"]


def read_pdf(path: str) -> str:
    """Extract text from PDF file."""
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def chunk_text(text: str, size: int = 500) -> list[str]:
    """
    Split text into chunks of specified size.
    For production, use LangChain's RecursiveCharacterTextSplitter.
    """
    return [text[i:i+size] for i in range(0, len(text), size)]


def main():
    """Main ingestion workflow."""
    client = SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(api_key)
    )
    
    # Get data directory path (relative to project root)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data")
    
    # Scan data directory
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))
    md_files = glob.glob(os.path.join(data_dir, "*.md"))
    txt_files = glob.glob(os.path.join(data_dir, "*.txt"))
    files = pdf_files + md_files + txt_files
    
    docs_to_upload = []
    
    print(f"Found {len(files)} files in {data_dir}")
    
    for file_path in files:
        filename = os.path.basename(file_path)
        print(f"Processing {filename}...")
        
        # Read file content
        if file_path.endswith(".pdf"):
            content = read_pdf(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # Chunk the content
        chunks = chunk_text(content)
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            
            doc = {
                "id": str(uuid4()),  # Generate unique ID
                "content": chunk,
                "contentVector": embed_text(chunk),
                "source": filename,
                "createdAt": datetime.now().isoformat()
            }
            docs_to_upload.append(doc)
    
    if docs_to_upload:
        print(f"\nUploading {len(docs_to_upload)} chunks...")
        # Batch upload
        client.upload_documents(documents=docs_to_upload)
        print("✅ Ingestion complete!")
    else:
        print("⚠️ No documents to upload.")
        print(f"   Please add PDF/MD/TXT files to: {data_dir}")


if __name__ == "__main__":
    main()
