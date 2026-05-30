# Aria Unified Brain — Design (Approach A) — v2

**Date:** 2026-05-30
**Status:** v2 — dev-team review folded in; approved for planning
**Scope:** The whole Aria brain — voice + chat transport, orchestration, the agent/tool layer, memory, and knowledge retrieval as one coherent architecture.

**v2 changelog (resolves the 5 panel blockers):**
1. Voice streaming preserved via a **decision-phase / stream-phase split** (§2, §2a).
2. `verify` reconciled: **blocking grounding-sufficiency check pre-respond for `factual`; async post-respond verify otherwise** (§4a).
3. `requires_confirmation` is **default-deny**, and tenant context is **hard-asserted** in `act` (§5, §6).
4. **Scoped parity** (tool resolution, not capability), **terminal regenerate behavior**, and a **parity harness as a merge gate** (§9).
5. **Per-surface feature flag with independent rollback** + **observability wired before cutover** + **written performance budgets** (§8, §10).

## Motivation

Aria today is **three separate brains**, each with its own dialogue logic and tool set. This duplication is the root cause of all four pains driving this work — answer quality/hallucination, cost, latency, and maintainability.

| Surface | Implementation | LLM | Tools |
|---|---|---|---|
| **Text chat** (WebSocket) | `aria/core/conversation_engine.py` — slot-filling state machine (`dispatch → nlu → slot_fill → slot_answer → confirmation → check_confirm → execute → response`) | `ChatAnthropic claude-sonnet-4-6`, **every node**, no tiering | `aria/tools/*` |
| **Voice** (LiveKit) | `aria/voice_agent.py` — a separate LiveKit `Agent` class running in a **LiveKit worker process**, streaming tokens straight to TTS | `livekit.plugins.anthropic` Sonnet 4.6 (`ARIA_LLM_MODEL`) | its own inline `@function_tool` methods |
| **"22 agents" service** | `agents/orchestrator.py` — `analyze → gather → reason_and_respond → verify_and_score → execute`, with circuit breaker, **model tiering (haiku/sonnet)**, and hallucination verification | tiered | the 210+ `@mortgage_tool` registry (`agents/tools/*`) |

Consequences mapped to the four pains:

- **Quality/hallucination:** only `agents/orchestrator.py` has a `verify_and_score` check. Chat and voice have none. Guideline RAG is a tool the model *may* call, not a guaranteed citation path.
- **Cost:** the chat graph runs **Sonnet on every node**, even though `agents/orchestrator.py` already proved Haiku suffices for routing-class steps.
- **Latency:** sequential Sonnet calls per turn; no fast path for trivial turns.
- **Maintainability:** a tool added to voice doesn't exist in chat; a hallucination fix in one brain stays broken in the other two. Three tool registries; two circuit breakers.

The "best architecture" is **collapsing three brains into one**, with the right shared layers — but *without* killing voice's token-streaming model (the core risk the panel surfaced).

## 1. Core principle

One **decision core**. Voice and chat are transports that translate their protocol's events into a `Turn`, call the core, and render the result. All dialogue logic, tool access, grounding, and compliance gates live in the core — exactly once. **Token streaming for the final reply stays in each transport**, fed by a prepared context the core returns (see §2a). This is the key v2 refinement: we unify *decision-making*, not *token emission*.

```
┌────────────────┐   ┌──────────────────┐      Transports (thin)
│ Voice (LiveKit) │   │ Chat (WebSocket)  │      translate + stream tokens
└──────┬─────────┘   └────────┬─────────┘
       │     Turn(text, ctx)   │
       └───────────┬───────────┘
                   ▼
   ┌────────────────────────────────────────────────────────────┐
   │              ARIA DECISION CORE (one LangGraph)               │
   │  understand → ground → confirm-gate → act → (grounding check) │
   │            └──────────────► returns CoreDecision ◄────────────┘
   └────────────────────────────────────────────────────────────┘
            │                 │                   │
   ┌────────▼────┐   ┌────────▼─────┐   ┌─────────▼────────┐   Shared services
   │ Model Router │   │ Grounding    │   │ Tool Registry    │   (one each, no dupes)
   │ haiku/sonnet │   │ (RAG + cite) │   │ (single source)  │
   └─────────────┘   └──────────────┘   └──────────────────┘
                   ▼ CoreDecision (grounded context + tool results + directive)
       transport streams `respond` tokens to WS chunks / TTS
```

