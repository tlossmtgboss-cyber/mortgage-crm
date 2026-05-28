"""
Programmatic Alembic Runner

Runs Alembic migrations at application startup.  Invoked from
app_lifespan.py BEFORE route registration and scheduler init.

Behavior:
1.  If no alembic_version table exists (fresh or pre-Alembic DB),
    stamps the DB at head so prior migrations are not re-run.
2.  Otherwise, runs ``alembic upgrade head`` to apply any pending
    migrations.
3.  Errors are logged but do NOT crash the application — production
    safety requires the app to start even if a migration fails.

Environment variable overrides:
    SKIP_ALEMBIC=true   — Skip Alembic entirely (escape hatch).
"""

import logging
import os

logger = logging.getLogger(__name__)

# The head revision that represents the baseline stamp.
# When stamping a DB that has never seen Alembic, we stamp to this.
_BASELINE_REVISION = "017_baseline_stamp"


def run_alembic_migrations() -> bool:
    """Run pending Alembic migrations.  Returns True on success."""

    if os.getenv("SKIP_ALEMBIC", "").lower() in ("true", "1", "yes"):
        logger.info("SKIP_ALEMBIC is set — skipping Alembic migrations")
        return True

    if os.getenv("TESTING") == "1":
        logger.debug("TESTING=1 — skipping Alembic migrations")
        return True

    try:
        from alembic.config import Config
        from alembic import command
        from sqlalchemy import text

        # Resolve alembic.ini relative to this file (backend/)
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        if not os.path.exists(ini_path):
            logger.error("alembic.ini not found at %s — skipping migrations", ini_path)
            return False

        alembic_cfg = Config(ini_path)

        # Determine whether the DB already has an alembic_version table.
        # If not, this is the first time Alembic is touching this DB.
        from db import engine as _engine
        needs_stamp = False
        try:
            with _engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )).fetchone()
                if result is None:
                    needs_stamp = True
                else:
                    # Table exists — check if it has any rows
                    row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                    if row is None:
                        needs_stamp = True
        except Exception as e:
            # If we can't even check (e.g. SQLite), just try upgrade
            logger.warning("Could not inspect alembic_version table: %s", e)

        if needs_stamp:
            logger.info(
                "No alembic_version found — stamping DB at baseline revision %s",
                _BASELINE_REVISION,
            )
            command.stamp(alembic_cfg, _BASELINE_REVISION)
            logger.info("Alembic baseline stamp complete")
            return True

        # Normal path: apply any pending migrations
        logger.info("Running Alembic upgrade head...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations complete")
        return True

    except Exception as e:
        logger.error(
            "Alembic migration failed (app will continue): %s",
            e,
            exc_info=True,
        )
        return False
