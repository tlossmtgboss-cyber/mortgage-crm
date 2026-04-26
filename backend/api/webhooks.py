# backend/api/webhooks.py
"""
Webhook endpoints for external system integrations, cache invalidation,
and Microsoft Graph email notifications.
"""
import hmac
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Request, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _DEFAULT_ORGANIZER_EMAIL
except ImportError:
    _DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# =============================================================================
# MICROSOFT GRAPH EMAIL WEBHOOK MODELS
# =============================================================================

class GraphResourceData(BaseModel):
    """Resource data from Graph notification."""
    id: Optional[str] = None

    class Config:
        extra = "allow"  # Allow additional fields


class GraphNotificationValue(BaseModel):
    """Individual notification from Graph."""
    subscriptionId: Optional[str] = None
    subscriptionExpirationDateTime: Optional[str] = None
    changeType: Optional[str] = None
    resource: Optional[str] = None
    resourceData: Optional[GraphResourceData] = None
    clientState: Optional[str] = None
    tenantId: Optional[str] = None

    class Config:
        extra = "allow"


class GraphNotificationPayload(BaseModel):
    """Payload from Microsoft Graph webhook notification."""
    value: List[GraphNotificationValue] = []

    class Config:
        extra = "allow"


# =============================================================================
# MICROSOFT GRAPH EMAIL WEBHOOK ENDPOINTS
# =============================================================================

@router.post("/graph", response_class=PlainTextResponse)
async def handle_graph_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: Optional[str] = Query(None),
):
    """
    Microsoft Graph webhook endpoint for email notifications.

    This endpoint handles:
    1. Subscription validation (returns validationToken)
    2. Email notifications (processes new emails)

    Setup:
    1. Configure GRAPH_WEBHOOK_SECRET in environment
    2. Register subscription via Graph API pointing to this endpoint
    3. Emails will be processed automatically when received

    Microsoft will call this endpoint when:
    - A new email arrives in the monitored mailbox
    - The subscription needs validation/renewal
    """
    # Handle subscription validation
    if validationToken:
        logger.info("[GRAPH WEBHOOK] Subscription validation request received")
        return PlainTextResponse(content=validationToken, media_type="text/plain")

    # Get webhook secret
    expected_secret = os.getenv("GRAPH_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET"))

    try:
        # Parse notification payload
        body = await request.json()
        payload = GraphNotificationPayload(**body)

        if not payload.value:
            logger.warning("[GRAPH WEBHOOK] Empty notification received")
            return PlainTextResponse(content="OK", status_code=202)

        # Reject all notifications if secret is not configured
        if not expected_secret:
            logger.critical("[GRAPH WEBHOOK] GRAPH_WEBHOOK_SECRET not configured — skipping ALL notifications")
            return PlainTextResponse(content="OK", status_code=202)

        # Validate client state for each notification
        for notification in payload.value:
            if notification.clientState != expected_secret:
                logger.warning(f"[GRAPH WEBHOOK] Invalid clientState for subscription {notification.subscriptionId}")
                # Still return 202 to avoid Microsoft retrying with invalid notifications
                continue

            # Process in background to respond quickly
            background_tasks.add_task(
                process_graph_email_notification,
                notification.dict()
            )

        logger.info(f"[GRAPH WEBHOOK] Queued {len(payload.value)} notifications for processing")
        return PlainTextResponse(content="OK", status_code=202)

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error processing notification: {e}", exc_info=True)
        # Return 202 to prevent Microsoft from retrying
        return PlainTextResponse(content="OK", status_code=202)


async def process_graph_email_notification(notification: Dict[str, Any]):
    """
    Process a Microsoft Graph email notification in the background.

    This function:
    1. Fetches the email content from Graph API
    2. Stores it in the database
    3. Optionally triggers email processing/classification
    """
    try:
        change_type = notification.get("changeType")
        resource = notification.get("resource")
        resource_data = notification.get("resourceData", {})
        email_id = resource_data.get("id")
        tenant_id = notification.get("tenantId")

        logger.info(f"[GRAPH WEBHOOK] Processing {change_type} for email {email_id}")

        if not email_id:
            logger.warning("[GRAPH WEBHOOK] No email ID in notification")
            return

        # Import database and services
        from database import get_db
        from sqlalchemy import text

        async for db in get_db():
            try:
                # Log the notification
                await db.execute(text("""
                    INSERT INTO email_webhook_log
                    (email_id, change_type, tenant_id, resource, received_at, processed)
                    VALUES (:email_id, :change_type, :tenant_id, :resource, :received_at, false)
                    ON CONFLICT (email_id) DO UPDATE SET
                        change_type = EXCLUDED.change_type,
                        received_at = EXCLUDED.received_at
                """), {
                    "email_id": email_id,
                    "change_type": change_type,
                    "tenant_id": tenant_id,
                    "resource": resource,
                    "received_at": datetime.now(timezone.utc),
                })
                await db.commit()

                # Fetch email content from Graph API
                email_content = await fetch_email_from_graph(email_id, tenant_id, db)

                if email_content:
                    # Process the email (classification, routing, etc.)
                    await process_incoming_email(email_content, db)

                    # Mark as processed
                    await db.execute(text("""
                        UPDATE email_webhook_log
                        SET processed = true, processed_at = :processed_at
                        WHERE email_id = :email_id
                    """), {
                        "email_id": email_id,
                        "processed_at": datetime.now(timezone.utc),
                    })
                    await db.commit()

                logger.info(f"[GRAPH WEBHOOK] Successfully processed email {email_id}")

            except Exception as e:
                logger.error(f"[GRAPH WEBHOOK] Error processing email {email_id}: {e}")
                await db.rollback()
            finally:
                await db.close()

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Background processing error: {e}", exc_info=True)


