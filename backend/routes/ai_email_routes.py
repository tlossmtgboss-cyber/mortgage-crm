"""
AI Email Routes — compose, send, and manage outbound email from LO's Outlook address.

Endpoints:
    POST /api/v1/email/send          — Send email via Microsoft Graph (LO's OAuth)
    POST /api/v1/email/ai-compose    — AI-generated draft (Claude) for LO review
    POST /api/v1/email/send-template — Send from template library with variable substitution
    GET  /api/v1/email/templates     — List available email templates
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db import get_db
from services.email_tracking_service import (
    generate_tracking_id,
    inject_tracking,
    store_link_mappings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/email", tags=["AI Email"])

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SEND_TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------


class EmailSendRequest(BaseModel):
    to_email: EmailStr
    subject: str = Field(..., min_length=1, max_length=998)
    body_html: str = Field(..., min_length=1)
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    lead_id: Optional[int] = None


class EmailSendResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    tracking_id: Optional[str] = None
    error: Optional[str] = None


class AIComposeRequest(BaseModel):
    lead_id: int
    email_type: str = Field(
        ...,
        description="One of: rate_alert, nurture, appointment_reminder, "
                    "pre_approval_intro, referral_ask, custom",
    )
    custom_instructions: Optional[str] = None


class AIComposeResponse(BaseModel):
    subject: str
    body_html: str
    lead_id: int
    email_type: str


class TemplateSendRequest(BaseModel):
    lead_id: int
    template_key: str
    extra_variables: Optional[Dict[str, str]] = None


class TemplateSendResponse(BaseModel):
    success: bool
    tracking_id: Optional[str] = None
    subject: str
    to_email: str
    error: Optional[str] = None


class TemplateInfo(BaseModel):
    key: str
    name: str
    subject_template: str
    description: str
    variables: List[str]


# ---------------------------------------------------------------------------
# Email template library
# ---------------------------------------------------------------------------

EMAIL_TEMPLATES: Dict[str, dict] = {
    "welcome": {
        "name": "Welcome Email",
        "subject": "Welcome, {first_name} — Let's Get Started",
        "description": "Initial outreach for new leads",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>Thank you for reaching out! I'm {lo_name} with {company_name}, "
            "and I'd love to help you explore your mortgage options.</p>"
            "<p>Whether you're buying your first home or refinancing, I'm here to "
            "make the process smooth and stress-free. Here's what I can do for you:</p>"
            "<ul>"
            "<li>Compare loan programs tailored to your situation</li>"
            "<li>Lock in competitive rates</li>"
            "<li>Guide you through every step of the process</li>"
            "</ul>"
            "<p>Would you have 15 minutes this week for a quick call? I'd love to learn "
            "more about your goals.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "rate_environment": {
        "name": "Rate Environment Update",
        "subject": "What Today's Rates Mean for You, {first_name}",
        "description": "Market rate update and refinance/purchase nudge",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>I wanted to share a quick update on the current rate environment. "
            "Market conditions have shifted recently, and I want to make sure you have "
            "the most up-to-date information as you consider your options.</p>"
            "<p>Based on your interest in {loan_type}, now could be a strategic time to "
            "move forward. I can run a quick analysis showing exactly what your monthly "
            "payment might look like.</p>"
            "<p>Want me to put together some numbers for you? It only takes a few minutes.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "appt_reminder": {
        "name": "Appointment Reminder",
        "subject": "Reminder: Your Consultation Tomorrow, {first_name}",
        "description": "T-24h appointment reminder",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>Just a friendly reminder about your consultation tomorrow. "
            "I'm looking forward to speaking with you!</p>"
            "<p>To make the most of our time, here are a few things to have handy:</p>"
            "<ul>"
            "<li>Recent pay stubs or income documentation</li>"
            "<li>A general idea of your budget or purchase price range</li>"
            "<li>Any questions you'd like answered</li>"
            "</ul>"
            "<p>If you need to reschedule, just reply to this email and we'll find "
            "a better time.</p>"
            "<p>Talk soon,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "pre_approval_intro": {
        "name": "Pre-Approval Introduction",
        "subject": "Your Pre-Approval Options, {first_name}",
        "description": "Encourage new purchase leads to get pre-approved",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>Getting pre-approved is one of the smartest first steps in the "
            "home-buying process. It gives you a clear picture of your purchasing "
            "power and shows sellers you're a serious buyer.</p>"
            "<p>The process takes about 10 minutes, and I'll walk you through every "
            "step. Here's what you can expect:</p>"
            "<ul>"
            "<li>We'll review your financial picture together</li>"
            "<li>I'll identify the best loan programs for your situation</li>"
            "<li>You'll receive a pre-approval letter you can use with confidence</li>"
            "</ul>"
            "<p>Ready to get started? Reply to this email or give me a call anytime.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "referral_ask": {
        "name": "Referral Request",
        "subject": "Know Anyone Looking to Buy or Refi, {first_name}?",
        "description": "Post-close referral generation",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>I hope you're enjoying your home! It's been a pleasure working "
            "with you, and I'm glad everything came together.</p>"
            "<p>If you know anyone — friends, family, or colleagues — who might "
            "be thinking about buying a home or refinancing, I'd truly appreciate "
            "the introduction. A personal referral means the world to me.</p>"
            "<p>Thank you again for your trust. I'm always here if you need anything "
            "down the road.</p>"
            "<p>Warm regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "nurture": {
        "name": "Lead Nurture Check-In",
        "subject": "Still Thinking About Your Options, {first_name}?",
        "description": "Gentle check-in for leads in nurture stage",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>I just wanted to check in and see how things are going. Buying a home "
            "is a big decision, and there's no rush — I'm here whenever you're ready.</p>"
            "<p>In the meantime, if you have any questions about the process, rates, "
            "or loan programs, don't hesitate to reach out. I'm happy to help even if "
            "you're just exploring.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
    "rate_alert": {
        "name": "Rate Drop Alert",
        "subject": "Rates Dropped — Your Savings Estimate, {first_name}",
        "description": "Rate-triggered alert for refi candidates",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>Rates have moved recently, and I wanted to make sure you have the latest "
            "information. Based on current market conditions, now could be a good time to "
            "explore your refinancing options.</p>"
            "<p>I can run a quick analysis to show you potential monthly savings and how "
            "long it would take to break even. Interested?</p>"
            "<p>Just reply to this email or give me a call — it only takes a few minutes.</p>"
            "<p>Best regards,<br>{lo_name}<br>NMLS# {nmls}<br>{company_name}</p>"
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_microsoft_token(user_id: int, db: Session) -> str:
    """Retrieve and validate the Microsoft Graph access token for the given user.

    Uses the enterprise-grade validate_microsoft_token() from dre_helpers,
    which handles expiry checks, proactive refresh, and lightweight /me
    verification before returning a decrypted token.

    Raises HTTPException if the token is unavailable or invalid.
    """
    from database.models.microsoft import MicrosoftOAuthToken
    from services.dre_helpers import validate_microsoft_token

    oauth_record = db.query(MicrosoftOAuthToken).filter(
        MicrosoftOAuthToken.user_id == user_id,
    ).first()

    if not oauth_record:
        raise HTTPException(
            status_code=400,
            detail="Microsoft 365 not connected. Connect your Outlook email first.",
        )

    validation = await validate_microsoft_token(oauth_record, db)

    if not validation.get("valid"):
        needs_reauth = validation.get("needs_reauth", False)
        error_msg = validation.get("error", "Token validation failed")
        if needs_reauth:
            raise HTTPException(
                status_code=401,
                detail=f"Microsoft re-authentication required: {error_msg}",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft Graph token error: {error_msg}",
        )

    return validation["access_token"]


def _get_user_fields(user) -> dict:
    """Extract LO identity fields from the User object."""
    user_id = user.get("user_id") if isinstance(user, dict) else getattr(user, "id", None)
    org_id = user.get("organization_id") if isinstance(user, dict) else getattr(user, "organization_id", None)
    first = user.get("first_name", "") if isinstance(user, dict) else getattr(user, "first_name", "") or ""
    last = user.get("last_name", "") if isinstance(user, dict) else getattr(user, "last_name", "") or ""
    email = user.get("email", "") if isinstance(user, dict) else getattr(user, "email", "") or ""
    nmls = user.get("nmls_number", "") if isinstance(user, dict) else getattr(user, "nmls_number", "") or ""
    full_name = f"{first} {last}".strip() if first or last else ""

    return {
        "user_id": user_id,
        "organization_id": org_id,
        "first_name": first,
        "last_name": last,
        "full_name": full_name,
        "email": email,
        "nmls": nmls,
    }


def _get_org_company_name(db: Session, organization_id) -> str:
    """Look up the organization's company name (or name) for email signatures."""
    if not organization_id:
        return ""
    try:
        from database.models.core import Organization
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org:
            return org.company or org.name or ""
    except Exception as e:
        logger.debug(f"Could not fetch org company name: {e}")
    return ""


