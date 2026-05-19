# Perennia AI — Master Platform Health Report

**Date:** 2026-05-19
**Mode:** Full (6 domains, 16 unique skills, 19 registered names)
**Platform Score:** **61.6 / 100**
**Grade:** **D**
**Certification:** **BLOCKED** — 3 domains scored F (Engineering, Agents, Portal/Security)

---

## Executive Summary

Perennia AI presents a paradox: enterprise-grade *paperwork* (multi-tenant isolation, compliance models, load test harness, SOC 2 scaffolding) sits atop a *code base in distress* (10,089 bare exceptions, 146 duplicate `get_current_user` definitions, Float-typed financial columns, sub-1% golden test coverage, 6,652-line seed scripts). The platform's enterprise-readiness paperwork scores an A, but two of three engineering- and security-facing domains fail outright. The result is a system that demos well and audits poorly — production deployment without remediation carries serious TCPA, TRID, and SOC 2 exposure.

Bottom line: the platform has the *blueprint* of a Tier-1 enterprise system. The *implementation* needs roughly one quarter of focused remediation before any enterprise-tier customer contract should be signed.

---

## Domain Scorecard

| # | Domain | Score | Grade | Weight | Weighted | Status |
|---|--------|-------|-------|--------|----------|--------|
| 1 | Platform & Enterprise Readiness | 92.9 | A | 25% | 23.23 | pass |
| 2 | Engineering Quality | 26.8 | F | 20% | 5.36 | **fail** |
| 3 | AI Agent Fleet | 55.0 | F | 20% | 11.00 | **fail** |
| 4 | Call Intelligence & Telephony | 68.0 | D | 15% | 10.20 | warn |
| 5 | Workflow & Data Integrity | 70.0 | C | 10% | 7.00 | pass |
| 6 | Portal, Security & Content | 48.0 | F | 10% | 4.80 | **fail** |
| | **PLATFORM TOTAL** | | **D** | 100% | **61.6** | **BLOCKED** |

**Certification rule applied:** Three domains scored F (≥ one F → certification blocked). Even before the D-cap rule fires, F-block precludes certification.

---

## Critical Failures (Certification Blockers)

Findings rated *critical* by their domain agents. Each one blocks enterprise certification on its own.

| # | Domain | Critical Failure | Regulatory Exposure |
|---|--------|------------------|---------------------|
| 1 | D2 Engineering | 146 duplicate `get_current_user` implementations across backend; single security patch cannot be applied uniformly | SOC 2 CC6.1 |
| 2 | D2 Engineering | `get_current_user_flexible` bypasses `_USE_SECURE_TOKENS` flag — HS256 admin impersonation path | SOC 2 CC6.1, fraud |
| 3 | D2 Engineering | `Float` SQLAlchemy columns store loan_amount, interest_rate, property_value (IEEE 754 rounding violates TRID tolerance math) | **TRID** |
| 4 | D2 Engineering | 10,089 bare `except Exception:` blocks silently swallow errors across 206+ files | Operational |
| 5 | D2 Engineering | <1% golden-path test coverage (~407 tests vs. 2,565 source files) — no CI gate enforcing critical-flow regression | Quality |
| 6 | D4 Telephony | Telnyx API key known-invalid since Feb 2026 — primary SMS/voice provider | Outage |
| 7 | D4 Telephony | BorrowerProfile `consent_revoked_at` not enforced on voicemail drops — revoked contacts still callable | **TCPA** |
| 8 | D4 Telephony | Slybroadcast webhook handler missing — delivery status never reconciled; no retry on failure | Operational |
| 9 | D4 Telephony | Audio duration not validated before Slybroadcast submission (>5 s required) | Silent failure |
| 10 | D5 Workflow | No persistent `loan_state_change_audit` table — state transitions logged only in-memory | **SOC 2**, regulator |
| 11 | D6 Portal | `/purl-admin/*` endpoints not verified to require admin JWT — privilege-escalation risk | Auth |
| 12 | D6 Portal | OWASP security headers missing (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) | XSS, clickjacking |
| 13 | D6 Portal | PURL token generation untestable in CI (missing test credentials) — borrower-portal auth has no regression coverage | Auth |

---

## Top 10 Priority Remediations