async def fetch_email_from_graph(
    email_id: str,
    tenant_id: str,
    db: Any
) -> Optional[Dict[str, Any]]:
    """
    Fetch email content from Microsoft Graph API.

    Returns the email with subject, body, sender, recipients, and attachments info.
    """
    try:
        # Get access token for the tenant
        from integrations.microsoft_graph import graph_client

        token = graph_client.get_access_token()
        if not token:
            logger.error("[GRAPH WEBHOOK] No access token available")
            return None

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{email_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params={
                    "$select": "id,subject,body,bodyPreview,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,importance,isRead",
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                email_data = response.json()

                return {
                    "id": email_data.get("id"),
                    "subject": email_data.get("subject", ""),
                    "body": email_data.get("body", {}),
                    "body_preview": email_data.get("bodyPreview", ""),
                    "from": email_data.get("from", {}),
                    "to_recipients": email_data.get("toRecipients", []),
                    "cc_recipients": email_data.get("ccRecipients", []),
                    "received_datetime": email_data.get("receivedDateTime"),
                    "has_attachments": email_data.get("hasAttachments", False),
                    "importance": email_data.get("importance", "normal"),
                    "is_read": email_data.get("isRead", False),
                }
            else:
                logger.error(f"[GRAPH WEBHOOK] Failed to fetch email: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error fetching email from Graph: {e}")
        return None


async def process_incoming_email(email: Dict[str, Any], db: Any):
    """
    Process an incoming email through the reconciliation system.

    FLOW:
    0. CHECK FOR AI CONVERSATION - if sender has active AI conversation, process with AI agent
    1. Create IncomingDataEvent for the email
    2. Classify email intent and recommended action
    3. Check for matching response patterns (learned behavior)
    4. Add to reconciliation queue for user review OR auto-execute if confidence is high
    5. User approves/rejects/modifies -> system learns

    This enables the AI to learn email handling preferences over time.
    """
    try:
        from sqlalchemy import text
        import json
        import re

        email_id = email.get("id")
        subject = email.get("subject", "")
        body_content = email.get("body", {}).get("content", "")
        body_preview = email.get("body_preview", "")
        from_email = email.get("from", {}).get("emailAddress", {}).get("address", "")
        from_name = email.get("from", {}).get("emailAddress", {}).get("name", "")
        to_recipients = email.get("to_recipients", [])
        received_at = email.get("received_datetime")
        has_attachments = email.get("has_attachments", False)

        # Extract sender domain for pattern matching
        sender_domain = from_email.split("@")[1] if "@" in from_email else ""

        logger.info(f"[GRAPH WEBHOOK] Processing email for reconciliation: {subject} from {from_email}")

        # =================================================================
        # STEP 0: Check if this is a reply to an AI conversation
        # =================================================================
        conv_id = f"email_{from_email.replace('@', '_').replace('.', '_')}"

        # Check if sender has an active AI conversation
        conv_check = await db.execute(text("""
            SELECT conversation_id, recipient_name, status
            FROM ai_email_conversations
            WHERE conversation_id = :conv_id AND status = 'active'
            LIMIT 1
        """), {"conv_id": conv_id})
        ai_conversation = conv_check.fetchone()

        if ai_conversation:
            logger.info(f"[GRAPH WEBHOOK] Found active AI conversation {conv_id} - routing to AI agent")
            await process_ai_conversation_reply(email, from_email, from_name, conv_id, db)
            return  # Skip normal reconciliation flow

        # Get the user_id from recipient (for multi-tenant support)
        # For now, we'll get the first user or use a system user
        user_result = await db.execute(text("""
            SELECT id FROM users WHERE email = :to_email LIMIT 1
        """), {"to_email": to_recipients[0].get("emailAddress", {}).get("address") if to_recipients else ""})
        user_row = user_result.fetchone()
        user_id = user_row.id if user_row else 1  # Default to admin user

        # =================================================================
        # STEP 1: Create IncomingDataEvent (enters reconciliation flow)
        # =================================================================
        result = await db.execute(text("""
            INSERT INTO incoming_data_events
            (source, external_message_id, raw_text, raw_html, subject, sender, recipients, attachments, received_at, processed, user_id, created_at)
            VALUES ('microsoft365', :email_id, :raw_text, :raw_html, :subject, :sender, :recipients, :attachments, :received_at, false, :user_id, :created_at)
            ON CONFLICT (external_message_id) DO UPDATE SET
                subject = EXCLUDED.subject,
                received_at = EXCLUDED.received_at
            RETURNING id
        """), {
            "email_id": email_id,
            "raw_text": body_preview[:5000] if body_preview else "",
            "raw_html": body_content[:50000] if body_content else "",
            "subject": subject,
            "sender": from_email,
            "recipients": json.dumps([r.get("emailAddress", {}).get("address") for r in to_recipients]),
            "attachments": json.dumps([]) if not has_attachments else json.dumps([{"type": "unknown"}]),
            "received_at": received_at,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        })
        event_row = result.fetchone()
        event_id = event_row.id if event_row else None
        await db.commit()

        if not event_id:
            logger.warning(f"[GRAPH WEBHOOK] Failed to create IncomingDataEvent for {email_id}")
            return

        # =================================================================
        # STEP 2: Classify email and recommend action
        # =================================================================
        email_type = classify_email_type(subject, body_content, from_email)
        email_intent = classify_email_intent_detailed(subject, body_content, from_email, sender_domain)
        recommended_action = recommend_email_action(email_intent, email_type, has_attachments)

        # =================================================================
        # STEP 3: Check for learned patterns
        # =================================================================
        pattern_match = await check_response_patterns(
            db, user_id, sender_domain, from_email, email_intent["intent"], subject
        )

        # =================================================================
        # STEP 4: Add to reconciliation queue OR auto-execute
        # =================================================================
        should_auto_execute = (
            pattern_match and
            pattern_match.get("is_active") and
            pattern_match.get("confidence_score", 0) >= pattern_match.get("auto_execute_threshold", 0.95)
        )

        # Determine priority
        priority = "normal"
        if email_type == "urgent_inquiry":
            priority = "urgent"
        elif email_type in ["loan_application", "document_submission"]:
            priority = "high"
        elif email_intent.get("confidence", 0) >= 0.90:
            priority = "high"

        # Add to email_response_queue for reconciliation review
        await db.execute(text("""
            INSERT INTO email_response_queue
            (user_id, email_id, incoming_event_id, sender_email, sender_name, subject, body_preview,
             received_at, email_intent, intent_confidence, recommended_action, recommended_response,
             recommendation_reasoning, recommendation_confidence, matched_pattern_id, pattern_confidence,
             status, priority, created_at)
            VALUES (:user_id, :email_id, :event_id, :sender_email, :sender_name, :subject, :body_preview,
                    :received_at, :email_intent, :intent_confidence, :recommended_action, :recommended_response,
                    :reasoning, :rec_confidence, :pattern_id, :pattern_confidence, :status, :priority, :created_at)
            ON CONFLICT DO NOTHING
        """), {
            "user_id": user_id,
            "email_id": email_id,
            "event_id": event_id,
            "sender_email": from_email,
            "sender_name": from_name,
            "subject": subject,
            "body_preview": body_preview[:500] if body_preview else "",
            "received_at": received_at,
            "email_intent": email_intent.get("intent"),
            "intent_confidence": email_intent.get("confidence", 0.5),
            "recommended_action": recommended_action.get("action_type"),
            "recommended_response": recommended_action.get("draft_response"),
            "reasoning": recommended_action.get("reasoning"),
            "rec_confidence": recommended_action.get("confidence", 0.5),
            "pattern_id": pattern_match.get("id") if pattern_match else None,
            "pattern_confidence": pattern_match.get("confidence_score") if pattern_match else None,
            "status": "auto_executed" if should_auto_execute else "pending",
            "priority": priority,
            "created_at": datetime.now(timezone.utc),
        })
        await db.commit()

        # If auto-execute, perform the action
        if should_auto_execute:
            logger.info(f"[GRAPH WEBHOOK] Auto-executing pattern {pattern_match.get('id')} for email {email_id}")
            await execute_email_response_pattern(db, user_id, email_id, pattern_match, email, recommended_action)
        else:
            logger.info(f"[GRAPH WEBHOOK] Email {email_id} added to reconciliation queue (priority: {priority})")

        # Mark event as processed
        await db.execute(text("""
            UPDATE incoming_data_events SET processed = true WHERE id = :event_id
        """), {"event_id": event_id})
        await db.commit()

        logger.info(f"[GRAPH WEBHOOK] Email processed: type={email_type}, intent={email_intent.get('intent')}, action={recommended_action.get('action_type')}")

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error in process_incoming_email: {e}", exc_info=True)
        raise


def classify_email_intent_detailed(subject: str, body: str, from_email: str, sender_domain: str) -> Dict[str, Any]:
    """
    Detailed email intent classification for reconciliation.
    Returns intent, confidence, and context.
    """
    subject_lower = subject.lower() if subject else ""
    body_lower = body.lower() if body else ""
    combined = subject_lower + " " + body_lower

    # Vendor/third-party domains
    vendor_domains = [
        "docusign.com", "optimalblue.com", "stewart.com", "firstam.com",
        "fidelity.com", "titlecompany", "appraisal", "title"
    ]

    # Clear to Close
    if any(kw in subject_lower for kw in ["clear to close", "ctc", "clear-to-close"]):
        return {"intent": "Clear to Close", "confidence": 0.95, "category": "status_update"}

    # Rate Lock
    if any(kw in subject_lower for kw in ["rate lock", "lock confirmation", "locked"]):
        return {"intent": "Rate Lock", "confidence": 0.90, "category": "status_update"}

    # Appraisal
    if any(kw in subject_lower for kw in ["appraisal", "home value", "property value"]):
        return {"intent": "Appraisal Update", "confidence": 0.90, "category": "document_update"}

    # Underwriting
    if any(kw in subject_lower for kw in ["underwriting", "conditional", "uw approval"]):
        return {"intent": "Underwriting Update", "confidence": 0.85, "category": "status_update"}

    # Title/Closing
    if any(kw in subject_lower for kw in ["title", "closing", "settlement", "hud"]):
        return {"intent": "Title/Closing", "confidence": 0.80, "category": "document_update"}

    # Document submission (client sending docs)
    if any(kw in combined for kw in ["attached", "please find", "sending you", "here is", "here are"]):
        if any(kw in combined for kw in ["paystub", "w2", "tax", "bank statement", "document"]):
            return {"intent": "Document Submission", "confidence": 0.85, "category": "document_received"}

    # Client question
    if any(kw in combined for kw in ["question", "status", "update", "when will", "how long"]):
        return {"intent": "Client Question", "confidence": 0.75, "category": "inquiry"}

    # Vendor notification
    if any(domain in sender_domain for domain in vendor_domains):
        return {"intent": "Vendor Notification", "confidence": 0.80, "category": "vendor_update"}

    return {"intent": "General", "confidence": 0.50, "category": "general"}


def recommend_email_action(intent: Dict[str, Any], email_type: str, has_attachments: bool) -> Dict[str, Any]:
    """
    Recommend what action to take based on email intent.
    Returns action type, draft response, and confidence.
    """
    intent_type = intent.get("intent", "General")
    category = intent.get("category", "general")

    # Status update emails - recommend acknowledging and updating CRM
    if category == "status_update":
        return {
            "action_type": "acknowledge_and_update",
            "title": f"Acknowledge {intent_type} and Update Status",
            "description": f"Send acknowledgment email and update loan status to reflect {intent_type}",
            "draft_response": f"Thank you for the update. I've noted the {intent_type.lower()} in our system.",
            "reasoning": f"This appears to be a {intent_type} notification that should be acknowledged and recorded.",
            "confidence": intent.get("confidence", 0.5),
            "creates_task": False,
            "updates_status": True,
        }

    # Document received - acknowledge and create task to review
    if category == "document_received" or email_type == "document_submission":
        return {
            "action_type": "acknowledge_and_task",
            "title": "Acknowledge Document and Create Review Task",
            "description": "Send acknowledgment and create task to review submitted documents",
            "draft_response": "Thank you for sending the documents. I'll review them and follow up if I need anything else.",
            "reasoning": "Documents were submitted and should be acknowledged with a review task created.",
            "confidence": intent.get("confidence", 0.5),
            "creates_task": True,
            "updates_status": False,
        }

    # Client question - create task to respond
    if category == "inquiry" or email_type == "client_inquiry":
        return {
            "action_type": "create_response_task",
            "title": "Create Task to Respond",
            "description": "This requires a personalized response - create a task to follow up",
            "draft_response": None,  # Needs human response
            "reasoning": "Client has a question that needs a thoughtful, personalized response.",
            "confidence": intent.get("confidence", 0.5),
            "creates_task": True,
            "updates_status": False,
        }

    # Vendor notification - acknowledge
    if category == "vendor_update":
        return {
            "action_type": "acknowledge",
            "title": "Acknowledge Vendor Update",
            "description": "Send brief acknowledgment to vendor",
            "draft_response": "Thank you for this update. I've received and noted the information.",
            "reasoning": "Vendor notifications typically just need acknowledgment.",
            "confidence": intent.get("confidence", 0.5),
            "creates_task": False,
            "updates_status": True,
        }

    # Default - queue for review
    return {
        "action_type": "queue_for_review",
        "title": "Review Email",
        "description": "Email needs manual review to determine appropriate action",
        "draft_response": None,
        "reasoning": "Could not confidently determine the appropriate action.",
        "confidence": 0.30,
        "creates_task": False,
        "updates_status": False,
    }


async def check_response_patterns(
    db: Any,
    user_id: int,
    sender_domain: str,
    sender_email: str,
    email_intent: str,
    subject: str
) -> Optional[Dict[str, Any]]:
    """
    Check if there's a learned response pattern for this email.
    Returns the matching pattern with highest confidence, or None.
    """
    try:
        from sqlalchemy import text

        result = await db.execute(text("""
            SELECT id, pattern_type, pattern_value, response_type, response_config,
                   confidence_score, is_active, auto_execute_threshold
            FROM email_response_patterns
            WHERE user_id = :user_id
              AND is_active = true
              AND (
                  (pattern_type = 'sender_domain' AND pattern_value = :domain)
                  OR (pattern_type = 'sender_email' AND pattern_value = :email)
                  OR (pattern_type = 'email_intent' AND pattern_value = :intent)
              )
            ORDER BY confidence_score DESC
            LIMIT 1
        """), {
            "user_id": user_id,
            "domain": sender_domain,
            "email": sender_email,
            "intent": email_intent,
        })

        row = result.fetchone()
        if row:
            return {
                "id": row.id,
                "pattern_type": row.pattern_type,
                "pattern_value": row.pattern_value,
                "response_type": row.response_type,
                "response_config": row.response_config,
                "confidence_score": float(row.confidence_score) if row.confidence_score else 0,
                "is_active": row.is_active,
                "auto_execute_threshold": float(row.auto_execute_threshold) if row.auto_execute_threshold else 0.95,
            }
        return None

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error checking patterns: {e}")
        return None


async def execute_email_response_pattern(
    db: Any,
    user_id: int,
    email_id: str,
    pattern: Dict[str, Any],
    email: Dict[str, Any],
    recommended_action: Dict[str, Any]
):
    """
    Execute an auto-approved email response pattern.
    This is called when confidence is high enough for autonomous action.
    """
    try:
        from sqlalchemy import text
        import json

        response_type = pattern.get("response_type")
        config = pattern.get("response_config") or {}

        logger.info(f"[GRAPH WEBHOOK] Auto-executing {response_type} for pattern {pattern.get('id')}")

        # Log the auto-execution
        await db.execute(text("""
            INSERT INTO email_response_log
            (user_id, email_id, sender_email, sender_domain, subject, email_intent,
             response_type, response_pattern_id, was_auto_executed, ai_recommended_action,
             ai_confidence, user_action, success, created_at, responded_at)
            VALUES (:user_id, :email_id, :sender_email, :sender_domain, :subject, :intent,
                    :response_type, :pattern_id, true, :ai_action, :ai_confidence,
                    'auto_approved', true, :now, :now)
        """), {
            "user_id": user_id,
            "email_id": email_id,
            "sender_email": email.get("from", {}).get("emailAddress", {}).get("address", ""),
            "sender_domain": email.get("from", {}).get("emailAddress", {}).get("address", "").split("@")[1] if "@" in email.get("from", {}).get("emailAddress", {}).get("address", "") else "",
            "subject": email.get("subject", ""),
            "intent": recommended_action.get("title"),
            "response_type": response_type,
            "pattern_id": pattern.get("id"),
            "ai_action": recommended_action.get("action_type"),
            "ai_confidence": recommended_action.get("confidence"),
            "now": datetime.now(timezone.utc),
        })

        # Update pattern usage
        await db.execute(text("""
            UPDATE email_response_patterns
            SET last_matched_at = :now, last_approved_at = :now
            WHERE id = :pattern_id
        """), {"now": datetime.now(timezone.utc), "pattern_id": pattern.get("id")})

        await db.commit()

        # Execute based on response type
        if response_type == "auto_reply" and config.get("template_id"):
            # Send auto-reply using template
            try:
                from email_service import email_service
                import re

                # Fetch the template
                template_result = await db.execute(text("""
                    SELECT id, name, subject, body, is_html, variables
                    FROM email_templates
                    WHERE id = :template_id AND is_active = true
                """), {"template_id": config.get("template_id")})
                template_row = template_result.fetchone()

                if template_row:
                    # Extract sender info
                    sender_email_addr = email.get("from", {}).get("emailAddress", {}).get("address", "")
                    sender_name = email.get("from", {}).get("emailAddress", {}).get("name", "")
                    if not sender_name:
                        sender_name = sender_email_addr.split("@")[0].replace(".", " ").title()

                    original_subject = email.get("subject", "")

                    # Build template variables
                    template_vars = {
                        "firstName": sender_name.split()[0] if sender_name else "there",
                        "senderName": sender_name,
                        "senderEmail": sender_email_addr,
                        "originalSubject": original_subject,
                        "companyName": os.getenv("COMPANY_NAME", "The Tim Loss Team"),
                        "supportEmail": os.getenv("SUPPORT_EMAIL", "support@perenniaai.com"),
                    }

                    # Render subject and body with variables
                    rendered_subject = template_row.subject
                    rendered_body = template_row.body

                    for var_name, var_value in template_vars.items():
                        # Support both {varName} and {{varName}} patterns
                        rendered_subject = re.sub(
                            rf"\{{\{{?\s*{var_name}\s*\}}?\}}",
                            str(var_value),
                            rendered_subject,
                            flags=re.IGNORECASE
                        )
                        rendered_body = re.sub(
                            rf"\{{\{{?\s*{var_name}\s*\}}?\}}",
                            str(var_value),
                            rendered_body,
                            flags=re.IGNORECASE
                        )

                    # Determine reply subject
                    reply_subject = rendered_subject
                    if not reply_subject.lower().startswith("re:") and original_subject:
                        reply_subject = f"Re: {original_subject}"

                    # Send the email
                    from_email_addr = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

                    if template_row.is_html:
                        email_sent = email_service.send_html_email(
                            to_email=sender_email_addr,
                            subject=reply_subject,
                            html_body=rendered_body,
                            plain_text_body=re.sub(r'<[^>]+>', '', rendered_body),  # Strip HTML for plain text
                            from_email=from_email_addr,
                            reply_to=from_email_addr
                        )
                    else:
                        email_sent = email_service.send_html_email(
                            to_email=sender_email_addr,
                            subject=reply_subject,
                            html_body=f"<pre style='font-family: sans-serif;'>{rendered_body}</pre>",
                            plain_text_body=rendered_body,
                            from_email=from_email_addr,
                            reply_to=from_email_addr
                        )

                    if email_sent:
                        logger.info(f"[GRAPH WEBHOOK] Auto-reply sent to {sender_email_addr} using template {template_row.name}")

                        # Update template usage stats
                        await db.execute(text("""
                            UPDATE email_templates
                            SET updated_at = :now
                            WHERE id = :template_id
                        """), {"now": datetime.now(timezone.utc), "template_id": config.get("template_id")})
                        await db.commit()
                    else:
                        logger.warning(f"[GRAPH WEBHOOK] Failed to send auto-reply to {sender_email_addr}")
                else:
                    logger.warning(f"[GRAPH WEBHOOK] Template {config.get('template_id')} not found or inactive")

            except Exception as email_err:
                logger.error(f"[GRAPH WEBHOOK] Error sending auto-reply: {email_err}", exc_info=True)

        elif response_type == "create_task":
            # Create a task
            await db.execute(text("""
                INSERT INTO tasks
                (title, description, type, priority, status, due_date, metadata, created_at, user_id)
                VALUES (:title, :description, :type, :priority, 'pending', :due_date, :metadata, :created_at, :user_id)
            """), {
                "title": f"Review: {email.get('subject', 'Email')[:100]}",
                "description": recommended_action.get("reasoning", ""),
                "type": config.get("task_type", "email_followup"),
                "priority": config.get("priority", "medium"),
                "due_date": datetime.now(timezone.utc),
                "metadata": json.dumps({"email_id": email_id, "pattern_id": pattern.get("id")}),
                "created_at": datetime.now(timezone.utc),
                "user_id": user_id,
            })
            await db.commit()
            logger.info(f"[GRAPH WEBHOOK] Created task from auto-executed pattern")

        elif response_type == "archive":
            # Mark as handled without response
            logger.info(f"[GRAPH WEBHOOK] Email archived by auto-execution")

        logger.info(f"[GRAPH WEBHOOK] Successfully auto-executed pattern {pattern.get('id')}")

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error executing pattern: {e}", exc_info=True)


async def handle_internal_user_email(
    email: Dict[str, Any],
    from_email: str,
    from_name: str,
    user_row: Any,
    clean_message: str,
    subject: str,
    conv_id: str,
    db: Any
):
    """
    Handle emails from internal users (team members, LOs, admins).

    Internal users should NOT be treated as leads or prospects.
    Instead, we should:
    1. Recognize their authority/role
    2. Parse their request (task, question, action needed)
    3. Route appropriately or provide helpful assistance
    """
    try:
        from email_service import email_service
        import os

        user_name = user_row.name or from_name
        user_role = user_row.role or "team_member"
        user_title = user_row.title or ""

        logger.info(f"[INTERNAL USER] Processing request from {user_name} ({user_role}): {clean_message[:100]}...")

        # Use AI to understand the internal user's request
        ai_response = await generate_internal_user_response(
            user_name=user_name,
            user_role=user_role,
            user_title=user_title,
            message=clean_message,
            subject=subject,
            db=db
        )

        # Build response email
        html_response = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px; }}
    </style>
