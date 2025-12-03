"""
Perennia AI - Email Intelligence Tools
======================================
Tools for the Email Intelligence Agent handling email analysis and automation.
8 tools for email parsing, threading, templates, and engagement tracking.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import re

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
)


# =============================================================================
# Email Intelligence Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="parse_email",
    description="Parse email content to extract intent, entities, and sentiment",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "subject": "Email subject",
        "body": "Email body",
        "from_email": "Sender email",
        "attachments": "List of attachment names",
    },
)
def parse_email(
    subject: str,
    body: str,
    from_email: str,
    attachments: Optional[List[str]] = None,
) -> ToolResult:
    """Parse email for intent and entities."""
    text = f"{subject} {body}".lower()

    # Intent detection
    intents = []
    intent_patterns = {
        "rate_inquiry": ["rate", "interest rate", "apr", "points", "current rate"],
        "status_check": ["status", "update", "where are we", "how long", "when will"],
        "document_submission": ["attached", "sending", "here are", "documents", "upload"],
        "question": ["?", "question", "wondering", "curious", "can you explain"],
        "complaint": ["frustrated", "upset", "disappointed", "problem", "issue"],
        "schedule_request": ["schedule", "meet", "call me", "available", "appointment"],
        "urgent": ["urgent", "asap", "immediately", "rush", "time sensitive"],
    }

    for intent, keywords in intent_patterns.items():
        if any(kw in text for kw in keywords):
            intents.append(intent)

    # Entity extraction
    entities = {
        "dates": re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text),
        "amounts": re.findall(r'\$[\d,]+(?:\.\d{2})?', text),
        "phone_numbers": re.findall(r'(?:\+1)?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text),
        "loan_numbers": re.findall(r'(?:loan|file|case)[\s#:]*([A-Z0-9-]+)', text, re.IGNORECASE),
    }

    # Sentiment analysis
    positive_words = ["thank", "great", "happy", "appreciate", "excellent"]
    negative_words = ["frustrated", "upset", "problem", "issue", "disappointed"]
    pos_count = sum(1 for w in positive_words if w in text)
    neg_count = sum(1 for w in negative_words if w in text)

    if neg_count > pos_count:
        sentiment = "negative"
    elif pos_count > neg_count:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    # Urgency detection
    urgency = "high" if "urgent" in intents or "complaint" in intents else "normal"

    parsed = {
        "from_email": from_email,
        "subject": subject,
        "intents": intents,
        "primary_intent": intents[0] if intents else "general",
        "entities": entities,
        "sentiment": sentiment,
        "urgency": urgency,
        "has_attachments": bool(attachments),
        "attachment_count": len(attachments) if attachments else 0,
        "attachment_names": attachments or [],
        "requires_response": len(intents) > 0 and "document_submission" not in intents,
        "auto_reply_eligible": "document_submission" in intents or sentiment == "positive",
    }

    return ToolResult.success(
        data=parsed,
        message=f"Intent: {parsed['primary_intent']}, Sentiment: {sentiment}",
    )


@mortgage_tool(
    name="get_email_thread",
    description="Get email thread history with a contact",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "limit": "Max emails to retrieve",
    },
)
def get_email_thread(
    contact_id: str,
    contact_type: str = "lead",
    limit: int = 20,
) -> ToolResult:
    """Get email thread with contact."""
    emails = execute_query("""
        SELECT
            id, direction, subject, body_preview,
            sent_at, read_at, replied_at, attachments
        FROM email_history
        WHERE contact_id = :contact_id AND contact_type = :contact_type
        ORDER BY sent_at DESC
        LIMIT :limit
    """, {"contact_id": contact_id, "contact_type": contact_type, "limit": limit})

    if not emails:
        emails = []

    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, email FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as name, borrower_email as email FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    thread = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": f"{contact.get('first_name', '')} {contact.get('last_name', contact.get('name', ''))}".strip() if contact else "Unknown",
        "contact_email": contact.get("email") if contact else None,
        "total_emails": len(emails),
        "emails": [
            {
                "id": e.get("id"),
                "direction": e.get("direction", "outbound"),
                "subject": e.get("subject"),
                "preview": e.get("body_preview", "")[:200],
                "sent_at": format_date(e.get("sent_at")),
                "read": e.get("read_at") is not None,
                "replied": e.get("replied_at") is not None,
                "has_attachments": bool(e.get("attachments")),
            }
            for e in emails
        ],
        "summary": {
            "inbound": len([e for e in emails if e.get("direction") == "inbound"]),
            "outbound": len([e for e in emails if e.get("direction") == "outbound"]),
            "unread": len([e for e in emails if not e.get("read_at")]),
        },
    }

    return ToolResult.success(
        data=thread,
        message=f"Thread: {len(emails)} emails",
    )


@mortgage_tool(
    name="draft_email_response",
    description="Draft email response based on context and templates",
    agent_roles=["email_intelligence"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "response_type": "Type: acknowledgment, status_update, document_request, follow_up",
        "original_subject": "Subject of original email",
        "context": "Additional context for response",
        "template_id": "Optional template ID to use",
    },
)
def draft_email_response(
    contact_id: str,
    contact_type: str = "lead",
    response_type: str = "acknowledgment",
    original_subject: Optional[str] = None,
    context: Optional[str] = None,
    template_id: Optional[str] = None,
) -> ToolResult:
    """Draft email response."""
    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, email, stage FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as first_name, borrower_email as email, stage FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    first_name = contact.get("first_name", "there") if contact else "there"
    stage = contact.get("stage", "processing") if contact else "processing"

    # Response templates
    templates = {
        "acknowledgment": {
            "subject": f"Re: {original_subject}" if original_subject else "Re: Your inquiry",
            "body": f"""Hi {first_name},

