# LiveKit Aria Voice Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Aria LiveKit voice agent (`backend/aria/voice_agent.py`) with Telnyx SIP telephony (inbound/outbound calls), warm transfers, voicemail drops with AMD, outbound call approval workflow, and a clean agent-to-backend HTTP boundary with circuit breaker.

**Architecture:** Two-service model — (1) LiveKit agent worker (existing `aria/voice_agent.py`, extended) connects to LiveKit Cloud, handles real-time voice via Claude streaming, (2) existing FastAPI backend gets new `/internal/aria/*` endpoints that expose CRM tools over HTTP. Agent never imports DB directly. Telnyx handles PSTN telephony, LiveKit handles audio rooms, Claude handles conversation.

**Tech Stack:** livekit-agents ~1.5, livekit-plugins-deepgram, livekit-plugins-anthropic, livekit-plugins-cartesia, httpx, tenacity, Telnyx Call Control API, FastAPI internal routes.

**Existing code to build on:**
- `backend/aria/voice_agent.py` — existing LiveKit agent with 13 CRM tools, Deepgram/Cartesia/Claude already configured
- `backend/agents/tools/base.py` — ToolRegistry singleton, `@mortgage_tool` decorator, ToolDefinition/ToolResult types
- `backend/routes/telnyx_webhook_routes.py` — existing Telnyx webhook handler with idempotency, AMD, SMS events
- `backend/routes/_register_telephony.py` — telephony route registration pattern
- `backend/integrations/sms_service.py` — SMSClient for paired voicemail SMS
- `backend/database/models/voice_call_session.py` — VoiceCallSession model (reuse for telephony calls)

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `backend/agents/aria_config.py` | Guardrails, AMD config, voicemail templates, graduation criteria — pure config, no imports from DB |
| `backend/agents/aria_prompts.py` | System prompts for inbound receptionist vs outbound follow-up vs LO assistant modes |
| `backend/agents/aria_backend_client.py` | Circuit breaker HTTP client for agent→backend tool calls (httpx + tenacity) |
| `backend/routes/internal/__init__.py` | Package marker |
| `backend/routes/internal/aria_tool_routes.py` | `/internal/aria/*` endpoints — lead lookup, loan status, schedule appointment (DB access here) |
| `backend/routes/internal/aria_call_routes.py` | `/internal/aria/*` endpoints — warm transfer, voicemail drop, call logging, outbound initiation |
| `backend/routes/internal/aria_workflow_routes.py` | `/internal/aria/trigger-workflow` — dispatches LangGraph workflows on dedicated executor |
| `backend/database/models/call_authorization.py` | CallAuthorization model — TCPA audit trail for every outbound call |
| `backend/tests/test_aria_backend_client.py` | Tests for circuit breaker, timeout, graceful degradation |
| `backend/tests/test_aria_internal_routes.py` | Tests for internal API endpoints |
| `backend/tests/test_aria_config.py` | Tests for guardrail validation, AMD confidence bands, voicemail template rendering |
| `backend/tests/test_call_authorization.py` | Tests for TCPA authorization chain |

### Modified files

| File | Changes |
|---|---|
| `backend/aria/voice_agent.py` | Refactor: replace direct tool execution with HTTP calls via `aria_backend_client`, add SIP/telephony session handling, add turn detection config, add health server |
| `backend/routes/_register_telephony.py` | Add internal aria route registration |
| `backend/routes/telnyx_webhook_routes.py` | Add inbound call routing logic (decide_route → LiveKit SIP bridge) |
| `backend/main.py` | Register internal aria routes, add LangGraph executor to lifespan |
| `backend/database/models/__init__.py` | Export CallAuthorization model |
| `backend/requirements.txt` | Add httpx, tenacity (if not present) |

---

## Task 1: Configuration & Constants

**Files:**
- Create: `backend/agents/aria_config.py`
- Test: `backend/tests/test_aria_config.py`

- [ ] **Step 1: Write the test file**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.aria_config'`

- [ ] **Step 3: Write the config module**

```python
# backend/agents/aria_config.py
"""
Aria Voice Agent Configuration
Guardrails, AMD config, voicemail templates, graduation criteria.
Pure config — no database or service imports.
"""
from typing import Dict, Optional

# ─── AMD Confidence Thresholds ──────────────────────────────────────────────
AMD_HIGH_CONFIDENCE = 0.92
AMD_MEDIUM_CONFIDENCE = 0.75

# ─── Voicemail ──────────────────────────────────────────────────────────────
MAX_VOICEMAIL_SECONDS = 28  # Telnyx cuts at 30s — 2s buffer

VOICEMAIL_TEMPLATES: Dict[str, str] = {
    "appointment_reminder": (
        "Hi {first_name}, this is Aria from Perennia. "
        "Quick reminder — you have a call with {lo_name} tomorrow at {time}. "
        "If you need to reschedule, just reply to the text I'm sending you now. "
        "Talk soon."
    ),
    "rate_lock_expiry": (
        "Hi {first_name}, Aria from Perennia. "
        "Your rate lock on the {loan_amount} {loan_type} expires {expiry_day}. "
        "{lo_name} has a couple of options to discuss — "
        "call us back at {company_phone} or just reply to my text. "
        "Thanks."
    ),
    "document_chase": (
        "Hi {first_name}, Aria from Perennia. "
        "The one thing holding up your file right now is {top_missing_doc}. "
        "You can upload it directly at the link I'm texting you — takes two minutes. "
        "Any questions, reply to that text. Thanks."
    ),
    "post_close": (
        "Hi {first_name}, Aria from Perennia — just calling to say congratulations "
        "on closing! {lo_name} wanted to check in and make sure everything's going smoothly. "
        "Give us a call at {company_phone} whenever you get a chance. "
        "Enjoy the new home."
    ),
}

# ─── Telnyx AMD Configuration ──────────────────────────────────────────────
OUTBOUND_CALL_CONFIG = {
    "answering_machine_detection": "premium",
    "answering_machine_detection_config": {
        "total_analysis_time_millis": 6000,
        "after_greeting_silence_millis": 1000,
        "between_words_silence_millis": 1000,
        "greeting_duration_millis": 3500,
        "initial_silence_millis": 4000,
        "maximum_number_of_words": 5,
        "silence_threshold": 256,
    },
    "timeout_secs": 30,
}

# ─── Autonomous Call Guardrails ─────────────────────────────────────────────
AUTONOMOUS_CALL_GUARDRAILS = {
    "calling_hours": "08:00-20:00 local borrower time",
    "days_allowed": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    "no_call_days": "Federal holidays + state-specific",
    "max_calls_per_lead_day": 1,
    "max_calls_per_lead_week": 3,
    "max_attempts_no_answer": 3,
    "cooling_off_after_dnc": "permanent",
    "permitted_intents": [
        "appointment_reminder",
        "document_chase",
        "rate_lock_expiry_warning",
        "closing_date_reminder",
        "post_close_satisfaction",
    ],
    "never_autonomous": [
        "first_touch",
        "rate_renegotiation",
        "price_objection_handling",
        "complaint_resolution",
        "legal_reference_in_file",
    ],
    "immediate_lo_alert": [
        "borrower_mentions_lawyer",
        "borrower_mentions_complaint",
        "borrower_expresses_distress",
        "dnc_request",
        "three_consecutive_no_answers",
        "call_duration_under_15_seconds",
    ],
}

# ─── Graduation Criteria (Phase B → C) ─────────────────────────────────────
GRADUATION_CRITERIA = {
    "appointment_reminder": {
        "min_calls": 50,
        "lo_override_rate": 0.05,
        "call_success_rate": 0.80,
        "complaint_rate": 0.00,
    },
    "rate_lock_reminder": {
        "min_calls": 30,
        "lo_override_rate": 0.08,
        "call_success_rate": 0.75,
        "complaint_rate": 0.00,
    },
    "document_chase": {
        "min_calls": 40,
        "lo_override_rate": 0.10,
        "call_success_rate": 0.70,
        "complaint_rate": 0.00,
    },
}


# ─── Helper Functions ───────────────────────────────────────────────────────

def render_voicemail_template(template_name: str, context: Dict[str, str]) -> Optional[str]:
    template = VOICEMAIL_TEMPLATES.get(template_name)
    if template is None:
        return None
    try:
        return template.format(**context)
    except KeyError:
        return template.format_map({**{k: "" for k in _extract_placeholders(template)}, **context})


def _extract_placeholders(template: str) -> list:
    import re
    return re.findall(r"\{(\w+)\}", template)


def is_intent_autonomous_eligible(intent: str) -> bool:
    if intent in AUTONOMOUS_CALL_GUARDRAILS["never_autonomous"]:
        return False
    return intent in AUTONOMOUS_CALL_GUARDRAILS["permitted_intents"]


def get_amd_action(result: str, confidence: float) -> str:
    if result == "human":
        return "route_to_agent"
    if result == "machine" and confidence >= AMD_HIGH_CONFIDENCE:
        return "voicemail_full"
    if result == "machine" and confidence >= AMD_MEDIUM_CONFIDENCE:
        return "voicemail_short"
    return "no_voicemail"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_config.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/aria_config.py backend/tests/test_aria_config.py
git commit -m "feat(aria): add voice agent config — guardrails, AMD bands, voicemail templates"
```