This retires the three-brain split: `aria/core/conversation_engine.py`, `aria/voice_agent.py`'s inline tools, and `agents/orchestrator.py` collapse into one decision core + one shared tool registry.

## 2. The decision core graph

Keep the existing phase model (`DialoguePhase`) and `AriaState` TypedDict — they are sound — but reorganize nodes so grounding and the confirm gate are **structural**:

| Node | Job | Model tier |
|---|---|---|
| `dispatch` | route by current `phase` (kept as-is) | none |
| `understand` (was `nlu`) | intent + `intent_category` + slot extraction | **Haiku** |
| `slot_fill` / `slot_answer` | ask for / capture missing slots | **Haiku** |
| `ground` | **mandatory for `factual`-category intents only** (§4) — call `GuidelineSearchService`, attach `citations[]` + `sources[]` | retrieval only |
| `grounding_check` | **blocking, factual only** — Haiku: do the retrieved sources actually cover the question? If not → disclaimer-terminal (§4a) | **Haiku** |
| `confirm-gate` | code gate; any `requires_confirmation` tool needs explicit, high-confidence yes (§6) | (parse: Haiku) |
| `act` (was `execute`) | run the resolved tool from the **shared registry** under asserted tenant context (§6) | none |
| *(respond)* | **not a core node** — see §2a; transport streams it | **Sonnet**, streamed |
| `post_verify` | async, fire-and-forget telemetry + next-turn regen signal (§4a) | **Haiku** |

Routing:
- Chitchat: `understand → CoreDecision(directive=chitchat)` → transport streams.
- Factual: `understand → ground → grounding_check → CoreDecision(grounded context)` → transport streams a cited reply.
- Operational read: `understand → [slot_fill]* → act → CoreDecision(tool_results)` → transport streams.
- Operational write: `understand → [slot_fill]* → confirm-gate → act → CoreDecision(tool_results)` → transport streams.

`AriaState` gains: `intent_category: Literal["factual","operational","chitchat"]`, `citations: list`, `sources: list`, `tool_results: dict | None`, `turn_id: str`, `low_confidence: bool`.

### 2a. The `CoreDecision` contract (the streaming seam)

The core returns a typed `CoreDecision` (Pydantic v2 model) instead of a finished string:

```
CoreDecision:
  intent: str
  intent_category: Literal["factual","operational","chitchat"]
  sources: list[Source]            # for citation in the streamed reply
  tool_results: dict | None        # already executed (act ran in-core)
  system_directive: str            # the system/assistant guidance for respond
  requires_confirmation: bool      # if True, transport renders preview, no stream-as-answer
  confirmation_preview: str | None
  terminal: bool                   # disclaimer/cancel paths set this; no further LLM call
  low_confidence: bool
  turn_id: str
```

- **Chat transport:** builds the respond prompt from `system_directive` + `sources` + history, streams Sonnet tokens over WebSocket chunks (it already chunk-streams).
- **Voice transport:** the LiveKit worker imports the core in-process (same monorepo/deploy), calls it to get `CoreDecision`, injects `system_directive` + `sources` into the **LiveKit streaming LLM**, preserving token→TTS streaming and barge-in. Voice never blocks on a separate respond LLM hop owned by the core.
- `terminal=True` (disclaimer, cancel, hard failure) → transport speaks/sends the prepared text directly, no respond LLM call.

This is what lets the brain be unified while voice keeps sub-second time-to-first-audio.

## 3. Model tiering policy

Centralized in one `ModelRouter`:

- **Haiku 4.5** (`claude-haiku-4-5-20251001`): `understand`, slot extraction, slot questions, `grounding_check`, confirmation parsing, `post_verify`.
- **Sonnet 4.6** (`claude-sonnet-4-6`): the streamed `respond` reasoning only (owned by the transport, fed by `CoreDecision`), and any open-ended planning.
- **Escalation hook:** Haiku `understand` low confidence → `ModelRouter` retries that single node on Sonnet; logged and metered (§10). Tested (§9).
- Driven by `ANTHROPIC_MODEL` + new `ARIA_HAIKU_MODEL`, tunable without code change.

