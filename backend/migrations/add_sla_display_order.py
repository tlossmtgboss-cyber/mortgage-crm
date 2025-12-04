"""
Migration: Add display_order column to sla_measures table

This migration adds the display_order column that was missing from the
database schema but is defined in the SLAMeasure model.
"""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_migration(db: Session) -> dict:
    """
    Add display_order column to sla_measures table.
    """
    results = {
        'success': True,
        'columns_added': [],
        'errors': []
    }

    try:
        # Check if column already exists
        check_sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'sla_measures'
        AND column_name = 'display_order'
        """
        existing = db.execute(text(check_sql)).fetchall()

        if not existing:
            db.execute(text("""
                ALTER TABLE sla_measures
                ADD COLUMN display_order INTEGER DEFAULT 0
            """))
            results['columns_added'].append('display_order')
            logger.info("Added display_order column to sla_measures table")
            db.commit()
        else:
            logger.info("display_order column already exists")
            results['message'] = "Column already exists"

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        results['success'] = False
        results['errors'].append(str(e))
        db.rollback()

    return results
