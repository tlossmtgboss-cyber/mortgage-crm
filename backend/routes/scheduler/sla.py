"""
Scheduler SLA - Appointment SLA tracking and enforcement endpoints.

Endpoints:
  - GET /sla/dashboard                                    SLA compliance dashboard (all metrics)
  - GET /sla/breaches                                     Recent SLA breaches with details
  - GET /sla/lo/{lo_id}                                   Per-LO SLA metrics
  - PUT /sla/targets                                      Update org-level SLA targets (admin only)
  - PUT /appointment-types/{type_id}/sla-targets          Update per-type SLA targets (admin only)
  - GET /appointment-types/{type_id}/sla-targets          Get effective SLA targets for a type (admin only)

All endpoints require authentication and are scoped to the user's organization.
"""

from datetime import date as date_type
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
)
from services.appointment_sla_service import (
    check_sla_compliance,
    get_sla_breaches,
    get_lo_sla_metrics,
    get_sla_targets,
    DEFAULT_SLA_TARGETS,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# PYDANTIC RESPONSE MODELS
# =============================================================================

class SLAMetricDetail(BaseModel):
    """Individual SLA metric with compliance status."""
    metric: str = Field(..., description="Machine-readable metric key")
    display_name: str = Field(..., description="Human-readable metric name")
    target: str = Field(..., description="Target value (formatted)")
    current_value: str = Field(..., description="Current measured value (formatted)")
    compliant: bool = Field(..., description="Whether the metric meets the target")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional metric details")


class SLADashboardResponse(BaseModel):
    """SLA compliance dashboard with all metrics."""
    organization_id: int
    period_days: int = Field(..., description="Lookback period in days")
    overall_compliance_score: float = Field(..., description="Percentage of metrics that are compliant")
    compliant_count: int = Field(..., description="Number of compliant metrics")
    total_metrics: int = Field(..., description="Total number of tracked metrics")
    metrics: List[SLAMetricDetail] = Field(default_factory=list)
    recent_breach_count: int = Field(0, description="SLA breaches in the last 7 days")
    targets: Dict[str, Any] = Field(default_factory=dict, description="Current SLA target values")

    model_config = ConfigDict(from_attributes=True)


class SLABreachItem(BaseModel):
    """A single SLA breach record."""
    breach_type: str = Field(..., description="Type of SLA breach")
    severity: str = Field("warning", description="Breach severity: warning or critical")
    entity_type: str = Field(..., description="Type of entity (lead, appointment)")
    entity_id: int = Field(..., description="ID of the breached entity")
    entity_name: Optional[str] = Field(None, description="Name for display")
    lo_id: Optional[int] = Field(None, description="Assigned LO ID if applicable")
    target_hours: Optional[float] = Field(None, description="SLA target in hours")
    actual_hours: Optional[float] = Field(None, description="Actual elapsed hours")
    message: str = Field(..., description="Human-readable breach description")
    detected_at: Optional[str] = Field(None, description="ISO timestamp of detection")


class SLABreachesResponse(BaseModel):
    """List of recent SLA breaches."""
    period_days: int = Field(..., description="Lookback period in days")
    total_breaches: int = Field(0, description="Total number of breaches")
    critical_count: int = Field(0, description="Number of critical breaches")
    warning_count: int = Field(0, description="Number of warning breaches")
    breaches: List[SLABreachItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TimeToFirstAppointment(BaseModel):
    """Time-to-first-appointment metrics for an LO."""
    avg_hours: Optional[float] = None
    median_hours: Optional[float] = None
    target_hours: float = 48
    total_leads_with_appointments: int = 0
    compliant: bool = True


class CompletionRate(BaseModel):
    """Appointment completion rate for an LO."""
    rate: float = 0
    total: int = 0
    completed: int = 0


class NoShowRate(BaseModel):
    """No-show rate with trend for an LO."""
    rate: float = 0
    total: int = 0
    no_shows: int = 0
    trend: str = "stable"


class RescheduleResponse(BaseModel):
    """Reschedule response time for an LO."""
    avg_hours: Optional[float] = None
    target_hours: float = 4
    compliant: bool = True


class LOSLAMetricsResponse(BaseModel):
    """Per-LO SLA metrics response."""
    lo_id: int
    lo_name: str = ""
    period_days: int = 30
    time_to_first_appointment: TimeToFirstAppointment = Field(default_factory=TimeToFirstAppointment)
    completion_rate: CompletionRate = Field(default_factory=CompletionRate)
    no_show_rate: NoShowRate = Field(default_factory=NoShowRate)
    reschedule_response: RescheduleResponse = Field(default_factory=RescheduleResponse)

    model_config = ConfigDict(from_attributes=True)


class SLATargetsUpdate(BaseModel):
    """Request body for updating SLA targets."""
    time_to_first_appointment_hours: Optional[float] = Field(
        None, ge=1, le=168, description="Hours target for lead -> first appointment (1-168)"
    )
    appointment_confirmation_minutes: Optional[float] = Field(
        None, ge=1, le=1440, description="Minutes target for booking -> confirmation (1-1440)"
    )
    reminder_lead_time_hours: Optional[float] = Field(
        None, ge=1, le=72, description="Hours before appointment to send reminder (1-72)"
    )
    reschedule_response_hours: Optional[float] = Field(
        None, ge=0.5, le=48, description="Hours target for reschedule response (0.5-48)"
    )
    post_appointment_followup_hours: Optional[float] = Field(
        None, ge=1, le=72, description="Hours target for post-appointment follow-up (1-72)"
    )


class SLATargetsResponse(BaseModel):
    """Response after updating SLA targets."""
    organization_id: int
    targets: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


# =============================================================================
# SLA DASHBOARD
# =============================================================================

@router.get("/sla/dashboard", response_model=SLADashboardResponse)
async def sla_dashboard(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
    db: Session = Depends(get_db),
):
    """
    SLA compliance dashboard showing all tracked metrics.

    Returns overall compliance score, individual metric status, and recent
    breach count. Available to all authenticated users; results are scoped
    to the user's organization.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(period, 30)

    try:
        data = check_sla_compliance(db, models, org_id, days=days)
        return SLADashboardResponse(**data)
    except Exception as e:
        logger.exception(f"SLA dashboard failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute SLA dashboard")


# =============================================================================
# SLA BREACHES
# =============================================================================

@router.get("/sla/breaches", response_model=SLABreachesResponse)
async def sla_breaches(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
    severity: Optional[str] = Query(None, pattern="^(critical|warning)$", description="Filter by severity"),
    breach_type: Optional[str] = Query(None, description="Filter by breach type"),
    db: Session = Depends(get_db),
):
    """
    List recent SLA breaches with details.

    Returns breaches sorted by severity (critical first) then by hours elapsed.
    Available to all authenticated users; results are scoped to the user's organization.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    try:
        breaches = get_sla_breaches(db, models, org_id, days=days)

        # Apply filters
        if severity:
            breaches = [b for b in breaches if b.get("severity") == severity]
        if breach_type:
            breaches = [b for b in breaches if b.get("breach_type") == breach_type]

        critical_count = sum(1 for b in breaches if b.get("severity") == "critical")
        warning_count = sum(1 for b in breaches if b.get("severity") == "warning")

        return SLABreachesResponse(
            period_days=days,
            total_breaches=len(breaches),
            critical_count=critical_count,
            warning_count=warning_count,
            breaches=[SLABreachItem(**b) for b in breaches],
        )
    except Exception as e:
        logger.exception(f"SLA breaches failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SLA breaches")


# =============================================================================
# PER-LO SLA METRICS
# =============================================================================

@router.get("/sla/lo/{lo_id}", response_model=LOSLAMetricsResponse)
async def sla_lo_metrics(
    request: Request,
    lo_id: int,
    period: str = Query("30d", pattern="^(7d|30d|90d)$", description="Time period"),
    db: Session = Depends(get_db),
):
    """
    Get SLA metrics for a specific loan officer.

    Non-admins can only view their own metrics. Admins can view any LO.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    # Authorization: non-admins can only see their own data
    if lo_id != current_user.id and not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can view other users' SLA metrics")

    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(period, 30)

    try:
        data = get_lo_sla_metrics(db, models, org_id, lo_id=lo_id, days=days)

        if "error" in data:
            raise HTTPException(status_code=503, detail=data["error"])

        return LOSLAMetricsResponse(
            lo_id=data["lo_id"],
            lo_name=data.get("lo_name", ""),
            period_days=data["period_days"],
            time_to_first_appointment=TimeToFirstAppointment(**data.get("time_to_first_appointment", {})),
            completion_rate=CompletionRate(**data.get("completion_rate", {})),
            no_show_rate=NoShowRate(**data.get("no_show_rate", {})),
            reschedule_response=RescheduleResponse(**data.get("reschedule_response", {})),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"LO SLA metrics failed for lo_id={lo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute LO SLA metrics")


# =============================================================================
# UPDATE SLA TARGETS (admin only)
# =============================================================================

@router.put("/sla/targets", response_model=SLATargetsResponse)
async def update_sla_targets(
    request: Request,
    body: SLATargetsUpdate,
    db: Session = Depends(get_db),
):
    """
    Update SLA targets for the organization.

    Only admins can modify SLA targets. Targets are stored in the org-level
    SchedulerConfig record (user_id IS NULL) as a JSON field.

    Only non-null fields in the request body are updated; others retain
    their current values.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required to update SLA targets")

    SchedulerConfig = models.get("SchedulerConfig")
    if not SchedulerConfig:
        raise HTTPException(status_code=503, detail="SchedulerConfig model not available")

    try:
        # Get or create org-level config
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.organization_id == org_id,
            SchedulerConfig.user_id.is_(None),
        ).first()

        if not config:
            # Create org-level config if it doesn't exist
            config = SchedulerConfig(
                organization_id=org_id,
                user_id=None,
                is_active=True,
            )
            db.add(config)
            db.flush()

        # Merge updates into existing sla_targets
        existing_targets = {}
        if hasattr(config, "sla_targets") and config.sla_targets:
            existing_targets = dict(config.sla_targets)

        # Apply non-null updates
        update_data = body.dict(exclude_none=True)
        if update_data:
            existing_targets.update(update_data)

            # Store back on config
            if hasattr(config, "sla_targets"):
                config.sla_targets = existing_targets
            else:
                # If sla_targets column doesn't exist yet, store in the
                # general-purpose settings JSON if available
                if hasattr(config, "settings") and isinstance(config.settings, dict):
                    config.settings["sla_targets"] = existing_targets
                else:
                    logger.warning("SchedulerConfig has no sla_targets or settings column")

        db.commit()

        # Return merged targets
        final_targets = get_sla_targets(db, models, org_id)

        return SLATargetsResponse(
            organization_id=org_id,
            targets=final_targets,
            message=f"Updated {len(update_data)} SLA target(s)" if update_data else "No changes",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to update SLA targets: {e}")
        raise HTTPException(status_code=500, detail="Failed to update SLA targets")


# =============================================================================
# PER-APPOINTMENT-TYPE SLA TARGETS (admin only)
# =============================================================================

class AppointmentTypeSLATargetsUpdate(BaseModel):
    """Request body for updating per-appointment-type SLA target overrides."""
    time_to_first_appointment_hours: Optional[float] = Field(
        None, ge=1, le=168,
        description="Hours from lead creation to first scheduled appointment (1-168). "
                    "Set null to clear override and inherit org/system default.",
    )
    appointment_confirmation_minutes: Optional[float] = Field(
        None, ge=1, le=1440,
        description="Minutes from booking creation to confirmation sent (1-1440). "
                    "Set null to clear override.",
    )
    reminder_lead_time_hours: Optional[float] = Field(
        None, ge=1, le=72,
        description="Hours before appointment to send reminder (1-72). "
                    "Set null to clear override.",
    )
    reschedule_response_hours: Optional[float] = Field(
        None, ge=0.5, le=48,
        description="Hours to respond to a reschedule request (0.5-48). "
                    "Set null to clear override.",
    )
    post_appointment_followup_hours: Optional[float] = Field(
        None, ge=1, le=72,
        description="Hours after appointment completion to send follow-up (1-72). "
                    "Set null to clear override.",
    )

    class Config:
        # Allow extra fields to be rejected cleanly
        extra = "forbid"


class AppointmentTypeSLATargetsResponse(BaseModel):
    """Response with per-type SLA target overrides and effective (merged) targets."""
    appointment_type_id: int
    type_name: str = ""
    organization_id: int
    # The raw overrides stored on this type (may be null/empty)
    type_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides stored specifically on this appointment type",
    )
    # The fully resolved targets (system defaults + org overrides + type overrides)
    effective_targets: Dict[str, Any] = Field(
        default_factory=dict,
        description="Effective targets after merging all levels of precedence",
    )
    message: str = ""

    model_config = ConfigDict(from_attributes=True)


# Known SLA target keys — used for validation of incoming override payloads
_KNOWN_SLA_KEYS = set(DEFAULT_SLA_TARGETS.keys())


@router.put(
    "/appointment-types/{type_id}/sla-targets",
    response_model=AppointmentTypeSLATargetsResponse,
)
async def update_appointment_type_sla_targets(
    request: Request,
    type_id: int,
    body: AppointmentTypeSLATargetsUpdate,
    db: Session = Depends(get_db),
):
    """
    Update per-appointment-type SLA target overrides (admin only).

    These overrides take the highest precedence — they override both the
    system defaults and any org-level targets set via PUT /sla/targets.

    Only the fields supplied in the request body are stored as overrides.
    Omitted fields are left at None (inherit from org/system). To clear an
    existing override, omit the field or pass null explicitly.

    Valid keys: time_to_first_appointment_hours, appointment_confirmation_minutes,
    reminder_lead_time_hours, reschedule_response_hours, post_appointment_followup_hours.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required to update appointment type SLA targets")

    AppointmentType = models.get("AppointmentType")
    if not AppointmentType:
        raise HTTPException(status_code=503, detail="AppointmentType model not available")

    try:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == type_id,
            AppointmentType.organization_id == org_id,
        ).first()

        if not appt_type:
            raise HTTPException(status_code=404, detail=f"Appointment type {type_id} not found")

        # Build the override dict from non-null fields only
        update_data = {k: v for k, v in body.dict().items() if v is not None}

        # Validate keys (belt-and-suspenders: Pydantic already limits fields via extra="forbid")
        unknown_keys = set(update_data.keys()) - _KNOWN_SLA_KEYS
        if unknown_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown SLA target keys: {sorted(unknown_keys)}. "
                       f"Valid keys: {sorted(_KNOWN_SLA_KEYS)}",
            )

        # Merge with existing type overrides (so partial updates don't wipe other keys)
        existing_overrides = {}
        if hasattr(appt_type, "sla_targets") and appt_type.sla_targets:
            existing_overrides = dict(appt_type.sla_targets)

        existing_overrides.update(update_data)

        # Persist
        appt_type.sla_targets = existing_overrides if existing_overrides else None
        db.commit()
        db.refresh(appt_type)

        # Return effective (merged) targets so the caller can see what will actually apply
        effective = get_sla_targets(db, models, org_id, appointment_type_id=type_id)

        type_name = getattr(appt_type, "type_name", "") or ""
        stored_overrides = appt_type.sla_targets or {}

        return AppointmentTypeSLATargetsResponse(
            appointment_type_id=type_id,
            type_name=type_name,
            organization_id=org_id,
            type_overrides=stored_overrides,
            effective_targets=effective,
            message=f"Updated {len(update_data)} SLA override(s) for '{type_name}'" if update_data else "No changes",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to update SLA targets for appointment type {type_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update appointment type SLA targets")


@router.get(
    "/appointment-types/{type_id}/sla-targets",
    response_model=AppointmentTypeSLATargetsResponse,
)
async def get_appointment_type_sla_targets(
    request: Request,
    type_id: int,
    db: Session = Depends(get_db),
):
    """
    Get the effective SLA targets for a specific appointment type (admin only).

    Returns both the raw per-type overrides stored on this type, and the
    fully resolved effective targets after merging system defaults,
    org-level overrides, and per-type overrides.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    if not _is_scheduler_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required to view appointment type SLA targets")

    AppointmentType = models.get("AppointmentType")
    if not AppointmentType:
        raise HTTPException(status_code=503, detail="AppointmentType model not available")

    try:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == type_id,
            AppointmentType.organization_id == org_id,
        ).first()

        if not appt_type:
            raise HTTPException(status_code=404, detail=f"Appointment type {type_id} not found")

        effective = get_sla_targets(db, models, org_id, appointment_type_id=type_id)
        type_name = getattr(appt_type, "type_name", "") or ""
        stored_overrides = appt_type.sla_targets or {}

        return AppointmentTypeSLATargetsResponse(
            appointment_type_id=type_id,
            type_name=type_name,
            organization_id=org_id,
            type_overrides=stored_overrides,
            effective_targets=effective,
            message="",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get SLA targets for appointment type {type_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve appointment type SLA targets")
