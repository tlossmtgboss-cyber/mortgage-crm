"""
Reminder Background Tasks

Celery tasks for processing appointment reminders on a schedule.

The main task ``process_pending_reminders`` runs every 5 minutes via
Celery Beat and processes up to 50 due reminders per run.

Usage:
    # Manually trigger
    from tasks.reminder_tasks import process_pending_reminders
    process_pending_reminders.delay()

    # Or via Celery Beat (configured in celery_app.py beat_schedule)
"""

import logging
from datetime import datetime, timezone

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.reminder_tasks.process_pending_reminders",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_pending_reminders(self, batch_size: int = 50):
    """
    Process all pending reminders that are due.

    Queries for AppointmentReminder rows where:
      - status = PENDING
      - scheduled_for <= now

    Sends reminders in batch via the ReminderService, logging every
    attempt to the reminder_logs table.

    Args:
        batch_size: Max reminders to process per run (default 50).
    """
    from db import SessionLocal
    from services.reminder_service import ReminderService

    logger.info(f"Starting reminder processing (batch_size={batch_size})")
    start_time = datetime.now(timezone.utc)

    session = SessionLocal()
    try:
        service = ReminderService(session)
        summary = service.process_pending_batch(batch_size=batch_size)
        session.commit()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"Reminder processing complete in {elapsed:.1f}s: "
            f"{summary['sent']} sent, {summary['failed']} failed, "
            f"{summary['skipped']} skipped out of {summary['processed']} processed"
        )
        return summary

    except Exception as e:
        session.rollback()
        logger.exception(f"Reminder processing failed: {e}")
        raise self.retry(exc=e)
    finally:
        session.close()


@celery_app.task(
    name="tasks.reminder_tasks.schedule_appointment_reminders",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def schedule_appointment_reminders(self, appointment_id: int):
    """
    Create reminder schedule for a newly created appointment.

    Called asynchronously after an appointment is created or rescheduled.
    """
    from db import SessionLocal
    from services.reminder_service import ReminderService

    session = SessionLocal()
    try:
        service = ReminderService(session)
        created = service.schedule_reminders(appointment_id)
        session.commit()

        logger.info(
            f"Scheduled {len(created)} reminders for appointment {appointment_id}"
        )
        return {"appointment_id": appointment_id, "reminders_created": len(created)}

    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to schedule reminders for appointment {appointment_id}: {e}")
        raise self.retry(exc=e)
    finally:
        session.close()


@celery_app.task(
    name="tasks.reminder_tasks.cancel_appointment_reminders",
    bind=True,
    max_retries=1,
)
def cancel_appointment_reminders(self, appointment_id: int):
    """
    Cancel all pending reminders for a cancelled appointment.
    """
    from db import SessionLocal
    from services.reminder_service import ReminderService

    session = SessionLocal()
    try:
        service = ReminderService(session)
        count = service.cancel_reminders(appointment_id)
        session.commit()

        logger.info(f"Cancelled {count} reminders for appointment {appointment_id}")
        return {"appointment_id": appointment_id, "cancelled": count}

    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to cancel reminders for appointment {appointment_id}: {e}")
        raise self.retry(exc=e)
    finally:
        session.close()


@celery_app.task(
    name="tasks.reminder_tasks.reschedule_appointment_reminders",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def reschedule_appointment_reminders(self, appointment_id: int):
    """
    Reschedule all reminders for an appointment that was rescheduled.
    Cancels existing pending reminders and creates new ones.
    """
    from db import SessionLocal
    from services.reminder_service import ReminderService

    session = SessionLocal()
    try:
        service = ReminderService(session)
        created = service.reschedule_reminders(appointment_id)
        session.commit()

        logger.info(
            f"Rescheduled reminders for appointment {appointment_id}: "
            f"{len(created)} new reminders created"
        )
        return {"appointment_id": appointment_id, "reminders_created": len(created)}

    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to reschedule reminders for appointment {appointment_id}: {e}")
        raise self.retry(exc=e)
    finally:
        session.close()
