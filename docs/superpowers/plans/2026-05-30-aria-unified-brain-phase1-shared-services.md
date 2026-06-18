# Aria Unified Brain — Phase 1: Shared Services Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared services every later phase depends on — a `ModelRouter` (Haiku/Sonnet tiering), one shared `LLMCircuitBreaker`, and default-deny confirmation metadata on `ToolDefinition` — then bank the lowest-risk cost/latency win by tiering the chat engine's classification nodes to Haiku.

**Architecture:** Pure additive/extraction work, no new dialogue behavior. Three new/extracted shared modules under `agents/orchestration/` and `agents/tools/`, then a behavior-preserving rewire of `aria/core/conversation_engine.py` to route classification-class LLM calls (NLU, slot-fill, slot-answer, confirmation) through Haiku while the chitchat/response node stays on Sonnet. No feature flag needed for Phase 1 because the tiering change is capability-equivalent (classification tasks) and independently revertable by one commit.

**Tech Stack:** Python 3.11, `langchain_anthropic.ChatAnthropic`, pytest, FastAPI/LangGraph (existing). Models: `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`.

**Spec:** `docs/superpowers/specs/2026-05-30-aria-unified-brain-design.md` (v2), §3 (tiering), §5 (registry flags), §6 (tenant assert primitives), §7 (one circuit breaker), §8 step 1.

**Deviation from spec §8 step 1 (flagged):** the interim Haiku win is applied to the **chat `conversation_engine` classification nodes**, not the voice agent. Voice's `livekit.plugins.anthropic.LLM` is the streaming spoken-response model and must stay Sonnet for output quality; its classification work happens server-side via the same backend the chat engine uses. Same cost/latency win, no risk to the LiveKit worker.

---

## File Structure

- `agents/orchestration/model_router.py` — **NEW.** `ModelRouter`: returns cached `ChatAnthropic` clients per tier (`"haiku"`/`"sonnet"`), env-configurable, breaker-aware. One responsibility: pick + build the LLM client for a tier.
- `agents/orchestration/llm_circuit_breaker.py` — **NEW.** `LLMCircuitBreaker` + `CircuitState`: the canonical breaker extracted from `agents/orchestrator.py`. Single source of truth for breaker logic.
- `agents/tools/base.py` — **MODIFY.** Add `side_effect` + `surface_constraints` to `ToolDefinition`; add `requires_confirmation_for(name)` default-deny helper.
- `agents/orchestrator.py` — **MODIFY.** Import the shared breaker instead of its local `CircuitBreaker` class (delete the local copy).
- `aria/core/conversation_engine.py` — **MODIFY.** Import the shared breaker; make `_get_llm(tier)` delegate to `ModelRouter`; route NLU/slot/confirmation call sites to Haiku.
- Tests: `tests/test_model_router.py`, `tests/test_llm_circuit_breaker.py`, `tests/test_tool_confirmation_policy.py`, `tests/test_conversation_engine_tiering.py` — **NEW.**

---

## Pre-flight (before Task 1)

Run once, before any task, to establish the baseline the whole phase is judged against (DevOps + Performance asks from review).

- [ ] **P1: Confirm the venv path resolves from `backend/`**

Run: `cd backend && ../.venv/bin/python --version`
Expected: prints a Python 3.11.x version. If it errors, find the correct interpreter (`which python3` inside the project venv) and substitute it in every `../.venv/bin/python` command below.

- [ ] **P2: Full-suite baseline (not the filtered subsets)**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q 2>&1 | tail -20`
Record the pass/fail/error counts. This is the baseline; Phase 1 must not introduce new failures vs. this run. (Filtered `-k` runs inside tasks are fast gates; this full run is the real regression check.)

- [ ] **P3: Capture a pre-change latency/cost sample (Performance)**

On staging (or a dev shell with Anthropic creds), send ~10 representative chat turns through the existing `conversation_engine` and record total tokens + wall-clock per turn for the NLU/slot/confirmation path. Save the numbers in the PR description. After Task 5, re-sample the same turns to confirm the projected ~5× cost / ~2× latency improvement on those nodes (and to catch quality-driven retries). If a live sample isn't feasible, at minimum confirm `model_tier` is logged by `ModelRouter` so the comparison can be done from logs post-deploy.

---

## Task 1: Shared `LLMCircuitBreaker` (extraction)

Extract the canonical breaker (currently duplicated in `agents/orchestrator.py` as `CircuitBreaker` and in `aria/core/conversation_engine.py` as `_AriaCircuitBreaker`) into one module. Behavior is identical to the existing `agents/orchestrator.py` version.

**Files:**
- Create: `backend/agents/orchestration/llm_circuit_breaker.py`
- Test: `backend/tests/test_llm_circuit_breaker.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_circuit_breaker.py
import time
import pytest
from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker, CircuitState


