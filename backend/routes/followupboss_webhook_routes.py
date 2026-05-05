"""
Follow Up Boss Webhook Routes
Perennia AI - Mortgage CRM

Handles inbound webhooks from Follow Up Boss:
- people.created - New person created
- people.updated - Person updated (check if assigned to user)
- people.stage_changed - Stage changed
- notes.created - Note added
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from sqlalchemy import text

from database import get_db
from models.followupboss_models import (
    FUBUserConnection, FUBSyncEvent, FUBEventType, FUBSyncStatus,
    FUBWebhookPayload
)
from integrations.followupboss_service import validate_webhook_signature
from services.followupboss_sync_service import FollowUpBossSyncService
from utils.background_tasks import tenant_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/followupboss", tags=["Follow Up Boss Webhooks"])


# =============================================================================
# WEBHOOK ENDPOINT
# =============================================================================

@router.post("/{user_id}")
async def handle_fub_webhook(
    user_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Handle incoming webhook from Follow Up Boss.

    FUB sends webhooks for subscribed events. Each user has their own
    webhook URL with a unique secret for validation.

    Args:
        user_id: The CRM user ID this webhook is for
        request: FastAPI request object
        background_tasks: For async processing
        db: Database session

    Returns:
        Acknowledgment response
    """
    # Get the user's FUB connection
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == user_id,
        FUBUserConnection.sync_enabled == True
    ).first()

    if not connection:
        logger.warning(f"FUB webhook received for user {user_id} with no active connection")
        raise HTTPException(status_code=404, detail="No active FUB connection for user")

    # Get raw body for signature validation
    body = await request.body()

    # Validate webhook signature — secret is required
    signature = request.headers.get("X-FUB-Signature", "")
    if not connection.webhook_secret:
        logger.error(f"FUB webhook secret not configured for user {user_id}")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not validate_webhook_signature(body, signature, connection.webhook_secret):
        logger.warning(f"FUB webhook signature validation failed for user {user_id}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse FUB webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("event", "unknown")
    event_data = payload.get("data", {})

    logger.info(f"FUB webhook received: {event_type} for user {user_id}")

    # Create sync event for audit
    sync_event = FUBSyncEvent(
        connection_id=connection.id,
        event_type=event_type,
        direction="inbound",
        fub_entity_type=event_type.split(".")[0] if "." in event_type else "unknown",
        fub_entity_id=event_data.get("id"),
        status=FUBSyncStatus.PENDING.value,
        request_payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sync_event)
    db.commit()
    db.refresh(sync_event)

    # Look up user's organization for RLS context in background task
    org_row = db.execute(
        text("SELECT organization_id FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    org_id = org_row.organization_id if org_row else None

    # Process webhook in background with tenant context
    if org_id:
        background_tasks.add_task(
            tenant_task, process_webhook_event, org_id,
            connection_id=connection.id,
            sync_event_id=sync_event.id,
            event_type=event_type,
            event_data=event_data,
        )
    else:
        background_tasks.add_task(
            process_webhook_event,
            connection_id=connection.id,
            sync_event_id=sync_event.id,
            event_type=event_type,
            event_data=event_data,
        )

    # Return immediately (best practice for webhooks)
    return {"status": "received", "event_id": sync_event.id}


# =============================================================================
# WEBHOOK PROCESSING
# =============================================================================

def process_webhook_event(
    connection_id: int = None,
    sync_event_id: int = None,
    event_type: str = None,
    event_data: dict = None,
    *,
    db: Session = None,
    organization_id: int = None,
):
    """
    Process webhook event in background.

    When invoked via tenant_task, receives a tenant-scoped db session.
    Falls back to unscoped SessionLocal for backward compatibility.

    Args:
        connection_id: FUB connection ID
        sync_event_id: Sync event ID for status updates
        event_type: FUB event type
        event_data: Event payload data
        db: Tenant-scoped DB session (from tenant_task)
        organization_id: Org ID for RLS (from tenant_task)
    """
    _owns_session = False
    if db is None:
        from database import SessionLocal
        db = SessionLocal()
        _owns_session = True
    try:
        # Get connection and sync event
        connection = db.query(FUBUserConnection).filter(
            FUBUserConnection.id == connection_id
        ).first()

        sync_event = db.query(FUBSyncEvent).filter(
            FUBSyncEvent.id == sync_event_id
        ).first()

        if not connection or not sync_event:
            logger.error(f"Connection or sync event not found: {connection_id}, {sync_event_id}")
            return

        # Update status to in progress
        sync_event.status = FUBSyncStatus.IN_PROGRESS.value
        db.commit()

        # Initialize sync service
        sync_service = FollowUpBossSyncService(db)

        # Process based on event type
        result = None
        error_message = None

        try:
            if event_type == "people.created":
                result = handle_person_created(sync_service, connection, event_data)
            elif event_type == "people.updated":
                result = handle_person_updated(sync_service, connection, event_data)
            elif event_type == "people.stage_changed":
                result = handle_stage_changed(sync_service, connection, event_data)
            elif event_type == "notes.created":
                result = handle_note_created(sync_service, connection, event_data)
            elif event_type == "people.assigned":
                result = handle_person_assigned(sync_service, connection, event_data)
            else:
                logger.info(f"Unhandled FUB event type: {event_type}")
                sync_event.status = FUBSyncStatus.SKIPPED.value
                db.commit()
                return

        except Exception as e:
            logger.exception(f"Error processing FUB webhook: {e}")
            error_message = str(e)

        # Update sync event with result
        if error_message:
            sync_event.status = FUBSyncStatus.FAILED.value
            sync_event.error_message = error_message
        else:
            sync_event.status = FUBSyncStatus.COMPLETED.value
            if result:
                sync_event.crm_entity_type = result.get("entity_type")
                sync_event.crm_entity_id = result.get("entity_id")
                sync_event.response_payload = result

        sync_event.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Speed-to-lead hook — fire for newly created leads
        if (
            result
            and result.get("entity_type") == "lead"
            and result.get("created")
            and result.get("entity_id")
        ):
            try:
                from services.lead_creation_hooks import on_lead_created_sync
                on_lead_created_sync(
                    db=db,
                    lead_id=result["entity_id"],
                    organization_id=getattr(connection, "organization_id", None),
                    source="followupboss",
                    owner_id=connection.user_id,
                )
            except Exception as stl_err:
                logger.warning(
                    f"Speed-to-lead hook failed for FUB lead {result.get('entity_id')}: {stl_err}"
                )

        # Update connection last sync
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = sync_event.status
        if error_message:
            connection.last_error = error_message
        db.commit()

        logger.info(f"FUB webhook processed: {event_type} -> {sync_event.status}")

    except Exception as e:
        logger.exception(f"Fatal error processing FUB webhook: {e}")
    finally:
        if _owns_session:
            db.close()


# =============================================================================
# EVENT HANDLERS
# =============================================================================

def handle_person_created(
    sync_service: FollowUpBossSyncService,
    connection: FUBUserConnection,
    event_data: dict,
) -> Optional[dict]:
    """
    Handle people.created event.

    Creates a new lead if the person is assigned to the connected user.
    """
    person_id = event_data.get("id")
    if not person_id:
        logger.warning("people.created event missing person ID")
        return None

    # Check if assigned to this user
    assigned_to = event_data.get("assignedTo")
    if assigned_to and connection.fub_user_id:
        # Check if it's a dict with id or just an id
        assigned_id = assigned_to.get("id") if isinstance(assigned_to, dict) else assigned_to
        if assigned_id != connection.fub_user_id:
            logger.info(f"Person {person_id} not assigned to user {connection.fub_user_id}, skipping")
            return {"skipped": True, "reason": "not_assigned_to_user"}

    # Sync person to lead
    lead_id, created = sync_service.sync_person_to_lead(
        connection=connection,
        fub_person=event_data,
        event_type=FUBEventType.PEOPLE_CREATED,
    )

    if lead_id:
        return {
            "entity_type": "lead",
            "entity_id": lead_id,
            "created": created,
        }

    return None


def handle_person_updated(
    sync_service: FollowUpBossSyncService,
    connection: FUBUserConnection,
    event_data: dict,
) -> Optional[dict]:
    """
    Handle people.updated event.

    Updates existing lead if mapped, or creates new if assigned to user.
    """
    person_id = event_data.get("id")
    if not person_id:
        return None

    # Check if we have a mapping for this person
    from models.followupboss_models import FUBLeadMapping

    mapping = sync_service.db.query(FUBLeadMapping).filter(
        FUBLeadMapping.connection_id == connection.id,
        FUBLeadMapping.fub_person_id == person_id,
    ).first()

    if mapping:
        # Update existing lead
        lead_id, _ = sync_service.sync_person_to_lead(
            connection=connection,
            fub_person=event_data,
            event_type=FUBEventType.PEOPLE_UPDATED,
        )
        return {
            "entity_type": "lead",
            "entity_id": lead_id,
            "updated": True,
        }
    else:
        # Check if now assigned to this user
        assigned_to = event_data.get("assignedTo")
        if assigned_to and connection.fub_user_id:
            assigned_id = assigned_to.get("id") if isinstance(assigned_to, dict) else assigned_to
            if assigned_id == connection.fub_user_id:
                # Create new lead
                lead_id, created = sync_service.sync_person_to_lead(
                    connection=connection,
                    fub_person=event_data,
                    event_type=FUBEventType.PEOPLE_UPDATED,
                )
                return {
                    "entity_type": "lead",
                    "entity_id": lead_id,
                    "created": created,
                }

    return {"skipped": True, "reason": "no_mapping_and_not_assigned"}


def handle_stage_changed(
    sync_service: FollowUpBossSyncService,
    connection: FUBUserConnection,
    event_data: dict,
) -> Optional[dict]:
    """
    Handle people.stage_changed event.

    Updates lead stage based on FUB stage mapping.
    """
    person_id = event_data.get("id") or event_data.get("personId")
    new_stage = event_data.get("stage") or event_data.get("newStage")

    if not person_id:
        return None

    # Find mapping
    from models.followupboss_models import FUBLeadMapping, FUBStageMapping
    from models.lead import Lead

    mapping = sync_service.db.query(FUBLeadMapping).filter(
        FUBLeadMapping.connection_id == connection.id,
        FUBLeadMapping.fub_person_id == person_id,
    ).first()

    if not mapping:
        logger.info(f"No mapping found for FUB person {person_id} on stage change")
        return {"skipped": True, "reason": "no_mapping"}

    # Get stage mapping
    if new_stage:
        stage_mapping = sync_service.db.query(FUBStageMapping).filter(
            FUBStageMapping.connection_id == connection.id,
            FUBStageMapping.fub_stage_name == new_stage,
        ).first()

        if stage_mapping:
            # Update lead stage
            lead = sync_service.db.query(Lead).filter(Lead.id == mapping.lead_id).first()
            if lead:
                lead.stage = stage_mapping.crm_stage
                lead.updated_at = datetime.now(timezone.utc)

                # Update mapping
                mapping.fub_stage = new_stage
                mapping.last_synced_at = datetime.now(timezone.utc)
                mapping.sync_direction = "inbound"

                sync_service.db.commit()

                # Event-driven workflow enrollment (eliminates 60s polling delay)
                try:
                    from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
                    trigger_workflow_evaluation_for_lead(
                        sync_service.db, mapping.lead_id,
                        stage_mapping.crm_stage,
                        lead_source=getattr(lead, 'source', None),
                    )
                except Exception as wf_err:
                    logger.warning(f"Workflow evaluation trigger failed for FUB lead {mapping.lead_id}: {wf_err}")

                return {
                    "entity_type": "lead",
                    "entity_id": mapping.lead_id,
                    "stage_updated": True,
                    "new_stage": stage_mapping.crm_stage,
                }

    return {"skipped": True, "reason": "no_stage_mapping"}


def handle_note_created(
    sync_service: FollowUpBossSyncService,
    connection: FUBUserConnection,
    event_data: dict,
) -> Optional[dict]:
    """
    Handle notes.created event.

    Creates activity in CRM for the associated lead.
    """
    if not connection.sync_notes:
        return {"skipped": True, "reason": "notes_sync_disabled"}

    person_id = event_data.get("personId")
    if not person_id:
        return None

    # Find mapping
    from models.followupboss_models import FUBLeadMapping

    mapping = sync_service.db.query(FUBLeadMapping).filter(
        FUBLeadMapping.connection_id == connection.id,
        FUBLeadMapping.fub_person_id == person_id,
    ).first()

    if not mapping:
        logger.info(f"No mapping found for FUB person {person_id} on note created")
        return {"skipped": True, "reason": "no_mapping"}

    # Sync note to activity
    activity_id = sync_service.sync_note_to_activity(connection, event_data)

    if activity_id:
        return {
            "entity_type": "activity",
            "entity_id": activity_id,
            "created": True,
        }

    return None


def handle_person_assigned(
    sync_service: FollowUpBossSyncService,
    connection: FUBUserConnection,
    event_data: dict,
) -> Optional[dict]:
    """
    Handle people.assigned event.

    If person is assigned to this user, import/update the lead.
    """
    person_id = event_data.get("id") or event_data.get("personId")
    assigned_to = event_data.get("assignedTo") or event_data.get("assignedUserId")

    if not person_id:
        return None

    # Check if assigned to this user
    if assigned_to and connection.fub_user_id:
        assigned_id = assigned_to.get("id") if isinstance(assigned_to, dict) else assigned_to
        if assigned_id == connection.fub_user_id:
            # Fetch full person data and sync
            from integrations.followupboss_service import FollowUpBossClient, decrypt_api_key

            try:
                api_key = decrypt_api_key(connection.api_key_encrypted)
                client = FollowUpBossClient(api_key)
                person_data = client.get_person(person_id)

                if person_data:
                    lead_id, created = sync_service.sync_person_to_lead(
                        connection=connection,
                        fub_person=person_data,
                        event_type=FUBEventType.PEOPLE_ASSIGNED,
                    )
                    return {
                        "entity_type": "lead",
                        "entity_id": lead_id,
                        "created": created,
                        "assigned": True,
                    }
            except Exception as e:
                logger.error(f"Error fetching person for assignment: {e}")
                raise

    return {"skipped": True, "reason": "not_assigned_to_user"}


# =============================================================================
# WEBHOOK TEST ENDPOINT
# =============================================================================

@router.post("/{user_id}/test")
async def test_webhook_endpoint(
    user_id: int,
):
    """
    Test endpoint for verifying webhook URL is reachable.

    Returns a minimal response without leaking internal state.
    Called by FUB or admin to confirm the URL is accessible.
    """
    return {
        "status": "ok",
        "message": "Webhook endpoint is accessible",
    }
