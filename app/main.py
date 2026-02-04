"""
Serverless RAG API - FastAPI application with Azure AI Search integration.
Uses local sentence-transformers for embedding (no API costs).
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from azure.search.documents.models import VectorizedQuery
from openai import OpenAI
from app.embed import embed_text, get_dimension
from app.search_client import get_search_client

load_dotenv(override=True)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    
    # 5. Generate answer using OpenAI gpt-5-mini
    if not contexts:
        answer = "抱歉，未能检索到相关信息来回答您的问题。"
    else:
        # Build context string from retrieved documents
        context_text = "\n\n".join([
            f"[来源: {ctx.source or 'unknown'}]\n{ctx.content}" 
            for ctx in contexts
        ])
        
        # Create prompt for RAG
        system_prompt = """你是一个专业的问答助手。请根据提供的上下文信息来回答用户的问题。
如果上下文中没有足够的信息来回答问题，请诚实地说明。没有就说我不知道。
回答时请尽量准确、简洁，并引用相关来源。"""
        
        user_prompt = f"""上下文信息：
{context_text}

用户问题：{req.question}

请基于上述上下文信息回答问题。"""

        try:
            completion = openai_client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_completion_tokens=1024  # gpt-5-mini requires this instead of max_tokens
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OpenAI API call failed: {str(e)}")

    return QueryResponse(answer=answer, contexts=contexts)
