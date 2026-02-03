"""
Azure AI Search client for document retrieval
"""

import os
from typing import List, Dict, Any
from azure.search.documents import SearchClient as AzureSearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI


class SearchClient:
    """Client for searching documents in Azure AI Search"""
    
    def __init__(self):
        """Initialize Azure AI Search and OpenAI clients"""
        # Initialize search client
        self.search_client = AzureSearchClient(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY"))
        )
        
        # Initialize OpenAI client for answer generation
        self.openai_client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.chat_model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
    
    def search(
        self, 
        query_embedding: List[float], 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents using vector similarity
        
        Args:
            query_embedding: Query vector embedding
            top_k: Number of top results to return
        
        Returns:
            List of search results with metadata
        """
        results = self.search_client.search(
            search_text="",
            vector_queries=[{
                "kind": "vector",
                "vector": query_embedding,
                "fields": "content_vector",
                "k": top_k
            }],
            select=["id", "content", "title", "metadata"]
        )
        
        return [
            {
                "id": result.get("id"),
                "content": result.get("content"),
                "title": result.get("title"),
                "score": result.get("@search.score"),
                "metadata": result.get("metadata", {})
            }
            for result in results
        ]
    
    def generate_answer(
        self, 
        query: str, 
        search_results: List[Dict[str, Any]]
    ) -> str:
        """
        Generate an answer using retrieved context
        
        Args:
            query: User's question
            search_results: Retrieved documents from search
        
        Returns:
            Generated answer string
        """
        # Construct context from search results
        context = "\n\n".join([
            f"Document {i+1} (Title: {doc.get('title', 'N/A')}):\n{doc.get('content', '')}"
            for i, doc in enumerate(search_results)
        ])
        
        # Create messages for chat completion
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that answers questions based on the provided context. "
                          "If the answer cannot be found in the context, say so clearly."
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
            }
        ]
        
        # Generate response
        response = self.openai_client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content
    
    def is_available(self) -> bool:
        """
        Check if the search service is available
        
        Returns:
            True if service is configured and accessible
        """
        try:
            # Test search connectivity
            list(self.search_client.search(search_text="test", top=1))
            return True
        except Exception:
            return False
