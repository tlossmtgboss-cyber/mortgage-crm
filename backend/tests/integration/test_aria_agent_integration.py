# backend/tests/integration/test_aria_agent_integration.py
"""
Integration test — verifies the Aria agent module loads, the internal
API endpoints respond, and the circuit breaker client works end-to-end.

Adapted from Task 11 of the LiveKit Aria voice agent plan, matching
the actual implementation (unified session handler, TurnHandlingOptions).
"""
import os

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
# Force dummy API keys for LiveKit plugin constructors (Deepgram, Anthropic, Cartesia).
# These are never used -- no real API calls are made during tests.
# Use direct assignment (not setdefault) because .env may set these to empty strings
# and load_dotenv runs in conftest.py before this file.
for _key in ("DEEPGRAM_API_KEY", "ANTHROPIC_API_KEY", "CARTESIA_API_KEY"):
    if not os.environ.get(_key):
        os.environ[_key] = f"test-{_key.lower()}"

import pytest


# ─── Agent module loading ────────────────────────────────────────────────────

def test_aria_agent_module_loads():
    """Agent module imports without errors."""
    from aria.voice_agent import server, AriaVoiceAgent, _build_session
    assert server is not None
    assert AriaVoiceAgent is not None
    assert callable(_build_session)


async def test_aria_agent_creates_lo_assistant_session():
    """Session builder returns (session, agent) for LO assistant mode.

    Async because AgentSession requires an event loop at construction time.
    """
    from aria.voice_agent import _build_session, AriaVoiceAgent
    session, agent = _build_session("lo_assistant")
    assert isinstance(agent, AriaVoiceAgent)
    assert agent._mode == "lo_assistant"
    assert session is not None


async def test_aria_agent_creates_inbound_receptionist_session():
    """Session builder returns (session, agent) for inbound receptionist mode."""
    from aria.voice_agent import _build_session, AriaVoiceAgent
    session, agent = _build_session("inbound_receptionist", {
        "first_name": "Marcus",
        "lo_name": "Sarah",
    })
    assert isinstance(agent, AriaVoiceAgent)
    assert agent._mode == "inbound_receptionist"
    # Inbound receptionist prompt should contain Aria and receptionist-specific content
    assert "Aria" in agent.instructions
    assert "caller" in agent.instructions.lower()


async def test_aria_agent_creates_outbound_followup_session():
    """Session builder returns (session, agent) for outbound follow-up mode."""
    from aria.voice_agent import _build_session, AriaVoiceAgent
    session, agent = _build_session("outbound_followup", {
        "first_name": "Jess",
        "lo_name": "Tim",
        "call_purpose": "rate lock expiry",
        "call_context": "Lock expires Friday",
    })
    assert isinstance(agent, AriaVoiceAgent)
    assert agent._mode == "outbound_followup"
    assert "Jess" in agent.instructions
    assert "Tim" in agent.instructions


async def test_aria_agent_unknown_mode_falls_back_to_lo_assistant():
    """Unknown mode should fall back to LO assistant prompt."""
    from aria.voice_agent import _build_session
    session, agent = _build_session("nonexistent_mode")
    # get_prompt returns LO_ASSISTANT_PROMPT for unknown modes
    assert "Aria" in agent.instructions
    assert len(agent.instructions) > 100


async def test_aria_agent_session_data_initialized():
    """Agent session data dict is initialized with mode and start time."""
    from aria.voice_agent import _build_session
    _, agent = _build_session("lo_assistant")
    assert agent._session_data["mode"] == "lo_assistant"
    assert agent._session_data["tools_executed"] == []
    assert "started_at" in agent._session_data


# ─── Config imports ──────────────────────────────────────────────────────────

def test_config_imports():
    """All config symbols import and have expected values."""
    from agents.aria_config import (
        AUTONOMOUS_CALL_GUARDRAILS,
        OUTBOUND_CALL_CONFIG,
        VOICEMAIL_TEMPLATES,
        MAX_VOICEMAIL_SECONDS,
        AMD_HIGH_CONFIDENCE,
        AMD_MEDIUM_CONFIDENCE,
        render_voicemail_template,
        get_amd_action,
        is_intent_autonomous_eligible,
    )
    assert len(VOICEMAIL_TEMPLATES) >= 4
    assert MAX_VOICEMAIL_SECONDS == 28
    assert AMD_HIGH_CONFIDENCE > AMD_MEDIUM_CONFIDENCE
    assert "answering_machine_detection" in OUTBOUND_CALL_CONFIG


def test_guardrails_structure():
    """Guardrails dict has all required safety keys."""
    from agents.aria_config import AUTONOMOUS_CALL_GUARDRAILS
    required = [
        "calling_hours", "days_allowed", "max_calls_per_lead_day",
        "max_calls_per_lead_week", "max_attempts_no_answer",
        "permitted_intents", "never_autonomous", "immediate_lo_alert",
    ]
    for key in required:
        assert key in AUTONOMOUS_CALL_GUARDRAILS, f"Missing guardrail: {key}"


def test_amd_action_routing():
    """AMD action function returns correct routing for each confidence band."""
    from agents.aria_config import get_amd_action
    assert get_amd_action("human", 0.99) == "route_to_agent"
    assert get_amd_action("human", 0.50) == "route_to_agent"
    assert get_amd_action("machine", 0.95) == "voicemail_full"
    assert get_amd_action("machine", 0.85) == "voicemail_short"
    assert get_amd_action("machine", 0.60) == "no_voicemail"


