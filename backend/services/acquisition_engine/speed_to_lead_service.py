"""
Speed-to-Lead Service for Acquisition Engine
Ensures hot leads are contacted within SLA (5 minutes)

Responsibilities:
- Monitor for hot lead events
- Orchestrate multi-channel outreach (SMS, Email, Dialer, Push)
- Track SLA compliance
- Create urgent callback tasks
"""

import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.acquisition_engine.event_models import AcquisitionEvent, EventType
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature
from models.acquisition_engine.campaign_models import CampaignInstance

logger = logging.getLogger(__name__)


class SpeedToLeadAction(str, Enum):
    """Actions that can be triggered for speed-to-lead"""
    SMS_SENT = "SMS_SENT"
    EMAIL_SENT = "EMAIL_SENT"
    DIALER_QUEUED = "DIALER_QUEUED"
    PUSH_NOTIFICATION = "PUSH_NOTIFICATION"
    TASK_CREATED = "TASK_CREATED"
    WEBHOOK_FIRED = "WEBHOOK_FIRED"


class SpeedToLeadStatus(str, Enum):
    """Status of speed-to-lead execution"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"  # Some actions completed, some failed
    FAILED = "FAILED"
    SLA_MISSED = "SLA_MISSED"


@dataclass
class SpeedToLeadConfig:
    """Configuration for speed-to-lead execution"""
    hot_lead_sla_seconds: int = 300  # 5 minutes
    warm_lead_sla_seconds: int = 3600  # 1 hour
    enable_sms: bool = True
    enable_email: bool = True
    enable_dialer: bool = True
    enable_push_notification: bool = True
    enable_task_creation: bool = True
    sms_template: Optional[str] = None
    email_template: Optional[str] = None
    dialer_priority: str = "URGENT"
    max_retry_attempts: int = 3


@dataclass
class SpeedToLeadResult:
    """Result of speed-to-lead execution"""
    lead_id: int
    status: SpeedToLeadStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    response_time_seconds: Optional[int] = None
    within_sla: bool = False
    actions_attempted: List[Dict[str, Any]] = field(default_factory=list)
    actions_completed: List[SpeedToLeadAction] = field(default_factory=list)
    actions_failed: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "response_time_seconds": self.response_time_seconds,
            "within_sla": self.within_sla,
            "actions_completed": [a.value for a in self.actions_completed],
            "actions_failed": self.actions_failed,
            "error": self.error,
        }


class SpeedToLeadService:
    """
    Speed-to-Lead Service

    When a hot lead is detected, this service orchestrates immediate outreach:
    1. Send SMS (if consented)
    2. Send Email confirmation
    3. Queue in Dialer as URGENT
    4. Create callback task
    5. Push notification to LO

    SLA Targets:
    - Hot leads: 5 minutes
    - Warm leads: 1 hour
    """

    # Default SMS templates
    DEFAULT_SMS_TEMPLATES = {
        "hot_lead": (
            "Hi {first_name}! Thank you for your interest in a mortgage. "
            "I'm {lo_name}, your dedicated loan officer. I'll be reaching out shortly. "
            "Reply STOP to opt out."
        ),
        "meeting_booked": (
            "Hi {first_name}! Your consultation is confirmed for {meeting_time}. "
            "I look forward to speaking with you! - {lo_name}"
        ),
        "application_started": (
            "Hi {first_name}! I noticed you started your application. "
            "I'm here to help - feel free to reply with any questions. - {lo_name}"
        ),
    }

    # Default Email templates
    DEFAULT_EMAIL_TEMPLATES = {
        "hot_lead": {
            "subject": "Thank you for your inquiry - Next Steps",
            "body": """
<html>
<body>
<p>Hi {first_name},</p>

<p>Thank you for your interest in exploring mortgage options! I'm {lo_name}, your dedicated loan officer.</p>

<p>I'll be reaching out shortly to discuss your needs and answer any questions you may have.</p>

