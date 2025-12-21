"""
Scheduler Service - Background jobs for automated notifications and reminders.

Uses APScheduler for job scheduling.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/mortgage_crm")

# Reminder configuration
REMINDER_INTERVALS = {
    "first": 24,      # Hours after last activity
    "second": 72,     # 3 days
    "third": 168,     # 7 days
    "final": 336,     # 14 days
}

# Import notification service lazily to avoid circular imports
notification_service = None


def get_notification_service():
    """Get notification service instance."""
    global notification_service
    if notification_service is None:
        from services.notification_service import NotificationService
        notification_service = NotificationService()
    return notification_service


def get_db_session():
    """Get database session."""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()


class SchedulerService:
    """Service for managing scheduled background jobs."""

    def __init__(self):
        self.scheduler = BackgroundScheduler(
            timezone="America/New_York",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            }
        )
        self._jobs_registered = False

    def start(self):
        """Start the scheduler and register jobs."""
        if not self._jobs_registered:
            self._register_jobs()
            self._jobs_registered = True

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _register_jobs(self):
        """Register all scheduled jobs."""

        # Application reminder job - runs every hour
        self.scheduler.add_job(
            func=self.send_application_reminders,
            trigger=IntervalTrigger(hours=1),
            id="application_reminders",
            name="Send Application Reminders",
            replace_existing=True,
        )

        # Document expiration check - runs daily at 9 AM
        self.scheduler.add_job(
            func=self.check_document_expirations,
            trigger=CronTrigger(hour=9, minute=0),
            id="document_expiration_check",
            name="Check Document Expirations",
            replace_existing=True,
        )

        # Appointment reminders - runs every 15 minutes
        self.scheduler.add_job(
            func=self.send_appointment_reminders,
            trigger=IntervalTrigger(minutes=15),
            id="appointment_reminders",
            name="Send Appointment Reminders",
            replace_existing=True,
        )

        # Stale application cleanup - runs daily at midnight
        self.scheduler.add_job(
            func=self.cleanup_stale_applications,
            trigger=CronTrigger(hour=0, minute=0),
            id="stale_cleanup",
            name="Cleanup Stale Applications",
            replace_existing=True,
        )

        # =================================================================
        # WORKFLOW SLA SYSTEM JOBS
        # =================================================================

        # Workflow task generation - runs every 5 minutes
        self.scheduler.add_job(
            func=self.run_workflow_task_generation,
            trigger=IntervalTrigger(minutes=5),
            id="workflow_task_generation",
            name="Generate Workflow Tasks",
            replace_existing=True,
        )

        # Workflow status processing - runs every 10 minutes
        self.scheduler.add_job(
            func=self.run_workflow_status_processing,
            trigger=IntervalTrigger(minutes=10),
            id="workflow_status_processing",
            name="Process Workflow Status Changes",
            replace_existing=True,
        )

        # Workflow escalation check - runs every hour
        self.scheduler.add_job(
            func=self.run_workflow_escalation,
            trigger=IntervalTrigger(hours=1),
            id="workflow_escalation",
            name="Escalate Overdue Workflow Tasks",
            replace_existing=True,
        )

        # Workflow completion check - runs every 30 minutes
        self.scheduler.add_job(
            func=self.run_workflow_completion_check,
            trigger=IntervalTrigger(minutes=30),
            id="workflow_completion_check",
            name="Check Workflow Completions",
            replace_existing=True,
        )

        # AI autonomous execution - runs every 15 minutes
        self.scheduler.add_job(
            func=self.run_ai_autonomous_execution,
            trigger=IntervalTrigger(minutes=15),
            id="ai_autonomous_execution",
            name="Run AI Autonomous Task Execution",
            replace_existing=True,
        )

        logger.info("Scheduled jobs registered")

    def send_application_reminders(self):
        """Send reminders for incomplete applications."""
        logger.info("Running application reminder job")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # Find incomplete applications that need reminders
            query = text("""
                SELECT
                    ba.id,
                    ba.borrower_email,
                    ba.borrower_first_name,
                    ba.borrower_phone,
                    ba.status,
                    ba.reminder_count,
                    ba.last_reminder_at,
                    ba.updated_at,
                    ba.assigned_lo_id,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name,
                    EXTRACT(EPOCH FROM (NOW() - COALESCE(ba.last_reminder_at, ba.updated_at))) / 3600 as hours_since_activity
                FROM borrower_applications ba
                LEFT JOIN users u ON u.id = ba.assigned_lo_id
                WHERE ba.status IN ('draft', 'in_progress')
                AND ba.borrower_email IS NOT NULL
                AND (
                    (ba.reminder_count = 0 AND EXTRACT(EPOCH FROM (NOW() - ba.updated_at)) / 3600 >= :first_interval)
                    OR (ba.reminder_count = 1 AND EXTRACT(EPOCH FROM (NOW() - ba.last_reminder_at)) / 3600 >= :second_interval)
                    OR (ba.reminder_count = 2 AND EXTRACT(EPOCH FROM (NOW() - ba.last_reminder_at)) / 3600 >= :third_interval)
                    OR (ba.reminder_count = 3 AND EXTRACT(EPOCH FROM (NOW() - ba.last_reminder_at)) / 3600 >= :final_interval)
                )
                AND ba.reminder_count < 4
                ORDER BY ba.updated_at ASC
                LIMIT 100
            """)

            result = session.execute(query, {
                "first_interval": REMINDER_INTERVALS["first"],
                "second_interval": REMINDER_INTERVALS["second"] - REMINDER_INTERVALS["first"],
                "third_interval": REMINDER_INTERVALS["third"] - REMINDER_INTERVALS["second"],
                "final_interval": REMINDER_INTERVALS["final"] - REMINDER_INTERVALS["third"],
            })

            applications = result.fetchall()
            sent_count = 0

            for app in applications:
                try:
                    app_dict = dict(app._mapping)
                    app_id = app_dict["id"]
                    borrower_email = app_dict["borrower_email"]
                    borrower_name = app_dict["borrower_first_name"] or "there"
                    borrower_phone = app_dict.get("borrower_phone")
                    reminder_count = app_dict["reminder_count"] or 0
                    lo_name = f"{app_dict.get('lo_first_name', '')} {app_dict.get('lo_last_name', '')}".strip() or "Your Loan Officer"

                    # Calculate progress (simplified)
                    progress = 25 if app_dict["status"] == "draft" else 50

                    # Generate resume link
                    resume_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/apply/resume/{app_id}"

                    # Send email reminder
                    email_result = notifier.send_application_reminder(
                        borrower_email=borrower_email,
                        borrower_name=borrower_name,
                        resume_link=resume_link,
                        progress_percent=progress,
                        lo_name=lo_name,
                    )

                    # Send SMS on second and subsequent reminders
                    if reminder_count >= 1 and borrower_phone:
                        notifier.send_reminder_sms(
                            borrower_phone=borrower_phone,
                            borrower_name=borrower_name,
                            resume_link=resume_link,
                        )

                    # Update reminder count
                    update_query = text("""
                        UPDATE borrower_applications
                        SET reminder_count = reminder_count + 1,
                            last_reminder_at = NOW()
                        WHERE id = :app_id
                    """)
                    session.execute(update_query, {"app_id": app_id})
                    session.commit()

                    sent_count += 1
                    logger.info(f"Sent reminder #{reminder_count + 1} for application {app_id}")

                except Exception as e:
                    logger.error(f"Failed to send reminder for application {app_dict.get('id')}: {e}")
                    session.rollback()

            logger.info(f"Application reminder job complete: {sent_count} reminders sent")

        except Exception as e:
            logger.error(f"Application reminder job failed: {e}")
        finally:
            session.close()

    def check_document_expirations(self):
        """Check for expiring documents and notify."""
        logger.info("Running document expiration check")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # Find documents expiring in the next 7 days
            query = text("""
                SELECT
                    ad.id as doc_id,
                    ad.document_type,
                    ad.expires_at,
                    ba.id as application_id,
                    ba.borrower_email,
                    ba.borrower_first_name,
                    ba.assigned_lo_id,
                    u.email as lo_email,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name
                FROM application_documents ad
                JOIN borrower_applications ba ON ba.id = ad.application_id
                LEFT JOIN users u ON u.id = ba.assigned_lo_id
                WHERE ad.expires_at IS NOT NULL
                AND ad.expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
                AND ad.expiration_notified = false
                AND ba.status NOT IN ('submitted', 'funded', 'denied', 'withdrawn')
            """)

            result = session.execute(query)
            docs = result.fetchall()

            for doc in docs:
                try:
                    doc_dict = dict(doc._mapping)
                    days_until_expiry = (doc_dict["expires_at"] - datetime.now()).days

                    # Notify borrower
                    upload_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/apply/documents/{doc_dict['application_id']}"

                    notifier.send_document_request(
                        borrower_email=doc_dict["borrower_email"],
                        borrower_name=doc_dict["borrower_first_name"] or "there",
                        documents_needed=[f"{doc_dict['document_type']} (expires in {days_until_expiry} days)"],
                        upload_link=upload_link,
                        lo_name=f"{doc_dict.get('lo_first_name', '')} {doc_dict.get('lo_last_name', '')}".strip(),
                    )

                    # Mark as notified
                    update_query = text("""
                        UPDATE application_documents
                        SET expiration_notified = true
                        WHERE id = :doc_id
                    """)
                    session.execute(update_query, {"doc_id": doc_dict["doc_id"]})
                    session.commit()

                    logger.info(f"Sent expiration notice for document {doc_dict['doc_id']}")

                except Exception as e:
                    logger.error(f"Failed to send expiration notice for document {doc_dict.get('doc_id')}: {e}")
                    session.rollback()

        except Exception as e:
            logger.error(f"Document expiration check failed: {e}")
        finally:
            session.close()

    def send_appointment_reminders(self):
        """Send reminders for upcoming appointments with cascading intervals (24h, 1h)."""
        logger.info("Running appointment reminder job")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # =====================================================================
            # PART 1: Legacy appointments table (single reminder)
            # =====================================================================
            legacy_query = text("""
                SELECT
                    a.id as appointment_id,
                    a.appointment_type,
                    a.scheduled_at,
                    a.meeting_link,
                    a.lead_id,
                    a.loan_id,
                    l.first_name as borrower_first_name,
                    l.email as borrower_email,
                    l.phone as borrower_phone,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name
                FROM appointments a
                LEFT JOIN leads l ON l.id = a.lead_id
                LEFT JOIN users u ON u.id = a.assigned_to
                WHERE a.scheduled_at BETWEEN NOW() AND NOW() + INTERVAL '24 hours'
                AND a.reminder_sent = false
                AND a.status = 'scheduled'
            """)

            result = session.execute(legacy_query)
            appointments = result.fetchall()

            for appt in appointments:
                try:
                    appt_dict = dict(appt._mapping)
                    lo_name = f"{appt_dict.get('lo_first_name', '')} {appt_dict.get('lo_last_name', '')}".strip()

                    # Send email reminder
                    if appt_dict.get("borrower_email"):
                        notifier.send_appointment_confirmation(
                            borrower_email=appt_dict["borrower_email"],
                            borrower_name=appt_dict.get("borrower_first_name", "there"),
                            appointment_type=f"Reminder: {appt_dict['appointment_type']}",
                            appointment_time=appt_dict["scheduled_at"],
                            lo_name=lo_name,
                            meeting_link=appt_dict.get("meeting_link"),
                        )

                    # Send SMS reminder
                    if appt_dict.get("borrower_phone"):
                        notifier.send_appointment_reminder_sms(
                            borrower_phone=appt_dict["borrower_phone"],
                            borrower_name=appt_dict.get("borrower_first_name", "there"),
                            appointment_time=appt_dict["scheduled_at"],
                            lo_name=lo_name,
                            meeting_link=appt_dict.get("meeting_link"),
                        )

                    # Mark as reminded
                    update_query = text("""
                        UPDATE appointments
                        SET reminder_sent = true
                        WHERE id = :appt_id
                    """)
                    session.execute(update_query, {"appt_id": appt_dict["appointment_id"]})
                    session.commit()

                    logger.info(f"Sent legacy reminder for appointment {appt_dict['appointment_id']}")

                except Exception as e:
                    logger.error(f"Failed to send legacy reminder for appointment {appt_dict.get('appointment_id')}: {e}")
                    session.rollback()

            # =====================================================================
            # PART 2: Smart scheduler appointments (cascading reminders: 24h, 1h)
            # =====================================================================
            self._send_smart_scheduler_reminders(session, notifier)

        except Exception as e:
            logger.error(f"Appointment reminder job failed: {e}")
        finally:
            session.close()

    def _send_smart_scheduler_reminders(self, session, notifier):
        """Send cascading reminders for smart scheduler appointments (24h and 1h before)."""
        try:
            # Check if scheduler_appointments table exists
            table_check = session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'scheduler_appointments'
                )
            """))
            if not table_check.scalar():
                logger.debug("scheduler_appointments table doesn't exist, skipping smart reminders")
                return

            # 24-hour reminders
            query_24h = text("""
                SELECT
                    sa.id as appointment_id,
                    sa.title,
                    sa.scheduled_start,
                    sa.video_link,
                    sa.attendee_name,
                    sa.attendee_email,
                    sa.attendee_phone,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name
                FROM scheduler_appointments sa
                LEFT JOIN users u ON u.id = sa.assigned_user_id
                WHERE sa.scheduled_start BETWEEN NOW() + INTERVAL '23 hours' AND NOW() + INTERVAL '25 hours'
                AND sa.status = 'booked'
                AND NOT EXISTS (
                    SELECT 1 FROM scheduler_reminders sr
                    WHERE sr.appointment_id = sa.id
                    AND sr.hours_before = 24
                    AND sr.status IN ('sent', 'delivered')
                )
            """)

            result_24h = session.execute(query_24h)
            appointments_24h = result_24h.fetchall()

            for appt in appointments_24h:
                self._send_reminder_for_smart_appt(session, notifier, appt, 24)

            # 1-hour reminders
            query_1h = text("""
                SELECT
                    sa.id as appointment_id,
                    sa.title,
                    sa.scheduled_start,
                    sa.video_link,
                    sa.attendee_name,
                    sa.attendee_email,
                    sa.attendee_phone,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name
                FROM scheduler_appointments sa
                LEFT JOIN users u ON u.id = sa.assigned_user_id
                WHERE sa.scheduled_start BETWEEN NOW() + INTERVAL '50 minutes' AND NOW() + INTERVAL '70 minutes'
                AND sa.status = 'booked'
                AND NOT EXISTS (
                    SELECT 1 FROM scheduler_reminders sr
                    WHERE sr.appointment_id = sa.id
                    AND sr.hours_before = 1
                    AND sr.status IN ('sent', 'delivered')
                )
            """)

            result_1h = session.execute(query_1h)
            appointments_1h = result_1h.fetchall()

            for appt in appointments_1h:
                self._send_reminder_for_smart_appt(session, notifier, appt, 1)

            logger.info(f"Processed {len(appointments_24h)} 24h reminders and {len(appointments_1h)} 1h reminders")

        except Exception as e:
            logger.error(f"Smart scheduler reminders failed: {e}")
            session.rollback()

    def _send_reminder_for_smart_appt(self, session, notifier, appt, hours_before: int):
        """Send reminder for a smart scheduler appointment and record it."""
        try:
            appt_dict = dict(appt._mapping)
            lo_name = f"{appt_dict.get('lo_first_name', '')} {appt_dict.get('lo_last_name', '')}".strip()
            appointment_id = appt_dict["appointment_id"]

            # Determine reminder message based on hours
            if hours_before == 24:
                reminder_prefix = "Reminder: Tomorrow - "
            elif hours_before == 1:
                reminder_prefix = "Starting Soon: "
            else:
                reminder_prefix = "Reminder: "

            email_sent = False
            sms_sent = False

            # Send email reminder
            if appt_dict.get("attendee_email"):
                try:
                    notifier.send_appointment_confirmation(
                        borrower_email=appt_dict["attendee_email"],
                        borrower_name=appt_dict.get("attendee_name", "there"),
                        appointment_type=f"{reminder_prefix}{appt_dict.get('title', 'Appointment')}",
                        appointment_time=appt_dict["scheduled_start"],
                        lo_name=lo_name,
                        meeting_link=appt_dict.get("video_link"),
                    )
                    email_sent = True
                except Exception as e:
                    logger.error(f"Failed to send email reminder for appointment {appointment_id}: {e}")

            # Send SMS reminder
            if appt_dict.get("attendee_phone"):
                try:
                    notifier.send_appointment_reminder_sms(
                        borrower_phone=appt_dict["attendee_phone"],
                        borrower_name=appt_dict.get("attendee_name", "there"),
                        appointment_time=appt_dict["scheduled_start"],
                        lo_name=lo_name,
                        meeting_link=appt_dict.get("video_link"),
                    )
                    sms_sent = True
                except Exception as e:
                    logger.error(f"Failed to send SMS reminder for appointment {appointment_id}: {e}")

            # Record the reminder in scheduler_reminders table
            if email_sent or sms_sent:
                # Check if scheduler_reminders table exists
                table_check = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'scheduler_reminders'
                    )
                """))
                if table_check.scalar():
                    if email_sent:
                        session.execute(text("""
                            INSERT INTO scheduler_reminders
                            (appointment_id, channel, scheduled_for, hours_before, status, sent_at, created_at, updated_at)
                            VALUES (:appt_id, 'email', NOW(), :hours_before, 'sent', NOW(), NOW(), NOW())
                        """), {"appt_id": appointment_id, "hours_before": hours_before})

                    if sms_sent:
                        session.execute(text("""
                            INSERT INTO scheduler_reminders
                            (appointment_id, channel, scheduled_for, hours_before, status, sent_at, created_at, updated_at)
                            VALUES (:appt_id, 'sms', NOW(), :hours_before, 'sent', NOW(), NOW(), NOW())
                        """), {"appt_id": appointment_id, "hours_before": hours_before})

                session.commit()
                logger.info(f"Sent {hours_before}h reminder for smart appointment {appointment_id} (email={email_sent}, sms={sms_sent})")

        except Exception as e:
            logger.error(f"Failed to send reminder for smart appointment: {e}")
            session.rollback()

    def cleanup_stale_applications(self):
        """Archive applications that have been inactive for 90+ days."""
        logger.info("Running stale application cleanup")

        session = get_db_session()

        try:
            # Mark applications as abandoned after 90 days of inactivity
            query = text("""
                UPDATE borrower_applications
                SET status = 'abandoned',
                    updated_at = NOW()
                WHERE status IN ('draft', 'in_progress')
                AND updated_at < NOW() - INTERVAL '90 days'
                AND reminder_count >= 4
                RETURNING id
            """)

            result = session.execute(query)
            abandoned = result.fetchall()
            session.commit()

            logger.info(f"Marked {len(abandoned)} applications as abandoned")

        except Exception as e:
            logger.error(f"Stale application cleanup failed: {e}")
            session.rollback()
        finally:
            session.close()

    # =========================================================================
    # WORKFLOW SLA SYSTEM METHODS
    # =========================================================================

    def run_workflow_task_generation(self):
        """Generate tasks for active workflows."""
        logger.info("Running workflow task generation job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.generate_due_tasks()

            if result.get("success"):
                logger.info(f"Workflow task generation complete: {result}")
            else:
                logger.error(f"Workflow task generation failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow task generation job failed: {e}")
        finally:
            session.close()

    def run_workflow_status_processing(self):
        """Process status changes and auto-enroll in workflows."""
        logger.info("Running workflow status processing job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.process_status_changes()

            if result.get("success"):
                enrolled = result.get("workflows_enrolled", 0)
                logger.info(f"Workflow status processing complete: {enrolled} workflows enrolled")
            else:
                logger.error(f"Workflow status processing failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow status processing job failed: {e}")
        finally:
            session.close()

    def run_workflow_escalation(self):
        """Escalate overdue workflow tasks."""
        logger.info("Running workflow escalation job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.escalate_overdue_tasks()

            if result.get("success"):
                escalated = result.get("escalated_count", 0)
                logger.info(f"Workflow escalation complete: {escalated} tasks escalated")
            else:
                logger.error(f"Workflow escalation failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow escalation job failed: {e}")
        finally:
            session.close()

    def run_workflow_completion_check(self):
        """Check for workflows that should be completed."""
        logger.info("Running workflow completion check job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.check_workflow_completions()

            if result.get("success"):
                completed = result.get("workflows_completed", 0)
                logger.info(f"Workflow completion check complete: {completed} workflows completed")
            else:
                logger.error(f"Workflow completion check failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow completion check job failed: {e}")
        finally:
            session.close()

    def run_ai_autonomous_execution(self):
        """Run autonomous AI task execution for high-confidence tasks."""
        logger.info("Running AI autonomous execution job")

        session = get_db_session()

        try:
            from services.workflow_ai_executor import run_autonomous_ai_tasks

            result = run_autonomous_ai_tasks(session, max_tasks=20)

            if result.get("success"):
                executed = result.get("executed_count", 0)
                logger.info(f"AI autonomous execution complete: {executed} tasks executed")
            else:
                logger.error(f"AI autonomous execution failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"AI autonomous execution job failed: {e}")
        finally:
            session.close()

    def get_job_status(self) -> List[Dict[str, Any]]:
        """Get status of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs


# Create singleton instance
scheduler_service = SchedulerService()


def init_scheduler():
    """Initialize and start the scheduler. Call this from main.py on startup."""
    scheduler_service.start()
    return scheduler_service
