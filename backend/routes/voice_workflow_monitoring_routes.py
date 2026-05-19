"""
Voice Workflow Monitoring Routes
================================
Health check and monitoring endpoints for the voice scheduling workflow system.

Endpoints:
    GET  /api/v1/voice-workflows/health           System health metrics
    GET  /api/v1/voice-workflows/active            Active workflows for current user's org
    GET  /api/v1/voice-workflows/{workflow_id}     Detailed workflow status
    POST /api/v1/voice-workflows/{workflow_id}/cancel  Cancel a workflow
    POST /api/v1/voice-workflows/{workflow_id}/admin-override  Admin force state transition
    POST /api/v1/voice-workflows/{workflow_id}/webhook-test    Preview webhook event payload
    GET  /api/v1/voice-workflows/export/gdpr/{contact_phone}   GDPR Article 15 data export

NOTE: This router must be registered in main.py:
    from routes.voice_workflow_monitoring_routes import router as voice_workflow_monitoring_router
    app.include_router(voice_workflow_monitoring_router)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_

from database import get_db
from middleware.feature_gate import require_feature_tier

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/voice-workflows",
    tags=["Voice Workflow Monitoring"],
)


# =============================================================================
# DEPENDENCY INJECTION — runtime import to avoid circular deps
# =============================================================================

def get_current_user_dep():
    """Get current user dependency — imports from main at runtime."""
    import main
    return main.get_current_user


# =============================================================================
# CONSTANTS
# =============================================================================

# Terminal states (workflow is no longer active)
_TERMINAL_STATES = {"completed", "expired", "cancelled", "failed"}

# Active states (workflow is in progress)
_ACTIVE_STATES = {
    "initiated", "contact_found", "sms_sent", "awaiting_reply",
    "negotiating", "time_confirmed", "appointment_booked",
}


# =============================================================================
# HELPERS
# =============================================================================

def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask phone number for display, showing only last 4 digits."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 4:
        return phone
    return "***-***-" + digits[-4:]


def _get_voice_workflow_model():
    """Lazy import VoiceWorkflow model to avoid circular imports."""
    from database.models.voice_workflow import VoiceWorkflow
    return VoiceWorkflow


# =============================================================================
# GET /api/v1/voice-workflows/health
# =============================================================================

@router.get("/health")
@require_feature_tier("voice_workflows")
async def get_voice_workflow_health(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Return voice workflow system health metrics for the current user's organization.

    Includes:
    - Count of active workflows by state
    - Count of stuck workflows (active but past expires_at)
    - Count of workflows created in the last hour
    - Count of workflows completed in the last hour
    - Average time-to-completion for completed workflows (last 24h)
    """
    VoiceWorkflow = _get_voice_workflow_model()
    org_id = getattr(current_user, "organization_id", None)

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context available",
        )

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    twenty_four_hours_ago = now - timedelta(hours=24)

    try:
        # Count of active workflows grouped by state
        active_by_state_rows = (
            db.query(VoiceWorkflow.state, func.count(VoiceWorkflow.id))
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.state.notin_(_TERMINAL_STATES),
            )
            .group_by(VoiceWorkflow.state)
            .all()
        )
        active_by_state = {row[0]: row[1] for row in active_by_state_rows}
        total_active = sum(active_by_state.values())

        # Count of stuck workflows: active but past expires_at
        stuck_count = (
            db.query(func.count(VoiceWorkflow.id))
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.state.notin_(_TERMINAL_STATES),
                VoiceWorkflow.expires_at.isnot(None),
                VoiceWorkflow.expires_at < now,
            )
            .scalar()
        ) or 0

        # Count of workflows created in last hour
        created_last_hour = (
            db.query(func.count(VoiceWorkflow.id))
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.created_at >= one_hour_ago,
            )
            .scalar()
        ) or 0

        # Count of workflows completed in last hour
        completed_last_hour = (
            db.query(func.count(VoiceWorkflow.id))
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.state.in_({"completed", "appointment_booked"}),
                VoiceWorkflow.completed_at.isnot(None),
                VoiceWorkflow.completed_at >= one_hour_ago,
            )
            .scalar()
        ) or 0

        # Average time-to-completion for completed workflows in last 24h
        # completed_at - created_at in seconds, then convert to minutes
        avg_completion_seconds = (
            db.query(
                func.avg(
                    func.extract("epoch", VoiceWorkflow.completed_at)
                    - func.extract("epoch", VoiceWorkflow.created_at)
                )
            )
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.state.in_({"completed", "appointment_booked"}),
                VoiceWorkflow.completed_at.isnot(None),
                VoiceWorkflow.completed_at >= twenty_four_hours_ago,
            )
            .scalar()
        )

        avg_completion_minutes = None
        if avg_completion_seconds is not None:
            avg_completion_minutes = round(float(avg_completion_seconds) / 60, 1)

        return {
            "status": "success",
            "data": {
                "total_active": total_active,
                "active_by_state": active_by_state,
                "stuck_count": stuck_count,
                "created_last_hour": created_last_hour,
                "completed_last_hour": completed_last_hour,
                "avg_completion_minutes_24h": avg_completion_minutes,
            },
        }

    except Exception as e:
        logger.exception(f"Failed to retrieve voice workflow health metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow health metrics",
        )


