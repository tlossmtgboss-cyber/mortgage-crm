"""
Add recruiting calendar tables.

Creates:
  recruit_interview_details  — linked 1:1 to scheduler_appointments for recruiting-specific metadata
  recruit_milestones         — start dates, 30/90-day check-ins, onboarding milestones

Both tables use app.current_tenant GUC for RLS (same pattern as enable_scheduler_rls.py).
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


DDL_INTERVIEW_DETAILS = """
CREATE TABLE IF NOT EXISTS recruit_interview_details (
    id                  SERIAL PRIMARY KEY,
    organization_id     INTEGER NOT NULL,
    appointment_id      INTEGER NOT NULL REFERENCES scheduler_appointments(id) ON DELETE CASCADE,
    candidate_id        INTEGER NOT NULL,
    interview_type      VARCHAR(50) NOT NULL DEFAULT 'phone_screen',
    outcome             VARCHAR(50),
    scorecard           JSONB DEFAULT '{}',
    panel_members       JSONB DEFAULT '[]',
    interviewer_notes   TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (appointment_id)
);
CREATE INDEX IF NOT EXISTS idx_recruit_interview_org ON recruit_interview_details(organization_id);
CREATE INDEX IF NOT EXISTS idx_recruit_interview_candidate ON recruit_interview_details(candidate_id);
CREATE INDEX IF NOT EXISTS idx_recruit_interview_appt ON recruit_interview_details(appointment_id);
"""

DDL_MILESTONES = """
CREATE TABLE IF NOT EXISTS recruit_milestones (
    id                  SERIAL PRIMARY KEY,
    organization_id     INTEGER NOT NULL,
    candidate_id        INTEGER NOT NULL,
    milestone_type      VARCHAR(50) NOT NULL,
    scheduled_date      TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    assigned_to_user_id INTEGER,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recruit_milestones_org ON recruit_milestones(organization_id);
CREATE INDEX IF NOT EXISTS idx_recruit_milestones_candidate ON recruit_milestones(candidate_id);
CREATE INDEX IF NOT EXISTS idx_recruit_milestones_date ON recruit_milestones(scheduled_date)
    WHERE completed_at IS NULL;
"""

RLS_INTERVIEW_DETAILS = """
ALTER TABLE recruit_interview_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruit_interview_details FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruit_interview_details_tenant_isolation ON recruit_interview_details;
CREATE POLICY recruit_interview_details_tenant_isolation ON recruit_interview_details
    USING (organization_id = current_setting('app.current_tenant', true)::int);
"""

RLS_MILESTONES = """
ALTER TABLE recruit_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruit_milestones FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruit_milestones_tenant_isolation ON recruit_milestones;
CREATE POLICY recruit_milestones_tenant_isolation ON recruit_milestones
    USING (organization_id = current_setting('app.current_tenant', true)::int);
"""


def run_migration(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(DDL_INTERVIEW_DETAILS))
            logger.info("[OK] recruit_interview_details table ready")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning("[WARN] recruit_interview_details: %s", e)

        try:
            conn.execute(text(DDL_MILESTONES))
            logger.info("[OK] recruit_milestones table ready")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning("[WARN] recruit_milestones: %s", e)

        for label, ddl in [("interview_details RLS", RLS_INTERVIEW_DETAILS),
                            ("milestones RLS", RLS_MILESTONES)]:
            try:
                conn.execute(text(ddl))
                logger.info("[OK] %s enabled", label)
            except Exception as e:
                logger.warning("[WARN] %s: %s", label, e)

    return {"created": ["recruit_interview_details", "recruit_milestones"]}


def rollback(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("DROP TABLE IF EXISTS recruit_interview_details CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS recruit_milestones CASCADE"))
        logger.info("Dropped recruit calendar tables")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_migration()
    sys.exit(0)