## 4. Grounding scope — `factual` intents only

- Intents tagged with a **category** in `aria/core/intent_registry.py`: `factual` | `operational` | `chitchat`.
- `factual` (guideline/eligibility/rate/program facts an LO might repeat to a borrower) → `ground` mandatory.
- `operational` (schedule/send/status) → skip `ground`; already grounded in the DB via tools.
- `chitchat` → skip `ground`.
- **Unknown/low-confidence intent → treated as `factual`** (fail-safe toward grounding).
- Escape hatch: an operational tool whose result Aria *interprets* ("you're $40k short on reserves") may opt into `post_verify` without a RAG round-trip.

### 4a. `verify`, reconciled

The §3-vs-§4 contradiction is resolved by splitting it:

- **Blocking, factual only — `grounding_check` (pre-respond):** Haiku confirms the retrieved `sources` actually cover the question. This runs on the *retrieval result*, not on generated tokens, so it does **not** break streaming. If sources are insufficient → set `terminal=True` with the explicit "general knowledge, not indexed official guidelines" disclaimer and stop.
- **Async, all intents — `post_verify` (post-respond):** fire-and-forget Haiku check for telemetry; a failure raises `regenerate_signal` consumed on the **next** turn (and feeds the alert in §10). Never blocks the reply the user already got.
- **Citation enforcement:** the respond prompt is hard-required to cite from `sources` and refuse guideline claims not present in them.

**Terminal regenerate behavior (QA-required):** at most **one** in-turn regenerate. Factual + zero usable sources after `ground` → go straight to disclaimer-terminal; do **not** loop. `low_confidence=True` is surfaced to the transport.

## 5. One tool registry — default-deny confirmation

- **The `@mortgage_tool` registry (`tool_registry`) is the only source of truth.** API: `get_all()`, `get_for_agent(role)`, `get(name)`; `ToolDefinition.func/.name/.description/.agent_roles`.
- `act` resolves tools via the existing `create_tool_functions_from_registry()` bridge in `agents/dynamic_tool_loader.py`.
- **Voice stops defining its own tools.** `aria/voice_agent.py`'s `@function_tool` methods become thin generated wrappers delegating to registry functions — **no business logic in the voice file.**
- **`ToolDefinition` gains `side_effect: bool` and `requires_confirmation: bool`.** Default-deny per Security: any tool that is side-effecting (or untagged/unknown) defaults to `requires_confirmation=True`. A tool opts *out* only explicitly, recorded in code review. Read-only tools default `requires_confirmation=False`.
- **`surface_constraints`** on `ToolDefinition` declares capability gates (e.g. pre-approval letters, mass email = LO-assistant mode only), replacing the inline checks in `voice_agent.py`. These are tested as explicit parity exceptions (§9).

## 6. Compliance / confirmation / tenant isolation

- Any tool with `requires_confirmation=True` cannot reach `act` without `phase == CONFIRMING` resolving to an explicit, **high-confidence** yes. Ambiguous/low-confidence yes → **re-prompt, never proceed** (Security).
- Confirmation yes/no is parsed by Haiku, but **the gate is code**.
- **Tenant context is hard-asserted in `act`:** the session must have `app.current_tenant` set from `AriaState.org_id` before any tool runs. Because `get_db()` RLS **fails silently** when context is unset (per `CLAUDE.md`), `act` raises `TenantIsolationError` if context is missing — converting the silent failure into a hard stop. The **voice worker must propagate org context from the authenticated LiveKit token's org claim** into the core call; without it, `act` refuses to run.
- Audit event emitted on every confirmed write.

## 7. Error handling & resilience

- **Consolidate the two circuit breakers** (`agents/orchestrator.py` `CircuitBreaker` + `conversation_engine.py` `_AriaCircuitBreaker`) into one shared `LLMCircuitBreaker` used by `ModelRouter`.
- Per-node LLM timeout (keep 30s) with fast-fail when the breaker is open.
- `ground` failure → degrade to disclaimer-terminal; never block.
- `act` failure → `_detect_execution_failure` (exists) routes to an apologetic `CoreDecision`; never narrated as success.
- **Idempotency:** writes are deduped per `turn_id` via Redis key `aria:turn:{turn_id}` (24h TTL). Replaying a `turn_id` after a transport reconnect returns the cached `CoreDecision` and does **not** re-execute `act`.

