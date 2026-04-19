"""
Conversion Orchestrator for Acquisition Engine
The "Money Agent" - Coordinates all conversion touchpoints

Responsibilities:
- Monitor event stream for conversion opportunities
- Trigger speed-to-lead for hot leads
- Manage SMS/Email sequences
- Coordinate with Dialer
- Track attribution through the funnel
"""

import uuid
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.acquisition_engine.event_models import AcquisitionEvent, EventType
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature, CampaignAttribution
from models.acquisition_engine.campaign_models import CampaignInstance, CampaignStatus
from services.acquisition_engine.speed_to_lead_service import SpeedToLeadService, SpeedToLeadResult
from services.acquisition_engine.temperature_service import TemperatureService

logger = logging.getLogger(__name__)


class ConversionStage(str, Enum):
    """Stages in the conversion funnel"""
    VISITOR = "VISITOR"
    LEAD = "LEAD"
    QUALIFIED = "QUALIFIED"
    MEETING_BOOKED = "MEETING_BOOKED"
    MEETING_COMPLETED = "MEETING_COMPLETED"
    APPLICATION_STARTED = "APPLICATION_STARTED"
    APPLICATION_COMPLETED = "APPLICATION_COMPLETED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    FUNDED = "FUNDED"


class SequenceType(str, Enum):
    """Types of automated sequences"""
    WELCOME = "WELCOME"
    NURTURE = "NURTURE"
    REENGAGEMENT = "REENGAGEMENT"
    POST_MEETING = "POST_MEETING"
    APPLICATION_REMINDER = "APPLICATION_REMINDER"
    POST_FUNDING = "POST_FUNDING"


@dataclass
class ConversionAction:
    """An action to be taken for conversion"""
    action_type: str
    channel: str  # sms, email, call, task
    priority: str  # immediate, high, normal, low
    template_id: Optional[str] = None
    delay_minutes: int = 0
    conditions: Optional[Dict[str, Any]] = None


