"""
Embedding Service for Aria Memory

Generates embeddings for memory facts using OpenAI text-embedding-3-small.
Provides both sync and async interfaces so callers in sync routes
(admin approval) and async workers (consolidation) can both use it.

Normalization matches retrieval_service._embed_query exactly:
lowercase, collapse whitespace, strip punctuation.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("aria.memory.embedding")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _normalize_text(text: str) -> str:
    """Normalize input text identically to retrieval_service._embed_query."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return normalized


def generate_embedding_sync(text: str) -> Optional[list[float]]:
    """
    Generate an embedding vector synchronously.

    Returns None on failure (caller should log and continue).
    """
    try:
        import openai

        normalized = _normalize_text(text)
        if not normalized:
            logger.warning("Empty text after normalization, skipping embedding")
            return None

        client = openai.OpenAI()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=normalized,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None


async def generate_embedding_async(text: str) -> Optional[list[float]]:
    """
    Generate an embedding vector asynchronously.

    Returns None on failure (caller should log and continue).
    """
    try:
        import openai

        normalized = _normalize_text(text)
        if not normalized:
            logger.warning("Empty text after normalization, skipping embedding")
            return None

        client = openai.AsyncOpenAI()
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=normalized,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None
