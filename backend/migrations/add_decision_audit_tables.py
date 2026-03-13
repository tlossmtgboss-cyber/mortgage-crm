"""
Decision Audit Trail Migration

Creates:
1. decision_audit_logs — append-only audit trail for all decisions
2. audit_retention_configs — per-org retention policy configuration
3. archived_decision_audit_logs — cold storage for expired records
4. Indexes for efficient querying by org, loan, entity, and time

Run with: python migrations/add_decision_audit_tables.py
Rollback:  python migrations/add_decision_audit_tables.py --rollback
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

    print("Running Decision Audit Trail migration...")

    with engine.connect() as conn:
        # =====================================================================
        # TABLE 1: decision_audit_logs (append-only)
        # =====================================================================

        if not table_exists(conn, 'decision_audit_logs'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE decision_audit_logs (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        loan_id INTEGER,
                        document_id INTEGER,
                        decision_type VARCHAR(64) NOT NULL,
                        entity_type VARCHAR(64) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        decision VARCHAR(32) NOT NULL,
                        decision_maker_type VARCHAR(20) NOT NULL,
                        decision_maker_id INTEGER,
                        decision_maker_name VARCHAR(255),
                        reasoning TEXT NOT NULL,
                        supporting_data JSONB,
                        previous_state VARCHAR(32),
                        new_state VARCHAR(32) NOT NULL,
                        ip_address VARCHAR(45),
                        user_agent TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE decision_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL,
                        loan_id INTEGER,
                        document_id INTEGER,
                        decision_type VARCHAR(64) NOT NULL,
                        entity_type VARCHAR(64) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        decision VARCHAR(32) NOT NULL,
                        decision_maker_type VARCHAR(20) NOT NULL,
                        decision_maker_id INTEGER,
                        decision_maker_name VARCHAR(255),
                        reasoning TEXT NOT NULL,
                        supporting_data TEXT,
                        previous_state VARCHAR(32),
                        new_state VARCHAR(32) NOT NULL,
                        ip_address VARCHAR(45),
                        user_agent TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            print("  Created decision_audit_logs table")
        else:
            print("  decision_audit_logs table already exists")

        # =====================================================================
        # TABLE 2: audit_retention_configs (one per org)
        # =====================================================================

        if not table_exists(conn, 'audit_retention_configs'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE audit_retention_configs (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL UNIQUE,
                        default_retention_days INTEGER NOT NULL DEFAULT 2555,
                        document_retention_days INTEGER NOT NULL DEFAULT 2555,
                        esign_retention_days INTEGER NOT NULL DEFAULT 2555,
                        followup_retention_days INTEGER NOT NULL DEFAULT 2555,
                        min_retention_days INTEGER NOT NULL DEFAULT 1095,
                        archive_to_cold_storage BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE audit_retention_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL UNIQUE,
                        default_retention_days INTEGER NOT NULL DEFAULT 2555,
                        document_retention_days INTEGER NOT NULL DEFAULT 2555,
                        esign_retention_days INTEGER NOT NULL DEFAULT 2555,
                        followup_retention_days INTEGER NOT NULL DEFAULT 2555,
                        min_retention_days INTEGER NOT NULL DEFAULT 1095,
                        archive_to_cold_storage BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            print("  Created audit_retention_configs table")
        else:
            print("  audit_retention_configs table already exists")

        # =====================================================================
        # TABLE 3: archived_decision_audit_logs (cold storage)
        # =====================================================================

        if not table_exists(conn, 'archived_decision_audit_logs'):
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE archived_decision_audit_logs (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        loan_id INTEGER,
                        document_id INTEGER,
                        decision_type VARCHAR(64) NOT NULL,
                        entity_type VARCHAR(64) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        decision VARCHAR(32) NOT NULL,
                        decision_maker_type VARCHAR(20) NOT NULL,
                        decision_maker_id INTEGER,
                        decision_maker_name VARCHAR(255),
                        reasoning TEXT NOT NULL,
                        supporting_data JSONB,
                        previous_state VARCHAR(32),
                        new_state VARCHAR(32) NOT NULL,
                        ip_address VARCHAR(45),
                        user_agent TEXT,
                        created_at TIMESTAMP NOT NULL,
                        archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        original_audit_id INTEGER
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE archived_decision_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL,
                        loan_id INTEGER,
                        document_id INTEGER,
                        decision_type VARCHAR(64) NOT NULL,
                        entity_type VARCHAR(64) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        decision VARCHAR(32) NOT NULL,
                        decision_maker_type VARCHAR(20) NOT NULL,
                        decision_maker_id INTEGER,
                        decision_maker_name VARCHAR(255),
                        reasoning TEXT NOT NULL,
                        supporting_data TEXT,
                        previous_state VARCHAR(32),
                        new_state VARCHAR(32) NOT NULL,
                        ip_address VARCHAR(45),
                        user_agent TEXT,
                        created_at TIMESTAMP NOT NULL,
                        archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        original_audit_id INTEGER
                    )
                """))
            print("  Created archived_decision_audit_logs table")
        else:
            print("  archived_decision_audit_logs table already exists")

        # =====================================================================
        # INDEXES on decision_audit_logs
        # =====================================================================

        indexes = [
            ("ix_decision_audit_org_loan",
             "decision_audit_logs", "(organization_id, loan_id)"),
            ("ix_decision_audit_org_type_created",
             "decision_audit_logs", "(organization_id, decision_type, created_at)"),
            ("ix_decision_audit_entity",
             "decision_audit_logs", "(entity_type, entity_id)"),
            ("ix_decision_audit_created_at",
             "decision_audit_logs", "(created_at)"),
            ("ix_decision_audit_maker",
             "decision_audit_logs", "(decision_maker_type, decision_maker_id)"),
            ("ix_decision_audit_org_id",
             "decision_audit_logs", "(organization_id)"),
            # Indexes on audit_retention_configs
            ("ix_audit_retention_org_unique",
             "audit_retention_configs", "(organization_id)"),
            # Indexes on archived_decision_audit_logs
            ("ix_archived_audit_org_loan",
             "archived_decision_audit_logs", "(organization_id, loan_id)"),
            ("ix_archived_audit_created_at",
             "archived_decision_audit_logs", "(created_at)"),
            ("ix_archived_audit_original_id",
             "archived_decision_audit_logs", "(original_audit_id)"),
        ]

        for idx_name, tbl_name, columns in indexes:
            if not index_exists(conn, idx_name, is_pg):
                try:
                    conn.execute(text(
                        f"CREATE INDEX {idx_name} ON {tbl_name} {columns}"
                    ))
                    print(f"  Created index {idx_name}")
                except Exception as e:
                    # Some indexes may conflict with unique constraints
                    print(f"  Skipped index {idx_name}: {e}")
            else:
                print(f"  Index {idx_name} already exists")

        conn.commit()

    print("\nDecision Audit Trail migration completed successfully!")
    logger.info("Decision Audit Trail migration completed")


def rollback_migration():
    """Rollback the migration (for development/testing)."""
    database_url = get_database_url()
    engine = create_engine(database_url)
    is_pg = is_postgresql(database_url)

    print("Rolling back Decision Audit Trail migration...")

    with engine.connect() as conn:
        # Drop indexes
        index_names = [
            "ix_decision_audit_org_loan",
            "ix_decision_audit_org_type_created",
            "ix_decision_audit_entity",
            "ix_decision_audit_created_at",
            "ix_decision_audit_maker",
            "ix_decision_audit_org_id",
            "ix_audit_retention_org_unique",
            "ix_archived_audit_org_loan",
            "ix_archived_audit_created_at",
            "ix_archived_audit_original_id",
        ]
        for idx in index_names:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                print(f"  Dropped index {idx}")
            except Exception as e:
                print(f"  Could not drop index {idx}: {e}")

        # Drop tables in reverse dependency order
        for tbl in ["archived_decision_audit_logs", "audit_retention_configs", "decision_audit_logs"]:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
            print(f"  Dropped table {tbl}")

        conn.commit()

    print("Rollback completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
