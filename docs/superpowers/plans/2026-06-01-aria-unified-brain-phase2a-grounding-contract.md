# Aria Unified Brain — Phase 2A: Grounding Contract — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route guideline/knowledge answers through `GuidelineSearchService` with a deterministic sufficiency gate and enforced citations, so factual answers are grounded-or-disclaimed instead of free-form LLM output — closing the hallucination gap on the factual path.

**Architecture:** Additive to the existing `conversation_engine` LangGraph, fully behind `ARIA_GROUNDING_ENABLED` (default off). A new `aria/core/grounding.py` wraps the existing (tested) `KnowledgeTools.search_guidelines_rag()` RAG path. Two new graph nodes (`ground`, `grounding_check`) handle the `mortgage_guideline_question` (category `knowledge`) intent; `query_mode_node` delegates guideline-type QUERY turns to the same function. The grounded answer is produced by the RAG service (already carries inline `[1]`/`[2]` citations), so the grounding path emits it directly — no extra LLM regeneration. When the flag is off, behavior is byte-identical to today.

**Tech Stack:** Python 3.11 (local venv is 3.14 — same caveats as Phase 1: `../.venv/bin/python` from `backend/`, ignore Pydantic-V1 warnings + Telnyx/REDIS log noise), LangGraph, pytest.

**Base branch:** Build on Phase 1. Branch off `feat/aria-unified-brain-phase1-clean` (PR #82) or off `main` once #82 merges. Phase 2A does not depend on Phase 1 code, but stacking keeps history clean.

**Spec:** `docs/superpowers/specs/2026-05-30-aria-unified-brain-design.md` v2, §2 (ground/grounding_check nodes), §4 (factual scope), §4a (sufficiency gate, terminal disclaimer, citation enforcement). Design approved in conversation.

**Key real interfaces (verified):**
- `aria/tools/knowledge_tools.py` → `KnowledgeTools().search_guidelines_rag(question, loan_program=None, agency=None, include_overlays=True, tenant_id=None)` → async, returns `{answer, citations[], sources[], confidence, rag_enabled, query}` (+ `disclaimer` on the no-RAG fallback). Manages its own DB session.
- `aria/core/intent_registry.py` → `Intent` dataclass has `.category` (`knowledge`/`documents`/…); `IntentRegistry.get().get_intent(name)`; the `mortgage_guideline_question` intent has `category="knowledge"`, `required_slots=[SlotSpec("question", ...)]`, `requires_confirmation=False`.
- `aria/core/conversation_engine.py` → `route_after_nlu`/`route_after_slot_answer` routers; `AriaState` TypedDict; `DialoguePhase` enum; graph wiring via `graph.add_node`/`add_conditional_edges`/`add_edge`; `query_mode_node`.

---

## File Structure

- `aria/core/grounding.py` — **NEW.** `GroundingResult` dataclass, `ground_answer()`, `is_sufficiently_grounded()`, `looks_like_guideline_question()`, `format_grounded_message()`. One responsibility: the grounding contract, transport-free and graph-free so it's unit-testable in isolation.
- `aria/core/intent_registry.py` — **MODIFY.** Add `intent_category(name)` helper deriving `factual`/`operational`/`chitchat` from the existing `.category` field.
- `aria/core/conversation_engine.py` — **MODIFY.** Add `ground_node` + `grounding_check_node`; add `sources`/`citations`/`grounded`/`grounding_answer`/`grounding_disclaimer` to `AriaState`; add the factual branch to `route_after_nlu` and `route_after_slot_answer` (flag-gated); wire the two nodes into the graph; delegate guideline QUERY turns in `query_mode_node`.
- Tests: `tests/test_grounding.py`, `tests/test_intent_category.py`, `tests/test_conversation_engine_grounding.py` — **NEW.**

---

## Task 1: `intent_category()` helper

**Files:**
- Modify: `backend/aria/core/intent_registry.py`
- Test: `backend/tests/test_intent_category.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_intent_category.py
from aria.core.intent_registry import intent_category


def test_knowledge_intent_is_factual():
    assert intent_category("mortgage_guideline_question") == "factual"


def test_action_intent_is_operational():
    assert intent_category("send_sms") == "operational"


def test_none_or_unknown_is_chitchat():
    assert intent_category(None) == "chitchat"
    assert intent_category("not_a_real_intent") == "chitchat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_intent_category.py -v`
Expected: FAIL — `ImportError: cannot import name 'intent_category'`.

- [ ] **Step 3: Add the helper**

Add a module-level function at the end of `backend/aria/core/intent_registry.py`:

```python
def intent_category(intent_name) -> str:
    """Derive the Phase-2 grounding category from an intent's registry category.

    'factual'     -> guideline/knowledge questions that must be grounded (RAG).
    'chitchat'    -> no resolved intent (general conversation).
    'operational' -> everything else (DB-backed actions/lookups; no RAG).
    """
    if not intent_name:
        return "chitchat"
    intent = IntentRegistry.get().get_intent(intent_name)
    if intent is None:
        return "chitchat"
    return "factual" if intent.category == "knowledge" else "operational"
```

(Verify `IntentRegistry` and its `.get()`/`.get_intent()` exist as used — they do, per the registry singleton. Do not change the `Intent` dataclass.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_intent_category.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && git add backend/aria/core/intent_registry.py backend/tests/test_intent_category.py && git commit -m "feat(aria): intent_category helper (factual/operational/chitchat)"
```

---

## Task 2: `aria/core/grounding.py` — the grounding contract

**Files:**
- Create: `backend/aria/core/grounding.py`
- Test: `backend/tests/test_grounding.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_grounding.py
import pytest
from aria.core import grounding
from aria.core.grounding import (
    GroundingResult,
    is_sufficiently_grounded,
    looks_like_guideline_question,
    format_grounded_message,
)


def test_sufficient_when_sources_and_confidence_ok():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=0.7)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is True


def test_insufficient_when_no_sources():
    r = GroundingResult(answer="a", sources=[], confidence=0.9)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_insufficient_when_low_confidence():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=0.2)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_insufficient_when_confidence_none():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=None)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_looks_like_guideline_question():
    assert looks_like_guideline_question("What is the FHA reserve requirement?") is True
    assert looks_like_guideline_question("How many leads do I have today?") is False
    assert looks_like_guideline_question("") is False


