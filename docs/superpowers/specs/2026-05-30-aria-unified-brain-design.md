# Aria Unified Brain — Design (Approach A)

**Date:** 2026-05-30
**Status:** Approved for planning
**Scope:** The whole Aria brain — voice + chat transport, orchestration, the agent/tool layer, memory, and knowledge retrieval as one coherent architecture.

## Motivation

Aria today is **three separate brains**, each with its own dialogue logic and tool set. This duplication is the root cause of all four pains driving this work — answer quality/hallucination, cost, latency, and maintainability.

| Surface | Implementation | LLM | Tools |
|---|---|---|---|
| **Text chat** (WebSocket) | `aria/core/conversation_engine.py` — slot-filling state machine (`dispatch → nlu → slot_fill → slot_answer → confirmation → check_confirm → execute → response`) | `ChatAnthropic claude-sonnet-4-6`, **every node**, no tiering | `aria/tools/*` |
| **Voice** (LiveKit) | `aria/voice_agent.py` — a separate LiveKit `Agent` class | `livekit.plugins.anthropic` Sonnet 4.6 (`ARIA_LLM_MODEL`) | its own inline `@function_tool` methods |
| **"22 agents" service** | `agents/orchestrator.py` — `analyze → gather → reason_and_respond → verify_and_score → execute`, with circuit breaker, **model tiering (haiku/sonnet)**, and hallucination verification | tiered | the 210+ `@mortgage_tool` registry (`agents/tools/*`) |

Consequences that map directly to the four pains:

- **Quality/hallucination:** only `agents/orchestrator.py` has a `verify_and_score` hallucination check. Chat and voice have none. Guideline RAG is a tool the model *may* call, not a guaranteed citation path.
- **Cost:** the chat graph runs **Sonnet on every node** (NLU, slot-fill, confirmation, chitchat), even though `agents/orchestrator.py` already proved Haiku is sufficient for routing-class steps.
- **Latency:** sequential Sonnet calls per turn; no fast path for trivial turns.
- **Maintainability:** a tool added to voice doesn't exist in chat; a hallucination fixed in one brain stays broken in the other two. Three tool registries to keep in sync; two separate circuit breakers.

The "best architecture" is therefore **collapsing three brains into one**, with the right shared layers.

## 1. Core principle

One reasoning core. Voice and chat become **thin transports** that translate their protocol's events into a `Turn` and render the core's `TurnResult` back out. All dialogue logic, tool access, grounding, and compliance gates live in the core — exactly once.

```
┌────────────────┐   ┌──────────────────┐      Transports (thin adapters)
│ Voice (LiveKit) │   │ Chat (WebSocket)  │      — translate only, no logic
└──────┬─────────┘   └────────┬─────────┘
       │     Turn(text, ctx)   │
       └───────────┬───────────┘
                   ▼
   ┌────────────────────────────────────────────────────────────┐
   │                    ARIA CORE (one LangGraph)                  │
   │  understand → ground → confirm → act → verify → respond       │
   └────────────────────────────────────────────────────────────┘
            │                 │                   │
   ┌────────▼────┐   ┌────────▼─────┐   ┌─────────▼────────┐   Shared services
   │ Model Router │   │ Grounding    │   │ Tool Registry    │   (one each, no dupes)
   │ haiku/sonnet │   │ (RAG + cite) │   │ (single source)  │
   └─────────────┘   └──────────────┘   └──────────────────┘
```

This retires the three-brain split: `aria/core/conversation_engine.py`, `aria/voice_agent.py`'s inline tools, and `agents/orchestrator.py` collapse into the one core + one shared tool registry.

## 2. The core graph

Keep the existing phase model (`DialoguePhase`) and `AriaState` TypedDict from `aria/core/conversation_engine.py` — they are sound — but reorganize nodes so grounding and verification are **structural, not optional**:

