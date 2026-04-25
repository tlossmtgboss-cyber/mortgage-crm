# Perennia Security Audit — Voice Agent (Aria)

**Date:** 2026-04-19
**Scope:** `backend/aria/*`, `backend/routes/telnyx_webhook_routes.py`, `backend/routes/internal/aria_*`
**Commit:** `c11fd42b`
**Auditor:** perennia-security-audit skill (manual deep-dive)

---

## Executive Summary

The Aria voice agent has a well-structured architecture — the agent worker is isolated from the database, all CRM access goes through authenticated HTTP endpoints, and the backend internal routes use `hmac.compare_digest` for constant-time key verification. The Telnyx webhook verification uses Ed25519 with replay protection.

However, **16 findings** were identified, including **1 Critical** and **6 High** severity issues. The most urgent is a hardcoded API key in source code that turns an internal endpoint into a phishing email relay. The AI agent security findings center on missing tenant isolation in tool calls and unmitigated prompt injection via voice transcription.

| Severity | Count |
|----------|-------|
| Critical | 1 |
| High | 6 |
| Medium | 6 |
| Low | 2 |
| Info | 1 |

---

## Critical Findings

### SEC-001: Hardcoded INTERNAL_API_KEY in send-appointment-invite endpoint
**File:** `telnyx_webhook_routes.py:1901` | **CWE-798** | **OWASP A07:2021**

The `/api/v1/telnyx/send-appointment-invite` endpoint has a **64-character hex API key hardcoded as a default value**:

```python
expected = os.environ.get(
    "INTERNAL_API_KEY",
    "068ef1be6beeb7fd1efbf4f4b928afda34ba9725d61521c2a27debcb5f6dfb1d",  # ← IN SOURCE CODE
)
```

This key is now in git history. Anyone who reads this file can call the endpoint and send calendar invite emails to **any email address**, impersonating "Aria — Perennia AI". The endpoint also has an SMTP fallback that sends directly via Gmail.

**Impact:** Open email relay for phishing. Spoofed calendar invites from a legitimate-looking sender.

**Fix:**
1. Remove the hardcoded fallback immediately
2. Rotate `INTERNAL_API_KEY` in Railway
3. Fail-closed: `os.environ.get("INTERNAL_API_KEY", "")` + reject if empty

---

## High Findings

### SEC-002: Timing-vulnerable API key comparison
**File:** `telnyx_webhook_routes.py:61, 1903` | **CWE-208**

Two endpoints use `==` / `!=` for API key comparison instead of `hmac.compare_digest()`. The internal Aria routes (`aria_tool_routes.py`, `aria_call_routes.py`) correctly use constant-time comparison — this is an inconsistency.

**Fix:** Replace `api_key != expected` with `hmac.compare_digest(api_key, expected)` in both `_validate_texml_request` and `send-appointment-invite`.

### SEC-003: Hardcoded LiveKit SIP Trunk ID
**File:** `telnyx_webhook_routes.py:87` | **CWE-798**

The LiveKit SIP outbound trunk ID `ST_nif29TasyWjm` is hardcoded as a default. Should be environment-only.

### SEC-004: No tenant isolation on voice agent tool calls
**File:** `voice_agent.py:127` | **CWE-284** | **LLM07**

All 21 `@function_tool` methods call the backend via `/internal/aria/tool/execute` but **never pass `organization_id`**. The `organization_id` exists in `_session_data` (from room metadata) but is never included in any tool payload. If the backend doesn't independently enforce tenant scoping, data leaks across orgs.

**Fix:** Include `organization_id` from `self._session_data` in every `call_backend_tool_safe` payload.

### SEC-005: Voice transcript is an unmitigated prompt injection surface
**File:** `voice_agent.py:77` | **CWE-77** | **LLM01**

Deepgram STT output feeds directly to Claude with no sanitization. A caller speaking injection payloads has them transcribed and delivered to the LLM. The agent has **write tools**: `send_sms`, `create_lead`, `create_task`, `generate_pre_approval_letter`. There is no injection detection layer.

