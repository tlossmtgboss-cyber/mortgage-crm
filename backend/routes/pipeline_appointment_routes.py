"""
Pipeline Appointment Trigger Routes

REST API for managing pipeline-to-calendar appointment trigger rules and
manually triggering appointments from loan stage changes.

Endpoints:
    GET    /api/v1/pipeline-appointments/rules             List rules (custom or defaults)
    POST   /api/v1/pipeline-appointments/rules             Create custom rule
    PUT    /api/v1/pipeline-appointments/rules/{rule_id}   Update rule
    DELETE /api/v1/pipeline-appointments/rules/{rule_id}   Delete rule
    POST   /api/v1/pipeline-appointments/trigger           Manually trigger for a loan
    GET    /api/v1/pipeline-appointments/history/{loan_id} View trigger history
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import html
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class RuleCreateRequest(BaseModel):
    """Request body for creating a pipeline appointment rule."""
    from_stage: str = Field(..., min_length=1, max_length=50, description="Loan stage that triggers the appointment")
    appointment_type: str = Field(..., min_length=1, max_length=100, description="Type key (e.g. 'closing_prep')")
    appointment_title: str = Field(..., min_length=1, max_length=255, description="Human-readable appointment title")
    delay_hours: int = Field(default=0, ge=0, le=720, description="Hours after stage change to schedule (0-720)")
    duration_minutes: int = Field(default=30, ge=5, le=480, description="Default meeting duration in minutes (5-480)")
    auto_book: bool = Field(default=False, description="Auto-create appointment vs send booking link")
    required: bool = Field(default=False, description="Compliance-required vs suggested")
    description: str = Field(default="", max_length=2000, description="Description included in appointment")
    meeting_mode: str = Field(default="video", description="Default meeting mode (video, phone, in_person)")


class RuleUpdateRequest(BaseModel):
    """Request body for updating a pipeline appointment rule."""
    from_stage: Optional[str] = Field(None, min_length=1, max_length=50)
    appointment_type: Optional[str] = Field(None, min_length=1, max_length=100)
    appointment_title: Optional[str] = Field(None, min_length=1, max_length=255)
    delay_hours: Optional[int] = Field(None, ge=0, le=720)
    duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    auto_book: Optional[bool] = None
    required: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=2000)
    meeting_mode: Optional[str] = None
    is_active: Optional[bool] = None


class ManualTriggerRequest(BaseModel):
    """Request body for manually triggering a pipeline appointment."""
    loan_id: int = Field(..., description="Loan ID to trigger appointments for")
    old_stage: str = Field(..., min_length=1, max_length=50, description="Previous loan stage")
    new_stage: str = Field(..., min_length=1, max_length=50, description="New loan stage (triggers matching rules)")
    loan_officer_id: Optional[int] = Field(None, description="Override LO assignment (defaults to loan's LO)")


# =============================================================================
# VALID STAGES (from database.enums.LoanStage)
# =============================================================================

VALID_STAGES = frozenset({
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
    "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED",
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "NURTURE",
    "WITHDRAWN", "DOES_NOT_QUALIFY",
})

VALID_MEETING_MODES = frozenset({"video", "phone", "in_person", "screen_share"})


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================

def register_pipeline_appointment_routes(app, get_db, get_current_user, **kwargs):
    """
    Register pipeline appointment trigger routes.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency returning current User.
    """

    # Lazy imports to avoid circular dependencies at module load
    from services.pipeline_appointment_trigger import (
        PipelineAppointmentTrigger,
        PipelineAppointmentRuleModel,
        PipelineAppointmentTriggerLog,
        DEFAULT_RULES,
    )

    # Ensure tables exist in production (Base.metadata.create_all is skipped)
    try:
        from db import engine
        PipelineAppointmentRuleModel.__table__.create(engine, checkfirst=True)
        PipelineAppointmentTriggerLog.__table__.create(engine, checkfirst=True)
        logger.info("Pipeline appointment tables verified")
    except Exception as e:
        logger.warning(f"Pipeline appointment table creation skipped: {e}")

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_org_id(user) -> int:
        """Extract organization_id from authenticated user."""
        org_id = getattr(user, "organization_id", None)
        if org_id is None:
            raise HTTPException(status_code=403, detail="No organization context")
        return org_id

    def _sanitize(text: str) -> str:
        """Sanitize user-provided text."""
        if not text:
            return text
        return html.escape(text.strip())

    def _validate_stage(stage: str) -> str:
        """Validate a loan stage string."""
        stage = stage.strip().upper()
        if stage not in VALID_STAGES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid loan stage: '{stage}'. Valid stages: {sorted(VALID_STAGES)}"
            )
        return stage

    def _validate_meeting_mode(mode: str) -> str:
        """Validate meeting mode."""
        mode = mode.strip().lower()
        if mode not in VALID_MEETING_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid meeting mode: '{mode}'. Valid modes: {sorted(VALID_MEETING_MODES)}"
            )
        return mode

    # =========================================================================
    # GET /api/v1/pipeline-appointments/rules — List rules
    # =========================================================================

    @app.get("/api/v1/pipeline-appointments/rules", tags=["Pipeline Appointments"])
    async def list_rules(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List pipeline appointment trigger rules for the current organization.

        Returns custom rules if any exist; otherwise returns the built-in defaults.
        """
        org_id = _get_org_id(current_user)

        custom_rules = (
            db.query(PipelineAppointmentRuleModel)
            .filter(
                PipelineAppointmentRuleModel.organization_id == org_id,
                PipelineAppointmentRuleModel.is_active == True,
            )
            .order_by(PipelineAppointmentRuleModel.from_stage)
            .all()
        )

        if custom_rules:
            return {
                "status": "success",
                "source": "custom",
                "count": len(custom_rules),
                "rules": [r.to_dict() for r in custom_rules],
            }

        # Return defaults
        from dataclasses import asdict
        default_list = [asdict(r) for r in DEFAULT_RULES]
        return {
            "status": "success",
            "source": "defaults",
            "count": len(default_list),
            "rules": default_list,
        }

    # =========================================================================
    # POST /api/v1/pipeline-appointments/rules — Create custom rule
    # =========================================================================

    @app.post("/api/v1/pipeline-appointments/rules", tags=["Pipeline Appointments"])
    async def create_rule(
        body: RuleCreateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Create a custom pipeline appointment trigger rule for the organization."""
        org_id = _get_org_id(current_user)

        from_stage = _validate_stage(body.from_stage)
        meeting_mode = _validate_meeting_mode(body.meeting_mode)

        # Check for duplicate: same org + stage + appointment_type
        existing = (
            db.query(PipelineAppointmentRuleModel)
            .filter(
                PipelineAppointmentRuleModel.organization_id == org_id,
                PipelineAppointmentRuleModel.from_stage == from_stage,
                PipelineAppointmentRuleModel.appointment_type == body.appointment_type.strip(),
                PipelineAppointmentRuleModel.is_active == True,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A rule for stage '{from_stage}' with type "
                    f"'{body.appointment_type}' already exists (id={existing.id})"
                ),
            )

        rule = PipelineAppointmentRuleModel(
            organization_id=org_id,
            from_stage=from_stage,
            appointment_type=body.appointment_type.strip(),
            appointment_title=_sanitize(body.appointment_title),
            delay_hours=body.delay_hours,
            duration_minutes=body.duration_minutes,
            auto_book=body.auto_book,
            required=body.required,
            description=_sanitize(body.description),
            meeting_mode=meeting_mode,
            is_active=True,
            created_by_user_id=getattr(current_user, "id", None),
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)

        logger.info(
            f"Created pipeline appointment rule {rule.id}: "
            f"stage={from_stage}, type={rule.appointment_type}, org={org_id}"
        )

        return {
            "status": "success",
            "message": f"Rule created for stage {from_stage}",
            "rule": rule.to_dict(),
        }

    # =========================================================================
    # PUT /api/v1/pipeline-appointments/rules/{rule_id} — Update rule
    # =========================================================================

    @app.put("/api/v1/pipeline-appointments/rules/{rule_id}", tags=["Pipeline Appointments"])
    async def update_rule(
        rule_id: int,
        body: RuleUpdateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update an existing pipeline appointment trigger rule."""
        org_id = _get_org_id(current_user)

        rule = (
            db.query(PipelineAppointmentRuleModel)
            .filter(
                PipelineAppointmentRuleModel.id == rule_id,
                PipelineAppointmentRuleModel.organization_id == org_id,
            )
            .first()
        )
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

        # Apply updates
        if body.from_stage is not None:
            rule.from_stage = _validate_stage(body.from_stage)
        if body.appointment_type is not None:
            rule.appointment_type = body.appointment_type.strip()
        if body.appointment_title is not None:
            rule.appointment_title = _sanitize(body.appointment_title)
        if body.delay_hours is not None:
            rule.delay_hours = body.delay_hours
        if body.duration_minutes is not None:
            rule.duration_minutes = body.duration_minutes
        if body.auto_book is not None:
            rule.auto_book = body.auto_book
        if body.required is not None:
            rule.required = body.required
        if body.description is not None:
            rule.description = _sanitize(body.description)
        if body.meeting_mode is not None:
            rule.meeting_mode = _validate_meeting_mode(body.meeting_mode)
        if body.is_active is not None:
            rule.is_active = body.is_active

        rule.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(rule)

        logger.info(f"Updated pipeline appointment rule {rule_id}, org={org_id}")

        return {
            "status": "success",
            "message": f"Rule {rule_id} updated",
            "rule": rule.to_dict(),
        }

    # =========================================================================
    # DELETE /api/v1/pipeline-appointments/rules/{rule_id} — Delete rule
    # =========================================================================

    @app.delete("/api/v1/pipeline-appointments/rules/{rule_id}", tags=["Pipeline Appointments"])
    async def delete_rule(
        rule_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Delete (soft-deactivate) a pipeline appointment trigger rule."""
        org_id = _get_org_id(current_user)

        rule = (
            db.query(PipelineAppointmentRuleModel)
            .filter(
                PipelineAppointmentRuleModel.id == rule_id,
                PipelineAppointmentRuleModel.organization_id == org_id,
            )
            .first()
        )
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

        # Soft delete — set is_active to False
        rule.is_active = False
        rule.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Deactivated pipeline appointment rule {rule_id}, org={org_id}")

        return {
            "status": "success",
            "message": f"Rule {rule_id} deleted",
        }

    # =========================================================================
    # POST /api/v1/pipeline-appointments/trigger — Manual trigger
    # =========================================================================

    @app.post("/api/v1/pipeline-appointments/trigger", tags=["Pipeline Appointments"])
    async def manual_trigger(
        body: ManualTriggerRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Manually trigger pipeline appointment rules for a loan stage change.

        Useful for testing rules or retroactively triggering for loans that
        changed stage before rules were configured.
        """
        org_id = _get_org_id(current_user)

        old_stage = _validate_stage(body.old_stage)
        new_stage = _validate_stage(body.new_stage)

        # Determine loan officer
        loan_officer_id = body.loan_officer_id
        if loan_officer_id is None:
            # Look up from the loan
            from database.models.lead_loan import Loan
            loan = (
                db.query(Loan)
                .filter(Loan.id == body.loan_id, Loan.organization_id == org_id)
                .first()
            )
            if not loan:
                raise HTTPException(status_code=404, detail=f"Loan {body.loan_id} not found")
            loan_officer_id = loan.loan_officer_id

        trigger = PipelineAppointmentTrigger(db, org_id)
        results = await trigger.on_stage_change(
            loan_id=body.loan_id,
            old_stage=old_stage,
            new_stage=new_stage,
            loan_officer_id=loan_officer_id,
        )
        db.commit()

        action_count = len([r for r in results if r.get("action") != "error"])
        error_count = len([r for r in results if r.get("action") == "error"])

        return {
            "status": "success",
            "message": f"Triggered {action_count} actions ({error_count} errors) for stage {new_stage}",
            "loan_id": body.loan_id,
            "new_stage": new_stage,
            "results": results,
        }

    # =========================================================================
    # GET /api/v1/pipeline-appointments/history/{loan_id} — Trigger history
    # =========================================================================

    @app.get("/api/v1/pipeline-appointments/history/{loan_id}", tags=["Pipeline Appointments"])
    async def get_trigger_history(
        loan_id: int,
        limit: int = Query(default=50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get the pipeline appointment trigger history for a loan.

        Returns all trigger events (auto-booked, booking links sent, errors)
        for the specified loan, ordered by most recent first.
        """
        org_id = _get_org_id(current_user)

        # Verify loan belongs to org
        from database.models.lead_loan import Loan
        loan = (
            db.query(Loan)
            .filter(Loan.id == loan_id, Loan.organization_id == org_id)
            .first()
        )
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        logs = (
            db.query(PipelineAppointmentTriggerLog)
            .filter(
                PipelineAppointmentTriggerLog.loan_id == loan_id,
                PipelineAppointmentTriggerLog.organization_id == org_id,
            )
            .order_by(desc(PipelineAppointmentTriggerLog.created_at))
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "count": len(logs),
            "history": [log.to_dict() for log in logs],
        }
