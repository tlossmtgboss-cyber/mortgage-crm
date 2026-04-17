# backend/tests/test_aria_config.py
import pytest
from agents.aria_config import (
    AUTONOMOUS_CALL_GUARDRAILS,
    OUTBOUND_CALL_CONFIG,
    VOICEMAIL_TEMPLATES,
    MAX_VOICEMAIL_SECONDS,
    AMD_HIGH_CONFIDENCE,
    AMD_MEDIUM_CONFIDENCE,
    render_voicemail_template,
    is_intent_autonomous_eligible,
    get_amd_action,
)


def test_guardrails_has_required_keys():
    required = [
        "calling_hours", "days_allowed", "max_calls_per_lead_day",
        "max_calls_per_lead_week", "max_attempts_no_answer",
        "permitted_intents", "never_autonomous", "immediate_lo_alert",
    ]
    for key in required:
        assert key in AUTONOMOUS_CALL_GUARDRAILS, f"Missing guardrail: {key}"


def test_voicemail_templates_exist():
    expected = ["appointment_reminder", "rate_lock_expiry", "document_chase", "post_close"]
    for name in expected:
        assert name in VOICEMAIL_TEMPLATES, f"Missing template: {name}"


def test_render_voicemail_template_appointment():
    result = render_voicemail_template("appointment_reminder", {
        "first_name": "Marcus",
        "lo_name": "Sarah",
        "time": "2 PM",
    })
    assert "Marcus" in result
    assert "Sarah" in result
    assert "2 PM" in result


def test_render_voicemail_template_unknown():
    result = render_voicemail_template("nonexistent_template", {})
    assert result is None


def test_max_voicemail_seconds():
    assert MAX_VOICEMAIL_SECONDS == 28


def test_is_intent_autonomous_eligible():
    assert is_intent_autonomous_eligible("appointment_reminder") is True
    assert is_intent_autonomous_eligible("first_touch") is False
    assert is_intent_autonomous_eligible("rate_renegotiation") is False
    assert is_intent_autonomous_eligible("document_chase") is True


def test_amd_confidence_bands():
    assert get_amd_action("human", 0.99) == "route_to_agent"
    assert get_amd_action("machine", 0.95) == "voicemail_full"
    assert get_amd_action("machine", 0.85) == "voicemail_short"
    assert get_amd_action("machine", 0.60) == "no_voicemail"
    assert get_amd_action("unknown", 0.50) == "no_voicemail"
