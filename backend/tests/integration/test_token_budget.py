"""
Integration tests for `agents/orchestration/token_budget.py`.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_budget():
    target = _BACKEND_DIR / "agents" / "orchestration" / "token_budget.py"
    if not target.exists():
        pytest.skip("token_budget.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_token_budget", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_tb = _load_budget()
TokenBudgetManager = _tb.TokenBudgetManager


# ---------------------------------------------------------------------------
# 1. Default budget enforced
# ---------------------------------------------------------------------------

def test_default_budget_applied():
    m = TokenBudgetManager(default_budget_tokens=1000)
    snap = m.get_usage("agent_x")
    assert snap["budget"] == 1000
    assert snap["tokens_used"] == 0


# ---------------------------------------------------------------------------
# 2. Per-agent override
# ---------------------------------------------------------------------------

def test_per_agent_override_applied():
    m = TokenBudgetManager(
        default_budget_tokens=1000,
        per_agent_overrides={"big_agent": 50_000},
    )
    assert m.get_usage("big_agent")["budget"] == 50_000
    assert m.get_usage("other_agent")["budget"] == 1000


# ---------------------------------------------------------------------------
# 3. 80% warning logged (captured via caplog)
# ---------------------------------------------------------------------------

def test_80pct_warning_logged(caplog):
    import logging

    m = TokenBudgetManager(default_budget_tokens=100)
    m.record_usage("agent_z", 70, 0)
    with caplog.at_level(logging.WARNING):
        ok = m.check_and_reserve("agent_z", 15)  # 70+15=85 → >80%
    assert ok is True
    assert any("utilization" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# 4. Reset on day rollover (reset_daily wipes state)
# ---------------------------------------------------------------------------

def test_reset_daily_wipes_state():
    m = TokenBudgetManager(default_budget_tokens=1000)
    m.record_usage("a", 500, 0)
    assert m.get_usage("a")["tokens_used"] == 500
    m.reset_daily()
    assert m.get_usage("a")["tokens_used"] == 0


# ---------------------------------------------------------------------------
# 5. Concurrent usage thread-safe
# ---------------------------------------------------------------------------

def test_concurrent_record_usage_thread_safe():
    m = TokenBudgetManager(default_budget_tokens=10_000_000)

    def writer():
        for _ in range(50):
            m.record_usage("shared", 10, 0)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.get_usage("shared")["tokens_used"] == 8 * 50 * 10


# ---------------------------------------------------------------------------
# 6. check_and_reserve False past budget
# ---------------------------------------------------------------------------

def test_check_and_reserve_false_when_over_budget():
    m = TokenBudgetManager(default_budget_tokens=100)
    m.record_usage("a", 90, 0)
    assert m.check_and_reserve("a", 50) is False


# ---------------------------------------------------------------------------
# 7. get_usage shape
# ---------------------------------------------------------------------------

def test_get_usage_returns_expected_shape():
    m = TokenBudgetManager(default_budget_tokens=1000)
    snap = m.get_usage("any_agent")
    assert set(snap.keys()) == {
        "tokens_used",
        "tokens_remaining",
        "pct_utilization",
        "budget",
    }


# ---------------------------------------------------------------------------
# 8. record_usage with zero delta is a no-op
# ---------------------------------------------------------------------------

def test_record_usage_zero_delta_noop():
    m = TokenBudgetManager(default_budget_tokens=1000)
    m.record_usage("z", 0, 0)
    assert m.get_usage("z")["tokens_used"] == 0
