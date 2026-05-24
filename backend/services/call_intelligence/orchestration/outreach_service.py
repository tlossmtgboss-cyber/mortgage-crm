"""
Outreach Service

Sends automated communications (email, SMS, etc.) based on
call intelligence results and orchestration decisions.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class OutreachChannel(str, Enum):
    """Communication channels."""
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    IN_APP = "in_app"


class OutreachType(str, Enum):
    """Types of outreach communications."""
    WELCOME = "welcome"
    DOCUMENT_REQUEST = "document_request"
    PREQUAL_RESULTS = "prequal_results"
    FOLLOWUP = "followup"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder"
    STATUS_UPDATE = "status_update"
    CUSTOM = "custom"


class OutreachStatus(str, Enum):
    """Status of outreach attempt."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    OPENED = "opened"
    CLICKED = "clicked"


@dataclass
class OutreachResult:
    """Result of an outreach attempt."""
    success: bool
    outreach_id: Optional[str] = None
    channel: Optional[OutreachChannel] = None
    outreach_type: Optional[OutreachType] = None
    status: OutreachStatus = OutreachStatus.PENDING
    sent_at: Optional[datetime] = None
    recipient: str = ""
    subject: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "outreach_id": self.outreach_id,
            "channel": self.channel.value if self.channel else None,
            "outreach_type": self.outreach_type.value if self.outreach_type else None,
            "status": self.status.value,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "recipient": self.recipient,
            "subject": self.subject,
            "errors": self.errors,
        }


@dataclass
class OutreachRequest:
    """Request to send an outreach communication."""
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_name: str = ""
    channel: OutreachChannel = OutreachChannel.EMAIL
    outreach_type: OutreachType = OutreachType.CUSTOM
    subject: str = ""
    body: str = ""
    template_id: Optional[str] = None
    template_data: Dict[str, Any] = field(default_factory=dict)
    scheduled_for: Optional[datetime] = None
    priority: str = "normal"  # low, normal, high

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipient_email": self.recipient_email,
            "recipient_phone": self.recipient_phone,
            "recipient_name": self.recipient_name,
            "channel": self.channel.value,
            "outreach_type": self.outreach_type.value,
            "subject": self.subject,
            "body": self.body,
            "template_id": self.template_id,
            "template_data": self.template_data,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "priority": self.priority,
        }


# =============================================================================
# Email Templates
# =============================================================================

EMAIL_TEMPLATES = {
    "welcome": {
        "subject": "Welcome to {company_name} - Your Mortgage Journey Starts Here",
        "body": """Hi {first_name},

Thank you for speaking with us about your mortgage needs. We're excited to help you with your {loan_purpose} goals.

Based on our conversation, here's a quick summary:
- Loan Purpose: {loan_purpose}
- Estimated Amount: ${estimated_amount:,.0f}
- Target Timeline: {target_timeline}

Your next steps:
{next_steps}

If you have any questions, please don't hesitate to reach out.

Best regards,
{lo_name}
{company_name}
""",
    },
    "document_request": {
        "subject": "Documents Needed for Your Mortgage Application",
        "body": """Hi {first_name},

To move forward with your mortgage application, we'll need the following documents:

Required Documents:
{required_documents}

You can securely upload your documents through our portal at: {upload_link}

Please try to submit these within the next {deadline_days} days to keep your application on track.

If you have any questions about what's needed, just reply to this email.

Best regards,
{lo_name}
{company_name}
""",
    },
    "prequal_results": {
        "subject": "Your Pre-Qualification Results Are Ready",
        "body": """Hi {first_name},

Great news! Based on the information you provided, here are your pre-qualification results:

Qualification Status: {qualification_status}
Maximum Purchase Price: ${max_purchase_price:,.0f}
Estimated Monthly Payment: ${monthly_payment:,.0f}
Estimated Rate: {estimated_rate}%

Loan Programs You Qualify For:
{qualified_programs}

{recommendations}

Ready to take the next step? {next_step_cta}

Best regards,
{lo_name}
{company_name}
""",
    },
    "appointment_confirmation": {
        "subject": "Appointment Confirmed: {appointment_type} on {appointment_date}",
        "body": """Hi {first_name},

Your appointment has been confirmed:

Date: {appointment_date}
Time: {appointment_time}
Type: {appointment_type}
{meeting_link_section}

What to prepare:
{preparation_items}

Need to reschedule? Click here: {reschedule_link}

We look forward to speaking with you!

Best regards,
{lo_name}
{company_name}
""",
    },
    "followup": {
        "subject": "Following Up on Your Mortgage Inquiry",
        "body": """Hi {first_name},

I wanted to follow up on our recent conversation about your {loan_purpose}.

{personalized_message}

Is there anything I can help clarify or any questions you have?

Best regards,
{lo_name}
{company_name}
""",
    },
}

