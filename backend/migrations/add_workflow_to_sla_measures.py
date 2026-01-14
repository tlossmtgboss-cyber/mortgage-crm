"""
Migration: Add workflow_configuration_id to sla_measures table

Adds a foreign key relationship between SLA measures and workflow configurations,
allowing admins to assign a specific workflow to each SLA milestone.

When an SLA milestone is triggered, the associated workflow will be enrolled.
"""

import os
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def run_migration():
    """Add workflow_configuration_id column to sla_measures table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if column already exists
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sla_measures'
                AND column_name = 'workflow_configuration_id'
            )
        """))
        column_exists = result.scalar()

        if column_exists:
            logger.info("Column workflow_configuration_id already exists in sla_measures")
            return True

        # Add the workflow_configuration_id column
        logger.info("Adding workflow_configuration_id column to sla_measures...")

        session.execute(text("""
            ALTER TABLE sla_measures
            ADD COLUMN workflow_configuration_id INTEGER REFERENCES workflow_configurations(id) ON DELETE SET NULL
        """))

        # Add an index for faster lookups
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sla_measures_workflow_config
            ON sla_measures(workflow_configuration_id)
        """))

        session.commit()
        logger.info("Successfully added workflow_configuration_id column to sla_measures")

        # Log suggested mappings for existing measures
        logger.info("""
Suggested workflow mappings for existing SLA measures:
- lead_response -> prospect
- pre_qualified -> prequal
- preapproval -> pre_approved
- contract_received -> under_contract
- clear_to_close -> last_mile
- funded -> post_close

Run the seed_workflow_mappings() function to apply default mappings.
""")

        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        session.close()


def seed_workflow_mappings():
    """
    Seed default workflow mappings for existing SLA measures.
    Maps milestone types to their logical workflow configurations.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Default mappings: milestone_type -> workflow_key
    DEFAULT_MAPPINGS = {
        "lead_response": "prospect",
        "initial_consultation": "prospect",
        "pre_qualified": "prequal",
        "preapproval": "pre_approved",
        "application_complete": "application",
        "contract_received": "under_contract",
        "submitted_to_processing": "processing",
        "submitted_to_uw": "underwriting",
        "approved": "approved",
        "clear_to_close": "last_mile",
        "closing_docs_out": "closing",
        "funded": "post_close",
    }

    try:
        updated_count = 0

        for milestone_type, workflow_key in DEFAULT_MAPPINGS.items():
            # Get the workflow configuration ID
            result = session.execute(text("""
                SELECT id FROM workflow_configurations
                WHERE workflow_key = :workflow_key
                LIMIT 1
            """), {"workflow_key": workflow_key})
            row = result.fetchone()

            if not row:
                logger.warning(f"Workflow '{workflow_key}' not found, skipping mapping for {milestone_type}")
                continue

            workflow_id = row[0]

            # Update SLA measures with this milestone type
            result = session.execute(text("""
                UPDATE sla_measures
                SET workflow_configuration_id = :workflow_id,
                    updated_at = :now
                WHERE milestone_type = :milestone_type
                AND workflow_configuration_id IS NULL
            """), {
                "workflow_id": workflow_id,
                "milestone_type": milestone_type,
                "now": datetime.now(timezone.utc)
            })

            if result.rowcount > 0:
                updated_count += result.rowcount
                logger.info(f"Mapped {result.rowcount} '{milestone_type}' measures to workflow '{workflow_key}'")

        session.commit()
        logger.info(f"Successfully mapped {updated_count} SLA measures to workflows")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Seeding workflow mappings failed: {e}")
        return False
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration completed successfully")
        print("\nTo apply default workflow mappings, run:")
        print("  python -c \"from migrations.add_workflow_to_sla_measures import seed_workflow_mappings; seed_workflow_mappings()\"")
    else:
        print("Migration failed")
    exit(0 if success else 1)
