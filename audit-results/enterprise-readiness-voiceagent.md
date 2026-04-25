# Aria Voice Agent — Enterprise Readiness Report

**Generated:** 2026-04-19
**Mode:** targeted (voiceagent)
**Scope:** Aria LiveKit voice agent system (7 applicable domains)
**Overall Grade:** F (34/100)

---

## Executive Summary

21 of 55 applicable checks passed across 7 domains.
**14 critical failures** require immediate remediation before any enterprise deployment of voice capabilities.

The Aria voice agent has strong **security fundamentals** (timing-safe auth, prompt injection defense, tool allowlisting, session timeout) but is **not enterprise-ready** due to systemic gaps in multi-tenant isolation, TCPA compliance, and white-label support. The most dangerous finding: **organization_id is optional throughout the entire voice agent stack** — tools can execute cross-tenant if metadata is missing.

---

## Domain Scores

| Domain | Score | Grade | Critical Failures | Applicable Checks |
|--------|-------|-------|-------------------|--------------------|
| 1. Multi-Tenant Isolation | 18 | **F** | 6 | 8 |
| 2. Compliance & Regulatory | 15 | **F** | 4 | 10 |
| 4. Security Audit | 49 | **F** | 1 | 12 |
| 5. Onboarding & Provisioning | 30 | **F** | 0 | 5 |
| 6. Performance & Load Testing | 82 | **B** | 0 | 6 |
| 7. Integration Health | 55 | **F** | 0 | 6 |
| 8. Disaster Recovery | 28 | **F** | 0 | 5 |
| 12. White-Label & Theming | 20 | **F** | 0 | 4 |

*Domains 3, 9, 10, 11 not applicable to voice agent scope.*

---

## Critical Failures (Immediate Action Required)

### 1.1 — Organization_ID Optional in Tool Execution
- **Severity:** CRITICAL
- **File:** `backend/routes/internal/aria_tool_routes.py:44`
- **Expected:** `organization_id` required on all tool execution requests
- **Actual:** `organization_id: Optional[int] = None` — tools execute without tenant filtering when omitted
- **Impact:** Any voice agent session without org_id in room metadata can read/write data across all tenants
- **Remediation:** Make `organization_id` required in `ToolExecuteRequest`. Return 400 if missing.

### 1.2 — WebRTC/LO Assistant Mode Never Populates org_id
- **Severity:** CRITICAL
- **File:** `backend/aria/voice_agent.py:686-688`
- **Expected:** LO assistant context includes authenticated user's org_id
- **Actual:** `context = {}` — empty dict, no org_id injected
- **Impact:** Every LO assistant voice session runs tools without tenant scope
- **Remediation:** Extract org_id from WebRTC auth token or room metadata for all modes.

### 1.3 — Internal API Routes Filter org_id Only If Provided
- **Severity:** CRITICAL
- **File:** `backend/routes/internal/aria_tool_routes.py:74-75, 118-119, 145-151`
- **Expected:** Queries always filter by org_id
- **Actual:** `if req.organization_id: q = q.filter(...)` — conditional filter
- **Remediation:** Remove conditional. Always require and apply org_id filter.

### 1.4 — Outbound Call/Voicemail Routes Missing org_id Entirely
- **Severity:** CRITICAL
- **File:** `backend/routes/internal/aria_call_routes.py:40-66`
- **Expected:** `InitiateOutboundRequest` and `VoicemailDropRequest` include org_id
- **Actual:** No `organization_id` field in request schemas
- **Remediation:** Add required `organization_id` to both request models.

### 1.5 — New Callers Have No org_id in Room Metadata
- **Severity:** CRITICAL
- **File:** `backend/routes/telnyx_webhook_routes.py:191-200`
- **Expected:** Room metadata always includes org_id
- **Actual:** `organization_id` only set when `caller_info` exists (known lead). New callers → `None`
- **Remediation:** Derive org_id from the Telnyx phone number → org mapping, not from the caller's lead record.

