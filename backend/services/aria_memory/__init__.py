"""
Aria Memory Service Package

Persistent borrower memory for the Aria voice agent.
Shared retrieval (pgvector + Redis), context loading,
consolidation pipeline, and staging management.
"""

from .retrieval_service import AriaRetrievalService
from .context_loader import AriaContextLoader, BorrowerContext, ContextLoadRequest

__all__ = [
    "AriaRetrievalService",
    "AriaContextLoader",
    "BorrowerContext",
    "ContextLoadRequest",
]
