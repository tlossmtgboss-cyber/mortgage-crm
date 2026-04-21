#!/usr/bin/env python3
"""
Alembic Stamp Head — Mark existing databases as up-to-date
Perennia AI

PURPOSE:
    When adopting Alembic on a project that already has a production database,
    you need to tell Alembic "the current schema is already at the latest
    migration" WITHOUT actually running any migration SQL.

    `alembic stamp head` creates the alembic_version table and inserts the
    current head revision hash. After stamping, future `alembic upgrade head`
    calls will only run NEW migrations created after the stamp point.

WHEN TO USE THIS:
    Run this ONCE on every existing environment (production, staging, local dev)
    that already has the schema created by init_db.py. You do NOT need to run
    this on fresh databases — those should use `alembic upgrade head` instead.

PROCEDURE:
    1. Ensure DATABASE_URL is set in the environment:
           export DATABASE_URL=postgresql://user:pass@host:5432/dbname

    2. Run this script from the backend/ directory:
           cd backend && python scripts/alembic_stamp_head.py

       Or equivalently:
           cd backend && python scripts/migrate.py stamp head

       Or directly with alembic:
           cd backend && alembic stamp head

    3. Verify the stamp worked:
           cd backend && alembic current
       Expected output: the latest revision hash followed by "(head)"

    4. Repeat for each environment (production, staging, dev).

WHAT THIS DOES:
    - Creates the `alembic_version` table if it doesn't exist
    - Inserts a single row with the current head revision hash
    - Does NOT execute any upgrade() or downgrade() functions
    - Does NOT modify any application tables

WHAT THIS DOES NOT DO:
    - Does NOT run any migration SQL — your existing schema is untouched
    - Does NOT generate any new migration files
    - Does NOT connect to any environment automatically — you must set DATABASE_URL

AFTER STAMPING:
    - New schema changes should be created as Alembic migrations:
          python scripts/migrate.py generate "add_xyz_column"
    - Review the generated file in alembic/versions/ before applying
    - Apply with: python scripts/migrate.py upgrade
    - The existing init_db.py continues to handle initial schema creation
      for brand-new databases; Alembic handles incremental changes after that
"""

import os
import sys

# Ensure we're running from the backend directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_this_dir)

if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

os.chdir(_backend_dir)

from alembic.config import Config
from alembic import command


def main():
    # Validate DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print(
            "ERROR: DATABASE_URL environment variable is not set.\n"
            "\n"
            "Set it before running this script:\n"
            "  export DATABASE_URL=postgresql://user:pass@host:5432/dbname\n"
            "\n"
            "For Railway production, copy the DATABASE_URL from the Railway dashboard.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Mask password for display
    display_url = db_url
    if "@" in display_url:
        pre_at = display_url.split("@")[0]
        post_at = display_url.split("@", 1)[1]
        if ":" in pre_at:
            scheme_user = pre_at.rsplit(":", 1)[0]
            display_url = f"{scheme_user}:****@{post_at}"

    print(f"Database: {display_url}")
    print()

    # Load alembic config
    ini_path = os.path.join(_backend_dir, "alembic.ini")
    if not os.path.exists(ini_path):
        print(f"ERROR: alembic.ini not found at {ini_path}", file=sys.stderr)
        sys.exit(1)

    cfg = Config(ini_path)

    # Show current state before stamping
    print("Current migration state:")
    try:
        command.current(cfg, verbose=True)
    except Exception as e:
        print(f"  (no alembic_version table yet — this is expected: {e})")
    print()

    # Stamp head
    print("Stamping database as HEAD (current migration chain tip)...")
    command.stamp(cfg, "head")
    print()

    # Verify
    print("Verification — current state after stamp:")
    command.current(cfg, verbose=True)
    print()
    print("Done. This database is now tracked by Alembic.")
    print("Future migrations created with `python scripts/migrate.py generate \"msg\"`")
    print("will be applied with `python scripts/migrate.py upgrade`.")


if __name__ == "__main__":
    main()
