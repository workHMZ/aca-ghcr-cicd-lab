"""Pinned multilingual E5 embedding service."""

import threading
from typing import Any, Literal, cast

from sentence_transformers import SentenceTransformer

from app.config import settings

InputType = Literal["query", "passage"]
EMBEDDING_DIMENSION = 384

_MODEL: SentenceTransformer | None = None
_MODEL_LOCK = threading.Lock()
_ENCODE_LOCK = threading.Lock()


def _get_model() -> SentenceTransformer:
    """Load the pinned model once; /health stays independent of model loading."""

    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                source = settings.embedding_model_path or settings.embedding_model_name
                kwargs: dict[str, object] = {
                    "local_files_only": settings.embedding_offline,
                }
                if not settings.embedding_model_path:
                    kwargs["revision"] = settings.embedding_model_revision
                _MODEL = SentenceTransformer(source, **kwargs)
                _MODEL.max_seq_length = settings.embedding_query_max_tokens
                dimension = _MODEL.get_embedding_dimension()
                if dimension != EMBEDDING_DIMENSION:
                    _MODEL = None
                    raise RuntimeError(
                        f"Embedding model dimension must be {EMBEDDING_DIMENSION}, got {dimension}"
                    )
    return _MODEL


def _prefixed(text: str, input_type: InputType) -> str:
    return f"{input_type}: {text.strip()}"


def embed_text(text: str, *, input_type: InputType = "query") -> list[float]:
    """Embed one query or passage using the required E5 prefix."""

    if not text:
        return []
    with _ENCODE_LOCK:
        vector = _get_model().encode(
            _prefixed(text, input_type),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
    return cast(list[float], vector.tolist())


def embed_batch(texts: list[str], *, input_type: InputType = "passage") -> list[list[float]]:
    """Embed a batch with normalized vectors and consistent E5 prefixes."""

    if not texts:
        return []
    with _ENCODE_LOCK:
        vectors = _get_model().encode(
            [_prefixed(text, input_type) for text in texts],
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
    return cast(list[list[float]], vectors.tolist())


def embed_query(text: str) -> list[float]:
    """Embed a retrieval query."""

    return embed_text(text, input_type="query")


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed retrieval passages."""

    return embed_batch(texts, input_type="passage")


def get_dimension() -> int:
    """Return the dense embedding dimension."""

    return EMBEDDING_DIMENSION


def get_model_name() -> str:
    """Return the configured Hugging Face model identifier."""

    return settings.embedding_model_name


def get_model_revision() -> str:
    """Return the immutable model revision used for remote loading."""

    return settings.embedding_model_revision


def get_tokenizer() -> Any:
    """Expose the pinned model tokenizer for ingestion and evaluation."""

    return _get_model().tokenizer
