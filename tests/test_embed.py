from __future__ import annotations

from typing import Any

import pytest

from app import embed


class FakeVector:
    def __init__(self, value: Any) -> None:
        self.value = value

    def tolist(self) -> Any:
        return self.value


class FakeModel:
    tokenizer = object()

    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def encode(self, value: Any, **kwargs: Any) -> FakeVector:
        self.calls.append((value, kwargs))
        if isinstance(value, list):
            return FakeVector([[1.0, 0.0] for _ in value])
        return FakeVector([1.0, 0.0])


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    model = FakeModel()
    monkeypatch.setattr(embed, "_MODEL", model)
    return model


def test_embed_query_adds_e5_prefix_and_normalizes(fake_model: FakeModel) -> None:
    vector = embed.embed_query("  HashMap  ")

    assert vector == [1.0, 0.0]
    value, kwargs = fake_model.calls[0]
    assert value == "query: HashMap"
    assert kwargs["normalize_embeddings"] is True
    assert kwargs["convert_to_numpy"] is True


def test_embed_passages_batches_with_passage_prefix(fake_model: FakeModel) -> None:
    vectors = embed.embed_passages(["first", " second "])

    assert vectors == [[1.0, 0.0], [1.0, 0.0]]
    assert fake_model.calls[0][0] == ["passage: first", "passage: second"]


def test_empty_embedding_inputs_do_not_load_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embed, "_MODEL", None)
    assert embed.embed_text("") == []
    assert embed.embed_batch([]) == []


def test_embedding_metadata(fake_model: FakeModel) -> None:
    assert embed.get_dimension() == 384
    assert embed.get_model_name() == "intfloat/multilingual-e5-small"
    assert len(embed.get_model_revision()) == 40
    assert embed.get_tokenizer() is fake_model.tokenizer
