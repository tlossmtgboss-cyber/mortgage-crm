"""Float to Numeric migration for TRID-safe financial math

Converts IEEE 754 Float columns to fixed-precision Numeric for all dollar
amounts and rates/percentages. Float storage of monetary values is a TRID
violation (e.g., 450000.01 stored as 450000.00999...).

Dollar amounts -> Numeric(14, 2)
Rates / percentages -> Numeric(8, 5)

Revision ID: 2026_05_19_float_to_numeric
Revises: 2026_05_19_audit_table
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2026_05_19_float_to_numeric"
down_revision = "2026_05_19_audit_table"
branch_labels = None
depends_on = None


# (table, column, precision, scale)
DOLLAR_COLUMNS = [
    ("ai_colleague_learning_metrics", "metric_value"),
    ("ai_colleague_learning_metrics", "baseline_value"),
    ("ai_performance_daily", "total_business_value"),
    ("platform_contracts", "contract_value"),
]

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


def upgrade() -> None:
    for table, column in DOLLAR_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Numeric(14, 2),
            existing_type=sa.Float(),
            postgresql_using=f"{column}::numeric(14,2)",
        )

    for table, column in RATE_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Numeric(8, 5),
            existing_type=sa.Float(),
            postgresql_using=f"{column}::numeric(8,5)",
        )


def downgrade() -> None:
    for table, column in DOLLAR_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Float(),
            existing_type=sa.Numeric(14, 2),
            postgresql_using=f"{column}::double precision",
        )

    for table, column in RATE_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Float(),
            existing_type=sa.Numeric(8, 5),
            postgresql_using=f"{column}::double precision",
        )