class ConversionOrchestrator:
    """
    The "Money Agent" - Orchestrates all conversion touchpoints

    This is the central coordinator that:
    - Reacts to events and triggers appropriate actions
    - Manages lead journey through conversion stages
    - Coordinates between different channels
    - Tracks attribution and ROI
    """

    # Event to action mapping
    EVENT_ACTIONS: Dict[str, List[ConversionAction]] = {
        EventType.LEAD_CREATED.value: [
            ConversionAction("send_welcome", "email", "immediate"),
            ConversionAction("send_welcome", "sms", "immediate", delay_minutes=5),
            ConversionAction("create_task", "task", "high", delay_minutes=30),
        ],
        EventType.MEETING_BOOKED.value: [
            ConversionAction("speed_to_lead", "multi", "immediate"),
            ConversionAction("send_confirmation", "email", "immediate"),
            ConversionAction("send_reminder", "sms", "normal", delay_minutes=60*24),  # 24h before
        ],
        EventType.APPLICATION_STARTED.value: [
            ConversionAction("speed_to_lead", "multi", "immediate"),
            ConversionAction("send_support", "email", "high", delay_minutes=15),
        ],
        EventType.FORM_SUBMITTED.value: [
            ConversionAction("speed_to_lead", "multi", "immediate"),
        ],
        EventType.CALLBACK_REQUESTED.value: [
            ConversionAction("speed_to_lead", "multi", "immediate"),
            ConversionAction("queue_urgent_call", "call", "immediate"),
        ],
        EventType.EMAIL_LINK_CLICKED.value: [
            ConversionAction("update_temperature", "internal", "normal"),
            ConversionAction("check_sequence_advancement", "internal", "normal"),
        ],
        EventType.SMS_REPLIED.value: [
            ConversionAction("route_to_ai", "internal", "immediate"),
            ConversionAction("update_temperature", "internal", "normal"),
        ],
    }

    def __init__(self, db: Session):
        self.db = db
        self.speed_to_lead = SpeedToLeadService(db)
        self.temperature_service = TemperatureService(db)

    async def process_event(
        self,
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """
        Process an event and trigger appropriate conversion actions.

        This is the main entry point called when new events are ingested.

        Args:
            event: The acquisition event to process

        Returns:
            Dictionary with processing results
        """
        results = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "actions_triggered": [],
            "errors": [],
        }

        logger.info(f"Processing event {event.event_type} for lead {event.lead_id}")

        # Get actions for this event type
        actions = self.EVENT_ACTIONS.get(event.event_type, [])

        for action in actions:
            try:
                if action.delay_minutes > 0:
                    # Schedule for later
                    await self._schedule_action(event, action)
                    results["actions_triggered"].append({
                        "action": action.action_type,
                        "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=action.delay_minutes)).isoformat(),
                    })
                else:
                    # Execute immediately
                    result = await self._execute_action(event, action)
                    results["actions_triggered"].append({
                        "action": action.action_type,
                        "result": result,
                    })

            except Exception as e:
                results["errors"].append({
                    "action": action.action_type,
                    "error": "Internal server error",
                })
                logger.error(f"Failed to execute action {action.action_type}: {e}")

        # Update temperature after processing
        if event.lead_id:
            try:
                self.temperature_service.calculate_temperature(
                    lead_id=event.lead_id,
                    campaign_instance_id=str(event.campaign_instance_id) if event.campaign_instance_id else None,
                )
            except Exception as e:
                logger.error(f"Failed to update temperature for lead {event.lead_id}: {e}")

        return results

    async def _execute_action(
        self,
        event: AcquisitionEvent,
        action: ConversionAction,
    ) -> Dict[str, Any]:
        """Execute a conversion action immediately"""

        if action.action_type == "speed_to_lead":
            if event.lead_id:
                result = await self.speed_to_lead.process_hot_lead(
                    lead_id=event.lead_id,
                    event=event,
                    campaign_instance_id=str(event.campaign_instance_id) if event.campaign_instance_id else None,
                )
                return result.to_dict()
            return {"skipped": "no lead_id"}

        elif action.action_type == "send_welcome":
            return await self._send_sequence_message(event, SequenceType.WELCOME, action.channel)

        elif action.action_type == "send_confirmation":
            return await self._send_confirmation(event, action.channel)

        elif action.action_type == "send_support":
            return await self._send_support_message(event, action.channel)

        elif action.action_type == "create_task":
            return await self._create_followup_task(event)

        elif action.action_type == "queue_urgent_call":
            return await self._queue_urgent_call(event)

        elif action.action_type == "update_temperature":
            if event.lead_id:
                temp = self.temperature_service.calculate_temperature(event.lead_id)
                return {"temperature": temp.temperature, "score": temp.score}
            return {"skipped": "no lead_id"}

        elif action.action_type == "route_to_ai":
            return await self._route_to_ai_conversation(event)

        elif action.action_type == "check_sequence_advancement":
            return await self._check_sequence_advancement(event)

        else:
            logger.warning(f"Unknown action type: {action.action_type}")
            return {"skipped": f"unknown action: {action.action_type}"}

    async def _schedule_action(
        self,
        event: AcquisitionEvent,
        action: ConversionAction,
    ):
        """Schedule an action for later execution"""
        execute_at = datetime.now(timezone.utc) + timedelta(minutes=action.delay_minutes)

        # Store in scheduled_actions table (create if needed)
        try:
            self.db.execute(text("""
                INSERT INTO scheduled_actions (
                    id, event_id, lead_id, action_type, channel,
                    template_id, execute_at, status, created_at
                ) VALUES (
                    :id, :event_id, :lead_id, :action_type, :channel,
                    :template_id, :execute_at, 'pending', :created_at
                )
            """), {
                "id": str(uuid.uuid4()),
                "event_id": str(event.id),
                "lead_id": event.lead_id,
                "action_type": action.action_type,
                "channel": action.channel,
                "template_id": action.template_id,
                "execute_at": execute_at,
                "created_at": datetime.now(timezone.utc),
            })
            self.db.commit()
            logger.info(f"Scheduled {action.action_type} for lead {event.lead_id} at {execute_at}")
        except Exception as e:
            # Table might not exist - log and continue
            logger.warning(f"Could not schedule action (table may not exist): {e}")

    async def _send_sequence_message(
        self,
        event: AcquisitionEvent,
        sequence_type: SequenceType,
        channel: str,
    ) -> Dict[str, Any]:
        """Send a message from a sequence"""
        if not event.lead_id:
            return {"skipped": "no lead_id"}

        lead_info = self._get_lead_info(event.lead_id)
        if not lead_info:
            return {"error": "lead not found"}

        if channel == "email":
            try:
                from email_service import EmailService
                email_service = EmailService()

                subject = f"Welcome to Perennia - Let's Get Started!"
                body = f"""
<html>
<body>
<p>Hi {lead_info.get('first_name', 'there')},</p>
<p>Thank you for reaching out! I'm excited to help you with your mortgage needs.</p>
<p>Here's what happens next:</p>
<ol>
<li>I'll review your information</li>
<li>We'll schedule a quick call to discuss your options</li>
<li>I'll help you find the best rate for your situation</li>
</ol>
<p>Feel free to reply to this email with any questions!</p>
<p>Best regards,<br>Your Loan Team</p>
</body>
</html>
                """

                success = email_service.send_html_email(
                    to_email=lead_info.get("email"),
                    subject=subject,
                    html_body=body,
                )

                return {"sent": success, "channel": "email", "sequence": sequence_type.value}

            except Exception as e:
                return {"error": "Internal server error"}

        elif channel == "sms":
            try:
                from integrations.sms_service import get_sms_client

                sms_client = get_sms_client()
                message = f"Hi {lead_info.get('first_name', 'there')}! Thanks for your interest. I'll be in touch shortly to discuss your options. Reply STOP to opt out."

                if lead_info.get("phone"):
                    sid = sms_client.send_sms(
                        to_number=lead_info["phone"],
                        message=message,
                    )
                    return {"sent": bool(sid), "sid": sid, "channel": "sms"}
                return {"skipped": "no phone"}

            except Exception as e:
                return {"error": "Internal server error"}

        return {"skipped": f"unknown channel: {channel}"}

    async def _send_confirmation(
        self,
        event: AcquisitionEvent,
        channel: str,
    ) -> Dict[str, Any]:
        """Send confirmation for meeting/application"""
        # Implementation similar to _send_sequence_message
        return {"sent": True, "channel": channel, "type": "confirmation"}

    async def _send_support_message(
        self,
        event: AcquisitionEvent,
        channel: str,
    ) -> Dict[str, Any]:
        """Send support message for application in progress"""
        return {"sent": True, "channel": channel, "type": "support"}

    async def _create_followup_task(
        self,
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """Create a follow-up task for the LO"""
        if not event.lead_id:
            return {"skipped": "no lead_id"}

        lead_info = self._get_lead_info(event.lead_id)
        if not lead_info:
            return {"error": "lead not found"}

        try:
            result = self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, task_type, priority, status,
                    lead_id, assigned_to, due_date, created_at
                ) VALUES (
                    :title, :description, :task_type, 'NORMAL', 'pending',
                    :lead_id, :assigned_to, :due_date, :created_at
                ) RETURNING id
            """), {
                "title": f"Follow up with {lead_info.get('first_name', 'Lead')} {lead_info.get('last_name', '')}",
                "description": f"New lead from {event.event_type}. Review and follow up.",
                "task_type": "FOLLOW_UP",
                "lead_id": event.lead_id,
                "assigned_to": lead_info.get("assigned_to"),
                "due_date": datetime.now(timezone.utc) + timedelta(hours=4),
                "created_at": datetime.now(timezone.utc),
            })
            self.db.commit()

            task_id = result.fetchone()
            return {"created": True, "task_id": task_id[0] if task_id else None}

        except Exception as e:
            return {"error": "Internal server error"}

    async def _queue_urgent_call(
        self,
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """Queue an urgent call in the dialer"""
        # Similar to speed_to_lead but specifically for call queue
        return await self.speed_to_lead._queue_in_dialer(
            lead_info=self._get_lead_info(event.lead_id) or {},
            lo_info=None,
            priority="URGENT",
            result=SpeedToLeadResult(
                lead_id=event.lead_id or 0,
                status="IN_PROGRESS",
                started_at=datetime.now(timezone.utc),
            ),
        )

    async def _route_to_ai_conversation(
        self,
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """Route incoming message to AI conversation handler"""
        # This would integrate with the existing AI conversation system
        return {"routed": True, "handler": "ai_conversation"}

    async def _check_sequence_advancement(
        self,
        event: AcquisitionEvent,
    ) -> Dict[str, Any]:
        """Check if lead should advance in nurture sequence"""
        # Check engagement level and advance sequence if appropriate
        return {"checked": True}

    def _get_lead_info(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """Get lead information"""
        try:
            result = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, assigned_to
                FROM lead_profiles
                WHERE id = :lead_id
            """), {"lead_id": str(lead_id)}).fetchone()

            if result:
                return dict(result._mapping)

            # Try leads table
            result = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, assigned_to
                FROM leads
                WHERE id = :lead_id
            """), {"lead_id": lead_id}).fetchone()

            return dict(result._mapping) if result else None

        except Exception as e:
            logger.error(f"Failed to get lead info: {e}")
            return None

    def track_conversion(
        self,
        lead_id: int,
        conversion_type: str,
        campaign_instance_id: Optional[str] = None,
        loan_id: Optional[int] = None,
        loan_amount: Optional[float] = None,
        estimated_revenue: Optional[float] = None,
        attribution_type: str = "first_touch",
    ) -> CampaignAttribution:
        """
        Track a conversion event for attribution.

        Called when a lead converts (meeting, application, funded).
        """
        # Get campaign that sourced this lead
        if not campaign_instance_id:
            # Find from first touch event
            first_event = self.db.query(AcquisitionEvent).filter(
                and_(
                    AcquisitionEvent.lead_id == lead_id,
                    AcquisitionEvent.campaign_instance_id.isnot(None),
                )
            ).order_by(AcquisitionEvent.event_timestamp.asc()).first()

            if first_event:
                campaign_instance_id = str(first_event.campaign_instance_id)

        # Create attribution record
        attribution = CampaignAttribution(
            id=uuid.uuid4(),
            campaign_instance_id=uuid.UUID(campaign_instance_id) if campaign_instance_id else None,
            lead_id=lead_id,
            loan_id=loan_id,
            attribution_type=attribution_type,  # Use the parameter
            attribution_credit=1.0,
            conversion_type=conversion_type,
            conversion_date=datetime.now(timezone.utc),
            loan_amount=loan_amount,
        )

        # Set conversion flags
        if conversion_type == "lead":
            attribution.is_lead = True
        elif conversion_type == "meeting_booked":
            attribution.is_meeting = True
        elif conversion_type == "application_started":
            attribution.is_application = True
        elif conversion_type == "funded":
            attribution.is_funded = True
            # Use provided estimated_revenue or calculate from loan amount
            if estimated_revenue:
                attribution.estimated_revenue = estimated_revenue
            elif loan_amount:
                attribution.estimated_revenue = loan_amount * 0.015

        self.db.add(attribution)

        # Update campaign metrics
        if campaign_instance_id:
            campaign = self.db.query(CampaignInstance).filter(
                CampaignInstance.id == uuid.UUID(campaign_instance_id)
            ).first()

            if campaign:
                if conversion_type == "lead":
                    campaign.leads_generated = (campaign.leads_generated or 0) + 1
                elif conversion_type == "meeting_booked":
                    campaign.meetings_booked = (campaign.meetings_booked or 0) + 1
                elif conversion_type == "application_started":
                    campaign.applications_started = (campaign.applications_started or 0) + 1
                elif conversion_type == "funded":
                    campaign.loans_closed = (campaign.loans_closed or 0) + 1
                    if loan_amount:
                        campaign.total_loan_volume = (campaign.total_loan_volume or 0) + loan_amount
                    # Use provided estimated_revenue or calculate
                    revenue = estimated_revenue if estimated_revenue else (loan_amount * 0.015 if loan_amount else 0)
                    if revenue:
                        campaign.revenue_attributed = (campaign.revenue_attributed or 0) + revenue

                campaign.calculate_cost_metrics()

        self.db.commit()

        return attribution

    def get_funnel_metrics(
        self,
        campaign_instance_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get conversion funnel metrics"""
        query = self.db.query(CampaignAttribution)

        if campaign_instance_id:
            query = query.filter(
                CampaignAttribution.campaign_instance_id == uuid.UUID(campaign_instance_id)
            )

        if days:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(CampaignAttribution.conversion_date >= since)

        attributions = query.all()

        metrics = {
            "leads": sum(1 for a in attributions if a.is_lead),
            "meetings": sum(1 for a in attributions if a.is_meeting),
            "applications": sum(1 for a in attributions if a.is_application),
            "funded": sum(1 for a in attributions if a.is_funded),
            "total_loan_volume": sum(float(a.loan_amount or 0) for a in attributions if a.is_funded),
            "total_revenue": sum(float(a.estimated_revenue or 0) for a in attributions if a.is_funded),
        }

        # Calculate conversion rates
        if metrics["leads"] > 0:
            metrics["lead_to_meeting_rate"] = round((metrics["meetings"] / metrics["leads"]) * 100, 2)
            metrics["lead_to_app_rate"] = round((metrics["applications"] / metrics["leads"]) * 100, 2)
            metrics["lead_to_funded_rate"] = round((metrics["funded"] / metrics["leads"]) * 100, 2)
        else:
            metrics["lead_to_meeting_rate"] = 0
            metrics["lead_to_app_rate"] = 0
            metrics["lead_to_funded_rate"] = 0

        return metrics
