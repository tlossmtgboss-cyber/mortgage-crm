"""
Pinecone Vector Database Service
Handles conversation memory storage and semantic search for AI context retrieval
"""
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

logger = logging.getLogger(__name__)


class VectorMemoryService:
    """Service for storing and retrieving conversation context using vector embeddings"""

    def __init__(self):
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.index_name = "crm-conversations"

        # Check if we have credentials
        if not self.pinecone_api_key or not self.openai_api_key:
            logger.warning("Pinecone or OpenAI API key not configured - vector memory disabled")
            self.enabled = False
            return

        try:
            # Initialize Pinecone
            self.pc = Pinecone(api_key=self.pinecone_api_key)

            # Create index if it doesn't exist
            if self.index_name not in self.pc.list_indexes().names():
                logger.info(f"Creating Pinecone index: {self.index_name}")
                self.pc.create_index(
                    name=self.index_name,
                    dimension=1536,  # OpenAI text-embedding-3-small dimension
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )

            # Connect to index
            self.index = self.pc.Index(self.index_name)

            # Initialize OpenAI
            self.openai = OpenAI(api_key=self.openai_api_key)

            self.enabled = True
            logger.info("Vector memory service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize vector memory service: {e}")
            self.enabled = False

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for text using OpenAI"""
        try:
            response = self.openai.embeddings.create(
                input=text,
                model="text-embedding-3-small"  # 1536 dimensions, $0.02 per 1M tokens
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    async def store_conversation(
        self,
        user_id: int,
        conversation_text: str,
        metadata: Dict = None
    ) -> Optional[str]:
        """
        Store a conversation in vector database for future retrieval

        Args:
            user_id: ID of the user
            conversation_text: The conversation content to store
            metadata: Additional metadata (lead_id, sentiment, intent, etc.)

        Returns:
            The vector ID if successful, None otherwise
        """
        if not self.enabled:
            logger.warning("Vector memory not enabled - cannot store conversation")
            return None

        try:
            # Generate unique ID
            vector_id = f"conv_{user_id}_{int(datetime.now().timestamp() * 1000)}"

            # Generate embedding
            embedding = self._generate_embedding(conversation_text)

            if not embedding:
                return None

            # Prepare metadata
            vector_metadata = {
                "user_id": user_id,
                "text": conversation_text[:1000],  # Store first 1000 chars in metadata
                "timestamp": datetime.now().isoformat(),
                "full_text_length": len(conversation_text)
            }

            # Add custom metadata if provided
            if metadata:
                vector_metadata.update(metadata)

            # Store in Pinecone
            self.index.upsert(
                vectors=[(vector_id, embedding, vector_metadata)],
                namespace=f"user_{user_id}"  # Use namespaces for user isolation
            )

            logger.info(f"Stored conversation vector: {vector_id} for user {user_id}")
            return vector_id

        except Exception as e:
            logger.error(f"Error storing conversation: {e}")
            return None

    async def retrieve_relevant_context(
        self,
        user_id: int,
        current_query: str,
        top_k: int = 5,
        filter_metadata: Dict = None
    ) -> List[Dict]:
        """
        Retrieve most relevant past conversations for current query

        Args:
            user_id: ID of the user
            current_query: The current message/query
            top_k: Number of relevant conversations to retrieve
            filter_metadata: Optional filters (e.g., {"lead_id": 123})

        Returns:
            List of relevant conversation metadata
        """
        if not self.enabled:
            logger.warning("Vector memory not enabled - cannot retrieve context")
            return []

        try:
            # Generate embedding for current query
            query_embedding = self._generate_embedding(current_query)

            if not query_embedding:
                return []

            # Build filter if provided
            query_filter = {}
            if filter_metadata:
                query_filter.update(filter_metadata)

            # Query Pinecone
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=f"user_{user_id}",
                filter=query_filter if query_filter else None,
                include_metadata=True
            )

            # Extract and return metadata
            relevant_contexts = []
            for match in results.matches:
                if match.score > 0.7:  # Only include high-relevance matches
                    relevant_contexts.append({
                        "text": match.metadata.get("text", ""),
                        "timestamp": match.metadata.get("timestamp", ""),
                        "relevance_score": match.score,
                        "metadata": match.metadata
                    })

            logger.info(f"Retrieved {len(relevant_contexts)} relevant contexts for user {user_id}")
            return relevant_contexts

        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return []

    async def delete_user_conversations(self, user_id: int):
        """Delete all conversations for a user (GDPR compliance)"""
        if not self.enabled:
            return

        try:
            # Delete namespace for user
            self.index.delete(namespace=f"user_{user_id}", delete_all=True)
            logger.info(f"Deleted all conversations for user {user_id}")
        except Exception as e:
            logger.error(f"Error deleting user conversations: {e}")

    async def get_conversation_count(self, user_id: int) -> int:
        """Get count of stored conversations for a user"""
        if not self.enabled:
            return 0

        try:
            stats = self.index.describe_index_stats()
            namespace_stats = stats.namespaces.get(f"user_{user_id}", None)
            if namespace_stats:
                return namespace_stats.vector_count
            return 0
        except Exception as e:
            logger.error(f"Error getting conversation count: {e}")
            return 0


# Global instance
vector_memory = VectorMemoryService()
