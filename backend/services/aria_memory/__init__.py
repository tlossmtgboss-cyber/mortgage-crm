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
from .embedding_service import generate_embedding_sync, generate_embedding_async
from .conflict_detector import (
    ConflictResult,
    SuggestedAction,
    detect_conflicts,
    resolve_auto_conflicts,
    apply_confidence_decay,
)

__all__ = [
    "AriaRetrievalService",
    "AriaContextLoader",
    "BorrowerContext",
    "ContextLoadRequest",
    "ConsolidationWorker",
    "ExclusionChecker",
    "ShadowEvaluator",
    "generate_embedding_sync",
    "generate_embedding_async",
    "ConflictResult",
    "SuggestedAction",
    "detect_conflicts",
    "resolve_auto_conflicts",
    "apply_confidence_decay",
]