### 1.6 — Tool Registry Strips org_id from Params
- **Severity:** CRITICAL
- **File:** `backend/routes/internal/aria_tool_routes.py:203-205`
- **Expected:** org_id propagated to tool function
- **Actual:** `safe_params` filters by function signature. Tools without `organization_id` param never receive it.
- **Remediation:** Inject org_id into tool execution context, not via params dict.

### 2.1 — No Consent Verification Before Outbound Voice Calls
- **Severity:** CRITICAL (TCPA)
- **File:** `backend/aria/voice_agent.py:674-685`
- **Expected:** `check_call_consent()` called before initiating outbound call
- **Actual:** Outbound call trigger routes directly to agent without consent check. `telephony/compliance.py` has the function but it's not invoked.
- **Remediation:** Add `check_call_consent()` gate in outbound call initiation flow.

### 2.2 — No DNC List Check Before Outbound Calls
- **Severity:** CRITICAL (TCPA)
- **File:** `backend/aria/voice_agent.py:674-685`
- **Expected:** DNC scrub before every outbound dial
- **Actual:** No DNC check anywhere in the voice agent outbound path
- **Remediation:** Call `check_dnc()` from `compliance.py` before outbound call setup.

### 2.3 — FTC AI Disclosure Missing on Outbound Calls
- **Severity:** CRITICAL (FTC Telemarketing Sales Rule, Jan 2025)
- **File:** `backend/aria/agents/aria_prompts.py:71, 19`
- **Expected:** Outbound AI calls clearly identify as AI-generated
- **Actual:** Outbound prompt says "this is Aria calling from {company_name}" — no AI disclosure. Inbound prompt explicitly says "NEVER say 'as an AI'" (line 19).
- **Remediation:** Add FTC-compliant AI disclosure to outbound prompt preamble. Keep inbound disclosure rules separate.

### 2.4 — No Recording Consent Disclosure
- **Severity:** CRITICAL (two-party consent states: CA, IL, PA, FL, etc.)
- **File:** `backend/aria/agents/aria_prompts.py`
- **Expected:** "This call may be recorded" disclosure at start of call
- **Actual:** No recording disclosure in any prompt mode
- **Remediation:** Add recording disclosure to on_enter greeting for all modes. Make configurable per state.

### 4.1 — Call Transcripts Stored in Plaintext
- **Severity:** CRITICAL (GLBA/SOC 2)
- **File:** `backend/routes/internal/aria_call_routes.py:163`
- **Expected:** Transcripts encrypted at rest (EncryptedString or equivalent)
- **Actual:** `transcript` column stored as plaintext in `VoiceCallSession` table
- **Remediation:** Use EncryptedString column type or application-level encryption for transcript field.

---

## All Results by Domain

### Domain 1: Multi-Tenant Isolation (18/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 1.1 | org_id required in tool requests | CRITICAL | **FAIL** | `Optional[int] = None` in schema |
| 1.2 | LO assistant mode provides org_id | CRITICAL | **FAIL** | `context = {}` on WebRTC path |
| 1.3 | Internal routes require org_id filter | CRITICAL | **FAIL** | Conditional `if req.organization_id` |
| 1.4 | Outbound/voicemail routes have org_id | CRITICAL | **FAIL** | Field missing from request schemas |
| 1.5 | New callers get org_id from phone mapping | CRITICAL | **FAIL** | org_id None for unknown callers |
| 1.6 | Tool registry propagates org_id | CRITICAL | **FAIL** | safe_params strips unknown params |
| 1.7 | Room names don't collide across orgs | MEDIUM | PASS | Random hex suffix |
| 1.8 | System prompts don't leak tenant data | CRITICAL | PASS | Static templates, context-injected |