<p>In the meantime, here are some helpful resources:</p>
<ul>
<li>Check current rates on our <a href="{rates_url}">rates page</a></li>
<li>Use our <a href="{calculator_url}">mortgage calculator</a></li>
</ul>

<p>Best regards,<br>
{lo_name}<br>
{company_name}</p>
</body>
</html>
            """,
        },
    }

    def __init__(self, db: Session):
        self.db = db
        self._sms_client = None
        self._email_service = None

    @property
    def sms_client(self):
        """Lazy load SMS client"""
        if self._sms_client is None:
            try:
                from integrations.sms_service import get_sms_client
                self._sms_client = get_sms_client()
            except ImportError:
                logger.warning("SMS client not available")
                self._sms_client = False
        return self._sms_client if self._sms_client else None

    @property
    def email_service(self):
        """Lazy load email service"""
        if self._email_service is None:
            try:
                from email_service import EmailService
                self._email_service = EmailService()
            except ImportError:
                logger.warning("Email service not available")
                self._email_service = False
        return self._email_service if self._email_service else None

    async def process_hot_lead(
        self,
        lead_id: int,
        event: AcquisitionEvent,
        campaign_instance_id: Optional[str] = None,
        config: Optional[SpeedToLeadConfig] = None,
    ) -> SpeedToLeadResult:
        """
        Process a hot lead with speed-to-lead protocol.

        This is the main entry point when a hot lead event is detected.
        Orchestrates all outreach channels in parallel for fastest response.

        Args:
            lead_id: Lead ID
            event: The triggering event
            campaign_instance_id: Optional campaign for configuration
            config: Optional custom configuration

        Returns:
            SpeedToLeadResult with execution details
        """
        started_at = datetime.now(timezone.utc)
        result = SpeedToLeadResult(
            lead_id=lead_id,
            status=SpeedToLeadStatus.IN_PROGRESS,
            started_at=started_at,
        )

        logger.info(f"Processing hot lead {lead_id} for event {event.event_type}")

        # Get configuration
        if config is None:
            config = self._get_config_for_campaign(campaign_instance_id)

        # Get lead details
        lead_info = self._get_lead_info(lead_id)
        if not lead_info:
            result.status = SpeedToLeadStatus.FAILED
            result.error = f"Lead {lead_id} not found"
            return result

        # Get LO info
        lo_info = self._get_lo_info(lead_info.get("assigned_to"))

        # Build template context
        template_context = self._build_template_context(lead_info, lo_info, event)

        # Execute actions in parallel
        tasks = []

        if config.enable_sms and lead_info.get("phone") and lead_info.get("sms_consent", True):
            tasks.append(self._send_sms(lead_info, template_context, event.event_type, result))

        if config.enable_email and lead_info.get("email"):
            tasks.append(self._send_email(lead_info, template_context, event.event_type, result))

        if config.enable_dialer and lead_info.get("phone"):
            tasks.append(self._queue_in_dialer(lead_info, lo_info, config.dialer_priority, result))

        if config.enable_task_creation:
            tasks.append(self._create_callback_task(lead_info, lo_info, event, result))

        if config.enable_push_notification and lo_info:
            tasks.append(self._send_push_notification(lead_info, lo_info, event, result))

        # Run all tasks concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate response time and SLA compliance
        completed_at = datetime.now(timezone.utc)
        response_time = (completed_at - started_at).total_seconds()

        result.completed_at = completed_at
        result.response_time_seconds = int(response_time)
        result.within_sla = response_time <= config.hot_lead_sla_seconds

        # Determine final status
        if result.actions_failed and not result.actions_completed:
            result.status = SpeedToLeadStatus.FAILED
        elif result.actions_failed:
            result.status = SpeedToLeadStatus.PARTIAL
        elif not result.within_sla:
            result.status = SpeedToLeadStatus.SLA_MISSED
        else:
            result.status = SpeedToLeadStatus.COMPLETED

        # Record result
        await self._record_result(lead_id, event, result, campaign_instance_id)

        logger.info(
            f"Speed-to-lead for lead {lead_id}: {result.status.value} "
            f"in {result.response_time_seconds}s (SLA: {result.within_sla})"
        )

        return result

    def _get_config_for_campaign(self, campaign_instance_id: Optional[str]) -> SpeedToLeadConfig:
        """Get speed-to-lead config from campaign or defaults"""
        if campaign_instance_id:
            try:
                campaign = self.db.query(CampaignInstance).filter(
                    CampaignInstance.id == uuid.UUID(campaign_instance_id)
                ).first()

                if campaign and campaign.speed_to_lead_config:
                    config_dict = campaign.speed_to_lead_config
                    return SpeedToLeadConfig(
                        hot_lead_sla_seconds=config_dict.get("hot_lead_sla_seconds", 300),
                        warm_lead_sla_seconds=config_dict.get("warm_lead_sla_seconds", 3600),
                        enable_sms=config_dict.get("enable_sms", True),
                        enable_email=config_dict.get("enable_email", True),
                        enable_dialer=config_dict.get("enable_dialer", True),
                        enable_push_notification=config_dict.get("enable_push_notification", True),
                    )
            except Exception as e:
                logger.warning(f"Failed to get campaign config: {e}")

        return SpeedToLeadConfig()

    def _get_lead_info(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """Get lead information from database"""
        try:
            from sqlalchemy import text
            result = self.db.execute(text("""
                SELECT
                    id, first_name, last_name, email, phone,
                    loan_officer as assigned_to, source, stage,
                    loan_purpose, loan_amount, property_type
                FROM lead_profiles
                WHERE id = :lead_id
            """), {"lead_id": str(lead_id)}).fetchone()

            if result:
                return dict(result._mapping)

            # Try leads table if lead_profiles doesn't have it
            result = self.db.execute(text("""
                SELECT
                    id, first_name, last_name, email, phone,
                    assigned_to, source, status as stage
                FROM leads
                WHERE id = :lead_id
            """), {"lead_id": lead_id}).fetchone()

            if result:
                return dict(result._mapping)

        except Exception as e:
            logger.error(f"Failed to get lead info for {lead_id}: {e}")

        return None

    def _get_lo_info(self, lo_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Get loan officer information"""
        if not lo_id:
            return None

        try:
            from sqlalchemy import text
            result = self.db.execute(text("""
                SELECT id, name, email, phone
                FROM users
                WHERE id = :lo_id
            """), {"lo_id": lo_id}).fetchone()

            if result:
                return dict(result._mapping)
        except Exception as e:
            logger.error(f"Failed to get LO info for {lo_id}: {e}")

        return None

    def _build_template_context(
        self,
        lead_info: Dict[str, Any],
        lo_info: Optional[Dict[str, Any]],
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """Build context for template rendering"""
        return {
            "first_name": lead_info.get("first_name", "there"),
            "last_name": lead_info.get("last_name", ""),
            "email": lead_info.get("email", ""),
            "phone": lead_info.get("phone", ""),
            "lo_name": lo_info.get("name", "Your Loan Officer") if lo_info else "Your Loan Officer",
            "lo_email": lo_info.get("email", "") if lo_info else "",
            "lo_phone": lo_info.get("phone", "") if lo_info else "",
            "company_name": "Perennia AI",
            "loan_purpose": lead_info.get("loan_purpose", "home loan"),
            "loan_amount": lead_info.get("loan_amount", ""),
            "event_type": event.event_type,
            "rates_url": "https://www.perenniaai.com/rates",
            "calculator_url": "https://www.perenniaai.com/calculator",
            "meeting_time": event.event_payload.get("meeting_time", "") if event.event_payload else "",
        }

    async def _send_sms(
        self,
        lead_info: Dict[str, Any],
        context: Dict[str, Any],
        event_type: str,
        result: SpeedToLeadResult,
    ):
        """Send SMS to lead"""
        action = {"action": SpeedToLeadAction.SMS_SENT.value, "phone": lead_info.get("phone")}
        result.actions_attempted.append(action)

        try:
            if not self.sms_client:
                raise Exception("SMS client not available")

            # Select template based on event type
            template_key = "hot_lead"
            if event_type == EventType.MEETING_BOOKED.value:
                template_key = "meeting_booked"
            elif event_type == EventType.APPLICATION_STARTED.value:
                template_key = "application_started"

            template = self.DEFAULT_SMS_TEMPLATES.get(template_key, self.DEFAULT_SMS_TEMPLATES["hot_lead"])
            message = template.format(**context)

            # Send SMS
            sid = await self.sms_client.send_sms(
                to_number=lead_info["phone"],
                message=message,
            )

            if sid:
                result.actions_completed.append(SpeedToLeadAction.SMS_SENT)
                action["sid"] = sid
                action["success"] = True
                logger.info(f"SMS sent to lead {lead_info['id']}: {sid}")
            else:
                raise Exception("SMS send returned no SID")

        except Exception as e:
            action["success"] = False
            action["error"] = str(e)
            result.actions_failed.append(action)
            logger.error(f"Failed to send SMS to lead {lead_info['id']}: {e}")

    async def _send_email(
        self,
        lead_info: Dict[str, Any],
        context: Dict[str, Any],
        event_type: str,
        result: SpeedToLeadResult,
    ):
        """Send email to lead"""
        action = {"action": SpeedToLeadAction.EMAIL_SENT.value, "email": lead_info.get("email")}
        result.actions_attempted.append(action)

        try:
            if not self.email_service:
                raise Exception("Email service not available")

            # Get template
            template = self.DEFAULT_EMAIL_TEMPLATES.get("hot_lead")
            subject = template["subject"].format(**context)
            body = template["body"].format(**context)

            # Send email (routes through Salesforce when connected)
            success = await self.email_service.send_html_email_sf(
                to_email=lead_info["email"],
                subject=subject,
                html_body=body,
                db=self.db,
                user_id=lead_info.get("assigned_to"),
            )

            if success:
                result.actions_completed.append(SpeedToLeadAction.EMAIL_SENT)
                action["success"] = True
                logger.info(f"Email sent to lead {lead_info['id']}")
            else:
                raise Exception("Email send returned False")

        except Exception as e:
            action["success"] = False
            action["error"] = str(e)
            result.actions_failed.append(action)
            logger.error(f"Failed to send email to lead {lead_info['id']}: {e}")

    async def _queue_in_dialer(
        self,
        lead_info: Dict[str, Any],
        lo_info: Optional[Dict[str, Any]],
        priority: str,
        result: SpeedToLeadResult,
    ):
        """Queue lead in power dialer"""
        action = {"action": SpeedToLeadAction.DIALER_QUEUED.value, "phone": lead_info.get("phone")}
        result.actions_attempted.append(action)

        try:
            from sqlalchemy import text

            # Create dialer task
            task_id = self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, task_type, priority, status,
                    lead_id, assigned_to, due_date, created_at
                ) VALUES (
                    :title, :description, 'CALL', :priority, 'pending',
                    :lead_id, :assigned_to, :due_date, :created_at
                ) RETURNING id
            """), {
                "title": f"URGENT: Call hot lead - {lead_info.get('first_name', '')} {lead_info.get('last_name', '')}",
                "description": f"Hot lead requires immediate callback. Phone: {lead_info.get('phone')}",
                "priority": priority,
                "lead_id": lead_info.get("id"),
                "assigned_to": lo_info.get("id") if lo_info else None,
                "due_date": datetime.now(timezone.utc) + timedelta(minutes=5),
                "created_at": datetime.now(timezone.utc),
            }).fetchone()

            self.db.commit()

            if task_id:
                result.actions_completed.append(SpeedToLeadAction.DIALER_QUEUED)
                action["task_id"] = task_id[0]
                action["success"] = True
                logger.info(f"Lead {lead_info['id']} queued in dialer as {priority}")
            else:
                raise Exception("Failed to create dialer task")

        except Exception as e:
            action["success"] = False
            action["error"] = str(e)
            result.actions_failed.append(action)
            logger.error(f"Failed to queue lead {lead_info['id']} in dialer: {e}")

    async def _create_callback_task(
        self,
        lead_info: Dict[str, Any],
        lo_info: Optional[Dict[str, Any]],
        event: AcquisitionEvent,
        result: SpeedToLeadResult,
    ):
        """Create urgent callback task"""
        action = {"action": SpeedToLeadAction.TASK_CREATED.value}
        result.actions_attempted.append(action)

        try:
            from sqlalchemy import text

            # Create task
            task_id = self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, task_type, priority, status,
                    lead_id, assigned_to, due_date, created_at
                ) VALUES (
                    :title, :description, :task_type, 'HIGH', 'pending',
                    :lead_id, :assigned_to, :due_date, :created_at
                ) RETURNING id
            """), {
                "title": f"Follow up: {event.event_type} - {lead_info.get('first_name', '')}",
                "description": f"Hot lead event: {event.event_type}. Respond within 5 minutes.",
                "task_type": "FOLLOW_UP",
                "lead_id": lead_info.get("id"),
                "assigned_to": lo_info.get("id") if lo_info else None,
                "due_date": datetime.now(timezone.utc) + timedelta(minutes=30),
                "created_at": datetime.now(timezone.utc),
            }).fetchone()

            self.db.commit()

            if task_id:
                result.actions_completed.append(SpeedToLeadAction.TASK_CREATED)
                action["task_id"] = task_id[0]
                action["success"] = True
                logger.info(f"Callback task created for lead {lead_info['id']}")
            else:
                raise Exception("Failed to create callback task")

        except Exception as e:
            action["success"] = False
            action["error"] = str(e)
            result.actions_failed.append(action)
            logger.error(f"Failed to create callback task for lead {lead_info['id']}: {e}")

    async def _send_push_notification(
        self,
        lead_info: Dict[str, Any],
        lo_info: Dict[str, Any],
        event: AcquisitionEvent,
        result: SpeedToLeadResult,
    ):
        """Send push notification to LO"""
        action = {"action": SpeedToLeadAction.PUSH_NOTIFICATION.value, "lo_id": lo_info.get("id")}
        result.actions_attempted.append(action)

        try:
            # For now, create a notification record
            # In production, this would use Firebase/WebPush
            from sqlalchemy import text

            self.db.execute(text("""
                INSERT INTO notifications (
                    user_id, title, message, type, priority,
                    read, created_at, data
                ) VALUES (
                    :user_id, :title, :message, 'HOT_LEAD', 'URGENT',
                    false, :created_at, :data
                )
            """), {
                "user_id": lo_info.get("id"),
                "title": "Hot Lead Alert",
                "message": f"New hot lead: {lead_info.get('first_name', '')} - {event.event_type}",
                "created_at": datetime.now(timezone.utc),
                "data": str({
                    "lead_id": lead_info.get("id"),
                    "event_type": event.event_type,
                    "phone": lead_info.get("phone"),
                }),
            })
            self.db.commit()

            result.actions_completed.append(SpeedToLeadAction.PUSH_NOTIFICATION)
            action["success"] = True
            logger.info(f"Push notification sent to LO {lo_info['id']} for lead {lead_info['id']}")

        except Exception as e:
            action["success"] = False
            action["error"] = str(e)
            result.actions_failed.append(action)
            logger.error(f"Failed to send push notification: {e}")

    async def _record_result(
        self,
        lead_id: int,
        event: AcquisitionEvent,
        result: SpeedToLeadResult,
        campaign_instance_id: Optional[str],
    ):
        """Record speed-to-lead result for metrics"""
        try:
            # Create a speed-to-lead event
            stl_event = AcquisitionEvent(
                id=uuid.uuid4(),
                organization_id=event.organization_id,
                campaign_instance_id=event.campaign_instance_id,
                lead_id=lead_id,
                event_type=EventType.SPEED_TO_LEAD_SUCCESS.value if result.within_sla else EventType.SLA_BREACH.value,
                event_payload={
                    "trigger_event": event.event_type,
                    "response_time_seconds": result.response_time_seconds,
                    "within_sla": result.within_sla,
                    "actions_completed": [a.value for a in result.actions_completed],
                    "status": result.status.value,
                },
                event_timestamp=datetime.now(timezone.utc),
            )
            self.db.add(stl_event)

            # Update campaign metrics
            if campaign_instance_id:
                campaign = self.db.query(CampaignInstance).filter(
                    CampaignInstance.id == uuid.UUID(campaign_instance_id)
                ).first()

                if campaign:
                    if result.within_sla:
                        campaign.hot_leads_within_sla = (campaign.hot_leads_within_sla or 0) + 1
                    else:
                        campaign.hot_leads_missed_sla = (campaign.hot_leads_missed_sla or 0) + 1

                    # Update average response time
                    current_avg = campaign.avg_speed_to_first_contact_seconds or 0
                    total_hot = (campaign.hot_leads_within_sla or 0) + (campaign.hot_leads_missed_sla or 0)
                    if total_hot > 0:
                        campaign.avg_speed_to_first_contact_seconds = int(
                            (current_avg * (total_hot - 1) + result.response_time_seconds) / total_hot
                        )

            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to record speed-to-lead result: {e}")

    def get_sla_metrics(
        self,
        campaign_instance_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get speed-to-lead SLA metrics"""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        query = self.db.query(AcquisitionEvent).filter(
            and_(
                AcquisitionEvent.event_type.in_([
                    EventType.SPEED_TO_LEAD_SUCCESS.value,
                    EventType.SLA_BREACH.value,
                ]),
                AcquisitionEvent.event_timestamp >= since,
            )
        )

        if campaign_instance_id:
            query = query.filter(
                AcquisitionEvent.campaign_instance_id == uuid.UUID(campaign_instance_id)
            )

        events = query.all()

        success_count = sum(1 for e in events if e.event_type == EventType.SPEED_TO_LEAD_SUCCESS.value)
        breach_count = sum(1 for e in events if e.event_type == EventType.SLA_BREACH.value)
        total = success_count + breach_count

        response_times = [
            e.event_payload.get("response_time_seconds", 0)
            for e in events
            if e.event_payload
        ]

        return {
            "period_days": days,
            "total_hot_leads": total,
            "within_sla": success_count,
            "missed_sla": breach_count,
            "compliance_rate": round((success_count / total) * 100, 2) if total > 0 else 100,
            "avg_response_time_seconds": int(sum(response_times) / len(response_times)) if response_times else 0,
            "min_response_time_seconds": min(response_times) if response_times else 0,
            "max_response_time_seconds": max(response_times) if response_times else 0,
        }

    async def process_pending_hot_leads(self, max_age_minutes: int = 10):
        """
        Process any pending hot leads that haven't been handled.
        Called by background task scheduler.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

        # Find hot events without speed-to-lead response
        hot_events = self.db.query(AcquisitionEvent).filter(
            and_(
                AcquisitionEvent.event_timestamp >= cutoff,
                AcquisitionEvent.lead_id.isnot(None),
                AcquisitionEvent.event_type.in_([
                    EventType.MEETING_BOOKED.value,
                    EventType.APPLICATION_STARTED.value,
                    EventType.FORM_SUBMITTED.value,
                    EventType.CALLBACK_REQUESTED.value,
                ]),
            )
        ).all()

        processed = 0
        for event in hot_events:
            # Check if already processed
            existing = self.db.query(AcquisitionEvent).filter(
                and_(
                    AcquisitionEvent.lead_id == event.lead_id,
                    AcquisitionEvent.event_type.in_([
                        EventType.SPEED_TO_LEAD_SUCCESS.value,
                        EventType.SLA_BREACH.value,
                    ]),
                    AcquisitionEvent.event_timestamp > event.event_timestamp,
                )
            ).first()

            if not existing:
                await self.process_hot_lead(
                    lead_id=event.lead_id,
                    event=event,
                    campaign_instance_id=str(event.campaign_instance_id) if event.campaign_instance_id else None,
                )
                processed += 1

        return processed