---

## Task 2: System Prompts

**Files:**
- Create: `backend/agents/aria_prompts.py`

- [ ] **Step 1: Write the prompts module**

```python
# backend/agents/aria_prompts.py
"""
Aria Voice Agent System Prompts
Separate prompts for each call mode — the LLM needs different instructions
for inbound receptionist vs outbound follow-up vs LO assistant.
"""

INBOUND_RECEPTIONIST_PROMPT = """\
You are Aria, the AI receptionist for {company_name}, a mortgage lending company.

A caller just dialed in. Your job:
1. Greet them warmly — "Thanks for calling {company_name}, this is Aria. How can I help you today?"
2. Identify who they are — ask for name, then look them up in the CRM
3. Understand what they need — rate quote, application status, speak with their LO, general question
4. If they're a new prospect, qualify them: loan purpose (purchase/refi), property type, rough timeline, credit range
5. If they need their LO, use warm_transfer_to_lo — give the LO a verbal brief before connecting them

Voice guidelines:
- Keep responses under 30 words when possible
- Use natural speech: "three fifty K" not "$350,000"
- One question at a time — never stack questions
- If looking something up, say "Let me check that" then do it
- Fill ring gaps naturally: "One moment while I get them on the line"

You have access to the CRM and can look up leads, check loan status, and book appointments.
When you're ready to hand off to a loan officer, use the warm_transfer_to_lo tool."""

OUTBOUND_FOLLOWUP_PROMPT = """\
You are Aria, calling {first_name} on behalf of {lo_name} at {company_name}.

Call purpose: {call_purpose}
Context: {call_context}

Guidelines:
- Identify yourself immediately: "Hi {first_name}, this is Aria calling from {company_name} on behalf of {lo_name}."
- State the reason for your call in one sentence
- Be helpful but brief — this is a phone call, not a meeting
- If they have questions you can answer, answer them
- If they need their LO, offer to transfer or schedule a callback
- If they want to opt out, respect it immediately and confirm

Never:
- Pressure or use urgency tactics
- Discuss rates or terms you're not certain about
- Continue the call if they say "stop" or "don't call me"
- Leave a message if this is a live pickup — only leave voicemail on machine detection"""

LO_ASSISTANT_PROMPT = """\
You are Aria, the AI voice assistant for Perennia AI — an all-in-one operating \
system for mortgage loan officers.

You are speaking with a loan officer via real-time voice. Be warm, professional, and concise.

Voice conversation guidelines:
- Keep responses under 40 words when possible — you're in a voice conversation, not a chat
- Use natural speech patterns. Say "three fifty K" not "$350,000"
- When performing actions, briefly confirm: "Done — I sent that text to John"
- If you need to look something up, say "Let me check that" (don't narrate the tool call)
- Ask one clarifying question at a time, never multiple
- For numbers and dates, speak them naturally: "next Tuesday at two PM"

You have full access to the CRM system and can:
- Look up leads, contacts, and loan pipeline status
- Check SLA timers and compliance alerts
- Send text messages and emails on behalf of the LO
- Create tasks, follow-ups, and appointments
- Provide mortgage rate information and guidelines
- Run pipeline analytics and reporting
- Schedule appointments and manage calendar

When the LO asks you to do something, do it — don't just describe what you could do.
If a tool call fails, say so briefly and offer an alternative."""


def get_prompt(mode: str, context: dict = None) -> str:
    context = context or {}
    prompts = {
        "inbound_receptionist": INBOUND_RECEPTIONIST_PROMPT,
        "outbound_followup": OUTBOUND_FOLLOWUP_PROMPT,
        "lo_assistant": LO_ASSISTANT_PROMPT,
    }
    template = prompts.get(mode, LO_ASSISTANT_PROMPT)
    try:
        return template.format_map({**_defaults(), **context})
    except KeyError:
        return template


def _defaults() -> dict:
    return {
        "company_name": "Perennia AI",
        "lo_name": "",
        "first_name": "",
        "call_purpose": "",
        "call_context": "",
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/agents/aria_prompts.py
git commit -m "feat(aria): add mode-specific system prompts — receptionist, outbound, LO assistant"
```

---

## Task 3: Circuit Breaker Backend Client

**Files:**
- Create: `backend/agents/aria_backend_client.py`
- Test: `backend/tests/test_aria_backend_client.py`

- [ ] **Step 1: Add httpx and tenacity to requirements**

Check if already present in `backend/requirements.txt`. If not, add:
```
httpx>=0.27.0
tenacity>=8.2.0
```

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && grep -E "^(httpx|tenacity)" requirements.txt`

If missing, append them. Then install:
Run: `cd /Users/timothyloss/my-project/mortgage-crm && .venv/bin/pip install httpx tenacity`

- [ ] **Step 2: Write the test file**

```python
# backend/tests/test_aria_backend_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from agents.aria_backend_client import call_backend_tool, BACKEND_TIMEOUT


