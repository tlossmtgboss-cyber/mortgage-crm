"""
Add immutable compliance decision log table.

Creates:
1. compliance_decision_log -- append-only audit trail for all compliance
   decisions (DNC checks, calling-hours validation, consent checks,
   rate-limit enforcement, soft-lock acquisition).
2. Indexes for efficient querying by org, decision type, and time.
3. Revokes UPDATE/DELETE on PostgreSQL to enforce immutability at the DB level.

Run with:   python migrations/add_compliance_decision_log.py
Rollback:   python migrations/add_compliance_decision_log.py --rollback
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
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


def is_postgresql(database_url):
    """Check if database is PostgreSQL."""
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def table_exists(conn, table_name):
    """Check if a table exists."""
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def index_exists(conn, index_name, is_pg=False):
    """Check if an index exists."""
    if is_pg:
        result = conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE indexname = :name"
        ), {"name": index_name})
    else:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=:name"
        ), {"name": index_name})
    return result.fetchone() is not None


def run_migration():
    """Execute the migration."""
    database_url = get_database_url()
    print(f"Using database: {database_url[:50]}...")

    is_pg = is_postgresql(database_url)
    print(f"Database type: {'PostgreSQL' if is_pg else 'SQLite'}")

    engine = create_engine(database_url)

    print("Running Compliance Decision Log migration...")

    with engine.connect() as conn:
        # =================================================================
        # TABLE: compliance_decision_log (append-only)
        # =================================================================

        if not table_exists(conn, 'compliance_decision_log'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE compliance_decision_log (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER REFERENCES organizations(id),
                        user_id INTEGER REFERENCES users(id),
                        decision_type VARCHAR NOT NULL,
                        phone_number VARCHAR,
                        contact_id INTEGER,
                        lead_id INTEGER,
                        decision VARCHAR NOT NULL,
                        reason VARCHAR,
                        details JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE compliance_decision_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER,
                        user_id INTEGER,
                        decision_type VARCHAR NOT NULL,
                        phone_number VARCHAR,
                        contact_id INTEGER,
                        lead_id INTEGER,
                        decision VARCHAR NOT NULL,
                        reason VARCHAR,
                        details TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            print("  Created compliance_decision_log table")
        else:
            print("  compliance_decision_log table already exists")

        # =================================================================
        # INDEXES
        # =================================================================

        indexes = [
            ("ix_cdl_org_created",
             "compliance_decision_log", "(organization_id, created_at)"),
            ("ix_cdl_type_created",
             "compliance_decision_log", "(decision_type, created_at)"),
            ("ix_cdl_org_id",
             "compliance_decision_log", "(organization_id)"),
            ("ix_cdl_user_id",
             "compliance_decision_log", "(user_id)"),
            ("ix_cdl_created",
             "compliance_decision_log", "(created_at)"),
            ("ix_cdl_decision_type",
             "compliance_decision_log", "(decision_type)"),
        ]

        for idx_name, tbl_name, columns in indexes:
            if not index_exists(conn, idx_name, is_pg):
                try:
                    conn.execute(text(
                        f"CREATE INDEX {idx_name} ON {tbl_name} {columns}"
                    ))
                    print(f"  Created index {idx_name}")
                except Exception as e:
                    print(f"  Skipped index {idx_name}: {e}")
            else:
                print(f"  Index {idx_name} already exists")

        # =================================================================
        # IMMUTABILITY: Revoke UPDATE and DELETE (PostgreSQL only)
        # =================================================================

        if is_pg:
            try:
                conn.execute(text(
                    "REVOKE UPDATE, DELETE ON compliance_decision_log FROM PUBLIC"
                ))
                print("  Revoked UPDATE/DELETE on compliance_decision_log")
            except Exception as e:
                print(f"  Note: Could not revoke UPDATE/DELETE (may need superuser): {e}")

        conn.commit()

    print("\nCompliance Decision Log migration completed successfully!")
    logger.info("Compliance Decision Log migration completed")


def rollback_migration():
    """Rollback the migration (for development/testing)."""
    database_url = get_database_url()
    engine = create_engine(database_url)
    is_pg = is_postgresql(database_url)

    print("Rolling back Compliance Decision Log migration...")

    with engine.connect() as conn:
        # Drop indexes
        index_names = [
            "ix_cdl_org_created",
            "ix_cdl_type_created",
            "ix_cdl_org_id",
            "ix_cdl_user_id",
            "ix_cdl_created",
            "ix_cdl_decision_type",
        ]
        for idx in index_names:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                print(f"  Dropped index {idx}")
            except Exception as e:
                print(f"  Could not drop index {idx}: {e}")

        # Drop table
        conn.execute(text("DROP TABLE IF EXISTS compliance_decision_log"))
        print("  Dropped table compliance_decision_log")

        conn.commit()

    print("Rollback completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
