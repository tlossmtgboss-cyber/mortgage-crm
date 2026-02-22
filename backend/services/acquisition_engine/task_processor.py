"""
Background Task Processor for Acquisition Engine
Handles scheduled actions, retries, and async processing

This processor runs in the background and handles:
- Speed-to-lead queue processing
- Failed action retries
- Scheduled follow-up sequences
- SLA monitoring and alerts
- Campaign metric updates
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database import SessionLocal

def get_session():
    """Get a new database session"""
    return SessionLocal()

from models.acquisition_engine.campaign_models import CampaignInstance, CampaignStatus
from models.acquisition_engine.event_models import AcquisitionEvent, EventType
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of background tasks"""
    SPEED_TO_LEAD = "speed_to_lead"
    RETRY_ACTION = "retry_action"
    SCHEDULED_SEQUENCE = "scheduled_sequence"
    SLA_CHECK = "sla_check"
    CAMPAIGN_METRICS = "campaign_metrics"
    TEMPERATURE_DECAY = "temperature_decay"
    STALE_LEAD_ALERT = "stale_lead_alert"


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class ScheduledTask:
    """A scheduled background task"""
    task_type: TaskType
    lead_id: Optional[int] = None
    campaign_instance_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    scheduled_at: datetime = None
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 5  # 1 = highest, 10 = lowest


