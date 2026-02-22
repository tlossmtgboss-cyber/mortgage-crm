"""
SOC 2 Compliance API Router
Provides endpoints for audit log queries, incident management,
compliance dashboard, and report generation.

Mount at: /api/v1/compliance
"""
from fastapi import APIRouter

from .audit_endpoints import router as audit_router
from .incident_endpoints import router as incident_router
from .compliance_endpoints import router as compliance_router

soc2_router = APIRouter()

soc2_router.include_router(
    audit_router,
    prefix="/audit",
    tags=["SOC 2 — Audit Logs"],
)

soc2_router.include_router(
    incident_router,
    prefix="/incidents",
    tags=["SOC 2 — Incidents"],
)

soc2_router.include_router(
    compliance_router,
    prefix="/dashboard",
    tags=["SOC 2 — Compliance Dashboard"],
)