def test_starts_closed_and_allows():
    cb = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold_failures():
    cb = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_half_open_after_cooldown_then_closes_on_success():
    cb = LLMCircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_probe_failure_reopens():
    cb = LLMCircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_llm_circuit_breaker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.orchestration.llm_circuit_breaker'`

- [ ] **Step 3: Write the module**

```python
# backend/agents/orchestration/llm_circuit_breaker.py
"""
Shared LLM circuit breaker.

Single source of truth, extracted from agents/orchestrator.py (CircuitBreaker)
and aria/core/conversation_engine.py (_AriaCircuitBreaker), which were identical.
Thread-safe; fast-fails LLM calls during Anthropic outages.
"""
import logging
import threading
import time as _time_module
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LLMCircuitBreaker:
    """Thread-safe circuit breaker for LLM API calls."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0, name: str = "llm"):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = _time_module.monotonic() - self._last_failure_time
                if elapsed >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning("[CIRCUIT-BREAKER:%s] OPEN -> HALF_OPEN (cooldown %.1fs elapsed)",
                                   self.name, self.cooldown_seconds)
            return self._state

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        with self._lock:
            prev = self._state
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            if prev != CircuitState.CLOSED:
                logger.warning("[CIRCUIT-BREAKER:%s] %s -> CLOSED (success)", self.name, prev.value)

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = _time_module.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("[CIRCUIT-BREAKER:%s] HALF_OPEN -> OPEN (probe failed)", self.name)
            elif (self._state == CircuitState.CLOSED
                  and self._consecutive_failures >= self.failure_threshold):
                self._state = CircuitState.OPEN
                logger.warning("[CIRCUIT-BREAKER:%s] CLOSED -> OPEN (%d consecutive failures)",
                               self.name, self._consecutive_failures)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_llm_circuit_breaker.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/orchestration/llm_circuit_breaker.py backend/tests/test_llm_circuit_breaker.py
git commit -m "feat(aria): extract shared LLMCircuitBreaker"
```

---

## Task 2: Rewire `orchestrator.py` to the shared breaker

Replace the local `CircuitBreaker` class in `agents/orchestrator.py` with an import of the shared one. Pure de-duplication; behavior identical.

**Files:**
- Modify: `backend/agents/orchestrator.py` (the `CircuitState`/`CircuitBreaker` block, ~lines 54-150)

- [ ] **Step 1: Run the existing orchestrator import smoke test to establish a baseline**

Run: `cd backend && ../.venv/bin/python -c "import agents.orchestrator; print('ok')"`
Expected: prints `ok`

- [ ] **Step 2: Delete the local breaker classes and import the shared one**

In `backend/agents/orchestrator.py`, delete the local `class CircuitState(Enum):` and `class CircuitBreaker:` definitions (the block from `class CircuitState(Enum):` through the end of `CircuitBreaker.record_failure`). Replace with an import near the other orchestration imports at the top of the file:

```python
from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker, CircuitState
```

Then update the module-level instance line:

```python
# was: _llm_circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
_llm_circuit_breaker = LLMCircuitBreaker(failure_threshold=5, cooldown_seconds=30.0, name="orchestrator")
```

Leave `_get_circuit_breaker()` and all call sites unchanged — they reference `_llm_circuit_breaker`, whose public API (`state`, `allow_request`, `record_success`, `record_failure`) is identical.

- [ ] **Step 3: Verify import and that no symbol is dangling**

Run: `cd backend && ../.venv/bin/python -c "import agents.orchestrator as o; print(type(o._llm_circuit_breaker).__name__); print(o.CircuitState.CLOSED)"`
Expected: prints `LLMCircuitBreaker` then `CircuitState.CLOSED`

- [ ] **Step 4: Run the orchestrator-touching tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -k "orchestrat or circuit" -v`
Expected: PASS (no regressions); if no tests match, the import check in Step 3 is the gate.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/orchestrator.py
git commit -m "refactor(aria): orchestrator uses shared LLMCircuitBreaker"
```

---

