"""
Embedding service for text vectorization using sentence-transformers.
Uses all-MiniLM-L6-v2 model (~80MB) - runs locally without external API calls.
Vector dimension: 384

sentence-transformers を使用したテキストベクトル化のための埋め込みサービス。
all-MiniLM-L6-v2 モデル（約80MB）を使用し、外部APIを呼び出さずにローカルで実行します。
ベクトル次元数: 384
"""

import threading
from sentence_transformers import SentenceTransformer

_MODEL = None
_MODEL_LOCK = threading.Lock()

def _get_model() -> SentenceTransformer:
    """
    Lazy-load the model so the app can start quickly and /health responds
    even if the model needs to download on first use.
    
    モデルを遅延ロードすることで、初回使用時にモデルのダウンロードが必要な場合でも、
    アプリケーションが迅速に起動し、/health エンドポイントが応答できるようにします。
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
    テキストのセマンティック埋め込みベクトルを生成します。
    
    Model: all-MiniLM-L6-v2
    Dimension: 384
    
    Args:
        text: Input text to embed (埋め込む入力テキスト)
        
    Returns:
        List of floats representing the embedding vector (埋め込みベクトルを表す浮動小数点数のリスト)
    """
    if not text:
        return []
    # convert to list for JSON serialization
    model = _get_model()
    return model.encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.
    複数のテキストの埋め込みベクトルを生成します。
    
    Args:
        texts: List of input texts to embed (埋め込む入力テキストのリスト)
        
    Returns:
        List of embedding vectors (埋め込みベクトルのリスト)
    """
    if not texts:
        return []
    model = _get_model()
    return model.encode(texts).tolist()


def get_dimension() -> int:
    """Return embedding vector dimension. / 埋め込みベクトルの次元数を返します。"""
    return 384
