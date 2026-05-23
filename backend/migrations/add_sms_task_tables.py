"""
Add SMS Task Tables for AI-assisted SMS response workflow.

Creates 4 tables:
  - sms_tasks: Inbound SMS messages requiring LO response, with AI recommendations
  - sms_response_patterns: Learned response templates by category
  - sms_ai_confidence: Per-category confidence tracking for auto-respond thresholds
  - sms_ai_audit_log: Audit trail for all AI SMS actions

Usage:
    python -m migrations.add_sms_task_tables
    # or
    from migrations.add_sms_task_tables import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create SMS task tables and indexes."""
    with engine.connect() as conn:
        # -------------------------------------------------------------------
        # 1. sms_tasks — inbound SMS requiring response
        # -------------------------------------------------------------------
        logger.info("Creating sms_tasks table...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_tasks (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    assigned_user_id INTEGER REFERENCES users(id),
                    lead_id INTEGER REFERENCES leads(id),
                    phone_number TEXT NOT NULL,
                    contact_name TEXT,
                    inbound_message TEXT NOT NULL,
                    inbound_message_id TEXT,
                    inbound_received_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    category TEXT,
                    ai_recommendation TEXT,
                    ai_confidence REAL DEFAULT 0,
                    ai_model_version TEXT,
                    ai_reasoning TEXT,
                    ai_generated_at TIMESTAMPTZ,
                    response_text TEXT,
                    response_source TEXT,
                    response_sent_at TIMESTAMPTZ,
                    responded_by_user_id INTEGER REFERENCES users(id),
                    user_feedback TEXT,
                    edit_distance INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.commit()
            logger.info("  sms_tasks table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  sms_tasks table already exists")
            else:
                logger.error(f"Failed to create sms_tasks table: {e}")

        # sms_tasks indexes
        sms_tasks_indexes = [
            (
                "ix_sms_tasks_org_status",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_org_status "
                "ON sms_tasks (organization_id, status)"
            ),
            (
                "ix_sms_tasks_org_assigned_user",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_org_assigned_user "
                "ON sms_tasks (organization_id, assigned_user_id)"
            ),
            (
                "ix_sms_tasks_assigned_user_status",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_assigned_user_status "
                "ON sms_tasks (assigned_user_id, status)"
            ),
            (
                "ix_sms_tasks_phone_number",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_phone_number "
                "ON sms_tasks (phone_number)"
            ),
            (
                "ix_sms_tasks_lead_id",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_lead_id "
                "ON sms_tasks (lead_id)"
            ),
            (
                "ix_sms_tasks_pending",
                "CREATE INDEX IF NOT EXISTS ix_sms_tasks_pending "
                "ON sms_tasks (organization_id, created_at) "
                "WHERE status = 'pending'"
            ),
        ]
        for idx_name, idx_sql in sms_tasks_indexes:
            try:
                conn.execute(text(idx_sql))
                logger.info(f"  Created index {idx_name}")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    pass
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")
        conn.commit()

        # -------------------------------------------------------------------
        # 2. sms_response_patterns — learned response templates
        # -------------------------------------------------------------------
        logger.info("Creating sms_response_patterns table...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_response_patterns (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    category TEXT NOT NULL,
                    message_keywords JSONB DEFAULT '[]',
                    response_template TEXT NOT NULL,
                    times_used INTEGER DEFAULT 1,
                    times_accepted INTEGER DEFAULT 0,
                    times_edited INTEGER DEFAULT 0,
                    times_rejected INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0,
                    last_used_at TIMESTAMPTZ,
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.commit()
            logger.info("  sms_response_patterns table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  sms_response_patterns table already exists")
            else:
                logger.error(f"Failed to create sms_response_patterns table: {e}")

        # sms_response_patterns index
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_response_patterns_org_category "
                "ON sms_response_patterns (organization_id, category)"
            ))
            conn.commit()
            logger.info("  Created index ix_sms_response_patterns_org_category")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                pass
            else:
                logger.warning(f"Could not create sms_response_patterns index: {e}")

        # GIN index for JSONB keyword overlap queries
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_response_patterns_keywords_gin "
                "ON sms_response_patterns USING GIN (message_keywords)"
            ))
            conn.commit()
            logger.info("  Created GIN index ix_sms_response_patterns_keywords_gin")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                pass
            else:
                logger.warning(f"Could not create GIN index on message_keywords: {e}")

        # -------------------------------------------------------------------
        # 3. sms_ai_confidence — per-category confidence tracking
        # -------------------------------------------------------------------
        logger.info("Creating sms_ai_confidence table...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_ai_confidence (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    user_id INTEGER REFERENCES users(id),
                    category TEXT NOT NULL,
                    total_recommendations INTEGER DEFAULT 0,
                    accepted_count INTEGER DEFAULT 0,
                    edited_count INTEGER DEFAULT 0,
                    rejected_count INTEGER DEFAULT 0,
                    confidence_score REAL DEFAULT 20.0,
                    auto_respond_enabled BOOLEAN DEFAULT FALSE,
                    auto_respond_threshold REAL DEFAULT 80.0,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.commit()
            logger.info("  sms_ai_confidence table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  sms_ai_confidence table already exists")
            else:
                logger.error(f"Failed to create sms_ai_confidence table: {e}")

        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_ai_confidence_org_user_cat "
                "ON sms_ai_confidence (organization_id, COALESCE(user_id, 0), category)"
            ))
            conn.commit()
            logger.info("  Created unique index uq_sms_ai_confidence_org_user_cat")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                pass
            else:
                logger.warning(f"Could not create sms_ai_confidence unique index: {e}")

        # sms_ai_confidence index
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_ai_confidence_org_user_category "
                "ON sms_ai_confidence (organization_id, user_id, category)"
            ))
            conn.commit()
            logger.info("  Created index ix_sms_ai_confidence_org_user_category")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                pass
            else:
                logger.warning(f"Could not create sms_ai_confidence index: {e}")

        # -------------------------------------------------------------------
        # 4. sms_ai_audit_log — audit trail
        # -------------------------------------------------------------------
        logger.info("Creating sms_ai_audit_log table...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_ai_audit_log (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    task_id INTEGER REFERENCES sms_tasks(id),
                    action TEXT NOT NULL,
                    details JSONB DEFAULT '{}',
                    user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.commit()
            logger.info("  sms_ai_audit_log table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  sms_ai_audit_log table already exists")
            else:
                logger.error(f"Failed to create sms_ai_audit_log table: {e}")

        # sms_ai_audit_log indexes
        audit_indexes = [
            (
                "ix_sms_ai_audit_log_org_id",
                "CREATE INDEX IF NOT EXISTS ix_sms_ai_audit_log_org_id "
                "ON sms_ai_audit_log (organization_id)"
            ),
            (
                "ix_sms_ai_audit_log_task_id",
                "CREATE INDEX IF NOT EXISTS ix_sms_ai_audit_log_task_id "
                "ON sms_ai_audit_log (task_id)"
            ),
            (
                "ix_sms_ai_audit_log_action",
                "CREATE INDEX IF NOT EXISTS ix_sms_ai_audit_log_action "
                "ON sms_ai_audit_log (action)"
            ),
        ]
        for idx_name, idx_sql in audit_indexes:
            try:
                conn.execute(text(idx_sql))
                logger.info(f"  Created index {idx_name}")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    pass
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")
        conn.commit()

        # -------------------------------------------------------------------
        # 5. Schema patches for existing tables
        # -------------------------------------------------------------------
        logger.info("Applying SMS schema patches...")

        patches = [
            ("Add category to sms_ai_audit_log",
             "ALTER TABLE sms_ai_audit_log ADD COLUMN IF NOT EXISTS category TEXT"),
            ("Add created_at to sms_ai_confidence",
             "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"),
            ("Add index on sms_ai_audit_log.created_at",
             "CREATE INDEX IF NOT EXISTS ix_sms_ai_audit_log_created_at ON sms_ai_audit_log (created_at)"),
            ("Add index on sms_ai_audit_log.category",
             "CREATE INDEX IF NOT EXISTS ix_sms_ai_audit_log_category ON sms_ai_audit_log (category)"),
        ]
        for desc, sql in patches:
            try:
                conn.execute(text(sql))
                logger.info(f"  {desc}")
            except Exception as e:
                logger.warning(f"  Patch failed ({desc}): {e}")
        conn.commit()

        # Unique constraint to prevent duplicate tasks from webhook retries
        try:
            conn.execute(text("""
                DO $$ BEGIN
                    ALTER TABLE sms_tasks
                        ADD CONSTRAINT uq_sms_tasks_org_message_id
                        UNIQUE (organization_id, inbound_message_id);
                EXCEPTION WHEN duplicate_table THEN NULL;
                          WHEN duplicate_object THEN NULL;
                END $$
            """))
            conn.commit()
            logger.info("  Added unique constraint uq_sms_tasks_org_message_id")
        except Exception as e:
            logger.warning(f"  Could not add unique constraint: {e}")

    logger.info("SMS task tables migration complete")
    return True


if __name__ == "__main__":
    import os
    import sys

    logging.basicConfig(level=logging.INFO)

    # Add backend to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from db import engine

    try:
        result = run_migration(engine)
        if result:
            logger.info("Migration completed successfully")
        else:
            logger.error("Migration failed")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Migration error: {e}")
        sys.exit(1)