Thank you for your email. I've received your message and wanted to let you know I'm looking into this right away.

I'll get back to you with a detailed response within 24 hours.

Best regards""",
        },
        "status_update": {
            "subject": f"Re: {original_subject}" if original_subject else "Loan Status Update",
            "body": f"""Hi {first_name},

Thank you for checking in! I wanted to give you a quick update on your loan.

Your loan is currently in the {stage} stage. Everything is progressing well and on track.

If you have any questions, please don't hesitate to reach out.

Best regards""",
        },
        "document_request": {
            "subject": "Documents Needed for Your Loan",
            "body": f"""Hi {first_name},

I hope this email finds you well. To continue processing your loan, we need the following documents:

[List of documents needed]

Please upload these at your earliest convenience. Let me know if you have any questions.

Best regards""",
        },
        "follow_up": {
            "subject": f"Re: {original_subject}" if original_subject else "Following Up",
            "body": f"""Hi {first_name},

I wanted to follow up on our previous conversation. Have you had a chance to review the information I sent?

I'm here to help if you have any questions.

Best regards""",
        },
    }

    template = templates.get(response_type, templates["acknowledgment"])

    draft = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "to": contact.get("email") if contact else None,
        "subject": template["subject"],
        "body": template["body"],
        "response_type": response_type,
        "template_id": template_id,
        "context_used": context,
        "status": "draft",
        "created_at": datetime.now().isoformat(),
        "requires_review": True,
    }

    return ToolResult.success(
        data=draft,
        message=f"Draft created for {first_name}",
    )


@mortgage_tool(
    name="send_email",
    description="Send email to contact",
    agent_roles=["email_intelligence"],
    risk_level="HIGH",
    parameters={
        "to_email": "Recipient email",
        "subject": "Email subject",
        "body": "Email body",
        "contact_id": "Associated contact ID",
        "contact_type": "Type: lead, borrower",
        "cc": "CC recipients",
        "attachments": "Attachment file IDs",
    },
)
def send_email(
    to_email: str,
    subject: str,
    body: str,
    contact_id: Optional[str] = None,
    contact_type: str = "lead",
    cc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
) -> ToolResult:
    """Send email."""
    import uuid
    email_id = str(uuid.uuid4())[:8].upper()

    email_data = {
        "email_id": f"EMAIL-{email_id}",
        "to": to_email,
        "cc": cc or [],
        "subject": subject,
        "body": body,
        "contact_id": contact_id,
        "contact_type": contact_type,
        "attachments": attachments or [],
        "status": "queued",
        "queued_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=email_data,
        message=f"Email queued to {to_email}",
        requires_approval=True,
    )


@mortgage_tool(
    name="get_email_templates",
    description="Get available email templates",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "category": "Optional category filter",
        "search": "Optional search term",
    },
)
def get_email_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> ToolResult:
    """Get email templates."""
    templates = [
        {
            "id": "tpl_welcome",
            "name": "Welcome Email",
            "category": "onboarding",
            "subject": "Welcome to {company_name}!",
            "preview": "Thank you for choosing us for your home financing...",
            "variables": ["first_name", "company_name", "lo_name"],
        },
        {
            "id": "tpl_status_update",
            "name": "Loan Status Update",
            "category": "status",
            "subject": "Update on Your Loan Application",
            "preview": "I wanted to give you a quick update on your loan...",
            "variables": ["first_name", "stage", "next_steps"],
        },
        {
            "id": "tpl_doc_request",
            "name": "Document Request",
            "category": "documents",
            "subject": "Documents Needed for Your Loan",
            "preview": "To continue processing your loan, we need...",
            "variables": ["first_name", "document_list"],
        },
        {
            "id": "tpl_rate_update",
            "name": "Rate Update",
            "category": "rates",
            "subject": "Great News About Rates!",
            "preview": "I wanted to share some exciting news about rates...",
            "variables": ["first_name", "rate", "savings"],
        },
        {
            "id": "tpl_closing_prep",
            "name": "Closing Preparation",
            "category": "closing",
            "subject": "Preparing for Your Closing",
            "preview": "Congratulations! Your closing is coming up...",
            "variables": ["first_name", "closing_date", "amount_due"],
        },
    ]

    if category:
        templates = [t for t in templates if t["category"] == category]

    if search:
        search_lower = search.lower()
        templates = [t for t in templates if search_lower in t["name"].lower() or search_lower in t["preview"].lower()]

    return ToolResult.success(
        data={
            "templates": templates,
            "count": len(templates),
            "categories": ["onboarding", "status", "documents", "rates", "closing"],
        },
        message=f"Found {len(templates)} templates",
    )


@mortgage_tool(
    name="analyze_email_engagement",
    description="Analyze email engagement metrics",
    agent_roles=["email_intelligence", "team_coach"],
    risk_level="LOW",
    parameters={
        "lo_id": "Optional LO ID filter",
        "period": "Period: week, month, quarter",
        "campaign_id": "Optional campaign filter",
    },
)
def analyze_email_engagement(
    lo_id: Optional[str] = None,
    period: str = "month",
    campaign_id: Optional[str] = None,
) -> ToolResult:
    """Analyze email engagement."""
    # Calculate date range
    today = datetime.now().date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "quarter":
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=30)

    engagement = {
        "period": period,
        "date_range": {
            "start": start_date.isoformat(),
            "end": today.isoformat(),
        },
        "summary": {
            "emails_sent": 0,
            "delivered": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0,
            "bounced": 0,
        },
        "rates": {
            "delivery_rate": 0,
            "open_rate": 0,
            "click_rate": 0,
            "reply_rate": 0,
            "bounce_rate": 0,
        },
        "by_template": [],
        "by_day": [],
        "top_performing_subjects": [],
        "lo_id": lo_id,
        "campaign_id": campaign_id,
    }

    return ToolResult.success(
        data=engagement,
        message=f"Email engagement for {period}",
    )


@mortgage_tool(
    name="match_email_to_loan",
    description="Match incoming email to existing loan/lead record",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "from_email": "Sender email address",
        "subject": "Email subject",
        "body": "Email body for context matching",
    },
)
def match_email_to_loan(
    from_email: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Match email to loan/lead record."""
    # Try to find by email
    lead = execute_single(
        "SELECT id, first_name, last_name, email, stage FROM leads WHERE email = :email",
        {"email": from_email}
    )

    loan = execute_single(
        "SELECT id, loan_number, borrower_name, borrower_email, stage FROM loans WHERE borrower_email = :email OR co_borrower_email = :email",
        {"email": from_email}
    )

    # Try to extract loan number from subject/body
    text = f"{subject} {body}"
    loan_numbers = re.findall(r'(?:loan|file|case)[\s#:]*([A-Z0-9-]+)', text, re.IGNORECASE)

    if loan_numbers and not loan:
        loan = execute_single(
            "SELECT id, loan_number, borrower_name, borrower_email, stage FROM loans WHERE loan_number = :ln",
            {"ln": loan_numbers[0]}
        )

    match_result = {
        "from_email": from_email,
        "matched": lead is not None or loan is not None,
        "match_type": None,
        "lead": None,
        "loan": None,
        "confidence": "none",
    }

    if loan:
        match_result["match_type"] = "loan"
        match_result["loan"] = {
            "id": loan.get("id"),
            "loan_number": loan.get("loan_number"),
            "borrower_name": loan.get("borrower_name"),
            "stage": loan.get("stage"),
        }
        match_result["confidence"] = "high"
    elif lead:
        match_result["match_type"] = "lead"
        match_result["lead"] = {
            "id": lead.get("id"),
            "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            "stage": lead.get("stage"),
        }
        match_result["confidence"] = "high"

    return ToolResult.success(
        data=match_result,
        message=f"Match: {match_result['match_type'] or 'none'} ({match_result['confidence']})",
    )