# =============================================================================
# GET /api/v1/voice-workflows/active
# =============================================================================

@router.get("/active")
@require_feature_tier("voice_workflows")
async def get_active_voice_workflows(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Return list of active (non-terminal) voice workflows for the current user's organization.

    Phone numbers are masked for privacy.
    """
    VoiceWorkflow = _get_voice_workflow_model()
    org_id = getattr(current_user, "organization_id", None)

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context available",
        )

    try:
        workflows = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.organization_id == org_id,
                VoiceWorkflow.state.notin_(_TERMINAL_STATES),
            )
            .order_by(VoiceWorkflow.updated_at.desc())
            .all()
        )

        return {
            "status": "success",
            "data": {
                "count": len(workflows),
                "workflows": [
                    {
                        "workflow_id": wf.id,
                        "contact_name": wf.contact_name,
                        "contact_phone": _mask_phone(wf.contact_phone),
                        "state": wf.state,
                        "workflow_type": wf.workflow_type,
                        "created_at": wf.created_at.isoformat() if wf.created_at else None,
                        "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
                    }
                    for wf in workflows
                ],
            },
        }

    except Exception as e:
        logger.exception(f"Failed to retrieve active voice workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active workflows",
        )


# =============================================================================
# GET /api/v1/voice-workflows/{workflow_id}
# =============================================================================

@router.get("/{workflow_id}")
@require_feature_tier("voice_workflows")
async def get_voice_workflow_detail(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Return detailed status for a specific voice workflow.

    Includes all fields from to_status_dict(), conversation history,
    proposed slots, and associated appointment_id.

    Tenant-isolated: workflow must belong to the current user's organization.
    """
    VoiceWorkflow = _get_voice_workflow_model()
    org_id = getattr(current_user, "organization_id", None)

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context available",
        )

    try:
        workflow = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.id == workflow_id,
                VoiceWorkflow.organization_id == org_id,
            )
            .first()
        )

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow {workflow_id} not found",
            )

        return {
            "status": "success",
            "data": {
                "workflow_id": workflow.id,
                "type": workflow.workflow_type,
                "state": workflow.state,
                "contact_name": workflow.contact_name,
                "contact_phone": _mask_phone(workflow.contact_phone),
                "contact_email": workflow.contact_email,
                "lead_id": workflow.lead_id,
                "meeting_type": workflow.meeting_type,
                "meeting_duration_minutes": workflow.meeting_duration_minutes,
                "message_context": workflow.message_context,
                "turn_count": workflow.turn_count,
                "max_turns": workflow.max_turns,
                "confirmed_datetime": workflow.confirmed_datetime.isoformat() if workflow.confirmed_datetime else None,
                "appointment_id": workflow.appointment_id,
                "proposed_slots": workflow.proposed_slots or [],
                "conversation_history": workflow.conversation_history or [],
                "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
                "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
                "expires_at": workflow.expires_at.isoformat() if workflow.expires_at else None,
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                "error": workflow.error_message,
                "last_sms_sent_at": workflow.last_sms_sent_at.isoformat() if workflow.last_sms_sent_at else None,
                "last_sms_received_at": workflow.last_sms_received_at.isoformat() if workflow.last_sms_received_at else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retrieve workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow details",
        )


# =============================================================================
# POST /api/v1/voice-workflows/{workflow_id}/cancel
# =============================================================================

@router.post("/{workflow_id}/cancel")
@require_feature_tier("voice_workflows")
async def cancel_voice_workflow(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Cancel an active voice workflow.

    Sets state to 'cancelled'. The workflow must:
    - Belong to the current user's organization (tenant isolation)
    - Be in a non-terminal state (cannot cancel already completed/cancelled workflows)

    Returns the updated workflow status.
    """
    VoiceWorkflow = _get_voice_workflow_model()
    org_id = getattr(current_user, "organization_id", None)

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context available",
        )

    try:
        workflow = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.id == workflow_id,
                VoiceWorkflow.organization_id == org_id,
            )
            .first()
        )

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow {workflow_id} not found",
            )

        if workflow.state in _TERMINAL_STATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow is already in terminal state '{workflow.state}' and cannot be cancelled",
            )

        # Use the model's transition_to method which updates state and updated_at
        workflow.transition_to("cancelled")
        db.commit()
        db.refresh(workflow)

        logger.info(
            f"Voice workflow {workflow_id} cancelled by user {getattr(current_user, 'id', 'unknown')} "
            f"(org={org_id})"
        )

        return {
            "status": "success",
            "message": f"Workflow {workflow_id} cancelled",
            "data": {
                "workflow_id": workflow.id,
                "type": workflow.workflow_type,
                "state": workflow.state,
                "contact_name": workflow.contact_name,
                "contact_phone": _mask_phone(workflow.contact_phone),
                "meeting_type": workflow.meeting_type,
                "turn_count": workflow.turn_count,
                "max_turns": workflow.max_turns,
                "confirmed_datetime": workflow.confirmed_datetime.isoformat() if workflow.confirmed_datetime else None,
                "appointment_id": workflow.appointment_id,
                "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
                "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
                "expires_at": workflow.expires_at.isoformat() if workflow.expires_at else None,
                "error": workflow.error_message,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to cancel workflow {workflow_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel workflow",
        )


# =============================================================================
# POST /api/v1/voice-workflows/{workflow_id}/admin-override
# =============================================================================

# TODO: Add rate limiting to prevent abuse of admin state transitions
# Consider: max 10 transitions per user per minute
@router.post("/{workflow_id}/admin-override", tags=["voice-workflows"])
@require_feature_tier("voice_workflows")
async def admin_override_workflow_state(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Admin-only: Force a workflow state transition (bypass normal validation).

    Requires platform_admin or site_admin role. Creates audit trail.
    """
    # Role check
    user_role = getattr(current_user, "role", None)
    if user_role not in ("platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    new_state = body.get("new_state")
    reason = body.get("reason", "Admin override")

    if not new_state:
        raise HTTPException(status_code=400, detail="new_state is required")

    from database.models.voice_workflow import VoiceWorkflowState

    valid_states = [s.value for s in VoiceWorkflowState]
    if new_state not in valid_states:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state: {new_state}. Valid: {valid_states}",
        )

    VoiceWorkflow = _get_voice_workflow_model()
    organization_id = getattr(current_user, "organization_id", None)

    try:
        workflow = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.id == workflow_id,
                VoiceWorkflow.organization_id == organization_id,
            )
            .first()
        )

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        old_state = workflow.state
        # Direct state set (bypass normal transition validation)
        workflow.transition_to(new_state)

        # Audit trail for admin override
        from database.models.communication import Activity
        from database.enums import ActivityType

        activity = Activity(
            organization_id=workflow.organization_id,
            user_id=current_user.id,
            type=ActivityType.NOTE,
            content=(
                f"ADMIN OVERRIDE: Voice workflow {workflow_id} "
                f"force-transitioned {old_state} -> {new_state}. Reason: {reason}"
            ),
            lead_id=workflow.lead_id,
        )
        db.add(activity)
        db.commit()

        logger.info(
            "Admin override on workflow",
            extra={
                "workflow_id": str(workflow_id),
                "admin_user_id": str(current_user.id),
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
            },
        )

        return {
            "status": "ok",
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed admin override on workflow {workflow_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform admin override",
        )


# =============================================================================
# POST /api/v1/voice-workflows/{workflow_id}/webhook-test
# =============================================================================

@router.post("/{workflow_id}/webhook-test", tags=["voice-workflows"])
@require_feature_tier("voice_workflows")
async def test_workflow_webhook(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Test webhook delivery for a workflow (sends current state as event).

    Returns the event payload that would be dispatched to registered webhook URLs.
    """
    VoiceWorkflow = _get_voice_workflow_model()
    organization_id = getattr(current_user, "organization_id", None)

    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context available",
        )

    try:
        workflow = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.id == workflow_id,
                VoiceWorkflow.organization_id == organization_id,
            )
            .first()
        )

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService

        service = VoiceSchedulingWorkflowService(db)
        status_dict = service.to_status_dict(workflow)

        # In production, this would dispatch to registered webhook URLs.
        # For now, return the event payload that would be sent.
        event_payload = {
            "event": "voice_workflow.state_change",
            "workflow_id": workflow.id,
            "organization_id": workflow.organization_id,
            "state": workflow.state,
            "data": status_dict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "status": "ok",
            "event_payload": event_payload,
            "message": "Webhook event payload preview",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate webhook test for workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate webhook test payload",
        )


# =============================================================================
# GET /api/v1/voice-workflows/export/gdpr/{contact_phone}
# =============================================================================

@router.get("/export/gdpr/{contact_phone}", tags=["voice-workflows"])
@require_feature_tier("voice_workflows")
async def export_voice_workflow_gdpr_data(
    contact_phone: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """GDPR Article 15: Export all voice workflow data for a given contact phone.

    Returns all workflow records, conversation histories, and state transition
    audit trails for the specified phone number within the user's organization.
    """
    organization_id = getattr(current_user, 'organization_id', None)
    if not organization_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    # Normalize phone number
    normalized_phone = re.sub(r'[^\d+]', '', contact_phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    VoiceWorkflow = _get_voice_workflow_model()

    try:
        workflows = (
            db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.organization_id == organization_id,
                VoiceWorkflow.contact_phone == normalized_phone,
            )
            .order_by(VoiceWorkflow.created_at.desc())
            .all()
        )

        if not workflows:
            return {
                "contact_phone": normalized_phone,
                "organization_id": organization_id,
                "workflow_count": 0,
                "workflows": [],
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "gdpr_article": "Article 15 — Right of Access",
            }

        exported_workflows = []
        for wf in workflows:
            exported_workflows.append({
                "workflow_id": wf.id,
                "workflow_type": wf.workflow_type,
                "state": wf.state,
                "contact_name": wf.contact_name,
                "contact_phone": wf.contact_phone,
                "contact_email": wf.contact_email,
                "meeting_type": wf.meeting_type,
                "meeting_duration_minutes": wf.meeting_duration_minutes,
                "message_context": wf.message_context,
                "conversation_history": wf.conversation_history or [],
                "turn_count": wf.turn_count,
                "confirmed_datetime": wf.confirmed_datetime.isoformat() if wf.confirmed_datetime else None,
                "appointment_id": wf.appointment_id,
                "error_message": wf.error_message,
                "created_at": wf.created_at.isoformat() if wf.created_at else None,
                "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
                "expires_at": wf.expires_at.isoformat() if wf.expires_at else None,
            })

        # Also get audit trail from activities
        from database.models.communication import Activity

        workflow_ids = [wf.id for wf in workflows]
        audit_entries = (
            db.query(Activity)
            .filter(
                Activity.organization_id == organization_id,
                Activity.content.like('%Voice scheduling workflow%'),
            )
            .order_by(Activity.created_at.desc())
            .limit(500)
            .all()
        )

        # Filter to only activities mentioning our workflow IDs
        relevant_audit = []
        for entry in audit_entries:
            if any(re.search(rf'\bworkflow {wid}\b', entry.content or '') for wid in workflow_ids):
                relevant_audit.append({
                    "activity_id": entry.id,
                    "content": entry.content,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                })

        logger.info(
            "GDPR data export for voice workflows",
            extra={
                "organization_id": str(organization_id),
                "requesting_user_id": str(current_user.id),
                "contact_phone_last4": normalized_phone[-4:] if len(normalized_phone) >= 4 else "****",
                "workflow_count": len(workflows),
            },
        )

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id, organization_id=organization_id,
                resource_type="voice_workflow_gdpr_data", export_format="json",
                ip_address=_get_client_ip(request),
                details={"workflow_count": len(workflows), "contact_phone_last4": normalized_phone[-4:] if len(normalized_phone) >= 4 else "****"},
            )
        except Exception as _exc:  # noqa: BLE001
            pass

        return {
            "contact_phone": normalized_phone,
            "organization_id": organization_id,
            "workflow_count": len(workflows),
            "workflows": exported_workflows,
            "audit_trail": relevant_audit,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "gdpr_article": "Article 15 — Right of Access",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed GDPR export for contact phone: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export GDPR data",
        )
