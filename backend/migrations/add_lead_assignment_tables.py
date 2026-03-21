"""
Migration: Create Lead Assignment Tables

Creates:
    - lead_assignment_configs (org-level strategy configuration)
    - lead_assignment_rules (condition-based routing rules)
    - lead_assignment_pool (LO pool membership with weights)
    - lead_assignment_exceptions (PTO, capacity overrides)
    - lead_assignment_audit_log (append-only assignment trail)

Usage:
    python migrations/add_lead_assignment_tables.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    """Create lead assignment tables."""
    from sqlalchemy import text
    from db import engine

    tables = [
        {
            "name": "lead_assignment_configs",
            "sql": """
                CREATE TABLE IF NOT EXISTS lead_assignment_configs (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    strategy VARCHAR(30) NOT NULL DEFAULT 'round_robin',
                    fallback_user_id INTEGER REFERENCES users(id),
                    respect_capacity BOOLEAN DEFAULT TRUE,
                    max_daily_leads_per_user INTEGER DEFAULT 50,
                    business_hours_only BOOLEAN DEFAULT FALSE,
                    business_hours_start VARCHAR(5) DEFAULT '08:00',
                    business_hours_end VARCHAR(5) DEFAULT '18:00',
                    business_hours_timezone VARCHAR(50) DEFAULT 'America/New_York',
                    notify_on_assignment BOOLEAN DEFAULT TRUE,
                    notification_channels JSONB DEFAULT '["email"]',
                    round_robin_index INTEGER DEFAULT 0,
                    dedup_enabled BOOLEAN DEFAULT TRUE,
                    dedup_match_fields JSONB DEFAULT '["email", "phone"]',
                    dedup_window_days INTEGER DEFAULT 30,
                    dedup_action VARCHAR(20) DEFAULT 'merge',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_by_user_id INTEGER REFERENCES users(id)
                )
            """,
        },
        {
            "name": "lead_assignment_rules",
            "sql": """
                CREATE TABLE IF NOT EXISTS lead_assignment_rules (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    rule_name VARCHAR(200) NOT NULL,
                    description VARCHAR(500),
                    priority INTEGER DEFAULT 100,
                    conditions JSONB NOT NULL,
                    match_type VARCHAR(10) DEFAULT 'ALL',
                    target_type VARCHAR(30) NOT NULL,
                    target_config JSONB NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """,
        },
        {
            "name": "lead_assignment_pool",
            "sql": """
                CREATE TABLE IF NOT EXISTS lead_assignment_pool (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    weight INTEGER DEFAULT 100,
                    max_daily_leads INTEGER DEFAULT 50,
                    is_active BOOLEAN DEFAULT TRUE,
                    geographic_states JSONB,
                    specialties JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """,
        },
        {
            "name": "lead_assignment_exceptions",
            "sql": """
                CREATE TABLE IF NOT EXISTS lead_assignment_exceptions (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    exception_type VARCHAR(30) NOT NULL,
                    reason VARCHAR(500),
                    starts_at TIMESTAMPTZ NOT NULL,
                    ends_at TIMESTAMPTZ,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """,
        },
        {
            "name": "lead_assignment_audit_log",
            "sql": """
                CREATE TABLE IF NOT EXISTS lead_assignment_audit_log (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    lead_id INTEGER REFERENCES leads(id),
                    action VARCHAR(50) NOT NULL,
                    strategy_used VARCHAR(30),
                    rule_id INTEGER REFERENCES lead_assignment_rules(id),
                    rule_name VARCHAR(200),
                    from_user_id INTEGER REFERENCES users(id),
                    to_user_id INTEGER REFERENCES users(id),
                    decision_reason TEXT,
                    event_data JSONB,
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """,
        },
    ]

    indexes = [
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_lead_assign_config_org ON lead_assignment_configs(organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_rules_org_priority ON lead_assignment_rules(organization_id, priority)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_rules_org_active ON lead_assignment_rules(organization_id, is_active)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_lead_assign_pool_org_user ON lead_assignment_pool(organization_id, user_id)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_pool_org_active ON lead_assignment_pool(organization_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_exc_org_user ON lead_assignment_exceptions(organization_id, user_id)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_exc_active ON lead_assignment_exceptions(organization_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_audit_org ON lead_assignment_audit_log(organization_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_lead_assign_audit_lead ON lead_assignment_audit_log(lead_id, created_at)",
    ]

    with engine.begin() as conn:
        for table in tables:
            try:
                conn.execute(text(table["sql"]))
                logger.info(f"Table '{table['name']}' created (or already exists)")
            except Exception as e:
                logger.error(f"Failed to create '{table['name']}': {e}")
                raise

        for idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.warning(f"Index creation note: {e}")

    logger.info("Lead assignment migration complete — 5 tables, 9 indexes")


if __name__ == "__main__":
    run_migration()
