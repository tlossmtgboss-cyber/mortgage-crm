"""
DSAR (Data Subject Access Request) Routes — CCPA/CPRA Compliance

Endpoints for managing privacy data requests and GLBA notice tracking.
"""

from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy", tags=["Privacy Compliance"])


class DSARCreateRequest(BaseModel):
    request_type: str
    requestor_email: str
    requestor_name: str
    requestor_phone: Optional[str] = None


class PrivacyNoticeRequest(BaseModel):
    borrower_email: str
    notice_version: str = "1.0"
    delivery_method: str = "email"


def register_dsar_routes(app, get_db_func, get_current_user_func):
    from services.privacy_compliance import PrivacyComplianceService

    @router.post("/dsar")
    async def create_dsar(
        request: DSARCreateRequest,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")

        service = PrivacyComplianceService(db, org_id)
        dsar = service.create_dsar(
            request_type=request.request_type,
            requestor_email=request.requestor_email,
            requestor_name=request.requestor_name,
            requestor_phone=request.requestor_phone,
        )
        return {
            "id": dsar.id,
            "status": dsar.status.value,
            "deadline": dsar.deadline.isoformat(),
            "submitted_at": dsar.submitted_at.isoformat(),
        }

    @router.post("/dsar/{dsar_id}/verify")
    async def verify_dsar_identity(
        dsar_id: str,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        service = PrivacyComplianceService(db, org_id)
        dsar = service.verify_identity(dsar_id, verified_by=str(current_user.id))
        return {"id": dsar.id, "status": dsar.status.value, "identity_verified": True}

    @router.post("/dsar/{dsar_id}/process")
    async def process_dsar(
        dsar_id: str,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        service = PrivacyComplianceService(db, org_id)

        dsar = service._load_dsar(dsar_id)
        if not dsar:
            raise HTTPException(status_code=404, detail="DSAR not found")

        if dsar.request_type.value == "access":
            result = service.process_access_request(dsar_id, str(current_user.id))
        elif dsar.request_type.value == "delete":
            result = service.process_deletion_request(dsar_id, str(current_user.id))
        elif dsar.request_type.value == "opt_out":
            result = service.process_opt_out(dsar_id, str(current_user.id))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported type: {dsar.request_type.value}")

        return {
            "id": result.id,
            "status": result.status.value,
            "response_data": result.response_data,
        }

    @router.post("/dsar/{dsar_id}/complete")
    async def complete_dsar(
        dsar_id: str,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        service = PrivacyComplianceService(db, org_id)
        dsar = service.complete_dsar(dsar_id, str(current_user.id))
        return {
            "id": dsar.id,
            "status": dsar.status.value,
            "completed_at": dsar.completed_at.isoformat() if dsar.completed_at else None,
        }

    @router.get("/dsar/overdue")
    async def get_overdue_dsars(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        service = PrivacyComplianceService(db, org_id)
        overdue = service.get_overdue_dsars()
        return {
            "overdue_count": len(overdue),
            "requests": [
                {
                    "id": d.id,
                    "type": d.request_type.value,
                    "email": d.requestor_email,
                    "deadline": d.deadline.isoformat(),
                    "status": d.status.value,
                }
                for d in overdue
            ],
        }

    @router.post("/glba/notice")
    async def record_privacy_notice(
        request: PrivacyNoticeRequest,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_func),
    ):
        org_id = getattr(current_user, "organization_id", None)
        service = PrivacyComplianceService(db, org_id)
        return service.record_privacy_notice_delivery(
            borrower_email=request.borrower_email,
            notice_version=request.notice_version,
            delivery_method=request.delivery_method,
        )

    app.include_router(router)