</head>
<body>
<div style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000;">
<p>Hi {user_name.split()[0] if user_name else 'there'},</p>

<p>{ai_response['response'].replace(chr(10), '<br>')}</p>

<p>Best regards,<br>
<b>Sarah</b><br>
<span style="color: #666666;">AI Assistant | The Tim Loss Team</span></p>
</div>
</body>
</html>"""

        plain_text_response = f"""Hi {user_name.split()[0] if user_name else 'there'},

{ai_response['response']}

Best regards,
Sarah
AI Assistant | The Tim Loss Team"""

        # Determine reply subject
        reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

        # Send response from the reply subdomain
        ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
        email_sent = email_service.send_html_email(
            to_email=from_email,
            subject=reply_subject,
            html_body=html_response,
            plain_text_body=plain_text_response,
            from_email=ai_from_email,
            reply_to=ai_from_email
        )

        logger.info(f"[INTERNAL USER] Sent response to {from_email}, email_sent={email_sent}")

        # Create a task if the AI detected an actionable request
        if ai_response.get("create_task") and ai_response.get("task_details"):
            task_details = ai_response["task_details"]
            await db.execute(text("""
                INSERT INTO tasks
                (title, description, type, priority, status, due_date, metadata, created_at, user_id, assigned_to)
                VALUES (:title, :description, :type, :priority, 'pending', :due_date, :metadata, :created_at, :user_id, :assigned_to)
            """), {
                "title": task_details.get("title", f"Request from {user_name}"),
                "description": task_details.get("description", clean_message),
                "type": task_details.get("type", "internal_request"),
                "priority": task_details.get("priority", "medium"),
                "due_date": datetime.now(timezone.utc),
                "metadata": json.dumps({"from_email": from_email, "original_message": clean_message[:500]}),
                "created_at": datetime.now(timezone.utc),
                "user_id": user_row.id,
                "assigned_to": task_details.get("assigned_to", user_row.id),
            })
            await db.commit()
            logger.info(f"[INTERNAL USER] Created task: {task_details.get('title')}")

    except Exception as e:
        logger.error(f"[INTERNAL USER] Error handling internal user email: {e}", exc_info=True)


async def generate_internal_user_response(
    user_name: str,
    user_role: str,
    user_title: str,
    message: str,
    subject: str,
    db: Any
) -> Dict[str, Any]:
    """
    Generate an appropriate response for an internal user's request.
    Uses AI to understand the request and provide helpful assistance.
    """
    try:
        import anthropic
        import os

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        system_prompt = f"""You are Sarah, an AI assistant for The Tim Loss Team, a mortgage lending team.