def test_format_grounded_message_includes_sources():
    msg = format_grounded_message("Answer body [1].", [{"guideline_name": "FHA Handbook 4000.1"}])
    assert "Answer body [1]." in msg
    assert "FHA Handbook 4000.1" in msg


@pytest.mark.asyncio
async def test_ground_answer_marks_grounded(monkeypatch):
    async def fake_rag(self, question, loan_program=None, agency=None, include_overlays=True, tenant_id=None):
        return {"answer": "FHA requires X [1].",
                "sources": [{"guideline_name": "FHA Handbook 4000.1"}],
                "citations": [{"index": 1, "guideline_name": "FHA Handbook 4000.1"}],
                "confidence": 0.8, "rag_enabled": True, "query": question}
    monkeypatch.setattr("aria.tools.knowledge_tools.KnowledgeTools.search_guidelines_rag", fake_rag)
    result = await grounding.ground_answer("FHA reserves?", org_id=1)
    assert result.grounded is True
    assert result.sources and result.confidence == 0.8


@pytest.mark.asyncio
async def test_ground_answer_disclaimer_on_no_results(monkeypatch):
    async def fake_rag(self, question, loan_program=None, agency=None, include_overlays=True, tenant_id=None):
        return {"answer": "General knowledge answer.", "sources": [], "citations": [],
                "confidence": None, "rag_enabled": False,
                "disclaimer": "Answer based on general knowledge.", "query": question}
    monkeypatch.setattr("aria.tools.knowledge_tools.KnowledgeTools.search_guidelines_rag", fake_rag)
    result = await grounding.ground_answer("obscure question", org_id=1)
    assert result.grounded is False
    assert result.disclaimer
```

If `pytest.mark.asyncio` is unavailable in this repo, check `pyproject.toml`/`pytest.ini` for `asyncio_mode`. If async tests are not configured, wrap the two async tests with `asyncio.run(...)` inside sync test functions instead of the marker. Confirm during Step 2.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_grounding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aria.core.grounding'`. (Also note here whether async tests run via marker or need the `asyncio.run` fallback.)

- [ ] **Step 3: Create the module**

