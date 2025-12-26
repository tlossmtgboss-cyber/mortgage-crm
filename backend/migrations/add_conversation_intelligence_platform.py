"""
Migration: Add Conversation Intelligence Platform Tables

This migration creates all tables needed for the Conversation Intelligence Platform:
- Call recordings and transcriptions
- QA scoring with rubrics
- Real-time assist
- Coaching workflows
- Compliance monitoring
- Agent metrics

Run with: python -m migrations.add_conversation_intelligence_platform
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from sqlalchemy import text


def run_sql_file(db_engine, filepath: str):
    """Execute a SQL file."""
    with open(filepath, 'r') as f:
        sql = f.read()

    # Split by statements (handle complex SQL with functions)
    # We'll execute the whole file as one transaction
    with db_engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print(f"✓ Executed: {filepath}")


def run_migration():
    """Run the conversation intelligence platform migration."""
    print("=" * 60)
    print("Conversation Intelligence Platform Migration")
    print("=" * 60)

    migrations_dir = Path(__file__).parent

    # Run schema migration
    schema_file = migrations_dir / "add_conversation_intelligence_platform.sql"
    if schema_file.exists():
        print(f"\nRunning schema migration...")
        try:
            run_sql_file(engine, str(schema_file))
        except Exception as e:
            print(f"Schema migration error: {e}")
            # Try statement by statement
            print("Attempting statement-by-statement execution...")
            run_migration_statements(engine, str(schema_file))
    else:
        print(f"Schema file not found: {schema_file}")
        return False

    # Run seed data
    seed_file = migrations_dir / "seed_mortgage_qa_rubrics.sql"
    if seed_file.exists():
        print(f"\nRunning seed data...")
        try:
            run_sql_file(engine, str(seed_file))
        except Exception as e:
            print(f"Seed data error: {e}")
            print("Attempting INSERT-by-INSERT execution...")
            run_seed_statements(engine, str(seed_file))
    else:
        print(f"Seed file not found: {seed_file}")

    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)
    return True


def run_seed_statements(db_engine, filepath: str):
    """Execute seed file by splitting on INSERT INTO for better handling."""
    with open(filepath, 'r') as f:
        sql = f.read()

    # Split by INSERT INTO to handle multi-value INSERTs
    parts = sql.split('INSERT INTO')
    success_count = 0
    error_count = 0

    with db_engine.connect() as conn:
        for i, part in enumerate(parts[1:], 1):  # Skip first empty part
            try:
                # Reconstruct the INSERT statement
                stmt = 'INSERT INTO' + part.rstrip().rstrip(';')
                conn.execute(text(stmt))
                success_count += 1
                print(f"  INSERT {i}: OK")
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                if "duplicate key" in error_msg.lower():
                    print(f"  INSERT {i}: SKIPPED (already exists)")
                else:
                    print(f"  INSERT {i}: ERROR - {error_msg[:80]}")
        conn.commit()

    print(f"  Seed complete: {success_count} succeeded, {error_count} failed/skipped")


def run_migration_statements(db_engine, filepath: str):
    """Execute SQL file statement by statement for better error handling."""

    with open(filepath, 'r') as f:
        sql = f.read()

    # Remove comments and split carefully
    statements = []
    current = []
    in_function = False

    for line in sql.split('\n'):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith('--'):
            continue

        # Track function blocks
        if 'CREATE OR REPLACE FUNCTION' in line or 'CREATE FUNCTION' in line:
            in_function = True

        current.append(line)

        # End of statement
        if stripped.endswith(';') and not in_function:
            statements.append('\n'.join(current))
            current = []
        elif in_function and stripped == '$$ LANGUAGE plpgsql;':
            in_function = False
            statements.append('\n'.join(current))
            current = []

    # Execute each statement
    with db_engine.connect() as conn:
        for i, stmt in enumerate(statements):
            try:
                if stmt.strip():
                    conn.execute(text(stmt))
                    print(f"  Statement {i+1}/{len(statements)}: OK")
            except Exception as e:
                print(f"  Statement {i+1}/{len(statements)}: ERROR - {str(e)[:100]}")
        conn.commit()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
