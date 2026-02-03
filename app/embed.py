"""
Embedding service for text vectorization
"""

import os
from typing import List
from openai import AzureOpenAI


class EmbeddingService:
    """Service for generating text embeddings using Azure OpenAI"""
    
    def __init__(self):
        """Initialize the Azure OpenAI client"""
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.model = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text to embed
        
        Returns:
            List of floats representing the embedding vector
        """
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of input texts to embed
        
        Returns:
            List of embedding vectors
        """
        response = self.client.embeddings.create(
            input=texts,
            model=self.model
        )
        return [item.embedding for item in response.data]
    
    def is_available(self) -> bool:
        """
        Check if the embedding service is available
        
        Returns:
            True if service is configured and accessible
        """
        try:
            # Test with a simple embedding
            self.embed_text("test")
            return True
        except Exception:
            return False
