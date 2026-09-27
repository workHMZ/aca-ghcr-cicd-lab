"""Check exported SDK events with synthetic data and no external telemetry."""

import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import telemetry
from app.__main__ import main as entrypoint


def test_entrypoint_disables_automatic_content_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_TRACE_ENABLED", "true")
    monkeypatch.setenv("DD_TRACE_OPENAI_ENABLED", "true")
    execute = Mock()
    monkeypatch.setattr(os, "execvp", execute)
    entrypoint()
    assert os.environ["DD_TRACE_OPENAI_ENABLED"] == "false"
    assert execute.call_args.args[0] == "ddtrace-run"


def test_disabled_telemetry_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_LLMOBS_ENABLED", "false")
    with telemetry.observe("workflow", "test") as span:
        assert span is None
        telemetry.annotate(span, metrics={"count": 1})


def test_telemetry_failure_preserves_application_result(monkeypatch: pytest.MonkeyPatch) -> None:
    span = Mock()
    span.finish.side_effect = RuntimeError("writer unavailable")
    sdk = SimpleNamespace(workflow=Mock(return_value=span), annotate=Mock(side_effect=RuntimeError))
    monkeypatch.setattr(telemetry, "_sdk", lambda: sdk)
    with telemetry.observe("workflow", "test") as current:
        telemetry.annotate(current, tags={"cached": True})
    sdk.workflow.side_effect = RuntimeError("startup unavailable")
    with telemetry.observe("workflow", "test") as current:
        assert current is None


def test_cancellation_is_preserved_and_span_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    span = Mock()
    monkeypatch.setattr(telemetry, "_sdk", lambda: SimpleNamespace(workflow=lambda **_: span))
    with pytest.raises(asyncio.CancelledError):
        with telemetry.observe("workflow", "test"):
            raise asyncio.CancelledError("private request")
    span.finish.assert_called_once()
    span.set_tag.assert_any_call("error.type", "CancelledError")
    assert "private request" not in str(span.mock_calls)


def test_real_sdk_exports_one_llm_call_with_tokens_and_no_content() -> None:
    # Isolate ddtrace's process-global hooks. Writers are intercepted before any
    # synthetic request, so this test needs neither an Agent nor provider keys.
    code = r"""
import asyncio
import json
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from ddtrace import tracer
from ddtrace.llmobs import LLMObs
from app import main

assert LLMObs.enabled
import openai
assert not getattr(openai, "__datadog_patch", False)
events = []
original = LLMObs._instance._llmobs_span_event

def capture(span):
    event = original(span)
    events.append(event)
    return event

LLMObs._instance._llmobs_span_event = capture
tracer._span_aggregator.writer.write = lambda *a, **k: None
LLMObs._instance._llmobs_span_writer.enqueue = lambda *a, **k: None

body = {
    "id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
    "model": "gpt-5.6-terra",
    "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "annotations": [], "text": json.dumps({
            "answer": "PRIVATE_ANSWER [1]", "citations": [1], "grounded": True})}]}],
    "usage": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27,
        "input_tokens_details": {"cached_tokens": 4}, "output_tokens_details": {"reasoning_tokens": 2}}
}
provider = AsyncOpenAI(api_key="synthetic", max_retries=0,
    http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
result = {"id": "private_id", "source": "PRIVATE_SOURCE", "title": "PRIVATE_TITLE",
    "content": "PRIVATE_EVIDENCE", "embeddingModel": main.get_model_name(),
    "embeddingRevision": main.get_model_revision(), "embeddingVariant": main.get_embedding_variant(),
    "@search.reranker_score": 2.7}
class Search:
    def search(self, **kwargs):
        return [result]

main.answer_cache.clear()
main.query_budget.reset()
client = TestClient(main.app)
with patch.object(main, "embed_query", return_value=[0.1] * 384), \
     patch.object(main, "get_search_client", return_value=Search()), \
     patch.object(main, "get_openai_client", return_value=provider):
    first = client.post("/query", json={"question": "PRIVATE_QUESTION", "language": "en"})
    assert first.status_code == 200, first.text
    second = client.post("/query", json={"question": "PRIVATE_QUESTION", "language": "en"})
    assert second.json()["metadata"]["cached"] is True
    assert second.json()["metadata"]["usage"] is None
    with patch.object(main, "_search", return_value=[]):
        assert client.post("/query", json={"question": "PRIVATE_NO_EVIDENCE"}).status_code == 200
    with patch.object(main, "_search", side_effect=RuntimeError("PRIVATE_EXCEPTION")):
        assert client.post("/query", json={"question": "PRIVATE_ERROR"}).status_code == 503

assert all(event for event in events)
llms = [event for event in events if event["meta"]["span"]["kind"] == "llm"]
assert len(llms) == 1, llms
llm = llms[0]
assert llm["metrics"]["input_tokens"] == 20
assert llm["metrics"]["output_tokens"] == 7
assert llm["metrics"]["total_tokens"] == 27
assert llm["metrics"]["cache_read_input_tokens"] == 4
assert llm["metrics"]["reasoning_output_tokens"] == 2
assert llm["duration"] > 0
root = next(e for e in events if e["name"] == "rag.query")
children = [e for e in events if e["parent_id"] == root["span_id"]]
assert {e["name"] for e in children} == {"rag.embed", "rag.search", "rag.generate"}, children
assert all(e["trace_id"] == root["trace_id"] for e in children)
assert any("rag.cached:True" in e["tags"] for e in events)
assert any("rag.no_evidence:True" in e["tags"] for e in events)
assert any(e["status"] == "error" for e in events)
assert "PRIVATE_" not in json.dumps(events), events
assert all(not e["meta"].get("input") and not e["meta"].get("output") for e in events)
print("SDK export verified: hierarchy, tokens, cache, no evidence, errors, no content")
"""
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.getcwd(),
        "DD_TRACE_ENABLED": "true",
        "DD_LLMOBS_ENABLED": "true",
        "DD_LLMOBS_ML_APP": "rag-test",
        "DD_LLMOBS_AGENTLESS_ENABLED": "false",
        "DD_TRACE_OPENAI_ENABLED": "false",
        "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
        "DD_REMOTE_CONFIGURATION_ENABLED": "false",
        "DD_TRACE_AGENT_URL": "http://127.0.0.1:1",
    }
    result = subprocess.run(  # noqa: S603 - fixed synthetic test script, no shell
        [sys.executable, "-c", "import ddtrace.auto\n" + code],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
