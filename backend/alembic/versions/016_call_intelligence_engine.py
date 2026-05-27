"""Create CIE call_records and intelligence_reports tables with RLS

Revision ID: 016_cie
Revises: 015_inline_ddl_consolidation
Create Date: 2026-05-26

Creates the two core tables for the Call Intelligence Engine and enables
PostgreSQL Row-Level Security with the same tenant_isolation pattern used
across all existing RLS-protected tables (see migration 006).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "016_cie"
down_revision = "015_inline_ddl_consolidation"
branch_labels = None
depends_on = None

CIE_TABLES = ["cie_call_records", "cie_intelligence_reports"]


def upgrade():
    bind = op.get_bind()

    # --- cie_call_records -------------------------------------------------
    op.create_table(
        "cie_call_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_call_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False, server_default="inbound"),
        sa.Column("phone_from", sa.Text, nullable=True),
        sa.Column("phone_to", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("transcript_encrypted", sa.Text, nullable=True),
        sa.Column("recording_url_encrypted", sa.Text, nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("contact_id", sa.Integer, nullable=True),
        sa.Column("loan_id", sa.Integer, nullable=True),
        sa.Column("lead_id", sa.Integer, nullable=True),
        sa.Column("owner_user_id", sa.Integer, nullable=True),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_unique_constraint("uq_cie_call_ext_org", "cie_call_records", ["external_call_id", "organization_id"])
    op.create_index("ix_cie_call_org_created", "cie_call_records", ["organization_id", "created_at"])
    op.create_index("ix_cie_call_status", "cie_call_records", ["processing_status"])
    op.create_index("ix_cie_call_loan", "cie_call_records", ["loan_id"])
    op.create_index("ix_cie_call_lead", "cie_call_records", ["lead_id"])
    op.create_index("ix_cie_call_org", "cie_call_records", ["organization_id"])

    # --- cie_intelligence_reports -----------------------------------------
    op.create_table(
        "cie_intelligence_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("call_record_id", UUID(as_uuid=True), sa.ForeignKey("cie_call_records.id", ondelete="CASCADE"), nullable=False, unique=True),
        # Scores
        sa.Column("cis_composite", sa.Float, nullable=True),
        sa.Column("engagement_score", sa.Float, nullable=True),
        sa.Column("information_quality_score", sa.Float, nullable=True),
        sa.Column("objection_handling_score", sa.Float, nullable=True),
        sa.Column("compliance_score", sa.Float, nullable=True),
        sa.Column("rapport_score", sa.Float, nullable=True),
        sa.Column("closing_effectiveness_score", sa.Float, nullable=True),
        # Intent
        sa.Column("primary_intent", sa.String(100), nullable=True),
        sa.Column("intent_confidence", sa.Float, nullable=True),
        # Conversion
        sa.Column("conversion_probability", sa.Float, nullable=True),
        sa.Column("conversion_ci_low", sa.Float, nullable=True),
        sa.Column("conversion_ci_high", sa.Float, nullable=True),
        # Structured findings
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("summary_bullets", JSONB, nullable=True),
        sa.Column("opportunities", JSONB, nullable=True),
        sa.Column("risks", JSONB, nullable=True),
        sa.Column("objections", JSONB, nullable=True),
        sa.Column("compliance_flags", JSONB, nullable=True),
        sa.Column("coaching_suggestions", JSONB, nullable=True),
        sa.Column("generated_tasks", JSONB, nullable=True),
        sa.Column("draft_messages", JSONB, nullable=True),
        # Metadata
        sa.Column("llm_model_used", sa.String(100), nullable=True),
        sa.Column("pipeline_version", sa.String(50), nullable=True),
        sa.Column("processing_time_ms", sa.Integer, nullable=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_cie_report_org_created", "cie_intelligence_reports", ["organization_id", "created_at"])
    op.create_index("ix_cie_report_call", "cie_intelligence_reports", ["call_record_id"])
    op.create_index("ix_cie_report_org", "cie_intelligence_reports", ["organization_id"])

    # --- RLS (same pattern as migration 006) -----------------------------
    if bind.dialect.name == "postgresql":
        for table in CIE_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            policy = f"tenant_isolation_{table}"
            op.execute(f"""
                DROP POLICY IF EXISTS {policy} ON {table};
                CREATE POLICY {policy} ON {table}
                FOR ALL
                USING (
                    organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
                )
            """)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in CIE_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("cie_intelligence_reports")
    op.drop_table("cie_call_records")
