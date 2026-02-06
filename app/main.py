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

# ---- Build / version metadata (injected by CI/CD) ----
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
BUILD_SHA = os.getenv("BUILD_SHA", "unknown")
IMAGE_TAG = os.getenv("IMAGE_TAG", "unknown")
ENV_NAME = os.getenv("ENV_NAME", "unknown")  # optional: dev/stg/prod
SERVICE_NAME = os.getenv("SERVICE_NAME", "azure-rag-student")

def get_openai_client() -> OpenAI:
    """
    Lazily initialize OpenAI client so the app can start and /health can respond
    even if OPENAI_API_KEY is missing (useful during infra bring-up).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

app = FastAPI(
    title="Serverless RAG API",
    description="RAG API using Azure AI Search with local sentence-transformers embedding",
    version=APP_VERSION,
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
        "version": APP_VERSION,
        "build_sha": BUILD_SHA,
        "image_tag": IMAGE_TAG,
        "env": ENV_NAME,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimension": get_dimension(),
    }

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": APP_VERSION,
        "build_sha": BUILD_SHA,
        "image_tag": IMAGE_TAG,
        "env": ENV_NAME,
    }

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """
    Query the RAG system using hybrid search (vector + keyword).
    """
    # 1) Generate query vector using local embedding
    qvec = embed_text(req.question)

    # 2) Construct vector query for Azure AI Search
    vector_query = VectorizedQuery(
        vector=qvec,
        k_nearest_neighbors=req.top_k,
        fields="contentVector",
        exhaustive=True,
    )

    search_client = get_search_client()

    # 3) Execute hybrid search (Vector + Keyword)
    try:
        results = search_client.search(
            search_text=req.question,
            vector_queries=[vector_query],
            top=req.top_k,
            select=["id", "content", "source", "createdAt"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    # 4) Format results
    contexts: list[ContextHit] = []
    for r in results:
        contexts.append(
            ContextHit(
                id=r.get("id"),
                source=r.get("source"),
                score=r.get("@search.score"),
                content=r.get("content"),
            )
        )

    # 5) Generate answer using OpenAI gpt-5-mini
    if not contexts:
        answer = "抱歉，未能检索到相关信息来回答您的问题。"
    else:
        context_text = "\n\n".join(
            [f"[来源: {ctx.source or 'unknown'}]\n{ctx.content}" for ctx in contexts]
        )

        system_prompt = (
            "你是一个专业的问答助手。请根据提供的上下文信息来回答用户的问题。\n"
            "如果上下文中没有足够的信息来回答问题，请诚实地说明。没有就说我不知道。\n"
            "回答时请尽量准确、简洁，并引用相关来源。"
        )

        user_prompt = f"""上下文信息：
{context_text}

用户问题：{req.question}

请基于上述上下文信息回答问题。"""

        try:
            openai_client = get_openai_client()
            resp = openai_client.responses.create(
                model="gpt-5-mini",
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=1024,
                reasoning={"effort": "low"},
            )
            answer = resp.output_text
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OpenAI API call failed: {str(e)}")

    return QueryResponse(answer=answer, contexts=contexts)
