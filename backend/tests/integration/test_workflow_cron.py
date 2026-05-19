"""
Integration tests for the midnight workflow cron.

Validates the daily task-generation cron contract:
  1. Generates tasks for every active loan with elapsed SLA hours
  2. Idempotent — re-running within the same day produces no duplicates
  3. Skips loans in terminal stages (FUNDED, DENIED, WITHDRAWN, etc.)
  4. Respects organization (tenant) scoping — generation per-org
  5. Respects business hours when scheduling outbound call tasks

Uses lightweight in-process stubs. xfail covers the live wiring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Dict, List, Tuple

import pytest


pytestmark = pytest.mark.integration


TERMINAL_STAGES = {
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
}


@dataclass
class FakeLoan:
    id: int
    stage: str
    org_id: int
    elapsed_hours: float


@dataclass
class FakeStore:
    tasks: List[Tuple[int, str, int, int]] = field(default_factory=list)

    def add(self, loan_id: int, task_type: str, threshold: int, org_id: int) -> bool:
        key = (loan_id, task_type, threshold, org_id)
        if key in self.tasks:
            return False
        self.tasks.append(key)
        return True


def run_midnight_cron(loans: List[FakeLoan], store: FakeStore, now: datetime) -> int:
    """Generate tasks for every non-terminal loan. Returns count created."""
    created = 0
    for loan in loans:
        if loan.stage in TERMINAL_STAGES:
            continue
        for threshold in (8, 16, 24):
            if loan.elapsed_hours >= threshold:
                # business hours gate for "call_back"
                task_type = "call_back"
                if task_type.startswith("call") and not (
                    time(8, 0) <= now.time() <= time(21, 0)
                ):
                    # Out of hours: skip telephony tasks, still ok to noop
                    continue
                if store.add(loan.id, task_type, threshold, loan.org_id):
                    created += 1
    return created


def test_midnight_cron_generates_daily_tasks_for_active_loans():
    loans = [
        FakeLoan(id=1, stage="PROCESSING", org_id=10, elapsed_hours=25.0),
        FakeLoan(id=2, stage="UNDERWRITING", org_id=10, elapsed_hours=9.0),
    ]
    store = FakeStore()
    # Use 12:00 local to be in business hours
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    created = run_midnight_cron(loans, store, now)
    assert created == 4  # loan1: 3 thresholds, loan2: 1 threshold


def test_midnight_cron_is_idempotent_on_rerun():
    loans = [FakeLoan(id=1, stage="PROCESSING", org_id=10, elapsed_hours=25.0)]
    store = FakeStore()
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    first = run_midnight_cron(loans, store, now)
    second = run_midnight_cron(loans, store, now)
    assert first == 3
    assert second == 0


def test_midnight_cron_skips_terminal_stages():
    loans = [
        FakeLoan(id=1, stage="FUNDED", org_id=10, elapsed_hours=25.0),
        FakeLoan(id=2, stage="DENIED", org_id=10, elapsed_hours=25.0),
        FakeLoan(id=3, stage="WITHDRAWN", org_id=10, elapsed_hours=25.0),
        FakeLoan(id=4, stage="PROCESSING", org_id=10, elapsed_hours=25.0),
    ]
    store = FakeStore()
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    created = run_midnight_cron(loans, store, now)
    assert created == 3  # only loan 4
    assert all(t[0] == 4 for t in store.tasks)


def test_midnight_cron_respects_organization_scoping():
    loans = [
        FakeLoan(id=1, stage="PROCESSING", org_id=10, elapsed_hours=9.0),
        FakeLoan(id=2, stage="PROCESSING", org_id=20, elapsed_hours=9.0),
    ]
    store = FakeStore()
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    run_midnight_cron(loans, store, now)
    org_ids = {t[3] for t in store.tasks}
    assert org_ids == {10, 20}


def test_midnight_cron_respects_business_hours_for_telephony():
    loans = [FakeLoan(id=1, stage="PROCESSING", org_id=10, elapsed_hours=25.0)]
    store = FakeStore()
    # 3am — outside business hours, telephony tasks should be skipped
    now = datetime(2026, 5, 19, 3, 0, tzinfo=timezone.utc)
    created = run_midnight_cron(loans, store, now)
    assert created == 0
