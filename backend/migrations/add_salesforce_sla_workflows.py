"""
Migration: Add Salesforce SLA Workflow Configurations

Creates workflow configurations that are triggered by Salesforce date field syncs:
- Closing workflow (triggered by closing_date)
- Rate Lock workflow (triggered by lock_date)
- Lock Expiration workflow (triggered by lock_expiration_date)

These workflows generate countdown tasks leading up to key dates.
"""

import os
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


# Salesforce-triggered workflow configurations
SALESFORCE_WORKFLOWS = [
    {
        "workflow_key": "closing",
        "workflow_name": "Closing Countdown",
        "description": "Tasks triggered when closing date is set from Salesforce. Generates countdown tasks at 14, 7, 3, and 1 days before closing.",
        "entity_type": "loan",
        "trigger_type": "salesforce_date",
        "trigger_field": "closing_date",
        "days": [
            {
                "day_value": -14,
                "day_label": "14 Days to Closing",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": False,
                "task_description": "Review file for closing readiness. Confirm all conditions are cleared or on track."
            },
            {
                "day_value": -7,
                "day_label": "7 Days to Closing",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": True,
                "task_description": "One week reminder - confirm borrower has scheduled closing, final walkthrough, and has funds ready."
            },
            {
                "day_value": -3,
                "day_label": "3 Days to Closing",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": True,
                "task_description": "Final closing confirmation. Review CD for accuracy, confirm wire instructions sent."
            },
            {
                "day_value": -1,
                "day_label": "1 Day to Closing",
                "phone_enabled": True,
                "email_enabled": False,
                "text_enabled": True,
                "task_description": "Day before closing - final confirmation call. Ensure borrower is ready for tomorrow."
            },
            {
                "day_value": 0,
                "day_label": "Closing Day",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": False,
                "task_description": "Closing day follow-up. Congratulate borrower, confirm signing went smoothly."
            }
        ]
    },
    {
        "workflow_key": "rate_lock",
        "workflow_name": "Rate Lock Monitoring",
        "description": "Tasks triggered when rate is locked. Monitors lock period and generates alerts before expiration.",
        "entity_type": "loan",
        "trigger_type": "salesforce_date",
        "trigger_field": "lock_date",
        "days": [
            {
                "day_value": 0,
                "day_label": "Rate Lock Confirmation",
                "phone_enabled": False,
                "email_enabled": True,
                "text_enabled": False,
                "task_description": "Send rate lock confirmation to borrower with lock details and expiration date."
            },
            {
                "day_value": 1,
                "day_label": "Rate Lock Follow-up",
                "phone_enabled": True,
                "email_enabled": False,
                "text_enabled": False,
                "task_description": "Confirm borrower received lock confirmation. Answer any questions about the locked rate."
            }
        ]
    },
    {
        "workflow_key": "lock_expiration",
        "workflow_name": "Lock Expiration Countdown",
        "description": "Urgent countdown tasks before rate lock expires. High priority alerts.",
        "entity_type": "loan",
        "trigger_type": "salesforce_date",
        "trigger_field": "lock_expiration_date",
        "days": [
            {
                "day_value": -7,
                "day_label": "7 Days to Lock Expiration",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": False,
                "task_description": "ALERT: Lock expires in 7 days. Review pipeline status - can we close in time?"
            },
            {
                "day_value": -3,
                "day_label": "3 Days to Lock Expiration",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": True,
                "task_description": "URGENT: Lock expires in 3 days. Escalate if closing timeline at risk."
            },
            {
                "day_value": -1,
                "day_label": "1 Day to Lock Expiration",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": True,
                "task_description": "CRITICAL: Lock expires tomorrow. If not closing, discuss extension options with borrower."
            }
        ]
    },
    {
        "workflow_key": "disclosure_sent",
        "workflow_name": "Post-Disclosure Follow-up",
        "description": "Follow-up sequence after initial disclosure is sent from Salesforce.",
        "entity_type": "loan",
        "trigger_type": "salesforce_date",
        "trigger_field": "disclosure_sent_date",
        "days": [
            {
                "day_value": 1,
                "day_label": "Disclosure Follow-up",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": False,
                "task_description": "Follow up on disclosure receipt. Answer questions, explain next steps."
            },
            {
                "day_value": 3,
                "day_label": "Disclosure Reminder",
                "phone_enabled": True,
                "email_enabled": True,
                "text_enabled": True,
                "task_description": "Reminder to sign disclosure if not yet returned. Offer to help via phone."
            }
        ]
    }
]


def run_migration():
    """Run the migration to add Salesforce SLA workflow configurations."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        now = datetime.now(timezone.utc)

        for workflow in SALESFORCE_WORKFLOWS:
            # Check if workflow already exists
            existing = session.execute(text("""
                SELECT id FROM workflow_configurations
                WHERE workflow_key = :key
            """), {"key": workflow["workflow_key"]}).fetchone()

            if existing:
                logger.info(f"Workflow '{workflow['workflow_key']}' already exists, skipping")
                continue

            # Create workflow configuration
            result = session.execute(text("""
                INSERT INTO workflow_configurations (
                    workflow_key, workflow_name, description,
                    entity_type, trigger_type, trigger_field,
                    is_active, is_system_template,
                    created_at, updated_at
                ) VALUES (
                    :workflow_key, :workflow_name, :description,
                    :entity_type, :trigger_type, :trigger_field,
                    true, true,
                    :now, :now
                )
                RETURNING id
            """), {
                "workflow_key": workflow["workflow_key"],
                "workflow_name": workflow["workflow_name"],
                "description": workflow["description"],
                "entity_type": workflow.get("entity_type", "loan"),
                "trigger_type": workflow.get("trigger_type", "salesforce_date"),
                "trigger_field": workflow.get("trigger_field"),
                "now": now
            })
            workflow_id = result.fetchone()[0]
            logger.info(f"Created workflow '{workflow['workflow_key']}' with ID {workflow_id}")

            # Create day configurations
            for day_config in workflow.get("days", []):
                session.execute(text("""
                    INSERT INTO workflow_day_configs (
                        workflow_id, day_value, day_label,
                        phone_enabled, email_enabled, text_enabled,
                        task_description, is_active,
                        created_at, updated_at
                    ) VALUES (
                        :workflow_id, :day_value, :day_label,
                        :phone_enabled, :email_enabled, :text_enabled,
                        :task_description, true,
                        :now, :now
                    )
                """), {
                    "workflow_id": workflow_id,
                    "day_value": day_config["day_value"],
                    "day_label": day_config["day_label"],
                    "phone_enabled": day_config.get("phone_enabled", False),
                    "email_enabled": day_config.get("email_enabled", True),
                    "text_enabled": day_config.get("text_enabled", False),
                    "task_description": day_config.get("task_description", ""),
                    "now": now
                })

            logger.info(f"Created {len(workflow.get('days', []))} day configs for workflow '{workflow['workflow_key']}'")

        session.commit()
        logger.info("Salesforce SLA workflow migration completed successfully")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    exit(0 if success else 1)
