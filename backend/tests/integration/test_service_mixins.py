"""
Integration tests for the AIAgentService mixin decomposition.

Validates MRO + method exposure of:
  - SessionStateMixin    (_session.py)
  - ToolDispatchMixin    (_tools.py)
  - ResponseGenerationMixin (_response.py)
  - VoiceFormattingMixin (_voice.py)

The mixins are loaded individually via importlib so the test doesn't import
the heavy agents.service package (which would require Anthropic + LangGraph).
A trivial composite class is built from the four mixins to assert MRO shape.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Build a stub parent package graph so the mixin modules' relative imports
# (e.g. ``from ..orchestrator import run_orchestrator``) resolve to no-op
# stubs instead of the real heavy modules (LangGraph, Anthropic, etc.).
# ---------------------------------------------------------------------------

def _build_stub_packages() -> ModuleType:
    """Construct stub agents/* package modules with the minimal symbols the
    mixin modules import."""
    # Top-level stub package "_pa" mirroring backend/agents/
    pa = ModuleType("_pa")
    pa.__path__ = [str(_BACKEND_DIR / "agents")]
    sys.modules["_pa"] = pa

    # Stub _pa.orchestrator
    orchestrator = ModuleType("_pa.orchestrator")
    async def _run_orchestrator(*a, **kw):  # pragma: no cover
        return {}
    class _OrchestratorSession:  # pragma: no cover
        pass
    orchestrator.run_orchestrator = _run_orchestrator
    orchestrator.OrchestratorSession = _OrchestratorSession
    sys.modules["_pa.orchestrator"] = orchestrator

    # Stub _pa.state
    state = ModuleType("_pa.state")
    def _create_initial_state(*a, **kw):  # pragma: no cover
        return {}
    class _QueryIntent:  # pragma: no cover
        GENERAL = "general"
    state.create_initial_state = _create_initial_state
    state.QueryIntent = _QueryIntent
    sys.modules["_pa.state"] = state

    # Stub _pa.service_governance
    sg = ModuleType("_pa.service_governance")
    def _apply_post_response_governance(*a, **kw):  # pragma: no cover
        return {}
    sg.apply_post_response_governance = _apply_post_response_governance
    sys.modules["_pa.service_governance"] = sg

    # Stub _pa.anthropic_client
    ac = ModuleType("_pa.anthropic_client")
    def _get_anthropic_client():  # pragma: no cover
        return None
    def _get_async_anthropic_client():  # pragma: no cover
        return None
    ac.get_anthropic_client = _get_anthropic_client
    ac.get_async_anthropic_client = _get_async_anthropic_client
    sys.modules["_pa.anthropic_client"] = ac

    # Stub _pa.service (sub-package containing the mixins) with the constants
    # imported by _response.py via ``from . import VOICE_MODE_INSTRUCTIONS``.
    svc_pkg = ModuleType("_pa.service")
    svc_pkg.__path__ = [str(_BACKEND_DIR / "agents" / "service")]
    svc_pkg.VOICE_MODE_INSTRUCTIONS = ""
    def _summarize_tool_result_for_voice(name, result):  # pragma: no cover
        return ""
    svc_pkg._summarize_tool_result_for_voice = _summarize_tool_result_for_voice
    sys.modules["_pa.service"] = svc_pkg

    return svc_pkg


_svc_pkg = _build_stub_packages()


def _load_mixin(rel: str, mod_name: str):
    target = _BACKEND_DIR / rel
    if not target.exists():
        pytest.skip(f"{rel} missing")
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_mixin_as_submodule(rel: str, sub_name: str):
    """Load a mixin file as a submodule of the stub ``_pa.service`` package so
    its ``from ..orchestrator import ...`` relative imports resolve correctly.
    """
    target = _BACKEND_DIR / rel
    if not target.exists():
        pytest.skip(f"{rel} missing")
    full_name = f"_pa.service.{sub_name}"
    spec = importlib.util.spec_from_file_location(full_name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_session = _load_mixin_as_submodule("agents/service/_session.py", "_session")
_tools = _load_mixin_as_submodule("agents/service/_tools.py", "_tools")
_response = _load_mixin_as_submodule("agents/service/_response.py", "_response")
_voice = _load_mixin_as_submodule("agents/service/_voice.py", "_voice")


SessionStateMixin = _session.SessionStateMixin
ToolDispatchMixin = _tools.ToolDispatchMixin
ResponseGenerationMixin = _response.ResponseGenerationMixin
VoiceFormattingMixin = _voice.VoiceFormattingMixin


class _Composite(
    SessionStateMixin,
    ToolDispatchMixin,
    ResponseGenerationMixin,
    VoiceFormattingMixin,
):
    """Mirror the production composition order in AIAgentService."""

    def __init__(self):
        self.db = None
        self.current_user = None
        self.model = "test-model"
        self._tool_functions = {}
        self._tool_definitions = []
        self._prompt_service = None


# ---------------------------------------------------------------------------
# Test 1: MRO contains all four mixins in production order
# ---------------------------------------------------------------------------

def test_mro_includes_all_four_mixins_in_order():
    mro = _Composite.__mro__
    assert SessionStateMixin in mro
    assert ToolDispatchMixin in mro
    assert ResponseGenerationMixin in mro
    assert VoiceFormattingMixin in mro
    # Session must precede Tools (matches production AIAgentService base order)
    assert mro.index(SessionStateMixin) < mro.index(ToolDispatchMixin)


# ---------------------------------------------------------------------------
# Test 2: Each mixin instantiable as part of the composite
# ---------------------------------------------------------------------------

def test_composite_instantiable():
    instance = _Composite()
    assert instance.model == "test-model"
    assert instance._tool_functions == {}


# ---------------------------------------------------------------------------
# Test 3: SessionStateMixin.register_tool stores callable
# ---------------------------------------------------------------------------

def test_session_register_tool():
    instance = _Composite()
    async def my_tool(args):
        return {"ok": True}
    instance.register_tool("my_tool", my_tool)
    assert instance._tool_functions["my_tool"] is my_tool


# ---------------------------------------------------------------------------
# Test 4: SessionStateMixin.register_tools bulk-registers
# ---------------------------------------------------------------------------

def test_session_register_tools_bulk():
    instance = _Composite()
    tools = {"a": lambda x: x, "b": lambda x: x, "c": lambda x: x}
    instance.register_tools(tools)
    assert set(instance._tool_functions.keys()) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Test 5: SessionStateMixin.set_tool_definitions sets list
# ---------------------------------------------------------------------------

def test_session_set_tool_definitions():
    instance = _Composite()
    defs = [{"name": "tool_a"}, {"name": "tool_b"}]
    instance.set_tool_definitions(defs)
    assert instance._tool_definitions == defs


# ---------------------------------------------------------------------------
# Test 6: SessionStateMixin.set_model overrides model
# ---------------------------------------------------------------------------

def test_session_set_model():
    instance = _Composite()
    instance.set_model("claude-haiku-4-5-20251001")
    assert instance.model == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Test 7: SessionStateMixin.get_prompt_stats degrades gracefully when no service
# ---------------------------------------------------------------------------

def test_session_get_prompt_stats_no_service():
    instance = _Composite()
    instance._prompt_service = None
    stats = instance.get_prompt_stats()
    assert stats == {"status": "optimization_not_available"}


# ---------------------------------------------------------------------------
# Test 8: ToolDispatchMixin._get_tool_definitions exposed via composite
# ---------------------------------------------------------------------------

def test_tool_dispatch_method_exposed():
    instance = _Composite()
    assert hasattr(instance, "_get_tool_definitions")
    assert callable(instance._get_tool_definitions)


# ---------------------------------------------------------------------------
# Test 9: ToolDispatchMixin._execute_tool exposed via composite
# ---------------------------------------------------------------------------

def test_tool_dispatch_execute_exposed():
    instance = _Composite()
    assert hasattr(instance, "_execute_tool")
    # _execute_tool is async; just verify the attribute exists
    import inspect
    assert inspect.iscoroutinefunction(instance._execute_tool)


# ---------------------------------------------------------------------------
# Test 10: ResponseGenerationMixin async methods exposed
# ---------------------------------------------------------------------------

def test_response_generation_methods_exposed():
    instance = _Composite()
    import inspect
    # process_message is a coroutine function
    assert inspect.iscoroutinefunction(instance.process_message)
    # process_message_stream + chat_streaming are async generator functions
    assert inspect.isasyncgenfunction(instance.process_message_stream)
    assert inspect.isasyncgenfunction(instance.chat_streaming)


# ---------------------------------------------------------------------------
# Test 11: VoiceFormattingMixin._split_response_for_streaming works
# ---------------------------------------------------------------------------

def test_voice_split_response_for_streaming():
    instance = _Composite()
    # The splitter takes a string and returns a list of utterances.
    parts = instance._split_response_for_streaming("Hello. How are you? I am fine.")
    assert isinstance(parts, list)
    assert len(parts) >= 1
    # Joining the parts back should preserve the original content (modulo whitespace)
    joined = " ".join(parts).strip()
    assert "Hello" in joined
    assert "fine" in joined


# ---------------------------------------------------------------------------
# Test 12: Tenant constraint injection appends to system prompt
# ---------------------------------------------------------------------------

def test_session_inject_tenant_constraints():
    instance = _Composite()

    class _User:
        id = 1
        organization_id = 42
        organization_name = "Acme Lending"
        permission_role = "loan_officer"
        first_name = "Alex"
        name = "Alex Doe"

    instance.current_user = _User()
    out = instance._inject_tenant_constraints("BASE PROMPT")
    assert out.startswith("BASE PROMPT")
    assert "Acme Lending" in out
    assert "42" in out
    assert "Tenant Isolation" in out
