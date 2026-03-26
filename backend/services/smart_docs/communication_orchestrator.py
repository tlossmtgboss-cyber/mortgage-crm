"""
Communication + Calendar Orchestrator for the Application Completion Orchestrator (ACO)

Handles all borrower-facing communication during the application completion
process and coordinates PA call scheduling with the existing calendar system.

Responsibilities:
  - Introductory SMS sequence (introduction, contact card delivery, confirmation)
  - Question-by-question SMS workflow for missing item resolution
  - Document request notifications (SMS + email)
  - Borrower availability collection for PA calls
  - PA calendar slot lookup, booking, and confirmation
  - Pre-call brief generation for production assistants
  - Follow-up reminders (missing docs, upcoming appointments, stalled responses)
  - VCard (contact card) generation for loan officer teams
  - Comprehensive communication logging to BorrowerCommunicationLog

Integrations:
  - Telnyx for outbound SMS / MMS
  - Existing notification_service for email delivery
  - Scheduler Appointment model for calendar bookings

Usage:
    from services.smart_docs.communication_orchestrator import (
        SMSOrchestrator,
        CalendarCoordinator,
        generate_vcard,
        MESSAGE_TEMPLATES,
    )

    sms = SMSOrchestrator(db=db, org_id=org_id)
    await sms.send_intro_sequence(
        loan_id=loan_id,
        borrower_phone="+15551234567",
        borrower_name="Jane Doe",
        lo_name="Tim Loss",
    )

    cal = CalendarCoordinator(db=db, org_id=org_id)
    result = await cal.book_appointment(
        loan_id=loan_id,
        pa_user_id=pa_id,
        borrower_name="Jane Doe",
        borrower_phone="+15551234567",
        start_time=slot_start,
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import textwrap
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from database.models.app_completion import (
    AppointmentCoordination,
    BorrowerCommunicationLog,
    BookingStatus,
    CommChannel,
    MessageIntent,
    MissingItem,
    MissingItemStatus,
    SenderType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

_APP_URL = os.getenv("APP_URL", "https://app.perenniaai.com")

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_FROM_NUMBER = os.getenv("TELNYX_FROM_NUMBER", "+18438838956")
TELNYX_MESSAGING_PROFILE_ID = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID",
    "40019bed-2fa1-4407-a0c6-fe4c6b222c93",
)

# Delay between messages in the intro sequence (seconds).  Short pause so
# messages arrive in order without overwhelming the recipient.
_INTRO_SEQUENCE_DELAY_SECS = 3.0

# Standard and extended PA call durations (minutes).
_STANDARD_CALL_DURATION = 15
_EXTENDED_CALL_DURATION = 30

# Complexity threshold: reviews at or above this score get the extended slot.
_COMPLEXITY_THRESHOLD = 7

# Maximum number of proposed time windows to return from slot search.
_MAX_PROPOSED_SLOTS = 5


# =============================================================================
# MESSAGE TEMPLATES
# =============================================================================

MESSAGE_TEMPLATES: Dict[str, str] = {
    # ------------------------------------------------------------------
    # Intro sequence
    # ------------------------------------------------------------------
    "intro_1": (
        "Hi {first_name}, this is {agent_name} with {lo_name}'s team at "
        "{company}. I'm helping review your application and next steps so "
        "we can keep everything moving smoothly."
    ),
    "intro_2": (
        "I'm sending over our contact card now. Please save it to your "
        "phone and reply SAVED once it's done. That way anytime our team "
        "reaches out, you'll know it's us."
    ),
    "intro_confirmed": (
        "Perfect \u2014 thank you. I reviewed your application and there are "
        "just a few items we need to finish up. Some we can handle right "
        "here by text, and if needed I can help coordinate a quick call "
        "with our team."
    ),

    # ------------------------------------------------------------------
    # Question flow
    # ------------------------------------------------------------------
    "question_prefix": "Quick question \u2014 {question}",
    "confirmation": (
        "Got it, thank you! Just to confirm \u2014 {value_summary}. "
        "Is that correct? Reply YES or correct me."
    ),

    # ------------------------------------------------------------------
    # Document requests
    # ------------------------------------------------------------------
    "doc_request_sms": (
        "We've updated your to-do list in the secure portal with "
        "{count} item(s) needed to keep your loan moving. Please log in "
        "to review and upload: {portal_link}"
    ),

    # ------------------------------------------------------------------
    # Availability & scheduling
    # ------------------------------------------------------------------
    "availability_request": (
        "Some of these items would be fastest to review together on a "
        "quick call with our team. What times are usually best for you "
        "today or tomorrow?"
    ),
    "appointment_booked": (
        "Great \u2014 I've scheduled a quick review call for {date_time} "
        "with {pa_name} from our team. You'll receive a calendar invite "
        "shortly. We'll cover the remaining items on your application so "
        "we can keep things moving."
    ),
    "appointment_reminder_24h": (
        "Reminder: You have a review call tomorrow at {time} with "
        "{pa_name}. If you need to reschedule, just reply here."
    ),
    "appointment_reminder_1h": (
        "Your review call with {pa_name} is in 1 hour at {time}. "
        "{meeting_link_text}"
    ),

    # ------------------------------------------------------------------
    # Follow-ups
    # ------------------------------------------------------------------
    "follow_up_docs": (
        "Hi {first_name}, just checking in \u2014 we're still waiting on "
        "{doc_count} document(s) in your portal. Uploading these helps us "
        "keep your loan on track: {portal_link}"
    ),
    "follow_up_response": (
        "Hi {first_name}, I sent a couple of questions earlier about your "
        "application. When you get a moment, your replies help us keep "
        "things moving!"
    ),

    # ------------------------------------------------------------------
    # Escalation / completion
    # ------------------------------------------------------------------
    "escalation_to_human": (
        "I'm going to have {pa_name} from our team reach out directly. "
        "They can walk through everything with you. You should hear from "
        "them shortly."
    ),
    "completion_congrats": (
        "Great news \u2014 your application is looking complete! Our team "
        "will review everything and be in touch with next steps. Thank "
        "you for your quick responses!"
    ),

    # ------------------------------------------------------------------
    # Email templates
    # ------------------------------------------------------------------
    "email_doc_request_subject": (
        "Action Needed: Documents for Your Loan Application"
    ),
    "email_doc_request_body": textwrap.dedent("""\
        Hi {first_name},

        We're making great progress on your loan application. To keep things
        moving, we need a few documents from you.

        Please log into your secure portal to review and upload the requested items:
        {portal_link}

        Items needed:
        {doc_list}

        If you have any questions, feel free to reply to this email or text us
        at {team_phone}.

        Best regards,
        {lo_name}'s Team
        {company}"""),

    "email_appointment_subject": "Review Call Scheduled \u2014 {date}",
    "email_appointment_body": textwrap.dedent("""\
        Hi {first_name},

        We've scheduled a brief review call to go over your loan application:

        Date: {date}
        Time: {time}
        Duration: {duration} minutes
        With: {pa_name}
        {meeting_link_section}

        We'll cover a few remaining items on your application. No preparation
        needed \u2014 we'll walk through everything together.

        Best regards,
        {lo_name}'s Team
        {company}"""),
}


# =============================================================================
# VCARD GENERATOR
# =============================================================================

def generate_vcard(
    lo_name: str,
    lo_phone: str,
    lo_email: str,
    company_name: str,
    lo_title: str = "Loan Officer",
    lo_nmls: str | None = None,
) -> str:
    """Generate a VCF (vCard 3.0) contact card for the loan officer's team.

    The card is suitable for sending via MMS (as a .vcf file URL) or as an
    email attachment.  It follows the RFC 2426 format for broad device
    compatibility.

    Args:
        lo_name: Full display name, e.g. ``"Tim Loss"``.
        lo_phone: E.164 phone number, e.g. ``"+18431234567"``.
        lo_email: Email address.
        company_name: Company / organization name.
        lo_title: Job title.  Defaults to ``"Loan Officer"``.
        lo_nmls: Optional NMLS number appended to the note field.

    Returns:
        A string containing the complete VCF payload.
    """
    parts = lo_name.strip().split(None, 1)
    first_name = parts[0] if parts else lo_name
    last_name = parts[1] if len(parts) > 1 else ""

    # Normalize phone: strip non-digits except leading +
    clean_phone = lo_phone.strip()
    if not clean_phone.startswith("+"):
        clean_phone = f"+1{clean_phone.lstrip('+')}"

    note_parts = []
    if lo_nmls:
        note_parts.append(f"NMLS# {lo_nmls}")

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{last_name};{first_name};;;",
        f"FN:{lo_name}",
        f"ORG:{company_name}",
        f"TITLE:{lo_title}",
        f"TEL;TYPE=WORK,VOICE:{clean_phone}",
        f"EMAIL;TYPE=WORK:{lo_email}",
    ]

    if note_parts:
        lines.append(f"NOTE:{' | '.join(note_parts)}")

    lines.extend([
        f"REV:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "END:VCARD",
    ])

    return "\r\n".join(lines)


# =============================================================================
# COMMUNICATION LOGGER (mixin)
# =============================================================================

class _CommunicationLoggerMixin:
    """Provides ``log_communication`` shared by SMSOrchestrator and CalendarCoordinator."""

    db: Session
    org_id: str

    def _log_communication(
        self,
        loan_id: str,
        channel: str,
        sender_type: str,
        message_intent: str,
        message_body: str,
        review_id: int | None = None,
        missing_item_id: int | None = None,
        template_id: str | None = None,
        recipient_phone: str | None = None,
        recipient_email: str | None = None,
        delivery_status: str = "QUEUED",
        external_message_id: str | None = None,
    ) -> int:
        """Persist a row to ``borrower_communication_logs``.

        Every outbound message (and inbound reply when processed) must be
        logged here so the ACO has a full audit trail.

        Returns:
            The auto-generated ``id`` of the new log row.
        """
        record = BorrowerCommunicationLog(
            organization_id=str(self.org_id),
            loan_id=str(loan_id),
            review_id=review_id,
            missing_item_id=missing_item_id,
            channel=channel,
            sender_type=sender_type,
            message_intent=message_intent,
            template_id=template_id,
            message_body=message_body,
            recipient_phone=recipient_phone,
            recipient_email=recipient_email,
            delivery_status=delivery_status,
            external_message_id=external_message_id,
        )
        self.db.add(record)
        self.db.flush()
        logger.info(
            "Communication logged: loan=%s channel=%s intent=%s status=%s log_id=%s",
            loan_id, channel, message_intent, delivery_status, record.id,
        )
        return record.id

    def _update_delivery_status(self, log_id: int, status: str, error: str | None = None) -> None:
        """Update the delivery status of an existing log entry."""
        record = self.db.query(BorrowerCommunicationLog).filter(
            BorrowerCommunicationLog.id == log_id,
        ).first()
        if record:
            record.delivery_status = status
            if error:
                record.error_message = error
            self.db.flush()


# =============================================================================
# TELNYX SMS INTEGRATION
# =============================================================================

class _TelnyxSMSMixin:
    """Low-level SMS / MMS delivery via Telnyx."""

    async def _send_sms(
        self,
        to_number: str,
        message: str,
        media_urls: list[str] | None = None,
    ) -> Dict[str, Any]:
        """Send an SMS (or MMS if media_urls provided) through Telnyx.

        Uses ``asyncio.to_thread`` to avoid blocking the event loop since
        the ``telnyx`` SDK is synchronous.

        Args:
            to_number: Recipient in E.164 format.
            message: Message body text.
            media_urls: Optional list of publicly-accessible media URLs for MMS.

        Returns:
            ``{"message_id": str, "status": str, "error": str | None}``
        """
        if not to_number:
            return {"message_id": None, "status": "failed", "error": "No recipient phone number"}

        telnyx_api_key = TELNYX_API_KEY
        telnyx_from = TELNYX_FROM_NUMBER
        messaging_profile = TELNYX_MESSAGING_PROFILE_ID

        if not telnyx_api_key or not telnyx_from:
            logger.warning("Telnyx not configured; SMS to %s suppressed", to_number)
            return {"message_id": None, "status": "failed", "error": "SMS service not configured"}

        def _blocking_send() -> Dict[str, Any]:
            from telephony.sms import send_sms as telnyx_send_sms

            try:
                result = telnyx_send_sms(
                    to=to_number,
                    from_=telnyx_from,
                    text=message,
                    messaging_profile_id=messaging_profile or None,
                    media_urls=media_urls,
                    api_key=telnyx_api_key,
                )
                msg_id = result.get("id") or str(uuid.uuid4())
                return {"message_id": str(msg_id), "status": "sent", "error": None}
            except Exception as e:
                logger.exception("Telnyx send failed to=%s", to_number)
                return {"message_id": None, "status": "failed", "error": str(e)}

        return await asyncio.to_thread(_blocking_send)

    async def _send_mms_vcard(
        self,
        to_number: str,
        vcard_text: str,
        caption: str = "",
    ) -> Dict[str, Any]:
        """Send a VCard as MMS.

        The VCF payload is sent as a publicly-hosted media URL.  If no
        hosting is available, falls back to sending the VCF content inline
        with a brief caption.

        In production, the VCard file should be uploaded to S3/CDN and the
        public URL passed via ``media_urls``.  For now, we send the caption
        text and note that VCard delivery requires MMS hosting.
        """
        vcard_hosting_url = os.getenv("VCARD_HOSTING_BASE_URL", "")
        if vcard_hosting_url:
            # If we have hosted VCards, construct the URL
            vcard_url = f"{vcard_hosting_url}/team-contact.vcf"
            return await self._send_sms(
                to_number=to_number,
                message=caption or "Here's our contact card \u2014 save it to your phone!",
                media_urls=[vcard_url],
            )

        # Fallback: send as plain SMS with the caption
        fallback_msg = (
            caption
            or "Here's our contact info \u2014 save this number so you know it's us!"
        )
        logger.info(
            "VCard hosting not configured; sending text fallback to %s", to_number,
        )
        return await self._send_sms(to_number=to_number, message=fallback_msg)


# =============================================================================
# SMS ORCHESTRATOR
# =============================================================================

class SMSOrchestrator(_CommunicationLoggerMixin, _TelnyxSMSMixin):
    """Manages sequential SMS conversations with borrowers during the ACO flow.

    Each public method sends one or more SMS messages, logs them to
    ``BorrowerCommunicationLog``, and returns delivery metadata.  The
    caller (typically the main ACO engine) drives the conversation state
    machine; this class owns only the *sending* and *logging* concerns.

    Args:
        db: Active SQLAlchemy session (caller owns commit lifecycle).
        org_id: Organization ID for tenant isolation.
        review_id: Optional review ID to associate all messages with.
    """

    def __init__(self, db: Session, org_id: str, review_id: int | None = None):
        self.db = db
        self.org_id = str(org_id)
        self.review_id = review_id

    # ------------------------------------------------------------------
    # Portal link helper
    # ------------------------------------------------------------------

    def _portal_link(self, loan_id: str) -> str:
        """Build the borrower portal upload URL for a loan."""
        return f"{_APP_URL}/portal/documents/{loan_id}"

    # ------------------------------------------------------------------
    # Template rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _render(template_key: str, variables: Dict[str, Any]) -> str:
        """Render a message template with the given variables.

        Uses ``str.format_map`` so missing keys do not raise; they stay
        as literal ``{key}`` in the output (safe fallback).
        """
        template = MESSAGE_TEMPLATES.get(template_key, "")
        if not template:
            logger.warning("Unknown template key: %s", template_key)
            return ""

        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return f"{{{key}}}"

        return template.format_map(_SafeDict(variables))

    # ------------------------------------------------------------------
    # Intro sequence
    # ------------------------------------------------------------------

    async def send_intro_sequence(
        self,
        loan_id: str,
        borrower_phone: str,
        borrower_name: str,
        lo_name: str,
        lo_phone: str | None = None,
        lo_email: str | None = None,
        company_name: str = "CMG Home Loans",
        agent_name: str = "Sarah",
    ) -> list[dict]:
        """Send the 3-message introduction sequence.

        1. Introduce ourselves as part of the LO's team.
        2. Announce the contact card and ask borrower to save it.
        3. Deliver the VCard (contact card via MMS or fallback).

        The ACO engine should wait for a ``SAVED`` reply before proceeding
        to the question flow.  This method only *sends*; reply processing
        is handled by the inbound webhook / response classifier.

        Args:
            loan_id: Loan being worked.
            borrower_phone: Borrower mobile in E.164 format.
            borrower_name: Borrower first name for personalization.
            lo_name: Loan officer full name.
            lo_phone: LO phone for the VCard (falls back to Telnyx from number).
            lo_email: LO email for the VCard.
            company_name: Company name used in templates.
            agent_name: AI agent persona name (default ``"Sarah"``).

        Returns:
            List of delivery result dicts, one per message sent.
        """
        first_name = borrower_name.split()[0] if borrower_name else "there"
        results: list[dict] = []

        # --- Message 1: Introduction ---
        msg1_text = self._render("intro_1", {
            "first_name": first_name,
            "agent_name": agent_name,
            "lo_name": lo_name,
            "company": company_name,
        })
        delivery1 = await self._send_sms(to_number=borrower_phone, message=msg1_text)
        log_id_1 = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.INTRO.value,
            template_id="intro_1",
            message_body=msg1_text,
            recipient_phone=borrower_phone,
            delivery_status=delivery1.get("status", "QUEUED"),
            external_message_id=delivery1.get("message_id"),
            review_id=self.review_id,
        )
        results.append({**delivery1, "template": "intro_1", "log_id": log_id_1})

        # Brief pause so messages arrive in order
        await asyncio.sleep(_INTRO_SEQUENCE_DELAY_SECS)

        # --- Message 2: Contact card announcement ---
        msg2_text = self._render("intro_2", {})
        delivery2 = await self._send_sms(to_number=borrower_phone, message=msg2_text)
        log_id_2 = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.INTRO.value,
            template_id="intro_2",
            message_body=msg2_text,
            recipient_phone=borrower_phone,
            delivery_status=delivery2.get("status", "QUEUED"),
            external_message_id=delivery2.get("message_id"),
            review_id=self.review_id,
        )
        results.append({**delivery2, "template": "intro_2", "log_id": log_id_2})

        await asyncio.sleep(_INTRO_SEQUENCE_DELAY_SECS)

        # --- Message 3: VCard delivery ---
        vcard_content = generate_vcard(
            lo_name=lo_name,
            lo_phone=lo_phone or TELNYX_FROM_NUMBER,
            lo_email=lo_email or "",
            company_name=company_name,
        )
        delivery3 = await self._send_mms_vcard(
            to_number=borrower_phone,
            vcard_text=vcard_content,
            caption=f"Contact card for {lo_name}'s team at {company_name}",
        )
        log_id_3 = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.VCARD.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.CONTACT_CARD.value,
            template_id="vcard",
            message_body=f"[VCard for {lo_name}]",
            recipient_phone=borrower_phone,
            delivery_status=delivery3.get("status", "QUEUED"),
            external_message_id=delivery3.get("message_id"),
            review_id=self.review_id,
        )
        results.append({**delivery3, "template": "vcard", "log_id": log_id_3})

        logger.info(
            "Intro sequence sent: loan=%s phone=%s messages=%d",
            loan_id, borrower_phone, len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Intro confirmed (post-SAVED reply)
    # ------------------------------------------------------------------

    async def send_intro_confirmed(
        self,
        loan_id: str,
        borrower_phone: str,
    ) -> dict:
        """Send the confirmation message after the borrower replies SAVED.

        This bridges the intro and the question-by-question flow.
        """
        msg_text = self._render("intro_confirmed", {})
        delivery = await self._send_sms(to_number=borrower_phone, message=msg_text)
        log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.INTRO.value,
            template_id="intro_confirmed",
            message_body=msg_text,
            recipient_phone=borrower_phone,
            delivery_status=delivery.get("status", "QUEUED"),
            external_message_id=delivery.get("message_id"),
            review_id=self.review_id,
        )
        return {**delivery, "template": "intro_confirmed", "log_id": log_id}

    # ------------------------------------------------------------------
    # Question flow
    # ------------------------------------------------------------------

    async def send_question(
        self,
        loan_id: str,
        borrower_phone: str,
        missing_item_id: int,
        question_text: str,
    ) -> dict:
        """Send a single question about a missing item.

        The question is rendered through the ``question_prefix`` template
        and logged with a reference to the specific ``MissingItem``.

        Args:
            loan_id: Loan ID.
            borrower_phone: Borrower phone in E.164.
            missing_item_id: FK to ``missing_items.id``.
            question_text: The borrower-facing question string.

        Returns:
            Delivery result dict with ``log_id``.
        """
        msg_text = self._render("question_prefix", {"question": question_text})
        delivery = await self._send_sms(to_number=borrower_phone, message=msg_text)

        log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.QUESTION.value,
            template_id="question_prefix",
            message_body=msg_text,
            recipient_phone=borrower_phone,
            missing_item_id=missing_item_id,
            delivery_status=delivery.get("status", "QUEUED"),
            external_message_id=delivery.get("message_id"),
            review_id=self.review_id,
        )

        # Mark the missing item as sent
        item = self.db.query(MissingItem).filter(
            MissingItem.id == missing_item_id,
        ).first()
        if item and item.status == MissingItemStatus.IDENTIFIED.value:
            item.status = MissingItemStatus.SENT_TO_BORROWER.value
            item.sent_at = datetime.now(timezone.utc)
            self.db.flush()

        return {**delivery, "template": "question_prefix", "log_id": log_id}

    async def send_confirmation(
        self,
        loan_id: str,
        borrower_phone: str,
        missing_item_id: int,
        value_summary: str,
    ) -> dict:
        """Send a confirmation prompt after borrower provides an answer.

        Asks the borrower to confirm or correct the value we captured.
        """
        msg_text = self._render("confirmation", {"value_summary": value_summary})
        delivery = await self._send_sms(to_number=borrower_phone, message=msg_text)

        log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.CONFIRMATION.value,
            template_id="confirmation",
            message_body=msg_text,
            recipient_phone=borrower_phone,
            missing_item_id=missing_item_id,
            delivery_status=delivery.get("status", "QUEUED"),
            external_message_id=delivery.get("message_id"),
            review_id=self.review_id,
        )
        return {**delivery, "template": "confirmation", "log_id": log_id}

    # ------------------------------------------------------------------
    # Document request notifications
    # ------------------------------------------------------------------

    async def send_doc_request_notification(
        self,
        loan_id: str,
        borrower_phone: str,
        borrower_email: str | None,
        borrower_name: str,
        lo_name: str,
        doc_count: int,
        doc_labels: list[str] | None = None,
        company_name: str = "CMG Home Loans",
    ) -> dict:
        """Notify the borrower that document requests are staged in the portal.

        Sends an SMS with a portal link and, when an email is available,
        a detailed email listing each requested document.

        Args:
            loan_id: Loan ID.
            borrower_phone: Borrower phone in E.164.
            borrower_email: Borrower email (optional).
            borrower_name: Borrower first name.
            lo_name: Loan officer name for email sign-off.
            doc_count: Number of documents requested.
            doc_labels: Optional human-readable labels for each doc.
            company_name: Company name.

        Returns:
            Dict with SMS and (optionally) email delivery results.
        """
        first_name = borrower_name.split()[0] if borrower_name else "there"
        portal_link = self._portal_link(loan_id)
        result: Dict[str, Any] = {"loan_id": loan_id, "doc_count": doc_count}

        # --- SMS ---
        sms_text = self._render("doc_request_sms", {
            "count": str(doc_count),
            "portal_link": portal_link,
        })
        sms_delivery = await self._send_sms(to_number=borrower_phone, message=sms_text)
        sms_log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.DOC_REQUEST.value,
            template_id="doc_request_sms",
            message_body=sms_text,
            recipient_phone=borrower_phone,
            delivery_status=sms_delivery.get("status", "QUEUED"),
            external_message_id=sms_delivery.get("message_id"),
            review_id=self.review_id,
        )
        result["sms"] = {**sms_delivery, "log_id": sms_log_id}

        # --- Email (if address available) ---
        if borrower_email:
            doc_list_str = "\n".join(
                f"  - {label}" for label in (doc_labels or [f"Document {i+1}" for i in range(doc_count)])
            )
            email_body = self._render("email_doc_request_body", {
                "first_name": first_name,
                "portal_link": portal_link,
                "doc_list": doc_list_str,
                "team_phone": TELNYX_FROM_NUMBER,
                "lo_name": lo_name,
                "company": company_name,
            })
            email_subject = self._render("email_doc_request_subject", {})

            email_delivery = await self._send_email(
                to_email=borrower_email,
                subject=email_subject,
                body=email_body,
            )
            email_log_id = self._log_communication(
                loan_id=loan_id,
                channel=CommChannel.EMAIL.value,
                sender_type=SenderType.AI_AGENT.value,
                message_intent=MessageIntent.DOC_REQUEST.value,
                template_id="email_doc_request",
                message_body=email_body[:2000],
                recipient_email=borrower_email,
                delivery_status=email_delivery.get("status", "QUEUED"),
                review_id=self.review_id,
            )
            result["email"] = {**email_delivery, "log_id": email_log_id}

        return result

    # ------------------------------------------------------------------
    # Availability request
    # ------------------------------------------------------------------

    async def send_availability_request(
        self,
        loan_id: str,
        borrower_phone: str,
        borrower_name: str,
    ) -> dict:
        """Ask the borrower for their availability for a PA call.

        The ACO engine will parse the free-text reply to extract proposed
        time windows.
        """
        msg_text = self._render("availability_request", {})
        delivery = await self._send_sms(to_number=borrower_phone, message=msg_text)

        log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.AVAILABILITY_REQUEST.value,
            template_id="availability_request",
            message_body=msg_text,
            recipient_phone=borrower_phone,
            delivery_status=delivery.get("status", "QUEUED"),
            external_message_id=delivery.get("message_id"),
            review_id=self.review_id,
        )
        return {**delivery, "template": "availability_request", "log_id": log_id}

    # ------------------------------------------------------------------
    # Appointment confirmation
    # ------------------------------------------------------------------

    async def send_appointment_confirmation(
        self,
        loan_id: str,
        borrower_phone: str,
        borrower_name: str,
        borrower_email: str | None,
        pa_name: str,
        booked_start: datetime,
        duration_minutes: int = _STANDARD_CALL_DURATION,
        lo_name: str = "",
        company_name: str = "CMG Home Loans",
        meeting_link: str | None = None,
    ) -> dict:
        """Confirm a scheduled appointment via SMS and optional email.

        Args:
            loan_id: Loan ID.
            borrower_phone: Borrower phone.
            borrower_name: Borrower first name.
            borrower_email: Borrower email (optional).
            pa_name: Production assistant name for the call.
            booked_start: UTC start time of the appointment.
            duration_minutes: Call duration.
            lo_name: Loan officer name for email.
            company_name: Company name.
            meeting_link: Optional video/phone meeting URL.

        Returns:
            Dict with SMS and email delivery results.
        """
        first_name = borrower_name.split()[0] if borrower_name else "there"
        # Format date/time for display (Eastern default)
        display_dt = booked_start.strftime("%A, %B %d at %-I:%M %p")
        display_date = booked_start.strftime("%B %d, %Y")
        display_time = booked_start.strftime("%-I:%M %p")

        result: Dict[str, Any] = {"loan_id": loan_id}

        # --- SMS ---
        meeting_link_text = f"Join here: {meeting_link}" if meeting_link else ""
        sms_text = self._render("appointment_booked", {
            "date_time": display_dt,
            "pa_name": pa_name,
        })
        sms_delivery = await self._send_sms(to_number=borrower_phone, message=sms_text)
        sms_log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=MessageIntent.SCHEDULING.value,
            template_id="appointment_booked",
            message_body=sms_text,
            recipient_phone=borrower_phone,
            delivery_status=sms_delivery.get("status", "QUEUED"),
            external_message_id=sms_delivery.get("message_id"),
            review_id=self.review_id,
        )
        result["sms"] = {**sms_delivery, "log_id": sms_log_id}

        # --- Email ---
        if borrower_email:
            meeting_link_section = (
                f"Meeting Link: {meeting_link}" if meeting_link else "We will call you at the number on file."
            )
            email_body = self._render("email_appointment_body", {
                "first_name": first_name,
                "date": display_date,
                "time": display_time,
                "duration": str(duration_minutes),
                "pa_name": pa_name,
                "meeting_link_section": meeting_link_section,
                "lo_name": lo_name,
                "company": company_name,
            })
            email_subject = self._render("email_appointment_subject", {
                "date": display_date,
            })
            email_delivery = await self._send_email(
                to_email=borrower_email,
                subject=email_subject,
                body=email_body,
            )
            email_log_id = self._log_communication(
                loan_id=loan_id,
                channel=CommChannel.EMAIL.value,
                sender_type=SenderType.AI_AGENT.value,
                message_intent=MessageIntent.SCHEDULING.value,
                template_id="email_appointment",
                message_body=email_body[:2000],
                recipient_email=borrower_email,
                delivery_status=email_delivery.get("status", "QUEUED"),
                review_id=self.review_id,
            )
            result["email"] = {**email_delivery, "log_id": email_log_id}

        return result

    # ------------------------------------------------------------------
    # Follow-up reminders
    # ------------------------------------------------------------------

    async def send_follow_up_reminder(
        self,
        loan_id: str,
        borrower_phone: str,
        reminder_type: str,
        context: Dict[str, Any],
    ) -> dict:
        """Send a follow-up reminder SMS.

        Supported ``reminder_type`` values:
          - ``"missing_docs"`` -- documents still needed in portal.
          - ``"unanswered_questions"`` -- borrower hasn't replied to questions.
          - ``"appointment_24h"`` -- 24-hour appointment reminder.
          - ``"appointment_1h"`` -- 1-hour appointment reminder.
          - ``"escalation"`` -- handoff to human PA.
          - ``"completion"`` -- all items resolved.

        Args:
            loan_id: Loan ID.
            borrower_phone: Borrower phone.
            reminder_type: One of the supported types above.
            context: Template variables (keys vary by type).

        Returns:
            Delivery result dict.
        """
        template_map = {
            "missing_docs": "follow_up_docs",
            "unanswered_questions": "follow_up_response",
            "appointment_24h": "appointment_reminder_24h",
            "appointment_1h": "appointment_reminder_1h",
            "escalation": "escalation_to_human",
            "completion": "completion_congrats",
        }

        template_key = template_map.get(reminder_type)
        if not template_key:
            logger.warning("Unknown reminder_type: %s", reminder_type)
            return {"status": "failed", "error": f"Unknown reminder type: {reminder_type}"}

        # Inject portal link for doc-related reminders
        if reminder_type == "missing_docs":
            context.setdefault("portal_link", self._portal_link(loan_id))

        msg_text = self._render(template_key, context)
        delivery = await self._send_sms(to_number=borrower_phone, message=msg_text)

        intent_map = {
            "missing_docs": MessageIntent.REMINDER.value,
            "unanswered_questions": MessageIntent.REMINDER.value,
            "appointment_24h": MessageIntent.REMINDER.value,
            "appointment_1h": MessageIntent.REMINDER.value,
            "escalation": MessageIntent.ESCALATION.value,
            "completion": MessageIntent.CONFIRMATION.value,
        }

        log_id = self._log_communication(
            loan_id=loan_id,
            channel=CommChannel.SMS.value,
            sender_type=SenderType.AI_AGENT.value,
            message_intent=intent_map.get(reminder_type, MessageIntent.REMINDER.value),
            template_id=template_key,
            message_body=msg_text,
            recipient_phone=borrower_phone,
            delivery_status=delivery.get("status", "QUEUED"),
            external_message_id=delivery.get("message_id"),
            review_id=self.review_id,
        )
        return {**delivery, "template": template_key, "log_id": log_id}

    # ------------------------------------------------------------------
    # Email helper (wraps existing notification service)
    # ------------------------------------------------------------------

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Send an email through the existing notification service.

        Falls back gracefully if the notification service is unavailable.
        """
        try:
            from services.notification_service import notification_service

            def _blocking_send():
                return notification_service.send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                )

            result = await asyncio.to_thread(_blocking_send)
            return {"status": "sent", "error": None, "detail": result}
        except ImportError:
            logger.warning("notification_service not available; email to %s suppressed", to_email)
            return {"status": "failed", "error": "Email service not available"}
        except Exception as e:
            logger.exception("Email send failed to=%s", to_email)
            return {"status": "failed", "error": str(e)}