def _build_template_variables(lead, user_fields: dict, company_name: str) -> dict:
    """Build variable dict for template substitution."""
    return {
        "first_name": getattr(lead, "first_name", "") or lead.name.split()[0] if lead.name else "",
        "last_name": getattr(lead, "last_name", "") or "",
        "lo_name": user_fields["full_name"],
        "company_name": company_name,
        "nmls": user_fields["nmls"],
        "loan_type": getattr(lead, "loan_type", "") or getattr(lead, "loan_purpose", "") or "home loan",
        "property_address": getattr(lead, "property_address", "") or getattr(lead, "address", "") or "",
    }


def _render_template(template_str: str, variables: dict) -> str:
    """Replace {key} placeholders with values from variables dict."""
    result = template_str
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value or ""))
    return result


def _build_compliance_footer(lo_name: str, nmls: str, company_name: str) -> str:
    """Build CAN-SPAM compliant footer."""
    return (
        '<div style="margin-top:30px;padding-top:15px;border-top:1px solid #e0e0e0;'
        'font-size:11px;color:#888;line-height:1.6;">'
        f'<p>{company_name}{f" | NMLS# {nmls}" if nmls else ""}</p>'
        '<p>Equal Housing Lender | Equal Housing Opportunity</p>'
        '</div>'
    )


