"""
Aria Memory Service Package

Persistent borrower memory for the Aria voice agent.
Shared retrieval (pgvector + Redis), context loading,
consolidation pipeline, and staging management.
"""

from .retrieval_service import AriaRetrievalService
from .context_loader import AriaContextLoader, BorrowerContext, ContextLoadRequest
from .consolidation_worker import ConsolidationWorker
from .exclusion_list import ExclusionChecker
from .shadow_evaluator import ShadowEvaluator

__all__ = [
    "AriaRetrievalService",
    "AriaContextLoader",
    "BorrowerContext",
    "ContextLoadRequest",
    "ConsolidationWorker",
    "ExclusionChecker",
    "ShadowEvaluator",
]
