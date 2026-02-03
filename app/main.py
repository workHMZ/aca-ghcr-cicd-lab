from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv

from app.embed import EmbeddingService
from app.search_client import SearchClient

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Serverless RAG API",
    description="Retrieval-Augmented Generation API using Azure AI Search",
    version="0.1.0"
)

# Initialize services
embedding_service = EmbeddingService()
search_client = SearchClient()


class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5


class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Serverless RAG API",
        "version": "0.1.0"
    }


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Query the RAG system
    
    Args:
        request: QueryRequest with query string and optional top_k parameter
    
    Returns:
        QueryResponse with answer and sources
    """
    try:
        # Generate query embedding
        query_embedding = embedding_service.embed_text(request.query)
        
        # Search for relevant documents
        search_results = search_client.search(
            query_embedding=query_embedding,
            top_k=request.top_k
        )
        
        # Generate answer using retrieved context
        answer = search_client.generate_answer(
            query=request.query,
            search_results=search_results
        )
        
        return QueryResponse(
            answer=answer,
            sources=search_results
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "services": {
            "embedding": embedding_service.is_available(),
            "search": search_client.is_available()
        }
    }
