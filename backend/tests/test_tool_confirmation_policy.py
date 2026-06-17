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
    # default-deny: a name not in the registry is treated as needing confirmation.
    # Use a collision-proof name so a future registration can't silently turn this
    # into a test of a registered tool's policy (ToolRegistry is a singleton).
    assert requires_confirmation_for("__no_such_tool_xyzzy_98f3c1__") is True