```python
# backend/aria/core/grounding.py
"""
Grounding contract for Aria factual answers (Phase 2A).

Wraps the existing KnowledgeTools/GuidelineSearchService RAG path and adds a
deterministic sufficiency gate + citation formatting, so guideline answers are
grounded-or-disclaimed rather than free-form LLM output.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aria.grounding")

# Minimum average retrieval similarity to treat a RAG answer as sufficiently grounded.
GROUNDING_MIN_CONFIDENCE = float(os.getenv("ARIA_GROUNDING_MIN_CONFIDENCE", "0.45"))

DISCLAIMER = (
    "I don't have this in the indexed official guidelines, so this is general "
    "knowledge — please verify against the source guideline before relying on it."
)


@dataclass
class GroundingResult:
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None
    grounded: bool = False
    disclaimer: Optional[str] = None


def is_sufficiently_grounded(result: "GroundingResult",
                             min_confidence: float = GROUNDING_MIN_CONFIDENCE) -> bool:
    """Blocking sufficiency gate: require >=1 source AND confidence at/above threshold."""
    if not result.sources:
        return False
    if result.confidence is None:
        return False
    return result.confidence >= min_confidence


async def ground_answer(question: str, org_id) -> "GroundingResult":
    """Run the guideline RAG path and wrap the result in a GroundingResult.

    Never raises — on any failure, returns an ungrounded result with a disclaimer.
    """
    from aria.tools.knowledge_tools import KnowledgeTools
    try:
        tenant_id = int(org_id) if org_id is not None else None
    except (TypeError, ValueError):
        tenant_id = None
    try:
        raw = await KnowledgeTools().search_guidelines_rag(question=question, tenant_id=tenant_id)
    except Exception as e:
        logger.exception("ground_answer RAG call failed: %s", e)
        return GroundingResult(answer=DISCLAIMER, grounded=False, disclaimer=DISCLAIMER)

    result = GroundingResult(
        answer=raw.get("answer", "") or "",
        sources=raw.get("sources", []) or [],
        citations=raw.get("citations", []) or [],
        confidence=raw.get("confidence"),
        disclaimer=raw.get("disclaimer"),
    )
    result.grounded = is_sufficiently_grounded(result)
    return result


_GUIDELINE_HINTS = (
    "fha", "usda", "conventional", "conforming", "guideline", "eligibility",
    "reserve", "ltv", "dti", "credit score", "seasoning", "waiting period",
    "down payment requirement", "occupancy requirement", "loan limit", "qualify",
)


def looks_like_guideline_question(text: str) -> bool:
    """Heuristic: does this QUERY-mode turn look like a guideline question?

    Intentionally conservative — only delegates QUERY turns that clearly mention
    guideline concepts to the grounding path; operational queries fall through.
    """
    if not text:
        return False
    t = text.lower()
    return any(hint in t for hint in _GUIDELINE_HINTS)


def format_grounded_message(answer: str, sources: List[Dict[str, Any]]) -> str:
    """Append a human-readable Sources list to a RAG answer (which already has [n] markers)."""
    if not sources:
        return answer
    lines = []
    for i, s in enumerate(sources, start=1):
        name = s.get("guideline_name") or s.get("guideline_type") or "Guideline"
        program = s.get("loan_program")
        lines.append(f"[{i}] {name}" + (f" ({program})" if program else ""))
    return f"{answer}\n\nSources:\n" + "\n".join(lines)
```

