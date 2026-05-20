"""Integration tests for ModelRouter (Wave 6 Slice E)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make ``backend`` importable when running from the repo root.
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agents.orchestration.model_router import (  # noqa: E402
    DEFAULT_MODEL,
    HIGH_COMPLEXITY_INTENTS,
    LOW_COMPLEXITY_INTENTS,
    MEDIUM_COMPLEXITY_INTENTS,
    MODEL_HAIKU,
    MODEL_OPUS,
    MODEL_SONNET,
    ModelRouter,
)


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter()


def test_high_complexity_intents_route_to_opus(router: ModelRouter) -> None:
    for intent in HIGH_COMPLEXITY_INTENTS:
        assert router.select_model(intent) == MODEL_OPUS, intent


def test_medium_complexity_intents_route_to_sonnet(router: ModelRouter) -> None:
    for intent in MEDIUM_COMPLEXITY_INTENTS:
        assert router.select_model(intent) == MODEL_SONNET, intent


def test_low_complexity_intents_route_to_haiku(router: ModelRouter) -> None:
    for intent in LOW_COMPLEXITY_INTENTS:
        assert router.select_model(intent) == MODEL_HAIKU, intent


def test_unknown_intent_falls_back_to_default_sonnet(router: ModelRouter) -> None:
    assert router.select_model("SOMETHING_NOVEL") == DEFAULT_MODEL
    assert DEFAULT_MODEL == MODEL_SONNET


def test_complexity_hint_overrides_table(router: ModelRouter) -> None:
    # "low" hint should force Haiku even for a high-complexity intent.
    assert router.select_model("UNDERWRITING_DECISION", complexity_hint="low") == MODEL_HAIKU
    # "high" hint should force Opus even for a greeting.
    assert router.select_model("GREETING", complexity_hint="high") == MODEL_OPUS
    # "auto" hint preserves table behaviour.
    assert router.select_model("GREETING", complexity_hint="auto") == MODEL_HAIKU


def test_env_override_wins_over_table_and_hint(
    router: ModelRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTENT_MODEL_OVERRIDE_UNDERWRITING_DECISION", "claude-sonnet-4-6")
    # Table says Opus, but env override should win.
    assert router.select_model("UNDERWRITING_DECISION") == "claude-sonnet-4-6"
    # Even an explicit "high" hint loses to the env override.
    assert router.select_model("UNDERWRITING_DECISION", complexity_hint="high") == "claude-sonnet-4-6"


def test_estimate_cost_uses_correct_pricing_per_model(router: ModelRouter) -> None:
    # Opus: 1K input + 1K output = 0.015 + 0.075 = 0.090
    opus_cost = router.estimate_cost("UNDERWRITING_DECISION", 1000, 1000)
    assert opus_cost == pytest.approx(0.090, rel=1e-6)

    # Sonnet: 1K + 1K = 0.003 + 0.015 = 0.018
    sonnet_cost = router.estimate_cost("LEAD_NURTURE", 1000, 1000)
    assert sonnet_cost == pytest.approx(0.018, rel=1e-6)

    # Haiku: 1K + 1K = 0.00080 + 0.0040 = 0.00480
    haiku_cost = router.estimate_cost("GREETING", 1000, 1000)
    assert haiku_cost == pytest.approx(0.00480, rel=1e-6)

    # Opus is materially more expensive than Haiku at equal volume.
    assert opus_cost > sonnet_cost > haiku_cost


def test_estimated_cost_is_monotonic_in_token_count(router: ModelRouter) -> None:
    prev = -1.0
    for tokens in (100, 500, 1000, 5000, 10_000, 50_000):
        cost = router.estimate_cost("LEAD_NURTURE", tokens, tokens)
        assert cost > prev, f"cost not monotonic at {tokens} tokens"
        prev = cost


def test_model_naming_matches_claude_md_convention() -> None:
    assert MODEL_OPUS == "claude-opus-4-7"
    assert MODEL_SONNET == "claude-sonnet-4-6"
    assert MODEL_HAIKU == "claude-haiku-4-5-20251001"


def test_select_model_returns_string_not_enum(router: ModelRouter) -> None:
    for intent in ("UNDERWRITING_DECISION", "LEAD_NURTURE", "GREETING", "UNKNOWN"):
        result = router.select_model(intent)
        assert isinstance(result, str), f"{intent} -> {type(result)}"
        assert not hasattr(result, "value"), "model id should be primitive str"