| Node | Job | Model tier |
|---|---|---|
| `dispatch` | route by current `phase` (kept as-is) | none |
| `understand` (was `nlu`) | intent + slot extraction | **Haiku** |
| `slot_fill` / `slot_answer` | ask for / capture missing slots | **Haiku** |
| `ground` | **NEW, mandatory for `factual`-category intents only** (see §4) — call `GuidelineSearchService`, attach `citations[]` + `sources[]` to state | retrieval only |
| `confirm` | render preview of any write action; gate on explicit user yes | **Haiku** |
| `act` (was `execute`) | run the resolved tool from the **shared registry** | none |
| `respond` | final NL reply; **must cite** when `ground` ran | **Sonnet** |
| `verify` | hallucination/grounding check on the drafted reply | **Haiku**, async |

Edges:

- Chitchat: `understand → respond` (short-circuit).
- Factual: `understand → ground → respond → verify`.
- Operational write: `understand → [slot_fill / slot_answer]* → confirm → act → verify → respond`.
- Operational read (e.g. "what's Mike's loan status"): `understand → [slot_fill]* → act → respond` (no `ground`; data comes from the tool/DB).

`AriaState` gains new fields: `citations: List`, `sources: List`, `intent_category: str` (`factual` | `operational` | `chitchat`), `turn_id: str`.

## 3. Model tiering policy

Today every node in the chat graph calls Sonnet 4.6. New policy, centralized in one `ModelRouter`:

- **Haiku 4.5** (`claude-haiku-4-5-20251001`): NLU/`understand`, slot extraction, slot questions, confirmation parsing ("did they say yes?"), and the `verify` pass. These are classification/extraction tasks — Haiku is sufficient, ~5× cheaper, ~2× faster.
- **Sonnet 4.6** (`claude-sonnet-4-6`): only the final `respond` reasoning and any genuinely open-ended planning.
- **Escalation hook:** if Haiku's `understand` returns low confidence, `ModelRouter` retries that single node on Sonnet. One knob, logged.

Driven by `ANTHROPIC_MODEL` and a new `ARIA_HAIKU_MODEL` env var, tunable without code change. This is the single biggest cost/latency lever and is currently unused in the chat and voice brains.

## 4. Grounding & citation contract

`GuidelineSearchService` already returns `{answer, citations, sources, disclaimer}` with a fallback (`aria/tools/knowledge_tools.py`). The design promotes it to a **first-class contract** every factual answer flows through.

**Grounding scope — `factual`-category intents only:**

- Intents are tagged with a **category** in `aria/core/intent_registry.py`: `factual`, `operational`, or `chitchat`.
- `factual` (guideline questions, eligibility/qualification claims, rate/program facts — anything an LO might repeat to a borrower) → `ground` is **mandatory**.
- `operational` (schedule, send, status lookups) → **skip `ground`**; these are already grounded in the DB via tools, so forcing RAG adds latency/cost for no quality gain.
- `chitchat` → skip `ground`.
- **Unknown/low-confidence intent → treated as `factual`** (fail-safe toward grounding).
- Escape hatch: when an operational tool returns data that Aria then *interprets* (e.g. "you're $40k short on reserves"), that turn may opt into the `verify` pass without a full RAG round-trip.

**Citation enforcement:**

- `ground` node populates `state["citations"]` and `state["sources"]`.
- `respond` node's system prompt is hard-required to cite from `state["sources"]` and **refuse to assert guideline facts not present in them**, falling back to the explicit "general knowledge, not indexed official guidelines" disclaimer the service already returns.
- `verify` node fails the turn (and triggers one regenerate) if the reply makes a guideline claim with **zero** backing sources.

This fixes hallucination *uniformly* across voice and chat, rather than only in `agents/orchestrator.py`.

## 5. One tool registry

Today there are three tool sets: `aria/tools/*`, `voice_agent.py` inline `@function_tool`s, and the 210+ `@mortgage_tool` registry. Target single source of truth:

