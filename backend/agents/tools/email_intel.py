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
    description="Send email to contact via Microsoft Graph (if connected) or queue for approval",
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
        "user_id": "User ID sending the email",
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
    user_id: Optional[int] = None,
) -> ToolResult:
    """Send email via Microsoft Graph if user has integration, otherwise queue for approval."""
    import uuid
    import asyncio
    import httpx
    import os

    email_id = str(uuid.uuid4())[:8].upper()
    send_status = "queued"
    send_error = None

    # Try to send via Microsoft Graph if user_id provided
    if user_id:
        try:
            from database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Check for Microsoft OAuth token
                oauth = db.execute(text("""
                    SELECT access_token, refresh_token, token_expires_at
                    FROM microsoft_oauth_tokens
                    WHERE user_id = :user_id
                    AND access_token IS NOT NULL
                    AND sync_enabled = true
                    LIMIT 1
                """), {"user_id": user_id}).fetchone()

                if oauth and oauth.access_token:
                    # Decrypt token
                    from main import decrypt_token
                    access_token = decrypt_token(oauth.access_token)

                    # Check if token expired and needs refresh
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                        # Token expired - try to refresh
                        refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                        if refresh_token:
                            client_id = os.getenv("MICROSOFT_CLIENT_ID")
                            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

                            import requests
                            refresh_response = requests.post(token_url, data={
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                                "scope": "https://graph.microsoft.com/Mail.Send offline_access",
                            }, timeout=30)

                            if refresh_response.status_code == 200:
                                tokens = refresh_response.json()
                                access_token = tokens["access_token"]

                                # Update stored tokens
                                from main import encrypt_token
                                from datetime import timedelta
                                new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

                                db.execute(text("""
                                    UPDATE microsoft_oauth_tokens
                                    SET access_token = :access_token,
                                        refresh_token = :refresh_token,
                                        token_expires_at = :expires_at,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE user_id = :user_id
                                """), {
                                    "access_token": encrypt_token(access_token),
                                    "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                                    "expires_at": new_expires_at,
                                    "user_id": user_id,
                                })
                                db.commit()

                    # Prepare email payload for Microsoft Graph
                    message = {
                        "subject": subject,
                        "body": {
                            "contentType": "HTML",
                            "content": body,
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": to_email}}
                        ],
                    }

                    if cc:
                        message["ccRecipients"] = [
                            {"emailAddress": {"address": email}} for email in cc
                        ]

                    payload = {
                        "message": message,
                        "saveToSentItems": True,
                    }

                    # Send via Graph API
                    import requests
                    response = requests.post(
                        "https://graph.microsoft.com/v1.0/me/sendMail",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        timeout=30,
                    )

                    if response.status_code == 202:  # Accepted
                        send_status = "sent"
                    else:
                        error_data = response.json() if response.content else {}
                        send_error = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                        send_status = "failed"
                else:
                    # No Microsoft integration
                    send_status = "queued"

            finally:
                db.close()

        except Exception as e:
            send_error = str(e)
            send_status = "failed"

    email_data = {
        "email_id": f"EMAIL-{email_id}",
        "to": to_email,
        "cc": cc or [],
        "subject": subject,
        "body": body,
        "contact_id": contact_id,
        "contact_type": contact_type,
        "attachments": attachments or [],
        "status": send_status,
        "sent_at": datetime.now().isoformat() if send_status == "sent" else None,
        "error": send_error,
    }

    if send_status == "sent":
        return ToolResult.success(
            data=email_data,
            message=f"Email sent successfully to {to_email}",
            requires_approval=False,
        )
    elif send_status == "failed":
        return ToolResult.error(
            error=send_error or "Failed to send email",
            message=f"Email failed to send to {to_email}: {send_error}",
        )
    else:
        return ToolResult.success(
            data=email_data,
            message=f"Email queued to {to_email} (connect Microsoft 365 to send directly)",
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


@mortgage_tool(
    name="search_email_inbox",
    description="Search user's Microsoft 365 email inbox for messages. Use this when user wants to find specific emails "
                "by sender name, subject, or content. Returns matching emails from Microsoft Graph.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "search_query": "Search term (name, email, subject keywords)",
        "user_id": "User ID to search inbox for",
        "limit": "Maximum results (default 10)",
        "folder": "Folder to search: inbox, sentitems, all (default: all)",
    },
)
def search_email_inbox(
    search_query: str,
    user_id: Optional[int] = None,
    limit: int = 10,
    folder: str = "all",
) -> ToolResult:
    """
    Search user's Microsoft 365 inbox for emails matching the query.
    Uses Microsoft Graph API to search across inbox and sent items.
    """
    import os
    import requests

    if not user_id:
        return ToolResult.error(
            "Unable to search emails: user_id is required. Please ensure you're logged in.",
            ["No user context available for email search"]
        )

    if not search_query or len(search_query.strip()) < 2:
        return ToolResult.error(
            "Search query is too short. Please provide at least 2 characters.",
            ["Invalid search query"]
        )

    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Check for Microsoft OAuth token
            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
                AND sync_enabled = true
                LIMIT 1
            """), {"user_id": user_id}).fetchone()

            if not oauth or not oauth.access_token:
                return ToolResult.error(
                    "Microsoft 365 not connected. Please connect your email to search your inbox.",
                    ["No Microsoft OAuth token found for user"]
                )

            # Decrypt and possibly refresh token
            from main import decrypt_token, encrypt_token
            from datetime import timezone
            access_token = decrypt_token(oauth.access_token)

            now = datetime.now(timezone.utc)
            if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                # Token expired - try to refresh
                refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                if refresh_token:
                    client_id = os.getenv("MICROSOFT_CLIENT_ID")
                    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                    refresh_response = requests.post(token_url, data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
                    }, timeout=30)

                    if refresh_response.status_code == 200:
                        tokens = refresh_response.json()
                        access_token = tokens["access_token"]

                        # Update stored tokens
                        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
                        db.execute(text("""
                            UPDATE microsoft_oauth_tokens
                            SET access_token = :access_token,
                                refresh_token = :refresh_token,
                                token_expires_at = :expires_at,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id
                        """), {
                            "access_token": encrypt_token(access_token),
                            "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                            "expires_at": new_expires_at,
                            "user_id": user_id,
                        })
                        db.commit()
                    else:
                        return ToolResult.error(
                            "Microsoft 365 token expired. Please reconnect your email.",
                            ["Token refresh failed"]
                        )
                else:
                    return ToolResult.error(
                        "Microsoft 365 token expired. Please reconnect your email.",
                        ["No refresh token available"]
                    )

            # Build Microsoft Graph search query
            # Search in subject, from, body using $search
            search_filter = f'"{search_query}"'

            # Determine which folders to search
            if folder == "inbox":
                endpoint = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            elif folder == "sentitems":
                endpoint = "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
            else:
                # Search all mail
                endpoint = "https://graph.microsoft.com/v1.0/me/messages"

            params = {
                "$search": search_filter,
                "$top": limit,
                "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,hasAttachments,isRead",
                "$orderby": "receivedDateTime desc",
            }

            response = requests.get(
                endpoint,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return ToolResult.error(
                    f"Failed to search emails: {error_msg}",
                    [error_msg]
                )

            data = response.json()
            messages = data.get("value", [])

            # Format results
            emails = []
            for msg in messages:
                from_info = msg.get("from", {}).get("emailAddress", {})
                to_info = msg.get("toRecipients", [])

                emails.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject"),
                    "from_name": from_info.get("name"),
                    "from_email": from_info.get("address"),
                    "to": [r.get("emailAddress", {}).get("address") for r in to_info[:3]],
                    "received": msg.get("receivedDateTime"),
                    "preview": (msg.get("bodyPreview") or "")[:200],
                    "has_attachments": msg.get("hasAttachments", False),
                    "is_read": msg.get("isRead", False),
                })

            if not emails:
                return ToolResult.success(
                    data={
                        "emails": [],
                        "count": 0,
                        "search_query": search_query,
                        "message": f"No emails found matching '{search_query}'",
                    },
                    message=f"No emails found for '{search_query}'"
                )

            return ToolResult.success(
                data={
                    "emails": emails,
                    "count": len(emails),
                    "search_query": search_query,
                    "folder": folder,
                },
                message=f"Found {len(emails)} emails matching '{search_query}'"
            )

        finally:
            db.close()

    except Exception as e:
        return ToolResult.error(
            f"Failed to search emails: {str(e)}",
            [str(e)]
        )


@mortgage_tool(
    name="find_contact_email",
    description="Find a person's email address by searching CRM contacts, leads, team members, and users. "
                "Use this when user wants to email someone and you need their email address. "
                "Searches across: team members/users, leads, loan borrowers, and partners.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "name": "Name to search for (first name, last name, or full name)",
        "user_id": "Current user ID for context",
    },
)
def find_contact_email(
    name: str,
    user_id: Optional[int] = None,
) -> ToolResult:
    """
    Find a contact's email address by searching across all CRM data sources.
    Searches: users/team members, leads, loan borrowers, partners.
    """
    if not name or len(name.strip()) < 2:
        return ToolResult.error(
            "Please provide a name to search for (at least 2 characters).",
            ["Name too short"]
        )

    search_name = name.strip().lower()
    search_parts = search_name.split()

    results = []

    # Search users/team members first (most likely for internal emails)
    try:
        users = execute_query("""
            SELECT id, name, email, role, phone
            FROM users
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for u in users:
            if u.get("email"):
                results.append({
                    "type": "team_member",
                    "id": u.get("id"),
                    "name": u.get("name"),
                    "email": u.get("email"),
                    "role": u.get("role"),
                    "phone": u.get("phone"),
                    "match_score": 100 if search_name in (u.get("name") or "").lower() else 80,
                })
    except Exception as e:
        pass  # Continue searching other sources

    # Search leads
    try:
        leads = execute_query("""
            SELECT id, name, email, phone, stage
            FROM leads
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for l in leads:
            if l.get("email"):
                results.append({
                    "type": "lead",
                    "id": l.get("id"),
                    "name": l.get("name"),
                    "email": l.get("email"),
                    "phone": l.get("phone"),
                    "stage": l.get("stage"),
                    "match_score": 90 if search_name in (l.get("name") or "").lower() else 70,
                })
    except Exception as e:
        pass

    # Search loan borrowers
    try:
        loans = execute_query("""
            SELECT id, loan_number, borrower_name, borrower_email, borrower_phone, stage
            FROM loans
            WHERE LOWER(borrower_name) LIKE :search
            OR LOWER(borrower_email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for loan in loans:
            if loan.get("borrower_email"):
                results.append({
                    "type": "borrower",
                    "id": loan.get("id"),
                    "loan_number": loan.get("loan_number"),
                    "name": loan.get("borrower_name"),
                    "email": loan.get("borrower_email"),
                    "phone": loan.get("borrower_phone"),
                    "stage": loan.get("stage"),
                    "match_score": 85 if search_name in (loan.get("borrower_name") or "").lower() else 65,
                })
    except Exception as e:
        pass

    # Search partners/referral sources
    try:
        partners = execute_query("""
            SELECT id, name, email, phone, company, partner_type
            FROM partners
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            OR LOWER(company) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for p in partners:
            if p.get("email"):
                results.append({
                    "type": "partner",
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "email": p.get("email"),
                    "phone": p.get("phone"),
                    "company": p.get("company"),
                    "partner_type": p.get("partner_type"),
                    "match_score": 75,
                })
    except Exception as e:
        pass

    # Sort by match score
    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    # If no CRM results, search user's email inbox
    if not results and user_id:
        inbox_results = _search_inbox_for_contact(name, user_id)
        if inbox_results:
            results.extend(inbox_results)

    if not results:
        return ToolResult.success(
            data={
                "contacts": [],
                "count": 0,
                "search_name": name,
                "message": f"No contacts found matching '{name}' in CRM or email inbox. Try a different spelling.",
            },
            message=f"No contacts found for '{name}'"
        )

    # Return best match prominently
    best_match = results[0]

    return ToolResult.success(
        data={
            "contacts": results[:5],  # Top 5 matches
            "count": len(results),
            "search_name": name,
            "best_match": best_match,
        },
        message=f"Found {best_match['name']} ({best_match['email']}) - {best_match['type']}"
    )


def _search_inbox_for_contact(name: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Search user's Microsoft 365 inbox for emails from someone matching the name.
    Returns email addresses found in inbox that match the search name.
    """
    import os
    import requests
    from datetime import timezone

    results = []
    search_name = name.strip().lower()

    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Check for Microsoft OAuth token
            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
                AND sync_enabled = true
                LIMIT 1
            """), {"user_id": user_id}).fetchone()

            if not oauth or not oauth.access_token:
                return []

            # Decrypt and possibly refresh token
            from main import decrypt_token, encrypt_token
            access_token = decrypt_token(oauth.access_token)

            now = datetime.now(timezone.utc)
            if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                # Token expired - try to refresh
                refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                if refresh_token:
                    client_id = os.getenv("MICROSOFT_CLIENT_ID")
                    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                    refresh_response = requests.post(token_url, data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
                    }, timeout=30)

                    if refresh_response.status_code == 200:
                        tokens = refresh_response.json()
                        access_token = tokens["access_token"]

                        # Update stored tokens
                        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
                        db.execute(text("""
                            UPDATE microsoft_oauth_tokens
                            SET access_token = :access_token,
                                refresh_token = :refresh_token,
                                token_expires_at = :expires_at,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id
                        """), {
                            "access_token": encrypt_token(access_token),
                            "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                            "expires_at": new_expires_at,
                            "user_id": user_id,
                        })
                        db.commit()
                    else:
                        return []
                else:
                    return []

            # Search inbox for emails from this person
            # Use $search to find by name in from field
            search_filter = f'"{name}"'

            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/messages",
                params={
                    "$search": search_filter,
                    "$top": 50,
                    "$select": "from,receivedDateTime",
                    "$orderby": "receivedDateTime desc",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code != 200:
                return []

            messages = response.json().get("value", [])

            # Extract unique email addresses that match the name
            seen_emails = set()
            for msg in messages:
                from_info = msg.get("from", {}).get("emailAddress", {})
                from_name = from_info.get("name", "")
                from_email = from_info.get("address", "")

                if not from_email or from_email in seen_emails:
                    continue

                # Check if name matches
                if search_name in from_name.lower() or any(part in from_name.lower() for part in search_name.split()):
                    seen_emails.add(from_email)
                    results.append({
                        "type": "email_contact",
                        "name": from_name,
                        "email": from_email,
                        "source": "inbox",
                        "match_score": 70 if search_name in from_name.lower() else 50,
                    })

            # Also search sent items to find people user has emailed
            sent_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages",
                params={
                    "$search": search_filter,
                    "$top": 50,
                    "$select": "toRecipients,receivedDateTime",
                    "$orderby": "receivedDateTime desc",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if sent_response.status_code == 200:
                sent_messages = sent_response.json().get("value", [])

                for msg in sent_messages:
                    for recipient in msg.get("toRecipients", []):
                        to_info = recipient.get("emailAddress", {})
                        to_name = to_info.get("name", "")
                        to_email = to_info.get("address", "")

                        if not to_email or to_email in seen_emails:
                            continue

                        # Check if name matches
                        if search_name in to_name.lower() or any(part in to_name.lower() for part in search_name.split()):
                            seen_emails.add(to_email)
                            results.append({
                                "type": "email_contact",
                                "name": to_name,
                                "email": to_email,
                                "source": "sent_items",
                                "match_score": 70 if search_name in to_name.lower() else 50,
                            })

        finally:
            db.close()

    except Exception as e:
        # Log but don't fail - just return empty results
        pass

    return results


@mortgage_tool(
    name="get_emails_needing_response",
    description="Get emails from your inbox that need a response. Shows unread/pending emails requiring attention, "
                "prioritized by urgency. Use this when user asks about emails to respond to, urgent emails, or inbox status.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "days": "Number of days to look back (default 7)",
        "unread_only": "Only show unread/pending emails (default True)",
        "limit": "Maximum number of emails to return (default 20)",
        "user_id": "User ID to check inbox for",
    },
)
def get_emails_needing_response(
    user_id: Optional[int] = None,
    days: int = 7,
    unread_only: bool = True,
    limit: int = 20,
) -> ToolResult:
    """
    Get emails that need a response from the user's inbox.

    Checks the email_reconciliation_queue for pending emails that:
    - Are unread/pending status
    - Require action (not just informational)
    - Are prioritized by urgency and recency
    """
    from datetime import timezone

    if not user_id:
        return ToolResult.error(
            "Unable to check emails: user_id is required. Please ensure you're logged in.",
            ["No user context available for email lookup"]
        )

    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Build query for emails needing response
        status_filter = "AND e.status = 'pending'" if unread_only else ""

        query = f"""
            SELECT
                e.id,
                e.from_email,
                e.from_name,
                e.subject,
                e.body_preview,
                COALESCE(e.received_date, e.sent_date, e.created_at) as received_date,
                e.match_client_name,
                e.matched_loan_id,
                e.matched_lead_id,
                e.is_priority,
                e.status,
                e.disposition,
                e.has_attachments,
                e.match_confidence
            FROM email_reconciliation_queue e
            WHERE e.user_id = :user_id
            AND e.created_at >= :start_date
            {status_filter}
            ORDER BY
                e.is_priority DESC,
                COALESCE(e.received_date, e.sent_date, e.created_at) DESC
            LIMIT :limit
        """

        results = execute_query(query, {
            "user_id": user_id,
            "start_date": start_date,
            "limit": limit
        })

        if not results:
            return ToolResult.success(
                data={
                    "emails": [],
                    "total_count": 0,
                    "priority_count": 0,
                    "message": "No emails requiring response found. Your inbox is clear!",
                    "checked_days": days,
                },
                message="No emails need response - inbox is clear!"
            )

        # Format results
        emails = []
        priority_count = 0

        for row in results:
            is_priority = row.get("is_priority", False)
            if is_priority:
                priority_count += 1

            received_date = row.get("received_date")
            if received_date and hasattr(received_date, 'isoformat'):
                received_str = received_date.isoformat()
            else:
                received_str = str(received_date) if received_date else None

            emails.append({
                "email_id": row.get("id"),
                "from_email": row.get("from_email"),
                "from_name": row.get("from_name"),
                "subject": row.get("subject"),
                "preview": (row.get("body_preview") or "")[:200],
                "received_date": received_str,
                "client_name": row.get("match_client_name"),
                "loan_id": row.get("matched_loan_id"),
                "lead_id": row.get("matched_lead_id"),
                "is_priority": is_priority,
                "status": row.get("status"),
                "disposition": row.get("disposition"),
                "has_attachments": row.get("has_attachments", False),
            })

        # Build summary message
        if priority_count > 0:
            summary = f"{len(emails)} emails need response ({priority_count} priority)"
        else:
            summary = f"{len(emails)} emails need response"

        return ToolResult.success(
            data={
                "emails": emails,
                "total_count": len(emails),
                "priority_count": priority_count,
                "checked_days": days,
                "unread_only": unread_only,
            },
            message=summary
        )

    except Exception as e:
        return ToolResult.error(
            f"Failed to retrieve emails: {str(e)}",
            [str(e)]
        )
