"""
Serverless RAG API - FastAPI application with Azure AI Search integration.
Uses local sentence-transformers for embedding (no API costs).

サーバーレス RAG API - Azure AI Search と統合された FastAPI アプリケーション。
ローカルの sentence-transformers を使用して埋め込みを行います（APIコストゼロ）。
"""

import os
import sys
import logging
from typing import Any

from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from azure.search.documents.models import VectorizedQuery
from openai import OpenAI

from app.embed import embed_text, get_dimension
from app.search_client import get_search_client


# ---- Build / version metadata (injected by CI/CD) ----
APP_VERSION = os.getenv("APP_VERSION", "2.1.0")
BUILD_SHA = os.getenv("BUILD_SHA", "unknown")
IMAGE_TAG = os.getenv("IMAGE_TAG", "unknown")
ENV_NAME = os.getenv("ENV_NAME", os.getenv("DD_ENV", "stg"))  # optional: dev/stg/prod
SERVICE_NAME = os.getenv("SERVICE_NAME", os.getenv("DD_SERVICE", "azure-rag-student"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1024"))
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
OPENAI_VERBOSITY = os.getenv("OPENAI_VERBOSITY", "medium")

_REASONING_EFFORT_ALLOWED = {"none", "minimal", "low", "medium", "high", "xhigh"}
_VERBOSITY_ALLOWED = {"low", "medium", "high"}


def _normalize_choice(value: str, allowed: set[str], default: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in allowed else default


def _safe_get_dd_correlation() -> dict[str, str]:
    """
    Safely return Datadog log correlation fields.
    Works when running under ddtrace-run; returns empty dict otherwise.
    
    Datadogのログ相関フィールド（Trace ID, Span ID等）を安全に返します。
    ddtrace-runのスコープ内で実行されている場合に機能し、それ以外の場合は空の辞書を返します。
    """
    try:
        import ddtrace  # type: ignore

        # Official correlation API: includes trace_id/span_id + service/env/version (if set)
        ctx = ddtrace.tracer.get_log_correlation_context() or {}
        out: dict[str, str] = {}
        # ddtrace returns strings already in many cases, but be defensive
        trace_id = ctx.get("trace_id")
        span_id = ctx.get("span_id")
        if trace_id:
            out["dd.trace_id"] = str(trace_id)
        if span_id:
            out["dd.span_id"] = str(span_id)

        # These are helpful for Logs in Context and unified service tagging
        service = ctx.get("service")
        env = ctx.get("env")
        version = ctx.get("version")
        if service:
            out["dd.service"] = str(service)
        if env:
            out["dd.env"] = str(env)
        if version:
            out["dd.version"] = str(version)

        return out
    except Exception:
        # Never let correlation break your app logging
        return {}


class DatadogJsonFormatter(jsonlogger.JsonFormatter):
    """
    JSON formatter that injects Datadog correlation fields + basic logger metadata.
    
    Datadogの相関フィールドと基本的なロガーメタデータを注入するカスタムJSONフォーマッター。
    """

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)

        # Always include stable service metadata (even if not inside a trace)
        log_record.setdefault("dd.service", os.getenv("DD_SERVICE", SERVICE_NAME))
        log_record.setdefault("dd.env", os.getenv("DD_ENV", ENV_NAME))
        log_record.setdefault("dd.version", os.getenv("DD_VERSION", APP_VERSION))

        # Inject correlation fields if available (trace/span + potentially overrides)
        log_record.update(_safe_get_dd_correlation())

        # Standard fields
        log_record["logger.name"] = record.name
        log_record["logger.thread_name"] = record.threadName
        log_record["logger.method_name"] = record.funcName
        log_record["logger.filename"] = record.filename
        log_record["logger.lineno"] = record.lineno
        log_record["process.pid"] = record.process
        log_record["process.name"] = record.processName


def _configure_logging() -> None:
    """
    Configure JSON logging once, avoid duplicate handlers, and unify uvicorn logs.
    
    JSONロギングを一度だけ設定し、ハンドラーの重複を防ぎ、uvicornのログ出力を一元化します。
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid adding multiple handlers if module is imported multiple times
    for h in list(root.handlers):
        if getattr(h, "_is_datadog_json", False):
            return  # already configured

    handler = logging.StreamHandler(stream=sys.stdout)
    handler._is_datadog_json = True  # type: ignore[attr-defined]

    # Keep format minimal; jsonlogger controls fields
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handler.setFormatter(DatadogJsonFormatter(fmt))

    # Replace handlers to avoid duplicates from uvicorn/gunicorn defaults
    root.handlers = [handler]

    # Unify uvicorn loggers to use root handler
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(logging.INFO)


# Configure logging immediately at import time
_configure_logging()
logger = logging.getLogger(__name__)

load_dotenv(override=True)


def get_openai_client() -> OpenAI:
    """
    Lazily initialize OpenAI client so the app can start and /health can respond
    even if OPENAI_API_KEY is missing (useful during infra bring-up).
    
    OpenAIクライアントを遅延初期化します。これにより、環境変数OPENAI_API_KEYが不足している場合でも、
    アプリケーションの起動と/healthエンドポイントへの応答が可能になります。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


app = FastAPI(
    title="Serverless RAG API",
    description="RAG API using Azure AI Search with local sentence-transformers embedding (Azure AI Search とローカルの sentence-transformers を使用した RAG API)",
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
    """Root endpoint with service info. / サービス情報を提供するルートエンドポイント"""
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
    """Health check endpoint. / ヘルスチェックエンドポイント"""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": APP_VERSION,
        "build_sha": BUILD_SHA,
        "image_tag": IMAGE_TAG,
        "env": ENV_NAME,
    }


@app.get("/warmup")
def warmup():
    """Warm up the embedding model so the first /query is fast. / 初回の /query 応答を高速化するため、埋め込みモデルをウォームアップします"""
    try:
        _ = embed_text("warmup")
        return {"status": "ok", "embedding_dimension": get_dimension()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Warmup failed: {str(e)}")


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """
    Query the RAG system using hybrid search (vector + keyword).
    
    ハイブリッド検索（ベクトル検索 + キーワード検索）を使用して、RAGシステムにクエリを実行します。
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
            [
                f"[{i + 1}] 来源: {ctx.source or 'unknown'}\n{ctx.content}"
                for i, ctx in enumerate(contexts)
            ]
        )

        system_prompt = (
            "你是一个专业的问答助手。只根据提供的上下文信息回答问题，禁止编造。\n"
            "如果上下文不足以回答，请直接说“我不知道”，或提出一个最关键的追问。\n"
            "回答要求：先给结论，再给要点；引用来源用编号，如 [1]、[2]。"
        )

        user_prompt = f"""上下文信息（已编号）：
{context_text}

用户问题：{req.question}

请基于上述上下文信息回答问题。"""

        try:
            logger.info(
                "Calling OpenAI to generate answer",
                extra={"question": req.question, "context_count": len(contexts)},
            )

            openai_client = get_openai_client()
            reasoning_effort = _normalize_choice(OPENAI_REASONING_EFFORT, _REASONING_EFFORT_ALLOWED, "medium")
            verbosity = _normalize_choice(OPENAI_VERBOSITY, _VERBOSITY_ALLOWED, "medium")

            request: dict[str, Any] = {
                "model": OPENAI_MODEL,
                "instructions": system_prompt,
                "input": user_prompt,
                "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
            }

            if OPENAI_MODEL.startswith("gpt-5"):
                request["reasoning"] = {"effort": reasoning_effort}
                request["text"] = {"verbosity": verbosity}

            resp = openai_client.responses.create(**request)
            answer = resp.output_text

            logger.info("Successfully generated answer", extra={"output_length": len(answer)})
        except Exception as e:
            logger.error("OpenAI API call failed", exc_info=True)
            raise HTTPException(status_code=500, detail=f"OpenAI API call failed: {str(e)}")

    return QueryResponse(answer=answer, contexts=contexts)
