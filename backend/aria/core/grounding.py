"""
Grounding contract for Aria factual answers (Phase 2A).

Wraps the existing KnowledgeTools/GuidelineSearchService RAG path and adds a
deterministic sufficiency gate + citation formatting, so guideline answers are
grounded-or-disclaimed rather than free-form LLM output.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aria.grounding")

# Minimum average retrieval similarity to treat a RAG answer as sufficiently grounded.
# Read once at import time; callers needing dynamic tuning should pass min_confidence
# to is_sufficiently_grounded() explicitly rather than mutating the env var at runtime.
GROUNDING_MIN_CONFIDENCE = float(os.getenv("ARIA_GROUNDING_MIN_CONFIDENCE", "0.45"))

DISCLAIMER = (
    "I don't have this in the indexed official guidelines, so this is general "
    "knowledge — please verify against the source guideline before relying on it."
)


@dataclass
class GroundingResult:
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None
    grounded: bool = False
    disclaimer: Optional[str] = None


def is_sufficiently_grounded(result: "GroundingResult",
                             min_confidence: float = GROUNDING_MIN_CONFIDENCE) -> bool:
    """Blocking sufficiency gate: require >=1 source AND confidence at/above threshold."""
    if not result.sources:
        return False
    if result.confidence is None:
        return False
    return result.confidence >= min_confidence


async def ground_answer(question: str, org_id: Any) -> "GroundingResult":
    """Run the guideline RAG path and wrap the result in a GroundingResult.

    Never raises — on any failure (or an unexpected RAG return type), returns an
    ungrounded result with a disclaimer.
    """
    from aria.tools.knowledge_tools import KnowledgeTools
    try:
        tenant_id = int(org_id) if org_id is not None else None
    except (TypeError, ValueError):
        tenant_id = None
    try:
        raw = await KnowledgeTools().search_guidelines_rag(question=question, tenant_id=tenant_id)
    except Exception:
        logger.exception("ground_answer RAG call failed")
        return GroundingResult(answer=DISCLAIMER, grounded=False, disclaimer=DISCLAIMER)

    if not isinstance(raw, dict):
        logger.warning("ground_answer: unexpected RAG response type %s", type(raw))
        return GroundingResult(answer=DISCLAIMER, grounded=False, disclaimer=DISCLAIMER)

    result = GroundingResult(
        answer=raw.get("answer", "") or "",
        sources=raw.get("sources", []) or [],
        citations=raw.get("citations", []) or [],
        confidence=raw.get("confidence"),
        disclaimer=raw.get("disclaimer"),
    )
    result.grounded = is_sufficiently_grounded(result)
    return result


_GUIDELINE_HINTS = (
    "fha", "usda", "conventional", "conforming", "guideline", "eligibility",
    "reserve", "ltv", "dti", "credit score", "seasoning", "waiting period",
    "down payment requirement", "occupancy requirement", "loan limit", "qualify for",
)


def looks_like_guideline_question(text: str) -> bool:
    """Heuristic: does this QUERY-mode turn look like a guideline question?

    A first-cut substring match behind the grounding flag — a false positive only
    costs an unnecessary RAG call (it does not produce a wrong answer), so the
    hints favour recall. Operational queries with none of these terms fall through.
    """
    if not text:
        return False
    t = text.lower()
    return any(hint in t for hint in _GUIDELINE_HINTS)


def format_grounded_message(answer: str, sources: List[Dict[str, Any]]) -> str:
    """Append a human-readable Sources list to a RAG answer (which already has [n] markers)."""
    if not sources:
        return answer
    lines = []
    for i, s in enumerate(sources, start=1):
        name = s.get("guideline_name") or s.get("guideline_type") or "Guideline"
        program = s.get("loan_program")
        lines.append(f"[{i}] {name}" + (f" ({program})" if program else ""))
    return f"{answer}\n\nSources:\n" + "\n".join(lines)
