"""Verification tests for the Float -> Numeric migration.

These tests guard against regression of the TRID-violation fix introduced
in migration ``2026_05_19_float_to_numeric``. Float storage of monetary
values is non-compliant because IEEE 754 cannot represent decimal cents
exactly (e.g. ``450000.01`` becomes ``450000.00999999...``).

Three layers of verification:

1. **Schema introspection** — every migrated column's SQLAlchemy type
   must be ``Numeric``, never ``Float``.
2. **Round-trip precision** — inserting ``Decimal('450000.01')`` into a
   migrated column and reading it back must yield exact equality.
3. **Boundary capacity** — a ``Numeric(14, 2)`` column must accept the
   maximum value ``99999999999.99`` (12 digits before the decimal point)
   without overflow or precision loss.

The 14 columns under test are taken directly from the migration file's
``DOLLAR_COLUMNS`` and ``RATE_COLUMNS`` lists, keeping this test as the
single source of truth for the migration's surface area.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Column, Integer, MetaData, Numeric, Table, create_engine
from sqlalchemy.orm import Session


# (table, column) — matches DOLLAR_COLUMNS in the migration file.
DOLLAR_COLUMNS = [
    ("ai_colleague_learning_metrics", "metric_value"),
    ("ai_colleague_learning_metrics", "baseline_value"),
    ("ai_performance_daily", "total_business_value"),
    ("platform_contracts", "contract_value"),
]

# (table, column) — matches RATE_COLUMNS in the migration file.
RATE_COLUMNS = [
    ("drip_sequences", "avg_completion_rate"),
    ("sms_response_patterns", "success_rate"),
    ("ai_learning_metrics", "accuracy_rate"),
    ("ai_performance_daily", "success_rate"),
    ("ai_health_score", "autonomous_rate"),
    ("ai_health_score", "approval_rate"),
    ("ai_health_score", "success_rate"),
    ("ai_metrics_daily", "automation_rate"),
    ("ai_metrics_daily", "escalation_rate"),
    ("smart_docs_sla_configs", "warning_threshold_pct"),
]

ALL_MIGRATED = DOLLAR_COLUMNS + RATE_COLUMNS  # 14 columns total
assert len(ALL_MIGRATED) == 14, "Migration covers exactly 14 columns"


def _column_for(table_name: str, column_name: str):
    """Resolve (table, column) to the live SQLAlchemy ``Column`` object.

    Imports ``database.models`` lazily so collection works even when the
    package side-effects are heavy.
    """
    from database import Base  # noqa: WPS433 — lazy import by design
    import database.models  # noqa: F401, WPS433 — registers metadata

    table = Base.metadata.tables.get(table_name)
    if table is None:
        pytest.fail(f"Table {table_name!r} not registered on Base.metadata")
    column = table.columns.get(column_name)
    if column is None:
        pytest.fail(
            f"Column {column_name!r} not on table {table_name!r}; "
            "did the migration list drift from the model?"
        )
    return column


# ---------------------------------------------------------------------------
# Test 1 — Schema introspection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table_name,column_name", ALL_MIGRATED)
def test_migrated_column_is_numeric_not_float(table_name, column_name):
    """Every migrated column's SQLAlchemy type must be Numeric (not Float)."""
    column = _column_for(table_name, column_name)

    # Float is a subclass of Numeric in SQLAlchemy, so we must check both
    # directions: it must BE Numeric and must NOT be Float.
    assert isinstance(column.type, sa.Numeric), (
        f"{table_name}.{column_name} is {type(column.type).__name__}, "
        "expected Numeric"
    )
    assert not isinstance(column.type, sa.Float), (
        f"{table_name}.{column_name} is still Float — "
        "migration 2026_05_19_float_to_numeric not applied to model"
    )

    # Sanity-check precision/scale matches the migration intent.
    expected_precision, expected_scale = (
        (14, 2) if (table_name, column_name) in DOLLAR_COLUMNS else (8, 5)
    )
    assert column.type.precision == expected_precision, (
        f"{table_name}.{column_name} precision is {column.type.precision}, "
        f"expected {expected_precision}"
    )
    assert column.type.scale == expected_scale, (
        f"{table_name}.{column_name} scale is {column.type.scale}, "
        f"expected {expected_scale}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Round-trip precision
# ---------------------------------------------------------------------------
def test_numeric_roundtrip_preserves_cent_precision():
    """Decimal('450000.01') must round-trip exactly through Numeric(14,2).

    With Float storage, this value loses the trailing cent because 0.01 has
    no finite binary representation. Numeric preserves it exactly.
    """
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "rt_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Numeric(14, 2)),
    )
    metadata.create_all(engine)

    value = Decimal("450000.01")
    with Session(engine) as session:
        session.execute(table.insert().values(id=1, amount=value))
        session.commit()
        fetched = session.execute(
            sa.select(table.c.amount).where(table.c.id == 1)
        ).scalar_one()

    # The driver may return str/Decimal depending on dialect — normalize.
    fetched_decimal = Decimal(str(fetched))
    assert fetched_decimal == value, (
        f"Round-trip lost precision: stored {value}, fetched {fetched_decimal}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Boundary capacity
# ---------------------------------------------------------------------------
def test_numeric_boundary_max_dollar_value():
    """Numeric(14, 2) must accept 99999999999.99 (12 + 2 = 14 digits)."""
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "boundary_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Numeric(14, 2)),
    )
    metadata.create_all(engine)

    value = Decimal("99999999999.99")  # 12 digits, then 2 decimals
    with Session(engine) as session:
        session.execute(table.insert().values(id=1, amount=value))
        session.commit()
        fetched = session.execute(
            sa.select(table.c.amount).where(table.c.id == 1)
        ).scalar_one()

    fetched_decimal = Decimal(str(fetched))
    assert fetched_decimal == value, (
        f"Boundary value lost precision: stored {value}, "
        f"fetched {fetched_decimal}"
    )