- **The `@mortgage_tool` registry (`tool_registry`) is the only source of truth.** It already has the right API: `get_all()`, `get_for_agent(role)`, `get(name)`, and `ToolDefinition` with `.func / .name / .description / .agent_roles`.
- The `act` node resolves tools via the existing `create_tool_functions_from_registry()` bridge in `agents/dynamic_tool_loader.py`.
- **Voice stops defining its own tools.** `aria/voice_agent.py`'s `@function_tool` methods become thin generated wrappers over the same registry. LiveKit requires function-tool decorators, but they delegate to registry functions — **no business logic in the voice file.**
- **Confirmation is registry-driven:** add a `requires_confirmation: bool` flag to `ToolDefinition`. The `confirm` gate reads this flag instead of each surface re-encoding which actions are dangerous (adverse-action notices, sends, etc. set it `True`).

This is the maintainability fix: add a tool once → both surfaces get it; fix a bug once → fixed everywhere.

## 6. Compliance / confirmation gates

Mortgage is regulated, so "the LO confirmed before sending the adverse-action notice" must be **deterministic**, not model-judged (this is why we keep the state machine rather than a free tool-calling loop):

- Any tool with `requires_confirmation=True` cannot reach `act` without `state["phase"] == CONFIRMING` resolving to an explicit yes.
- Preview text is generated and shown; the user's yes/no is parsed by Haiku, but **the gate itself is code**, not the LLM.
- An audit event is emitted on every confirmed write (existing audit infrastructure).

## 7. Error handling & resilience

- **Consolidate the two circuit breakers** (`agents/orchestrator.py` `CircuitBreaker` and `conversation_engine.py` `_AriaCircuitBreaker`) into one shared `LLMCircuitBreaker` used by `ModelRouter`.
- Per-node LLM timeout (keep the current 30s) with fast-fail when the breaker is open.
- `ground` failure → degrade to the existing disclaimer fallback; never block the turn.
- `act` failure → `_detect_execution_failure` (exists) routes to an apologetic `respond`; never narrated as success.
- Transport drop (WS/LiveKit) → the core turn is **idempotent per `turn_id`** so reconnect does not double-execute writes.

## 8. Migration path (incremental, no big-bang)

Chat-first, because chat is observable (full transcripts, replayable turns, low blast radius) while voice is ephemeral and real-time. Voice inherits a proven core.

1. **Extract shared services** (no behavior change): `ModelRouter`, unified `LLMCircuitBreaker`, and the `requires_confirmation` flag on `ToolDefinition`.
   - **Interim win:** apply Haiku tiering via `ModelRouter` to the *existing* `aria/voice_agent.py` immediately, so voice gets cheaper/faster before the full voice migration in step 3, and the tiering policy is de-risked on real traffic early.
2. **Rebuild the chat graph** in `aria/core/conversation_engine.py` to the §2 node set, wiring `ground` (factual-only) + tiering + the citation contract. Prove the new core here.
3. **Point voice at the core:** replace `voice_agent.py`'s inline tools with registry-backed wrappers; route voice dialogue through the same core turn function.
4. **Retire `agents/orchestrator.py`** as a separate brain — its good parts (verify, tiering) now live in the core; reduce it to the registry it owns or delete it.
5. **Delete `aria/tools/*` duplicates** once registry parity is confirmed.

Each step is independently shippable and reversible.

## 9. Testing strategy

- **Golden-turn tests:** a fixture set of (intent, expected tool, expected citation-presence) run against the core directly — transport-free, so one suite covers both voice and chat.
- **Grounding contract tests:** assert `factual` replies contain ≥1 source; assert `verify` rejects an un-sourced guideline claim; assert `operational` turns skip `ground`. Build on existing `tests/test_aria_retrieval.py` and `tests/test_guideline_rag_e2e.py`.
- **Confirmation gate tests:** assert no `requires_confirmation` tool executes without an explicit yes.
- **Tiering tests:** assert `understand`/slot/`confirm`/`verify` nodes call the Haiku model id and `respond` calls Sonnet (mock the router).
- **Parity test:** the same `Turn` through the voice adapter and the chat adapter yields the same tool calls.
- **Idempotency test:** replaying a `turn_id` after a simulated transport drop does not double-execute a write.

## Open questions

None outstanding. The two prior open decisions are resolved in this spec:
1. `ground` scope → `factual`-category intents only, unknown → factual (§4).
2. Migration order → chat-first, with voice tiering pulled forward as an interim win (§8).
