"""
Integration tests for `services/call_quality_scorer.py` dimension scoring.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_scorer():
    target = _BACKEND_DIR / "services" / "call_quality_scorer.py"
    if not target.exists():
        pytest.skip("call_quality_scorer.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_call_quality_scorer", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_cq = _load_scorer()


def _session(**kw):
    """Build a fake session-row-like object."""
    defaults = dict(
        stt_provider="deepgram",
        duration_seconds=120,
        message_count=10,
        error_message=None,
        outcome="completed",
        sentiment="positive",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Each of 4 dimensions scored
# ---------------------------------------------------------------------------

def test_audio_clarity_scored_for_deepgram():
    sess = _session(stt_provider="deepgram")
    assert _cq._score_audio_clarity(sess) == 0.92


def test_conversation_flow_scored_for_healthy_call():
    sess = _session(duration_seconds=120, message_count=10)
    assert _cq._score_conversation_flow(sess) >= 0.9


def test_compliance_dimension_scored_for_clean_session():
    sess = _session(error_message=None, outcome="completed")
    assert _cq._score_compliance(sess) == 0.9


def test_sentiment_dimension_scored_for_positive_sentiment():
    sess = _session(sentiment="positive")
    assert _cq._score_sentiment(sess) == 0.95


# ---------------------------------------------------------------------------
# Missing data fallback (stub when db unavailable returns coherent structure)
# ---------------------------------------------------------------------------

def test_stub_response_when_db_unavailable():
    # Force stub fallback by passing an id that wouldn't match.
    res = _cq.score_call("nonexistent-id-xyz")
    assert "quality_score" in res
    assert "dimensions" in res
    assert "issues" in res


# ---------------------------------------------------------------------------
# Very short call scores lower on conversation flow
# ---------------------------------------------------------------------------

def test_very_short_call_lower_conversation_flow():
    sess = _session(duration_seconds=5, message_count=1)
    # short call should not get duration bonuses
    score = _cq._score_conversation_flow(sess)
    assert score <= 0.7


# ---------------------------------------------------------------------------
# Null sentiment handled
# ---------------------------------------------------------------------------

def test_null_sentiment_returns_default():
    sess = _session(sentiment=None)
    assert _cq._score_sentiment(sess) == 0.7


# ---------------------------------------------------------------------------
# Issues list populated when dimensions are weak
# ---------------------------------------------------------------------------

def test_issues_list_populated_when_dimensions_low():
    dims = {
        "audio_clarity": 0.5,
        "conversation_flow": 0.5,
        "compliance_adherence": 0.5,
        "sentiment_balance": 0.5,
    }
    sess = _session()
    issues = _cq._collect_issues(sess, dims)
    assert "low_audio_clarity" in issues
    assert "uneven_conversation_flow" in issues
    assert "possible_compliance_gap" in issues
    assert "negative_sentiment_detected" in issues
