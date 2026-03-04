"""
Migration: Sync tasktype PostgreSQL enum with Python TaskType enum

Ensures all Python TaskType enum values exist in the PostgreSQL tasktype enum.
Uses ALTER TYPE ... ADD VALUE IF NOT EXISTS (PostgreSQL 9.3+).

This eliminates the need for dynamic enum resolution in ops_manager_agent.py.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Python TaskType values (from database/enums.py)
PYTHON_TASK_TYPE_VALUES = [
    "Human Needed",
    "Awaiting Review",
    "In Progress",
    "Completed",
]


def run_migration(engine):
    """Sync PostgreSQL tasktype enum with Python TaskType values."""
    with engine.connect() as conn:
        try:
            # Check if the tasktype enum exists
            result = conn.execute(text(
                "SELECT 1 FROM pg_type WHERE typname = 'tasktype'"
            )).fetchone()

            if not result:
                logger.info("Migration: tasktype enum does not exist, skipping sync")
                return

            # Get current DB enum values
            rows = conn.execute(text(
                "SELECT unnest(enum_range(NULL::tasktype)) as val"
            )).fetchall()
            db_values = {r[0] for r in rows}
            logger.info(f"Current tasktype DB values: {db_values}")

            # Add missing values
            added = []
            for py_val in PYTHON_TASK_TYPE_VALUES:
                if py_val not in db_values:
                    # ADD VALUE must run outside a transaction in PostgreSQL
                    # Use a separate connection for each ADD VALUE
                    try:
                        conn.execute(text(
                            f"ALTER TYPE tasktype ADD VALUE IF NOT EXISTS '{py_val}'"
                        ))
                        added.append(py_val)
                    except Exception as e:
                        logger.warning(f"Could not add tasktype value '{py_val}': {e}")

            conn.commit()

            if added:
                logger.info(f"Migration: Added tasktype values: {added}")
            else:
                logger.info("Migration: tasktype enum already in sync")

        except Exception as e:
            logger.warning(f"Migration: tasktype sync skipped: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
