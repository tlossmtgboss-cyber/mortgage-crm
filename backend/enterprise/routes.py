"""
Enterprise Feature API Routes

Provides FastAPI routes for:
- MFA management
- Audit log access
- GDPR/CCPA compliance
- Health monitoring
- Metrics export
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create routers
mfa_router = APIRouter(prefix="/mfa", tags=["MFA"])
audit_router = APIRouter(prefix="/audit", tags=["Audit"])
compliance_router = APIRouter(prefix="/compliance", tags=["Compliance"])
health_router = APIRouter(prefix="/health", tags=["Health"])
metrics_router = APIRouter(prefix="/metrics", tags=["Metrics"])


# ============================================================================
# Pydantic Models
# ============================================================================

class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: List[str]
    qr_code_data: str


class MFAVerifyRequest(BaseModel):
    code: str
    device_fingerprint: Optional[str] = None


class MFAVerifyResponse(BaseModel):
    success: bool
    message: str
    backup_codes_remaining: Optional[int] = None


class AuditSearchRequest(BaseModel):
    event_type: Optional[str] = None
    actor_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    severity: Optional[str] = None
    limit: int = 100
    offset: int = 0


class DSARRequest(BaseModel):
    request_type: str  # access, erasure, rectification, portability
    notes: Optional[str] = None


class ConsentRequest(BaseModel):
    consent_type: str
    granted: bool


class ConsentResponse(BaseModel):
    consent_id: str
    consent_type: str
    granted: bool
    recorded_at: str


# ============================================================================
# MFA Routes
# ============================================================================

@mfa_router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(request: Request):
    """
    Initialize MFA setup for the current user.

    Returns secret, QR code URI, and backup codes.
    """
    from .security.mfa import MFAService, TOTPManager

    # Get current user from request state (set by auth middleware)
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get database session factory
    db_session_factory = request.app.state.db_session_factory

    mfa_service = MFAService(db_session_factory)
    result = await mfa_service.setup_totp(user.id)

    return MFASetupResponse(**result)


@mfa_router.post("/confirm", response_model=MFAVerifyResponse)
async def confirm_mfa_setup(request: Request, body: MFAVerifyRequest):
    """
    Confirm MFA setup by verifying first code.
    """
    from .security.mfa import MFAService

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    mfa_service = MFAService(db_session_factory)

    result = await mfa_service.confirm_totp_setup(user.id, body.code)

    return MFAVerifyResponse(
        success=result.success,
        message=result.message,
        backup_codes_remaining=result.backup_codes_remaining,
    )


@mfa_router.post("/verify", response_model=MFAVerifyResponse)
async def verify_mfa(request: Request, body: MFAVerifyRequest):
    """
    Verify MFA code during login.
    """
    from .security.mfa import MFAService, MFAMethod

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    mfa_service = MFAService(db_session_factory)

    result = await mfa_service.verify_mfa(
        user.id,
        body.code,
        MFAMethod.TOTP,
        body.device_fingerprint,
    )

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.message,
            headers={"X-Remaining-Attempts": str(result.remaining_attempts or 0)},
        )

    return MFAVerifyResponse(
        success=True,
        message=result.message,
        backup_codes_remaining=result.backup_codes_remaining,
    )


@mfa_router.delete("/disable", response_model=MFAVerifyResponse)
async def disable_mfa(request: Request, body: MFAVerifyRequest):
    """
    Disable MFA for the current user (requires valid code).
    """
    from .security.mfa import MFAService

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    mfa_service = MFAService(db_session_factory)

    result = await mfa_service.disable_mfa(user.id, body.code)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return MFAVerifyResponse(success=True, message=result.message)


@mfa_router.get("/status")
async def get_mfa_status(request: Request):
    """
    Get MFA status for the current user.
    """
    from .security.mfa import MFAService

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    mfa_service = MFAService(db_session_factory)

    is_enabled = await mfa_service.check_mfa_required(user.id)

    return {
        "enabled": is_enabled,
        "method": "totp" if is_enabled else None,
    }


# ============================================================================
# Audit Routes
# ============================================================================

@audit_router.post("/search")
async def search_audit_logs(request: Request, body: AuditSearchRequest):
    """
    Search audit logs with filters.

    Requires admin role.
    """
    from .security.audit import AuditLogger

    user = getattr(request.state, 'user', None)
    if not user or not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")

    db_session_factory = request.app.state.db_session_factory
    audit_logger = AuditLogger(db_session_factory)

    events = await audit_logger.search(
        event_type=body.event_type,
        actor_id=body.actor_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        start_time=body.start_time,
        end_time=body.end_time,
        severity=body.severity,
        limit=body.limit,
        offset=body.offset,
    )

    return {"events": [e.to_dict() for e in events], "count": len(events)}


@audit_router.get("/verify-integrity")
async def verify_audit_integrity(request: Request):
    """
    Verify audit log hash chain integrity.

    Requires admin role.
    """
    from .security.audit import AuditLogger

    user = getattr(request.state, 'user', None)
    if not user or not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")

    db_session_factory = request.app.state.db_session_factory
    audit_logger = AuditLogger(db_session_factory)

    is_valid = audit_logger.verify_chain_integrity()

    return {
        "integrity_valid": is_valid,
        "checked_at": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Compliance Routes (GDPR/CCPA)
# ============================================================================

@compliance_router.post("/dsar/submit")
async def submit_dsar(request: Request, body: DSARRequest):
    """
    Submit a Data Subject Access Request.
    """
    from .compliance.gdpr import DataSubjectRightsService, RequestType

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    dsr_service = DataSubjectRightsService(db_session_factory)

    try:
        request_type = RequestType(body.request_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid request type: {body.request_type}")

    dsar = await dsr_service.submit_request(
        user_id=str(user.id),
        user_email=user.email,
        request_type=request_type,
        notes=body.notes or "",
    )

    return {
        "request_id": dsar.request_id,
        "status": dsar.status.value,
        "due_date": dsar.due_date,
        "message": f"Your {request_type.value} request has been submitted.",
    }


@compliance_router.get("/dsar/{request_id}")
async def get_dsar_status(request: Request, request_id: str):
    """
    Get status of a Data Subject Request.
    """
    from .compliance.gdpr import DataSubjectRightsService

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    dsr_service = DataSubjectRightsService(db_session_factory)

    dsar = await dsr_service.get_request_status(request_id)

    if not dsar:
        raise HTTPException(status_code=404, detail="Request not found")

    # Users can only see their own requests (unless admin)
    if dsar.user_id != str(user.id) and not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Access denied")

    return dsar.to_dict()


@compliance_router.get("/export")
async def export_user_data(request: Request, background_tasks: BackgroundTasks):
    """
    Export all user data (Right to Access).
    """
    from .compliance.gdpr import DataSubjectRightsService

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    dsr_service = DataSubjectRightsService(db_session_factory)

    export = await dsr_service.export_user_data(str(user.id))

    return Response(
        content=export.to_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=data_export_{user.id}.json"
        }
    )


@compliance_router.post("/consent")
async def record_consent(request: Request, body: ConsentRequest):
    """
    Record a user consent decision.
    """
    from .compliance.gdpr import ConsentManager, ConsentType

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    consent_manager = ConsentManager(db_session_factory)

    try:
        consent_type = ConsentType(body.consent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid consent type: {body.consent_type}")

    # Get IP from request
    ip_address = request.client.host if request.client else None

    consent_id = await consent_manager.record_consent(
        user_id=str(user.id),
        consent_type=consent_type,
        granted=body.granted,
        source="api",
        ip_address=ip_address,
    )

    return ConsentResponse(
        consent_id=consent_id,
        consent_type=body.consent_type,
        granted=body.granted,
        recorded_at=datetime.utcnow().isoformat(),
    )


@compliance_router.get("/consents")
async def get_all_consents(request: Request):
    """
    Get all consent statuses for the current user.
    """
    from .compliance.gdpr import ConsentManager

    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db_session_factory = request.app.state.db_session_factory
    consent_manager = ConsentManager(db_session_factory)

    consents = await consent_manager.get_all_consents(str(user.id))

    return {"consents": consents}


# ============================================================================
# Health Routes
# ============================================================================

@health_router.get("")
async def health_check(request: Request):
    """
    Deep health check of all components.
    """
    from .observability.health import DeepHealthCheck, HealthStatus

    db_session_factory = getattr(request.app.state, 'db_session_factory', None)
    health = DeepHealthCheck(db_session_factory=db_session_factory)

    report = await health.check_all()

    status_code = 200 if report.status == HealthStatus.HEALTHY else 503

    return JSONResponse(
        content=report.to_dict(),
        status_code=status_code,
    )


@health_router.get("/live")
async def liveness_probe(request: Request):
    """
    Kubernetes liveness probe - is the process alive?
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@health_router.get("/ready")
async def readiness_probe(request: Request):
    """
    Kubernetes readiness probe - can we accept traffic?
    """
    from .observability.health import DeepHealthCheck

    db_session_factory = getattr(request.app.state, 'db_session_factory', None)
    health = DeepHealthCheck(db_session_factory=db_session_factory)

    result = await health.check_readiness()

    status_code = 200 if result["status"] == "ready" else 503

    return JSONResponse(content=result, status_code=status_code)


# ============================================================================
# Metrics Routes
# ============================================================================

@metrics_router.get("")
async def prometheus_metrics(request: Request):
    """
    Prometheus-compatible metrics endpoint.
    """
    from .observability.metrics import MetricsCollector

    collector = getattr(request.app.state, 'metrics_collector', None)
    if not collector:
        collector = MetricsCollector()

    return Response(
        content=collector.to_prometheus(),
        media_type="text/plain; charset=utf-8",
    )


# ============================================================================
# Router Registration Helper
# ============================================================================

def register_enterprise_routes(app, prefix: str = "/api/v1/enterprise"):
    """
    Register all enterprise routes with a FastAPI application.

    Usage:
        from enterprise.routes import register_enterprise_routes
        register_enterprise_routes(app)
    """
    app.include_router(mfa_router, prefix=prefix)
    app.include_router(audit_router, prefix=prefix)
    app.include_router(compliance_router, prefix=prefix)
    app.include_router(health_router, prefix=prefix)
    app.include_router(metrics_router, prefix=prefix)

    logger.info(f"Enterprise routes registered at {prefix}")