## Task 3: `ModelRouter` with tiering

A single place that maps a tier name to a configured, cached `ChatAnthropic` client. Reads `ANTHROPIC_MODEL` (Sonnet default) and `ARIA_HAIKU_MODEL` (Haiku default) so models are tunable without code change (§3).

**Files:**
- Create: `backend/agents/orchestration/model_router.py`
- Test: `backend/tests/test_model_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_model_router.py
import pytest
from agents.orchestration.model_router import ModelRouter


def test_haiku_tier_uses_haiku_model(monkeypatch):
    monkeypatch.delenv("ARIA_HAIKU_MODEL", raising=False)
    r = ModelRouter()
    client = r.get("haiku")
    assert "haiku" in client.model.lower()


def test_sonnet_tier_uses_sonnet_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    r = ModelRouter()
    client = r.get("sonnet")
    assert "sonnet" in client.model.lower()


def test_env_overrides_model_id(monkeypatch):
    monkeypatch.setenv("ARIA_HAIKU_MODEL", "claude-haiku-4-5-20251001")
    r = ModelRouter()
    assert r.get("haiku").model == "claude-haiku-4-5-20251001"


def test_clients_are_cached(monkeypatch):
    r = ModelRouter()
    assert r.get("haiku") is r.get("haiku")


def test_unknown_tier_raises():
    r = ModelRouter()
    with pytest.raises(ValueError):
        r.get("turbo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_model_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.orchestration.model_router'`

- [ ] **Step 3: Write the module**

```python
# backend/agents/orchestration/model_router.py
"""
ModelRouter — single source for tier -> LLM client mapping.

Tiers:
  "haiku"  — classification/extraction/routing (cheap, fast)
  "sonnet" — open-ended reasoning and final responses

Model ids are env-tunable:
  ANTHROPIC_MODEL   (default claude-sonnet-4-6)
  ARIA_HAIKU_MODEL  (default claude-haiku-4-5-20251001)
"""
import os
import logging
from typing import Dict

from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)

_SONNET_DEFAULT = "claude-sonnet-4-6"
_HAIKU_DEFAULT = "claude-haiku-4-5-20251001"


class ModelRouter:
    """Maps a tier name to a cached, configured ChatAnthropic client."""

    def __init__(self, temperature: float = 0.3, max_tokens: int = 1024):
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._cache: Dict[str, ChatAnthropic] = {}

    def _model_id(self, tier: str) -> str:
        if tier == "haiku":
            return os.getenv("ARIA_HAIKU_MODEL", _HAIKU_DEFAULT)
        if tier == "sonnet":
            return os.getenv("ANTHROPIC_MODEL", _SONNET_DEFAULT)
        raise ValueError(f"Unknown model tier: {tier!r} (expected 'haiku' or 'sonnet')")

    def get(self, tier: str) -> ChatAnthropic:
        if tier not in self._cache:
            model_id = self._model_id(tier)
            self._cache[tier] = ChatAnthropic(
                model=model_id,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            logger.info("[MODEL-ROUTER] tier=%s -> %s", tier, model_id)
        return self._cache[tier]


# Module-level shared router (mirrors the circuit-breaker singleton pattern).
_router = ModelRouter()


def get_model_router() -> ModelRouter:
    return _router
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_model_router.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/orchestration/model_router.py backend/tests/test_model_router.py
git commit -m "feat(aria): ModelRouter for Haiku/Sonnet tiering"
```

---

## Task 4: Default-deny confirmation policy on `ToolDefinition`

`ToolDefinition` (`agents/tools/base.py:527`) already has `requires_confirmation: bool = False` and `risk_level: str = "low"`. Add `side_effect` and `surface_constraints`, and a `requires_confirmation_for(name)` helper that is **default-deny**: any side-effecting, high/critical-risk, explicitly-flagged, or *unknown* tool requires confirmation (§5, §6).