# =============================================================================
# CALENDAR COORDINATOR
# =============================================================================

class CalendarCoordinator(_CommunicationLoggerMixin):
    """Coordinates PA call scheduling with the existing calendar system.

    Finds available production assistants, books appointments on the
    scheduler calendar, generates pre-call briefs, and sends confirmation
    messages through the :class:`SMSOrchestrator`.

    Args:
        db: Active SQLAlchemy session.
        org_id: Organization ID for tenant isolation.
    """

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = str(org_id)
        self._sms = SMSOrchestrator(db=db, org_id=org_id)

    # ------------------------------------------------------------------
    # Find available PA
    # ------------------------------------------------------------------

    async def find_available_pa(
        self,
        preferred_windows: list[dict],
        duration_minutes: int = _STANDARD_CALL_DURATION,
    ) -> dict:
        """Find an available production assistant for the requested time windows.

        Queries users with ``permission_role = 'processing'`` in the org and
        checks their existing ``scheduler_appointments`` for conflicts.

        Args:
            preferred_windows: List of ``{"start": datetime, "end": datetime}``
                windows the borrower is available.
            duration_minutes: Required slot duration in minutes.

        Returns:
            Dict with ``pa_user_id``, ``pa_name``, ``available_slots``, and
            ``recommended_slot``.  Returns empty ``available_slots`` if no PA
            is free during the requested windows.
        """
        # Get PAs (processing role) in this org
        pa_rows = self.db.execute(
            text("""
                SELECT id, first_name, last_name, timezone
                FROM users
                WHERE organization_id = :org_id
                  AND permission_role IN ('processing', 'operations')
                  AND is_active = TRUE
                ORDER BY last_activity_at DESC NULLS LAST
            """),
            {"org_id": self.org_id},
        ).fetchall()

        if not pa_rows:
            logger.warning("No active PAs found for org %s", self.org_id)
            return {
                "pa_user_id": None,
                "pa_name": None,
                "available_slots": [],
                "recommended_slot": None,
            }

        # For each PA, check availability against each borrower window
        best_pa = None
        best_slots: list[dict] = []

        for pa in pa_rows:
            pa_id = pa[0]
            pa_name = f"{pa[1] or ''} {pa[2] or ''}".strip()
            pa_slots: list[dict] = []

            for window in preferred_windows:
                window_start = window.get("start")
                window_end = window.get("end")
                if not window_start or not window_end:
                    continue

                # Ensure datetimes are timezone-aware
                if window_start.tzinfo is None:
                    window_start = window_start.replace(tzinfo=timezone.utc)
                if window_end.tzinfo is None:
                    window_end = window_end.replace(tzinfo=timezone.utc)

                # Check for conflicting appointments
                conflict_count = self.db.execute(
                    text("""
                        SELECT COUNT(*) FROM scheduler_appointments
                        WHERE organization_id = :org_id
                          AND assigned_user_id = :pa_id
                          AND status NOT IN ('cancelled', 'no_show')
                          AND scheduled_start < :window_end
                          AND scheduled_end > :window_start
                    """),
                    {
                        "org_id": self.org_id,
                        "pa_id": pa_id,
                        "window_start": window_start,
                        "window_end": window_end,
                    },
                ).scalar()

                if conflict_count == 0:
                    slot_end = window_start + timedelta(minutes=duration_minutes)
                    if slot_end <= window_end:
                        pa_slots.append({
                            "start": window_start,
                            "end": slot_end,
                        })

            if pa_slots and (not best_slots or len(pa_slots) > len(best_slots)):
                best_pa = {"id": pa_id, "name": pa_name}
                best_slots = pa_slots

        if not best_pa or not best_slots:
            return {
                "pa_user_id": None,
                "pa_name": None,
                "available_slots": [],
                "recommended_slot": None,
            }

        # Limit to max proposed slots and pick the earliest as recommended
        limited_slots = best_slots[:_MAX_PROPOSED_SLOTS]
        recommended = min(limited_slots, key=lambda s: s["start"])

        return {
            "pa_user_id": str(best_pa["id"]),
            "pa_name": best_pa["name"],
            "available_slots": limited_slots,
            "recommended_slot": recommended,
        }

    # ------------------------------------------------------------------
    # Book appointment
    # ------------------------------------------------------------------

    async def book_appointment(
        self,
        loan_id: str,
        pa_user_id: str,
        borrower_name: str,
        borrower_phone: str,
        start_time: datetime,
        duration_minutes: int | None = None,
        review_id: int | None = None,
        borrower_email: str | None = None,
        lo_name: str = "",
        company_name: str = "CMG Home Loans",
        pre_call_brief: str | None = None,
    ) -> dict:
        """Book a PA call appointment and send confirmations.

        Creates an ``AppointmentCoordination`` record, inserts a
        ``scheduler_appointments`` row, notifies the PA (with pre-call
        brief), and confirms with the borrower via SMS + email.

        Appointment title follows the convention:
        ``"Application Review Call \u2013 {borrower_name}"``

        Duration defaults to 15 minutes for standard complexity or
        30 minutes when ``complexity_score >= 7`` on the linked review.

        Args:
            loan_id: Loan ID.
            pa_user_id: User ID of the production assistant.
            borrower_name: Borrower name.
            borrower_phone: Borrower phone.
            start_time: Appointment start in UTC.
            duration_minutes: Override duration (auto-selects if None).
            review_id: Optional linked review ID.
            borrower_email: Optional borrower email.
            lo_name: Loan officer name.
            company_name: Company name.
            pre_call_brief: Pre-generated brief (generated if None).

        Returns:
            Dict with ``coordination_id``, ``calendar_event_id``,
            ``booked_start``, ``booked_end``, ``pa_name``, and
            ``confirmation_results``.
        """
        # Ensure timezone-aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        # Determine duration based on complexity
        if duration_minutes is None:
            duration_minutes = self._determine_duration(review_id)

        end_time = start_time + timedelta(minutes=duration_minutes)

        # Look up PA name
        pa_row = self.db.execute(
            text("SELECT first_name, last_name, email FROM users WHERE id = :pa_id"),
            {"pa_id": pa_user_id},
        ).fetchone()
        pa_name = f"{pa_row[0] or ''} {pa_row[1] or ''}".strip() if pa_row else "Team Member"
        pa_email = pa_row[2] if pa_row else None

        # Generate pre-call brief if not provided
        if pre_call_brief is None and review_id:
            pre_call_brief = await self.generate_pre_call_brief(review_id)

        # Count unresolved items for the coordination record
        unresolved_count = 0
        complexity = 0
        if review_id:
            from database.models.app_completion import ApplicationCompletenessReview
            review = self.db.query(ApplicationCompletenessReview).filter(
                ApplicationCompletenessReview.id == review_id,
            ).first()
            if review:
                complexity = review.complexity_score or 0
                unresolved_count = self.db.query(MissingItem).filter(
                    MissingItem.review_id == review_id,
                    MissingItem.status.notin_([
                        MissingItemStatus.RESOLVED.value,
                        MissingItemStatus.CANCELLED.value,
                    ]),
                ).count()

        # --- Create AppointmentCoordination record ---
        coordination = AppointmentCoordination(
            organization_id=str(self.org_id),
            loan_id=str(loan_id),
            review_id=review_id,
            assigned_pa_user_id=str(pa_user_id),
            borrower_name=borrower_name,
            borrower_phone=borrower_phone,
            borrower_email=borrower_email,
            booked_start=start_time,
            booked_end=end_time,
            duration_minutes=duration_minutes,
            booking_status=BookingStatus.BOOKED.value,
            appointment_type="APPLICATION_REVIEW",
            pre_call_brief=pre_call_brief,
            unresolved_items_count=unresolved_count,
            complexity_score=complexity,
        )
        self.db.add(coordination)
        self.db.flush()

        # --- Create scheduler_appointments row ---
        calendar_event_id = str(uuid.uuid4())
        title = f"Application Review Call \u2013 {borrower_name}"

        self.db.execute(
            text("""
                INSERT INTO scheduler_appointments (
                    organization_id, assigned_user_id, loan_id,
                    title, description, meeting_type, meeting_mode,
                    scheduled_start, scheduled_end, duration_minutes,
                    timezone, attendee_name, attendee_phone, attendee_email,
                    status, booked_by_ai, ai_booking_context,
                    internal_notes, external_id, external_source,
                    created_at, updated_at
                ) VALUES (
                    :org_id, :pa_id, :loan_id,
                    :title, :description, 'phone_call', 'phone',
                    :start, :end, :duration,
                    'America/New_York', :attendee_name, :attendee_phone, :attendee_email,
                    'booked', TRUE, :ai_context,
                    :internal_notes, :external_id, 'aco',
                    :now, :now
                )
            """),
            {
                "org_id": self.org_id,
                "pa_id": pa_user_id,
                "loan_id": loan_id,
                "title": title,
                "description": f"ACO-scheduled review call for loan {loan_id}",
                "start": start_time,
                "end": end_time,
                "duration": duration_minutes,
                "attendee_name": borrower_name,
                "attendee_phone": borrower_phone,
                "attendee_email": borrower_email,
                "ai_context": '{"source": "aco_communication_orchestrator"}',
                "internal_notes": pre_call_brief or "",
                "external_id": calendar_event_id,
                "now": datetime.now(timezone.utc),
            },
        )

        # Update coordination with calendar reference
        coordination.calendar_event_id = calendar_event_id
        self.db.flush()

        # --- Send confirmations ---
        self._sms.review_id = review_id
        confirmation_results = await self._sms.send_appointment_confirmation(
            loan_id=loan_id,
            borrower_phone=borrower_phone,
            borrower_name=borrower_name,
            borrower_email=borrower_email,
            pa_name=pa_name,
            booked_start=start_time,
            duration_minutes=duration_minutes,
            lo_name=lo_name,
            company_name=company_name,
        )

        # --- Notify PA ---
        if pa_email:
            await self._notify_pa(
                pa_email=pa_email,
                pa_name=pa_name,
                borrower_name=borrower_name,
                booked_start=start_time,
                duration_minutes=duration_minutes,
                pre_call_brief=pre_call_brief or "No brief available.",
                loan_id=loan_id,
            )

        logger.info(
            "Appointment booked: loan=%s pa=%s start=%s duration=%d coordination_id=%d",
            loan_id, pa_name, start_time.isoformat(), duration_minutes, coordination.id,
        )

        return {
            "coordination_id": coordination.id,
            "calendar_event_id": calendar_event_id,
            "booked_start": start_time.isoformat(),
            "booked_end": end_time.isoformat(),
            "duration_minutes": duration_minutes,
            "pa_user_id": pa_user_id,
            "pa_name": pa_name,
            "borrower_name": borrower_name,
            "confirmation_results": confirmation_results,
        }

    # ------------------------------------------------------------------
    # Pre-call brief generation
    # ------------------------------------------------------------------

    async def generate_pre_call_brief(self, review_id: int) -> str:
        """Generate a summary for the PA before the call.

        Includes: borrower name, loan purpose, outstanding items count by
        category, items already attempted via SMS, and complexity indicators.

        Args:
            review_id: ``ApplicationCompletenessReview.id`` to summarize.

        Returns:
            Plain-text brief string suitable for display in the PA's
            calendar event or dashboard.
        """
        from database.models.app_completion import ApplicationCompletenessReview

        review = self.db.query(ApplicationCompletenessReview).filter(
            ApplicationCompletenessReview.id == review_id,
        ).first()

        if not review:
            return f"[Review {review_id} not found]"

        # Load borrower and loan info
        loan_info = self.db.execute(
            text("""
                SELECT l.loan_number, l.borrower_name, l.loan_type,
                       l.amount, l.stage, l.property_address
                FROM loans l WHERE l.id = :loan_id
            """),
            {"loan_id": review.loan_id},
        ).fetchone()

        # Load unresolved missing items
        items = self.db.query(MissingItem).filter(
            MissingItem.review_id == review_id,
            MissingItem.status.notin_([
                MissingItemStatus.RESOLVED.value,
                MissingItemStatus.CANCELLED.value,
            ]),
        ).all()

        # Categorize items
        by_type: Dict[str, list] = {}
        attempted_sms = 0
        for item in items:
            cat = item.item_type or "UNKNOWN"
            by_type.setdefault(cat, []).append(item)
            if item.status == MissingItemStatus.SENT_TO_BORROWER.value:
                attempted_sms += 1

        # Build brief
        sections = []
        sections.append("=" * 50)
        sections.append("PRE-CALL BRIEF")
        sections.append("=" * 50)

        if loan_info:
            sections.append(f"Borrower: {loan_info[1] or 'N/A'}")
            sections.append(f"Loan: {loan_info[0] or 'N/A'} | Type: {loan_info[2] or 'N/A'}")
            sections.append(f"Amount: ${float(loan_info[3] or 0):,.2f}")
            sections.append(f"Stage: {loan_info[4] or 'N/A'}")
            if loan_info[5]:
                sections.append(f"Property: {loan_info[5]}")
        else:
            sections.append(f"Loan ID: {review.loan_id}")

        sections.append("")
        sections.append(f"Overall Score: {review.overall_score or 'N/A'}/100")
        sections.append(f"Complexity: {review.complexity_level or 'N/A'} ({review.complexity_score or 0}/10)")
        sections.append("")

        sections.append(f"Outstanding Items: {len(items)} total")
        if attempted_sms > 0:
            sections.append(f"  - {attempted_sms} already asked via SMS (no response yet)")

        for item_type, type_items in by_type.items():
            sections.append(f"\n  [{item_type}] ({len(type_items)} items)")
            for item in type_items[:5]:  # Show first 5 per category
                severity_marker = "*" if item.severity in ("CRITICAL", "HIGH") else "-"
                question = (item.borrower_question or item.internal_note or item.field_path or "")[:80]
                status_label = item.status or ""
                sections.append(f"    {severity_marker} {question} [{status_label}]")
            if len(type_items) > 5:
                sections.append(f"    ... and {len(type_items) - 5} more")

        if review.review_summary:
            sections.append(f"\nAI Summary: {review.review_summary[:300]}")

        sections.append("")
        sections.append("=" * 50)

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _determine_duration(self, review_id: int | None) -> int:
        """Pick call duration based on review complexity score."""
        if not review_id:
            return _STANDARD_CALL_DURATION

        from database.models.app_completion import ApplicationCompletenessReview
        review = self.db.query(ApplicationCompletenessReview).filter(
            ApplicationCompletenessReview.id == review_id,
        ).first()

        if review and (review.complexity_score or 0) >= _COMPLEXITY_THRESHOLD:
            return _EXTENDED_CALL_DURATION

        return _STANDARD_CALL_DURATION

    async def _notify_pa(
        self,
        pa_email: str,
        pa_name: str,
        borrower_name: str,
        booked_start: datetime,
        duration_minutes: int,
        pre_call_brief: str,
        loan_id: str,
    ) -> None:
        """Send the PA an email notification with the pre-call brief."""
        display_dt = booked_start.strftime("%A, %B %d at %-I:%M %p")
        subject = f"ACO Review Call Scheduled \u2013 {borrower_name} \u2013 {display_dt}"

        body = (
            f"Hi {pa_name.split()[0] if pa_name else 'Team'},\n\n"
            f"An application review call has been scheduled:\n\n"
            f"  Borrower: {borrower_name}\n"
            f"  Loan: {loan_id}\n"
            f"  When: {display_dt}\n"
            f"  Duration: {duration_minutes} minutes\n\n"
            f"--- Pre-Call Brief ---\n\n"
            f"{pre_call_brief}\n\n"
            f"This call was scheduled by the Application Completion Orchestrator.\n"
        )

        try:
            from services.notification_service import notification_service

            def _blocking():
                return notification_service.send_email(
                    to_email=pa_email,
                    subject=subject,
                    body=body,
                )

            await asyncio.to_thread(_blocking)
            logger.info("PA notification sent to %s for loan %s", pa_email, loan_id)
        except Exception as e:
            logger.exception("Failed to notify PA %s for loan %s: %s", pa_email, loan_id, e)

    # ------------------------------------------------------------------
    # Appointment status updates
    # ------------------------------------------------------------------

    async def mark_confirmed(self, coordination_id: int, by: str = "borrower") -> dict:
        """Mark an appointment as confirmed by borrower or PA.

        Args:
            coordination_id: ``AppointmentCoordination.id``.
            by: ``"borrower"`` or ``"pa"``.

        Returns:
            Updated status dict.
        """
        coord = self.db.query(AppointmentCoordination).filter(
            AppointmentCoordination.id == coordination_id,
            AppointmentCoordination.organization_id == str(self.org_id),
        ).first()

        if not coord:
            return {"status": "error", "error": f"Coordination {coordination_id} not found"}

        if by == "borrower":
            coord.borrower_confirmed = True
        elif by == "pa":
            coord.pa_confirmed = True

        # Both confirmed -> update status
        if coord.borrower_confirmed and coord.pa_confirmed:
            coord.booking_status = BookingStatus.CONFIRMED.value

        self.db.flush()
        return {
            "coordination_id": coordination_id,
            "booking_status": coord.booking_status,
            "borrower_confirmed": coord.borrower_confirmed,
            "pa_confirmed": coord.pa_confirmed,
        }

    async def mark_completed(
        self,
        coordination_id: int,
        items_resolved: int = 0,
        call_notes: str | None = None,
    ) -> dict:
        """Mark an appointment as completed after the call.

        Args:
            coordination_id: ``AppointmentCoordination.id``.
            items_resolved: Number of missing items resolved during the call.
            call_notes: PA's post-call notes.

        Returns:
            Updated coordination summary.
        """
        coord = self.db.query(AppointmentCoordination).filter(
            AppointmentCoordination.id == coordination_id,
            AppointmentCoordination.organization_id == str(self.org_id),
        ).first()

        if not coord:
            return {"status": "error", "error": f"Coordination {coordination_id} not found"}

        coord.booking_status = BookingStatus.COMPLETED.value
        coord.completed_at = datetime.now(timezone.utc)
        coord.items_resolved_in_call = items_resolved
        if call_notes:
            coord.call_notes = call_notes

        self.db.flush()

        logger.info(
            "Appointment completed: coordination_id=%d items_resolved=%d",
            coordination_id, items_resolved,
        )
        return {
            "coordination_id": coordination_id,
            "booking_status": BookingStatus.COMPLETED.value,
            "items_resolved_in_call": items_resolved,
            "completed_at": coord.completed_at.isoformat(),
        }

    async def cancel_appointment(
        self,
        coordination_id: int,
        reason: str = "cancelled_by_system",
    ) -> dict:
        """Cancel an appointment and update the scheduler calendar.

        Args:
            coordination_id: ``AppointmentCoordination.id``.
            reason: Cancellation reason.

        Returns:
            Updated status dict.
        """
        coord = self.db.query(AppointmentCoordination).filter(
            AppointmentCoordination.id == coordination_id,
            AppointmentCoordination.organization_id == str(self.org_id),
        ).first()

        if not coord:
            return {"status": "error", "error": f"Coordination {coordination_id} not found"}

        coord.booking_status = BookingStatus.CANCELLED.value
        coord.cancelled_at = datetime.now(timezone.utc)
        coord.cancel_reason = reason

        # Also cancel the scheduler appointment
        if coord.calendar_event_id:
            self.db.execute(
                text("""
                    UPDATE scheduler_appointments
                    SET status = 'cancelled',
                        cancelled_at = :now,
                        cancellation_reason = :reason,
                        updated_at = :now
                    WHERE external_id = :event_id
                      AND organization_id = :org_id
                """),
                {
                    "event_id": coord.calendar_event_id,
                    "org_id": self.org_id,
                    "reason": reason,
                    "now": datetime.now(timezone.utc),
                },
            )

        self.db.flush()

        logger.info(
            "Appointment cancelled: coordination_id=%d reason=%s",
            coordination_id, reason,
        )
        return {
            "coordination_id": coordination_id,
            "booking_status": BookingStatus.CANCELLED.value,
            "cancel_reason": reason,
        }

    # ------------------------------------------------------------------
    # Reminder scheduling helpers
    # ------------------------------------------------------------------

    async def send_appointment_reminders(
        self,
        coordination_id: int,
    ) -> list[dict]:
        """Check if reminders are due for an appointment and send them.

        Called by a cron task.  Sends 24-hour and 1-hour reminders based
        on the ``booked_start`` time.

        Returns:
            List of reminder delivery results (may be empty if no reminders due).
        """
        coord = self.db.query(AppointmentCoordination).filter(
            AppointmentCoordination.id == coordination_id,
            AppointmentCoordination.organization_id == str(self.org_id),
            AppointmentCoordination.booking_status.in_([
                BookingStatus.BOOKED.value,
                BookingStatus.CONFIRMED.value,
            ]),
        ).first()

        if not coord or not coord.booked_start:
            return []

        now = datetime.now(timezone.utc)
        results: list[dict] = []

        # Ensure booked_start is tz-aware
        booked = coord.booked_start
        if booked.tzinfo is None:
            booked = booked.replace(tzinfo=timezone.utc)

        time_until = booked - now
        display_time = booked.strftime("%-I:%M %p")

        # Look up PA name
        pa_name = "our team"
        if coord.assigned_pa_user_id:
            pa_row = self.db.execute(
                text("SELECT first_name, last_name FROM users WHERE id = :pa_id"),
                {"pa_id": coord.assigned_pa_user_id},
            ).fetchone()
            if pa_row:
                pa_name = f"{pa_row[0] or ''} {pa_row[1] or ''}".strip()

        # 24-hour reminder: send between 24h and 23h before
        if timedelta(hours=23) < time_until <= timedelta(hours=24):
            r = await self._sms.send_follow_up_reminder(
                loan_id=coord.loan_id,
                borrower_phone=coord.borrower_phone or "",
                reminder_type="appointment_24h",
                context={"time": display_time, "pa_name": pa_name},
            )
            results.append(r)

        # 1-hour reminder: send between 1h and 50min before
        if timedelta(minutes=50) < time_until <= timedelta(hours=1):
            meeting_link_text = (
                f"Join here: {coord.meeting_link}" if coord.meeting_link else ""
            )
            r = await self._sms.send_follow_up_reminder(
                loan_id=coord.loan_id,
                borrower_phone=coord.borrower_phone or "",
                reminder_type="appointment_1h",
                context={
                    "time": display_time,
                    "pa_name": pa_name,
                    "meeting_link_text": meeting_link_text,
                },
            )
            results.append(r)

        return results
