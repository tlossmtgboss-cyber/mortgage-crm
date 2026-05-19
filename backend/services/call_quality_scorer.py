"""
Call Quality Scorer (CC-005)
============================

Lightweight call quality scoring stub used by the call intelligence dashboard.

Real implementations should pull from:
  * Deepgram word-confidence + signal metrics (audio_clarity)
  * Conversation turn count + silence ratio (conversation_flow)
  * Compliance agent flags / TCPA disclosure detection (compliance_adherence)
  * Sentiment timeline (sentiment_balance)

Until those pipelines are unified, this module returns a structurally-correct
score envelope derived from whatever data we *do* have on the
`VoiceCallSession` row. If the row is missing we return a neutral baseline
rather than failing — keeping dashboards stable while the underlying
intelligence is wired in.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_session():
    try:
        from database import SessionLocal
        return SessionLocal()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("call_quality_scorer: SessionLocal unavailable (%s)", exc)
        return None


def _safe_model():
    try:
        from database.models.voice_call_session import VoiceCallSession
        return VoiceCallSession
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("call_quality_scorer: VoiceCallSession model unavailable (%s)", exc)
        return None


# ---------------------------------------------------------------------------
# Dimension scoring helpers
# ---------------------------------------------------------------------------

def _score_audio_clarity(session: Any) -> float:
    """Best-effort audio clarity from STT provider tier."""
    provider = (getattr(session, "stt_provider", "") or "").lower()
    if "deepgram" in provider:
        return 0.92
    if "whisper" in provider or "openai" in provider:
        return 0.88
    if provider:
        return 0.80
    return 0.75  # unknown


def _score_conversation_flow(session: Any) -> float:
    """Score based on duration + message_count balance.

    Healthy calls have multiple turns and >30s duration. Short or one-sided
    calls score lower.
    """
    duration = getattr(session, "duration_seconds", None) or 0
    messages = getattr(session, "message_count", None) or 0
    if duration <= 0 and messages <= 0:
        return 0.5
    score = 0.6
    if duration >= 30:
        score += 0.1
    if duration >= 120:
        score += 0.1
    if messages >= 4:
        score += 0.1
    if messages >= 10:
        score += 0.1
    return min(score, 1.0)


def _score_compliance(session: Any) -> float:
    """Compliance adherence — defaults to high (0.9) unless an error/issue was
    flagged on the session row."""
    if getattr(session, "error_message", None):
        return 0.65
    outcome = (getattr(session, "outcome", "") or "").lower()
    if outcome in {"abandoned", "failed", "no_consent"}:
        return 0.6
    return 0.9


def _score_sentiment(session: Any) -> float:
    sentiment = (getattr(session, "sentiment", "") or "").lower()
    mapping = {
        "positive": 0.95,
        "neutral": 0.75,
        "mixed": 0.65,
        "negative": 0.45,
    }
    return mapping.get(sentiment, 0.7)


def _collect_issues(session: Any, dimensions: Dict[str, float]) -> List[str]:
    issues: List[str] = []
    if dimensions["audio_clarity"] < 0.8:
        issues.append("low_audio_clarity")
    if dimensions["conversation_flow"] < 0.7:
        issues.append("uneven_conversation_flow")
    if dimensions["compliance_adherence"] < 0.8:
        issues.append("possible_compliance_gap")
    if dimensions["sentiment_balance"] < 0.6:
        issues.append("negative_sentiment_detected")
    if getattr(session, "error_message", None):
        issues.append(f"session_error: {session.error_message}")
    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_call(call_session_id: Any) -> Dict[str, Any]:
    """Return a quality score envelope for the given call session.

    Args:
        call_session_id: Either the integer PK of `VoiceCallSession` or the
            `session_uuid` string.

    Returns:
        Dict with `quality_score` (0-1 float), `dimensions` (per-axis scores),
        and `issues` (list of human-readable flags).
    """
    Session = _safe_session()
    Model = _safe_model()

    if Session is None or Model is None:
        # Stub fallback when DB layer is not available (e.g. early-boot tests).
        return _stub_response(call_session_id, reason="db_unavailable")

    session_row: Optional[Any] = None
    try:
        if isinstance(call_session_id, int) or (
            isinstance(call_session_id, str) and call_session_id.isdigit()
        ):
            session_row = (
                Session.query(Model).filter(Model.id == int(call_session_id)).first()
            )
        if session_row is None:
            session_row = (
                Session.query(Model)
                .filter(Model.session_uuid == str(call_session_id))
                .first()
            )
    except Exception as exc:
        logger.warning("score_call lookup failed: %s", exc)
    finally:
        try:
            Session.close()
        except Exception as _exc:  # noqa: BLE001
            pass

    if session_row is None:
        return _stub_response(call_session_id, reason="session_not_found")

    dimensions = {
        "audio_clarity": _score_audio_clarity(session_row),
        "conversation_flow": _score_conversation_flow(session_row),
        "compliance_adherence": _score_compliance(session_row),
        "sentiment_balance": _score_sentiment(session_row),
    }
    overall = round(sum(dimensions.values()) / len(dimensions), 3)
    issues = _collect_issues(session_row, dimensions)

    return {
        "call_session_id": call_session_id,
        "quality_score": overall,
        "dimensions": dimensions,
        "issues": issues,
        "stub": False,
    }


def _stub_response(call_session_id: Any, reason: str) -> Dict[str, Any]:
    dimensions = {
        "audio_clarity": 0.75,
        "conversation_flow": 0.7,
        "compliance_adherence": 0.85,
        "sentiment_balance": 0.7,
    }
    return {
        "call_session_id": call_session_id,
        "quality_score": round(sum(dimensions.values()) / len(dimensions), 3),
        "dimensions": dimensions,
        "issues": [],
        "stub": True,
        "stub_reason": reason,
    }


__all__ = ["score_call"]