@mortgage_tool(
    name="categorize_email_attachments",
    description="Categorize email attachments for document processing",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "attachments": "List of attachment info (name, size, mime_type)",
    },
)
def categorize_email_attachments(
    attachments: List[Dict[str, Any]],
) -> ToolResult:
    """Categorize email attachments."""
    # Document type patterns
    doc_patterns = {
        "income": ["paystub", "w2", "w-2", "tax return", "1099", "profit", "loss", "income"],
        "assets": ["bank statement", "investment", "401k", "ira", "brokerage"],
        "identity": ["driver", "license", "passport", "ssn", "social security"],
        "property": ["purchase", "contract", "appraisal", "title", "insurance", "hoa"],
        "credit": ["credit report", "explanation", "bankruptcy"],
    }

    categorized = []
    for attachment in attachments:
        name = attachment.get("name", "").lower()
        category = "other"
        confidence = "low"

        for doc_type, patterns in doc_patterns.items():
            if any(p in name for p in patterns):
                category = doc_type
                confidence = "high"
                break

        # Check file extension
        if name.endswith(".pdf"):
            if confidence == "low":
                confidence = "medium"
        elif name.endswith((".jpg", ".jpeg", ".png")):
            if "id" in name or "license" in name:
                category = "identity"
                confidence = "medium"

        categorized.append({
            "name": attachment.get("name"),
            "size": attachment.get("size"),
            "mime_type": attachment.get("mime_type"),
            "category": category,
            "confidence": confidence,
            "suggested_doc_type": f"{category}_document",
        })

    summary = {}
    for item in categorized:
        cat = item["category"]
        summary[cat] = summary.get(cat, 0) + 1

    return ToolResult.success(
        data={
            "attachments": categorized,
            "total": len(categorized),
            "by_category": summary,
            "auto_process_eligible": all(c["confidence"] == "high" for c in categorized),
        },
        message=f"Categorized {len(categorized)} attachments",
    )
