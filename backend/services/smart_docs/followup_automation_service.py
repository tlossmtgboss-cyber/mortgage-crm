"""
Smart Docs Follow-Up Automation Service

Manages automated multi-step follow-up campaigns for outstanding document
requests. Supports email, SMS, scheduled calls, appointment booking, and
LO escalation with configurable step sequences per campaign type.

Campaign types and default sequences:

INITIAL_REQUEST (when needs list is first generated):
  Step 1: Email with document list + portal link (immediate)
  Step 2: SMS reminder (48 hours)
  Step 3: Email follow-up (96 hours)
  Step 4: Call scheduled / appointment offered (168 hours)
  Step 5: Escalate to LO (240 hours)

GENTLE_REMINDER (periodic check-in):
  Step 1: Friendly email reminder (immediate)
  Step 2: SMS nudge (48 hours)

URGENT_REMINDER (SLA approaching):
  Step 1: Urgent email (immediate)
  Step 2: SMS + call (24 hours)
  Step 3: LO escalation (48 hours)

DOCUMENT_REJECTED (doc was rejected, need re-upload):
  Step 1: Email with rejection reason + fix instructions (immediate)
  Step 2: SMS reminder (72 hours)
  Step 3: Offer appointment for help (120 hours)

DOCUMENT_EXPIRED (doc expired, need fresh version):
  Step 1: Email notifying expiration (immediate)
  Step 2: SMS reminder (48 hours)
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from database.models.document_followup import (
    FollowupCampaign,
    FollowupEvent,
    DocumentAppointment,
    FollowupTemplate,
    CampaignType,
    CampaignStatus,
    CampaignTriggerSource,
    FollowupEventType,
    DeliveryStatus,
    AppointmentType,
    AppointmentStatus,
    LocationType,
)
from models.smart_docs_models import DocumentRequest, RequestStatus

logger = logging.getLogger(__name__)


# =============================================================================
# DEFAULT STEP CONFIGURATIONS
# =============================================================================

_DEFAULT_STEP_CONFIGS: Dict[str, List[Dict[str, Any]]] = {
    "initial_request": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request", "action": "send_email"},
        {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder_sms", "action": "send_sms"},
        {"step": 3, "channel": "email", "delay_hours": 96, "template": "gentle_reminder", "action": "send_email"},
        {"step": 4, "channel": "call", "delay_hours": 168, "template": "appointment_offer", "action": "offer_appointment"},
        {"step": 5, "channel": "escalation", "delay_hours": 240, "template": "escalation", "action": "escalate_to_lo"},
    ],
    "gentle_reminder": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "gentle_reminder", "action": "send_email"},
        {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder_sms", "action": "send_sms"},
    ],
    "urgent_reminder": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "urgent_reminder", "action": "send_email"},
        {"step": 2, "channel": "sms", "delay_hours": 24, "template": "urgent_reminder_sms", "action": "send_sms"},
        {"step": 3, "channel": "escalation", "delay_hours": 48, "template": "escalation", "action": "escalate_to_lo"},
    ],
    "escalation": [
        {"step": 1, "channel": "escalation", "delay_hours": 0, "template": "escalation", "action": "escalate_to_lo"},
    ],
    "appointment_offer": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "appointment_offer", "action": "offer_appointment"},
    ],
    "document_rejected": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "document_rejected", "action": "send_email"},
        {"step": 2, "channel": "sms", "delay_hours": 72, "template": "document_rejected_sms", "action": "send_sms"},
        {"step": 3, "channel": "call", "delay_hours": 120, "template": "appointment_offer", "action": "offer_appointment"},
    ],
    "document_expired": [
        {"step": 1, "channel": "email", "delay_hours": 0, "template": "document_expired", "action": "send_email"},
        {"step": 2, "channel": "sms", "delay_hours": 48, "template": "document_expired_sms", "action": "send_sms"},
    ],
}


# =============================================================================
# DEFAULT TEMPLATES (hardcoded fallbacks)
# =============================================================================

_DEFAULT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "initial_request": {
        "subject": "Documents needed for your loan application",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "To keep your loan moving forward, we need the following documents:\n\n"
            "{{document_list}}\n\n"
            "You can upload them securely here: {{portal_link}}\n\n"
            "If you have any questions, don't hesitate to reach out.\n\n"
            "Best regards,\n{{lo_name}}"
        ),
    },
    "gentle_reminder": {
        "subject": "Friendly reminder: Documents still needed",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "Just a friendly reminder that we're still waiting on a few documents "
            "to continue processing your loan:\n\n"
            "{{document_list}}\n\n"
            "Upload here: {{portal_link}}\n\n"
            "Thanks,\n{{lo_name}}"
        ),
    },
    "gentle_reminder_sms": {
        "subject": "",
        "body": (
            "Hi {{borrower_name}}, just a reminder - we still need {{document_count}} "
            "document(s) for your loan. Upload anytime at {{portal_link}}"
        ),
    },
    "urgent_reminder": {
        "subject": "URGENT: Documents needed to proceed with your loan",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "We urgently need the following documents to keep your loan on track:\n\n"
            "{{document_list}}\n\n"
            "Without these documents, we may not be able to meet your closing timeline. "
            "Please upload as soon as possible: {{portal_link}}\n\n"
            "If you need help, reply to this email or call us.\n\n"
            "{{lo_name}}"
        ),
    },
    "urgent_reminder_sms": {
        "subject": "",
        "body": (
            "URGENT: {{borrower_name}}, we need {{document_count}} document(s) to proceed "
            "with your loan. Please upload ASAP at {{portal_link}} or call us."
        ),
    },
    "document_rejected": {
        "subject": "Action needed: Document requires re-submission",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "Unfortunately, a document you submitted needs to be re-uploaded:\n\n"
            "{{document_list}}\n\n"
            "{{rejection_details}}\n\n"
            "Please upload a corrected version here: {{portal_link}}\n\n"
            "If you have questions about what's needed, we're happy to help.\n\n"
            "{{lo_name}}"
        ),
    },
    "document_rejected_sms": {
        "subject": "",
        "body": (
            "Hi {{borrower_name}}, a document you submitted needs to be re-uploaded. "
            "Please check your email for details or upload at {{portal_link}}"
        ),
    },
    "document_expired": {
        "subject": "Document update needed",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "A document on file has expired and we need an updated version:\n\n"
            "{{document_list}}\n\n"
            "Please upload the latest version here: {{portal_link}}\n\n"
            "{{lo_name}}"
        ),
    },
    "document_expired_sms": {
        "subject": "",
        "body": (
            "Hi {{borrower_name}}, a document on your loan file has expired. "
            "Please upload an updated version at {{portal_link}}"
        ),
    },
    "appointment_offer": {
        "subject": "Schedule a time to complete your documents",
        "body": (
            "Hi {{borrower_name}},\n\n"
            "We notice you still have outstanding documents for your loan. "
            "Would you like to schedule a quick call or meeting so we can help "
            "you get everything together?\n\n"
            "Outstanding items:\n{{document_list}}\n\n"
            "Reply to this email or call us to set up a time.\n\n"
            "{{lo_name}}"
        ),
    },
    "escalation": {
        "subject": "Escalation: Borrower has not responded to document requests",
        "body": (
            "{{lo_name}},\n\n"
            "The borrower {{borrower_name}} has not responded to {{reminder_count}} "
            "follow-up attempts for the following documents:\n\n"
            "{{document_list}}\n\n"
            "Campaign started: {{campaign_start_date}}\n"
            "Last contact attempt: {{last_contact_date}}\n\n"
            "Please reach out directly to keep this loan on track."
        ),
    },
}


# =============================================================================
# TRIGGER SOURCE MAPPING
# =============================================================================

_CAMPAIGN_TYPE_TO_TRIGGER: Dict[str, CampaignTriggerSource] = {
    "initial_request": CampaignTriggerSource.NEEDS_LIST_GENERATED,
    "gentle_reminder": CampaignTriggerSource.MANUAL,
    "urgent_reminder": CampaignTriggerSource.SLA_BREACH,
    "escalation": CampaignTriggerSource.MANUAL,
    "appointment_offer": CampaignTriggerSource.MANUAL,
    "document_rejected": CampaignTriggerSource.DOCUMENT_REJECTED,
    "document_expired": CampaignTriggerSource.DOCUMENT_EXPIRED,
}


# =============================================================================
# SERVICE
# =============================================================================

class FollowupAutomationService:
    """
    Automated document follow-up management.

    Orchestrates multi-step outreach campaigns for outstanding document
    requests. Each campaign progresses through a configured sequence of
    steps (email, SMS, call, appointment, escalation) with configurable
    delays between steps.
    """

    def __init__(self, db: Session):
        self.db = db
        self._portal_base_url = os.getenv("PORTAL_BASE_URL", "https://app.perenniaai.com/portal")

    # =========================================================================
    # CAMPAIGN LIFECYCLE
    # =========================================================================

    def create_campaign(
        self,
        loan_id: int,
        borrower_id: int,
        organization_id: int,
        campaign_type: str,
        request_ids: List[int],
        created_by_user_id: Optional[int] = None,
    ) -> Dict:
        """Create a new follow-up campaign with step configuration.

        Args:
            loan_id: The loan to follow up on.
            borrower_id: The borrower (lead) ID.
            organization_id: Tenant org ID.
            campaign_type: One of the _DEFAULT_STEP_CONFIGS keys
                (initial_request, gentle_reminder, urgent_reminder, etc.).
            request_ids: List of smart_document_requests.id to follow up on.
            created_by_user_id: User who triggered the campaign (None for system).

        Returns:
            Dict with campaign details.
        """
        step_config = _DEFAULT_STEP_CONFIGS.get(campaign_type)
        if step_config is None:
            logger.warning(
                "Unknown campaign_type %s, falling back to initial_request", campaign_type
            )
            step_config = _DEFAULT_STEP_CONFIGS["initial_request"]

        # Map string campaign_type to CampaignType enum
        campaign_type_enum = self._resolve_campaign_type_enum(campaign_type)
        trigger_source = _CAMPAIGN_TYPE_TO_TRIGGER.get(campaign_type, CampaignTriggerSource.MANUAL)

        now = datetime.now(timezone.utc)

        # Calculate first action time from step 1 delay
        first_delay_hours = step_config[0].get("delay_hours", 0) if step_config else 0
        next_action_at = now + timedelta(hours=first_delay_hours)

        campaign = FollowupCampaign(
            organization_id=organization_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            campaign_type=campaign_type_enum,
            status=CampaignStatus.ACTIVE,
            trigger_source=trigger_source,
            linked_request_ids=request_ids,
            total_steps=len(step_config),
            current_step=0,
            step_config=step_config,
            next_action_at=next_action_at,
            started_at=now,
            max_reminders=len(step_config),
            created_by_user_id=created_by_user_id,
        )
        self.db.add(campaign)
        self.db.flush()

        logger.info(
            "Created %s follow-up campaign %d for loan %d (%d steps, %d requests)",
            campaign_type, campaign.id, loan_id, len(step_config), len(request_ids),
        )

        return {
            "campaign_id": campaign.id,
            "loan_id": loan_id,
            "borrower_id": borrower_id,
            "campaign_type": campaign_type,
            "status": CampaignStatus.ACTIVE.value,
            "total_steps": len(step_config),
            "next_action_at": next_action_at.isoformat(),
            "linked_request_ids": request_ids,
        }

    def pause_campaign(self, campaign_id: int, reason: str) -> Dict:
        """Pause an active campaign.

        Args:
            campaign_id: Campaign to pause.
            reason: Why the campaign is being paused.

        Returns:
            Dict with updated status.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"error": f"Campaign {campaign_id} not found"}

        if campaign.status != CampaignStatus.ACTIVE:
            return {"error": f"Campaign {campaign_id} is not active (status={campaign.status.value})"}

        campaign.status = CampaignStatus.PAUSED
        campaign.cancel_reason = reason
        campaign.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info("Paused campaign %d: %s", campaign_id, reason)
        return {"campaign_id": campaign_id, "status": CampaignStatus.PAUSED.value, "reason": reason}

    def resume_campaign(self, campaign_id: int) -> Dict:
        """Resume a paused campaign. Sets next_action_at to now.

        Args:
            campaign_id: Campaign to resume.

        Returns:
            Dict with updated status.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"error": f"Campaign {campaign_id} not found"}

        if campaign.status != CampaignStatus.PAUSED:
            return {"error": f"Campaign {campaign_id} is not paused (status={campaign.status.value})"}

        now = datetime.now(timezone.utc)
        campaign.status = CampaignStatus.ACTIVE
        campaign.next_action_at = now
        campaign.cancel_reason = None
        campaign.updated_at = now
        self.db.flush()

        logger.info("Resumed campaign %d", campaign_id)
        return {"campaign_id": campaign_id, "status": CampaignStatus.ACTIVE.value, "next_action_at": now.isoformat()}

    def cancel_campaign(self, campaign_id: int, reason: str) -> Dict:
        """Cancel a campaign permanently.

        Args:
            campaign_id: Campaign to cancel.
            reason: Cancellation reason.

        Returns:
            Dict with confirmation.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"error": f"Campaign {campaign_id} not found"}

        if campaign.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
            return {"error": f"Campaign {campaign_id} is already {campaign.status.value}"}

        now = datetime.now(timezone.utc)
        campaign.status = CampaignStatus.CANCELLED
        campaign.cancelled_at = now
        campaign.cancel_reason = reason
        campaign.next_action_at = None
        campaign.updated_at = now
        self.db.flush()

        logger.info("Cancelled campaign %d: %s", campaign_id, reason)
        return {"campaign_id": campaign_id, "status": CampaignStatus.CANCELLED.value, "reason": reason}

    # =========================================================================
    # CRON / STEP PROCESSING
    # =========================================================================

    def process_pending_actions(self) -> Dict:
        """Main cron entry point. Find and execute all due campaign steps.

        Should be called periodically (e.g., every 5-15 minutes).

        Returns:
            Dict with summary of actions taken.
        """
        now = datetime.now(timezone.utc)

        due_campaigns = (
            self.db.query(FollowupCampaign)
            .filter(
                FollowupCampaign.status == CampaignStatus.ACTIVE,
                FollowupCampaign.next_action_at <= now,
            )
            .order_by(FollowupCampaign.next_action_at.asc())
            .limit(100)
            .all()
        )

        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "completed_campaigns": 0,
            "details": [],
        }

        for campaign in due_campaigns:
            try:
                step_result = self.execute_campaign_step(campaign.id)
                results["processed"] += 1

                if step_result.get("error"):
                    results["failed"] += 1
                else:
                    results["succeeded"] += 1

                if step_result.get("campaign_completed"):
                    results["completed_campaigns"] += 1

                results["details"].append(step_result)

            except Exception as e:
                logger.exception("Error processing campaign %d", campaign.id)
                results["processed"] += 1
                results["failed"] += 1
                results["details"].append({
                    "campaign_id": campaign.id,
                    "error": str(e),
                })

        if results["processed"]:
            logger.info(
                "Processed %d follow-up campaigns: %d succeeded, %d failed, %d completed",
                results["processed"], results["succeeded"],
                results["failed"], results["completed_campaigns"],
            )

        return results

    def execute_campaign_step(self, campaign_id: int) -> Dict:
        """Execute the next pending step for a campaign.

        Looks up the current step from step_config, executes the action,
        records a FollowupEvent, then advances to the next step or
        marks the campaign as COMPLETED.

        Args:
            campaign_id: The campaign to advance.

        Returns:
            Dict with step execution result.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"campaign_id": campaign_id, "error": "Campaign not found"}

        if campaign.status != CampaignStatus.ACTIVE:
            return {"campaign_id": campaign_id, "error": f"Campaign is {campaign.status.value}"}

        steps = campaign.step_config or []
        next_step_index = campaign.current_step  # 0-based index into step list

        if next_step_index >= len(steps):
            # All steps exhausted
            self._complete_campaign(campaign)
            return {"campaign_id": campaign_id, "campaign_completed": True}

        step = steps[next_step_index]
        now = datetime.now(timezone.utc)

        # Gather context
        borrower_info = self._get_borrower_info(campaign.loan_id, campaign.borrower_id)
        outstanding_docs = self._get_outstanding_documents(campaign.linked_request_ids or [])

        # Execute the step action
        action = step.get("action", step.get("channel", "send_email"))
        template_slug = step.get("template", "gentle_reminder")
        step_number = step.get("step", next_step_index + 1)

        result: Dict[str, Any] = {}
        event_type = FollowupEventType.EMAIL_SENT
        delivery_status = DeliveryStatus.QUEUED

        try:
            if action == "send_email":
                event_type = FollowupEventType.EMAIL_SENT
                result = self._send_email_reminder(
                    campaign_id=campaign_id,
                    template_slug=template_slug,
                    borrower_email=borrower_info.get("borrower_email", ""),
                    borrower_name=borrower_info.get("borrower_name", "Borrower"),
                    documents=outstanding_docs,
                    lo_name=borrower_info.get("lo_name", "Your Loan Officer"),
                    portal_link=self._build_portal_link(campaign.loan_id),
                )

            elif action == "send_sms":
                event_type = FollowupEventType.SMS_SENT
                result = self._send_sms_reminder(
                    campaign_id=campaign_id,
                    template_slug=template_slug,
                    borrower_phone=borrower_info.get("borrower_phone", ""),
                    borrower_name=borrower_info.get("borrower_name", "Borrower"),
                    document_count=len(outstanding_docs),
                )

            elif action == "schedule_call":
                event_type = FollowupEventType.CALL_SCHEDULED
                result = self._schedule_call(
                    campaign_id=campaign_id,
                    loan_id=campaign.loan_id,
                    borrower_phone=borrower_info.get("borrower_phone", ""),
                    lo_user_id=borrower_info.get("lo_user_id"),
                )

            elif action == "offer_appointment":
                event_type = FollowupEventType.APPOINTMENT_BOOKED
                result = self._offer_appointment(
                    campaign_id=campaign_id,
                    loan_id=campaign.loan_id,
                    borrower_id=campaign.borrower_id or 0,
                    organization_id=campaign.organization_id or 0,
                )

            elif action == "escalate_to_lo":
                event_type = FollowupEventType.ESCALATED_TO_LO
                result = self._escalate_to_lo(
                    campaign_id=campaign_id,
                    loan_id=campaign.loan_id,
                )

            else:
                logger.warning("Unknown action '%s' for campaign %d step %d", action, campaign_id, step_number)
                result = {"status": "skipped", "reason": f"Unknown action: {action}"}

            delivery_status = DeliveryStatus.SENT if result.get("status") != "failed" else DeliveryStatus.FAILED

        except Exception as e:
            logger.exception("Failed to execute step %d of campaign %d", step_number, campaign_id)
            result = {"status": "failed", "error": str(e)}
            delivery_status = DeliveryStatus.FAILED

        # Record the event
        event = FollowupEvent(
            campaign_id=campaign_id,
            event_type=event_type,
            step_number=step_number,
            channel=step.get("channel", "email"),
            template_used=template_slug,
            recipient_email=borrower_info.get("borrower_email"),
            recipient_phone=borrower_info.get("borrower_phone"),
            message_subject=result.get("subject"),
            message_preview=(result.get("body", "") or "")[:500],
            delivery_status=delivery_status,
            delivery_error=result.get("error"),
            metadata={"step_config": step, "result_summary": result.get("status")},
        )
        self.db.add(event)

        # Advance campaign
        campaign.current_step = next_step_index + 1
        campaign.reminders_sent = (campaign.reminders_sent or 0) + 1
        campaign.updated_at = now

        # Set next action time or complete
        if campaign.current_step >= len(steps):
            self._complete_campaign(campaign)
            campaign_completed = True
        else:
            next_step = steps[campaign.current_step]
            delay_hours = next_step.get("delay_hours", 24)
            campaign.next_action_at = now + timedelta(hours=delay_hours)
            campaign_completed = False

        self.db.flush()

        return {
            "campaign_id": campaign_id,
            "step_number": step_number,
            "action": action,
            "channel": step.get("channel"),
            "delivery_status": delivery_status.value,
            "campaign_completed": campaign_completed,
            "next_action_at": campaign.next_action_at.isoformat() if campaign.next_action_at else None,
            "result": result,
        }

    # =========================================================================
    # BORROWER RESPONSE HANDLING
    # =========================================================================

    def handle_borrower_response(self, campaign_id: int, response_type: str) -> Dict:
        """Handle a borrower response to a follow-up campaign.

        Args:
            campaign_id: The campaign the borrower responded to.
            response_type: One of 'document_uploaded', 'appointment_booked',
                'replied', 'called_back'.

        Returns:
            Dict with updated campaign info.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"error": f"Campaign {campaign_id} not found"}

        now = datetime.now(timezone.utc)
        campaign.borrower_responded = True
        campaign.response_date = now
        campaign.updated_at = now

        # Record the response event
        event = FollowupEvent(
            campaign_id=campaign_id,
            event_type=FollowupEventType.BORROWER_RESPONDED,
            channel="borrower_action",
            metadata={"response_type": response_type},
        )
        self.db.add(event)

        if response_type == "document_uploaded":
            # Check if all linked requests are now fulfilled
            outstanding = self._get_outstanding_documents(campaign.linked_request_ids or [])
            if not outstanding:
                self._complete_campaign(campaign)
                self.db.flush()
                return {
                    "campaign_id": campaign_id,
                    "status": "completed",
                    "message": "All documents received, campaign completed",
                }
            else:
                # Some docs still outstanding, keep campaign going
                self.db.flush()
                return {
                    "campaign_id": campaign_id,
                    "status": "active",
                    "message": f"{len(outstanding)} document(s) still outstanding",
                    "remaining_documents": [d.get("title", "") for d in outstanding],
                }

        elif response_type == "appointment_booked":
            # Pause campaign until appointment is completed
            campaign.status = CampaignStatus.PAUSED
            campaign.cancel_reason = "Appointment booked by borrower"
            campaign.next_action_at = None
            self.db.flush()
            return {
                "campaign_id": campaign_id,
                "status": "paused",
                "message": "Campaign paused pending appointment completion",
            }

        else:
            # Generic response (replied, called_back) -- keep campaign active
            # but note the response
            self.db.flush()
            return {
                "campaign_id": campaign_id,
                "status": campaign.status.value,
                "message": f"Borrower response recorded: {response_type}",
            }

    def handle_document_uploaded(self, loan_id: int, request_id: int) -> None:
        """Handle a document upload event. Checks active campaigns and
        completes them if all requested documents are now received.

        Args:
            loan_id: The loan the document was uploaded for.
            request_id: The document request that was fulfilled.
        """
        # Find active campaigns that reference this request
        campaigns = (
            self.db.query(FollowupCampaign)
            .filter(
                FollowupCampaign.loan_id == loan_id,
                FollowupCampaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
            )
            .all()
        )

        now = datetime.now(timezone.utc)

        for campaign in campaigns:
            linked_ids = campaign.linked_request_ids or []
            if request_id not in linked_ids:
                continue

            # Record the upload event
            event = FollowupEvent(
                campaign_id=campaign.id,
                event_type=FollowupEventType.DOCUMENT_UPLOADED,
                channel="borrower_action",
                metadata={"request_id": request_id, "loan_id": loan_id},
            )
            self.db.add(event)

            # Check if all linked requests are now fulfilled
            outstanding = self._get_outstanding_documents(linked_ids)
            if not outstanding:
                self._complete_campaign(campaign)
                logger.info(
                    "All documents received for campaign %d (loan %d), completing",
                    campaign.id, loan_id,
                )
            else:
                campaign.updated_at = now
                logger.info(
                    "Document %d uploaded for campaign %d, %d still outstanding",
                    request_id, campaign.id, len(outstanding),
                )

        self.db.flush()

    # =========================================================================
    # APPOINTMENTS
    # =========================================================================

    def create_appointment(
        self,
        loan_id: int,
        borrower_id: int,
        organization_id: int,
        appointment_type: str,
        title: str,
        scheduled_time: datetime,
        duration_minutes: int = 30,
        assigned_to_user_id: Optional[int] = None,
        documents_to_discuss: Optional[List[int]] = None,
    ) -> Dict:
        """Create a document-related appointment.

        Args:
            loan_id: Loan this appointment relates to.
            borrower_id: Borrower (lead) ID.
            organization_id: Tenant org ID.
            appointment_type: One of AppointmentType values.
            title: Appointment title.
            scheduled_time: When the appointment is scheduled.
            duration_minutes: Duration in minutes (default 30).
            assigned_to_user_id: LO or processor user ID.
            documents_to_discuss: List of document request IDs.

        Returns:
            Dict with appointment details.
        """
        try:
            appt_type_enum = AppointmentType(appointment_type)
        except ValueError:
            appt_type_enum = AppointmentType.GENERAL_CONSULTATION

        end_time = scheduled_time + timedelta(minutes=duration_minutes)
        borrower_info = self._get_borrower_info(loan_id, borrower_id)

        appointment = DocumentAppointment(
            organization_id=organization_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            appointment_type=appt_type_enum,
            title=title,
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=scheduled_time.date(),
            scheduled_time_start=scheduled_time,
            scheduled_time_end=end_time,
            duration_minutes=duration_minutes,
            location_type=LocationType.PHONE_CALL,
            assigned_to_user_id=assigned_to_user_id or borrower_info.get("lo_user_id"),
            attendee_name=borrower_info.get("borrower_name"),
            attendee_email=borrower_info.get("borrower_email"),
            attendee_phone=borrower_info.get("borrower_phone"),
            documents_to_discuss=documents_to_discuss,
        )
        self.db.add(appointment)
        self.db.flush()

        # Send confirmation email to borrower
        self._send_appointment_confirmation(appointment, borrower_info)

        logger.info(
            "Created document appointment %d for loan %d at %s",
            appointment.id, loan_id, scheduled_time.isoformat(),
        )

        return {
            "appointment_id": appointment.id,
            "loan_id": loan_id,
            "type": appt_type_enum.value,
            "title": title,
            "scheduled_time": scheduled_time.isoformat(),
            "duration_minutes": duration_minutes,
            "status": AppointmentStatus.SCHEDULED.value,
            "assigned_to_user_id": appointment.assigned_to_user_id,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
        }

    # =========================================================================
    # QUERIES
    # =========================================================================

    def get_active_campaigns(
        self,
        organization_id: int,
        loan_id: Optional[int] = None,
    ) -> List[Dict]:
        """Get active follow-up campaigns.

        Args:
            organization_id: Filter by organization.
            loan_id: Optionally filter by specific loan.

        Returns:
            List of campaign summary dicts.
        """
        query = self.db.query(FollowupCampaign).filter(
            FollowupCampaign.organization_id == organization_id,
            FollowupCampaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
        )

        if loan_id is not None:
            query = query.filter(FollowupCampaign.loan_id == loan_id)

        campaigns = query.order_by(FollowupCampaign.next_action_at.asc().nullslast()).all()

        return [
            {
                "campaign_id": c.id,
                "loan_id": c.loan_id,
                "borrower_id": c.borrower_id,
                "campaign_type": c.campaign_type.value if c.campaign_type else None,
                "status": c.status.value,
                "current_step": c.current_step,
                "total_steps": c.total_steps,
                "reminders_sent": c.reminders_sent,
                "borrower_responded": c.borrower_responded,
                "next_action_at": c.next_action_at.isoformat() if c.next_action_at else None,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "linked_request_ids": c.linked_request_ids,
            }
            for c in campaigns
        ]

    def get_campaign_timeline(self, campaign_id: int) -> List[Dict]:
        """Get the full event timeline for a campaign.

        Args:
            campaign_id: The campaign to get timeline for.

        Returns:
            Chronologically ordered list of events.
        """
        events = (
            self.db.query(FollowupEvent)
            .filter(FollowupEvent.campaign_id == campaign_id)
            .order_by(FollowupEvent.created_at.asc())
            .all()
        )

        return [
            {
                "event_id": e.id,
                "event_type": e.event_type.value if e.event_type else None,
                "step_number": e.step_number,
                "channel": e.channel,
                "template_used": e.template_used,
                "delivery_status": e.delivery_status.value if e.delivery_status else None,
                "delivery_error": e.delivery_error,
                "recipient_email": e.recipient_email,
                "recipient_phone": e.recipient_phone,
                "message_subject": e.message_subject,
                "message_preview": e.message_preview,
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "metadata": e.metadata,
            }
            for e in events
        ]

    def get_followup_stats(self, organization_id: int, days: int = 30) -> Dict:
        """Get follow-up campaign statistics for an organization.

        Args:
            organization_id: The organization to get stats for.
            days: Lookback window in days (default 30).

        Returns:
            Dict with campaign stats, response rates, channel effectiveness.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Campaign counts
        campaigns = (
            self.db.query(FollowupCampaign)
            .filter(
                FollowupCampaign.organization_id == organization_id,
                FollowupCampaign.created_at >= cutoff,
            )
            .all()
        )

        total = len(campaigns)
        completed = sum(1 for c in campaigns if c.status == CampaignStatus.COMPLETED)
        active = sum(1 for c in campaigns if c.status == CampaignStatus.ACTIVE)
        cancelled = sum(1 for c in campaigns if c.status == CampaignStatus.CANCELLED)
        responded = sum(1 for c in campaigns if c.borrower_responded)

        # Average response time (for campaigns that got a response)
        response_times = []
        for c in campaigns:
            if c.borrower_responded and c.response_date and c.started_at:
                delta = (c.response_date - c.started_at).total_seconds() / 3600.0
                response_times.append(delta)
        avg_response_hours = (
            round(sum(response_times) / len(response_times), 1)
            if response_times
            else None
        )

        # Channel effectiveness from events
        campaign_ids = [c.id for c in campaigns]
        channel_stats: Dict[str, Dict[str, int]] = {}

        if campaign_ids:
            events = (
                self.db.query(FollowupEvent)
                .filter(FollowupEvent.campaign_id.in_(campaign_ids))
                .all()
            )

            for ev in events:
                ch = ev.channel or "unknown"
                if ch not in channel_stats:
                    channel_stats[ch] = {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "failed": 0}

                channel_stats[ch]["sent"] += 1
                if ev.delivery_status == DeliveryStatus.DELIVERED:
                    channel_stats[ch]["delivered"] += 1
                elif ev.delivery_status == DeliveryStatus.OPENED:
                    channel_stats[ch]["opened"] += 1
                elif ev.delivery_status == DeliveryStatus.CLICKED:
                    channel_stats[ch]["clicked"] += 1
                elif ev.delivery_status == DeliveryStatus.FAILED:
                    channel_stats[ch]["failed"] += 1

        # Most effective channel (highest open/click rate)
        most_effective_channel = None
        best_engagement = 0
        for ch, stats in channel_stats.items():
            engagement = stats.get("opened", 0) + stats.get("clicked", 0)
            if engagement > best_engagement:
                best_engagement = engagement
                most_effective_channel = ch

        # Document collection rate (completed campaigns / total)
        collection_rate = round((completed / total) * 100, 1) if total > 0 else 0

        return {
            "period_days": days,
            "total_campaigns": total,
            "active_campaigns": active,
            "completed_campaigns": completed,
            "cancelled_campaigns": cancelled,
            "response_count": responded,
            "response_rate": round((responded / total) * 100, 1) if total > 0 else 0,
            "avg_response_time_hours": avg_response_hours,
            "collection_rate": collection_rate,
            "most_effective_channel": most_effective_channel,
            "channel_stats": channel_stats,
        }

    # =========================================================================
    # STEP ACTION IMPLEMENTATIONS
    # =========================================================================

    def _send_email_reminder(
        self,
        campaign_id: int,
        template_slug: str,
        borrower_email: str,
        borrower_name: str,
        documents: List[Dict],
        lo_name: str,
        portal_link: str,
    ) -> Dict:
        """Compose and send an email reminder.

        Args:
            campaign_id: The campaign this email belongs to.
            template_slug: Template identifier for subject/body.
            borrower_email: Recipient email.
            borrower_name: Recipient name.
            documents: List of outstanding document dicts.
            lo_name: Loan officer name for sign-off.
            portal_link: URL to the borrower portal.

        Returns:
            Dict with delivery status and rendered content.
        """
        if not borrower_email:
            return {"status": "failed", "error": "No borrower email address"}

        # Build template variables
        doc_list_text = "\n".join(
            f"  - {d.get('title', 'Document')}" for d in documents
        ) if documents else "  (no outstanding documents)"

        variables = {
            "borrower_name": borrower_name,
            "document_list": doc_list_text,
            "document_count": str(len(documents)),
            "portal_link": portal_link,
            "lo_name": lo_name,
            "reminder_count": "",
            "campaign_start_date": "",
            "last_contact_date": "",
            "rejection_details": "",
        }

        # Enrich with campaign metadata
        campaign = self._get_campaign(campaign_id)
        if campaign:
            variables["reminder_count"] = str(campaign.reminders_sent or 0)
            variables["campaign_start_date"] = (
                campaign.started_at.strftime("%m/%d/%Y") if campaign.started_at else ""
            )

        rendered = self._render_template(template_slug, variables)

        # Send via EmailService
        try:
            from email_service import EmailService
            email_svc = EmailService()
            success = email_svc.send_html_email(
                to_email=borrower_email,
                subject=rendered["subject"],
                html_body=rendered["body"],
                plain_text_body=rendered["body"],
            )
            status = "sent" if success else "failed"
        except Exception as e:
            logger.exception("Email send failed for campaign %d", campaign_id)
            return {"status": "failed", "error": str(e), "subject": rendered["subject"]}

        return {
            "status": status,
            "channel": "email",
            "recipient": borrower_email,
            "subject": rendered["subject"],
            "body": rendered["body"],
        }

    def _send_sms_reminder(
        self,
        campaign_id: int,
        template_slug: str,
        borrower_phone: str,
        borrower_name: str,
        document_count: int,
    ) -> Dict:
        """Compose and send an SMS reminder.

        Args:
            campaign_id: The campaign this SMS belongs to.
            template_slug: Template identifier.
            borrower_phone: Recipient phone number.
            borrower_name: Recipient name.
            document_count: Number of outstanding documents.

        Returns:
            Dict with delivery status.
        """
        if not borrower_phone:
            return {"status": "failed", "error": "No borrower phone number"}

        campaign = self._get_campaign(campaign_id)
        portal_link = self._build_portal_link(campaign.loan_id if campaign else 0)

        variables = {
            "borrower_name": borrower_name,
            "document_count": str(document_count),
            "portal_link": portal_link,
        }

        rendered = self._render_template(template_slug, variables)
        message_body = rendered["body"]

        # Send via Telnyx
        try:
            import telnyx
            telnyx_api_key = os.getenv("TELNYX_API_KEY", "")
            telnyx_from = os.getenv("TELNYX_FROM_NUMBER", "")
            messaging_profile = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

            if not telnyx_api_key or not telnyx_from:
                logger.warning("Telnyx not configured, SMS not sent for campaign %d", campaign_id)
                return {"status": "failed", "error": "SMS service not configured"}

            telnyx.api_key = telnyx_api_key
            telnyx.Message.create(
                from_=telnyx_from,
                to=borrower_phone,
                text=message_body,
                messaging_profile_id=messaging_profile,
            )
            status = "sent"
        except Exception as e:
            logger.exception("SMS send failed for campaign %d", campaign_id)
            return {"status": "failed", "error": str(e), "body": message_body}

        return {
            "status": status,
            "channel": "sms",
            "recipient": borrower_phone,
            "body": message_body,
        }

    def _schedule_call(
        self,
        campaign_id: int,
        loan_id: int,
        borrower_phone: str,
        lo_user_id: Optional[int],
    ) -> Dict:
        """Create a call task for the loan officer.

        Args:
            campaign_id: The campaign requesting the call.
            loan_id: The loan this relates to.
            borrower_phone: Borrower phone to call.
            lo_user_id: Loan officer user ID.

        Returns:
            Dict with task details.
        """
        if not lo_user_id:
            return {"status": "failed", "error": "No loan officer assigned"}

        # Create a task for the LO to call the borrower
        try:
            result = self.db.execute(
                text("""
                    INSERT INTO tasks (
                        title, description, task_type, priority, status,
                        assigned_to_id, loan_id, due_date, created_at
                    ) VALUES (
                        :title, :description, 'call', 'high', 'pending',
                        :assigned_to, :loan_id, :due_date, :created_at
                    ) RETURNING id
                """),
                {
                    "title": f"Call borrower about outstanding documents (Loan #{loan_id})",
                    "description": (
                        f"Follow-up campaign #{campaign_id} has scheduled a call. "
                        f"Please call the borrower at {borrower_phone} to discuss "
                        f"outstanding documents."
                    ),
                    "assigned_to": lo_user_id,
                    "loan_id": loan_id,
                    "due_date": datetime.now(timezone.utc) + timedelta(hours=4),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            task_row = result.fetchone()
            task_id = task_row[0] if task_row else None
        except Exception as e:
            logger.exception("Failed to create call task for campaign %d", campaign_id)
            return {"status": "failed", "error": str(e)}

        return {
            "status": "sent",
            "channel": "call",
            "task_id": task_id,
            "assigned_to_user_id": lo_user_id,
            "borrower_phone": borrower_phone,
        }

    def _offer_appointment(
        self,
        campaign_id: int,
        loan_id: int,
        borrower_id: int,
        organization_id: int,
    ) -> Dict:
        """Create appointment slots and notify the borrower.

        Args:
            campaign_id: The campaign offering the appointment.
            loan_id: The loan this relates to.
            borrower_id: The borrower (lead) ID.
            organization_id: Tenant org ID.

        Returns:
            Dict with appointment offer details.
        """
        borrower_info = self._get_borrower_info(loan_id, borrower_id)
        outstanding_docs = self._get_outstanding_documents(
            self._get_campaign(campaign_id).linked_request_ids or [] if self._get_campaign(campaign_id) else []
        )

        # Create an appointment slot for the next business day at 10am
        now = datetime.now(timezone.utc)
        next_slot = self._next_business_day(now).replace(hour=15, minute=0, second=0, microsecond=0)
        # 15:00 UTC ~ 10:00 AM ET

        appointment = DocumentAppointment(
            organization_id=organization_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            campaign_id=campaign_id,
            appointment_type=AppointmentType.DOCUMENT_COLLECTION,
            title="Document Collection Assistance",
            description=(
                f"Help borrower complete {len(outstanding_docs)} outstanding "
                f"document(s) for their loan application."
            ),
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=next_slot.date(),
            scheduled_time_start=next_slot,
            scheduled_time_end=next_slot + timedelta(minutes=30),
            duration_minutes=30,
            location_type=LocationType.PHONE_CALL,
            assigned_to_user_id=borrower_info.get("lo_user_id"),
            attendee_name=borrower_info.get("borrower_name"),
            attendee_email=borrower_info.get("borrower_email"),
            attendee_phone=borrower_info.get("borrower_phone"),
            documents_to_discuss=[d.get("request_id") for d in outstanding_docs if d.get("request_id")],
        )
        self.db.add(appointment)
        self.db.flush()

        # Send appointment offer email
        portal_link = self._build_portal_link(loan_id)
        variables = {
            "borrower_name": borrower_info.get("borrower_name", "Borrower"),
            "document_list": "\n".join(f"  - {d.get('title', '')}" for d in outstanding_docs),
            "document_count": str(len(outstanding_docs)),
            "portal_link": portal_link,
            "lo_name": borrower_info.get("lo_name", "Your Loan Officer"),
        }
        rendered = self._render_template("appointment_offer", variables)

        borrower_email = borrower_info.get("borrower_email")
        if borrower_email:
            try:
                from email_service import EmailService
                email_svc = EmailService()
                email_svc.send_html_email(
                    to_email=borrower_email,
                    subject=rendered["subject"],
                    html_body=rendered["body"],
                    plain_text_body=rendered["body"],
                )
            except Exception as e:
                logger.exception("Failed to send appointment offer email for campaign %d", campaign_id)

        return {
            "status": "sent",
            "channel": "appointment",
            "appointment_id": appointment.id,
            "scheduled_time": next_slot.isoformat(),
            "subject": rendered["subject"],
        }

    def _escalate_to_lo(self, campaign_id: int, loan_id: int) -> Dict:
        """Escalate unresponsive borrower to their loan officer.

        Creates a high-priority task for the LO with a summary of all
        follow-up attempts made during this campaign.

        Args:
            campaign_id: The campaign to escalate.
            loan_id: The loan this relates to.

        Returns:
            Dict with escalation details.
        """
        campaign = self._get_campaign(campaign_id)
        if campaign is None:
            return {"status": "failed", "error": "Campaign not found"}

        borrower_info = self._get_borrower_info(loan_id, campaign.borrower_id)
        lo_user_id = borrower_info.get("lo_user_id")
        lo_email = borrower_info.get("lo_email")

        # Build escalation summary from events
        events = (
            self.db.query(FollowupEvent)
            .filter(FollowupEvent.campaign_id == campaign_id)
            .order_by(FollowupEvent.created_at.asc())
            .all()
        )
        attempt_summary = "\n".join(
            f"  - {e.created_at.strftime('%m/%d %H:%M') if e.created_at else '??'}: "
            f"{e.event_type.value if e.event_type else 'unknown'} via {e.channel or '?'} "
            f"({e.delivery_status.value if e.delivery_status else '?'})"
            for e in events
        )

        outstanding_docs = self._get_outstanding_documents(campaign.linked_request_ids or [])
        doc_list = "\n".join(f"  - {d.get('title', '')}" for d in outstanding_docs)

        description = (
            f"Borrower {borrower_info.get('borrower_name', 'Unknown')} has not responded "
            f"to {campaign.reminders_sent or 0} follow-up attempts.\n\n"
            f"Outstanding documents:\n{doc_list}\n\n"
            f"Follow-up history:\n{attempt_summary}\n\n"
            f"Borrower contact: {borrower_info.get('borrower_email', '')} / "
            f"{borrower_info.get('borrower_phone', '')}"
        )

        # Create high-priority task
        task_id = None
        if lo_user_id:
            try:
                result = self.db.execute(
                    text("""
                        INSERT INTO tasks (
                            title, description, task_type, priority, status,
                            assigned_to_id, loan_id, due_date, created_at
                        ) VALUES (
                            :title, :description, 'escalation', 'urgent', 'pending',
                            :assigned_to, :loan_id, :due_date, :created_at
                        ) RETURNING id
                    """),
                    {
                        "title": f"ESCALATION: Borrower unresponsive - documents needed (Loan #{loan_id})",
                        "description": description,
                        "assigned_to": lo_user_id,
                        "loan_id": loan_id,
                        "due_date": datetime.now(timezone.utc) + timedelta(hours=8),
                        "created_at": datetime.now(timezone.utc),
                    },
                )
                task_row = result.fetchone()
                task_id = task_row[0] if task_row else None
            except Exception as e:
                logger.exception("Failed to create escalation task for campaign %d", campaign_id)

        # Also email the LO
        if lo_email:
            variables = {
                "borrower_name": borrower_info.get("borrower_name", "Unknown"),
                "lo_name": borrower_info.get("lo_name", ""),
                "document_list": doc_list,
                "reminder_count": str(campaign.reminders_sent or 0),
                "campaign_start_date": (
                    campaign.started_at.strftime("%m/%d/%Y") if campaign.started_at else ""
                ),
                "last_contact_date": datetime.now(timezone.utc).strftime("%m/%d/%Y"),
                "portal_link": self._build_portal_link(loan_id),
                "document_count": str(len(outstanding_docs)),
            }
            rendered = self._render_template("escalation", variables)
            try:
                from email_service import EmailService
                email_svc = EmailService()
                email_svc.send_html_email(
                    to_email=lo_email,
                    subject=rendered["subject"],
                    html_body=rendered["body"],
                    plain_text_body=rendered["body"],
                )
            except Exception as e:
                logger.exception("Failed to send escalation email to LO for campaign %d", campaign_id)

        logger.info(
            "Escalated campaign %d to LO (user_id=%s, task_id=%s)",
            campaign_id, lo_user_id, task_id,
        )

        return {
            "status": "sent",
            "channel": "escalation",
            "task_id": task_id,
            "lo_user_id": lo_user_id,
            "lo_email": lo_email,
            "outstanding_document_count": len(outstanding_docs),
        }

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _get_campaign(self, campaign_id: int) -> Optional[FollowupCampaign]:
        """Fetch a campaign by ID."""
        return (
            self.db.query(FollowupCampaign)
            .filter(FollowupCampaign.id == campaign_id)
            .first()
        )

    def _complete_campaign(self, campaign: FollowupCampaign) -> None:
        """Mark a campaign as completed."""
        now = datetime.now(timezone.utc)
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = now
        campaign.next_action_at = None
        campaign.updated_at = now

    def _get_borrower_info(self, loan_id: int, borrower_id: Optional[int]) -> Dict:
        """Get borrower and LO contact info from leads and loans tables.

        Args:
            loan_id: The loan to look up.
            borrower_id: The borrower (lead) ID.

        Returns:
            Dict with borrower_name, borrower_email, borrower_phone,
            lo_name, lo_email, lo_user_id.
        """
        info: Dict[str, Any] = {
            "borrower_name": "Borrower",
            "borrower_email": None,
            "borrower_phone": None,
            "lo_name": "Your Loan Officer",
            "lo_email": None,
            "lo_user_id": None,
        }

        # Get borrower info from leads table
        if borrower_id:
            try:
                borrower_row = self.db.execute(
                    text("""
                        SELECT first_name, last_name, email, phone
                        FROM leads
                        WHERE id = :lead_id
                        LIMIT 1
                    """),
                    {"lead_id": borrower_id},
                ).fetchone()

                if borrower_row:
                    first = borrower_row[0] or ""
                    last = borrower_row[1] or ""
                    info["borrower_name"] = f"{first} {last}".strip() or "Borrower"
                    info["borrower_email"] = borrower_row[2]
                    info["borrower_phone"] = borrower_row[3]
            except Exception as e:
                logger.warning("Failed to fetch borrower info for lead %d: %s", borrower_id, e)

        # Get LO info from loans + users tables
        try:
            lo_row = self.db.execute(
                text("""
                    SELECT
                        u.id as lo_user_id,
                        u.first_name, u.last_name, u.email
                    FROM loans l
                    JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id
                    LIMIT 1
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if lo_row:
                info["lo_user_id"] = lo_row[0]
                lo_first = lo_row[1] or ""
                lo_last = lo_row[2] or ""
                info["lo_name"] = f"{lo_first} {lo_last}".strip() or "Your Loan Officer"
                info["lo_email"] = lo_row[3]
        except Exception as e:
            logger.warning("Failed to fetch LO info for loan %d: %s", loan_id, e)

        # Fallback: try borrower info from loans table if leads lookup failed
        if not info["borrower_email"]:
            try:
                loan_row = self.db.execute(
                    text("""
                        SELECT borrower_name, borrower_email, borrower_phone
                        FROM loans
                        WHERE id = :loan_id
                        LIMIT 1
                    """),
                    {"loan_id": loan_id},
                ).fetchone()

                if loan_row:
                    if not info["borrower_name"] or info["borrower_name"] == "Borrower":
                        info["borrower_name"] = loan_row[0] or "Borrower"
                    info["borrower_email"] = info["borrower_email"] or loan_row[1]
                    info["borrower_phone"] = info["borrower_phone"] or loan_row[2]
            except Exception as e:
                logger.warning("Failed to fetch borrower info from loan %d: %s", loan_id, e)

        return info

    def _get_outstanding_documents(self, request_ids: List[int]) -> List[Dict]:
        """Get document request details for outstanding (unfulfilled) requests.

        Args:
            request_ids: List of smart_document_requests.id values.

        Returns:
            List of dicts with request_id, title, doc_type, due_date for
            requests that are still OPEN or PENDING_REVIEW.
        """
        if not request_ids:
            return []

        try:
            requests = (
                self.db.query(DocumentRequest)
                .filter(
                    DocumentRequest.id.in_(request_ids),
                    DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]),
                    DocumentRequest.is_active == True,
                )
                .all()
            )

            return [
                {
                    "request_id": r.id,
                    "title": r.title,
                    "doc_type": r.doc_type.value if r.doc_type else None,
                    "priority": r.priority.value if r.priority else None,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "sla_due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
                }
                for r in requests
            ]
        except Exception as e:
            logger.warning("Failed to fetch outstanding documents for request_ids %s: %s", request_ids, e)
            return []

    def _render_template(self, template_slug: str, variables: Dict) -> Dict:
        """Render a follow-up template with variable substitution.

        Looks for a matching FollowupTemplate in the database first,
        then falls back to hardcoded defaults.

        Args:
            template_slug: The template slug to look up.
            variables: Dict of {{variable}} -> value replacements.

        Returns:
            Dict with 'subject' and 'body' keys.
        """
        subject = ""
        body = ""

        # Try database template first
        try:
            db_template = (
                self.db.query(FollowupTemplate)
                .filter(
                    FollowupTemplate.slug == template_slug,
                    FollowupTemplate.is_active == True,
                )
                .order_by(
                    # Prefer org-specific over default
                    FollowupTemplate.organization_id.desc().nullslast()
                )
                .first()
            )
            if db_template:
                subject = db_template.subject_template or ""
                body = db_template.body_template or ""
                # Increment usage count
                db_template.usage_count = (db_template.usage_count or 0) + 1
        except Exception as e:
            logger.warning("Failed to load template '%s' from DB: %s", template_slug, e)

        # Fall back to hardcoded defaults
        if not body:
            default = _DEFAULT_TEMPLATES.get(template_slug)
            if default:
                subject = default.get("subject", "")
                body = default.get("body", "")
            else:
                # Ultimate fallback
                subject = "Document follow-up"
                body = (
                    "Hi {{borrower_name}}, we still need documents for your loan. "
                    "Please upload at {{portal_link}}"
                )

        # Substitute variables
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))

        return {"subject": subject, "body": body}

    def _build_portal_link(self, loan_id: int) -> str:
        """Build the borrower portal upload link for a loan."""
        return f"{self._portal_base_url}/documents/{loan_id}"

    def _send_appointment_confirmation(
        self,
        appointment: DocumentAppointment,
        borrower_info: Dict,
    ) -> None:
        """Send an appointment confirmation email to the borrower."""
        if not borrower_info.get("borrower_email"):
            return

        scheduled_str = (
            appointment.scheduled_time_start.strftime("%B %d, %Y at %I:%M %p")
            if appointment.scheduled_time_start
            else "TBD"
        )

        subject = f"Appointment Confirmed: {appointment.title}"
        body = (
            f"Hi {borrower_info.get('borrower_name', 'there')},\n\n"
            f"Your appointment has been scheduled:\n\n"
            f"  Date/Time: {scheduled_str}\n"
            f"  Duration: {appointment.duration_minutes} minutes\n"
            f"  Type: {appointment.location_type.value if appointment.location_type else 'Phone call'}\n\n"
            f"We'll be reviewing your outstanding documents. Please have them "
            f"ready or upload ahead of time.\n\n"
            f"Best regards,\n{borrower_info.get('lo_name', 'Your Loan Team')}"
        )

        try:
            from email_service import EmailService
            email_svc = EmailService()
            email_svc.send_html_email(
                to_email=borrower_info["borrower_email"],
                subject=subject,
                html_body=body,
                plain_text_body=body,
            )
        except Exception as e:
            logger.exception(
                "Failed to send appointment confirmation for appointment %d",
                appointment.id,
            )

    @staticmethod
    def _resolve_campaign_type_enum(campaign_type: str) -> CampaignType:
        """Map a string campaign_type to the CampaignType enum.

        The CampaignType enum has fewer values than our step config keys,
        so we map the extras to the closest match.
        """
        mapping = {
            "initial_request": CampaignType.INITIAL_REQUEST,
            "gentle_reminder": CampaignType.GENTLE_REMINDER,
            "urgent_reminder": CampaignType.URGENT_REMINDER,
            "escalation": CampaignType.ESCALATION,
            "appointment_offer": CampaignType.APPOINTMENT_OFFER,
            "document_rejected": CampaignType.GENTLE_REMINDER,
            "document_expired": CampaignType.GENTLE_REMINDER,
        }
        return mapping.get(campaign_type, CampaignType.INITIAL_REQUEST)

    @staticmethod
    def _next_business_day(dt: datetime) -> datetime:
        """Return the next business day (Mon-Fri) after the given datetime."""
        next_day = dt + timedelta(days=1)
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day += timedelta(days=1)
        return next_day


# =============================================================================
# SINGLETON FACTORY
# =============================================================================

def get_followup_automation_service(db: Session) -> FollowupAutomationService:
    """Get a FollowupAutomationService instance for the given DB session.

    This is the recommended way to obtain the service in route handlers:

        service = get_followup_automation_service(db)
        result = service.create_campaign(...)
    """
    return FollowupAutomationService(db)
