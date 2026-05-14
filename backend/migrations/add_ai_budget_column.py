"""
Migration: Add ai_daily_budget_usd column to organizations table.

This column stores the per-org daily AI spending limit (USD).
NULL means unlimited (no budget enforcement).
Default is $50.00 per day.

Usage:
    cd backend
    python migrations/add_ai_budget_column.py

Idempotent — safe to re-run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def get_engine():
    """Create engine from DATABASE_URL."""
    url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url)


def run_migration():
    """Add ai_daily_budget_usd column to organizations table."""
    engine = get_engine()

    with engine.begin() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'organizations'
              AND column_name = 'ai_daily_budget_usd'
        """))

        if result.fetchone():
            print("Column 'ai_daily_budget_usd' already exists on 'organizations' — skipping.")
            return

        # Add the column
        conn.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN ai_daily_budget_usd NUMERIC(10, 2) DEFAULT 50.00
        """))
        print("Added 'ai_daily_budget_usd' column to 'organizations' table (default=$50.00).")


if __name__ == "__main__":
    run_migration()
