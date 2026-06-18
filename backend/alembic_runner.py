"""
Alembic Head Canary

Checks whether the running DB is at the Alembic head revision and emits a
CRITICAL log warning if it is behind.  It does NOT run migrations.

The authoritative migration path is:
    start.py  →  run_migrations.py  (advisory-locked, exits non-zero on failure)

This canary is called from app_lifespan.py AFTER that path has already run.
Its job is purely diagnostic: catch any gap between what start.py applied and
what the app actually loaded.

Environment variable overrides:
    SKIP_ALEMBIC=true   — Skip the check entirely (escape hatch).
"""

import logging
import os

logger = logging.getLogger(__name__)


def check_alembic_head() -> bool:
    """Check whether the DB is at the Alembic head revision.

    Does NOT run migrations.  Returns True if DB is at head (or if the
    check cannot be performed), False if the DB is detectably behind head.

    Logs a CRITICAL warning when the DB is behind so operators are alerted
    without crashing the application.
    """
    if os.getenv("SKIP_ALEMBIC", "").lower() in ("true", "1", "yes"):
        logger.info("SKIP_ALEMBIC is set — skipping Alembic head check")
        return True

    if os.getenv("TESTING") == "1":
        logger.debug("TESTING=1 — skipping Alembic head check")
        return True

    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        # Resolve alembic.ini relative to this file (backend/)
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        if not os.path.exists(ini_path):
            logger.warning("alembic.ini not found at %s — skipping head check", ini_path)
            return True

        alembic_cfg = Config(ini_path)

        # Determine head revision from migration scripts (no DB access needed)
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script_dir.get_current_head()

        # Query DB for the current revision (read-only)
        from db import engine as _engine
        with _engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        if current_rev is None:
            # No alembic_version row at all — DB was likely stamped or bootstrapped
            # before Alembic, or the advisory-lock runner hasn't finished yet.
            logger.warning(
                "Alembic head check: no version stamp in DB "
                "(current=None, head=%s). start.py advisory-lock runner should "
                "have handled this — verify run_migrations.py output.",
                head_rev,
            )
            return False

        if current_rev == head_rev:
            logger.info("Alembic head check OK: DB is at head (%s)", head_rev)
            return True

        logger.critical(
            "Alembic head check FAILED: DB is at %r but head is %r. "
            "The advisory-lock migration runner (start.py → run_migrations.py) "
            "should have upgraded the DB before the app started. "
            "Check run_migrations.py exit code in deployment logs.",
            current_rev,
            head_rev,
        )
        return False

    except Exception as e:
        # Never crash the app over a canary check failure.
        logger.warning(
            "Alembic head check could not complete (app will continue): %s",
            e,
            exc_info=True,
        )
        return True


# ---------------------------------------------------------------------------
# Backward-compat shim — old callers that imported run_alembic_migrations()
# will get the read-only check instead of a write operation.
# ---------------------------------------------------------------------------
def run_alembic_migrations() -> bool:
    """Deprecated: use check_alembic_head() instead.

    This shim exists so that any external callers that imported
    ``run_alembic_migrations`` from this module continue to work without
    modifications.  It delegates to the read-only head check — it no longer
    runs ``alembic upgrade head``.
    """
    logger.warning(
        "run_alembic_migrations() is deprecated — delegating to check_alembic_head(). "
        "Migrations are now run exclusively by start.py → run_migrations.py."
    )
    return check_alembic_head()
