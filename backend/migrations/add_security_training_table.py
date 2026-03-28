"""
Add Security Training Records Table — SOC 2 CC1.4

Creates the security_training_records table for tracking employee
security awareness training completions, attestations, and certificates.

Usage:
    python -m migrations.add_security_training_table
    # or
    from migrations.add_security_training_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create the security_training_records table and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        logger.info("Creating security_training_records table...")

        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS security_training_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        organization_id INTEGER,
                        training_type VARCHAR NOT NULL,
                        training_year INTEGER NOT NULL,
                        completed_at TIMESTAMP,
                        score INTEGER,
                        passed BOOLEAN DEFAULT 0,
                        passing_score INTEGER DEFAULT 80,
                        attestation_text TEXT,
                        attested_at TIMESTAMP,
                        certificate_id VARCHAR,
                        expires_at TIMESTAMP,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (organization_id) REFERENCES organizations(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS security_training_records (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        organization_id INTEGER REFERENCES organizations(id),
                        training_type VARCHAR NOT NULL,
                        training_year INTEGER NOT NULL,
                        completed_at TIMESTAMPTZ,
                        score INTEGER,
                        passed BOOLEAN DEFAULT FALSE,
                        passing_score INTEGER DEFAULT 80,
                        attestation_text TEXT,
                        attested_at TIMESTAMPTZ,
                        certificate_id VARCHAR,
                        expires_at TIMESTAMPTZ,
                        metadata JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """))

            conn.commit()
            logger.info("  security_training_records table created")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  security_training_records table already exists")
            else:
                logger.error(f"Failed to create security_training_records table: {e}")
                return False

        # Create indexes
        indexes = [
            (
                "ix_security_training_user_id",
                "CREATE INDEX IF NOT EXISTS ix_security_training_user_id "
                "ON security_training_records (user_id)",
            ),
            (
                "ix_security_training_org_id",
                "CREATE INDEX IF NOT EXISTS ix_security_training_org_id "
                "ON security_training_records (organization_id)",
            ),
            (
                "ix_security_training_user_year",
                "CREATE INDEX IF NOT EXISTS ix_security_training_user_year "
                "ON security_training_records (user_id, training_year)",
            ),
            (
                "ix_security_training_org_type_year",
                "CREATE INDEX IF NOT EXISTS ix_security_training_org_type_year "
                "ON security_training_records (organization_id, training_type, training_year)",
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

    logger.info("Security training migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
