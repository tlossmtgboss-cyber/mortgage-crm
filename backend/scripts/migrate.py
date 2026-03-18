#!/usr/bin/env python3
"""
Alembic migration helper script — Perennia AI

Usage:
    python scripts/migrate.py upgrade          # Run all pending migrations
    python scripts/migrate.py upgrade +1       # Run one migration forward
    python scripts/migrate.py downgrade -1     # Roll back one migration
    python scripts/migrate.py downgrade <rev>  # Roll back to specific revision
    python scripts/migrate.py current          # Show current migration state
    python scripts/migrate.py history          # Show migration history
    python scripts/migrate.py heads            # Show current head revision(s)
    python scripts/migrate.py generate "msg"   # Generate new autogenerate migration
    python scripts/migrate.py stamp head       # Stamp DB as current head (no-op migration)
    python scripts/migrate.py check            # Check if DB is up to date (exit 1 if not)

Environment:
    DATABASE_URL  — Required. PostgreSQL connection string.

Notes:
    - This script must be run from the backend/ directory (or with cwd set there)
      so that Alembic can find alembic.ini and the alembic/ package.
    - The existing init_db.py handles initial schema creation. Alembic handles
      incremental changes after that.
"""

import os
import sys

# Ensure we're running from the backend directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_this_dir)

# Add backend to sys.path so that `from database import Base` works in env.py
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Change working directory to backend/ so alembic.ini is found
os.chdir(_backend_dir)

from alembic.config import Config
from alembic import command


def _get_alembic_config() -> Config:
    """Build Alembic Config pointing at backend/alembic.ini."""
    ini_path = os.path.join(_backend_dir, "alembic.ini")
    if not os.path.exists(ini_path):
        print(f"ERROR: alembic.ini not found at {ini_path}", file=sys.stderr)
        sys.exit(1)

    cfg = Config(ini_path)
    return cfg


def upgrade(revision: str = "head") -> None:
    """Run pending migrations up to the given revision (default: head)."""
    cfg = _get_alembic_config()
    print(f"Upgrading database to revision: {revision}")
    command.upgrade(cfg, revision)
    print("Upgrade complete.")


def downgrade(revision: str = "-1") -> None:
    """Roll back to the given revision (default: one step back)."""
    cfg = _get_alembic_config()
    print(f"Downgrading database to revision: {revision}")
    command.downgrade(cfg, revision)
    print("Downgrade complete.")


def current() -> None:
    """Show the current migration revision stamped in the database."""
    cfg = _get_alembic_config()
    command.current(cfg, verbose=True)


def history() -> None:
    """Show the full migration history."""
    cfg = _get_alembic_config()
    command.history(cfg, verbose=True)


def heads() -> None:
    """Show the current head revision(s)."""
    cfg = _get_alembic_config()
    command.heads(cfg, verbose=True)


def generate(message: str) -> None:
    """Generate a new migration using autogenerate.

    Compares the current database schema against the SQLAlchemy models
    and produces a migration script with the detected differences.
    """
    if not message:
        print("ERROR: Migration message is required.", file=sys.stderr)
        print("Usage: python scripts/migrate.py generate \"description here\"", file=sys.stderr)
        sys.exit(1)

    cfg = _get_alembic_config()
    print(f"Generating migration: {message}")
    command.revision(cfg, message=message, autogenerate=True)
    print("Migration file generated. Review it before running upgrade.")


def stamp(revision: str = "head") -> None:
    """Stamp the database with a revision without running migrations.

    Useful for marking an existing database as up-to-date with the
    current migration head (e.g., after initial schema creation via init_db.py).
    """
    cfg = _get_alembic_config()
    print(f"Stamping database as revision: {revision}")
    command.stamp(cfg, revision)
    print("Stamp complete.")


def check() -> None:
    """Check if the database is up to date with the latest migration.

    Exits with code 0 if up to date, code 1 if migrations are pending.
    """
    cfg = _get_alembic_config()
    try:
        command.check(cfg)
        print("Database is up to date.")
    except SystemExit:
        raise
    except Exception as e:
        print(f"Database is NOT up to date: {e}", file=sys.stderr)
        sys.exit(1)


def _print_usage():
    print(__doc__)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        _print_usage()

    cmd = sys.argv[1].lower()
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    # Validate DATABASE_URL is set for commands that need it
    if cmd not in ("help", "--help", "-h"):
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print(
                "ERROR: DATABASE_URL environment variable is not set.\n"
                "Set it before running migrations:\n"
                "  export DATABASE_URL=postgresql://user:pass@host:5432/dbname",
                file=sys.stderr,
            )
            sys.exit(1)

    commands = {
        "upgrade": lambda: upgrade(arg or "head"),
        "downgrade": lambda: downgrade(arg or "-1"),
        "current": current,
        "history": history,
        "heads": heads,
        "generate": lambda: generate(arg or ""),
        "stamp": lambda: stamp(arg or "head"),
        "check": check,
        "help": _print_usage,
        "--help": _print_usage,
        "-h": _print_usage,
    }

    handler = commands.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}\n", file=sys.stderr)
        _print_usage()

    handler()


if __name__ == "__main__":
    main()