SMS_TEMPLATES = {
    "welcome": "Hi {first_name}, thanks for speaking with {company_name} about your mortgage! We'll be in touch soon with next steps.",
    "document_reminder": "Hi {first_name}, friendly reminder: we're still waiting on some documents for your mortgage application. Check your email or call us to discuss.",
    "appointment_reminder": "Reminder: Your {appointment_type} is tomorrow at {appointment_time}. Reply YES to confirm or call us to reschedule.",
}


class OutreachService:
    """
    Manages automated outreach communications.

    Usage:
        service = OutreachService(email_client, sms_client)

        # Send welcome email
        result = await service.send_welcome_email(
            lead_data=extracted_data,
            lo_name="John Smith",
            company_name="ABC Mortgage"
        )

        # Send document request
        result = await service.send_document_request(
            lead_data=extracted_data,
            required_documents=checklist.required_documents,
            deadline_days=5
        )
    """

    def __init__(self, email_client=None, sms_client=None):
        """
        Initialize outreach service.

        Args:
            email_client: Email sending client (optional for testing)
            sms_client: SMS sending client (optional for testing)
        """
        self.email_client = email_client
        self.sms_client = sms_client
        # Track sent messages for testing
        self._sent_messages: List[OutreachResult] = []

    async def send_welcome_email(
        self,
        extracted_data: Dict[str, Any],
        lo_name: str,
        company_name: str,
        next_steps: Optional[List[str]] = None,
    ) -> OutreachResult:
        """
        Send welcome email after call.

        Args:
            extracted_data: Data extracted from the call
            lo_name: Loan officer name
            company_name: Company name
            next_steps: List of next steps for the borrower

        Returns:
            OutreachResult with send status
        """
        identity = extracted_data.get("identity", {})
        intent = extracted_data.get("intent", {})
        property_info = extracted_data.get("property", {})

        email = self._get_value(identity, "email")
        if not email:
            return OutreachResult(
                success=False,
                errors=["No email address available"],
            )

        first_name = self._get_value(identity, "first_name") or "there"
        loan_purpose = self._get_value(intent, "loan_purpose") or "home purchase"
        estimated_amount = self._get_numeric_value(property_info, "purchase_price") or 0
        target_timeline = self._get_value(intent, "target_timeline") or "As soon as possible"

        default_steps = [
            "Complete your full application online",
            "Gather required documents (we'll send a detailed list)",
            "Schedule a follow-up call to review your options",
        ]
        steps = next_steps or default_steps
        steps_text = "\n".join(f"• {step}" for step in steps)

        template = EMAIL_TEMPLATES["welcome"]
        subject = template["subject"].format(company_name=company_name)
        body = template["body"].format(
            first_name=first_name,
            loan_purpose=loan_purpose,
            estimated_amount=estimated_amount,
            target_timeline=target_timeline,
            next_steps=steps_text,
            lo_name=lo_name,
            company_name=company_name,
        )

        return await self._send_email(
            to_email=email,
            subject=subject,
            body=body,
            outreach_type=OutreachType.WELCOME,
        )

    async def send_document_request(
        self,
        extracted_data: Dict[str, Any],
        required_documents: List[Any],  # List[DocumentRequirement]
        lo_name: str,
        company_name: str,
        upload_link: str = "https://portal.example.com/upload",
        deadline_days: int = 5,
    ) -> OutreachResult:
        """
        Send document request email.

        Args:
            extracted_data: Data extracted from the call
            required_documents: List of required documents
            lo_name: Loan officer name
            company_name: Company name
            upload_link: Link to document upload portal
            deadline_days: Days until documents are due

        Returns:
            OutreachResult with send status
        """
        identity = extracted_data.get("identity", {})

        email = self._get_value(identity, "email")
        if not email:
            return OutreachResult(
                success=False,
                errors=["No email address available"],
            )

        first_name = self._get_value(identity, "first_name") or "there"

        # Format document list
        docs_text = ""
        for i, doc in enumerate(required_documents, 1):
            if hasattr(doc, "description"):
                docs_text += f"{i}. {doc.description}\n"
            elif isinstance(doc, dict):
                docs_text += f"{i}. {doc.get('description', doc.get('document_type', 'Document'))}\n"
            else:
                docs_text += f"{i}. {str(doc)}\n"

        template = EMAIL_TEMPLATES["document_request"]
        subject = template["subject"]
        body = template["body"].format(
            first_name=first_name,
            required_documents=docs_text,
            upload_link=upload_link,
            deadline_days=deadline_days,
            lo_name=lo_name,
            company_name=company_name,
        )

        return await self._send_email(
            to_email=email,
            subject=subject,
            body=body,
            outreach_type=OutreachType.DOCUMENT_REQUEST,
        )

    async def send_prequal_results(
        self,
        extracted_data: Dict[str, Any],
        prequal_result: Dict[str, Any],
        lo_name: str,
        company_name: str,
    ) -> OutreachResult:
        """
        Send pre-qualification results email.

        Args:
            extracted_data: Data extracted from the call
            prequal_result: Pre-qualification calculation results
            lo_name: Loan officer name
            company_name: Company name

        Returns:
            OutreachResult with send status
        """
        identity = extracted_data.get("identity", {})

        email = self._get_value(identity, "email")
        if not email:
            return OutreachResult(
                success=False,
                errors=["No email address available"],
            )

        first_name = self._get_value(identity, "first_name") or "there"

        # Format qualified programs
        programs = prequal_result.get("qualified_programs", [])
        programs_text = "\n".join(f"• {p.upper()}" for p in programs) if programs else "Please contact us to discuss options"

        # Format recommendations
        recommendations = prequal_result.get("recommendations", [])
        rec_text = "Recommendations:\n" + "\n".join(f"• {r}" for r in recommendations) if recommendations else ""

        status = prequal_result.get("status", "unknown")
        status_display = {
            "qualified": "Congratulations! You're Pre-Qualified",
            "conditionally_qualified": "Conditionally Pre-Qualified",
            "not_qualified": "Additional Information Needed",
            "insufficient_data": "More Information Needed",
        }.get(status, status)

        template = EMAIL_TEMPLATES["prequal_results"]
        subject = template["subject"]
        body = template["body"].format(
            first_name=first_name,
            qualification_status=status_display,
            max_purchase_price=prequal_result.get("max_purchase_price", 0),
            monthly_payment=prequal_result.get("estimated_monthly_payment", 0),
            estimated_rate=prequal_result.get("estimated_rate", 0),
            qualified_programs=programs_text,
            recommendations=rec_text,
            next_step_cta="Schedule a call to discuss your options.",
            lo_name=lo_name,
            company_name=company_name,
        )

        return await self._send_email(
            to_email=email,
            subject=subject,
            body=body,
            outreach_type=OutreachType.PREQUAL_RESULTS,
        )

    async def send_appointment_confirmation(
        self,
        extracted_data: Dict[str, Any],
        appointment_data: Dict[str, Any],
        lo_name: str,
        company_name: str,
    ) -> OutreachResult:
        """
        Send appointment confirmation email.

        Args:
            extracted_data: Data extracted from the call
            appointment_data: Appointment details
            lo_name: Loan officer name
            company_name: Company name

        Returns:
            OutreachResult with send status
        """
        identity = extracted_data.get("identity", {})

        email = self._get_value(identity, "email")
        if not email:
            return OutreachResult(
                success=False,
                errors=["No email address available"],
            )

        first_name = self._get_value(identity, "first_name") or "there"

        appointment_date = appointment_data.get("date", "TBD")
        appointment_time = appointment_data.get("time", "TBD")
        appointment_type = appointment_data.get("type", "Follow-up Call")
        meeting_link = appointment_data.get("meeting_link")
        reschedule_link = appointment_data.get("reschedule_link", "#")

        meeting_link_section = f"\nMeeting Link: {meeting_link}" if meeting_link else ""

        # Default preparation items
        prep_items = appointment_data.get("preparation_items", [
            "Have your ID ready for verification",
            "Prepare any questions you have",
            "Have recent pay stubs and bank statements accessible",
        ])
        prep_text = "\n".join(f"• {item}" for item in prep_items)

        template = EMAIL_TEMPLATES["appointment_confirmation"]
        subject = template["subject"].format(
            appointment_type=appointment_type,
            appointment_date=appointment_date,
        )
        body = template["body"].format(
            first_name=first_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            appointment_type=appointment_type,
            meeting_link_section=meeting_link_section,
            preparation_items=prep_text,
            reschedule_link=reschedule_link,
            lo_name=lo_name,
            company_name=company_name,
        )

        return await self._send_email(
            to_email=email,
            subject=subject,
            body=body,
            outreach_type=OutreachType.APPOINTMENT_CONFIRMATION,
        )

    async def send_sms(
        self,
        extracted_data: Dict[str, Any],
        message: str,
        outreach_type: OutreachType = OutreachType.CUSTOM,
    ) -> OutreachResult:
        """
        Send SMS message.

        Args:
            extracted_data: Data extracted from the call
            message: SMS message text
            outreach_type: Type of outreach

        Returns:
            OutreachResult with send status
        """
        identity = extracted_data.get("identity", {})
        phone = self._get_value(identity, "phone")

        if not phone:
            return OutreachResult(
                success=False,
                errors=["No phone number available"],
            )

        return await self._send_sms(
            to_phone=phone,
            message=message,
            outreach_type=outreach_type,
        )

    async def send_custom_email(
        self,
        request: OutreachRequest,
    ) -> OutreachResult:
        """
        Send a custom email.

        Args:
            request: OutreachRequest with email details

        Returns:
            OutreachResult with send status
        """
        if not request.recipient_email:
            return OutreachResult(
                success=False,
                errors=["No recipient email provided"],
            )

        return await self._send_email(
            to_email=request.recipient_email,
            subject=request.subject,
            body=request.body,
            outreach_type=request.outreach_type,
        )

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        outreach_type: OutreachType,
    ) -> OutreachResult:
        """Internal email sending."""
        outreach_id = str(uuid.uuid4())[:8].upper()

        result = OutreachResult(
            success=True,
            outreach_id=outreach_id,
            channel=OutreachChannel.EMAIL,
            outreach_type=outreach_type,
            status=OutreachStatus.SENT,
            sent_at=datetime.now(timezone.utc),
            recipient=to_email,
            subject=subject,
        )

        if self.email_client:
            try:
                await self.email_client.send(
                    to=to_email,
                    subject=subject,
                    body=body,
                )
                result.status = OutreachStatus.DELIVERED
            except Exception as e:
                result.success = False
                result.status = OutreachStatus.FAILED
                result.errors.append(str(e))
        else:
            # Testing mode - just log
            logger.info(f"[TEST] Email to {to_email}: {subject}")

        self._sent_messages.append(result)
        return result

    async def _send_sms(
        self,
        to_phone: str,
        message: str,
        outreach_type: OutreachType,
    ) -> OutreachResult:
        """Internal SMS sending."""
        outreach_id = str(uuid.uuid4())[:8].upper()

        result = OutreachResult(
            success=True,
            outreach_id=outreach_id,
            channel=OutreachChannel.SMS,
            outreach_type=outreach_type,
            status=OutreachStatus.SENT,
            sent_at=datetime.now(timezone.utc),
            recipient=to_phone,
            subject=message[:50] + "..." if len(message) > 50 else message,
        )

        if self.sms_client:
            try:
                await self.sms_client.send(
                    to=to_phone,
                    message=message,
                )
                result.status = OutreachStatus.DELIVERED
            except Exception as e:
                result.success = False
                result.status = OutreachStatus.FAILED
                result.errors.append(str(e))
        else:
            # Testing mode - just log
            logger.info(f"[TEST] SMS to {to_phone}: {message}")

        self._sent_messages.append(result)
        return result

    def _get_value(self, data: Dict, field: str) -> Optional[str]:
        """Get string value from extraction dict."""
        if not data:
            return None

        value = data.get(field)
        if isinstance(value, dict):
            return value.get("value")
        return value

    def _get_numeric_value(self, data: Dict, field: str) -> Optional[float]:
        """Get numeric value from extraction dict."""
        value = self._get_value(data, field)
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_sent_messages(self) -> List[OutreachResult]:
        """Get list of sent messages (for testing)."""
        return self._sent_messages


# =============================================================================
# Factory
# =============================================================================

def create_outreach_service(
    email_client=None,
    sms_client=None,
) -> OutreachService:
    """Create outreach service instance."""
    return OutreachService(email_client, sms_client)
