"""
Fix smart_document_requests schema

Ensures all columns expected by the ORM model exist in the production table.
The table may have been created via raw SQL fallback with different column names
or missing columns. This migration adds any missing columns.

Run with: python migrations/fix_smart_docs_requests_schema.py
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def get_database_url():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1]
    return "sqlite:///./mortgage_crm.db"


def run_migration():
    database_url = get_database_url()
    engine = create_engine(database_url)
    is_pg = database_url.startswith('postgresql') or database_url.startswith('postgres')

    if not is_pg:
        logger.info("Skipping smart_docs schema fix — not PostgreSQL")
        return

    with engine.connect() as conn:
        inspector = inspect(conn)
        if 'smart_document_requests' not in inspector.get_table_names():
            logger.info("smart_document_requests table does not exist, skipping")
            return

        existing = {c['name'] for c in inspector.get_columns('smart_document_requests')}
        logger.info(f"smart_document_requests has columns: {sorted(existing)}")

        migrations = [
            ("required_count", "ALTER TABLE smart_document_requests ADD COLUMN required_count INTEGER DEFAULT 1"),
            ("is_required", "ALTER TABLE smart_document_requests ADD COLUMN is_required BOOLEAN DEFAULT TRUE"),
            ("freshness_days", "ALTER TABLE smart_document_requests ADD COLUMN freshness_days INTEGER"),
            ("completed_at", "ALTER TABLE smart_document_requests ADD COLUMN completed_at TIMESTAMP"),
            ("fulfilled_at", "ALTER TABLE smart_document_requests ADD COLUMN fulfilled_at TIMESTAMP"),
            ("payroll_frequency", "ALTER TABLE smart_document_requests ADD COLUMN payroll_frequency VARCHAR(50)"),
            ("requires_esign", "ALTER TABLE smart_document_requests ADD COLUMN requires_esign BOOLEAN DEFAULT FALSE"),
            ("sla_due_at", "ALTER TABLE smart_document_requests ADD COLUMN sla_due_at TIMESTAMP"),
            ("is_active", "ALTER TABLE smart_document_requests ADD COLUMN is_active BOOLEAN DEFAULT TRUE"),
            ("superseded_by", "ALTER TABLE smart_document_requests ADD COLUMN superseded_by INTEGER"),
            ("next_expected_available_at", "ALTER TABLE smart_document_requests ADD COLUMN next_expected_available_at TIMESTAMP"),
        ]

        added = []
        for col_name, sql in migrations:
            if col_name not in existing:
                try:
                    conn.execute(text(sql))
                    added.append(col_name)
                    logger.info(f"  Added column: {col_name}")
                except Exception as e:
                    logger.warning(f"  Could not add {col_name}: {e}")

        # If production has freshness_period_days but not freshness_days,
        # copy data over
        if 'freshness_period_days' in existing and 'freshness_days' in (existing | set(added)):
            try:
                conn.execute(text("""
                    UPDATE smart_document_requests
                    SET freshness_days = freshness_period_days
                    WHERE freshness_days IS NULL AND freshness_period_days IS NOT NULL
                """))
                logger.info("  Copied freshness_period_days → freshness_days")
            except Exception as e:
                logger.warning(f"  Could not copy freshness data: {e}")

        # Convert any PG ENUM columns to VARCHAR to avoid type mismatches
        for col_name, varchar_size in [
            ("doc_type", 100), ("status", 50), ("priority", 50),
            ("applies_to", 50), ("payroll_frequency", 50),
        ]:
            if col_name in existing or col_name in added:
                try:
                    col_info = next(
                        (c for c in inspector.get_columns('smart_document_requests')
                         if c['name'] == col_name), None
                    )
                    if col_info:
                        col_type = str(col_info.get('type', '')).upper()
                        if 'VARCHAR' not in col_type and 'TEXT' not in col_type and 'CHAR' not in col_type:
                            conn.execute(text(f"""
                                ALTER TABLE smart_document_requests
                                ALTER COLUMN {col_name} TYPE VARCHAR({varchar_size})
                                USING {col_name}::VARCHAR({varchar_size})
                            """))
                            logger.info(f"  Converted {col_name} from {col_type} to VARCHAR({varchar_size})")
                except Exception as e:
                    logger.warning(f"  Could not convert {col_name} to VARCHAR: {e}")

        conn.commit()

        if added:
            logger.info(f"Schema fix complete — added {len(added)} columns: {added}")
        else:
            logger.info("Schema fix complete — all columns present")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
