"""
Migration Squash Utility

Generates a single baseline schema SQL from the current SQLAlchemy models,
replacing the 257 individual migration files.

Usage:
    # Generate baseline SQL (dry run — prints to stdout):
    python migrations/squash_migrations.py --dry-run

    # Generate baseline SQL file:
    python migrations/squash_migrations.py --output migrations/000_baseline_schema.sql

    # Verify current DB matches models (detect drift):
    python migrations/squash_migrations.py --verify

The generated baseline captures:
  - All 98 SQLAlchemy model tables (from database/models/)
  - All indexes and constraints defined in model __table_args__
  - Does NOT include: seed data, raw SQL tables, or runtime ALTER TABLEs

After generating the baseline:
  1. Move old migrations to migrations/_archive/
  2. Update init_db.py to run baseline + any post-baseline migrations
  3. New migrations go in migrations/ with sequential numbering
"""

import argparse
import logging
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def generate_baseline_ddl() -> str:
    """Generate CREATE TABLE DDL from all registered SQLAlchemy models."""
    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateTable, CreateIndex
    from db import Base

    # Import ALL models so they register with Base.metadata
    try:
        from database.models import (  # noqa: F401
            Organization, User, Lead, Loan, Task,
        )
    except ImportError as e:
        logger.warning(f"Some models failed to import: {e}")

    # Also import models that live outside database/models/
    model_modules = [
        "salesforce_integration_models",
        "models.user_integration",
        "models.smart_docs_models",
        "models.sms_models",
    ]
    for mod in model_modules:
        try:
            __import__(mod)
        except ImportError:
            pass

    # Use a PostgreSQL dialect for proper DDL
    pg_engine = create_engine("postgresql://", strategy="mock", executor=lambda *a, **kw: None)
    dialect = pg_engine.dialect

    lines = [
        "-- Perennia AI Mortgage CRM — Baseline Schema",
        f"-- Generated from {len(Base.metadata.tables)} SQLAlchemy models",
        "-- Replaces 257 individual migration files",
        "--",
        "-- Usage: psql $DATABASE_URL < 000_baseline_schema.sql",
        "",
        "BEGIN;",
        "",
    ]

    # Sort tables by dependency order
    sorted_tables = Base.metadata.sorted_tables

    for table in sorted_tables:
        try:
            create_stmt = CreateTable(table).compile(dialect=dialect)
            ddl = str(create_stmt).strip()
            # Add IF NOT EXISTS for safety
            ddl = ddl.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
            lines.append(ddl + ";")
            lines.append("")
        except Exception as e:
            lines.append(f"-- ERROR generating DDL for {table.name}: {e}")
            lines.append("")

    # Generate indexes separately (some are partial/conditional)
    lines.append("-- Indexes")
    for table in sorted_tables:
        for index in table.indexes:
            try:
                create_idx = CreateIndex(index).compile(dialect=dialect)
                idx_ddl = str(create_idx).strip()
                # Make idempotent
                idx_ddl = idx_ddl.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
                idx_ddl = idx_ddl.replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS", 1)
                lines.append(idx_ddl + ";")
            except Exception:
                pass  # Some indexes may not compile cleanly outside of a real connection

    lines.append("")
    lines.append("COMMIT;")

    return "\n".join(lines)


def verify_schema():
    """Compare model metadata against live database and report drift."""
    from sqlalchemy import inspect
    from db import Base, engine

    # Import models
    try:
        from database.models import Organization, User, Lead, Loan  # noqa: F401
    except ImportError:
        pass

    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables.keys())

    missing_in_db = model_tables - db_tables
    extra_in_db = db_tables - model_tables

    print(f"\n{'='*60}")
    print(f"Schema Verification Report")
    print(f"{'='*60}")
    print(f"Tables in models: {len(model_tables)}")
    print(f"Tables in database: {len(db_tables)}")
    print(f"Tables matching: {len(model_tables & db_tables)}")

    if missing_in_db:
        print(f"\n⚠️  Tables in models but NOT in database ({len(missing_in_db)}):")
        for t in sorted(missing_in_db):
            print(f"  - {t}")

    if extra_in_db:
        print(f"\nℹ️  Tables in database but NOT in models ({len(extra_in_db)}):")
        for t in sorted(extra_in_db)[:20]:
            print(f"  - {t}")
        if len(extra_in_db) > 20:
            print(f"  ... and {len(extra_in_db) - 20} more")

    # Check for column drift on key tables
    key_tables = ["leads", "loans", "users", "organizations", "tasks"]
    for table_name in key_tables:
        if table_name not in db_tables or table_name not in model_tables:
            continue

        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_table = Base.metadata.tables[table_name]
        model_cols = {c.name for c in model_table.columns}

        missing_cols = model_cols - db_cols
        extra_cols = db_cols - model_cols

        if missing_cols:
            print(f"\n⚠️  {table_name}: columns in model but NOT in DB: {sorted(missing_cols)}")
        if extra_cols and len(extra_cols) < 10:
            print(f"ℹ️  {table_name}: columns in DB but NOT in model: {sorted(extra_cols)}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Squash migrations into baseline schema")
    parser.add_argument("--dry-run", action="store_true", help="Print DDL to stdout")
    parser.add_argument("--output", type=str, help="Write DDL to file")
    parser.add_argument("--verify", action="store_true", help="Verify DB matches models")
    args = parser.parse_args()

    if args.verify:
        verify_schema()
        return

    ddl = generate_baseline_ddl()

    if args.output:
        with open(args.output, "w") as f:
            f.write(ddl)
        print(f"Baseline schema written to {args.output}")
        print(f"Next steps:")
        print(f"  1. mkdir -p migrations/_archive && mv migrations/add_*.py migrations/_archive/")
        print(f"  2. Update init_db.py to use {args.output}")
        print(f"  3. Test with: psql $TEST_DATABASE_URL < {args.output}")
    elif args.dry_run:
        print(ddl)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