def test_voicemail_template_rendering():
    """Voicemail templates render with context variables."""
    from agents.aria_config import render_voicemail_template
    result = render_voicemail_template("appointment_reminder", {
        "first_name": "Marcus",
        "lo_name": "Sarah",
        "time": "2 PM",
    })
    assert result is not None
    assert "Marcus" in result
    assert "Sarah" in result
    assert "2 PM" in result


def test_intent_eligibility():
    """Intent eligibility function correctly classifies autonomous vs blocked intents."""
    from agents.aria_config import is_intent_autonomous_eligible
    assert is_intent_autonomous_eligible("appointment_reminder") is True
    assert is_intent_autonomous_eligible("document_chase") is True
    assert is_intent_autonomous_eligible("first_touch") is False
    assert is_intent_autonomous_eligible("complaint_resolution") is False


# ─── Backend client imports ──────────────────────────────────────────────────

def test_backend_client_imports():
    """Backend client module imports with correct timeout and fallback."""
    from agents.aria_backend_client import (
        call_backend_tool,
        call_backend_tool_safe,
        BACKEND_TIMEOUT,
        GRACEFUL_FALLBACK,
    )
    assert BACKEND_TIMEOUT == 3.0
    assert len(GRACEFUL_FALLBACK) > 0
    assert callable(call_backend_tool)
    assert callable(call_backend_tool_safe)


# ─── Prompt modes ────────────────────────────────────────────────────────────

def test_prompts_all_modes():
    """All 3 prompt modes return non-empty prompts containing 'Aria'."""
    from agents.aria_prompts import get_prompt
    for mode in ["lo_assistant", "inbound_receptionist", "outbound_followup"]:
        prompt = get_prompt(mode)
        assert len(prompt) > 100, f"Prompt for {mode} seems too short"
        assert "Aria" in prompt, f"Prompt for {mode} should mention Aria"


def test_prompt_inbound_has_receptionist_instructions():
    """Inbound receptionist prompt includes greeting and qualification instructions."""
    from agents.aria_prompts import get_prompt
    prompt = get_prompt("inbound_receptionist")
    assert "caller" in prompt.lower()
    assert "greet" in prompt.lower()


def test_prompt_outbound_has_compliance_guardrails():
    """Outbound follow-up prompt includes compliance language."""
    from agents.aria_prompts import get_prompt
    prompt = get_prompt("outbound_followup")
    # Should mention stopping if caller says stop/don't call
    assert "stop" in prompt.lower() or "opt out" in prompt.lower()


def test_prompt_lo_assistant_has_tool_descriptions():
    """LO assistant prompt describes available CRM capabilities."""
    from agents.aria_prompts import get_prompt
    prompt = get_prompt("lo_assistant")
    assert "pipeline" in prompt.lower() or "loan" in prompt.lower()


# ─── Internal routes via TestClient ──────────────────────────────────────────

@pytest.fixture(scope="module")
def test_client():
    """Create a TestClient with mocked DB for internal route testing.

    Also patches module-level INTERNAL_API_KEY in route modules that capture
    the env var at import time (before this test file sets it).
    """
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    import routes.internal.aria_call_routes as call_routes_mod
    import routes.internal.aria_workflow_routes as workflow_routes_mod

    # Patch module-level INTERNAL_API_KEY for routes that captured it at import
    call_routes_mod.INTERNAL_API_KEY = "test-internal-key"
    workflow_routes_mod.INTERNAL_API_KEY = "test-internal-key"

    def _mock_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _mock_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def test_internal_lead_lookup_requires_api_key(test_client):
    """Lead lookup endpoint rejects requests without API key."""
    resp = test_client.post("/internal/aria/lead-lookup", json={"phone": "+18435551234"})
    assert resp.status_code == 403


def test_internal_lead_lookup_with_valid_key(test_client):
    """Lead lookup endpoint responds 200 with valid API key (no lead found is OK)."""
    resp = test_client.post(
        "/internal/aria/lead-lookup",
        json={"phone": "+18435551234"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "lead" in data


def test_internal_loan_status_no_borrower(test_client):
    """Loan status returns spoken summary even when no loan found."""
    resp = test_client.post(
        "/internal/aria/loan-status",
        json={"borrower_id": 99999},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "spoken_summary" in data


def test_internal_tool_execute_unknown_tool(test_client):
    """Tool execute endpoint returns error for unknown tool name."""
    resp = test_client.post(
        "/internal/aria/tool/execute",
        json={"tool_name": "nonexistent_tool_xyz", "params": {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") is not None


def test_internal_lead_info_not_found(test_client):
    """Lead info returns error when lead not found."""
    resp = test_client.post(
        "/internal/aria/lead-info",
        json={"lead_id": 99999},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


def test_internal_trigger_workflow(test_client):
    """Trigger workflow endpoint accepts valid request and returns dispatched status."""
    resp = test_client.post(
        "/internal/aria/trigger-workflow",
        json={"workflow_id": "test-workflow", "params": {}, "lead_id": 1},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "dispatched"
    assert "test-workflow" in data.get("workflow_id", "")


def test_internal_voicemail_drop_unknown_template(test_client):
    """Voicemail drop returns error for unknown template."""
    resp = test_client.post(
        "/internal/aria/call/voicemail-drop",
        json={"lead_id": 1, "intent": "nonexistent_template", "template_context": {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is False
    assert "error" in data


def test_internal_call_log_requires_api_key(test_client):
    """Call log endpoint rejects requests without API key."""
    resp = test_client.post(
        "/internal/aria/call/log",
        json={"direction": "inbound"},
    )
    assert resp.status_code == 403