### Domain 2: Compliance & Regulatory (15/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 2.11 | Consent before outbound calls | CRITICAL | **FAIL** | check_call_consent() not invoked |
| 2.12 | DNC list check | CRITICAL | **FAIL** | check_dnc() not invoked |
| 2.13 | Calling hours enforcement | HIGH | **FAIL** | check_calling_hours() not invoked |
| 2.14 | Opt-out processing | HIGH | **FAIL** | Prompt instruction only, no code |
| — | FTC AI disclosure (outbound) | CRITICAL | **FAIL** | No AI identification in prompt |
| — | Recording consent disclosure | CRITICAL | **FAIL** | No disclosure in any mode |
| — | TCPA warm-up message | MEDIUM | **FAIL** | No pre-message on outbound |
| 3.18 | PII not in prompts/logs | HIGH | PASS | No SSN/DOB found |
| 3.19 | Phone numbers masked in logs | HIGH | PASS | `...[-4:]` masking pattern |
| 3.20 | Recording encryption | HIGH | UNKNOWN | Handled by LiveKit/Telnyx upstream |

### Domain 4: Security Audit (49/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 4.1 | Internal API key verification | CRITICAL | PASS | hmac.compare_digest() on all routes |
| 4.7 | RBAC / mode-based restrictions | HIGH | PASS | Pre-approval locked to LO, SMS guarded |
| 4.20 | No hardcoded secrets | CRITICAL | PASS | All credentials from env vars |
| 4.12 | SQL injection prevention | HIGH | PASS | ORM parameterized queries |
| — | Prompt injection defense | HIGH | PASS | INJECTION_DEFENSE in system prompt |
| — | Tool parameter validation | HIGH | PASS | _CRM_TOOL_ALLOWLIST frozenset |
| 4.17 | HTTPS for backend calls | HIGH | PASS | httpx client, env-configured URL |
| — | Session timeout | HIGH | PASS | 30-min hard limit, asyncio enforce |
| — | Audit trail for tool calls | HIGH | PASS | tools_executed + on_exit POST |
| 4.19 | Transcript encryption at rest | CRITICAL | **FAIL** | Plaintext VoiceCallSession.transcript |
| — | Rate limiting on tool endpoints | HIGH | **FAIL** | No limits on /internal/aria/* |
| — | Error message sanitization | HIGH | **FAIL** | Raw exception strings reach TTS |

### Domain 5: Onboarding & Provisioning (30/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 5.7 | Per-org voice config | HIGH | **FAIL** | Global CARTESIA_VOICE_ID env var |
| 5.8 | Per-org tool enablement | HIGH | **FAIL** | Static _CRM_TOOL_ALLOWLIST |
| — | Per-org prompt customization | HIGH | **FAIL** | Hardcoded "Perennia AI" default |
| — | Admin API for voice settings | HIGH | **FAIL** | No configuration endpoints exist |
| — | Per-org greeting customization | MEDIUM | **FAIL** | Hardcoded greetings in on_enter |

### Domain 6: Performance & Load Testing (82/100 — B)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 6.12 | Agent response latency config | HIGH | PASS | claude-sonnet + max_tokens=256 |
| 6.13 | Token budget per turn | HIGH | PASS | max_tokens=256 enforced |
| 6.14 | Concurrent session support | HIGH | PASS | Stateless AgentServer |
| — | STT/TTS telephony optimization | MEDIUM | PASS | endpointing_ms=25, dynamic mode |
| — | Session timeout (resource exhaustion) | HIGH | PASS | MAX_SESSION_SECONDS = 1800 |
| — | Backend connection pooling | MEDIUM | **FAIL** | New AsyncClient per request |

### Domain 7: Integration Health (55/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 7.14 | Call flow traceability | HIGH | PASS | Complete webhook → room → agent chain |
| — | Graceful degradation (CRM down) | HIGH | PASS | spoken_fallback in backend client |
| — | LiveKit credentials via env | HIGH | PASS | All from os.getenv |
| — | Retry logic for backend calls | HIGH | PARTIAL | 2 retries, no circuit breaker |
| — | SIP trunk ID validation | HIGH | **FAIL** | No check before use |
| — | Health check endpoint | HIGH | **FAIL** | No /health for agent worker |

### Domain 8: Disaster Recovery (28/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| — | CRM backend unreachable | HIGH | PASS | Graceful fallback message |
| — | Mid-call restart recovery | HIGH | **FAIL** | All state in-memory, lost on crash |
| 8.7 | Claude API failure handling | HIGH | **FAIL** | No fallback model or degradation |
| 8.8 | Telnyx failure handling | HIGH | **FAIL** | No retry on callback failure |
| — | Health check for monitoring | HIGH | **FAIL** | No endpoint exposed |

### Domain 12: White-Label & Theming (20/100 — F)

| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 12.5 | "Perennia" not in voice output | HIGH | **FAIL** | Hardcoded in prompts + greetings |
| 12.6 | Caller ID per tenant | HIGH | PARTIAL | Single global phone number |
| 12.7 | Voice personality per org | HIGH | **FAIL** | Global Cartesia voice ID |
| — | Company name from org config | HIGH | **FAIL** | Default "Perennia AI" in _defaults() |

---

## Remediation Plan

| Priority | Check | Domain | Issue | Effort | Owner |
|----------|-------|--------|-------|--------|-------|
| **P0** | 1.1-1.6 | Tenant Isolation | org_id optional throughout stack | 3-5 days | backend |
| **P0** | 2.11-2.12 | Compliance | No TCPA consent/DNC gates on outbound | 2-3 days | backend |
| **P0** | 2.3 | Compliance | FTC AI disclosure missing | 1 day | backend |
| **P0** | 2.4 | Compliance | No recording consent disclosure | 1 day | backend |
| **P0** | 4.19 | Security | Plaintext transcript storage | 1-2 days | backend |
| **P1** | 2.13-2.14 | Compliance | Calling hours + opt-out | 2-3 days | backend |
| **P1** | 4.x | Security | Rate limiting on tool endpoints | 1-2 days | backend |
| **P1** | 4.x | Security | Error message sanitization before TTS | 1 day | backend |
| **P1** | 7.x | Integration | Health check endpoint + circuit breaker | 1-2 days | backend |
| **P2** | 8.x | DR | LLM fallback + session persistence | 3-5 days | backend |
| **P2** | 5.x | Onboarding | Per-org voice/prompt/tool config | 5-8 days | backend |
| **P3** | 12.x | White-Label | Tenant-scoped branding layer | 3-5 days | backend + frontend |
| **P3** | 6.x | Performance | AsyncClient connection pooling | 0.5 day | backend |

---

## Blocking Path to Enterprise

```
CURRENT STATE                    MINIMUM VIABLE ENTERPRISE
─────────────                    ─────────────────────────
org_id optional ──────────────── org_id REQUIRED everywhere        [P0, 3-5 days]
No TCPA gates ────────────────── consent + DNC + hours enforced    [P0, 2-3 days]
No AI disclosure ─────────────── FTC-compliant outbound preamble   [P0, 1 day]
No recording consent ──────────── "This call may be recorded"       [P0, 1 day]
Plaintext transcripts ─────────── Encrypted at rest                 [P0, 1-2 days]
                                                          TOTAL:    8-12 days P0 work
```

**After P0 remediation**, the voice agent would score approximately:
- Domain 1: ~75 (C) — org_id enforced, pending live verification
- Domain 2: ~65 (D) — TCPA gates in place, calling hours + opt-out still needed
- Domain 4: ~82 (B) — encryption + rate limiting addressed
- Overall: ~55 → still F until P1 items close

**After P0 + P1 remediation** (~3-4 additional days): Overall ~68, Grade D — conditional readiness with documented gaps in onboarding/white-label/DR.

**Full enterprise readiness** requires P0-P2 (~20-25 days total effort).