IMPORTANT: The person emailing you is an INTERNAL TEAM MEMBER, not a lead or prospect:
- Name: {user_name}
- Role: {user_role}
- Title: {user_title}

They are a person of authority within the organization. Do NOT:
- Treat them as a potential mortgage customer
- Offer to connect them with a loan officer (they likely ARE a loan officer or manager)
- Ask qualifying questions about their mortgage needs
- Suggest they schedule a consultation

Instead, you should:
- Recognize their authority and role
- Help with their request professionally
- If they're asking for something to be done (like sending a letter), acknowledge the request
- If they're asking about a client/lead, provide helpful information
- If you can't complete their request directly, explain what steps are needed

Be professional, concise, and helpful. You're assisting a colleague, not qualifying a lead.

If they're asking you to perform a task (like send a pre-approval letter, look up a client, etc.):
1. Acknowledge their request
2. Explain what you can help with
3. If it requires manual action, create a task for follow-up

Respond in a friendly, professional tone appropriate for internal communication."""

        user_prompt = f"""Subject: {subject}

Message from {user_name}:
{message}

Please provide an appropriate response and indicate if a task should be created."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        ai_text = response.content[0].text

        # Check if we should create a task
        create_task = False
        task_details = None

        # Simple heuristics for task creation
        task_keywords = ["pre-approval", "letter", "send", "create", "generate", "look up", "find", "check"]
        if any(kw in message.lower() for kw in task_keywords):
            create_task = True
            task_details = {
                "title": f"Request: {subject[:50]}" if subject else f"Request from {user_name}",
                "description": f"Original request from {user_name}:\n\n{message}",
                "type": "internal_request",
                "priority": "high" if "urgent" in message.lower() or "asap" in message.lower() else "medium",
            }

        return {
            "response": ai_text,
            "create_task": create_task,
            "task_details": task_details
        }

    except Exception as e:
        logger.error(f"[INTERNAL USER] AI response generation failed: {e}")

        # Fallback response
        return {
            "response": f"""Thank you for your message, {user_name.split()[0] if user_name else 'there'}!

I've received your request regarding "{subject}". Since this requires specific action, I've flagged it for follow-up.

If this is urgent, please reach out directly through the CRM or contact the appropriate team member.

Is there anything else I can help you with?""",
            "create_task": True,
            "task_details": {
                "title": f"Email request: {subject[:50]}" if subject else f"Request from {user_name}",
                "description": f"Original request from {user_name}:\n\n{message}",
                "type": "internal_request",
                "priority": "medium",
            }
        }


