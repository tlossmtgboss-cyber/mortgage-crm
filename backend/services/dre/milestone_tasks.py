"""
DRE Milestone Tasks — Auto-create tasks when loan/lead milestones are reached.

Functions:
    create_milestone_tasks      — Create tasks for loan milestone triggers
    create_lead_milestone_tasks — Create tasks for lead milestone triggers
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from services.dre._base import _ensure_models

logger = logging.getLogger(__name__)


def create_milestone_tasks(loan, updated_fields: list, db: Session) -> list:
    """Create tasks automatically when milestone dates are populated."""
    _ensure_models()
    from services.dre._base import Task

    tasks_created = []

    milestone_task_triggers = [
        ("stage->PROCESSING", "Review Application Package", "Review newly submitted application for completeness", 0, "high"),
        ("stage->SUBMITTED", "Monitor UW Queue", "Application submitted - monitor underwriting queue", 1, "medium"),
        ("stage->UW_RECEIVED", "Follow Up on Underwriting", "File in underwriting - follow up for status", 2, "high"),
        ("stage->APPROVED", "Review Approval Conditions", "Loan approved - review and clear any conditions", 0, "high"),
        ("stage->CTC", "Schedule Closing", "Clear to Close received - coordinate closing date", 0, "urgent"),
        ("stage->FUNDED", "Send Thank You & Request Review", "Loan funded - send thank you and request review", 1, "medium"),
        ("appraisal_ordered_date", "Follow Up on Appraisal", "Appraisal ordered - follow up in 3 days if not scheduled", 3, "medium"),
        ("appraisal_scheduled_date", "Confirm Appraisal Access", "Appraisal scheduled - confirm property access", 0, "medium"),
        ("appraisal_completed_date", "Review Appraisal Report", "Appraisal completed - review report for value/issues", 1, "high"),
        ("lock_date", "Monitor Lock Expiration", "Rate locked - monitor expiration and closing timeline", 0, "high"),
        ("lock_expiration_date", "Lock Expiration Alert", "Rate lock expires soon - verify closing timeline", -3, "urgent"),
        ("closing_date", "7-Day Closing Checklist", "Closing approaching - verify all items ready", -7, "high"),
        ("closing_date", "Final Closing Prep", "Closing in 3 days - final verification", -3, "urgent"),
    ]

    try:
        logger.info(f"create_milestone_tasks called for loan {loan.loan_number} with updated_fields: {updated_fields}")

        for trigger_field, task_title, task_desc, days_offset, priority in milestone_task_triggers:
            if trigger_field not in updated_fields:
                continue

            logger.info(f"Trigger matched: {trigger_field} -> Creating task: {task_title}")

            due_date = None
            if trigger_field.startswith("stage->"):
                due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
            else:
                date_value = getattr(loan, trigger_field, None)
                if date_value:
                    if isinstance(date_value, datetime):
                        due_date = date_value + timedelta(days=days_offset)
                    else:
                        due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

            if not due_date:
                due_date = datetime.now(timezone.utc) + timedelta(days=1)

            existing_task = db.query(Task).filter(
                Task.loan_id == loan.id,
                Task.title == task_title,
                Task.status != "completed"
            ).first()

            if existing_task:
                logger.info(f"Task '{task_title}' already exists for loan {loan.loan_number}, skipping")
                continue

            new_task = Task(
                title=task_title,
                description=f"{task_desc}\n\nLoan: {loan.loan_number}\nBorrower: {loan.borrower_name or 'N/A'}",
                status="pending",
                priority=priority,
                due_date=due_date,
                loan_id=loan.id,
                owner_id=loan.loan_officer_id,
                related_contact_name=loan.borrower_name,
                related_type="loan",
                created_at=datetime.now(timezone.utc)
            )

            db.add(new_task)
            tasks_created.append(task_title)
            logger.info(f"Created task: '{task_title}' for loan {loan.loan_number}, due: {due_date}")

        if tasks_created:
            logger.info(f"Committing {len(tasks_created)} tasks to database...")
            db.commit()
            logger.info(f"Tasks committed successfully: {tasks_created}")
        else:
            logger.info(f"No matching triggers found for updated_fields: {updated_fields}")

    except Exception as e:
        import traceback
        logger.error(f"Error creating milestone tasks: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        db.rollback()

    return tasks_created


def create_lead_milestone_tasks(lead, updated_fields: list, db: Session) -> list:
    """Create tasks automatically when lead milestone dates are populated."""
    _ensure_models()
    from services.dre._base import Task

    tasks_created = []

    lead_task_triggers = [
        ("application_started_date", "Review Started Application", "Application started - follow up to encourage completion", 1, "high"),
        ("application_completed_date", "Review Completed Application", "Application completed - review for completeness and pull credit", 0, "high"),
        ("stage->APPLICATION", "Process Application Package", "Application received - begin processing and verification", 0, "high"),
        ("credit_pulled_date", "Review Credit Report", "Credit pulled - review report and discuss with borrower", 0, "high"),
        ("preapproval_issued_date", "Send Preapproval Letter", "Preapproval issued - send letter to borrower and realtor", 0, "high"),
        ("stage->PRE_APPROVED", "Connect with Realtor", "Lead pre-approved - connect with realtor for home search", 1, "medium"),
    ]

    try:
        for trigger_field, task_title, task_desc, days_offset, priority in lead_task_triggers:
            if trigger_field not in updated_fields:
                continue

            due_date = None
            if trigger_field.startswith("stage->"):
                due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
            else:
                date_value = getattr(lead, trigger_field, None)
                if date_value:
                    if isinstance(date_value, datetime):
                        due_date = date_value + timedelta(days=days_offset)
                    else:
                        due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

            if not due_date:
                due_date = datetime.now(timezone.utc) + timedelta(days=1)

            existing_task = db.query(Task).filter(
                Task.lead_id == lead.id,
                Task.title == task_title,
                Task.status != "completed"
            ).first()

            if existing_task:
                logger.info(f"Task '{task_title}' already exists for lead {lead.name}, skipping")
                continue

            new_task = Task(
                title=task_title,
                description=f"{task_desc}\n\nLead: {lead.name}\nEmail: {lead.email or 'N/A'}",
                status="pending",
                priority=priority,
                due_date=due_date,
                lead_id=lead.id,
                owner_id=lead.owner_id,
                created_at=datetime.now(timezone.utc)
            )

            db.add(new_task)
            tasks_created.append(task_title)
            logger.info(f"Created task: '{task_title}' for lead {lead.name}, due: {due_date}")

        if tasks_created:
            db.commit()

    except Exception as e:
        logger.error(f"Error creating lead milestone tasks: {e}")
        db.rollback()

    return tasks_created
