"""
LOS Webhook Receiver Routes

Receives and processes webhook events from LOS systems (Encompass).
Handles signature verification, event routing, and async processing.

Enterprise Readiness: Check 7.6 (LOS Webhook Receiver)

Endpoints:
    POST /api/v1/webhooks/encompass  - Receive Encompass webhook events

Registration pattern: function-based (same as gdpr_routes, scorecard_routes)
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Schemas
# =============================================================================

class WebhookEventResponse(BaseModel):
    """Response for webhook event receipt."""
    status: str
    event_id: Optional[str] = None
    message: str


# =============================================================================
# Webhook Event Types
# =============================================================================

ENCOMPASS_EVENT_TYPES = {
    "loan.created",
    "loan.updated",
    "loan.deleted",
    "loan.milestone.changed",
    "loan.document.added",
    "loan.document.updated",
    "loan.condition.added",
    "loan.condition.cleared",
    "loan.disclosure.sent",
    "loan.lock.requested",
    "loan.lock.confirmed",
    "loan.lock.expired",
}


# =============================================================================
# Route Registration
# =============================================================================

def register_los_webhook_routes(app, get_db, **kwargs):
    """Register LOS webhook routes.

    Endpoints:
        POST /api/v1/webhooks/encompass
        GET  /api/v1/webhooks/encompass/events  (admin: list recent events)
    """
    import os

    WEBHOOK_SECRET = os.getenv("ENCOMPASS_WEBHOOK_SECRET", "")
    ENVIRONMENT = kwargs.get("ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))

    # -----------------------------------------------------------------
    # Signature Verification
    # -----------------------------------------------------------------

    def verify_encompass_signature(request_body: bytes, signature: str) -> bool:
        """Verify Encompass webhook signature using HMAC-SHA256.

        Encompass signs webhooks with HMAC-SHA256 using a shared secret.
        The signature is sent in the X-Encompass-Signature header.

        Args:
            request_body: Raw request body bytes
            signature: Signature from X-Encompass-Signature header

        Returns:
            True if signature is valid
        """
        if not WEBHOOK_SECRET:
            logger.error("ENCOMPASS_WEBHOOK_SECRET not configured - rejecting webhook (fail-closed)")
            return False

        expected = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            request_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature or "")

    def _resolve_org_from_webhook_secret(
        db: Session, request_body: bytes, signature: str
    ) -> Optional[int]:
        """Resolve organization_id by matching the webhook signature against per-org secrets.

        Iterates active EncompassConfig records and checks which org's webhook_secret
        produces a matching HMAC. Returns the organization_id on match, or None if
        only the global fallback secret matched.

        Args:
            db: Database session
            request_body: Raw request body bytes
            signature: Signature from X-Encompass-Signature header

        Returns:
            organization_id if a per-org secret matched, else None
        """
        if not signature:
            return None

        try:
            from database.models.encompass_config import EncompassConfig

            configs = db.query(EncompassConfig).filter(
                EncompassConfig.is_active == True,  # noqa: E712
                EncompassConfig.webhook_secret.isnot(None),
            ).all()

            for config in configs:
                secret = config.webhook_secret
                if not secret:
                    continue
                expected = hmac.new(
                    secret.encode("utf-8"),
                    request_body,
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(expected, signature):
                    return config.organization_id
        except Exception as e:
            logger.warning(f"Could not resolve org from webhook secret: {e}")

        return None

    # -----------------------------------------------------------------
    # Event Processing
    # -----------------------------------------------------------------

    async def process_webhook_event(
        event_type: str,
        payload: dict,
        db: Session,
        organization_id: Optional[int] = None,
    ) -> None:
        """Process a webhook event asynchronously.

        Routes the event to the appropriate handler based on event type.

        Args:
            event_type: The event type string
            payload: Event payload data
            db: Database session
            organization_id: Resolved org for tenant-scoped loan lookup
        """
        try:
            los_loan_id = payload.get("loanId") or payload.get("resourceId")
            resource_type = payload.get("resourceType", "loan")

            logger.info(f"Processing LOS webhook: {event_type} for {resource_type} {los_loan_id} (org={organization_id})")

            if event_type == "loan.milestone.changed":
                await _handle_milestone_change(db, los_loan_id, payload, organization_id)
            elif event_type in ("loan.created", "loan.updated"):
                await _handle_loan_update(db, los_loan_id, payload, organization_id)
            elif event_type.startswith("loan.document."):
                await _handle_document_event(db, los_loan_id, event_type, payload, organization_id)
            elif event_type.startswith("loan.condition."):
                await _handle_condition_event(db, los_loan_id, event_type, payload, organization_id)
            elif event_type.startswith("loan.lock."):
                await _handle_lock_event(db, los_loan_id, event_type, payload, organization_id)
            elif event_type.startswith("loan.disclosure."):
                await _handle_disclosure_event(db, los_loan_id, event_type, payload, organization_id)
            else:
                logger.info(f"Unhandled LOS webhook event type: {event_type}")

            # Log to audit
            _log_webhook_event(db, event_type, los_loan_id, payload, status="processed")

        except Exception as e:
            logger.error(f"Error processing LOS webhook {event_type}: {e}")
            _log_webhook_event(db, event_type, los_loan_id, payload, status="error", error=str(e))

    # -----------------------------------------------------------------
    # Event Handlers
    # -----------------------------------------------------------------

    async def _handle_milestone_change(
        db: Session, los_loan_id: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle milestone/stage change from LOS."""
        from database.models.lead_loan import Loan
        from services.los_integration.encompass_client import ENCOMPASS_STAGE_MAP

        new_milestone = payload.get("newValue") or payload.get("milestone")
        crm_stage = ENCOMPASS_STAGE_MAP.get(new_milestone)

        if not crm_stage:
            logger.warning(f"Unknown LOS milestone: {new_milestone}")
            return

        # Find CRM loan by LOS ID (tenant-scoped)
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            logger.warning(f"No CRM loan found for LOS loan {los_loan_id}")
            return

        old_stage = loan.stage
        if old_stage != crm_stage:
            loan.stage = crm_stage
            loan.stage_changed_at = datetime.now(timezone.utc)

            # Update Encompass sync tracking columns
            if hasattr(loan, "encompass_last_synced_at"):
                loan.encompass_last_synced_at = datetime.now(timezone.utc)
            if hasattr(loan, "encompass_sync_status"):
                loan.encompass_sync_status = "synced"

            db.flush()
            logger.info(f"Loan {loan.loan_number} stage updated: {old_stage} -> {crm_stage} (from LOS milestone: {new_milestone})")

            # Wire to SLA tracking
            try:
                from services.sla_tracking_service import track_loan_stage_change
                old_stage_str = old_stage.value if hasattr(old_stage, 'value') else str(old_stage) if old_stage else None
                track_loan_stage_change(
                    db, loan.id, old_stage_str, crm_stage,
                    loan_number=loan.loan_number,
                    organization_id=getattr(loan, "organization_id", None),
                )
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for LOS loan {loan.id}: {e}")

            # Event-driven workflow enrollment (eliminates 60s polling delay)
            try:
                from services.workflow_scheduler import trigger_workflow_evaluation_for_loan
                trigger_workflow_evaluation_for_loan(db, loan.id, crm_stage)
            except Exception as e:
                logger.warning(f"Workflow evaluation trigger failed for LOS loan {loan.id}: {e}")

    async def _handle_loan_update(
        db: Session, los_loan_id: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle general loan update from LOS.

        If auto_pull_on_webhook is enabled for the loan's organization,
        performs a full pull from Encompass. Otherwise, just notes the event.
        """
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            logger.info(f"LOS loan {los_loan_id} not linked to CRM - skipping update")
            return

        # Check if auto-pull is enabled for this org
        auto_pull = False
        org_id = getattr(loan, "organization_id", None)
        if org_id:
            try:
                from database.models.encompass_config import EncompassConfig
                config = db.query(EncompassConfig).filter(
                    EncompassConfig.organization_id == org_id,
                    EncompassConfig.is_active == True,  # noqa: E712
                ).first()
                if config and config.auto_pull_on_webhook:
                    auto_pull = True
            except Exception as e:
                logger.warning(f"Could not check auto_pull config for org {org_id}: {e}")

        if auto_pull:
            # Perform full pull from Encompass
            try:
                from services.los_integration.encompass_oauth_service import EncompassOAuthService
                from services.los_integration.sync_service import LOSSyncService

                oauth_service = EncompassOAuthService()
                client = await oauth_service.get_authenticated_client(db=db, org_id=org_id)
                sync_service = LOSSyncService(client=client)
                result = await sync_service.pull_from_los(
                    db=db, loan_id=loan.id, los_loan_id=los_loan_id,
                )

                # Update Encompass sync status columns
                loan.encompass_last_synced_at = datetime.now(timezone.utc)
                loan.encompass_sync_status = (
                    "synced" if result.status.value == "success" else "error"
                )
                db.flush()

                logger.info(
                    f"Auto-pulled LOS update for loan {loan.loan_number}: "
                    f"{result.status.value} ({result.fields_synced} fields synced)"
                )
            except Exception as e:
                logger.error(f"Auto-pull failed for loan {loan.loan_number}: {e}")
                loan.encompass_sync_status = "error"
                loan.updated_at = datetime.now(timezone.utc)
                db.flush()
        else:
            # Just note the event
            loan.updated_at = datetime.now(timezone.utc)
            if hasattr(loan, "encompass_sync_status"):
                loan.encompass_sync_status = "pending"
            db.flush()
            logger.info(f"Noted LOS update for loan {loan.loan_number} (auto-pull disabled)")

    async def _handle_document_event(
        db: Session, los_loan_id: str, event_type: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle document events from LOS."""
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            return

        doc_title = payload.get("title") or payload.get("documentTitle", "Unknown")
        logger.info(f"LOS document event for loan {loan.loan_number}: {event_type} - {doc_title}")

    async def _handle_condition_event(
        db: Session, los_loan_id: str, event_type: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle condition events from LOS."""
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            return

        condition = payload.get("conditionName") or payload.get("description", "Unknown")
        logger.info(f"LOS condition event for loan {loan.loan_number}: {event_type} - {condition}")

    async def _handle_lock_event(
        db: Session, los_loan_id: str, event_type: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle rate lock events from LOS."""
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            return

        if event_type == "loan.lock.confirmed":
            lock_date = payload.get("lockDate")
            lock_expiration = payload.get("lockExpirationDate")
            rate = payload.get("rate")

            if lock_date:
                loan.lock_date = datetime.fromisoformat(lock_date.replace("Z", "+00:00"))
            if lock_expiration:
                loan.lock_expiration_date = datetime.fromisoformat(lock_expiration.replace("Z", "+00:00"))
            if rate:
                try:
                    loan.rate = float(rate)
                except (ValueError, TypeError):
                    pass
            db.flush()
            logger.info(f"Loan {loan.loan_number} lock confirmed from LOS")

        elif event_type == "loan.lock.expired":
            loan.lock_expiration_date = None
            db.flush()
            logger.info(f"Loan {loan.loan_number} lock expired (from LOS)")

    async def _handle_disclosure_event(
        db: Session, los_loan_id: str, event_type: str, payload: dict, organization_id: Optional[int] = None,
    ):
        """Handle disclosure events from LOS."""
        loan = _find_loan_by_los_id(db, los_loan_id, organization_id)
        if not loan:
            return

        disclosure_type = payload.get("disclosureType", "unknown")
        sent_date = payload.get("sentDate")

        if disclosure_type in ("loan_estimate", "LE") and sent_date:
            loan.loan_estimate_sent_date = datetime.fromisoformat(sent_date.replace("Z", "+00:00"))
            db.flush()
            logger.info(f"Loan {loan.loan_number} LE sent date updated from LOS")
        elif disclosure_type in ("closing_disclosure", "CD") and sent_date:
            loan.cd_sent_to_borrower_date = datetime.fromisoformat(sent_date.replace("Z", "+00:00"))
            db.flush()
            logger.info(f"Loan {loan.loan_number} CD sent date updated from LOS")

    # -----------------------------------------------------------------
    # Helper Functions
    # -----------------------------------------------------------------

    def _find_loan_by_los_id(
        db: Session,
        los_loan_id: str,
        organization_id: Optional[int] = None,
    ):
        """Find a CRM loan by its LOS loan ID, scoped to an organization.

        Checks the dedicated encompass_loan_id column first (fast indexed query),
        then falls back to scanning user_metadata JSON for backward compatibility.

        Args:
            db: Database session
            los_loan_id: The LOS/Encompass loan identifier
            organization_id: Organization ID for tenant isolation. When provided,
                all queries are scoped to this org. When None, queries are unscoped
                (legacy behavior — callers should always provide this).
        """
        from database.models.lead_loan import Loan

        if not los_loan_id:
            return None

        def _org_filter(query):
            """Apply organization_id filter if available."""
            if organization_id is not None:
                return query.filter(Loan.organization_id == organization_id)
            return query

        # Primary: query dedicated encompass_loan_id column (indexed)
        try:
            query = db.query(Loan).filter(
                Loan.encompass_loan_id == los_loan_id
            )
            loan = _org_filter(query).first()
            if loan:
                return loan
        except Exception as e:
            logger.warning(f"Error querying encompass_loan_id column: {e}")

        # Fallback: search in user_metadata JSON for backward compatibility
        try:
            # Try PostgreSQL JSON operator
            query = db.query(Loan).filter(
                Loan.user_metadata["los_loan_id"].astext == los_loan_id
            )
            loan = _org_filter(query).first()
            if loan:
                # Migrate: set the dedicated column for future lookups
                if hasattr(loan, "encompass_loan_id") and not loan.encompass_loan_id:
                    loan.encompass_loan_id = los_loan_id
                    try:
                        db.flush()
                    except Exception:
                        pass
                return loan
        except Exception:
            pass

        # Last resort: scan user_metadata (org-scoped only, never cross-tenant)
        if organization_id is not None:
            try:
                query = db.query(Loan).filter(
                    Loan.organization_id == organization_id,
                    Loan.user_metadata.isnot(None),
                ).limit(200)
                loans = query.all()
                for loan in loans:
                    meta = loan.user_metadata if isinstance(loan.user_metadata, dict) else {}
                    if meta.get("los_loan_id") == los_loan_id or meta.get("encompass_guid") == los_loan_id:
                        # Migrate: set the dedicated column for future lookups
                        if hasattr(loan, "encompass_loan_id") and not loan.encompass_loan_id:
                            loan.encompass_loan_id = los_loan_id
                            try:
                                db.flush()
                            except Exception:
                                pass
                        return loan
            except Exception as e:
                logger.error(f"Error searching for LOS loan ID in user_metadata: {e}")
        else:
            logger.warning(
                f"Skipping user_metadata full scan for LOS loan {los_loan_id}: "
                "no organization_id provided (would be cross-tenant)"
            )

        return None

    def _log_webhook_event(
        db: Session,
        event_type: str,
        los_loan_id: str,
        payload: dict,
        status: str = "received",
        error: str = None,
    ):
        """Log webhook event to audit trail."""
        try:
            from database.models.security import AuditLog

            log = AuditLog(
                action="los_webhook",
                entity_type="loan",
                details={
                    "event_type": event_type,
                    "los_loan_id": los_loan_id,
                    "status": status,
                    "error": error,
                    "payload_keys": list(payload.keys()) if payload else [],
                },
            )
            db.add(log)
            db.flush()
        except Exception as e:
            logger.warning(f"Failed to log webhook event: {e}")

    # -----------------------------------------------------------------
    # Endpoints
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/webhooks/encompass",
        response_model=WebhookEventResponse,
        tags=["LOS Integration"],
    )
    async def receive_encompass_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
    ):
        """Receive and process Encompass webhook events.

        Verifies the webhook signature, validates the event type,
        and queues the event for async processing.

        Headers:
            X-Encompass-Signature: HMAC-SHA256 signature of the request body
            X-Encompass-Event: Event type string

        Body:
            JSON payload with event data including loanId, resourceType, etc.
        """
        # Read raw body for signature verification
        body = await request.body()

        # Verify signature
        signature = request.headers.get("X-Encompass-Signature", "")
        if not verify_encompass_signature(body, signature):
            logger.warning("Invalid webhook signature rejected")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        # Parse payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        # Get event type
        event_type = (
            request.headers.get("X-Encompass-Event")
            or payload.get("eventType")
            or payload.get("event")
        )

        if not event_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing event type",
            )

        # Validate event type
        if event_type not in ENCOMPASS_EVENT_TYPES:
            logger.info(f"Unknown LOS webhook event type: {event_type}")
            # Accept but don't process unknown events (for forward compatibility)

        # Generate event ID for tracking
        import uuid
        event_id = str(uuid.uuid4())[:12].upper()

        # Resolve organization from per-org webhook secret for tenant isolation
        organization_id = _resolve_org_from_webhook_secret(db, body, signature)
        if organization_id is None:
            logger.warning(
                "Could not resolve organization from webhook secret — "
                "loan lookups will lack tenant scoping"
            )

        # Log receipt
        _log_webhook_event(db, event_type, payload.get("loanId"), payload, status="received")

        # Queue for async processing
        background_tasks.add_task(
            process_webhook_event,
            event_type=event_type,
            payload=payload,
            db=db,
            organization_id=organization_id,
        )

        return WebhookEventResponse(
            status="accepted",
            event_id=event_id,
            message=f"Event {event_type} queued for processing",
        )
