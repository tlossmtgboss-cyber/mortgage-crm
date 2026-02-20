"""Add GMI (Government Monitoring Information) demographic fields to borrower_applications

Revision ID: 011_gmi_demographics
Revises: 010_los_compliance
Create Date: 2026-02-19

ECOA (Equal Credit Opportunity Act) requires collection of Government Monitoring
Information (race, ethnicity, sex) on mortgage applications. These fields must be
stored separately from decisioning data.

HMDA (Home Mortgage Disclosure Act) requires reporting of applicant demographics
in the Loan Application Register (LAR) export.

New columns on borrower_applications:
    - applicant_ethnicity (String) - HMDA ethnicity code
    - applicant_race (String) - HMDA race code
    - applicant_sex (String) - HMDA sex code
    - applicant_age (Integer) - Applicant age at application
    - co_applicant_ethnicity (String)
    - co_applicant_race (String)
    - co_applicant_sex (String)
    - co_applicant_age (Integer)
    - gmi_collection_method (String) - face_to_face, telephone, mail_internet
    - gmi_collected_at (DateTime) - When GMI was collected

Also makes disclosure_events.sent_at nullable (pending disclosures have sent_at=None).

All fields are nullable (GMI is voluntary per ECOA).
Migration is idempotent (checks column existence before adding).
Supports both PostgreSQL and SQLite.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '011_gmi_demographics'
down_revision = '010_los_compliance'
branch_labels = None
depends_on = None


# ============================================================================
# Helper Functions (Dual PostgreSQL / SQLite support)
# ============================================================================

def _column_exists_pg(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table (PostgreSQL)."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :table_name
            AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def _table_exists_pg(conn, table_name: str) -> bool:
    """Check if a table exists (PostgreSQL)."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def _add_column_safe_pg(conn, table_name: str, column_name: str, column_type: str) -> bool:
    """Add a column if it doesn't already exist (PostgreSQL). Returns True if added."""
    if not _column_exists_pg(conn, table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, _sa_type(column_type), nullable=True))
        print(f"  Added {table_name}.{column_name} ({column_type})")
        return True
    else:
        print(f"  {table_name}.{column_name} already exists - skipping")
        return False


def _sa_type(type_str: str):
    """Convert a type string to a SQLAlchemy type object."""
    type_map = {
        "String": sa.String,
        "Integer": sa.Integer,
        "DateTime": sa.DateTime,
    }
    return type_map.get(type_str, sa.String)()


def _add_column_safe_sqlite(conn, table_name: str, column_name: str, sql_type: str) -> bool:
    """Add a column if it doesn't already exist (SQLite). Returns True if added."""
    try:
        conn.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))
        print(f"  Added {table_name}.{column_name} ({sql_type})")
        return True
    except Exception:
        print(f"  {table_name}.{column_name} already exists - skipping")
        return False


# ============================================================================
# GMI Columns to Add
# ============================================================================

# Format: (column_name, sa_type_string, sqlite_type_string)
GMI_COLUMNS = [
    ("applicant_ethnicity", "String", "VARCHAR"),
    ("applicant_race", "String", "VARCHAR"),
    ("applicant_sex", "String", "VARCHAR"),
    ("applicant_age", "Integer", "INTEGER"),
    ("co_applicant_ethnicity", "String", "VARCHAR"),
    ("co_applicant_race", "String", "VARCHAR"),
    ("co_applicant_sex", "String", "VARCHAR"),
    ("co_applicant_age", "Integer", "INTEGER"),
    ("gmi_collection_method", "String", "VARCHAR"),
    ("gmi_collected_at", "DateTime", "TIMESTAMP"),
]

TABLE_NAME = "borrower_applications"


# ============================================================================
# Upgrade
# ============================================================================

def upgrade() -> None:
    """Add GMI demographic fields to borrower_applications and fix disclosure_events.sent_at."""
    bind = op.get_bind()

    if bind.dialect.name == 'sqlite':
        _upgrade_sqlite(bind)
    else:
        _upgrade_postgres(bind)

    print("GMI demographics migration complete")


def _upgrade_postgres(conn) -> None:
    """PostgreSQL upgrade path."""
    # Add GMI columns to borrower_applications
    if _table_exists_pg(conn, TABLE_NAME):
        print(f"Adding GMI demographic columns to {TABLE_NAME}:")
        for col_name, sa_type, _ in GMI_COLUMNS:
            _add_column_safe_pg(conn, TABLE_NAME, col_name, sa_type)
    else:
        print(f"Table {TABLE_NAME} not found - skipping GMI columns")

    # Fix disclosure_events.sent_at to be nullable (for pending disclosures)
    if _table_exists_pg(conn, 'disclosure_events'):
        if _column_exists_pg(conn, 'disclosure_events', 'sent_at'):
            try:
                conn.execute(sa.text(
                    "ALTER TABLE disclosure_events ALTER COLUMN sent_at DROP NOT NULL"
                ))
                print("  Made disclosure_events.sent_at nullable (for pending disclosures)")
            except Exception as e:
                print(f"  disclosure_events.sent_at nullable change skipped: {e}")


def _upgrade_sqlite(conn) -> None:
    """SQLite upgrade path."""
    print(f"SQLite detected - adding GMI columns to {TABLE_NAME}:")
    for col_name, _, sqlite_type in GMI_COLUMNS:
        _add_column_safe_sqlite(conn, TABLE_NAME, col_name, sqlite_type)

    # SQLite doesn't enforce NOT NULL constraints the same way;
    # sent_at is already effectively nullable in SQLite


# ============================================================================
# Downgrade
# ============================================================================

def downgrade() -> None:
    """Remove GMI demographic columns from borrower_applications."""
    bind = op.get_bind()

    if bind.dialect.name == 'sqlite':
        print("SQLite does not support DROP COLUMN reliably - skipping downgrade")
        return

    if _table_exists_pg(bind, TABLE_NAME):
        for col_name, _, _ in GMI_COLUMNS:
            if _column_exists_pg(bind, TABLE_NAME, col_name):
                op.drop_column(TABLE_NAME, col_name)
                print(f"  Dropped {TABLE_NAME}.{col_name}")

    # Re-add NOT NULL to disclosure_events.sent_at
    if _table_exists_pg(bind, 'disclosure_events'):
        if _column_exists_pg(bind, 'disclosure_events', 'sent_at'):
            try:
                # Set any NULL sent_at to now() before adding constraint
                bind.execute(sa.text(
                    "UPDATE disclosure_events SET sent_at = created_at WHERE sent_at IS NULL"
                ))
                bind.execute(sa.text(
                    "ALTER TABLE disclosure_events ALTER COLUMN sent_at SET NOT NULL"
                ))
            except Exception as e:
                print(f"  Could not restore sent_at NOT NULL: {e}")

    print("GMI demographics downgrade complete")
