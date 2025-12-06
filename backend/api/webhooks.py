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
    Process an incoming email - classify, route, and create tasks as needed.

    This integrates with the Email Orchestrator processors:
    - LoanApplicationProcessor: Detect loan applications
    - ClientInquiryProcessor: Handle client questions
    - DocumentProcessor: Classify document submissions
    - SLAMonitorProcessor: Track response times
    """
    try:
        from sqlalchemy import text

        email_id = email.get("id")
        subject = email.get("subject", "")
        body = email.get("body", {}).get("content", "")
        from_email = email.get("from", {}).get("emailAddress", {}).get("address", "")
        from_name = email.get("from", {}).get("emailAddress", {}).get("name", "")
        received_at = email.get("received_datetime")

        logger.info(f"[GRAPH WEBHOOK] Processing email: {subject} from {from_email}")

        # Store in email_tracking table
        await db.execute(text("""
            INSERT INTO email_tracking
            (email_id, subject, from_email, from_name, body_preview, received_at, status, has_attachments)
            VALUES (:email_id, :subject, :from_email, :from_name, :body_preview, :received_at, 'pending', :has_attachments)
            ON CONFLICT (email_id) DO UPDATE SET
                subject = EXCLUDED.subject,
                received_at = EXCLUDED.received_at
        """), {
            "email_id": email_id,
            "subject": subject,
            "from_email": from_email,
            "from_name": from_name,
            "body_preview": email.get("body_preview", "")[:500],
            "received_at": received_at,
            "has_attachments": email.get("has_attachments", False),
        })
        await db.commit()

        # Classify email type using simple pattern matching
        # (Full AI classification would be done by the Email Orchestrator)
        email_type = classify_email_type(subject, body, from_email)

        # Create task if needed
        if email_type in ["loan_application", "document_submission", "urgent_inquiry"]:
            await db.execute(text("""
                INSERT INTO tasks
                (title, description, type, priority, status, due_date, metadata, created_at)
                VALUES (:title, :description, :type, :priority, 'pending', :due_date, :metadata, :created_at)
            """), {
                "title": f"Review: {subject[:100]}",
                "description": f"Email from {from_name or from_email}: {email.get('body_preview', '')[:300]}",
                "type": f"email_{email_type}",
                "priority": "high" if email_type == "urgent_inquiry" else "medium",
                "due_date": datetime.utcnow(),
                "metadata": f'{{"email_id": "{email_id}", "from": "{from_email}"}}',
                "created_at": datetime.utcnow(),
            })
            await db.commit()
            logger.info(f"[GRAPH WEBHOOK] Created task for {email_type} email")

        # Update tracking status
        await db.execute(text("""
            UPDATE email_tracking
            SET status = 'processed',
                email_type = :email_type,
                processed_at = :processed_at
            WHERE email_id = :email_id
        """), {
            "email_id": email_id,
            "email_type": email_type,
            "processed_at": datetime.utcnow(),
        })
        await db.commit()

        logger.info(f"[GRAPH WEBHOOK] Email classified as: {email_type}")

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error in process_incoming_email: {e}", exc_info=True)
        raise


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

    Returns information about active subscriptions and recent notifications.
    """
    try:
        from database import get_db
        from sqlalchemy import text

        async for db in get_db():
            try:
                # Get recent webhook activity
                recent = await db.execute(text("""
                    SELECT
                        COUNT(*) as total_received,
                        COUNT(CASE WHEN processed THEN 1 END) as total_processed,
                        MAX(received_at) as last_received
                    FROM email_webhook_log
                    WHERE received_at > NOW() - INTERVAL '24 hours'
                """))
                stats = recent.fetchone()

                return {
                    "status": "active",
                    "last_24h": {
                        "received": stats.total_received if stats else 0,
                        "processed": stats.total_processed if stats else 0,
                        "last_received": stats.last_received.isoformat() if stats and stats.last_received else None,
                    },
                    "webhook_url": os.getenv("GRAPH_WEBHOOK_URL", "Not configured"),
                    "secret_configured": bool(os.getenv("GRAPH_WEBHOOK_SECRET") or os.getenv("WEBHOOK_SECRET")),
                }
            finally:
                await db.close()

    except Exception as e:
        logger.error(f"[GRAPH WEBHOOK] Error getting status: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


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
