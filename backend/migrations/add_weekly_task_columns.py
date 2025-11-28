"""
Migration: Add Weekly Task Scheduling Columns to WorkflowDayConfig

This migration adds columns to support weekly recurring tasks:
- repeat_weekly: Boolean flag to mark tasks as weekly recurring
- repeat_day_of_week: Integer (0=Monday, 6=Sunday) for which day to send
- repeat_until_status: JSON array of statuses that stop the recurrence

Business Rules:
- Monday Weekly Update: First update goes out on the Monday FOLLOWING the
  LE Pending date entry (not same day if added on Monday)
- Tasks repeat until loan is closed, canceled, withdrawn, or denied
"""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_migration(db: Session) -> dict:
    """
    Add weekly task scheduling columns to workflow_day_configs table.
    """
    results = {
        'success': True,
        'columns_added': [],
        'errors': []
    }

    try:
        # Check if columns already exist
        check_sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'workflow_day_configs'
        AND column_name IN ('repeat_weekly', 'repeat_day_of_week', 'repeat_until_status')
        """
        existing = db.execute(text(check_sql)).fetchall()
        existing_columns = [row[0] for row in existing]

        # Add repeat_weekly column if not exists
        if 'repeat_weekly' not in existing_columns:
            db.execute(text("""
                ALTER TABLE workflow_day_configs
                ADD COLUMN repeat_weekly BOOLEAN DEFAULT FALSE
            """))
            results['columns_added'].append('repeat_weekly')
            logger.info("Added repeat_weekly column")

        # Add repeat_day_of_week column if not exists
        if 'repeat_day_of_week' not in existing_columns:
            db.execute(text("""
                ALTER TABLE workflow_day_configs
                ADD COLUMN repeat_day_of_week INTEGER
            """))
            results['columns_added'].append('repeat_day_of_week')
            logger.info("Added repeat_day_of_week column")

        # Add repeat_until_status column if not exists
        if 'repeat_until_status' not in existing_columns:
            db.execute(text("""
                ALTER TABLE workflow_day_configs
                ADD COLUMN repeat_until_status JSONB DEFAULT '[]'::jsonb
            """))
            results['columns_added'].append('repeat_until_status')
            logger.info("Added repeat_until_status column")

        db.commit()

        if results['columns_added']:
            logger.info(f"Migration complete. Added columns: {results['columns_added']}")
        else:
            logger.info("Migration complete. All columns already exist.")
            results['message'] = "All columns already exist"

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        results['success'] = False
        results['errors'].append(str(e))
        db.rollback()

    return results


def update_existing_monday_tasks(db: Session) -> dict:
    """
    Update existing Monday Weekly Update tasks to have repeat_weekly enabled.

    This finds tasks with 'Monday' in the day_label that are email tasks
    and sets them up for weekly recurrence.
    """
    results = {
        'success': True,
        'tasks_updated': 0,
        'errors': []
    }

    try:
        # Find and update Monday email tasks
        update_sql = """
        UPDATE workflow_day_configs
        SET
            repeat_weekly = TRUE,
            repeat_day_of_week = 0,
            repeat_until_status = '["closed", "canceled", "withdrawn", "denied", "funded"]'::jsonb
        WHERE
            LOWER(day_label) LIKE '%monday%'
            AND email_enabled = TRUE
            AND (repeat_weekly IS NULL OR repeat_weekly = FALSE)
        """
        result = db.execute(text(update_sql))
        results['tasks_updated'] = result.rowcount if hasattr(result, 'rowcount') else 0

        # Also update Tuesday survey tasks
        update_tuesday_sql = """
        UPDATE workflow_day_configs
        SET
            repeat_weekly = TRUE,
            repeat_day_of_week = 1,
            repeat_until_status = '["closed", "canceled", "withdrawn", "denied", "funded"]'::jsonb
        WHERE
            LOWER(day_label) LIKE '%tuesday%'
            AND (LOWER(day_label) LIKE '%survey%' OR LOWER(day_label) LIKE '%text%')
            AND (repeat_weekly IS NULL OR repeat_weekly = FALSE)
        """
        result = db.execute(text(update_tuesday_sql))
        results['tasks_updated'] += result.rowcount if hasattr(result, 'rowcount') else 0

        db.commit()
        logger.info(f"Updated {results['tasks_updated']} existing weekly tasks")

    except Exception as e:
        logger.error(f"Failed to update existing tasks: {e}")
        results['success'] = False
        results['errors'].append(str(e))
        db.rollback()

    return results
