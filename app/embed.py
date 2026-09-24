"""Pinned multilingual E5 embeddings served by ONNX Runtime.

The service runs the ONNX export published in the pinned Hugging Face
revision instead of PyTorch. That removes torch/transformers from the image,
cuts cold-start time, and lets a 0.5 vCPU / 1 GiB replica serve queries.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np

from app.config import settings
from app.model_manifest import (
    EMBEDDING_DIMENSION,
    MODEL_FILES,
    TOKENIZER_FILE,
    default_model_dir,
    ensure_model_files,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from tokenizers import Tokenizer

InputType = Literal["query", "passage"]

# XLM-RoBERTa special tokens used by the E5 tokenizer.
_PAD_TOKEN = "<pad>"  # noqa: S105 - tokenizer special token, not a secret
_PAD_ID = 1


class OnnxEmbedder:
    """Mean-pooled, L2-normalised E5 embeddings from an ONNX session."""

    def __init__(self, model_dir: Path, *, model_file: str, threads: int, max_tokens: int) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        # Size the pool explicitly: ONNX Runtime otherwise spawns one thread per
        # host core, which oversubscribes a CPU-quota-limited container.
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(model_dir / model_file),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {model_input.name for model_input in self._session.get_inputs()}
        # Configured once: mutating truncation per call would race between threads.
        self._tokenizer: Tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE.local_name))
        self._tokenizer.enable_truncation(max_length=max_tokens)
        self._tokenizer.enable_padding(pad_id=_PAD_ID, pad_token=_PAD_TOKEN)

    def encode(self, texts: list[str], *, batch_size: int) -> NDArray[np.float32]:
        batches: list[NDArray[np.float32]] = []
        for offset in range(0, len(texts), batch_size):
            encodings = self._tokenizer.encode_batch(texts[offset : offset + batch_size])
            input_ids = np.asarray([encoding.ids for encoding in encodings], dtype=np.int64)
            attention_mask = np.asarray([encoding.attention_mask for encoding in encodings], dtype=np.int64)
            feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.zeros_like(input_ids)
            hidden = self._session.run(["last_hidden_state"], feeds)[0]
            mask = attention_mask[..., None].astype(np.float32)
            pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
            norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            batches.append((pooled / norms).astype(np.float32))
        return np.vstack(batches)


_EMBEDDER: OnnxEmbedder | None = None
_LOAD_LOCK = threading.Lock()


def model_dir() -> Path:
    return Path(settings.embedding_model_path) if settings.embedding_model_path else default_model_dir()


def _get_embedder() -> OnnxEmbedder:
    """Load the pinned model once; /health stays independent of model loading."""

    global _EMBEDDER
    if _EMBEDDER is None:
        with _LOAD_LOCK:
            if _EMBEDDER is None:
                directory = ensure_model_files(
                    model_dir(),
                    settings.embedding_variant,
                    allow_download=not settings.embedding_offline,
                )
                embedder = OnnxEmbedder(
                    directory,
                    model_file=MODEL_FILES[settings.embedding_variant].local_name,
                    threads=settings.embedding_threads,
                    max_tokens=settings.embedding_max_tokens,
                )
                probe = embedder.encode(["query: dimension probe"], batch_size=1)
                if probe.shape[1] != EMBEDDING_DIMENSION:
                    raise RuntimeError(
                        f"Embedding model dimension must be {EMBEDDING_DIMENSION}, got {probe.shape[1]}"
                    )
                _EMBEDDER = embedder
    return _EMBEDDER


def load_model() -> None:
    """Eagerly load the model (used by the startup preloader and /warmup)."""

    _get_embedder()


def is_loaded() -> bool:
    return _EMBEDDER is not None


def _prefixed(text: str, input_type: InputType) -> str:
    return f"{input_type}: {text.strip()}"


def embed_text(text: str, *, input_type: InputType = "query") -> list[float]:
    """Embed one query or passage using the required E5 prefix."""

    if not text:
        return []
    vectors = _get_embedder().encode([_prefixed(text, input_type)], batch_size=1)
    return [float(value) for value in vectors[0]]


def embed_batch(texts: list[str], *, input_type: InputType = "passage") -> list[list[float]]:
    """Embed a batch with normalized vectors and consistent E5 prefixes."""

    if not texts:
        return []
    vectors = _get_embedder().encode(
        [_prefixed(text, input_type) for text in texts],
        batch_size=settings.embedding_batch_size,
    )
    return [[float(value) for value in vector] for vector in vectors]


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


def get_embedding_variant() -> str:
    """Return the runtime/quantisation variant that produced the vectors."""

    return settings.embedding_variant


def get_tokenizer() -> Tokenizer:
    """Return a fresh pinned tokenizer (no padding/truncation) for chunking."""

    from tokenizers import Tokenizer

    directory = ensure_model_files(
        model_dir(),
        settings.embedding_variant,
        allow_download=not settings.embedding_offline,
    )
    return Tokenizer.from_file(str(directory / TOKENIZER_FILE.local_name))