class TaskProcessor:
    """
    Background task processor for acquisition engine.

    Processes:
    - Speed-to-lead actions for hot leads
    - Failed action retries with exponential backoff
    - Scheduled sequence steps (drip campaigns)
    - SLA monitoring and breach alerts
    - Campaign metric recalculations
    - Temperature decay for stale leads
    """

    def __init__(self, db: Session = None):
        self.db = db or get_session()
        self._task_queue: List[ScheduledTask] = []
        self._running = False
        self._process_interval = 10  # seconds

    async def start(self):
        """Start the background processor"""
        self._running = True
        logger.info("Task processor started")

        while self._running:
            try:
                await self._process_queue()
                await self._check_scheduled_tasks()
                await asyncio.sleep(self._process_interval)
            except Exception as e:
                logger.error(f"Task processor error: {e}")
                await asyncio.sleep(5)  # Brief pause on error

    def stop(self):
        """Stop the background processor"""
        self._running = False
        logger.info("Task processor stopped")

    def add_task(self, task: ScheduledTask):
        """Add a task to the queue"""
        if task.scheduled_at is None:
            task.scheduled_at = datetime.utcnow()
        self._task_queue.append(task)
        # Sort by priority and scheduled time
        self._task_queue.sort(key=lambda t: (t.priority, t.scheduled_at))
        logger.debug(f"Task added: {task.task_type.value}")

    async def _process_queue(self):
        """Process pending tasks in the queue"""
        now = datetime.utcnow()
        tasks_to_process = [
            t for t in self._task_queue
            if t.scheduled_at <= now
        ]

        for task in tasks_to_process:
            try:
                await self._execute_task(task)
                self._task_queue.remove(task)
            except Exception as e:
                logger.error(f"Task {task.task_type.value} failed: {e}")
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    self._task_queue.remove(task)
                    logger.error(f"Task {task.task_type.value} exceeded max retries")
                else:
                    # Exponential backoff
                    delay = 2 ** task.retry_count * 30  # 30s, 60s, 120s...
                    task.scheduled_at = now + timedelta(seconds=delay)

    async def _execute_task(self, task: ScheduledTask):
        """Execute a specific task"""
        handlers = {
            TaskType.SPEED_TO_LEAD: self._handle_speed_to_lead,
            TaskType.RETRY_ACTION: self._handle_retry_action,
            TaskType.SCHEDULED_SEQUENCE: self._handle_scheduled_sequence,
            TaskType.SLA_CHECK: self._handle_sla_check,
            TaskType.CAMPAIGN_METRICS: self._handle_campaign_metrics,
            TaskType.TEMPERATURE_DECAY: self._handle_temperature_decay,
            TaskType.STALE_LEAD_ALERT: self._handle_stale_lead_alert,
        }

        handler = handlers.get(task.task_type)
        if handler:
            await handler(task)
        else:
            logger.warning(f"Unknown task type: {task.task_type}")

    async def _check_scheduled_tasks(self):
        """Check for scheduled tasks that need to be added to queue"""
        # Check for hot leads needing speed-to-lead
        await self._check_hot_leads()

        # Check for scheduled sequence steps
        await self._check_sequence_steps()

        # Check for SLA breaches
        await self._check_sla_breaches()

    async def _check_hot_leads(self):
        """Check for hot leads that need speed-to-lead processing"""
        try:
            # Find recent hot events that haven't been processed
            recent_hot = self.db.execute(text("""
                SELECT DISTINCT ae.lead_id, ae.campaign_instance_id, ae.event_type
                FROM acquisition_events ae
                WHERE ae.event_timestamp >= :since
                AND ae.lead_id IS NOT NULL
                AND ae.event_type IN :hot_types
                AND ae.processed_at IS NULL
                LIMIT 50
            """), {
                "since": datetime.utcnow() - timedelta(minutes=10),
                "hot_types": tuple([
                    EventType.MEETING_BOOKED.value,
                    EventType.APPLICATION_STARTED.value,
                    EventType.FORM_SUBMITTED.value,
                    EventType.CALLBACK_REQUESTED.value,
                ]),
            }).fetchall()

            for row in recent_hot:
                self.add_task(ScheduledTask(
                    task_type=TaskType.SPEED_TO_LEAD,
                    lead_id=row.lead_id,
                    campaign_instance_id=str(row.campaign_instance_id) if row.campaign_instance_id else None,
                    payload={"event_type": row.event_type},
                    priority=1,  # Highest priority
                ))

        except Exception as e:
            logger.error(f"Error checking hot leads: {e}")

    async def _check_sequence_steps(self):
        """Check for scheduled sequence steps that need execution"""
        try:
            # Find scheduled sequence steps
            scheduled = self.db.execute(text("""
                SELECT ss.id, ss.lead_id, ss.campaign_instance_id,
                       ss.step_type, ss.template_id, ss.channel
                FROM sequence_steps ss
                WHERE ss.scheduled_at <= :now
                AND ss.executed_at IS NULL
                AND ss.status = 'scheduled'
                LIMIT 100
            """), {"now": datetime.utcnow()}).fetchall()

            for step in scheduled:
                self.add_task(ScheduledTask(
                    task_type=TaskType.SCHEDULED_SEQUENCE,
                    lead_id=step.lead_id,
                    campaign_instance_id=str(step.campaign_instance_id) if step.campaign_instance_id else None,
                    payload={
                        "step_id": step.id,
                        "step_type": step.step_type,
                        "template_id": step.template_id,
                        "channel": step.channel,
                    },
                    priority=3,
                ))

        except Exception as e:
            # Table might not exist yet - that's OK
            if "relation" not in str(e).lower():
                logger.error(f"Error checking sequence steps: {e}")

    async def _check_sla_breaches(self):
        """Check for SLA breaches that need alerts"""
        try:
            # Check for hot leads not contacted within SLA
            sla_seconds = 300  # 5 minutes

            breaches = self.db.execute(text("""
                SELECT ae.lead_id, ae.event_type, ae.event_timestamp,
                       ae.campaign_instance_id
                FROM acquisition_events ae
                LEFT JOIN acquisition_events contact ON (
                    contact.lead_id = ae.lead_id
                    AND contact.event_type IN ('SMS_SENT', 'EMAIL_SENT', 'CALL_ATTEMPTED')
                    AND contact.event_timestamp > ae.event_timestamp
                    AND contact.event_timestamp <= ae.event_timestamp + INTERVAL ':sla seconds'
                )
                WHERE ae.event_timestamp >= :since
                AND ae.event_timestamp < :before
                AND ae.event_type IN :hot_types
                AND contact.id IS NULL
            """).bindparams(sla=sla_seconds), {
                "since": datetime.utcnow() - timedelta(hours=1),
                "before": datetime.utcnow() - timedelta(seconds=sla_seconds),
                "hot_types": tuple([
                    EventType.MEETING_BOOKED.value,
                    EventType.FORM_SUBMITTED.value,
                    EventType.CALLBACK_REQUESTED.value,
                ]),
            }).fetchall()

            for breach in breaches:
                self.add_task(ScheduledTask(
                    task_type=TaskType.SLA_CHECK,
                    lead_id=breach.lead_id,
                    campaign_instance_id=str(breach.campaign_instance_id) if breach.campaign_instance_id else None,
                    payload={
                        "event_type": breach.event_type,
                        "event_timestamp": breach.event_timestamp.isoformat(),
                        "breach_type": "speed_to_lead",
                    },
                    priority=2,
                ))

        except Exception as e:
            logger.debug(f"SLA breach check skipped: {e}")

    async def _handle_speed_to_lead(self, task: ScheduledTask):
        """Handle speed-to-lead task"""
        from services.acquisition_engine.speed_to_lead_service import SpeedToLeadService, SpeedToLeadConfig

        stl_service = SpeedToLeadService(self.db)
        config = SpeedToLeadConfig()

        result = await stl_service.process_hot_lead(
            lead_id=task.lead_id,
            event=None,
            campaign_instance_id=task.campaign_instance_id,
            config=config,
        )

        logger.info(f"Speed-to-lead for lead {task.lead_id}: success={result.success}")

    async def _handle_retry_action(self, task: ScheduledTask):
        """Handle retry of a failed action"""
        action_type = task.payload.get("action_type")

        if action_type == "sms":
            await self._retry_sms(task)
        elif action_type == "email":
            await self._retry_email(task)
        elif action_type == "dialer":
            await self._retry_dialer(task)
        else:
            logger.warning(f"Unknown action type for retry: {action_type}")

    async def _retry_sms(self, task: ScheduledTask):
        """Retry failed SMS"""
        try:
            from integrations.sms_service import get_sms_client

            client = get_sms_client()
            result = await client.send_sms(
                to=task.payload.get("phone"),
                message=task.payload.get("message"),
            )
            logger.info(f"SMS retry success for lead {task.lead_id}")
        except Exception as e:
            logger.error(f"SMS retry failed: {e}")
            raise

    async def _retry_email(self, task: ScheduledTask):
        """Retry failed email"""
        try:
            from email_service import EmailService

            service = EmailService()
            service.send_html_email(
                to_email=task.payload.get("email"),
                subject=task.payload.get("subject"),
                html_content=task.payload.get("html_content"),
            )
            logger.info(f"Email retry success for lead {task.lead_id}")
        except Exception as e:
            logger.error(f"Email retry failed: {e}")
            raise

    async def _retry_dialer(self, task: ScheduledTask):
        """Retry dialer queue"""
        try:
            from telephony.dialer_engine import DialerEngine

            engine = DialerEngine(self.db)
            engine.add_to_queue(
                lead_id=task.lead_id,
                priority=task.payload.get("priority", "normal"),
            )
            logger.info(f"Dialer retry success for lead {task.lead_id}")
        except Exception as e:
            logger.error(f"Dialer retry failed: {e}")
            raise

    async def _handle_scheduled_sequence(self, task: ScheduledTask):
        """Handle scheduled sequence step execution"""
        step_id = task.payload.get("step_id")
        channel = task.payload.get("channel")

        try:
            if channel == "sms":
                await self._execute_sms_step(task)
            elif channel == "email":
                await self._execute_email_step(task)
            elif channel == "call":
                await self._execute_call_step(task)

            # Mark step as executed
            self.db.execute(text("""
                UPDATE sequence_steps
                SET executed_at = :now, status = 'completed'
                WHERE id = :step_id
            """), {"now": datetime.utcnow(), "step_id": step_id})
            self.db.commit()

        except Exception as e:
            # Mark step as failed
            self.db.execute(text("""
                UPDATE sequence_steps
                SET status = 'failed', error = :error
                WHERE id = :step_id
            """), {"error": "Internal server error", "step_id": step_id})
            self.db.commit()
            raise

    async def _execute_sms_step(self, task: ScheduledTask):
        """Execute SMS sequence step"""
        from integrations.sms_service import get_sms_client

        # Get lead info
        lead = self.db.execute(text("""
            SELECT first_name, phone FROM leads WHERE id = :lead_id
        """), {"lead_id": task.lead_id}).fetchone()

        if not lead or not lead.phone:
            raise ValueError(f"No phone for lead {task.lead_id}")

        # Get template (simplified - would use template service)
        template_id = task.payload.get("template_id")
        message = f"Hi {lead.first_name}, following up on your mortgage inquiry. Reply to connect!"

        client = get_sms_client()
        await client.send_sms(to_number=lead.phone, message=message)

    async def _execute_email_step(self, task: ScheduledTask):
        """Execute email sequence step"""
        from email_service import EmailService

        # Get lead info
        lead = self.db.execute(text("""
            SELECT first_name, email FROM leads WHERE id = :lead_id
        """), {"lead_id": task.lead_id}).fetchone()

        if not lead or not lead.email:
            raise ValueError(f"No email for lead {task.lead_id}")

        # Get template (simplified)
        template_id = task.payload.get("template_id")
        subject = "Following up on your mortgage inquiry"
        html_content = f"<p>Hi {lead.first_name},</p><p>Just checking in...</p>"

        service = EmailService()
        service.send_html_email(
            to_email=lead.email,
            subject=subject,
            html_content=html_content,
        )

    async def _execute_call_step(self, task: ScheduledTask):
        """Queue a call in the dialer"""
        from telephony.dialer_engine import DialerEngine

        engine = DialerEngine(self.db)
        engine.add_to_queue(
            lead_id=task.lead_id,
            priority="normal",
            script_id=task.payload.get("template_id"),
        )

    async def _handle_sla_check(self, task: ScheduledTask):
        """Handle SLA breach alert"""
        breach_type = task.payload.get("breach_type")

        logger.warning(
            f"SLA BREACH: {breach_type} for lead {task.lead_id} - "
            f"Event: {task.payload.get('event_type')} at {task.payload.get('event_timestamp')}"
        )

        # Update campaign metrics
        if task.campaign_instance_id:
            self.db.execute(text("""
                UPDATE campaign_instances
                SET hot_leads_missed_sla = COALESCE(hot_leads_missed_sla, 0) + 1
                WHERE id = :cid
            """), {"cid": task.campaign_instance_id})
            self.db.commit()

        # Create SLA breach event
        from services.acquisition_engine.event_service import EventService

        event_service = EventService(self.db)
        event_service.ingest_event(
            organization_id=1,
            event_type=EventType.SLA_BREACH.value,
            lead_id=task.lead_id,
            campaign_instance_id=task.campaign_instance_id,
            event_payload={
                "breach_type": breach_type,
                "original_event": task.payload.get("event_type"),
            },
        )

    async def _handle_campaign_metrics(self, task: ScheduledTask):
        """Recalculate campaign metrics"""
        campaign_id = task.campaign_instance_id

        if not campaign_id:
            return

        # Count conversions
        counts = self.db.execute(text("""
            SELECT
                COUNT(CASE WHEN conversion_type = 'lead' THEN 1 END) as leads,
                COUNT(CASE WHEN conversion_type = 'meeting' THEN 1 END) as meetings,
                COUNT(CASE WHEN conversion_type = 'application' THEN 1 END) as applications,
                COUNT(CASE WHEN conversion_type = 'funded' THEN 1 END) as funded,
                COALESCE(SUM(CASE WHEN conversion_type = 'funded' THEN estimated_revenue END), 0) as revenue
            FROM campaign_attributions
            WHERE campaign_instance_id = :cid
        """), {"cid": campaign_id}).fetchone()

        # Update campaign
        self.db.execute(text("""
            UPDATE campaign_instances SET
                leads_generated = :leads,
                meetings_booked = :meetings,
                applications_started = :applications,
                loans_closed = :funded,
                revenue_attributed = :revenue,
                cost_per_lead = CASE WHEN :leads > 0
                    THEN total_spend / :leads ELSE NULL END,
                cost_per_funded_loan = CASE WHEN :funded > 0
                    THEN total_spend / :funded ELSE NULL END,
                roi_percentage = CASE WHEN total_spend > 0
                    THEN ((:revenue - total_spend) / total_spend) * 100 ELSE NULL END
            WHERE id = :cid
        """), {
            "cid": campaign_id,
            "leads": counts.leads or 0,
            "meetings": counts.meetings or 0,
            "applications": counts.applications or 0,
            "funded": counts.funded or 0,
            "revenue": float(counts.revenue or 0),
        })
        self.db.commit()

        logger.info(f"Updated metrics for campaign {campaign_id}")

    async def _handle_temperature_decay(self, task: ScheduledTask):
        """Apply temperature decay to stale leads"""
        # Decay leads with no activity in X days
        decay_days = 14

        self.db.execute(text("""
            UPDATE lead_temperatures SET
                score = GREATEST(score - 10, 0),
                temperature = CASE
                    WHEN score - 10 >= 70 THEN 'HOT'
                    WHEN score - 10 >= 40 THEN 'WARM'
                    ELSE 'COLD'
                END,
                last_calculated_at = :now
            WHERE days_since_last_activity >= :decay_days
            AND score > 0
        """), {"now": datetime.utcnow(), "decay_days": decay_days})
        self.db.commit()

        logger.info("Applied temperature decay to stale leads")

    async def _handle_stale_lead_alert(self, task: ScheduledTask):
        """Alert on stale leads that need attention"""
        # Find hot leads that have gone cold
        stale = self.db.execute(text("""
            SELECT lt.lead_id, lt.temperature, lt.days_since_last_activity
            FROM lead_temperatures lt
            WHERE lt.temperature IN ('HOT', 'WARM')
            AND lt.days_since_last_activity >= 7
        """)).fetchall()

        for lead in stale:
            logger.warning(
                f"Stale lead alert: Lead {lead.lead_id} was {lead.temperature} "
                f"but inactive for {lead.days_since_last_activity} days"
            )