| # | Domain | Issue | Severity | Effort | Impact |
|---|--------|-------|----------|--------|--------|
| 1 | D2 | Consolidate 146 `get_current_user` copies into `backend/auth/dependencies.py`; fix flexible-auth bypass; add pre-commit guard | Critical | 1 wk | Closes auth blast radius |
| 2 | D2 | Migrate `Float` → `Numeric(12,2)` / `Numeric(8,5)` on all financial columns; Alembic + backfill | Critical | 1 wk | TRID-safe math |
| 3 | D5/D2 | Add `loan_state_change_audit` table with immutable insert-only writes; persist every reconciliation result | Critical | 3 d | SOC 2 audit trail |
| 4 | D6 | Add OWASP security-header middleware (CSP, XFO, XCTO, RP, PP) + verify admin-route auth gates | Critical | 2 d | Closes XSS / privilege gaps |
| 5 | D4 | Rotate Telnyx API key; validate via probe in startup health check; add Slybroadcast webhook + audio-duration validator + consent-revocation block | Critical | 3 d | Restores telephony + TCPA hygiene |
| 6 | D2 | Replace 10K bare `except` with `except SpecificError: logger.exception(...); raise`; enforce `ruff E722` in pre-commit | High | 3 d | Restores observability |
| 7 | D2 | Stand up minimum golden test suite (auth, lead CRUD, loan state, portal login, pipeline load); CI gate at 85% | High | 1 wk | Regression net |
| 8 | D3 | Split `agents/service.py` (3,267 lines) into `session_manager` / `context_injector` / `tool_executor`; add per-agent token-budget enforcement | High | 2 wk | Cost control + maintainability |
| 9 | D5 | Register explicit midnight workflow-generation cron in `main.py`; validate Important-Dates field presence before generation | High | 2 d | Closes silent SLA gap |
| 10 | D1 | Execute documented DR drill end-to-end (PITR restore + cross-region failover); publish RTO/RPO benchmark results | Medium | 1 wk | Validates DRP paperwork |

---

## Domain Detail

### Domain 1 — Platform & Enterprise Readiness — 92.9 / A

- **enterprise-readiness (65% weight): 86/100.** All 12 enterprise sub-domains score B or better. RLS on 54+ tables; SAML 2.0 + SCIM 2.0; HMDA LAR export per CFPB spec; TRID auto-calculation; WAL archiving + PITR; circuit breaker + dead-letter queue; per-tenant rate limits; load-test harness at 1,819 lines.
- **u-multi-tenant-challenge (35% weight): 100/100.** Documented audit report (`multi_tenant_readiness_report.md`) shows 87/87 checks passing across 8 SaaS-readiness domains.
- **Gaps:** DR plan exists but no executed restore drill; load-test SLA benchmarks not published; API gateway SDKs not shipped.
- **Critical failures:** none.

### Domain 2 — Engineering Quality — 26.8 / F

- **engineering-discipline-challenge (60%): 24/100.** Hits every one of the 7 failure pillars: 146 auth duplicates; flexible-auth bypass; Float financial columns across 4 model files; 10,089 bare excepts in 206+ files; oversized modules (`seed_full_demo.py` 6,652 lines, `salesforce/sync_service.py` 4,242, `inline_legacy_routes.py` 3,415, `PurchaseApplication.js` 5,881); `pool_size=3 / max_overflow=5` against async route handlers.
- **code-evaluator (40%): 31/100.** 16 % test-to-source ratio; mypy not enforced; no consistent error-envelope shape; no `selectinload` discipline in high-traffic routes; 6,556 stray `print()` statements.
- **Critical failures:** 4 (auth duplication, token bypass, Float money, test vacuum).

### Domain 3 — AI Agent Fleet — 55 / F

- **u_agent_challenge (25%): 62.** Challenge framework + scoring rubric exist; no CI integration, no regression baselines.
- **u_agent_audit (25%): 55.** Per-agent prompt analysis missing; hallucination verifier present but not wired into audit.
- **u_agent_fleet (20%): 58.** Real architecture is 10 consolidated agents (60-role backward-compat map), not the 22 advertised; tool redundancy detection absent; no caching strategy.
- **agent_optimization_framework (15%): 48.** Documented but token-budget enforcement, model routing, and prompt compression mostly absent.
- **u-gap-analysis (15%): 52.** 13 modules across 4 phases identified; no module→agent mapping in code.
- **Strengths:** prompts externalized (`SYSTEM_PROMPTS.md` + `prompt_loader.py`); dynamic tool loader scopes 8–16 tools per intent (≈90 % context reduction); hallucination_verifier.py exists (638 lines).
- **Critical issues:** monolithic `agents/service.py` (3,267 lines); no per-agent cost governance; TRID/RESPA rules in challenge suite are not enforced at the agent prompt boundary; intent router has no confidence threshold or fallback.

### Domain 4 — Call Intelligence & Telephony — 68 / D

Single skill, 11 sub-domains, ≈100 checks.

