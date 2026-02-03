"""
Embedding service for text vectorization using sentence-transformers.
Uses all-MiniLM-L6-v2 model (~80MB) - runs locally, no API costs.
Vector dimension: 384
"""

from sentence_transformers import SentenceTransformer

# Load model once at module level for efficiency
# First run will auto-download (~80MB), cached locally afterward
model = SentenceTransformer('all-MiniLM-L6-v2')


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
    return model.encode(texts).tolist()


def get_dimension() -> int:
    """Return embedding vector dimension."""
    return 384
