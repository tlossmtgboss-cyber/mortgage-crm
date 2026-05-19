"""
Important Dates Consolidated Model — Perennia AI

Provides a unified ImportantDatesMixin that consolidates milestone date
columns across Lead/Loan/Client profiles. Mixin is additive — applies only
columns that are not already present on the host model (idempotent).

Why:
- Pre-consolidation, milestone dates were scattered across legacy fields
  (application_date, conditional_approval_date, funded_date, etc.) with no
  single authoritative shape. The SLA tracking engine and workflow task
  engine both need a deterministic, indexed surface to read milestone
  dates from.

Use:
- Inherit on Loan / Lead / ClientProfile models *or* call
  `apply_important_dates_columns(cls)` post-definition to add any missing
  date columns without overriding existing ones.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Tuple

from sqlalchemy import Column, DateTime, Index


# Canonical list of (column_name, indexed) for milestone dates.
# Order matters: this defines the canonical milestone progression used by
# get_next_due_milestone() in the helper service.
IMPORTANT_DATE_COLUMNS: Tuple[Tuple[str, bool], ...] = (
    ("new_lead_date", True),
    ("application_date", True),
    ("disclosed_date", True),
    ("processing_date", True),
    ("submitted_date", True),
    ("uw_submission_date", True),
    ("conditional_approval_date", True),
    ("approved_date", True),
    ("ctc_date", True),
    ("clear_to_close_date", True),
    ("docs_out_date", True),
    ("closing_date", True),
    ("funded_date", True),
)


def _make_column(indexed: bool) -> Column:
    return Column(DateTime(timezone=True), nullable=True, index=indexed)


class ImportantDatesMixin:
    """
    Unified mixin for milestone date tracking. Idempotent — column attributes
    are only assigned on the subclass if not already declared, so this is safe
    to add to existing models that already declare some of these fields.

    Inheritance order should put this mixin BEFORE `Base` in the MRO::

        class Loan(ImportantDatesMixin, Base):
            ...
    """

    new_lead_date = _make_column(True)
    application_date = _make_column(True)
    disclosed_date = _make_column(True)
    processing_date = _make_column(True)
    submitted_date = _make_column(True)
    uw_submission_date = _make_column(True)
    conditional_approval_date = _make_column(True)
    approved_date = _make_column(True)
    ctc_date = _make_column(True)
    clear_to_close_date = _make_column(True)
    docs_out_date = _make_column(True)
    closing_date = _make_column(True)
    funded_date = _make_column(True)

    def get_important_dates(self) -> dict:
        """Return a dict of milestone_name -> datetime|None for this row."""
        out: dict = {}
        for name, _idx in IMPORTANT_DATE_COLUMNS:
            out[name] = getattr(self, name, None)
        return out


def apply_important_dates_columns(model_cls) -> Iterable[str]:
    """
    Post-declaration helper that adds any missing milestone columns to
    ``model_cls`` without overriding existing ones. Yields the names of
    columns it added (useful for logging / migrations).

    NOTE: SQLAlchemy 2.0 mapping prefers declaring columns at class-creation
    time, so the preferred path is to mix in ``ImportantDatesMixin``. This
    function exists for runtime migrations where re-declaring the model is
    not feasible.
    """
    added = []
    table = getattr(model_cls, "__table__", None)
    if table is None:
        return added
    for name, indexed in IMPORTANT_DATE_COLUMNS:
        if name in table.c:
            continue
        col = Column(name, DateTime(timezone=True), nullable=True)
        col._creation_order = Column.__visit_name__  # type: ignore[attr-defined]
        try:
            table.append_column(col)
            if indexed:
                Index(f"ix_{table.name}_{name}", col)
            added.append(name)
        except Exception:
            # Idempotent — if append fails (e.g., already attached), skip.
            continue
    return added


def utc_now() -> datetime:
    """Tz-aware now() helper used by the service layer."""
    return datetime.now(timezone.utc)


__all__ = [
    "ImportantDatesMixin",
    "IMPORTANT_DATE_COLUMNS",
    "apply_important_dates_columns",
    "utc_now",
]