async def _send_via_graph(
    access_token: str,
    to_email: str,
    subject: str,
    body_html: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
) -> dict:
    """Send an email using Microsoft Graph /me/sendMail.

    Returns dict with 'success', 'error' keys.
    Graph returns 202 Accepted on success with empty body.
    """
    to_recipients = [{"emailAddress": {"address": to_email}}]
    cc_recipients = [{"emailAddress": {"address": addr}} for addr in (cc or [])]
    bcc_recipients = [{"emailAddress": {"address": addr}} for addr in (bcc or [])]

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html,
            },
            "toRecipients": to_recipients,
        },
        "saveToSentItems": True,
    }

    if cc_recipients:
        payload["message"]["ccRecipients"] = cc_recipients
    if bcc_recipients:
        payload["message"]["bccRecipients"] = bcc_recipients

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=GRAPH_SEND_TIMEOUT) as client:
        response = await client.post(
            f"{GRAPH_API_BASE}/me/sendMail",
            json=payload,
            headers=headers,
        )

    if response.status_code == 202:
        # Extract internet message ID if available from response headers
        message_id = response.headers.get("request-id")
        return {"success": True, "message_id": message_id}

    error_text = response.text[:500]
    logger.error(
        "Microsoft Graph sendMail failed: status=%d body=%s",
        response.status_code,
        error_text,
    )
    return {
        "success": False,
        "error": f"Graph API error ({response.status_code}): {error_text}",
    }


