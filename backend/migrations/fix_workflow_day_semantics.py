"""
Migration: Fix Workflow Day Semantics

This migration fixes a semantic design flaw where "First 24 Hours" was
configured with day_value=1, causing tasks to fire AFTER 24 hours elapsed.

The fix:
1. Changes "First 24 Hours" entries to day_value=0 (immediate)
2. Backdates test instance 6 for immediate testing

Run with:
    python -m migrations.fix_workflow_day_semantics

Or import and call run_migration(db) from startup.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def run_migration(db: Session = None) -> dict:
    """
    Run the workflow day semantics fix migration.

    Args:
        db: Optional SQLAlchemy session. If not provided, creates a new connection.

    Returns:
        dict with migration results
    """
    results = {
        'success': True,
        'before_state': [],
        'after_state': [],
        'rows_updated': 0,
        'instance_backdated': False,
        'errors': [],
        'warnings': []
    }

    # Read the SQL migration file
    migration_dir = Path(__file__).parent
    sql_file = migration_dir / 'fix_workflow_day_semantics.sql'

    if not sql_file.exists():
        results['success'] = False
        results['errors'].append(f"SQL file not found: {sql_file}")
        return results

    with open(sql_file, 'r') as f:
        sql_content = f.read()

    # Execute migration
    if db is not None:
        # Use provided session
        try:
            _execute_migration(db, sql_content, results)
            db.commit()
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            results['success'] = False
            results['errors'].append(str(e))
            db.rollback()
    else:
        # Create new connection
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            try:
                _execute_migration(conn, sql_content, results)
                conn.commit()
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                results['success'] = False
                results['errors'].append(str(e))
                conn.rollback()
                raise

    return results


def _execute_migration(conn, sql_content: str, results: dict):
    """Execute the SQL migration and track results."""

    # Step 1: Capture BEFORE state
    logger.info("Capturing before state...")
    before_result = conn.execute(text("""
        SELECT
            wc.name as workflow_name,
            wdc.id as config_id,
            wdc.day_value,
            wdc.day_label,
            wdc.status_label
        FROM workflow_day_configs wdc
        JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
        WHERE wdc.day_label ILIKE '%24 Hour%'
           OR wdc.day_label ILIKE '%First%'
           OR wdc.day_value IN (0, 1)
        ORDER BY wc.name, wdc.day_value
    """))

    results['before_state'] = [dict(row._mapping) for row in before_result]
    logger.info(f"Found {len(results['before_state'])} day configs to analyze")

    # Step 2: Execute the SQL migration
    logger.info("Executing migration SQL...")
    conn.execute(text(sql_content))

    # Step 3: Capture AFTER state
    logger.info("Capturing after state...")
    after_result = conn.execute(text("""
        SELECT
            wc.name as workflow_name,
            wdc.id as config_id,
            wdc.day_value,
            wdc.day_label,
            wdc.status_label
        FROM workflow_day_configs wdc
        JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
        WHERE wdc.day_label ILIKE '%24 Hour%'
           OR wdc.day_label ILIKE '%First%'
           OR wdc.day_value IN (0, 1)
        ORDER BY wc.name, wdc.day_value
    """))

    results['after_state'] = [dict(row._mapping) for row in after_result]

    # Step 4: Calculate changes
    before_ids = {row['config_id']: row['day_value'] for row in results['before_state']}
    after_ids = {row['config_id']: row['day_value'] for row in results['after_state']}

    changed_count = sum(1 for cid in before_ids if before_ids[cid] != after_ids.get(cid))
    results['rows_updated'] = changed_count

    # Step 5: Verify instance 6 was backdated
    instance_result = conn.execute(text("""
        SELECT
            id,
            trigger_milestone_entered_at,
            last_task_generated_day,
            status,
            EXTRACT(EPOCH FROM (NOW() - trigger_milestone_entered_at)) / 86400 as days_since_trigger
        FROM workflow_instances
        WHERE id = 6
    """))

    instance_row = instance_result.fetchone()
    if instance_row:
        days_since = instance_row._mapping.get('days_since_trigger', 0)
        results['instance_backdated'] = days_since >= 1.9  # Should be ~2 days
        results['instance_6_details'] = dict(instance_row._mapping)
        logger.info(f"Instance 6: {days_since:.2f} days since trigger")
    else:
        results['warnings'].append("Instance 6 not found")

    # Step 6: Log summary
    logger.info(f"Migration complete: {results['rows_updated']} day configs updated")
    logger.info(f"Instance 6 backdated: {results['instance_backdated']}")


def verify_fix(db: Session = None) -> dict:
    """
    Verify the migration was applied correctly.

    Returns dict with verification results.
    """
    verification = {
        'day_configs_correct': False,
        'instance_6_eligible': False,
        'full_timeline': [],
        'issues': []
    }

    if db is None:
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()
    else:
        conn = db

    try:
        # Check 1: Verify "First 24 Hours" entries have day_value=0
        result = conn.execute(text("""
            SELECT
                wc.name as workflow_name,
                wdc.day_value,
                wdc.day_label
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE wdc.day_label ILIKE '%First 24 Hour%'
               OR wdc.day_label ILIKE '%First%24%Hour%'
        """))

        first_24_configs = [dict(row._mapping) for row in result]

        if first_24_configs:
            all_day_zero = all(c['day_value'] == 0 for c in first_24_configs)
            verification['day_configs_correct'] = all_day_zero
            if not all_day_zero:
                bad_configs = [c for c in first_24_configs if c['day_value'] != 0]
                verification['issues'].append(f"Found {len(bad_configs)} 'First 24 Hours' configs with day_value != 0")
        else:
            verification['issues'].append("No 'First 24 Hours' day configs found")

        # Check 2: Verify instance 6 is eligible for task generation
        result = conn.execute(text("""
            SELECT
                wi.id,
                wi.trigger_milestone_entered_at,
                wi.last_task_generated_day,
                wi.status,
                EXTRACT(EPOCH FROM (NOW() - wi.trigger_milestone_entered_at)) / 86400 as days_elapsed,
                wc.name as workflow_name
            FROM workflow_instances wi
            JOIN workflow_configurations wc ON wi.workflow_configuration_id = wc.id
            WHERE wi.id = 6
        """))

        instance = result.fetchone()
        if instance:
            instance_data = dict(instance._mapping)
            days_elapsed = instance_data.get('days_elapsed', 0)
            verification['instance_6_eligible'] = (
                instance_data['status'] == 'active' and
                days_elapsed >= 1
            )
            verification['instance_6_details'] = instance_data
        else:
            verification['issues'].append("Instance 6 not found")

        # Check 3: Show full prospect workflow timeline
        result = conn.execute(text("""
            SELECT
                wdc.day_value,
                wdc.day_label,
                wdc.status_label,
                wdc.phone_enabled,
                wdc.email_enabled,
                wdc.text_enabled
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE wc.name = 'prospect'
            ORDER BY wdc.day_value
        """))

        verification['full_timeline'] = [dict(row._mapping) for row in result]

        # Check 4: Count tasks that would be generated for instance 6
        if verification.get('instance_6_details'):
            days_elapsed = int(verification['instance_6_details'].get('days_elapsed', 0))
            result = conn.execute(text("""
                SELECT
                    wdc.day_value,
                    wdc.day_label,
                    COUNT(*) FILTER (WHERE wdc.phone_enabled) as phone_tasks,
                    COUNT(*) FILTER (WHERE wdc.email_enabled) as email_tasks,
                    COUNT(*) FILTER (WHERE wdc.text_enabled) as text_tasks
                FROM workflow_day_configs wdc
                JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
                WHERE wc.name = 'prospect'
                  AND wdc.day_value <= :days_elapsed
                GROUP BY wdc.day_value, wdc.day_label
                ORDER BY wdc.day_value
            """), {'days_elapsed': days_elapsed})

            verification['eligible_days'] = [dict(row._mapping) for row in result]

    finally:
        if db is None:
            conn.close()

    return verification


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Fix workflow day semantics migration')
    parser.add_argument('--check', action='store_true', help='Verify migration status without applying')
    parser.add_argument('--dry-run', action='store_true', help='Parse SQL but do not execute')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    args = parser.parse_args()

    if args.check:
        print("Verifying migration status...")
        verification = verify_fix()

        if args.json:
            print(json.dumps(verification, indent=2, default=str))
        else:
            print("\n=== Migration Verification ===")
            print(f"Day configs correct (First 24 Hours = day 0): {verification['day_configs_correct']}")
            print(f"Instance 6 eligible for tasks: {verification['instance_6_eligible']}")

            if verification.get('instance_6_details'):
                details = verification['instance_6_details']
                print(f"\nInstance 6 Details:")
                print(f"  - Status: {details.get('status')}")
                print(f"  - Days elapsed: {details.get('days_elapsed', 0):.2f}")
                print(f"  - Last generated day: {details.get('last_task_generated_day')}")

            if verification.get('full_timeline'):
                print(f"\nProspect Workflow Timeline:")
                for day in verification['full_timeline']:
                    channels = []
                    if day['phone_enabled']: channels.append('phone')
                    if day['email_enabled']: channels.append('email')
                    if day['text_enabled']: channels.append('text')
                    print(f"  Day {day['day_value']}: {day['day_label']} [{', '.join(channels)}]")

            if verification.get('eligible_days'):
                print(f"\nDays eligible for task generation:")
                for day in verification['eligible_days']:
                    print(f"  Day {day['day_value']}: {day['phone_tasks']} phone, {day['email_tasks']} email, {day['text_tasks']} text")

            if verification['issues']:
                print(f"\nIssues found:")
                for issue in verification['issues']:
                    print(f"  - {issue}")

        sys.exit(0 if verification['day_configs_correct'] and verification['instance_6_eligible'] else 1)

    if args.dry_run:
        print("Dry run - parsing SQL only...")
        migration_dir = Path(__file__).parent
        sql_file = migration_dir / 'fix_workflow_day_semantics.sql'
        if sql_file.exists():
            with open(sql_file, 'r') as f:
                content = f.read()
            print(f"SQL file loaded: {len(content)} characters")
            print("Dry run complete - no changes made")
        else:
            print(f"ERROR: SQL file not found: {sql_file}")
            sys.exit(1)
        sys.exit(0)

    print("Running workflow day semantics fix migration...")
    try:
        results = run_migration()

        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print("\n=== Migration Results ===")
            print(f"Success: {results['success']}")
            print(f"Day configs updated: {results['rows_updated']}")
            print(f"Instance 6 backdated: {results['instance_backdated']}")

            if results['before_state']:
                print(f"\nBefore state ({len(results['before_state'])} configs):")
                for config in results['before_state'][:5]:  # Show first 5
                    print(f"  - {config['workflow_name']}: Day {config['day_value']} = {config['day_label']}")

            if results['after_state']:
                print(f"\nAfter state ({len(results['after_state'])} configs):")
                for config in results['after_state'][:5]:
                    print(f"  - {config['workflow_name']}: Day {config['day_value']} = {config['day_label']}")

            if results.get('instance_6_details'):
                print(f"\nInstance 6 details:")
                details = results['instance_6_details']
                print(f"  - Days since trigger: {details.get('days_since_trigger', 0):.2f}")
                print(f"  - Status: {details.get('status')}")

            if results['warnings']:
                print(f"\nWarnings:")
                for warning in results['warnings']:
                    print(f"  - {warning}")

            if results['errors']:
                print(f"\nErrors:")
                for error in results['errors']:
                    print(f"  - {error}")
                sys.exit(1)

            print("\nMigration completed successfully!")
            print("\n=== Next Steps ===")
            print("1. Wait 5 min for scheduler OR call: POST /api/v1/workflow-sla/init/generate-tasks")
            print("2. Check tasks: GET /api/v1/workflow-sla/diagnostic/6")
            print("3. Verify tasks in database:")
            print("   SELECT * FROM workflow_task_instances WHERE workflow_instance_id = 6;")

    except Exception as e:
        print(f"\nMigration failed: {e}")
        sys.exit(1)
