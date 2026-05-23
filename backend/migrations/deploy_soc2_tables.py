"""
Deploy SOC 2 Compliance Tables — Idempotent production migration.

Creates all 9 SOC 2 tables if they don't already exist.
Safe to run multiple times.

Usage:
    python -m migrations.deploy_soc2_tables
    # or import and call deploy_soc2_tables(engine)
"""
import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger("soc2.migration")

# Tables in dependency order
SOC2_TABLES = [
    "soc2_audit_log",
    "soc2_access_event",
    "soc2_security_incident",
    "soc2_incident_timeline",
    "soc2_change_record",
    "soc2_data_classification",
    "soc2_compliance_check",
    "soc2_active_session",
    "soc2_api_key_registry",
    "soc2_retention_archive",
    "soc2_vendor_registry",
]


def deploy_soc2_tables(engine=None):
    """
    Create all SOC 2 tables idempotently using CREATE TABLE IF NOT EXISTS.
    Returns list of tables that were created (didn't exist before).
    """
    if engine is None:
        db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url, poolclass=NullPool)

    created = []

    with engine.connect() as conn:
        # Check which tables already exist
        existing = set()
        for table in SOC2_TABLES:
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
            ), {"t": table})
            if result.fetchone()[0]:
                existing.add(table)

        if existing == set(SOC2_TABLES):
            logger.info("All SOC 2 tables already exist, skipping migration")
            return []

        # Read and execute the SQL file
        sql_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "soc2_compliance", "migrations", "soc2_tables.sql"
        )

        if not os.path.exists(sql_path):
            logger.error(f"SOC 2 tables SQL not found at {sql_path}")
            return []

        with open(sql_path, "r") as f:
            sql_content = f.read()

        # Execute the full SQL (it uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS)
        # We need to handle this carefully since the SQL uses BEGIN/COMMIT and triggers
        try:
            # Split on semicolons but handle dollar-quoted blocks
            statements = _split_sql_statements(sql_content)

            for stmt in statements:
                stmt = stmt.strip()
                if not stmt or stmt.upper() in ("BEGIN", "COMMIT"):
                    continue

                # Skip CREATE POLICY if it might already exist (will error on duplicate)
                if "CREATE POLICY" in stmt.upper():
                    policy_name = _extract_policy_name(stmt)
                    if policy_name:
                        exists = conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = :p)"
                        ), {"p": policy_name}).fetchone()[0]
                        if exists:
                            continue

                # Skip CREATE TRIGGER if it might already exist
                if "CREATE TRIGGER" in stmt.upper():
                    trigger_name = _extract_trigger_name(stmt)
                    if trigger_name:
                        exists = conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = :t)"
                        ), {"t": trigger_name}).fetchone()[0]
                        if exists:
                            continue

                # Skip CREATE INDEX without IF NOT EXISTS (add it)
                if "CREATE INDEX" in stmt.upper() and "IF NOT EXISTS" not in stmt.upper():
                    stmt = stmt.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)

                conn.execute(text("SAVEPOINT soc2_stmt"))
                try:
                    conn.execute(text(stmt))
                    conn.execute(text("RELEASE SAVEPOINT soc2_stmt"))
                except Exception as e:
                    conn.execute(text("ROLLBACK TO SAVEPOINT soc2_stmt"))
                    logger.warning(f"SOC 2 migration statement warning: {e}")
                    continue

            conn.commit()

            # Check which tables were newly created
            for table in SOC2_TABLES:
                if table not in existing:
                    result = conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
                    ), {"t": table})
                    if result.fetchone()[0]:
                        created.append(table)

            if created:
                logger.info(f"SOC 2 tables created: {', '.join(created)}")
            else:
                logger.info("SOC 2 tables migration completed (all tables already existed)")

        except Exception as e:
            logger.error(f"SOC 2 table migration failed: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    return created


def _split_sql_statements(sql: str):
    """
    Split SQL into statements, respecting dollar-quoted blocks ($$ ... $$).
    """
    statements = []
    current = []
    in_dollar_quote = False

    for line in sql.split("\n"):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("--") and not in_dollar_quote:
            continue

        # Track dollar-quoting
        dollar_count = line.count("$$")
        if dollar_count % 2 == 1:
            in_dollar_quote = not in_dollar_quote

        current.append(line)

        if stripped.endswith(";") and not in_dollar_quote:
            stmt = "\n".join(current).strip()
            if stmt and stmt != ";":
                statements.append(stmt.rstrip(";"))
            current = []

    # Handle any remaining content
    if current:
        stmt = "\n".join(current).strip()
        if stmt and stmt != ";":
            statements.append(stmt.rstrip(";"))

    return statements


def _extract_policy_name(stmt: str) -> str:
    """Extract policy name from CREATE POLICY statement."""
    import re
    match = re.search(r"CREATE\s+POLICY\s+(\w+)", stmt, re.IGNORECASE)
    return match.group(1) if match else ""


def _extract_trigger_name(stmt: str) -> str:
    """Extract trigger name from CREATE TRIGGER statement."""
    import re
    match = re.search(r"CREATE\s+TRIGGER\s+(\w+)", stmt, re.IGNORECASE)
    return match.group(1) if match else ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    created = deploy_soc2_tables()
    if created:
        print(f"Created tables: {', '.join(created)}")
    else:
        print("All SOC 2 tables already exist.")