def _log_email_message(
    db: Session,
    organization_id,
    user_id: int,
    to_email: str,
    from_email: str,
    subject: str,
    body_html: str,
    lead_id: Optional[int] = None,
    tracking_id: Optional[str] = None,
    status: str = "sent",
):
    """Persist outbound email record in email_messages table."""
    try:
        from database.models.communication import EmailMessage as EmailMessageModel

        record = EmailMessageModel(
            organization_id=organization_id,
            user_id=user_id,
            lead_id=lead_id,
            to_email=to_email,
            from_email=from_email,
            subject=subject,
            html_body=body_html,
            direction="outbound",
            status=status,
            meta_data={"tracking_id": tracking_id} if tracking_id else None,
        )
        db.add(record)
        db.commit()
        return record.id
    except Exception as e:
        logger.exception("Failed to log email message: %s", e)
        db.rollback()
        return None


def _log_activity(
    db: Session,
    organization_id,
    user_id: int,
    lead_id: Optional[int],
    subject: str,
    email_type: str = "email",
):
    """Record an Activity entry for the email send."""
    if not lead_id:
        return
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        activity = Activity(
            organization_id=organization_id,
            user_id=user_id,
            lead_id=lead_id,
            type=ActivityType.EMAIL,
            content=f"Email sent: {subject} (type: {email_type})",
        )
        db.add(activity)
        db.commit()
    except Exception as e:
        logger.debug("Could not log email activity: %s", e)
        db.rollback()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/send", response_model=EmailSendResponse)
