"""
Serverless RAG API - FastAPI application with Azure AI Search integration.
Uses local sentence-transformers for embedding (no API costs).
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from azure.search.documents.models import VectorizedQuery
from app.embed import embed_text, get_dimension
from app.search_client import get_search_client

load_dotenv(override=True)

app = FastAPI(
    title="Serverless RAG API",
    description="RAG API using Azure AI Search with local sentence-transformers embedding",
    version="0.1.0"
)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to search for")
    top_k: int = Field(3, ge=1, le=10, description="Number of results to return")


class ContextHit(BaseModel):
    id: str
    source: str | None = None
    score: float | None = None
    content: str


class QueryResponse(BaseModel):
    answer: str
    contexts: list[ContextHit]


@app.get("/")
def root():
    """Root endpoint with service info."""
    return {
        "service": "Serverless RAG API",
        "version": "0.1.0",
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimension": get_dimension()
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "azure-rag-student"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """
    Query the RAG system using hybrid search (vector + keyword).
    
    Args:
        req: QueryRequest with question and top_k parameters
        
    Returns:
        QueryResponse with mock answer and retrieved contexts
    """
    # 1. Generate query vector using local embedding
    qvec = embed_text(req.question)
    
    # 2. Construct vector query for Azure AI Search
    vector_query = VectorizedQuery(
        vector=qvec,
        k_nearest_neighbors=req.top_k,
        fields="contentVector",
        exhaustive=True  # For small datasets, ensures best recall
    )
    
    search_client = get_search_client()
    
    # 3. Execute hybrid search (Vector + Keyword)
    try:
        results = search_client.search(
            search_text=req.question,  # Enables hybrid search
            vector_queries=[vector_query],
            top=req.top_k,
            select=["id", "content", "source", "createdAt"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    # 4. Format results
    contexts = []
    for r in results:
        contexts.append(ContextHit(
            id=r.get("id"),
            source=r.get("source"),
            score=r.get("@search.score"),
            content=r.get("content"),
        ))
    
    # Mock answer (integrate real LLM in next phase)
    mock_answer = f"基于检索到的 {len(contexts)} 个片段，我分析如下... (这里是 Mock 回答)"
    
    return QueryResponse(answer=mock_answer, contexts=contexts)