@pytest.mark.asyncio
async def test_call_backend_tool_success():
    mock_response = httpx.Response(200, json={"spoken_summary": "Your loan is in underwriting."})
    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.return_value = mock_response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await call_backend_tool("/internal/aria/loan-status", {"borrower_id": 42})
        assert result == {"spoken_summary": "Your loan is in underwriting."}
        instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_call_backend_tool_timeout():
    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = httpx.TimeoutException("timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(httpx.TimeoutException):
            await call_backend_tool("/internal/aria/test", {})


@pytest.mark.asyncio
async def test_call_backend_tool_retries_on_500():
    error_response = httpx.Response(500)
    success_response = httpx.Response(200, json={"ok": True})

    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = [
            httpx.HTTPStatusError("500", request=httpx.Request("POST", "http://test"), response=error_response),
            success_response,
        ]
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await call_backend_tool("/internal/aria/test", {})
        assert result == {"ok": True}
        assert instance.post.call_count == 2


def test_backend_timeout_is_3_seconds():
    assert BACKEND_TIMEOUT == 3.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_backend_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write the backend client**

```python
# backend/agents/aria_backend_client.py
"""
Circuit-breaker HTTP client for Aria agent → FastAPI backend tool calls.

All CRM data access goes through this client. The agent process never
imports from db, database.models, or services directly.

3-second timeout. 2 retries with exponential backoff. Graceful degradation.
"""
import os
import logging
from typing import Dict, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("aria.backend_client")

BACKEND_URL = os.environ.get("INTERNAL_BACKEND_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BACKEND_TIMEOUT = 3.0

GRACEFUL_FALLBACK = (
    "I'm having a little trouble pulling that up right now. "
    "Let me have your loan officer send you an update directly — "
    "I'll flag it for them."
)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=0.3),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
)
async def call_backend_tool(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = INTERNAL_API_KEY
    async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
        resp = await client.post(
            f"{BACKEND_URL}{endpoint}",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def call_backend_tool_safe(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call backend with graceful degradation — returns fallback on failure."""
    try:
        return await call_backend_tool(endpoint, payload)
    except Exception as e:
        logger.warning(f"Backend tool call failed ({endpoint}): {e}")
        return {"error": True, "spoken_fallback": GRACEFUL_FALLBACK}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_backend_client.py -v`
Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agents/aria_backend_client.py backend/tests/test_aria_backend_client.py backend/requirements.txt
git commit -m "feat(aria): add circuit-breaker HTTP client for agent→backend tool calls"
```

---

## Task 4: CallAuthorization Model (TCPA Audit Trail)

**Files:**
- Create: `backend/database/models/call_authorization.py`
- Modify: `backend/database/models/__init__.py`
- Test: `backend/tests/test_call_authorization.py`

- [ ] **Step 1: Write the test file**

```python
# backend/tests/test_call_authorization.py
import pytest
from database.models.call_authorization import CallAuthorization


def test_call_authorization_has_required_columns():
    columns = {c.name for c in CallAuthorization.__table__.columns}
    required = {
        "id", "lead_id", "call_id", "authorization_type",
        "authorized_by", "rule_id", "borrower_consent_source",
        "borrower_consent_date", "created_at",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_call_authorization_table_name():
    assert CallAuthorization.__tablename__ == "call_authorizations"


def test_authorization_type_values():
    auth = CallAuthorization(authorization_type="lo_manual", lead_id=1)
    assert auth.authorization_type == "lo_manual"
    auth2 = CallAuthorization(authorization_type="auto_rule", lead_id=1, rule_id="appointment_reminder_v2")
    assert auth2.rule_id == "appointment_reminder_v2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_call_authorization.py -v`
Expected: FAIL

- [ ] **Step 3: Write the model**

```python
# backend/database/models/call_authorization.py
"""
TCPA Call Authorization audit trail.
Every outbound call — manual, LO-approved, or autonomous — gets a record.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Index
import uuid

from db import Base


class CallAuthorization(Base):
    __tablename__ = "call_authorizations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    call_id = Column(PG_UUID(as_uuid=True), nullable=True)
    authorization_type = Column(String, nullable=False)  # lo_manual, lo_approval, auto_rule
    authorized_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rule_id = Column(String, nullable=True)
    borrower_consent_source = Column(String, nullable=True)  # web_form, verbal, signed_disclosure
    borrower_consent_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_call_auth_lead_created", "lead_id", "created_at"),
    )
```

- [ ] **Step 4: Add to model exports**

Open `backend/database/models/__init__.py`. Add this import alongside the other model imports:
```python
from .call_authorization import CallAuthorization
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_call_authorization.py -v`
Expected: all 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/database/models/call_authorization.py backend/database/models/__init__.py backend/tests/test_call_authorization.py
git commit -m "feat(aria): add CallAuthorization model for TCPA audit trail"
```

---

## Task 5: Internal API Routes — Tool Endpoints

**Files:**
- Create: `backend/routes/internal/__init__.py`
- Create: `backend/routes/internal/aria_tool_routes.py`
- Test: `backend/tests/test_aria_internal_routes.py`

- [ ] **Step 1: Create the package marker**

```python
# backend/routes/internal/__init__.py
```

- [ ] **Step 2: Write the test file**

```python
# backend/tests/test_aria_internal_routes.py
import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

from main import app

client = TestClient(app)
HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def test_internal_lead_lookup_requires_api_key():
    resp = client.post("/internal/aria/lead-lookup", json={"phone": "+18435551234"})
    assert resp.status_code == 403


def test_internal_lead_lookup_with_valid_key():
    resp = client.post(
        "/internal/aria/lead-lookup",
        json={"phone": "+18435551234"},
        headers=HEADERS,
    )
    # Should return 200 even if no lead found (empty result, not error)
    assert resp.status_code == 200
    data = resp.json()
    assert "lead" in data


def test_internal_tool_execute_unknown_tool():
    resp = client.post(
        "/internal/aria/tool/execute",
        json={"tool_name": "nonexistent_tool_xyz", "params": {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_internal_routes.py -v -x`
Expected: FAIL (routes not registered yet)

- [ ] **Step 4: Write the internal tool routes**

```python
# backend/routes/internal/aria_tool_routes.py
"""
Internal API endpoints for Aria voice agent tool calls.
These endpoints are called by the LiveKit agent worker via HTTP.
Auth: X-Internal-API-Key header (shared secret, no user JWT).
"""
import os
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.internal")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal"])

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _verify_internal_key(request: Request):
    key = request.headers.get("X-Internal-API-Key", "")
    if not INTERNAL_API_KEY or key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# ─── Request/Response Schemas ───────────────────────────────────────────────

class LeadLookupRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    lead_id: Optional[int] = None

class ToolExecuteRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}

class LeadInfoRequest(BaseModel):
    lead_id: int

class LoanStatusRequest(BaseModel):
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/lead-lookup")
async def lead_lookup(
    req: LeadLookupRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    lead = None
    if req.lead_id:
        lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    elif req.phone:
        from integrations.sms_service import _to_e164
        normalized = _to_e164(req.phone) or req.phone
        lead = db.query(Lead).filter(Lead.phone == normalized).first()
        if not lead:
            lead = db.query(Lead).filter(Lead.phone == req.phone).first()
    elif req.email:
        lead = db.query(Lead).filter(Lead.email == req.email).first()

    if not lead:
        return {"lead": None}

    return {
        "lead": {
            "id": lead.id,
            "first_name": getattr(lead, "first_name", None) or lead.name,
            "last_name": getattr(lead, "last_name", ""),
            "phone": lead.phone,
            "email": lead.email,
            "stage": lead.stage,
            "owner_id": lead.owner_id,
            "organization_id": lead.organization_id,
            "preferred_communication": getattr(lead, "preferred_communication", None),
            "loan_type": getattr(lead, "loan_type", None),
            "loan_amount": str(getattr(lead, "loan_amount", "")) if getattr(lead, "loan_amount", None) else None,
            "credit_score": getattr(lead, "credit_score", None),
        }
    }


@router.post("/lead-info")
async def lead_info(
    req: LeadInfoRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_internal_key(request)
    from database.models.lead_loan import Lead
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found"}
    return {
        "first_name": getattr(lead, "first_name", None) or lead.name,
        "last_name": getattr(lead, "last_name", ""),
        "phone": lead.phone,
        "email": lead.email,
        "stage": lead.stage,
        "owner_id": lead.owner_id,
    }


@router.post("/loan-status")
async def loan_status(
    req: LoanStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_internal_key(request)
    from database.models.lead_loan import Loan, Lead

    loan = None
    if req.loan_id:
        loan = db.query(Loan).filter(Loan.id == req.loan_id).first()
    elif req.borrower_id:
        lead = db.query(Lead).filter(Lead.id == req.borrower_id).first()
        if lead:
            loan = db.query(Loan).filter(Loan.lead_id == lead.id).order_by(Loan.created_at.desc()).first()

    if not loan:
        return {"spoken_summary": "I couldn't find an active loan on file for that borrower."}

    stage = getattr(loan, "stage", "unknown")
    loan_type = getattr(loan, "loan_type", "")
    amount = getattr(loan, "loan_amount", "")
    amount_str = f"${amount:,.0f}" if amount else "unknown amount"

    return {
        "spoken_summary": f"The {loan_type or 'loan'} for {amount_str} is currently in {stage.replace('_', ' ').lower()}.",
        "stage": stage,
        "loan_type": loan_type,
        "loan_amount": str(amount) if amount else None,
        "loan_id": loan.id,
    }


@router.post("/tool/execute")
async def execute_tool(
    req: ToolExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generic tool execution — runs any @mortgage_tool by name."""
    _verify_internal_key(request)

    try:
        from agents.tools.base import ToolRegistry
        registry = ToolRegistry()
        tool_def = registry.get(req.tool_name)
    except Exception as e:
        return {"error": f"Tool registry unavailable: {e}"}

    if tool_def is None:
        return {"error": f"Tool '{req.tool_name}' not found"}

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tool_def.func(**req.params))
        if hasattr(result, "to_dict"):
            return {"result": result.to_dict()}
        return {"result": result}
    except Exception as e:
        logger.error(f"Tool {req.tool_name} failed: {e}")
        return {"error": str(e)}


@router.post("/lo-info")
async def lo_info(
    request: Request,
    db: Session = Depends(get_db),
    lead_id: int = None,
    user_id: int = None,
):
    """Get the assigned LO for a lead, or info about a specific user."""
    _verify_internal_key(request)
    from database.models.core import User
    from database.models.lead_loan import Lead

    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead or not lead.owner_id:
            return {"error": "No LO assigned to this lead"}
        user_id = lead.owner_id

    if not user_id:
        return {"error": "No user_id or lead_id provided"}

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": f"User {user_id} not found"}

    return {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "phone": user.phone or "",
        "email": user.email,
        "timezone": getattr(user, "timezone", "America/Chicago"),
    }
```

- [ ] **Step 5: Register routes in _register_telephony.py**

Add this block at the end of `register_telephony_routes()` in `backend/routes/_register_telephony.py`:

```python
    # Include Aria Internal API routes (agent-to-backend tool calls)
    try:
        from routes.internal.aria_tool_routes import router as aria_tool_router
        app.include_router(aria_tool_router, tags=["Aria Internal"])
        logger.info("Aria Internal Tool routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Tool routes: {e}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_internal_routes.py -v -x`
Expected: all 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routes/internal/__init__.py backend/routes/internal/aria_tool_routes.py backend/routes/_register_telephony.py backend/tests/test_aria_internal_routes.py
git commit -m "feat(aria): add internal API routes for agent→backend tool calls"
```

---

## Task 6: Internal API Routes — Call & Workflow Endpoints

**Files:**
- Create: `backend/routes/internal/aria_call_routes.py`
- Create: `backend/routes/internal/aria_workflow_routes.py`

- [ ] **Step 1: Write the call routes**

```python
# backend/routes/internal/aria_call_routes.py
"""
Internal API endpoints for Aria call management.
Warm transfer, voicemail drop, call logging, outbound initiation.
"""
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.internal.calls")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal Calls"])

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
TELNYX_API_KEY = os.environ.get("TELNYX_API_KEY", "")
TELNYX_PHONE_NUMBER = os.environ.get("TELNYX_PHONE_NUMBER", "")
TELNYX_CONNECTION_ID = os.environ.get("TELNYX_CONNECTION_ID", "")


def _verify_internal_key(request: Request):
    key = request.headers.get("X-Internal-API-Key", "")
    if not INTERNAL_API_KEY or key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# ─── Schemas ────────────────────────────────────────────────────────────────

class InitiateOutboundRequest(BaseModel):
    to_phone: str
    lead_id: Optional[int] = None
    intent: str = "general"
    authorization_type: str = "lo_manual"
    authorized_by: Optional[int] = None
    rule_id: Optional[str] = None

class LogCallRequest(BaseModel):
    lead_id: Optional[int] = None
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    direction: str = "inbound"
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    outcome: Optional[str] = None
    transcript: Optional[list] = None
    tools_executed: Optional[list] = None
    livekit_room_name: Optional[str] = None

class VoicemailDropRequest(BaseModel):
    lead_id: int
    intent: str
    template_context: dict = {}


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/call/initiate-outbound")
async def initiate_outbound_call(
    req: InitiateOutboundRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Initiate an outbound call via Telnyx, bridging into a LiveKit room."""
    _verify_internal_key(request)

    from integrations.sms_service import _to_e164
    normalized = _to_e164(req.to_phone)
    if not normalized:
        return {"success": False, "error": f"Invalid phone: {req.to_phone}"}

    # Record TCPA authorization
    try:
        from database.models.call_authorization import CallAuthorization
        auth_record = CallAuthorization(
            lead_id=req.lead_id or 0,
            authorization_type=req.authorization_type,
            authorized_by=req.authorized_by,
            rule_id=req.rule_id,
        )
        db.add(auth_record)
        db.flush()
    except Exception as e:
        logger.error(f"Failed to record call authorization: {e}")

    # Place call via Telnyx Call Control API
    from agents.aria_config import OUTBOUND_CALL_CONFIG
    import requests

    try:
        payload = {
            "to": normalized,
            "from": TELNYX_PHONE_NUMBER,
            "connection_id": TELNYX_CONNECTION_ID,
            "answering_machine_detection": OUTBOUND_CALL_CONFIG["answering_machine_detection"],
            "answering_machine_detection_config": OUTBOUND_CALL_CONFIG["answering_machine_detection_config"],
            "timeout_secs": OUTBOUND_CALL_CONFIG["timeout_secs"],
            "webhook_url": f"{os.getenv('API_URL', 'https://api.perenniaai.com')}/api/v1/telnyx/webhook",
        }

        resp = requests.post(
            "https://api.telnyx.com/v2/calls",
            headers={
                "Authorization": f"Bearer {TELNYX_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            call_control_id = data.get("data", {}).get("call_control_id")
            return {"success": True, "call_control_id": call_control_id}
        else:
            logger.error(f"Telnyx call initiation failed: {resp.status_code} {resp.text[:200]}")
            return {"success": False, "error": "Failed to initiate call"}
    except Exception as e:
        logger.error(f"Outbound call error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/call/log")
async def log_call(
    req: LogCallRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Log a completed call session to the database."""
    _verify_internal_key(request)

    try:
        from database.models.voice_call_session import VoiceCallSession

        session = VoiceCallSession(
            organization_id=req.organization_id,
            user_id=req.user_id,
            lead_id=req.lead_id,
            direction=req.direction,
            status="completed",
            duration_seconds=req.duration_seconds,
            summary=req.summary,
            outcome=req.outcome,
            transcript=req.transcript or [],
            tools_executed=req.tools_executed or [],
        )
        db.add(session)
        db.commit()
        return {"success": True, "session_id": session.id}
    except Exception as e:
        logger.error(f"Failed to log call: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


@router.post("/call/voicemail-drop")
async def voicemail_drop(
    req: VoicemailDropRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Record a voicemail drop and send paired SMS."""
    _verify_internal_key(request)

    from agents.aria_config import render_voicemail_template

    message = render_voicemail_template(req.intent, req.template_context)
    if not message:
        return {"success": False, "error": f"Unknown voicemail template: {req.intent}"}

    # Send paired SMS (non-blocking)
    try:
        from integrations.sms_service import SMSClient
        sms_client = SMSClient(db)
        phone = req.template_context.get("phone", "")
        if phone:
            asyncio.create_task(
                sms_client.send_sms(
                    to_phone=phone,
                    message=message,
                    lead_id=req.lead_id,
                    bypass_compliance=False,
                )
            )
    except Exception as e:
        logger.warning(f"Paired SMS failed: {e}")

    return {"success": True, "voicemail_text": message}
```

- [ ] **Step 2: Write the workflow routes**

```python
# backend/routes/internal/aria_workflow_routes.py
"""
Internal API for dispatching LangGraph workflows from the Aria agent.
Workflows run on a dedicated thread pool executor to avoid blocking API workers.
"""
import logging
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import os

from database import get_db

logger = logging.getLogger("aria.internal.workflows")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal Workflows"])

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _verify_internal_key(request: Request):
    key = request.headers.get("X-Internal-API-Key", "")
    if not INTERNAL_API_KEY or key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")


class WorkflowRequest(BaseModel):
    workflow_id: str
    params: Dict[str, Any] = {}
    lead_id: Optional[int] = None
    user_id: Optional[int] = None


@router.post("/trigger-workflow")
async def trigger_workflow(
    req: WorkflowRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Dispatch a LangGraph workflow asynchronously.
    Returns immediately — the workflow runs in background on a dedicated executor.
    """
    _verify_internal_key(request)

    executor = getattr(request.app.state, "langgraph_executor", None)
    if executor is None:
        logger.warning("LangGraph executor not configured — running inline")

    logger.info(f"Dispatching workflow: {req.workflow_id} for lead={req.lead_id}")

    # For now, log the dispatch. Full LangGraph integration wired in a later task.
    return {
        "status": "dispatched",
        "workflow_id": req.workflow_id,
        "message": f"Workflow {req.workflow_id} queued for execution.",
    }
```

- [ ] **Step 3: Register the new routes**

Add these blocks to `register_telephony_routes()` in `backend/routes/_register_telephony.py`:

```python
    # Include Aria Internal Call routes
    try:
        from routes.internal.aria_call_routes import router as aria_call_router
        app.include_router(aria_call_router, tags=["Aria Internal Calls"])
        logger.info("Aria Internal Call routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Call routes: {e}")

    # Include Aria Internal Workflow routes
    try:
        from routes.internal.aria_workflow_routes import router as aria_workflow_router
        app.include_router(aria_workflow_router, tags=["Aria Internal Workflows"])
        logger.info("Aria Internal Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Workflow routes: {e}")
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/internal/aria_call_routes.py backend/routes/internal/aria_workflow_routes.py backend/routes/_register_telephony.py
git commit -m "feat(aria): add internal call and workflow API routes"
```

---

## Task 7: Add LangGraph Executor to FastAPI Lifespan

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Find the lifespan function in main.py**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && grep -n "async def lifespan\|asynccontextmanager\|app = FastAPI" main.py | head -10`

- [ ] **Step 2: Add the LangGraph executor to the lifespan**

Find the lifespan context manager. Inside its startup section (before `yield`), add:

```python
    # Dedicated executor for LangGraph workflows — keeps them off the main event loop
    from concurrent.futures import ThreadPoolExecutor
    langgraph_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph")
    app.state.langgraph_executor = langgraph_executor
```

In the shutdown section (after `yield`), add:

```python
    langgraph_executor.shutdown(wait=False)
```

If the project uses `@app.on_event("startup")` / `@app.on_event("shutdown")` instead of lifespan, add the executor creation in the startup handler and shutdown in the shutdown handler.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat(aria): add dedicated LangGraph thread pool executor to FastAPI lifespan"
```

---

## Task 8: Refactor Voice Agent — HTTP Boundary + Turn Detection + Health Server

This is the core task — refactoring `backend/aria/voice_agent.py` to use the HTTP backend client instead of direct tool execution, add SIP telephony session handling, and add the Railway health server.

**Files:**
- Modify: `backend/aria/voice_agent.py`

- [ ] **Step 1: Read the current file**

Run: `cat backend/aria/voice_agent.py`

Verify the file matches what we read earlier (AriaVoiceAgent class with 13 @function_tool methods, AgentServer with aria_voice_session handler).

- [ ] **Step 2: Rewrite voice_agent.py**

Replace the entire file. Key changes:
1. Replace `_execute_crm_tool()` (direct registry calls) with `call_backend_tool_safe()` (HTTP)
2. Add semantic turn detection (`MultilingualModel` with min/max endpointing delays)
3. Add health server for Railway
4. Add SIP telephony session handler alongside the existing WebRTC handler
5. Add mode-specific prompts (receptionist, outbound, LO assistant)
6. Add warm transfer tool
7. Keep existing tool definitions but route through HTTP

```python
# backend/aria/voice_agent.py
"""
Perennia AI — Aria LiveKit Voice Agent Worker

Two session types:
  - WebRTC (browser/mobile) — LO assistant mode
  - SIP (Telnyx telephony) — inbound receptionist / outbound follow-up

Run:
  python -m aria.voice_agent dev     # development
  python -m aria.voice_agent start   # production
"""

import os
import json
import logging
import asyncio
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from livekit import agents, api as livekit_api
from livekit.agents import (
    Agent,
    AgentSession,
    RunContext,
    function_tool,
    AgentServer,
    MultilingualModel,
)
from livekit.plugins import cartesia, deepgram
from livekit.plugins.anthropic import LLM as AnthropicLLM

from agents.aria_backend_client import call_backend_tool_safe
from agents.aria_prompts import get_prompt

logger = logging.getLogger("aria.voice_agent")

# ─── Configuration ───────────────────────────────────────────────────────────

CARTESIA_VOICE_ID = os.getenv(
    "ARIA_CARTESIA_VOICE_ID",
    "a0e99841-438c-4a64-b679-ae501e7d6091",  # Jacqueline
)
CLAUDE_MODEL = os.getenv("ARIA_LLM_MODEL", "claude-sonnet-4-20250514")
TELNYX_TRUNK_ID = os.getenv("TELNYX_SIP_TRUNK_ID", "")


# ─── Health Server (Railway worker health check) ────────────────────────────

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"healthy")

    def log_message(self, *args):
        pass


def _start_health_server():
    port = int(os.environ.get("PORT", 8081))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"[AriaVoice] Health server on port {port}")


# ─── Aria Agent ──────────────────────────────────────────────────────────────

class AriaVoiceAgent(Agent):
    """Aria — Perennia AI's real-time voice assistant."""

    def __init__(self, mode: str = "lo_assistant", context: dict = None) -> None:
        prompt = get_prompt(mode, context or {})
        super().__init__(instructions=prompt)
        self._mode = mode
        self._session_data: Dict[str, Any] = {
            "mode": mode,
            "tools_executed": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    async def on_enter(self) -> None:
        greetings = {
            "lo_assistant": "Greet the loan officer briefly. Say something like 'Hey, Aria here. What can I help you with?'",
            "inbound_receptionist": "Greet the caller warmly. Say 'Thanks for calling Perennia, this is Aria. How can I help you today?'",
            "outbound_followup": "Introduce yourself briefly using the context in your instructions.",
        }
        await self.session.generate_reply(
            instructions=greetings.get(self._mode, greetings["lo_assistant"])
        )

    # ─── CRM Tools (all via HTTP backend) ─────────────────────────────

    @function_tool()
    async def search_pipeline(self, context: RunContext, query: str):
        """Search the loan pipeline by borrower name, loan number, or stage."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "search_pipeline", "params": {"query": query}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_pipeline_summary(self, context: RunContext):
        """Get a summary of the current loan pipeline — total loans, by stage, SLA alerts."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_pipeline_summary", "params": {}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def search_leads(self, context: RunContext, query: str):
        """Search for leads by name, email, or phone number."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "search_leads", "params": {"query": query}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_lead_details(self, context: RunContext, lead_id: int):
        """Get full details for a specific lead by ID."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_lead_details", "params": {"lead_id": lead_id}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_loan_status(self, context: RunContext, lead_id: int):
        """Check the current loan status for a borrower."""
        result = await call_backend_tool_safe(
            "/internal/aria/loan-status",
            {"borrower_id": lead_id},
        )
        if result.get("spoken_summary"):
            return result["spoken_summary"]
        return json.dumps(result, default=str)

    @function_tool()
    async def send_sms(self, context: RunContext, recipient_name: str, phone_number: str, message: str):
        """Send an SMS text message to a contact."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "send_sms_message", "params": {
                "recipient_name": recipient_name,
                "phone_number": phone_number,
                "message": message,
            }},
        )
        self._session_data["tools_executed"].append({
            "tool": "send_sms", "recipient": recipient_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def create_task(self, context: RunContext, title: str, description: str = "", due_date: str = "", priority: str = "medium"):
        """Create a task or follow-up item."""
        params = {"title": title, "description": description, "priority": priority}
        if due_date:
            params["due_date"] = due_date
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "create_task", "params": params},
        )
        self._session_data["tools_executed"].append({
            "tool": "create_task", "title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def get_sla_alerts(self, context: RunContext):
        """Get current SLA alerts and overdue items."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_sla_alerts", "params": {}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def check_rates(self, context: RunContext, loan_type: str = "conventional"):
        """Check current mortgage rates."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_current_rates", "params": {"loan_type": loan_type}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def schedule_appointment(self, context: RunContext, title: str, date: str, time: str, duration_minutes: int = 30, attendee_name: str = "", attendee_email: str = ""):
        """Schedule a new appointment."""
        params = {"title": title, "date": date, "time": time, "duration_minutes": duration_minutes}
        if attendee_name:
            params["attendee_name"] = attendee_name
        if attendee_email:
            params["attendee_email"] = attendee_email
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "schedule_appointment", "params": params},
        )
        self._session_data["tools_executed"].append({
            "tool": "schedule_appointment", "title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def get_daily_briefing(self, context: RunContext):
        """Get a morning briefing with today's tasks, appointments, pipeline updates, and alerts."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_daily_briefing", "params": {}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def look_up_caller(self, context: RunContext, phone_number: str):
        """Look up a caller by phone number in the CRM. Use this when receiving an inbound call."""
        result = await call_backend_tool_safe(
            "/internal/aria/lead-lookup",
            {"phone": phone_number},
        )
        lead = result.get("lead")
        if not lead:
            return "I don't have this caller in the system yet — they're a new prospect."
        return json.dumps(lead, default=str)

    @function_tool()
    async def warm_transfer_to_lo(self, context: RunContext, reason: str, summary: str):
        """Transfer the caller to their assigned loan officer with a verbal brief. Use when the caller needs to speak with their LO directly. Reason: ready_to_apply, complex_scenario, or customer_request."""
        room_name = context.session.room.name if context.session and context.session.room else None
        if not room_name:
            return "I can't transfer right now — no active call room."

        metadata = {}
        if context.session and context.session.room:
            try:
                metadata = json.loads(context.session.room.metadata or "{}")
            except (json.JSONDecodeError, AttributeError):
                pass

        lead_id = metadata.get("lead_id") or metadata.get("borrower_id")
        if not lead_id:
            return "I don't know which borrower this is — I can't look up their loan officer without an ID."

        lo = await call_backend_tool_safe("/internal/aria/lo-info", {"lead_id": lead_id})
        if lo.get("error"):
            return f"I couldn't find an assigned loan officer: {lo['error']}"

        borrower = await call_backend_tool_safe("/internal/aria/lead-info", {"lead_id": lead_id})

        # Add LO as SIP participant to the current LiveKit room
        if TELNYX_TRUNK_ID and lo.get("phone"):
            try:
                lk_api = livekit_api.LiveKitAPI()
                await lk_api.sip.create_sip_participant(
                    livekit_api.CreateSIPParticipantRequest(
                        sip_trunk_id=TELNYX_TRUNK_ID,
                        sip_call_to=lo["phone"],
                        room_name=room_name,
                        participant_identity=f"lo_{lo['id']}",
                        participant_name=lo.get("full_name", "Loan Officer"),
                    )
                )
            except Exception as e:
                logger.error(f"SIP transfer failed: {e}")
                return f"I wasn't able to connect the call — the transfer failed. {lo.get('full_name', 'Your loan officer')} can be reached at {lo.get('phone', 'their direct number')}."

        borrower_name = borrower.get("first_name", "the caller")
        lo_name = lo.get("first_name", "")

        return (
            f"{lo_name}, I have {borrower_name} on the line. "
            f"{summary} "
            f"I'll let you two take it from here."
        )

    @function_tool()
    async def run_crm_tool(self, context: RunContext, tool_name: str, parameters: str = "{}"):
        """Run any CRM tool by name with JSON parameters. Fallback for tools without a specific wrapper."""
        try:
            params = json.loads(parameters)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON parameters"})
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": tool_name, "params": params},
        )
        return json.dumps(result, default=str)


# ─── Agent Server ────────────────────────────────────────────────────────────

server = AgentServer()


def _build_session(mode: str = "lo_assistant", context: dict = None) -> tuple:
    """Build AgentSession + AriaVoiceAgent for a given mode."""
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=AnthropicLLM(model=CLAUDE_MODEL),
        tts=cartesia.TTS(model="sonic-3", voice=CARTESIA_VOICE_ID),
        turn_detection=MultilingualModel(),
        min_endpointing_delay=0.4,
        max_endpointing_delay=6.0,
    )
    agent = AriaVoiceAgent(mode=mode, context=context)
    return session, agent


@server.rtc_session(agent_name="aria-voice")
async def aria_voice_session(ctx: agents.JobContext):
    """WebRTC session — LO using the browser/mobile voice interface."""
    logger.info(f"[AriaVoice] WebRTC session: room={ctx.room.name}")
    session, agent = _build_session("lo_assistant")
    await session.start(room=ctx.room, agent=agent)


@server.rtc_session(agent_name="aria-telephony")
async def aria_telephony_session(ctx: agents.JobContext):
    """SIP session — inbound or outbound phone call via Telnyx."""
    logger.info(f"[AriaVoice] Telephony session: room={ctx.room.name}")

    metadata = {}
    try:
        metadata = json.loads(ctx.room.metadata or "{}")
    except (json.JSONDecodeError, AttributeError):
        pass

    trigger = metadata.get("trigger", "inbound_call")
    mode = "inbound_receptionist" if trigger == "inbound_call" else "outbound_followup"
    context = {
        "first_name": metadata.get("borrower_name", ""),
        "lo_name": metadata.get("lo_name", ""),
        "call_purpose": metadata.get("call_purpose", ""),
        "call_context": metadata.get("call_context", ""),
    }

    session, agent = _build_session(mode, context)
    await session.start(room=ctx.room, agent=agent)


# ─── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _start_health_server()
    agents.cli.run_app(server)
```

- [ ] **Step 3: Verify the agent starts without errors**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && LIVEKIT_URL=wss://test.livekit.cloud LIVEKIT_API_KEY=test LIVEKIT_API_SECRET=test python -c "from aria.voice_agent import server; print('Agent module loads OK')"`
Expected: `Agent module loads OK` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add backend/aria/voice_agent.py
git commit -m "refactor(aria): HTTP boundary, SIP telephony, turn detection, health server"
```

---

## Task 9: Telnyx Inbound Call Routing

**Files:**
- Modify: `backend/routes/telnyx_webhook_routes.py`

- [ ] **Step 1: Read the current webhook handler**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && grep -n "def handle_call_answered\|def handle_telnyx_webhook\|CALL_INITIATED\|call.initiated" routes/telnyx_webhook_routes.py`

Identify where to add inbound call routing — specifically after `CALL_INITIATED` or `CALL_ANSWERED` events.

- [ ] **Step 2: Add inbound routing function**

Add this function at the module level in `telnyx_webhook_routes.py` (before the webhook handler):

```python
async def _route_inbound_to_livekit(call_control_id: str, from_number: str, db: Session):
    """Route an inbound call to Aria via LiveKit SIP bridge."""
    import requests as http_requests

    # Look up caller in CRM
    from database.models.lead_loan import Lead
    from integrations.sms_service import _to_e164

    normalized = _to_e164(from_number) or from_number
    lead = db.query(Lead).filter(Lead.phone == normalized).first()
    if not lead:
        lead = db.query(Lead).filter(Lead.phone == from_number).first()

    # Routing decision
    route = "aria"  # Default: Aria handles it
    if lead and getattr(lead, "ai_score", 0) and lead.ai_score >= 80:
        from database.models.core import User
        if lead.owner_id:
            lo = db.query(User).filter(User.id == lead.owner_id, User.is_active == True).first()
            if lo and lo.phone:
                # Hot lead + LO available = consider direct transfer
                # For now, always route to Aria (direct_lo requires calendar check)
                pass

    if route == "aria":
        # Create LiveKit room and bridge the Telnyx call into it
        livekit_url = os.getenv("LIVEKIT_URL", "")
        livekit_key = os.getenv("LIVEKIT_API_KEY", "")
        livekit_secret = os.getenv("LIVEKIT_API_SECRET", "")

        if not all([livekit_url, livekit_key, livekit_secret]):
            logger.warning("LiveKit not configured — cannot route inbound call to Aria")
            return

        try:
            from livekit import api as lk_api
            import json as _json

            lk = lk_api.LiveKitAPI(livekit_url, livekit_key, livekit_secret)

            room_name = f"aria-inbound-{call_control_id[:12]}"
            metadata = _json.dumps({
                "trigger": "inbound_call",
                "from_number": from_number,
                "lead_id": lead.id if lead else None,
                "borrower_name": (getattr(lead, "first_name", "") or getattr(lead, "name", "")) if lead else "",
            })

            await lk.room.create_room(
                lk_api.CreateRoomRequest(name=room_name, metadata=metadata)
            )

            # Bridge Telnyx call into LiveKit room as SIP participant
            sip_trunk_id = os.getenv("TELNYX_SIP_TRUNK_ID", "")
            sip_domain = os.getenv("LIVEKIT_SIP_DOMAIN", "")

            if sip_trunk_id and sip_domain:
                # Use Telnyx Call Control to SIP REFER into LiveKit
                telnyx_key = os.getenv("TELNYX_API_KEY", "")
                http_requests.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transfer",
                    headers={
                        "Authorization": f"Bearer {telnyx_key}",
                        "Content-Type": "application/json",
                    },
                    json={"to": f"sip:{room_name}@{sip_domain}"},
                    timeout=10,
                )
                logger.info(f"Inbound call bridged to LiveKit room {room_name}")
            else:
                logger.warning("SIP trunk or domain not configured — cannot bridge call")
        except Exception as e:
            logger.error(f"Failed to route inbound call to LiveKit: {e}")
```

- [ ] **Step 3: Wire the routing into the webhook handler**

In the `handle_telnyx_webhook` function, find the event dispatch section. Add handling for `call.initiated` or `call.answered` events for inbound calls:

```python
    # After parsing the event type, add:
    if event_type_raw == "call.initiated":
        direction = payload.get("data", {}).get("payload", {}).get("direction", "")
        if direction == "incoming":
            from_number = payload.get("data", {}).get("payload", {}).get("from", "")
            call_ctrl_id = payload.get("data", {}).get("payload", {}).get("call_control_id", "")
            if from_number and call_ctrl_id:
                try:
                    await _route_inbound_to_livekit(call_ctrl_id, from_number, db)
                except Exception as e:
                    logger.error(f"Inbound routing failed: {e}")
            return Response(status_code=200)
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/telnyx_webhook_routes.py
git commit -m "feat(aria): add inbound call routing — Telnyx webhook → LiveKit SIP bridge"
```

---

## Task 10: Railway Deployment Configuration

**Files:**
- Create: `backend/aria/railway.toml` (or project-level config for the agent service)

- [ ] **Step 1: Create the railway.toml for the agent worker**

```toml
# backend/aria/railway.toml
# Configuration for the aria-agent-worker Railway service
[deploy]
startCommand = "python -m aria.voice_agent start"
healthcheckPath = "/"
healthcheckTimeout = 30
restartPolicyType = "always"
```

- [ ] **Step 2: Document the required environment variables**

Create or update a `.env.example` for the agent worker:

```bash
# backend/aria/.env.example
# LiveKit Cloud
LIVEKIT_URL=wss://aria-xxxx.livekit.cloud
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Backend connection (Railway internal URL)
INTERNAL_BACKEND_URL=http://perennia-api.railway.internal
INTERNAL_API_KEY=

# LLM
ANTHROPIC_API_KEY=

# STT
DEEPGRAM_API_KEY=

# TTS
CARTESIA_API_KEY=

# Voice
ARIA_CARTESIA_VOICE_ID=a0e99841-438c-4a64-b679-ae501e7d6091
ARIA_LLM_MODEL=claude-sonnet-4-20250514

# Telnyx SIP
TELNYX_SIP_TRUNK_ID=
LIVEKIT_SIP_DOMAIN=
```

- [ ] **Step 3: Commit**

```bash
git add backend/aria/railway.toml backend/aria/.env.example
git commit -m "feat(aria): add Railway deployment config and env template"
```

---

## Task 11: Integration Test — End-to-End Agent Startup

**Files:**
- Create: `backend/tests/integration/test_aria_agent_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# backend/tests/integration/test_aria_agent_integration.py
"""
Integration test — verifies the Aria agent module loads, the internal
API endpoints respond, and the circuit breaker client works end-to-end.
"""
import pytest
import os

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")


def test_aria_agent_module_loads():
    """Agent module imports without errors."""
    from aria.voice_agent import server, AriaVoiceAgent, _build_session
    assert server is not None


def test_aria_agent_creates_session():
    """Session builder returns session + agent."""
    from aria.voice_agent import _build_session
    session, agent = _build_session("lo_assistant")
    assert agent._mode == "lo_assistant"


def test_aria_agent_inbound_mode():
    from aria.voice_agent import _build_session
    session, agent = _build_session("inbound_receptionist", {
        "first_name": "Marcus",
        "lo_name": "Sarah",
    })
    assert agent._mode == "inbound_receptionist"
    assert "Marcus" not in agent._instructions  # name goes in prompt context, not raw


def test_config_imports():
    from agents.aria_config import (
        AUTONOMOUS_CALL_GUARDRAILS,
        OUTBOUND_CALL_CONFIG,
        VOICEMAIL_TEMPLATES,
        render_voicemail_template,
        get_amd_action,
        is_intent_autonomous_eligible,
    )
    assert len(VOICEMAIL_TEMPLATES) >= 4
    assert get_amd_action("human", 0.99) == "route_to_agent"


def test_backend_client_imports():
    from agents.aria_backend_client import (
        call_backend_tool,
        call_backend_tool_safe,
        BACKEND_TIMEOUT,
        GRACEFUL_FALLBACK,
    )
    assert BACKEND_TIMEOUT == 3.0
    assert len(GRACEFUL_FALLBACK) > 0


def test_prompts_all_modes():
    from agents.aria_prompts import get_prompt
    for mode in ["lo_assistant", "inbound_receptionist", "outbound_followup"]:
        prompt = get_prompt(mode)
        assert len(prompt) > 100, f"Prompt for {mode} seems too short"
        assert "Aria" in prompt


def test_internal_routes_registered():
    """Internal routes are accessible via TestClient."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    resp = client.post(
        "/internal/aria/lead-lookup",
        json={"phone": "+18435551234"},
        headers={"X-Internal-API-Key": "test-internal-key"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/integration/test_aria_agent_integration.py -v`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_aria_agent_integration.py
git commit -m "test(aria): add integration tests for agent module, config, routes"
```

---

## Task 12: Final Verification & Push

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_aria_config.py tests/test_aria_backend_client.py tests/test_call_authorization.py tests/test_aria_internal_routes.py tests/integration/test_aria_agent_integration.py -v`

Expected: all tests PASS

- [ ] **Step 2: Verify agent module loads cleanly**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from aria.voice_agent import server; print(f'Server: {server}'); from agents.aria_config import AUTONOMOUS_CALL_GUARDRAILS; print(f'Guardrails: {len(AUTONOMOUS_CALL_GUARDRAILS)} keys'); from agents.aria_backend_client import BACKEND_TIMEOUT; print(f'Timeout: {BACKEND_TIMEOUT}s')"`

Expected output:
```
Server: <AgentServer ...>
Guardrails: 9 keys
Timeout: 3.0s
```

- [ ] **Step 3: Verify no import cycles**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "import routes.internal.aria_tool_routes; import routes.internal.aria_call_routes; import routes.internal.aria_workflow_routes; print('All internal routes import OK')"`

Expected: `All internal routes import OK`

- [ ] **Step 4: Push to production**

```bash
git push origin main
```

Railway auto-deploys from main. The existing `perennia-api` service picks up the new internal routes. The `aria-agent-worker` service needs to be created separately in Railway.

---

## Post-Implementation: Railway Service Setup (Manual)

These steps are done in the Railway dashboard, not in code:

1. **Create new service** in the Railway project: `aria-agent-worker`
2. **Set root directory** to `backend/aria/` (or configure start command)
3. **Set environment variables** per `.env.example`
4. **Generate INTERNAL_API_KEY** — same value on both agent worker and perennia-api service
5. **Configure SIP trunk** in LiveKit Cloud dashboard pointing to Telnyx
6. **Update Telnyx** inbound call webhook URL to point to `/api/v1/telnyx/webhook`