## 8. Migration path — flag-gated parallel run, chat first

Driven by a feature flag **`ARIA_UNIFIED_CORE`** with per-surface values: `off` | `chat` | `voice` | `both`. Default `off` in prod. The old `conversation_engine` and `voice_agent` paths stay deployable and independently revertable until the flag has been at `both`/100% for **two weeks**.

1. **Extract shared services** (no behavior change): `ModelRouter`, unified `LLMCircuitBreaker`, `side_effect`/`requires_confirmation`/`surface_constraints` on `ToolDefinition`.
   - **Interim win:** route the *existing* `voice_agent.py` LLM calls through `ModelRouter` Haiku tiering immediately — voice gets cheaper/faster before its full migration, and tiering is de-risked on real traffic.
2. **Build the decision core + `CoreDecision`** and wire the **chat** transport behind `ARIA_UNIFIED_CORE=chat`. Shadow-compare against the old chat path before flipping. Chat is observable and low blast radius.
3. **Point voice at the core** (`=voice`): replace inline tools with registry wrappers; voice fulfills `respond` via its streaming LLM fed by `CoreDecision`. Validate voice TTFB budget (§10) on staging before flip.
4. **Retire `agents/orchestrator.py`** as a separate brain — its verify/tiering value now lives in the core.
5. **Delete `aria/tools/*` duplicates** — only after the parity harness (§9) is green in CI and the flag has been at 100% for two weeks. Never in the same PR as a cutover.

Each step is independently shippable and reversible per surface.

## 9. Testing & definition of done

- **Parity harness (merge gate):** `tests/test_aria_core_parity.py` runs a fixture corpus of `Turn`s through both the chat and voice transport adapters against the core and asserts **identical resolved tool calls** — *modulo* declared `surface_constraints`, which are asserted as explicit exceptions. Must be green in CI before any step-4/5 deletion. "Parity" = **tool-resolution parity, not capability parity.**
- **Grounding contract tests:** `factual` replies contain ≥1 source; `grounding_check` sets `terminal` when sources are insufficient; `operational` turns skip `ground`. Build on `tests/test_aria_retrieval.py`, `tests/test_guideline_rag_e2e.py`.
- **Regenerate terminal test:** factual + zero sources → exactly one disclaimer-terminal, no loop; `low_confidence=True`.
- **Confirmation gate tests:** no `requires_confirmation` tool executes without explicit high-confidence yes; ambiguous yes → re-prompt.
- **Tenant isolation test:** `act` raises `TenantIsolationError` when `app.current_tenant` is unset; voice path propagates org from token.
- **Tiering tests:** Haiku model id on `understand`/slot/`grounding_check`/parse/`post_verify`; Sonnet on streamed respond; escalation hook fires on low confidence and is metered.
- **Idempotency test:** replaying a `turn_id` after a simulated reconnect returns cached `CoreDecision`, no double write.

## 10. Performance budgets & observability (wired before cutover)

**Budgets (per DevOps/Performance, measured on staging):**
- Voice **time-to-first-audio < 1.0s p75**.
- Chat **time-to-first-token < 800ms p75**.
- Factual **decision-phase (understand→ground→grounding_check) < 1.2s p95**.
- `GuidelineSearchService` results cached in Redis keyed on normalized query (confirm it isn't already sharing `retrieval_service`'s 60s hot-cache; add if not).

**Metrics emitted per turn:** per-node latency, `grounding_hit_rate`, `confirmation_misparse_rate` (sampled human review), `regenerate_rate`, per-surface `error_rate`, `model_tier` usage, escalation-hook fire count.

**Alerts (before cutover):** `regenerate_rate` spike (RAG/verify regression), voice TTFB p75 over budget, per-surface error_rate, escalation-hook firing on >X% of turns (cost blowout).

## Open questions

None blocking. The five panel blockers are resolved above. Remaining judgment calls deferred to the implementation plan: exact `Source` schema shape, the staging fixture corpus contents for the parity harness, and the confidence-threshold value for the escalation hook (start conservative, tune on telemetry).