**Files:**
- Modify: `backend/agents/tools/base.py` (the `@dataclass class ToolDefinition` at ~527, and add a module-level helper after the `ToolRegistry` class)
- Test: `backend/tests/test_tool_confirmation_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tool_confirmation_policy.py
import pytest
from agents.tools.base import ToolDefinition, ToolRegistry, requires_confirmation_for


def _td(**kw):
    base = dict(func=lambda **_: None, name="t", description="d", agent_roles=["x"])
    base.update(kw)
    return ToolDefinition(**base)


def test_new_fields_default_safe():
    td = _td()
    assert td.side_effect is False
    assert td.surface_constraints == []


def test_explicit_requires_confirmation_true():
    assert requires_confirmation_for(_td(name="a", requires_confirmation=True)) is True


def test_side_effect_requires_confirmation():
    assert requires_confirmation_for(_td(name="b", side_effect=True)) is True


def test_high_risk_requires_confirmation():
    assert requires_confirmation_for(_td(name="c", risk_level="high")) is True


def test_readonly_low_risk_does_not_require():
    assert requires_confirmation_for(_td(name="d", risk_level="low")) is False


def test_unknown_tool_name_defaults_to_require():
    # default-deny: a name not in the registry is treated as needing confirmation
    assert requires_confirmation_for("a_tool_that_does_not_exist") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tool_confirmation_policy.py -v`
Expected: FAIL — `ImportError: cannot import name 'requires_confirmation_for'` (and `side_effect`/`surface_constraints` unknown)

- [ ] **Step 3: Add the fields to `ToolDefinition`**

In `backend/agents/tools/base.py`, in the `@dataclass class ToolDefinition`, add two fields after `requires_confirmation: bool = False`:

```python
    requires_confirmation: bool = False
    side_effect: bool = False
    surface_constraints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Add the default-deny helper**

After the `class ToolRegistry:` definition in the same file, add:

```python
_HIGH_RISK_LEVELS = {"high", "critical"}


def requires_confirmation_for(tool_or_name) -> bool:
    """
    Default-deny confirmation policy (spec §5/§6).

    Returns True (confirmation required) when the tool is side-effecting,
    high/critical risk, explicitly flagged, OR unknown. Read-only, low-risk,
    known tools return False.

    Accepts a ToolDefinition or a tool name (str). An unrecognised name is
    treated as requiring confirmation — fail safe.
    """
    if isinstance(tool_or_name, str):
        td = ToolRegistry().get(tool_or_name)
        if td is None:
            return True  # unknown -> default-deny
    else:
        td = tool_or_name
    if td.requires_confirmation or td.side_effect:
        return True
    if (td.risk_level or "").lower() in _HIGH_RISK_LEVELS:
        return True
    return False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tool_confirmation_policy.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Verify the registry still imports (210+ tools register at import)**

Run: `cd backend && ../.venv/bin/python -c "from agents.tools.base import ToolRegistry; import agents.tools; print(len(ToolRegistry()))"`
Expected: prints a positive integer (existing tool count), no exceptions

- [ ] **Step 7: Commit**

```bash
git add backend/agents/tools/base.py backend/tests/test_tool_confirmation_policy.py
git commit -m "feat(aria): define default-deny confirmation policy (not yet enforced)

Adds requires_confirmation_for() + side_effect/surface_constraints. This is
the policy definition only; the confirm gate that consumes it lands in Phase 2.
No change to confirmation behavior ships in Phase 1."
```

> **Security note (review):** this task defines the policy but **nothing calls `requires_confirmation_for()` yet** — the confirm gate is Phase 2. Phase 1 ships zero change to confirmation behavior. Do not describe it as "hardened confirmations."

---

## Task 5: Tier chat classification nodes to Haiku (interim win)

Rewire `aria/core/conversation_engine.py` so classification-class LLM calls use Haiku via `ModelRouter`, while the chitchat/response node stays Sonnet. Also swap its duplicate `_AriaCircuitBreaker` for the shared breaker. Capability-equivalent for classification; large cost/latency win.

**Files:**
- Modify: `backend/aria/core/conversation_engine.py` (the `_AriaCircuitBreaker` block ~62-148, `_get_llm()` ~152-164, and the call sites in `nlu_node`, `slot_fill_node`, `slot_answer_node`, `confirmation_node`)
- Test: `backend/tests/test_conversation_engine_tiering.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_conversation_engine_tiering.py
from aria.core import conversation_engine as ce


def test_get_llm_haiku_tier_returns_haiku_model():
    client = ce._get_llm("haiku")
    assert "haiku" in client.model.lower()


def test_get_llm_default_is_sonnet():
    client = ce._get_llm()
    assert "sonnet" in client.model.lower()


def test_uses_shared_circuit_breaker():
    from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker
    assert isinstance(ce._circuit_breaker, LLMCircuitBreaker)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_tiering.py -v`
Expected: FAIL — `_get_llm()` takes no args / `_circuit_breaker` is `_AriaCircuitBreaker`