async def send_email(
    request: EmailSendRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send an email from the LO's Outlook address via Microsoft Graph.

    - Auto-injects tracking pixel and rewrites links for open/click tracking.
    - Records the email in email_messages and logs an Activity if lead_id is provided.
    """
    user_fields = _get_user_fields(current_user)
    user_id = user_fields["user_id"]
    org_id = user_fields["organization_id"]

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # 1. Get validated Microsoft Graph token
    access_token = await _get_microsoft_token(user_id, db)

    # 2. Inject tracking pixel and rewrite links
    tracking_id = generate_tracking_id()
    tracked_html, link_mappings = inject_tracking(request.body_html, tracking_id)
    if link_mappings:
        store_link_mappings(db, tracking_id, link_mappings)

    # 3. Send via Microsoft Graph
    result = await _send_via_graph(
        access_token=access_token,
        to_email=request.to_email,
        subject=request.subject,
        body_html=tracked_html,
        cc=request.cc,
        bcc=request.bcc,
    )

    if not result["success"]:
        logger.warning(
            "Email send failed for user=%s to=%s: %s",
            user_id,
            request.to_email,
            result.get("error"),
        )
        # Still log the attempt
        _log_email_message(
            db,
            organization_id=org_id,
            user_id=user_id,
            to_email=request.to_email,
            from_email=user_fields["email"],
            subject=request.subject,
            body_html=tracked_html,
            lead_id=request.lead_id,
            tracking_id=tracking_id,
            status="failed",
        )
        raise HTTPException(status_code=502, detail=result.get("error", "Email send failed"))

    # 4. Persist email record and activity
    _log_email_message(
        db,
        organization_id=org_id,
        user_id=user_id,
        to_email=request.to_email,
        from_email=user_fields["email"],
        subject=request.subject,
        body_html=tracked_html,
        lead_id=request.lead_id,
        tracking_id=tracking_id,
        status="sent",
    )
    _log_activity(db, org_id, user_id, request.lead_id, request.subject, email_type="manual")

    logger.info("Email sent successfully: user=%s to=%s subject=%s", user_id, request.to_email, request.subject)

    return EmailSendResponse(
        success=True,
        message_id=result.get("message_id"),
        tracking_id=tracking_id,
    )


@router.post("/ai-compose", response_model=AIComposeResponse)
async def ai_compose_email(
    request: AIComposeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """AI-generated email draft using Claude.

    Returns subject + body_html for LO review before sending.
    The body includes the LO's name, company, and NMLS# in the signature.
    """
    user_fields = _get_user_fields(current_user)
    user_id = user_fields["user_id"]
    org_id = user_fields["organization_id"]

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    valid_types = {"rate_alert", "nurture", "appointment_reminder", "pre_approval_intro", "referral_ask", "custom"}
    if request.email_type not in valid_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid email_type. Must be one of: {', '.join(sorted(valid_types))}",
        )

    # Load lead data (tenant-scoped)
    from database.models.lead_loan import Lead

    lead = db.query(Lead).filter(
        Lead.id == request.lead_id,
        Lead.organization_id == org_id,
    ).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    company_name = _get_org_company_name(db, org_id)

    # Build context for Claude
    lead_context = {
        "first_name": lead.first_name or (lead.name.split()[0] if lead.name else ""),
        "last_name": lead.last_name or "",
        "email": lead.email or "",
        "stage": lead.stage or "",
        "loan_type": lead.loan_type or lead.loan_purpose or "",
        "property_type": getattr(lead, "property_type", "") or "",
        "loan_amount": str(lead.loan_amount) if lead.loan_amount else "",
        "credit_score": str(lead.credit_score) if lead.credit_score else "",
        "source": lead.source or "",
        "city": getattr(lead, "city", "") or "",
        "state": getattr(lead, "state", "") or "",
    }

    lo_signature = f"{user_fields['full_name']}"
    if user_fields["nmls"]:
        lo_signature += f"\nNMLS# {user_fields['nmls']}"
    if company_name:
        lo_signature += f"\n{company_name}"

    email_type_descriptions = {
        "rate_alert": "A rate drop alert encouraging the borrower to explore refinancing or locking a rate.",
        "nurture": "A warm check-in email for a lead who hasn't engaged recently. Gentle, no pressure.",
        "appointment_reminder": "A reminder about an upcoming consultation or call. Friendly and preparatory.",
        "pre_approval_intro": "An introduction to the pre-approval process for a new purchase lead.",
        "referral_ask": "A post-close referral request to a past client. Warm and appreciative.",
        "custom": request.custom_instructions or "A professional mortgage-related outreach email.",
    }

    system_prompt = (
        f"You are a professional mortgage email writer for {company_name or 'a mortgage company'}. "
        f"Write emails on behalf of loan officer {user_fields['full_name']}.\n\n"
        "COMPLIANCE RULES (MUST FOLLOW):\n"
        "- Never promise or quote a specific interest rate unless referencing a locked rate\n"
        "- Include the loan officer's NMLS# in the signature\n"
        "- Include Equal Housing Lender mention\n"
        "- Never reference race, sex, religion, national origin, marital status, age, or disability (ECOA)\n"
        "- No kickback language or undisclosed referral arrangements (RESPA)\n"
        "- Professional, warm tone\n\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY a JSON object with exactly two keys:\n"
        '  {"subject": "...", "body_html": "..."}\n'
        "The body_html should use HTML tags (<p>, <ul>, <li>, <br>) for formatting.\n"
        "The body should be 80-150 words.\n"
        "End with a signature block containing the LO name, NMLS#, and company.\n"
        "Do NOT include any other text outside the JSON object."
    )

    user_prompt = (
        f"Email type: {request.email_type}\n"
        f"Purpose: {email_type_descriptions[request.email_type]}\n\n"
        f"Lead info:\n"
        f"  Name: {lead_context['first_name']} {lead_context['last_name']}\n"
        f"  Stage: {lead_context['stage']}\n"
        f"  Loan type: {lead_context['loan_type'] or 'Not specified'}\n"
        f"  Property type: {lead_context['property_type'] or 'Not specified'}\n"
        f"  Location: {lead_context['city']}{', ' + lead_context['state'] if lead_context['state'] else ''}\n"
        f"  Loan amount: {lead_context['loan_amount'] or 'Not specified'}\n\n"
        f"Loan officer signature:\n{lo_signature}\n"
    )

    if request.email_type == "custom" and request.custom_instructions:
        user_prompt += f"\nAdditional instructions: {request.custom_instructions}\n"

    # Call Claude
    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()

        # Parse the JSON response — handle potential markdown code fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        parsed = json.loads(raw_text)
        subject = parsed.get("subject", f"A message from {user_fields['full_name']}")
        body_html = parsed.get("body_html", "")

        if not body_html:
            raise ValueError("Empty body_html from AI response")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("AI compose response parse error: %s — raw: %s", e, raw_text[:300] if 'raw_text' in dir() else "N/A")
        # Fallback: use the raw text as body if JSON parsing fails
        subject = f"A message from {user_fields['full_name']}"
        body_html = (
            f"<p>Hi {lead_context['first_name']},</p>"
            f"<p>I wanted to reach out regarding your mortgage needs. "
            f"I'd love to help you find the best solution.</p>"
            f"<p>Please feel free to reply to this email or call me directly.</p>"
            f"<p>Best regards,<br>{user_fields['full_name']}"
            f"{'<br>NMLS# ' + user_fields['nmls'] if user_fields['nmls'] else ''}"
            f"{'<br>' + company_name if company_name else ''}</p>"
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="AI service (anthropic) not installed")
    except Exception as e:
        logger.exception("AI email composition failed: %s", e)
        raise HTTPException(status_code=500, detail="AI email composition failed")

    logger.info(
        "AI email composed: user=%s lead=%s type=%s",
        user_id,
        request.lead_id,
        request.email_type,
    )

    return AIComposeResponse(
        subject=subject,
        body_html=body_html,
        lead_id=request.lead_id,
        email_type=request.email_type,
    )


@router.post("/send-template", response_model=TemplateSendResponse)
async def send_template_email(
    request: TemplateSendRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send an email from the template library with variable substitution.

    Automatically injects tracking pixel and rewrites links.
    Sends via the LO's Microsoft Graph OAuth token.
    """
    user_fields = _get_user_fields(current_user)
    user_id = user_fields["user_id"]
    org_id = user_fields["organization_id"]

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Validate template
    template = EMAIL_TEMPLATES.get(request.template_key)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{request.template_key}' not found. "
                   f"Available: {', '.join(EMAIL_TEMPLATES.keys())}",
        )

    # Load lead (tenant-scoped)
    from database.models.lead_loan import Lead

    lead = db.query(Lead).filter(
        Lead.id == request.lead_id,
        Lead.organization_id == org_id,
    ).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.email:
        raise HTTPException(status_code=422, detail="Lead has no email address")

    # Build variables
    company_name = _get_org_company_name(db, org_id)
    variables = _build_template_variables(lead, user_fields, company_name)

    # Merge any extra variables from the request
    if request.extra_variables:
        variables.update(request.extra_variables)

    # Render subject and body
    subject = _render_template(template["subject"], variables)
    body_html = _render_template(template["body"], variables)

    # Add compliance footer
    footer = _build_compliance_footer(user_fields["full_name"], user_fields["nmls"], company_name)
    full_html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>'
        '<body style="font-family:Arial,Helvetica,sans-serif;max-width:600px;'
        'margin:0 auto;padding:20px;color:#333;font-size:15px;line-height:1.6;">'
        f'{body_html}{footer}</body></html>'
    )

    # Get Microsoft Graph token
    access_token = await _get_microsoft_token(user_id, db)

    # Inject tracking
    tracking_id = generate_tracking_id()
    tracked_html, link_mappings = inject_tracking(full_html, tracking_id)
    if link_mappings:
        store_link_mappings(db, tracking_id, link_mappings)

    # Send
    result = await _send_via_graph(
        access_token=access_token,
        to_email=lead.email,
        subject=subject,
        body_html=tracked_html,
    )

    status = "sent" if result["success"] else "failed"

    # Log email and activity
    _log_email_message(
        db,
        organization_id=org_id,
        user_id=user_id,
        to_email=lead.email,
        from_email=user_fields["email"],
        subject=subject,
        body_html=tracked_html,
        lead_id=request.lead_id,
        tracking_id=tracking_id,
        status=status,
    )

    if result["success"]:
        _log_activity(db, org_id, user_id, request.lead_id, subject, email_type=f"template:{request.template_key}")
        logger.info("Template email sent: user=%s lead=%s template=%s", user_id, request.lead_id, request.template_key)
    else:
        logger.warning(
            "Template email failed: user=%s lead=%s template=%s error=%s",
            user_id,
            request.lead_id,
            request.template_key,
            result.get("error"),
        )
        raise HTTPException(status_code=502, detail=result.get("error", "Email send failed"))

    return TemplateSendResponse(
        success=True,
        tracking_id=tracking_id,
        subject=subject,
        to_email=lead.email,
    )