# =============================================================================
# TASK RUNNER
# =============================================================================

_processor: Optional[TaskProcessor] = None


def get_processor() -> TaskProcessor:
    """Get or create the global task processor"""
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor


async def run_processor():
    """Run the task processor (for use with asyncio)"""
    processor = get_processor()
    await processor.start()


def schedule_task(task: ScheduledTask):
    """Schedule a task for background processing"""
    processor = get_processor()
    processor.add_task(task)


# Convenience functions for common tasks
def schedule_speed_to_lead(lead_id: int, campaign_instance_id: str = None):
    """Schedule speed-to-lead processing for a lead"""
    schedule_task(ScheduledTask(
        task_type=TaskType.SPEED_TO_LEAD,
        lead_id=lead_id,
        campaign_instance_id=campaign_instance_id,
        priority=1,
    ))


def schedule_retry(
    action_type: str,
    lead_id: int,
    payload: Dict[str, Any],
    delay_seconds: int = 60,
):
    """Schedule a retry for a failed action"""
    schedule_task(ScheduledTask(
        task_type=TaskType.RETRY_ACTION,
        lead_id=lead_id,
        payload={"action_type": action_type, **payload},
        scheduled_at=datetime.utcnow() + timedelta(seconds=delay_seconds),
        priority=2,
    ))


def schedule_campaign_metrics_update(campaign_instance_id: str):
    """Schedule campaign metrics recalculation"""
    schedule_task(ScheduledTask(
        task_type=TaskType.CAMPAIGN_METRICS,
        campaign_instance_id=campaign_instance_id,
        priority=5,
    ))