- [ ] **Step 3: Replace the duplicate breaker with the shared one**

In `backend/aria/core/conversation_engine.py`, delete the local `class _CircuitState(...)` and `class _AriaCircuitBreaker:` definitions (~lines 66-147) and add an import near the top:

```python
from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker
```

Replace the instance line:

```python
# was: _circuit_breaker = _AriaCircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
_circuit_breaker = LLMCircuitBreaker(failure_threshold=5, cooldown_seconds=30.0, name="aria-chat")
```

(All `_circuit_breaker.allow_request()/record_success()/record_failure()` call sites are unchanged — identical API.)

- [ ] **Step 4: Make `_get_llm` tier-aware via ModelRouter**

Replace the `_get_llm` function (~152-164):

```python
from agents.orchestration.model_router import get_model_router

def _get_llm(tier: str = "sonnet"):
    """Return the tier-appropriate LLM client.

    'haiku' for classification/extraction nodes (NLU, slot-fill, confirmation),
    'sonnet' for the chitchat/response node. Default sonnet preserves prior
    behavior for any unmodified caller.
    """
    return get_model_router().get(tier)
```

- [ ] **Step 5: Route classification call sites to Haiku**

In `backend/aria/core/conversation_engine.py`, in each of `nlu_node`, `slot_fill_node`, `slot_answer_node`, and `confirmation_node`, change the LLM acquisition from `_get_llm()` to `_get_llm("haiku")`. The response/chitchat node (`response_node`) keeps `_get_llm()` (Sonnet). Each call currently looks like:

```python
# before
_get_llm().ainvoke([...])
# after
_get_llm("haiku").ainvoke([...])
```

Apply to exactly the four classification nodes; leave `response_node` untouched.

- [ ] **Step 6: Run the tiering tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_conversation_engine_tiering.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the existing Aria chat/retrieval tests for regressions**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -k "aria and (chat or retrieval or config or consolidation)" -v`
Expected: PASS / no new failures vs. a pre-change baseline. If a test asserts a specific Sonnet model id on a classification node, update it to expect Haiku (that is the intended change) and note it in the commit.

- [ ] **Step 8: Verify the graph still compiles and imports**

Run: `cd backend && ../.venv/bin/python -c "from aria.core.conversation_engine import get_aria_graph; get_aria_graph(); print('graph ok')"`
Expected: prints `graph ok`

- [ ] **Step 9: Commit**

```bash
git add backend/aria/core/conversation_engine.py backend/tests/test_conversation_engine_tiering.py
git commit -m "perf(aria): tier chat classification nodes to Haiku; shared circuit breaker"
```

---

## Phase 1 Definition of Done

- [ ] `ModelRouter`, `LLMCircuitBreaker` exist with passing unit tests.
- [ ] `agents/orchestrator.py` and `aria/core/conversation_engine.py` both import the shared breaker; no duplicate breaker classes remain.
- [ ] `ToolDefinition` has `side_effect` + `surface_constraints`; `requires_confirmation_for()` is default-deny with passing tests. **(Policy defined, not yet enforced — Phase 2 wires the gate.)**
- [ ] Chat NLU/slot/confirmation nodes run on Haiku; chitchat/response stays Sonnet; graph compiles; existing Aria tests green.
- [ ] **Full-suite re-run after Task 5** (`cd backend && ../.venv/bin/python -m pytest tests/ -q`) shows no new failures vs. the Pre-flight P2 baseline.
- [ ] **NLU-on-Haiku correctness smoke (QA):** at least one integration-level check that a representative user message still resolves to the correct intent on Haiku (live LLM; staging or manual is acceptable). Wiring tests prove the model id; this proves the cheaper model still understands the user.
- [ ] **Before/after numbers captured (Performance):** the P3 sample re-run, with token-cost and latency deltas recorded in the PR description (or the log-based comparison if a live sample wasn't feasible).
- [ ] All five commits landed on the branch.

## Out of scope (later phases, own plans)

- Phase 2: decision core + `CoreDecision` contract + chat transport behind `ARIA_UNIFIED_CORE=chat`.
- Phase 3: voice transport on the core; registry-backed voice tool wrappers; tenant propagation from LiveKit token; `act` `TenantIsolationError` hard-assert.
- Phase 4: retire `agents/orchestrator.py` as a separate brain.
- Phase 5: delete `aria/tools/*` duplicates after parity harness green + flag at 100% for two weeks.
