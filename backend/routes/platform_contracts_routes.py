"""
Platform Contracts API Routes

REST API endpoints for managing licensing agreements, contracts, and
e-signed documents between the platform and CRM licensees.

All endpoints require Platform Administrator access.
"""

import logging
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel

from database import get_db
from main import get_current_user
from utils.auth import require_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/platform-contracts", tags=["Platform Contracts"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ContractCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    contract_type: str = "license_agreement"
    organization_id: int
    client_profile_id: Optional[int] = None
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    auto_renew: bool = False
    renewal_term_months: Optional[int] = None
    contract_value: Optional[float] = None
    billing_frequency: Optional[str] = None
    signer_name: Optional[str] = None
    signer_email: Optional[str] = None
    signer_title: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class ContractUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    contract_type: Optional[str] = None
    status: Optional[str] = None
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    auto_renew: Optional[bool] = None
    renewal_term_months: Optional[int] = None
    contract_value: Optional[float] = None
    billing_frequency: Optional[str] = None
    signer_name: Optional[str] = None
    signer_email: Optional[str] = None
    signer_title: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


# =============================================================================
# Constants & Helpers
# =============================================================================

VALID_STATUSES = {"draft", "sent", "viewed", "signed", "expired", "voided"}
VALID_TYPES = {"license_agreement", "addendum", "nda", "service_agreement"}


def _parse_date(date_str: Optional[str]):
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return datetime.fromisoformat(date_str).date()


# =============================================================================
# Routes
# =============================================================================