async def process_ai_conversation_reply(
    email: Dict[str, Any],
    from_email: str,
    from_name: str,
    conv_id: str,
    db: Any
):
    """
    Process a reply to an AI outreach conversation.
    Routes through the AI qualification agent and sends AI response.
    """
    try:
        from sqlalchemy import text
        import re
        from agents.qualification_agent import process_qualification_message
        from email_service import email_service

        subject = email.get("subject", "")
        body_content = email.get("body", {}).get("content", "")
        body_preview = email.get("body_preview", "")

        # Get message content - prefer plain text or strip HTML
        message_body = body_preview or body_content
        if body_content and not body_preview:
            # Strip HTML tags
            message_body = re.sub(r'<[^>]+>', ' ', body_content)
            message_body = re.sub(r'\s+', ' ', message_body)

        # Clean up quoted replies
        lines = message_body.split('\n')
        clean_lines = []
        for line in lines:
            line_lower = line.lower().strip()
            if line.strip().startswith('>'):
                break
            if 'wrote:' in line_lower and ('@' in line_lower or 'on ' in line_lower):
                break
            if line_lower.startswith('from:') and '@' in line_lower:
                break
            if '-------- original message --------' in line_lower:
                break
            if 'sent from my iphone' in line_lower or 'sent from my ipad' in line_lower:
                break
            clean_lines.append(line)

        clean_message = '\n'.join(clean_lines).strip()

        if not clean_message:
            clean_message = message_body[:500].strip() if message_body else ""

        if not clean_message:
            logger.warning(f"[GRAPH WEBHOOK] Empty AI conversation reply from {from_email}")
            return

        logger.info(f"[GRAPH WEBHOOK] Processing AI conversation reply from {from_email}: {clean_message[:100]}...")

        # =================================================================
        # CHECK IF SENDER IS AN INTERNAL USER (team member, LO, admin)
        # =================================================================
        internal_user = await db.execute(text("""
            SELECT id, name, email, role, title
            FROM users
            WHERE LOWER(email) = LOWER(:email)
            LIMIT 1
        """), {"email": from_email})
        internal_user_row = internal_user.fetchone()

        if internal_user_row:
            # This is an internal user (team member) - don't treat them as a lead!
            logger.info(f"[GRAPH WEBHOOK] Sender {from_email} is internal user: {internal_user_row.name} ({internal_user_row.role})")

            # Route to internal user handler instead of qualification agent
            await handle_internal_user_email(
                email=email,
                from_email=from_email,
                from_name=from_name or internal_user_row.name,
                user_row=internal_user_row,
                clean_message=clean_message,
                subject=subject,
                conv_id=conv_id,
                db=db
            )
            return

        # Process through AI qualification agent (for external contacts only)
        result = process_qualification_message(
            conversation_id=conv_id,
            message=clean_message,
            channel="email",
            sender_info={"email": from_email, "first_name": from_name}
        )

        # Only send response if AI has one
        if result.get("should_send") and result.get("response"):
            # Get conversation state for threading
            from services.conversation_intelligence import get_conversation_service, Channel
            conv_service = get_conversation_service()
            state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

            # Record user message in history
            state.message_history.append({
                "role": "user",
                "content": clean_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            # Record AI response in history
            state.message_history.append({
                "role": "assistant",
                "content": result['response'],
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            # Format response email
            html_response = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px; }}
    </style>
</head>
<body>
<div style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000;">
<p>Hi {from_name or 'there'},</p>

<p>{result['response'].replace(chr(10), '<br>')}</p>

<p>Best regards,<br>
<b>Sarah</b><br>
<span style="color: #666666;">AI Mortgage Assistant | The Tim Loss Team</span></p>
</div>
</body>
</html>"""

            plain_text_response = f"""Hi {from_name or 'there'},

{result['response']}

Best regards,
Sarah
AI Mortgage Assistant | The Tim Loss Team"""

            # Determine reply subject
            reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

            # Send AI response FROM the reply subdomain so replies come back to us
            ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
            email_sent = email_service.send_html_email(
                to_email=from_email,
                subject=reply_subject,
                html_body=html_response,
                plain_text_body=plain_text_response,
                from_email=ai_from_email,
                reply_to=ai_from_email  # Also set reply-to for good measure
            )

            # Update conversation in database
            await db.execute(text("""
                UPDATE ai_email_conversations
                SET message_count = message_count + 2,
                    last_message_at = :now
                WHERE conversation_id = :conv_id
            """), {"conv_id": conv_id, "now": datetime.now(timezone.utc)})

            # Log the message exchange (use the same AI email for consistency)
            ai_email = ai_from_email
            await db.execute(text("""
                INSERT INTO ai_email_messages
                (conversation_id, direction, from_email, to_email, subject, body_text, ai_generated, created_at)
                VALUES (:conv_id, 'inbound', :from_email, :ai_email, :subject, :body, false, :now)
            """), {
                "conv_id": conv_id,
                "from_email": from_email,
                "ai_email": ai_email,
                "subject": subject,
                "body": clean_message,
                "now": datetime.now(timezone.utc),
            })

            await db.execute(text("""
                INSERT INTO ai_email_messages
                (conversation_id, direction, from_email, to_email, subject, body_text, ai_generated, created_at)
                VALUES (:conv_id, 'outbound', :ai_email, :to_email, :subject, :body, true, :now)
            """), {
                "conv_id": conv_id,
                "ai_email": ai_email,
                "to_email": from_email,
                "subject": reply_subject,
                "body": result['response'],
                "now": datetime.now(timezone.utc),
            })

            await db.commit()

            logger.info(f"[GRAPH WEBHOOK] Sent AI response to {from_email}, email_sent={email_sent}")
        else:
            logger.info(f"[GRAPH WEBHOOK] AI chose not to respond to {from_email}")

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error processing AI conversation reply: {e}", exc_info=True)


def classify_email_type(subject: str, body: str, from_email: str) -> str:
    """
    Simple email classification based on keywords.

    For production, this would use the AI-powered Email Orchestrator.
    """
    subject_lower = subject.lower()
    body_lower = body.lower() if body else ""
    combined = subject_lower + " " + body_lower

    # Loan application indicators
    loan_keywords = ["loan application", "mortgage application", "apply for loan",
                     "pre-approval", "preapproval", "home purchase", "refinance application"]
    if any(kw in combined for kw in loan_keywords):
        return "loan_application"

    # Document submission indicators
    doc_keywords = ["attached", "document", "paystub", "w2", "tax return", "bank statement",
                    "please find attached", "sending you", "here is the", "here are the"]
    if any(kw in combined for kw in doc_keywords):
        return "document_submission"

    # Urgent inquiry indicators
    urgent_keywords = ["urgent", "asap", "immediately", "critical", "emergency",
                       "time sensitive", "deadline"]
    if any(kw in combined for kw in urgent_keywords):
        return "urgent_inquiry"

    # Client inquiry indicators
    inquiry_keywords = ["question", "status", "update", "when", "how long",
                        "what is", "can you", "could you", "please advise"]
    if any(kw in combined for kw in inquiry_keywords):
        return "client_inquiry"

    # Invoice/billing
    invoice_keywords = ["invoice", "payment", "bill", "charge", "fee"]
    if any(kw in combined for kw in invoice_keywords):
        return "invoice"

    return "general"


@router.get("/graph/status")
async def get_graph_webhook_status():
    """
    Get the status of Microsoft Graph webhook subscriptions.
    """
    return {
        "status": "active",
        "webhook_url": os.getenv("GRAPH_WEBHOOK_URL", "Not configured"),
        "secret_configured": bool(os.getenv("GRAPH_WEBHOOK_SECRET") or os.getenv("WEBHOOK_SECRET")),
    }


@router.post("/graph/register")
async def register_graph_subscription(user_email: str = "admin@perenniaai.com"):
    """
    Register a Microsoft Graph webhook subscription for email notifications.
    """
    import requests
    from datetime import datetime, timedelta

    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    webhook_url = os.getenv("GRAPH_WEBHOOK_URL")
    webhook_secret = os.getenv("GRAPH_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET", ""))

    if not all([tenant_id, client_id, client_secret]):
        return {"error": "Missing Microsoft Graph credentials"}

    if not webhook_url:
        return {"error": "GRAPH_WEBHOOK_URL not configured"}

    # Get access token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_response = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if token_response.status_code != 200:
        return {"error": f"Failed to get access token: {token_response.text}"}

    access_token = token_response.json().get("access_token")

    # Check existing subscriptions
    list_response = requests.get(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )

    existing_subs = list_response.json().get("value", []) if list_response.status_code == 200 else []
    for sub in existing_subs:
        if sub.get("notificationUrl") == webhook_url:
            # Renew existing subscription
            expiration = (datetime.now(timezone.utc) + timedelta(days=2, hours=23)).isoformat() + "Z"
            renew_response = requests.patch(
                f"https://graph.microsoft.com/v1.0/subscriptions/{sub['id']}",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"expirationDateTime": expiration},
            )
            if renew_response.status_code == 200:
                return {"status": "renewed", "subscription_id": sub['id'], "expires": expiration}
            else:
                return {"error": f"Failed to renew: {renew_response.text}"}

    # Create new subscription
    expiration = (datetime.now(timezone.utc) + timedelta(days=2, hours=23)).isoformat() + "Z"
    resource = f"users/{user_email}/mailFolders/inbox/messages"

    subscription_data = {
        "changeType": "created",
        "notificationUrl": webhook_url,
        "resource": resource,
        "expirationDateTime": expiration,
        "clientState": webhook_secret,
    }

    create_response = requests.post(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=subscription_data,
    )

    if create_response.status_code == 201:
        subscription = create_response.json()
        return {
            "status": "created",
            "subscription_id": subscription.get("id"),
            "resource": resource,
            "expires": subscription.get("expirationDateTime"),
            "webhook_url": webhook_url,
        }
    else:
        return {"error": f"Failed to create subscription: {create_response.text}"}


# =============================================================================
# CACHE INVALIDATION WEBHOOK (existing)
# =============================================================================

class CacheInvalidationPayload(BaseModel):
    event: str  # "lead.updated", "loan.status_changed", etc.
    entity_type: str  # "lead", "loan", "contact", "rate"
    entity_id: Optional[int] = None
    user_id: Optional[str] = None


@router.post("/cache-invalidation")
async def handle_cache_invalidation(
    payload: CacheInvalidationPayload,
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")
):
    """
    Webhook endpoint for external systems to trigger cache invalidation.

    This allows CRM actions, database triggers, or external integrations
    to invalidate cached responses when data changes.

    Headers:
        X-Webhook-Secret: Required secret for authentication

    Request body:
    {
        "event": "lead.status_changed",
        "entity_type": "lead",
        "entity_id": 12345,
        "user_id": "user_123"  // Optional - invalidate for specific user
    }

    Events supported:
    - lead.created, lead.updated, lead.status_changed, lead.deleted
    - loan.created, loan.updated, loan.status_changed, loan.funded
    - rate.updated, rate.lock_changed
    - contact.updated
    """
    # Verify webhook secret
    expected_secret = os.getenv("WEBHOOK_SECRET")
    if not expected_secret:
        logger.warning("WEBHOOK_SECRET not configured - webhook disabled")
        raise HTTPException(503, "Webhook not configured")

    if not hmac.compare_digest(x_webhook_secret or "", expected_secret):
        logger.warning(f"Invalid webhook secret attempt for event: {payload.event}")
        raise HTTPException(403, "Invalid webhook secret")

    invalidated = {
        "response_cache": [],
        "tool_cache": []
    }

    try:
        # Import caches
        from utils.cache import cache as response_cache
        from core.cache import cache as tool_cache

        # Invalidate based on entity type
        if payload.entity_type == "lead":
            # Response cache invalidations
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"lead_{payload.entity_id}")
                invalidated["response_cache"].append(f"lead_{payload.entity_id}: {count}")

            count = await response_cache.invalidate_by_intent("lead_status")
            invalidated["response_cache"].append(f"lead_status intent: {count}")

            count = await response_cache.invalidate_by_intent("pipeline_query")
            invalidated["response_cache"].append(f"pipeline_query intent: {count}")

            # Tool cache invalidations
            if payload.entity_id:
                await tool_cache.delete(f"perennia:agent:get_lead_details:{payload.entity_id}")
                invalidated["tool_cache"].append(f"get_lead_details:{payload.entity_id}")

            await tool_cache.delete_pattern("perennia:agent:pipeline*")
            invalidated["tool_cache"].append("pipeline patterns")

        elif payload.entity_type == "loan":
            # Response cache invalidations
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"loan_{payload.entity_id}")
                invalidated["response_cache"].append(f"loan_{payload.entity_id}: {count}")

            count = await response_cache.invalidate_by_intent("loan_details")
            invalidated["response_cache"].append(f"loan_details intent: {count}")

            count = await response_cache.invalidate_by_intent("pipeline_query")
            invalidated["response_cache"].append(f"pipeline_query intent: {count}")

            # Tool cache invalidations
            if payload.entity_id:
                await tool_cache.delete(f"perennia:agent:get_loan_details:{payload.entity_id}")
                invalidated["tool_cache"].append(f"get_loan_details:{payload.entity_id}")

            await tool_cache.delete_pattern("perennia:agent:pipeline*")
            invalidated["tool_cache"].append("pipeline patterns")

        elif payload.entity_type == "rate":
            # Rate changes affect lock decisions
            count = await response_cache.invalidate_by_intent("rate_lock")
            invalidated["response_cache"].append(f"rate_lock intent: {count}")

            await tool_cache.delete_pattern("perennia:agent:*rate*")
            invalidated["tool_cache"].append("rate patterns")

            await tool_cache.delete_pattern("perennia:agent:*market*")
            invalidated["tool_cache"].append("market patterns")

        elif payload.entity_type == "contact":
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"contact_{payload.entity_id}")
                invalidated["response_cache"].append(f"contact_{payload.entity_id}: {count}")

        elif payload.entity_type == "task":
            count = await response_cache.invalidate_by_intent("tasks")
            invalidated["response_cache"].append(f"tasks intent: {count}")

            await tool_cache.delete_pattern("perennia:agent:*task*")
            invalidated["tool_cache"].append("task patterns")

        # If user_id provided, also invalidate user-specific caches
        if payload.user_id:
            count = await response_cache.invalidate_pattern(payload.user_id)
            invalidated["response_cache"].append(f"user {payload.user_id}: {count}")

        logger.info(f"[WEBHOOK] Cache invalidated for {payload.event}: {invalidated}")

        return {
            "status": "invalidated",
            "event": payload.event,
            "entity_type": payload.entity_type,
            "entity_id": payload.entity_id,
            "invalidated": invalidated
        }

    except ImportError as e:
        logger.warning(f"Cache module not available: {e}")
        return {
            "status": "skipped",
            "reason": "Cache not available",
            "event": payload.event
        }
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}", exc_info=True)
        raise HTTPException(500, "Cache invalidation failed")


@router.post("/data-sync")
async def handle_data_sync(
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")
):
    """
    Webhook to trigger full cache clear after bulk data sync.

    Use this after importing data or running migrations that affect
    multiple records.
    """
    expected_secret = os.getenv("WEBHOOK_SECRET")
    if not expected_secret or not hmac.compare_digest(x_webhook_secret or "", expected_secret):
        raise HTTPException(403, "Invalid webhook secret")

    try:
        from utils.cache import cache as response_cache
        from core.cache import cache as tool_cache

        response_count = await response_cache.clear_all()
        await tool_cache.delete_pattern("perennia:agent:*")

        logger.info(f"[WEBHOOK] Full cache clear after data sync: {response_count} response cache entries")

        return {
            "status": "cleared",
            "response_cache_cleared": response_count,
            "tool_cache_cleared": True
        }

    except Exception as e:
        logger.error(f"Data sync cache clear failed: {e}")
        raise HTTPException(500, "Internal server error")


# =============================================================================
# RETR RECRUITING WEBHOOK - Import Loan Officers and Realtors
# =============================================================================
# RETR (retr.app) is a recruiting platform for mortgage professionals.
# This webhook receives loan officer recruits and realtor/agent contacts
# from RETR and imports them into Perennia AI's recruiting engine.
#
# Setup in RETR:
# 1. Go to RETR Settings > Integrations
# 2. Add webhook URL: https://your-domain.com/webhooks/retr/import
# 3. Configure the RETR_WEBHOOK_SECRET environment variable for security
# =============================================================================


class RETRAgentData(BaseModel):
    """
    RETR Agent (Realtor) payload structure.
    Agents are imported as ReferralPartners in Perennia AI.
    """
    # Basic Info
    Owner: Optional[str] = None  # The RETR user who exported this record
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    FullName: Optional[str] = None
    Company: Optional[str] = None
    Email: Optional[str] = None
    Phone: Optional[str] = None

    # RETR Profile
    RetrProfileURL: Optional[str] = None
    RETRAgentId: Optional[str] = None

    # Production Metrics (Last 12 Months)
    BuyerCt_12Mo: Optional[int] = None  # Buyer transaction count
    BuyerVol_12Mo: Optional[float] = None  # Buyer volume
    LoanOfficerCt_12Mo: Optional[int] = None  # LO connections
    SellerCt_12Mo: Optional[int] = None  # Seller transaction count
    SellerVol_12Mo: Optional[float] = None  # Seller volume
    TotalCt_12Mo: Optional[int] = None  # Total transactions
    TotalVol_12Mo: Optional[float] = None  # Total volume

    # Loan Type Breakdown
    Conventional: Optional[int] = None
    VA: Optional[int] = None
    FHA: Optional[int] = None
    LMI: Optional[int] = None  # Low-to-Moderate Income
    MMCT: Optional[int] = None  # Minority/Majority Census Tract

    # Tags and Lists
    Tags: Optional[str] = None
    ListName: Optional[str] = None

    # Export metadata
    ExportDate: Optional[str] = None

    class Config:
        extra = "allow"  # Allow additional fields from RETR


class RETRLoanOfficerData(BaseModel):
    """
    RETR Loan Officer recruit payload structure.
    LO recruits are imported as candidates in the Recruiting Engine.
    """
    # Basic Info
    Owner: Optional[str] = None
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    FullName: Optional[str] = None
    Company: Optional[str] = None
    Email: Optional[str] = None
    Phone: Optional[str] = None

    # RETR Profile
    RetrProfileURL: Optional[str] = None
    RETRLoanOfficerId: Optional[str] = None
    NMLSID: Optional[str] = None

    # Production Metrics
    UnitsLast12Mo: Optional[int] = None
    VolumeLast12Mo: Optional[float] = None
    AvgLoanSize: Optional[float] = None

    # Loan Type Mix
    ConventionalPct: Optional[float] = None
    FHAPct: Optional[float] = None
    VAPct: Optional[float] = None
    JumboPct: Optional[float] = None

    # Social Media (LO Recruit add-on)
    LinkedInURL: Optional[str] = None
    FacebookURL: Optional[str] = None

    # Tags and Lists
    Tags: Optional[str] = None
    ListName: Optional[str] = None

    # Export metadata
    ExportDate: Optional[str] = None

    class Config:
        extra = "allow"


class RETRWebhookPayload(BaseModel):
    """
    Combined RETR webhook payload that can contain agents and/or loan officers.
    RETR sends either a single record or an array of records.
    """
    # For batch imports
    agents: Optional[List[RETRAgentData]] = None
    loan_officers: Optional[List[RETRLoanOfficerData]] = None

    # For single record imports (RETR may send directly)
    # These fields allow direct agent/LO data at root level
    Owner: Optional[str] = None
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    FullName: Optional[str] = None
    Email: Optional[str] = None
    Phone: Optional[str] = None
    Company: Optional[str] = None
    RETRAgentId: Optional[str] = None
    RETRLoanOfficerId: Optional[str] = None

    class Config:
        extra = "allow"


class RETRImportResult(BaseModel):
    """Result of RETR import operation."""
    import_id: str
    status: str
    agents_queued: int = 0
    loan_officers_queued: int = 0
    created_at: str


@router.post("/retr/import", response_class=PlainTextResponse)
async def handle_retr_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret"),
    x_retr_signature: str = Header(None, alias="X-RETR-Signature"),
):
    """
    RETR webhook endpoint for importing loan officers and realtors.

    This endpoint receives data exports from RETR and imports them into:
    - Loan Officers → mm_candidates (Recruiting Engine)
    - Agents/Realtors → referral_partners (Referral Partner CRM)

    Headers:
        X-Webhook-Secret: Shared secret for authentication
        X-RETR-Signature: Optional RETR signature validation

    Returns:
        202 Accepted with import_id for tracking
    """
    import uuid
    import json

    # Generate import ID for tracking
    import_id = str(uuid.uuid4())[:8].upper()

    # Validate webhook secret
    expected_secret = os.getenv("RETR_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET"))
    if not expected_secret:
        logger.warning("[RETR WEBHOOK] RETR_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook secret not configured")

    secret_match = (
        (x_webhook_secret and hmac.compare_digest(x_webhook_secret, expected_secret))
        or (x_retr_signature and hmac.compare_digest(x_retr_signature, expected_secret))
    )
    if not secret_match:
        logger.warning(f"[RETR WEBHOOK] Invalid secret for import {import_id}")
        # Still return 202 to prevent RETR from retrying with bad credentials
        # but don't process the data
        return PlainTextResponse(
            content=json.dumps({
                "import_id": import_id,
                "status": "rejected",
                "error": "Invalid webhook secret"
            }),
            status_code=202,
            media_type="application/json"
        )

    try:
        # Parse the request body
        body = await request.json()
        logger.info(f"[RETR WEBHOOK] Received import request {import_id}")

        agents_count = 0
        los_count = 0

        # Handle different payload structures
        # RETR may send: single object, array, or structured payload

        if isinstance(body, list):
            # Array of records - determine type by presence of specific fields
            for record in body:
                if record.get("RETRAgentId") or record.get("BuyerCt_12Mo") is not None:
                    # This is an agent/realtor
                    background_tasks.add_task(
                        process_retr_agent_import,
                        import_id,
                        record
                    )
                    agents_count += 1
                elif record.get("RETRLoanOfficerId") or record.get("NMLSID") or record.get("UnitsLast12Mo") is not None:
                    # This is a loan officer
                    background_tasks.add_task(
                        process_retr_loan_officer_import,
                        import_id,
                        record
                    )
                    los_count += 1
                else:
                    # Default to agent if has basic contact info
                    if record.get("Email") or record.get("FirstName"):
                        background_tasks.add_task(
                            process_retr_agent_import,
                            import_id,
                            record
                        )
                        agents_count += 1

        elif isinstance(body, dict):
            # Single object or structured payload
            if "agents" in body and body["agents"]:
                for agent in body["agents"]:
                    background_tasks.add_task(
                        process_retr_agent_import,
                        import_id,
                        agent
                    )
                    agents_count += 1

            if "loan_officers" in body and body["loan_officers"]:
                for lo in body["loan_officers"]:
                    background_tasks.add_task(
                        process_retr_loan_officer_import,
                        import_id,
                        lo
                    )
                    los_count += 1

            # Check if it's a single record at root level
            if not body.get("agents") and not body.get("loan_officers"):
                if body.get("RETRAgentId") or body.get("BuyerCt_12Mo") is not None:
                    background_tasks.add_task(
                        process_retr_agent_import,
                        import_id,
                        body
                    )
                    agents_count += 1
                elif body.get("RETRLoanOfficerId") or body.get("NMLSID") or body.get("UnitsLast12Mo") is not None:
                    background_tasks.add_task(
                        process_retr_loan_officer_import,
                        import_id,
                        body
                    )
                    los_count += 1
                elif body.get("Email") or body.get("FirstName"):
                    # Default to agent for unknown records with contact info
                    background_tasks.add_task(
                        process_retr_agent_import,
                        import_id,
                        body
                    )
                    agents_count += 1

        logger.info(f"[RETR WEBHOOK] Import {import_id}: {agents_count} agents, {los_count} LOs queued")

        return PlainTextResponse(
            content=json.dumps({
                "import_id": import_id,
                "status": "processing",
                "agents_queued": agents_count,
                "loan_officers_queued": los_count,
                "created_at": datetime.now(timezone.utc).isoformat()
            }),
            status_code=202,
            media_type="application/json"
        )

    except Exception as e:
        logger.error(f"[RETR WEBHOOK] Error processing import {import_id}: {e}", exc_info=True)
        return PlainTextResponse(
            content=json.dumps({
                "import_id": import_id,
                "status": "error",
                "error": "Internal server error"
            }),
            status_code=202,
            media_type="application/json"
        )


def process_retr_agent_import(import_id: str, agent_data: Dict[str, Any]):
    """
    Process a single RETR agent (realtor) import in the background.
    Creates or updates a ReferralPartner record.
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text

        logger.info(f"[RETR IMPORT {import_id}] Processing agent: {agent_data.get('Email', 'unknown')}")

        # Extract and normalize data
        first_name = agent_data.get("FirstName", "")
        last_name = agent_data.get("LastName", "")
        full_name = agent_data.get("FullName") or f"{first_name} {last_name}".strip()
        email = agent_data.get("Email", "").strip().lower() if agent_data.get("Email") else None
        phone = agent_data.get("Phone", "").strip() if agent_data.get("Phone") else None
        company = agent_data.get("Company", "").strip() if agent_data.get("Company") else None

        if not full_name and not email:
            logger.warning(f"[RETR IMPORT {import_id}] Skipping agent with no name or email")
            return

        # Calculate total volume and transaction count
        total_volume = float(agent_data.get("TotalVol_12Mo") or 0)
        if total_volume == 0:
            total_volume = float(agent_data.get("BuyerVol_12Mo") or 0) + float(agent_data.get("SellerVol_12Mo") or 0)

        total_transactions = int(agent_data.get("TotalCt_12Mo") or 0)
        if total_transactions == 0:
            total_transactions = int(agent_data.get("BuyerCt_12Mo") or 0) + int(agent_data.get("SellerCt_12Mo") or 0)

        # Build notes with RETR data
        notes_parts = []
        if agent_data.get("RetrProfileURL"):
            notes_parts.append(f"RETR Profile: {agent_data['RetrProfileURL']}")
        if agent_data.get("RETRAgentId"):
            notes_parts.append(f"RETR ID: {agent_data['RETRAgentId']}")
        if agent_data.get("Tags"):
            notes_parts.append(f"Tags: {agent_data['Tags']}")
        if agent_data.get("ListName"):
            notes_parts.append(f"List: {agent_data['ListName']}")
        if agent_data.get("Owner"):
            notes_parts.append(f"Exported by: {agent_data['Owner']}")

        # Add production summary
        if total_transactions > 0:
            notes_parts.append(f"\n12-Month Production: {total_transactions} transactions, ${total_volume:,.0f} volume")
            if agent_data.get("Conventional"):
                notes_parts.append(f"  - Conventional: {agent_data['Conventional']}")
            if agent_data.get("FHA"):
                notes_parts.append(f"  - FHA: {agent_data['FHA']}")
            if agent_data.get("VA"):
                notes_parts.append(f"  - VA: {agent_data['VA']}")

        notes = "\n".join(notes_parts) if notes_parts else None

        # Determine loyalty tier based on volume
        if total_volume >= 10000000:  # $10M+
            loyalty_tier = "gold"
        elif total_volume >= 5000000:  # $5M+
            loyalty_tier = "silver"
        else:
            loyalty_tier = "bronze"

        db = SessionLocal()
        try:
            # Check for existing partner by email
            existing = None
            if email:
                result = db.execute(text("""
                    SELECT id, name, notes FROM referral_partners
                    WHERE LOWER(email) = LOWER(:email)
                    LIMIT 1
                """), {"email": email})
                existing = result.fetchone()

            if existing:
                # Update existing partner
                db.execute(text("""
                    UPDATE referral_partners
                    SET name = COALESCE(:name, name),
                        company = COALESCE(:company, company),
                        phone = COALESCE(:phone, phone),
                        volume = GREATEST(volume, :volume),
                        closed_loans = GREATEST(closed_loans, :transactions),
                        loyalty_tier = :loyalty_tier,
                        notes = CASE
                            WHEN notes IS NULL OR notes = '' THEN :notes
                            ELSE notes || E'\n\n--- RETR Update ' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD') || ' ---\n' || COALESCE(:notes, '')
                        END,
                        last_interaction = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {
                    "id": existing.id,
                    "name": full_name,
                    "company": company,
                    "phone": phone,
                    "volume": total_volume,
                    "transactions": total_transactions,
                    "loyalty_tier": loyalty_tier,
                    "notes": notes,
                })
                db.commit()
                logger.info(f"[RETR IMPORT {import_id}] Updated agent: {email} (ID: {existing.id})")

            else:
                # Create new partner
                result = db.execute(text("""
                    INSERT INTO referral_partners (
                        name, business_name, contact_name, category, company, type,
                        email, phone, volume, closed_loans, loyalty_tier, status, notes
                    ) VALUES (
                        :name, :business_name, :contact_name, 'realtor', :company, 'Realtor',
                        :email, :phone, :volume, :transactions, :loyalty_tier, 'active', :notes
                    )
                    RETURNING id
                """), {
                    "name": full_name,
                    "business_name": company or "",
                    "contact_name": full_name,
                    "company": company,
                    "email": email,
                    "phone": phone,
                    "volume": total_volume,
                    "transactions": total_transactions,
                    "loyalty_tier": loyalty_tier,
                    "notes": notes,
                })
                new_id = result.fetchone()
                db.commit()
                logger.info(f"[RETR IMPORT {import_id}] Created agent: {email or full_name} (ID: {new_id.id if new_id else 'unknown'})")

        except Exception as e:
            logger.error(f"[RETR IMPORT {import_id}] Database error for agent {email}: {e}")
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[RETR IMPORT {import_id}] Error processing agent: {e}", exc_info=True)


def process_retr_loan_officer_import(import_id: str, lo_data: Dict[str, Any]):
    """
    Process a single RETR loan officer import in the background.
    Creates or updates a candidate in the Recruiting Engine.
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text
        import json

        logger.info(f"[RETR IMPORT {import_id}] Processing LO: {lo_data.get('Email', 'unknown')}")

        # Extract and normalize data
        first_name = lo_data.get("FirstName", "")
        last_name = lo_data.get("LastName", "")
        full_name = lo_data.get("FullName") or f"{first_name} {last_name}".strip()
        email = lo_data.get("Email", "").strip().lower() if lo_data.get("Email") else None
        phone = lo_data.get("Phone", "").strip() if lo_data.get("Phone") else None
        company = lo_data.get("Company", "").strip() if lo_data.get("Company") else None
        nmls_id = lo_data.get("NMLSID", "").strip() if lo_data.get("NMLSID") else None
        linkedin_url = lo_data.get("LinkedInURL", "").strip() if lo_data.get("LinkedInURL") else None

        if not email and not full_name:
            logger.warning(f"[RETR IMPORT {import_id}] Skipping LO with no name or email")
            return

        # Production metrics
        units_12mo = int(lo_data.get("UnitsLast12Mo") or 0)
        volume_12mo = float(lo_data.get("VolumeLast12Mo") or 0)
        avg_loan_size = float(lo_data.get("AvgLoanSize") or 0)

        # Estimate years of experience based on production (rough estimate)
        if units_12mo >= 50:
            years_experience = 5
        elif units_12mo >= 24:
            years_experience = 3
        elif units_12mo >= 12:
            years_experience = 2
        else:
            years_experience = 1

        # Build talent profile JSON with RETR data
        talent_profile = {
            "source": "retr",
            "retr_id": lo_data.get("RETRLoanOfficerId"),
            "retr_profile_url": lo_data.get("RetrProfileURL"),
            "nmls_id": nmls_id,
            "current_company": company,
            "production_12mo": {
                "units": units_12mo,
                "volume": volume_12mo,
                "avg_loan_size": avg_loan_size
            },
            "loan_mix": {
                "conventional_pct": lo_data.get("ConventionalPct"),
                "fha_pct": lo_data.get("FHAPct"),
                "va_pct": lo_data.get("VAPct"),
                "jumbo_pct": lo_data.get("JumboPct")
            },
            "social_media": {
                "linkedin": linkedin_url,
                "facebook": lo_data.get("FacebookURL")
            },
            "tags": lo_data.get("Tags"),
            "list_name": lo_data.get("ListName"),
            "exported_by": lo_data.get("Owner"),
            "export_date": lo_data.get("ExportDate"),
            "import_date": datetime.now(timezone.utc).isoformat()
        }

        db = SessionLocal()
        try:
            # Check for existing candidate by email
            existing = None
            if email:
                result = db.execute(text("""
                    SELECT id, first_name, last_name, talent_profile FROM mm_candidates
                    WHERE LOWER(email) = LOWER(:email)
                    LIMIT 1
                """), {"email": email})
                existing = result.fetchone()

            if existing:
                # Update existing candidate
                # Merge talent profiles
                existing_profile = existing.talent_profile or {}
                if isinstance(existing_profile, str):
                    existing_profile = json.loads(existing_profile)
                merged_profile = {**existing_profile, **talent_profile}

                db.execute(text("""
                    UPDATE mm_candidates
                    SET first_name = COALESCE(:first_name, first_name),
                        last_name = COALESCE(:last_name, last_name),
                        phone = COALESCE(:phone, phone),
                        previous_companies = COALESCE(:company, previous_companies),
                        linkedin_url = COALESCE(:linkedin, linkedin_url),
                        talent_profile = :profile,
                        years_mortgage_experience = GREATEST(COALESCE(years_mortgage_experience, 0), :years_exp),
                        has_mortgage_experience = true,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {
                    "id": existing.id,
                    "first_name": first_name or None,
                    "last_name": last_name or None,
                    "phone": phone,
                    "company": company,
                    "linkedin": linkedin_url,
                    "profile": json.dumps(merged_profile),
                    "years_exp": years_experience,
                })

                # Log activity
                db.execute(text("""
                    INSERT INTO mm_candidate_activities (
                        candidate_id, activity_type, description, is_automated
                    ) VALUES (
                        :candidate_id, 'profile_updated', 'Profile updated from RETR import', true
                    )
                """), {"candidate_id": existing.id})

                db.commit()
                logger.info(f"[RETR IMPORT {import_id}] Updated LO candidate: {email} (ID: {existing.id})")

            else:
                # Create new candidate
                result = db.execute(text("""
                    INSERT INTO mm_candidates (
                        first_name, last_name, email, phone,
                        source, target_role_name,
                        years_experience, years_mortgage_experience, has_mortgage_experience,
                        previous_companies, linkedin_url, talent_profile,
                        status, applied_at, is_active
                    ) VALUES (
                        :first_name, :last_name, :email, :phone,
                        'retr', 'Loan Officer',
                        :years_exp, :years_exp, true,
                        :company, :linkedin, :profile,
                        'new', CURRENT_TIMESTAMP, true
                    )
                    RETURNING id
                """), {
                    "first_name": first_name or "Unknown",
                    "last_name": last_name or "",
                    "email": email,
                    "phone": phone,
                    "years_exp": years_experience,
                    "company": company,
                    "linkedin": linkedin_url,
                    "profile": json.dumps(talent_profile),
                })
                new_id = result.fetchone()
                candidate_id = new_id.id if new_id else None

                if candidate_id:
                    # Log activity
                    db.execute(text("""
                        INSERT INTO mm_candidate_activities (
                            candidate_id, activity_type, description, is_automated
                        ) VALUES (
                            :candidate_id, 'imported', 'Candidate imported from RETR', true
                        )
                    """), {"candidate_id": candidate_id})

                db.commit()
                logger.info(f"[RETR IMPORT {import_id}] Created LO candidate: {email or full_name} (ID: {candidate_id})")

        except Exception as e:
            logger.error(f"[RETR IMPORT {import_id}] Database error for LO {email}: {e}")
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[RETR IMPORT {import_id}] Error processing LO: {e}", exc_info=True)


@router.get("/retr/status")
async def get_retr_webhook_status():
    """
    Get the status of the RETR webhook configuration.
    """
    return {
        "status": "active",
        "endpoint": "/webhooks/retr/import",
        "secret_configured": bool(os.getenv("RETR_WEBHOOK_SECRET") or os.getenv("WEBHOOK_SECRET")),
        "supported_types": ["agents", "loan_officers"],
        "documentation": "https://kb.retr.app/how-do-i-set-up-an-integration"
    }
