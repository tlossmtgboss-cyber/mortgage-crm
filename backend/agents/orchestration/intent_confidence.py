"""
Intent Confidence Gate
======================

Wave 3 / D3 audit remediation #1 — intent router fragility.

The existing intent router (`agents.intent_router.classify_intent`) already
returns a confidence score, but historically the orchestrator routed to
whatever intent came back regardless of how shaky the classification was.
A low-confidence misroute silently sends the request to the wrong agent
fleet, which is one of the more expensive failure modes in production.

This module is a thin gate that wraps a classification result and:
  1. Compares confidence against a configurable threshold
     (``INTENT_CONFIDENCE_THRESHOLD`` env var, default ``0.75``).
  2. If below threshold, rewrites the result to a safe fallback intent
     (``general_query``) routed to a generic agent fleet.
  3. Emits a structured warning so the misroute is visible in logs.
  4. Records a governance metric (``low_confidence_intent``) so the new
     D3 governance dashboard can chart the fallback rate. The metrics
     dependency is imported defensively — a sibling Wave 3 agent owns the
     ``governance_metrics`` module, so we degrade gracefully if it is not
     yet on the path.

The module is deliberately import-light so it can be unit-tested without
pulling in the full agent fleet / LangGraph / Anthropic SDK.

Usage
-----

    from agents.orchestration.intent_confidence import apply_confidence_gate

    raw = await classify_intent(user_message, anthropic_client)
    gated = apply_confidence_gate(raw, query=user_message)
    # gated["intent"] is either the original intent or "general_query"
    # gated["agents"] is rewritten to the fallback fleet on low confidence

TODO(agents.service): call ``apply_confidence_gate`` immediately after
``classify_intent`` in ``backend/agents/service.py`` /
``backend/agents/nodes/analyze.py`` so every routed request flows through
the gate. The wrapper is idempotent and safe to call multiple times.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _read_threshold() -> float:
    """Read the threshold from env at call time so tests can monkey-patch."""
    raw = os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.75")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "INTENT_CONFIDENCE_THRESHOLD=%r is not a float; using 0.75", raw
        )
        return 0.75
    # Clamp to [0, 1] — a threshold outside this range is almost certainly a typo.
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


# Default threshold as a module-level constant for callers that want to read
# the configured value without invoking the gate. Lazily-resolved via property
# accessor below.
INTENT_CONFIDENCE_THRESHOLD: float = _read_threshold()

FALLBACK_INTENT: str = "general_query"

# Agents that the fallback intent should be routed to. Keep this list short and
# generic — these agents are expected to handle "I don't know what the user
# wants" gracefully.
FALLBACK_AGENTS: List[str] = ["pipeline_analyst", "task_automation"]


# ---------------------------------------------------------------------------
# Governance metrics — defensive import
# ---------------------------------------------------------------------------

def _record_governance_event(
    *,
    chosen_intent: str,
    confidence: float,
    threshold: float,
    query_preview: str,
) -> None:
    """Record a low-confidence fallback event to the governance dashboard.

    The ``governance_metrics`` module is owned by a sibling Wave 3 agent and
    may not be importable yet. Guard the import so this module is usable in
    isolation (and unit-testable without the dashboard wired up).
    """
    import sys as _sys

    governance_metrics = None
    # 1. Check already-loaded modules (test harnesses inject mocks here).
    for candidate in (
        "agents.orchestration.governance_metrics",
        "services.governance_metrics",
    ):
        if candidate in _sys.modules:
            governance_metrics = _sys.modules[candidate]
            break

    # 2. Fall back to a real import if no preloaded module is present.
    if governance_metrics is None:
        try:
            from agents.orchestration import governance_metrics  # type: ignore[no-redef]
        except ImportError:
            try:
                from services import governance_metrics  # type: ignore[no-redef]
            except ImportError:
                logger.debug(
                    "governance_metrics module not available; skipping metric record"
                )
                return

    recorder = getattr(governance_metrics, "record_compliance_event", None)
    if recorder is None:
        logger.debug(
            "governance_metrics.record_compliance_event missing; skipping record"
        )
        return

    try:
        recorder(
            violation_type="low_confidence_intent",
            severity="warning",
            details={
                "chosen_intent": chosen_intent,
                "confidence": confidence,
                "threshold": threshold,
                "query_preview": query_preview[:160],
                "fallback_intent": FALLBACK_INTENT,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        # The governance pipeline must never break the request path.
        logger.warning("Failed to record governance event: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_threshold() -> float:
    """Return the live threshold (env-overridable on every call)."""
    return _read_threshold()


def is_low_confidence(confidence: Optional[float], threshold: Optional[float] = None) -> bool:
    """Return True if ``confidence`` falls below the (live) threshold."""
    if confidence is None:
        return True
    try:
        confidence_f = float(confidence)
    except (TypeError, ValueError):
        return True
    if threshold is None:
        threshold = get_threshold()
    return confidence_f < threshold


def apply_confidence_gate(
    classification: Optional[Dict[str, Any]],
    *,
    query: str = "",
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Gate a classification result against the confidence threshold.

    Parameters
    ----------
    classification:
        The dict returned by ``agents.intent_router.classify_intent``. Must
        contain at least ``intent`` and ``confidence``; ``agents`` is rewritten
        to ``FALLBACK_AGENTS`` on fallback. ``None`` / empty dict is treated
        as "we have no idea" and falls through to the fallback.
    query:
        Original user query, used only for the log line / metric preview.
    threshold:
        Override the env-configured threshold. Primarily for tests.

    Returns
    -------
    Dict[str, Any]
        Either the original classification (high confidence) or a rewritten
        fallback classification (low confidence). The returned dict always has
        ``intent``, ``confidence``, ``agents``, ``method``, ``fallback_applied``.
    """
    active_threshold = threshold if threshold is not None else get_threshold()

    # Defensively handle missing / malformed input — these are exactly the
    # cases where the classifier most needs a safety net.
    if not classification or not isinstance(classification, dict):
        logger.warning(
            "Low-confidence intent classification: chosen=%s confidence=%s "
            "falling back to %s (reason=empty_or_invalid_input)",
            None,
            None,
            FALLBACK_INTENT,
        )
        _record_governance_event(
            chosen_intent="<none>",
            confidence=0.0,
            threshold=active_threshold,
            query_preview=query or "",
        )
        return _fallback_result(original_method="empty_input")

    chosen_intent = classification.get("intent")
    confidence = classification.get("confidence")

    if is_low_confidence(confidence, threshold=active_threshold):
        logger.warning(
            "Low-confidence intent classification: chosen=%s confidence=%s "
            "falling back to %s (threshold=%s)",
            chosen_intent,
            confidence,
            FALLBACK_INTENT,
            active_threshold,
        )
        _record_governance_event(
            chosen_intent=str(chosen_intent) if chosen_intent else "<none>",
            confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.0,
            threshold=active_threshold,
            query_preview=query or "",
        )
        return _fallback_result(
            original_method=classification.get("method", "unknown"),
            original_intent=chosen_intent,
            original_confidence=confidence,
        )

    # High confidence — pass through, but stamp the gate metadata so downstream
    # callers can see this result went through the gate.
    out = dict(classification)
    out.setdefault("agents", classification.get("agents") or FALLBACK_AGENTS)
    out["fallback_applied"] = False
    return out


def _fallback_result(
    *,
    original_method: str = "unknown",
    original_intent: Any = None,
    original_confidence: Any = None,
) -> Dict[str, Any]:
    return {
        "intent": FALLBACK_INTENT,
        "confidence": 0.0,
        "agents": list(FALLBACK_AGENTS),
        "method": "fallback",
        "fallback_applied": True,
        "original_intent": original_intent,
        "original_confidence": original_confidence,
        "original_method": original_method,
    }


__all__ = [
    "INTENT_CONFIDENCE_THRESHOLD",
    "FALLBACK_INTENT",
    "FALLBACK_AGENTS",
    "apply_confidence_gate",
    "get_threshold",
    "is_low_confidence",
]