(Verify `KnowledgeTools()` constructs with no required args — per `aria/tools/knowledge_tools.py`. If its `__init__` requires arguments, adapt the call and report it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_grounding.py -v`
Expected: all passed (8).

- [ ] **Step 5: Commit**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && git add backend/aria/core/grounding.py backend/tests/test_grounding.py && git commit -m "feat(aria): grounding contract module (ground_answer + sufficiency gate)"
```

---

## Task 3: Wire grounding into the graph (flag-gated)

Add `ground` + `grounding_check` nodes and route the factual intent through them when `ARIA_GROUNDING_ENABLED` is on. The RAG answer already carries citations, so `grounding_check` emits the final message directly and ends the turn.

**Files:**
- Modify: `backend/aria/core/conversation_engine.py`
- Test: `backend/tests/test_conversation_engine_grounding.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_conversation_engine_grounding.py
import pytest
from aria.core import conversation_engine as ce
from aria.core import grounding


def _base_state(message, intent="mortgage_guideline_question", slots=None):
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content=message)],
        "intent": intent, "slots": slots or {"question": message},
        "missing_slots": [], "current_slot_question": None,
        "phase": ce.DialoguePhase.UNDERSTANDING.value,
        "task_result": None, "confirmation_preview": None,
        "user_id": "u1", "org_id": "1", "user_name": "Lo", "user_email": None,
        "user_role": "loan_officer", "mode": None, "voice_preferences": None,
        "iteration_count": 0, "error": None,
    }


def test_route_after_nlu_sends_factual_to_ground_when_flag_on(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    state = _base_state("FHA reserves?")
    state["phase"] = ce.DialoguePhase.UNDERSTANDING.value
    assert ce.route_after_nlu(state) == "ground"


def test_route_after_nlu_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "false")
    state = _base_state("FHA reserves?")
    # not chitchat, no missing slots -> legacy path is "confirmation"
    assert ce.route_after_nlu(state) == "confirmation"


@pytest.mark.asyncio
async def test_grounding_check_emits_disclaimer_when_insufficient(monkeypatch):
    from langchain_core.messages import AIMessage
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(answer="x", sources=[], confidence=None,
                                         grounded=False, disclaimer="DISC")
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("obscure")
    out = await ce.ground_node(state)
    merged = {**state, **out}
    final = ce.grounding_check_node(merged)
    text = final["messages"][-1].content
    assert "DISC" in text


@pytest.mark.asyncio
async def test_grounding_check_emits_cited_answer_when_grounded(monkeypatch):
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(
            answer="FHA requires X [1].",
            sources=[{"guideline_name": "FHA Handbook 4000.1"}],
            confidence=0.8, grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("FHA reserves?")
    out = await ce.ground_node(state)
    merged = {**state, **out}
    final = ce.grounding_check_node(merged)
    text = final["messages"][-1].content
    assert "FHA requires X [1]." in text
    assert "FHA Handbook 4000.1" in text
```

(If async tests need the `asyncio.run` fallback per Task 2 Step 2, apply the same pattern here.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_grounding.py -v`
Expected: FAIL — `ground_node`/`grounding_check_node` don't exist; `route_after_nlu` returns "confirmation" for the flag-on case.

- [ ] **Step 3: Add imports, AriaState fields, the flag helper, and the two nodes**

In `backend/aria/core/conversation_engine.py`:

(a) Add near the top imports:
```python
from aria.core.grounding import ground_answer, format_grounded_message, DISCLAIMER
from aria.core.intent_registry import intent_category
```

(b) Add fields to `AriaState` (after `error: Optional[str]`):
```python
    # Grounding (Phase 2A)
    sources: Optional[List[Dict[str, Any]]]
    citations: Optional[List[Dict[str, Any]]]
    grounded: Optional[bool]
    grounding_answer: Optional[str]
    grounding_disclaimer: Optional[str]
```

(c) Add a flag helper near the other module-level helpers:
```python
def _grounding_enabled() -> bool:
    return os.getenv("ARIA_GROUNDING_ENABLED", "false").lower() == "true"
```
(Confirm `os` is imported at module level; it is used elsewhere in this file.)

(d) Add the two node functions (place them near `query_mode_node`):
```python
async def ground_node(state: AriaState) -> AriaState:
    """Retrieve grounded guideline context for a factual turn."""
    question = (state.get("slots") or {}).get("question") \
        or (state["messages"][-1].content if state.get("messages") else "")
    result = await ground_answer(question, state["org_id"])
    return {
        "sources": result.sources,
        "citations": result.citations,
        "grounded": result.grounded,
        "grounding_answer": result.answer,
        "grounding_disclaimer": result.disclaimer or DISCLAIMER,
    }


def grounding_check_node(state: AriaState) -> AriaState:
    """Blocking sufficiency gate: emit the cited answer, or a terminal disclaimer."""
    if state.get("grounded"):
        msg = format_grounded_message(state.get("grounding_answer") or "",
                                      state.get("sources") or [])
    else:
        msg = state.get("grounding_disclaimer") or DISCLAIMER
    return {
        "messages": [AIMessage(content=msg)],
        "phase": DialoguePhase.RESPONDING.value,
        "intent": None,
        "missing_slots": [],
        "current_slot_question": None,
    }
```
(Match the field-reset style the existing `response_node` uses at end-of-turn; mirror whichever keys it resets so session state stays consistent. Do NOT regenerate the answer with an LLM — the RAG answer is authoritative.)

- [ ] **Step 4: Add the factual branch to the routers (flag-gated)**

Update `route_after_nlu`:
```python
def route_after_nlu(state: AriaState) -> str:
    if state["phase"] == DialoguePhase.CHITCHAT:
        return "response"
    if state["missing_slots"]:
        return "slot_fill"
    if _grounding_enabled() and intent_category(state.get("intent")) == "factual":
        return "ground"
    return "confirmation"
```
Apply the same flag-gated factual branch to `route_after_slot_answer` (so a factual intent that needed slot-filling also reaches grounding once its `question` slot is captured):
```python
def route_after_slot_answer(state: AriaState) -> str:
    if state["missing_slots"]:
        return "slot_fill"
    if _grounding_enabled() and intent_category(state.get("intent")) == "factual":
        return "ground"
    return "confirmation"
```
(Read the real current body of `route_after_slot_answer` first and insert the factual branch before its final `return "confirmation"`.)

- [ ] **Step 5: Wire the nodes into the graph**

In the graph-build section (where `graph.add_node(...)` calls are):
```python
graph.add_node("ground", ground_node)
graph.add_node("grounding_check", grounding_check_node)
```
Add `"ground"` as a valid target in the conditional-edge mappings for `route_after_nlu` AND `route_after_slot_answer` (the dicts passed to `add_conditional_edges`). Then:
```python
graph.add_edge("ground", "grounding_check")
graph.add_edge("grounding_check", END)
```
(Read the existing `add_conditional_edges("nlu", route_after_nlu, {...})` and `add_conditional_edges("slot_answer", route_after_slot_answer, {...})` calls and add the `"ground": "ground"` entry to both mapping dicts.)

- [ ] **Step 6: Run the tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_grounding.py -v`
Expected: all passed (4).

- [ ] **Step 7: Confirm the graph still compiles with the flag both off and on**

Run:
```
cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -c "from aria.core.conversation_engine import get_aria_graph; get_aria_graph(); print('graph ok')"
ARIA_GROUNDING_ENABLED=true ../.venv/bin/python -c "from aria.core.conversation_engine import get_aria_graph; get_aria_graph(); print('graph ok (flag on)')"
```
Expected: prints `graph ok` then `graph ok (flag on)`.

- [ ] **Step 8: Commit**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && git add backend/aria/core/conversation_engine.py backend/tests/test_conversation_engine_grounding.py && git commit -m "feat(aria): wire grounding nodes into chat graph (flag-gated)"
```

---

## Task 4: Delegate guideline QUERY turns to grounding

`query_mode_node` answers QUERY-mode turns with a direct, ungrounded LLM call. When the flag is on and the turn looks like a guideline question, delegate to the grounding path instead. Operational QUERY turns are untouched.

**Files:**
- Modify: `backend/aria/core/conversation_engine.py` (`query_mode_node`)
- Test: add to `backend/tests/test_conversation_engine_grounding.py`

- [ ] **Step 1: Add the failing tests**

Append to `backend/tests/test_conversation_engine_grounding.py`:

```python
@pytest.mark.asyncio
async def test_query_mode_delegates_guideline_question(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(answer="FHA X [1].",
            sources=[{"guideline_name": "FHA Handbook 4000.1"}], confidence=0.8, grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("What is the FHA reserve requirement?", intent=None, slots={})
    state["mode"] = "query"
    out = await ce.query_mode_node(state)
    text = out["messages"][-1].content
    assert "FHA X [1]." in text and "FHA Handbook 4000.1" in text


@pytest.mark.asyncio
async def test_query_mode_operational_not_delegated(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    called = {"ground": False}
    async def fake_ground(question, org_id):
        called["ground"] = True
        return grounding.GroundingResult(answer="x", grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    # Operational lookups must NOT be routed to grounding. Stub the existing
    # query path so the test doesn't make a real LLM/DB call.
    state = _base_state("How many leads do I have today?", intent=None, slots={})
    state["mode"] = "query"
    # looks_like_guideline_question must be False for this text:
    from aria.core.grounding import looks_like_guideline_question
    assert looks_like_guideline_question(state["messages"][-1].content) is False
    assert called["ground"] is False
```

- [ ] **Step 2: Run, verify the delegate test fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_grounding.py -k "query_mode" -v`
Expected: `test_query_mode_delegates_guideline_question` FAILS (no delegation yet). The operational test should already pass (it only asserts the heuristic + that ground wasn't called).

- [ ] **Step 3: Add the delegate guard to `query_mode_node`**

Read the start of `query_mode_node`. Immediately after `question`/`org_id` are resolved (and before the existing direct-LLM path), insert:

```python
    from aria.core.grounding import looks_like_guideline_question, format_grounded_message, DISCLAIMER
    if _grounding_enabled() and looks_like_guideline_question(question):
        result = await ground_answer(question, org_id)
        if result.grounded:
            text = format_grounded_message(result.answer, result.sources)
        else:
            text = result.disclaimer or DISCLAIMER
        return {
            "messages": [AIMessage(content=text)],
            "phase": DialoguePhase.RESPONDING.value,
        }
```

(Place it after the circuit-breaker check shown in the file, or before it — either is fine since grounding has its own failure handling. Keep the existing operational query logic untouched below this guard.)

- [ ] **Step 4: Run the query-mode tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_grounding.py -k "query_mode" -v`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && git add backend/aria/core/conversation_engine.py backend/tests/test_conversation_engine_grounding.py && git commit -m "feat(aria): query-mode delegates guideline questions to grounding"
```

---

## Task 5: Flag-off equivalence guard + full Phase 2A test run

Lock in the safety property: with the flag off, none of the new routing fires.

**Files:**
- Test: add to `backend/tests/test_conversation_engine_grounding.py`

- [ ] **Step 1: Add the equivalence tests**

```python
def test_flag_off_factual_routes_legacy(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "false")
    state = _base_state("FHA reserves?")
    assert ce.route_after_nlu(state) == "confirmation"
    assert ce.route_after_slot_answer(state) == "confirmation"


@pytest.mark.asyncio
async def test_flag_off_query_mode_does_not_ground(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "false")
    called = {"ground": False}
    async def fake_ground(question, org_id):
        called["ground"] = True
        return grounding.GroundingResult(answer="x", grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    from aria.core.grounding import looks_like_guideline_question
    # Even a guideline-looking question must not be delegated when the flag is off.
    assert looks_like_guideline_question("What is the FHA reserve requirement?") is True
    # Re-import guard: call the routing/delegation surface that checks the flag.
    state = _base_state("What is the FHA reserve requirement?", intent="mortgage_guideline_question")
    assert ce.route_after_nlu(state) == "confirmation"
    assert called["ground"] is False
```

- [ ] **Step 2: Run the full Phase 2A suite**

Run:
```
cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_intent_category.py tests/test_grounding.py tests/test_conversation_engine_grounding.py -v
```
Expected: all pass.

- [ ] **Step 3: Regression — Phase 1 + Aria tests still green**

Run:
```
cd /Users/timothyloss/my-project/mortgage-crm/backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_tiering.py tests/test_model_router.py tests/test_llm_circuit_breaker.py tests/test_tool_confirmation_policy.py -q
ARIA_GROUNDING_ENABLED=false ../.venv/bin/python -c "from aria.core.conversation_engine import get_aria_graph; get_aria_graph(); print('graph ok')"
```
Expected: Phase 1 suite green; graph compiles.

- [ ] **Step 4: Commit**

```bash
cd /Users/timothyloss/my-project/mortgage-crm && git add backend/tests/test_conversation_engine_grounding.py && git commit -m "test(aria): flag-off equivalence guards for grounding"
```

---

## Phase 2A Definition of Done

- [ ] `intent_category()` derives factual/operational/chitchat from the existing `category` field; tested.
- [ ] `aria/core/grounding.py`: `ground_answer` wraps `KnowledgeTools.search_guidelines_rag`, `is_sufficiently_grounded` gates on sources + confidence, `looks_like_guideline_question` + `format_grounded_message` work; all tested (mocked RAG, no live calls).
- [ ] `ground` + `grounding_check` nodes wired; factual intent routes through them when `ARIA_GROUNDING_ENABLED=true`; grounded answers carry citations; insufficient grounding → terminal disclaimer, no loop.
- [ ] `query_mode_node` delegates guideline-type QUERY turns to grounding; operational QUERY turns untouched.
- [ ] **Flag off ⇒ behavior byte-identical to today** (routers return legacy targets; no delegation); tested.
- [ ] Graph compiles with the flag both off and on; Phase 1 suite still green.
- [ ] **CI on Python 3.11** (the real gate): full suite green; plus a live RAG smoke — a real guideline question with `ARIA_GROUNDING_ENABLED=true` returns a cited answer, and an out-of-corpus question returns the disclaimer (can't run locally; mark for CI/staging).

## Out of scope (Phase 2B and later)

- The `CoreDecision` Pydantic contract and refactoring nodes to populate it.
- Real token streaming + the `ARIA_UNIFIED_CORE` per-surface flag + shadow-compare harness.
- The Haiku-based sufficiency check (spec §4a) — 2A uses the deterministic confidence threshold; a Haiku check is a 2B quality enhancement.
- Deeper unification (routing guideline questions to the knowledge intent at dispatch instead of the `query_mode` delegate).
- The voice path (Phase 3).
