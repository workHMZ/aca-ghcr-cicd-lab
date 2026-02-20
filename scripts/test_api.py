#!/usr/bin/env python3
"""
Test script for Azure Container Apps deployed RAG API.
Requires AZURE_ACCESS_TOKEN environment variable to be set for authenticated endpoints.

Azure Container Apps にデプロイされた RAG API のテストスクリプト。
認証付きエンドポイントには AZURE_ACCESS_TOKEN 環境変数が必要です。
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# API endpoint
API_URL = os.getenv("API_URL")
# Reasonable timeouts to avoid hanging forever
HEALTH_TIMEOUT_SECS = 10
QUERY_TIMEOUT_SECS = 30


def _get_token() -> str | None:
    token = os.getenv("AZURE_ACCESS_TOKEN")
    if token:
        token = token.strip()
    return token or None


def _auth_headers(token: str | None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _print_response_debug(resp: requests.Response) -> None:
    """Print helpful debug info without assuming JSON. / JSONを前提としないデバッグ情報を出力"""
    print(f"Status Code: {resp.status_code}")
    ct = resp.headers.get("content-type", "")
    print(f"Content-Type: {ct}")

    # Try JSON only when it really looks like JSON
    if "application/json" in ct.lower():
        try:
            print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
            return
        except Exception as e:
            print(f"(JSON parse failed: {type(e).__name__}: {e})")

    # Fallback: print text (truncate if huge)
    text = resp.text or ""
    if len(text) > 2000:
        text = text[:2000] + "\n... (truncated)"
    print(text if text else "(empty body)")


def test_health() -> bool:
    """Test the health endpoint. / ヘルスエンドポイントのテスト"""
    token = _get_token()
    headers = _auth_headers(token)

    print("\n🏥 GET /health")
    print("-" * 50)

    try:
        resp = requests.get(f"{API_URL}/health", headers=headers, timeout=HEALTH_TIMEOUT_SECS)
        _print_response_debug(resp)
        return resp.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Health request failed: {type(e).__name__}: {e}")
        return False


def test_query(question: str = "什么是 RAG？", top_k: int = 3) -> bool:
    """Test the query endpoint. / クエリエンドポイントのテスト"""
    token = _get_token()
    headers = _auth_headers(token)
    data = {"question": question, "top_k": top_k}

    print(f"\n🔍 POST /query")
    print(f"Question: {question}")
    print("-" * 50)

    try:
        resp = requests.post(f"{API_URL}/query", json=data, headers=headers, timeout=QUERY_TIMEOUT_SECS)

        if resp.status_code != 200:
            _print_response_debug(resp)
            return False

        # Expect JSON on 200
        result = resp.json()
        answer = result.get("answer", "No answer")
        contexts = result.get("contexts", []) or []

        print("✅ Success")
        print(f"\n📝 Answer:\n{answer}")

        print(f"\n📚 Contexts ({len(contexts)}):")
        for i, ctx in enumerate(contexts, 1):
            source = ctx.get("source", "unknown")
            score = ctx.get("score", None)
            score_str = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
            print(f"  {i}. [{source}] (score: {score_str})")

        return True

    except requests.exceptions.ReadTimeout:
        print(f"Query request timed out after {QUERY_TIMEOUT_SECS}s")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Query request failed: {type(e).__name__}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Testing Azure Container Apps RAG API")
    print("=" * 50)

    token = _get_token()
    if token:
        print("Auth: ✅ AZURE_ACCESS_TOKEN is set")
    else:
        print("Auth: ⚠️  AZURE_ACCESS_TOKEN is NOT set (health may 401; query will fail)")

    ok_health = test_health()
    ok_query = test_query()

    # Exit code helpful for CI
    sys.exit(0 if (ok_health and ok_query) else 1)