@router.get("/summary")
async def get_contracts_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get KPI summary cards for platform contracts."""
    from database.models.platform_contract import PlatformContract

    require_platform_admin(current_user)

    total = db.query(func.count(PlatformContract.id)).scalar() or 0
    signed = db.query(func.count(PlatformContract.id)).filter(
        PlatformContract.status == "signed"
    ).scalar() or 0
    pending = db.query(func.count(PlatformContract.id)).filter(
        PlatformContract.status.in_(["sent", "viewed"])
    ).scalar() or 0
    drafts = db.query(func.count(PlatformContract.id)).filter(
        PlatformContract.status == "draft"
    ).scalar() or 0

    thirty_days = date.today() + timedelta(days=30)
    expiring = db.query(func.count(PlatformContract.id)).filter(
        and_(
            PlatformContract.status == "signed",
            PlatformContract.expiration_date != None,
            PlatformContract.expiration_date <= thirty_days,
            PlatformContract.expiration_date >= date.today(),
        )
    ).scalar() or 0

    total_value = db.query(func.sum(PlatformContract.contract_value)).filter(
        PlatformContract.status == "signed"
    ).scalar() or 0

    return {
        "total": total,
        "signed": signed,
        "pending_signature": pending,
        "drafts": drafts,
        "expiring_soon": expiring,
        "total_contract_value": round(float(total_value), 2),
    }


@router.get("/")
async def list_contracts(
    status: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List platform contracts with optional filters."""
    from database.models.platform_contract import PlatformContract
    from database.models.core import Organization

    require_platform_admin(current_user)

    query = db.query(PlatformContract)

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.filter(PlatformContract.status == status)

    if contract_type:
        if contract_type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid contract_type: {contract_type}")
        query = query.filter(PlatformContract.contract_type == contract_type)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                PlatformContract.title.ilike(search_term),
                PlatformContract.signer_name.ilike(search_term),
                PlatformContract.signer_email.ilike(search_term),
                PlatformContract.description.ilike(search_term),
            )
        )

    total = query.count()
    contracts = query.order_by(PlatformContract.created_at.desc()).offset(
        (page - 1) * limit
    ).limit(limit).all()

    # Enrich with organization name
    org_ids = list(set(c.organization_id for c in contracts if c.organization_id))
    orgs = {}
    if org_ids:
        org_rows = db.query(Organization.id, Organization.name).filter(
            Organization.id.in_(org_ids)
        ).all()
        orgs = {row.id: row.name for row in org_rows}

    items = []
    for c in contracts:
        d = c.to_dict()
        d["organization_name"] = orgs.get(c.organization_id, "Unknown")
        items.append(d)

    return {
        "contracts": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/{contract_id}")
async def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get single contract detail."""
    from database.models.platform_contract import PlatformContract
    from database.models.core import Organization

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    data = contract.to_dict()
    if contract.organization_id:
        org = db.query(Organization.name).filter(
            Organization.id == contract.organization_id
        ).scalar()
        data["organization_name"] = org or "Unknown"

    return data


@router.post("/")
async def create_contract(
    body: ContractCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a draft contract."""
    from database.models.platform_contract import PlatformContract
    from database.models.core import Organization

    require_platform_admin(current_user)

    if body.contract_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid contract_type: {body.contract_type}")

    org = db.query(Organization).filter(Organization.id == body.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {body.organization_id} not found")

    try:
        contract = PlatformContract(
            organization_id=body.organization_id,
            client_profile_id=body.client_profile_id,
            title=body.title,
            description=body.description,
            contract_type=body.contract_type,
            status="draft",
            effective_date=_parse_date(body.effective_date),
            expiration_date=_parse_date(body.expiration_date),
            auto_renew=body.auto_renew,
            renewal_term_months=body.renewal_term_months,
            contract_value=body.contract_value,
            billing_frequency=body.billing_frequency,
            signer_name=body.signer_name,
            signer_email=body.signer_email,
            signer_title=body.signer_title,
            notes=body.notes,
            tags=body.tags,
            created_by_user_id=current_user.id,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        data = contract.to_dict()
        data["organization_name"] = org.name
        return data
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating contract: {e}")
        raise HTTPException(status_code=500, detail="Failed to create contract")


@router.put("/{contract_id}")
async def update_contract(
    contract_id: int,
    body: ContractUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a contract."""
    from database.models.platform_contract import PlatformContract

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    update_data = body.dict(exclude_unset=True)

    if "status" in update_data and update_data["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")
    if "contract_type" in update_data and update_data["contract_type"] not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid contract_type: {update_data['contract_type']}")

    for date_field in ["effective_date", "expiration_date"]:
        if date_field in update_data:
            update_data[date_field] = _parse_date(update_data[date_field])

    try:
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in update_data.items():
            if key not in _protected:
                setattr(contract, key, value)

        contract.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(contract)
        return contract.to_dict()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update contract")


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Void or delete a contract."""
    from database.models.platform_contract import PlatformContract

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    try:
        if contract.status == "signed":
            contract.status = "voided"
            contract.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"message": "Signed contract has been voided", "id": contract_id}

        db.delete(contract)
        db.commit()
        return {"message": "Contract deleted", "id": contract_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete contract")


@router.post("/{contract_id}/upload-pdf")
async def upload_contract_pdf(
    contract_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload a contract PDF to S3."""
    from database.models.platform_contract import PlatformContract
    from services.perennia_s3_service import PerenniaS3Service

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    unique_id = uuid.uuid4().hex
    storage_key = f"contracts/{contract_id}/{unique_id}.pdf"

    try:
        s3 = PerenniaS3Service()
        result = s3.upload_file(
            storage_key=storage_key,
            file_content=content,
            content_type="application/pdf",
            metadata={"contract_id": str(contract_id), "original_name": file.filename},
        )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))

        contract.pdf_storage_key = storage_key
        contract.pdf_file_name = file.filename
        contract.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "message": "PDF uploaded successfully",
            "storage_key": storage_key,
            "file_name": file.filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading PDF for contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload PDF")


@router.get("/{contract_id}/download-url")
async def get_download_url(
    contract_id: int,
    signed: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get presigned S3 download URL for contract PDF."""
    from database.models.platform_contract import PlatformContract
    from services.perennia_s3_service import PerenniaS3Service

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if signed:
        storage_key = contract.signed_pdf_storage_key
        file_name = f"signed_{contract.pdf_file_name or 'contract.pdf'}"
    else:
        storage_key = contract.pdf_storage_key
        file_name = contract.pdf_file_name or "contract.pdf"

    if not storage_key:
        raise HTTPException(status_code=404, detail="No PDF available for this contract")

    s3 = PerenniaS3Service()
    result = s3.get_presigned_download_url(
        storage_key=storage_key,
        file_name=file_name,
        expires_in=300,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate URL"))

    return {
        "download_url": result["presigned_url"],
        "file_name": file_name,
        "expires_in": result["expires_in"],
    }


@router.post("/{contract_id}/send-for-signature")
async def send_for_signature(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create an EsignEnvelope and send contract for signature."""
    from database.models.platform_contract import PlatformContract

    require_platform_admin(current_user)

    contract = db.query(PlatformContract).filter(
        PlatformContract.id == contract_id
    ).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not contract.pdf_storage_key:
        raise HTTPException(status_code=400, detail="Upload a PDF before sending for signature")

    if not contract.signer_email:
        raise HTTPException(status_code=400, detail="Signer email is required")

    if contract.status not in ("draft", "sent"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send contract with status '{contract.status}' for signature"
        )

    try:
        from models.esign_models import create_esign_models
        EsignEnvelope, EsignSigner, _EsignField = create_esign_models(db.bind)

        envelope = EsignEnvelope(
            name=contract.title,
            status="sent",
            organization_id=contract.organization_id,
            created_by_user_id=current_user.id,
        )
        db.add(envelope)
        db.flush()

        signer = EsignSigner(
            envelope_id=envelope.id,
            name=contract.signer_name or "Signer",
            email=contract.signer_email,
            title=contract.signer_title,
            order_number=1,
            status="pending",
        )
        db.add(signer)
        db.flush()

        contract.esign_envelope_id = envelope.id
        contract.status = "sent"
        contract.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "message": "Contract sent for signature",
            "envelope_id": envelope.id,
            "signer_email": contract.signer_email,
            "status": "sent",
        }
    except ImportError:
        logger.warning("Esign models not available, marking contract as sent without envelope")
        contract.status = "sent"
        contract.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "message": "Contract marked as sent (esign system unavailable)",
            "status": "sent",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error sending contract {contract_id} for signature: {e}")
        raise HTTPException(status_code=500, detail="Failed to send for signature")
