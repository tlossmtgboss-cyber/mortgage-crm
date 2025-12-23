# backend/api/webhooks.py
"""
Webhook endpoints for external system integrations, cache invalidation,
and Microsoft Graph email notifications.
"""
import os
import logging
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Request, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

        # Validate client state if secret is configured
        for notification in payload.value:
            if expected_secret and notification.clientState != expected_secret:
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
                    "received_at": datetime.utcnow(),
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
                        "processed_at": datetime.utcnow(),
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
            "created_at": datetime.utcnow(),
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
            "created_at": datetime.utcnow(),
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
            "now": datetime.utcnow(),
        })

        # Update pattern usage
        await db.execute(text("""
            UPDATE email_response_patterns
            SET last_matched_at = :now, last_approved_at = :now
            WHERE id = :pattern_id
        """), {"now": datetime.utcnow(), "pattern_id": pattern.get("id")})

        await db.commit()

        # Execute based on response type
        if response_type == "auto_reply" and config.get("template_id"):
            # TODO: Send auto-reply using template
            logger.info(f"[GRAPH WEBHOOK] Would send auto-reply using template {config.get('template_id')}")

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
                "due_date": datetime.utcnow(),
                "metadata": json.dumps({"email_id": email_id, "pattern_id": pattern.get("id")}),
                "created_at": datetime.utcnow(),
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

        # Process through AI qualification agent
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
                "timestamp": datetime.utcnow().isoformat()
            })

            # Record AI response in history
            state.message_history.append({
                "role": "assistant",
                "content": result['response'],
                "timestamp": datetime.utcnow().isoformat()
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
<span style="color: #666666;">AI Mortgage Assistant | Perennia AI</span></p>
</div>
</body>
</html>"""

            plain_text_response = f"""Hi {from_name or 'there'},

{result['response']}

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            # Determine reply subject
            reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

            # Send AI response
            email_sent = email_service.send_html_email(
                to_email=from_email,
                subject=reply_subject,
                html_body=html_response,
                plain_text_body=plain_text_response,
                reply_to=os.getenv("REPLY_TO_EMAIL", "sarah@perenniaai.com")
            )

            # Update conversation in database
            await db.execute(text("""
                UPDATE ai_email_conversations
                SET message_count = message_count + 2,
                    last_message_at = :now
                WHERE conversation_id = :conv_id
            """), {"conv_id": conv_id, "now": datetime.utcnow()})

            # Log the message exchange
            ai_email = os.getenv("FROM_EMAIL", "sarah@perenniaai.com")
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
                "now": datetime.utcnow(),
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
                "now": datetime.utcnow(),
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
            expiration = (datetime.utcnow() + timedelta(days=2, hours=23)).isoformat() + "Z"
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
    expiration = (datetime.utcnow() + timedelta(days=2, hours=23)).isoformat() + "Z"
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

    if x_webhook_secret != expected_secret:
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
        raise HTTPException(500, f"Cache invalidation failed: {str(e)}")


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
    if not expected_secret or x_webhook_secret != expected_secret:
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
        raise HTTPException(500, str(e))
