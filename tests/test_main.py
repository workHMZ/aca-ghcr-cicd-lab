from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def test_root_and_health_expose_reproducible_metadata(client: TestClient) -> None:
    root = client.get("/")
    health = client.get("/health")

    assert root.status_code == 200
    assert root.json()["version"] == "3.0.0"
    assert root.json()["embedding_model"] == "intfloat/multilingual-e5-small"
    assert root.json()["embedding_dimension"] == 384
    assert root.json()["openai_model"] == "gpt-5.6-terra"
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_ready_checks_configuration_and_local_model(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "search_is_configured", lambda: True)
    monkeypatch.setattr(main.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(main, "embed_query", lambda _text: [0.0] * 384)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_returns_stable_503_without_configuration(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "search_is_configured", lambda: False)
    monkeypatch.setattr(main.settings, "openai_api_key", None)
    monkeypatch.setattr(main, "embed_query", lambda _text: [0.0] * 384)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["missing"] == ["azure_search", "openai"]


def test_warmup_hides_internal_embedding_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_text: str) -> list[float]:
        raise RuntimeError("secret internal path")

    monkeypatch.setattr(main, "embed_query", fail)
    response = client.get("/warmup")

    assert response.status_code == 503
    assert "secret internal path" not in response.text


def test_query_without_context_skips_generation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "embed_query", lambda _text: [0.0] * 384)
    monkeypatch.setattr(main, "_search", lambda *_args: [])

    response = client.post("/query", json={"question": "unknown topic", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["answer"].startswith("I'm sorry")
    assert response.json()["contexts"] == []
    assert response.json()["metadata"]["grounded"] is False


def test_query_returns_context_metadata_and_structured_generation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = [
        main.ContextHit(
            id="chunk-1",
            source="guide.pdf",
            score=0.9,
            content="HashMap uses buckets.",
        )
    ]

    async def generated(_question: str, received: list[main.ContextHit]) -> tuple[str, main.QueryMetadata]:
        assert received == contexts
        return (
            "It uses buckets [1].",
            main.QueryMetadata(model="gpt-5.6-terra", grounded=True, citations=[1]),
        )

    monkeypatch.setattr(main, "embed_query", lambda _text: [0.0] * 384)
    monkeypatch.setattr(main, "_search", lambda *_args: contexts)
    monkeypatch.setattr(main, "_generate_answer", generated)

    response = client.post("/query", json={"question": "How does HashMap work?", "top_k": 1})

    assert response.status_code == 200
    assert response.json()["answer"] == "It uses buckets [1]."
    assert response.json()["metadata"]["citations"] == [1]
    assert response.json()["metadata"]["model"] == "gpt-5.6-terra"


def test_search_rejects_embedding_metadata_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    class SearchClient:
        def search(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "id": "legacy",
                    "content": "old vector",
                    "embeddingModel": "sentence-transformers/all-MiniLM-L6-v2",
                    "embeddingRevision": "legacy",
                }
            ]

    monkeypatch.setattr(main, "get_search_client", SearchClient)
    with pytest.raises(RuntimeError, match="embedding metadata"):
        main._search("question", [0.0] * 384, 1)


def test_query_validates_input_boundaries(client: TestClient) -> None:
    assert client.post("/query", json={"question": "", "top_k": 3}).status_code == 422
    assert client.post("/query", json={"question": "x", "top_k": 11}).status_code == 422
    assert client.post("/query", json={"question": "x" * 8_001, "top_k": 3}).status_code == 422


def test_query_maps_retrieval_and_generation_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "embed_query", lambda _text: [0.0] * 384)
    monkeypatch.setattr(main, "_search", lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))
    retrieval = client.post("/query", json={"question": "question", "top_k": 3})
    assert retrieval.status_code == 503
    assert "boom" not in retrieval.text

    context = main.ContextHit(id="1", source="a", score=1.0, content="context")
    monkeypatch.setattr(main, "_search", lambda *_args: [context])

    async def generation_failure(*_args: Any) -> tuple[str, main.QueryMetadata]:
        raise RuntimeError("provider detail")

    monkeypatch.setattr(main, "_generate_answer", generation_failure)
    generation = client.post("/query", json={"question": "question", "top_k": 3})
    assert generation.status_code == 502
    assert "provider detail" not in generation.text


@pytest.mark.asyncio
async def test_generate_answer_uses_terra_structured_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    parsed = main.GeneratedAnswer(answer="Grounded [1].", citations=[1, 99, 1], grounded=True)
    response = SimpleNamespace(
        id="resp_test",
        model="gpt-5.6-terra",
        status="completed",
        output=[],
        output_parsed=parsed,
        usage=SimpleNamespace(
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            input_tokens_details=SimpleNamespace(cached_tokens=4),
            output_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )

    class Responses:
        async def parse(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return response

    fake_client = SimpleNamespace(responses=Responses())
    monkeypatch.setattr(main, "get_openai_client", lambda: fake_client)
    contexts = [main.ContextHit(id="1", source="guide", score=1.0, content="fact")]

    answer, metadata = await main._generate_answer("question", contexts)

    assert answer == "Grounded [1]."
    assert metadata.citations == [1]
    assert metadata.usage is not None
    assert metadata.usage.cached_input_tokens == 4
    assert metadata.usage.reasoning_tokens == 2
    assert captured["model"] == "gpt-5.6-terra"
    assert captured["reasoning"]["effort"] == "low"
    assert captured["store"] is False
    assert captured["text_format"] is main.GeneratedAnswer


@pytest.mark.asyncio
async def test_generate_answer_replaces_unsupported_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = main.GeneratedAnswer(answer="Invented answer", citations=[], grounded=False)
    response = SimpleNamespace(
        id="resp_test",
        model="gpt-5.6-terra",
        status="completed",
        output=[],
        output_parsed=parsed,
        usage=None,
    )

    class Responses:
        async def parse(self, **_kwargs: Any) -> Any:
            return response

    monkeypatch.setattr(main, "get_openai_client", lambda: SimpleNamespace(responses=Responses()))
    answer, metadata = await main._generate_answer(
        "unsupported question",
        [main.ContextHit(id="1", source="guide", score=1.0, content="unrelated")],
    )

    assert answer.startswith("I'm sorry")
    assert metadata.grounded is False
    assert metadata.citations == []


@pytest.mark.asyncio
async def test_generate_answer_rejects_incomplete_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        id="resp_test",
        model="gpt-5.6-terra",
        status="incomplete",
        output=[],
        output_parsed=None,
        usage=None,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )

    class Responses:
        async def parse(self, **_kwargs: Any) -> Any:
            return response

    monkeypatch.setattr(main, "get_openai_client", lambda: SimpleNamespace(responses=Responses()))

    with pytest.raises(RuntimeError, match="incomplete"):
        await main._generate_answer(
            "question",
            [main.ContextHit(id="1", source="guide", score=1.0, content="fact")],
        )
