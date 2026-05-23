"""Create briefing_threads, briefing_tasks, and briefing_audit_logs tables.
Run: python migrations/create_briefing_thread_tables.py

Uses raw DDL instead of model-based creation to avoid FK ordering issues
and SQLAlchemy 2.0 autocommit complications.
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS briefing_threads (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    morning_briefing_id INTEGER,
                    thread_token UUID NOT NULL UNIQUE,
                    outbound_message_id VARCHAR(512),
                    state VARCHAR(50) NOT NULL DEFAULT 'BRIEFING_SENT',
                    trust_mode INTEGER NOT NULL DEFAULT 3,
                    loop_count INTEGER NOT NULL DEFAULT 0,
                    briefing_items JSONB,
                    extracted_tasks JSONB,
                    lo_reply_raw TEXT,
                    lo_approval_raw TEXT,
                    expires_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS briefing_tasks (
                    id SERIAL PRIMARY KEY,
                    thread_id INTEGER NOT NULL REFERENCES briefing_threads(id),
                    organization_id INTEGER NOT NULL,
                    briefing_item_number INTEGER,
                    briefing_item_summary TEXT,
                    action_type VARCHAR(50),
                    action_params JSONB,
                    tool_name VARCHAR(100),
                    lo_override_notes TEXT,
                    confidence_score FLOAT,
                    risk_level VARCHAR(20) NOT NULL DEFAULT 'low',
                    preflight_result JSONB,
                    idempotency_key VARCHAR(255) UNIQUE,
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    carryover_target_date DATE,
                    result_data JSONB,
                    error_message TEXT,
                    executed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS briefing_audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    thread_id INTEGER REFERENCES briefing_threads(id),
                    task_id INTEGER REFERENCES briefing_tasks(id),
                    event_type VARCHAR(50),
                    actor VARCHAR(100),
                    payload JSONB,
                    payload_hash VARCHAR(64),
                    prev_hash VARCHAR(64),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))

            # Indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_briefing_threads_org_user_state ON briefing_threads (organization_id, user_id, state)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_briefing_threads_outbound_message_id ON briefing_threads (outbound_message_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_briefing_tasks_thread_status ON briefing_tasks (thread_id, status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_briefing_tasks_organization_id ON briefing_tasks (organization_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_briefing_audit_logs_org_created_at ON briefing_audit_logs (organization_id, created_at)"))

    print("Migration complete: briefing_threads, briefing_tasks, briefing_audit_logs created.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
