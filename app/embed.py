"""
Embedding service for text vectorization using sentence-transformers.
Uses all-MiniLM-L6-v2 model (~80MB) - runs locally, no API costs.
Vector dimension: 384
"""

import threading
from sentence_transformers import SentenceTransformer

_MODEL = None
_MODEL_LOCK = threading.Lock()

def _get_model() -> SentenceTransformer:
    """
    Lazy-load the model so the app can start quickly and /health responds
    even if the model needs to download on first use.
    """
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def embed_text(text: str) -> list[float]:
    """
    Generate semantic embedding vector for text.
    
    Model: all-MiniLM-L6-v2
    Dimension: 384
    
    Args:
        text: Input text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    if not text:
        return []
    # convert to list for JSON serialization
    model = _get_model()
    return model.encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.
    
    Args:
        texts: List of input texts to embed
        
    Returns:
        List of embedding vectors
    """
    if not texts:
        return []
    model = _get_model()
    return model.encode(texts).tolist()


def get_dimension() -> int:
    """Return embedding vector dimension."""
    return 384