- **Power dialer:** PASS (10/10 — strong: DialerSession + AgentTelephonySettings + VerifiedCallerId + ComplianceChecker.check_dnc).
- **Live call whisper, SMS Intelligence, Call compliance/TCPA:** PASS / PASS / PASS.
- **AI receptionist, voicemail drops, transcription/scribe, recording/retention, routing/queuing:** PARTIAL — features wired but observability and edge-case handling weak.
- **Telephony provider creds:** TEL-003 Telnyx key invalid since Feb 2026; TEL-006 Slybroadcast creds hardcoded.
- **7 BLOCKERS** as enumerated above (Telnyx key, consent revocation, audio duration, Slybroadcast webhook, 1003 intake, SMS opt-out persistence, WebSocket session cleanup).

### Domain 5 — Workflow & Data Integrity — 70 / C

- **u-workflow-challenge (53.3% renormalized): 72.** SLA models (`SLAMeasure`, `LoanMilestoneHistory`, `SLAAlert`, `SLAPerformanceSnapshot`) present; business-hours calculator correct; task→destination routing implemented. Gaps: "Important Dates" consolidated record not found on profile models; `days_elapsed` source ambiguous; no explicit cron-job registration in `main.py`.
- **loan-state-reconciliation (46.7% renormalized): 68.** State machine + STAGE_ORDER + Salesforce inbound sync + SOQL injection guard all present. **Critical gap: no durable state-change audit table** — transitions log only to in-memory `ReconciliationResult`. SUSPENDED-resume logic, Lead→MUM gate, and DOES_NOT_QUALIFY disposition handling are advisory rather than enforced.
- **crm-workflow-audit:** *Not available in this environment*; weight redistributed.

### Domain 6 — Portal, Security & Content — 48 / F

- **portal-skill-challenge (40% weight, treated as 100% with substitutes): 42.** Portal infrastructure resolves and SSL is valid; **4 critical / 2 high failures** — PURL admin endpoints not protected, OWASP security headers absent (1 of 6 present), PURL token generation untestable, multi-tenant isolation (UA-011) untested due to missing credentials.
- **u-challenge (30%):** *Not installed.* Static substitute from prior `u-challenge-report.html`: 55/100. Platform B- (Late Beta / Early Production — overextended). SOC 2 Type II not certified; Encompass sync incomplete.
- **hallucination-detector (30%):** *Not installed.* Static substitute: 48/100. No grounding/citation patterns in system prompts; no RAG-with-sources discipline; no automated output validation; agents instructed to be "direct, no disclaimers."

---

## Skill Inventory

| # | Skill | Domain | Location | Score | Status |
|---|-------|--------|----------|-------|--------|
| 1 | enterprise-readiness | Platform | .claude/commands/ | 86 | run |
| 2 | u-multi-tenant-challenge | Platform | .claude/commands/ | 100 | run |
| 3 | engineering-discipline-challenge | Engineering | .claude/commands/ | 24 | run |
| 4 | code-evaluator | Engineering | .claude/commands/ | 31 | run |
| 5 | u_agent_challenge | Agents | .claude/commands/ | 62 | run |
| 6 | u_agent_audit | Agents | .claude/commands/ | 55 | run |
| 7 | u_agent_fleet | Agents | .claude/commands/ | 58 | run |
| 8 | agent_optimization_framework | Agents | .claude/commands/ | 48 | run |
| 9 | u-gap-analysis | Agents | .claude/commands/ | 52 | run |
| 10 | call-intelligence-challenge | Telephony | .claude/commands/ | 68 | run |
| 11 | u-workflow-challenge | Workflow | .claude/commands/ | 72 | run |
| 12 | loan-state-reconciliation | Workflow | .claude/commands/ | 68 | run |
| 13 | crm-workflow-audit | Workflow | ~/.claude/skills/ | — | **not installed** (weight redistributed) |
| 14 | portal-skill-challenge | Portal | .claude/commands/ | 42 | run |
| 15 | u-challenge | Portal | ~/.claude/skills/ | 55 | **not installed** (static substitute) |
| 16 | hallucination-detector | Portal | ~/.claude/skills/ | 48 | **not installed** (static substitute) |

**Execution coverage:** 13 of 16 unique skills executed natively; 3 substituted via static analysis. Partial-execution caveat applies to Domains 5 and 6 — true scores could shift ±5 once the missing skills are installed.

---

## Recommendation

Do **not** ship a v1 enterprise contract on this codebase as-is. Run the 10-item remediation plan above (estimated 6–8 weeks of one senior engineer plus one platform engineer). Re-run `/u-master-challenge` after each remediation block; target Platform Score ≥ 80 (B) with no domain below 70 before pursuing first paid enterprise pilot or SOC 2 Type II readiness audit.