@router.get("/templates", response_model=List[TemplateInfo])
async def list_email_templates(
    current_user=Depends(get_current_user),
):
    """List all available email templates with their metadata."""
    templates = []
    for key, tmpl in EMAIL_TEMPLATES.items():
        # Extract variable names from subject + body
        all_text = tmpl["subject"] + tmpl["body"]
        variable_names = sorted(set(re.findall(r"\{(\w+)\}", all_text)))

        templates.append(TemplateInfo(
            key=key,
            name=tmpl["name"],
            subject_template=tmpl["subject"],
            description=tmpl["description"],
            variables=variable_names,
        ))

    return templates


# ============================================================================
# AI Text Generation — lightweight endpoint for generating field content
# ============================================================================

class AIGenerateTextRequest(BaseModel):
    field_type: str = Field(..., description="Type of field (e.g., 'appointment_description', 'lead_notes')")
    context: Dict = Field(default_factory=dict, description="Contextual data for generation")
    current_value: Optional[str] = Field(None, description="Current value to improve/replace")


class AIGenerateTextResponse(BaseModel):
    text: str
    field_type: str


FIELD_PROMPTS = {
    "appointment_description": (
        "Write a brief, professional description for a mortgage appointment type. "
        "It should be 1-2 sentences that clearly explain what the meeting covers and "
        "who it's for. Use a warm, approachable tone suitable for borrowers."
    ),
    "lead_notes": (
        "Write a concise internal note for a mortgage lead based on the provided context. "
        "Keep it factual and useful for the loan officer."
    ),
    "task_description": (
        "Write a clear, actionable task description for a mortgage workflow step. "
        "Be specific about what needs to be done."
    ),
    "marketing_description": (
        "Write a compelling marketing description for the given context. "
        "Keep it professional, concise, and focused on value to the reader."
    ),
}


@router.post("/ai-generate-text", response_model=AIGenerateTextResponse)
async def ai_generate_text(
    request: AIGenerateTextRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate text content for a CRM field using AI."""
    field_prompt = FIELD_PROMPTS.get(request.field_type, FIELD_PROMPTS.get("marketing_description"))

    context_parts = []
    for key, val in request.context.items():
        if val:
            context_parts.append(f"{key}: {val}")
    context_str = "\n".join(context_parts) if context_parts else "No additional context provided."

    user_prompt = f"Context:\n{context_str}"
    if request.current_value:
        user_prompt += f"\n\nCurrent text (improve or replace):\n{request.current_value}"

    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system=f"{field_prompt}\nRespond with ONLY the generated text, no quotes or formatting.",
            messages=[{"role": "user", "content": user_prompt}],
        )

        generated = response.content[0].text.strip()
        generated = generated.strip('"\'')

        return AIGenerateTextResponse(text=generated, field_type=request.field_type)

    except ImportError:
        raise HTTPException(status_code=500, detail="AI service not installed")
    except Exception as e:
        logger.exception("AI text generation failed: %s", e)
        raise HTTPException(status_code=500, detail="AI text generation failed")
