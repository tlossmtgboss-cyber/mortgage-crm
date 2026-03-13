"""
Add Business Rules Configuration Table

Creates the business_rule_configs table for storing configurable business
rules that previously required code deploys to change.

Usage:
    python -m migrations.add_business_rules_table
    # or
    from migrations.add_business_rules_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create the business_rule_configs table and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        logger.info("Creating business_rule_configs table...")

        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS business_rule_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER,
                        rule_category VARCHAR(50) NOT NULL,
                        rule_key VARCHAR(100) NOT NULL,
                        rule_value TEXT NOT NULL,
                        value_type VARCHAR(20) NOT NULL DEFAULT 'integer',
                        description TEXT,
                        effective_date DATE NOT NULL,
                        expiration_date DATE,
                        source VARCHAR(100),
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by_user_id INTEGER,
                        FOREIGN KEY (organization_id) REFERENCES organizations(id),
                        FOREIGN KEY (updated_by_user_id) REFERENCES users(id),
                        UNIQUE (organization_id, rule_key, effective_date)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS business_rule_configs (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER REFERENCES organizations(id),
                        rule_category VARCHAR(50) NOT NULL,
                        rule_key VARCHAR(100) NOT NULL,
                        rule_value JSONB NOT NULL,
                        value_type VARCHAR(20) NOT NULL DEFAULT 'integer',
                        description TEXT,
                        effective_date DATE NOT NULL,
                        expiration_date DATE,
                        source VARCHAR(100),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        updated_by_user_id INTEGER REFERENCES users(id),
                        CONSTRAINT uq_business_rule_org_key_date
                            UNIQUE (organization_id, rule_key, effective_date)
                    )
                """))

            conn.commit()
            logger.info("  business_rule_configs table created")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  business_rule_configs table already exists")
            else:
                logger.error(f"Failed to create business_rule_configs table: {e}")
                return False

        # Create indexes
        indexes = [
            (
                "ix_business_rule_key_active",
                "CREATE INDEX IF NOT EXISTS ix_business_rule_key_active "
                "ON business_rule_configs (rule_key, is_active)",
            ),
            (
                "ix_business_rule_org_category",
                "CREATE INDEX IF NOT EXISTS ix_business_rule_org_category "
                "ON business_rule_configs (organization_id, rule_category)",
            ),
            (
                "ix_business_rule_effective",
                "CREATE INDEX IF NOT EXISTS ix_business_rule_effective "
                "ON business_rule_configs (rule_key, effective_date, expiration_date)",
            ),
            (
                "ix_business_rule_org_id",
                "CREATE INDEX IF NOT EXISTS ix_business_rule_org_id "
                "ON business_rule_configs (organization_id)",
            ),
        ]

        for idx_name, idx_sql in indexes:
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

    logger.info("Business rules migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