**Impact:** A malicious caller could instruct the AI to send SMS to arbitrary numbers, create fake leads, or generate fraudulent pre-approval letters.

### SEC-006: send_sms allows arbitrary phone numbers
**File:** `voice_agent.py:175` | **CWE-284** | **LLM08**

The `send_sms` tool accepts any `phone_number` with no restriction. Combined with prompt injection, a caller could instruct Aria to spam arbitrary numbers.

**Fix:** In `inbound_receptionist` mode, restrict to `self._session_data['from_number']`.

### SEC-007: Pre-approval letter generation available to inbound callers
**File:** `voice_agent.py:324` | **CWE-284** | **LLM08**

`generate_pre_approval_letter` is available in all modes including `inbound_receptionist`. An unknown caller could potentially social-engineer the AI into generating a pre-approval letter. Pre-approval letters are legal documents — unauthorized generation is mortgage fraud.

**Fix:** Restrict to `lo_assistant` mode only.

---

## Medium Findings

### SEC-008: No max_tokens on LLM calls
No explicit token cap on `AnthropicLLM`. Cost amplification risk.

### SEC-009: No audit trail for tool invocations
Tool calls tracked in-memory only — lost when call ends. SOC 2 and TILA/RESPA audit gap.

### SEC-010: PII in plaintext logs
Caller first/last name logged at WARNING level. Should log lead_id only.

### SEC-011: Email endpoint lacks rate limiting
`/send-appointment-invite` accepts unlimited email recipients with no rate limit.

### SEC-012: Predictable room names (MD5)
Room names use `md5(phone-time)[:8]` — only 32 bits of entropy. Use `secrets.token_hex(8)`.

### SEC-013: System prompt leaks tool surface area
LO_ASSISTANT_PROMPT enumerates every capability. Aids targeted prompt injection.

---

## Low Findings

### SEC-014: run_crm_tool allows LLM-directed tool dispatch
Allowlist-gated but enables read-only data exfiltration via prompt injection.

### SEC-015: Hardcoded phone number and messaging profile
Infrastructure identifiers should be env-only.

---

## Info

### SEC-016: No session timeout
No max call duration enforced. Resource exhaustion risk.

---

## What's Working Well

- **Architecture isolation**: Agent worker never imports from `db`, `database.models`, or `services` — all access via HTTP
- **Backend internal routes**: Use `hmac.compare_digest` and Pydantic schema validation
- **Webhook verification**: Telnyx Ed25519 signature verification with replay protection and env-dependent fail-closed
- **Tool allowlist**: `_CRM_TOOL_ALLOWLIST` restricts the generic `run_crm_tool` to read-only operations
- **No .env files in git**: Clean git index
- **No eval/exec/pickle/subprocess**: No command injection or deserialization surfaces
- **No TLS bypass**: No `verify=False` anywhere in voice agent code
- **Graceful degradation**: Circuit-breaker pattern with human-friendly fallback messages

---

## Remediation Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| **P0 — Today** | SEC-001: Remove hardcoded API key | <1h | Closes open email relay |
| **P0 — Today** | SEC-002: Fix timing comparison | <1h | Closes side-channel |
| **P1 — This week** | SEC-004: Add org_id to tool calls | 1-4h | Tenant isolation |
| **P1 — This week** | SEC-007: Restrict pre-approval to LO mode | 1-4h | Compliance |
| **P1 — This week** | SEC-006: Restrict send_sms phone numbers | 1-4h | Abuse prevention |
| **P2 — Next sprint** | SEC-005: Prompt injection mitigation | 4-8h | Defense in depth |
| **P2 — Next sprint** | SEC-009: Audit trail for tool calls | 4-8h | SOC 2 / compliance |
| **P2 — Next sprint** | SEC-011: Rate limit email endpoint | 1-4h | Abuse prevention |
| **P3 — Backlog** | SEC-003, 008, 010, 012, 013, 014, 015, 016 | Various | Hardening |
