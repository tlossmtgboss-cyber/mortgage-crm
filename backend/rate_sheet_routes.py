"""
Rate Sheet Routes
API endpoints for rate sheet upload, parsing, and refinance opportunity management.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from decimal import Decimal

from database import get_db
from middleware.webhook_verification import require_vapi_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rate-monitor", tags=["rate-monitor-sheets"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ScanOpportunitiesRequest(BaseModel):
    min_savings: Optional[float] = Field(None, description="Minimum monthly savings threshold")
    min_rate_drop: Optional[float] = Field(None, description="Minimum rate drop percentage")


class UpdateOpportunityRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class BulkOutreachRequest(BaseModel):
    opportunity_ids: List[int]
    skip_sms: bool = False


class OutreachRequest(BaseModel):
    skip_sms: bool = False
    custom_message: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_current_user_flexible():
    """Get current user - flexible for auth or no auth."""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# =============================================================================
# RATE SHEET ENDPOINTS
# =============================================================================

@router.post("/sheets/upload")
async def upload_rate_sheet(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """
    Upload a rate sheet (PDF or Excel).
    The file will be parsed asynchronously.
    """
    from models.rate_sheet import RateSheet
    from services.rate_sheet_parser_service import RateSheetParserService

    # Validate file type by extension
    filename = file.filename.lower() if file.filename else ""
    allowed_extensions = ['.pdf', '.xlsx', '.xls', '.csv']
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(allowed_extensions)}"
        )

    # Rate sheet MIME types (PDF, Excel, CSV)
    _RATE_SHEET_MIMES = {
        'application/pdf',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/csv', 'text/plain', 'application/csv',
        # Some systems send .xls as octet-stream
        'application/octet-stream',
    }

    # Run full security pipeline: MIME check, magic bytes, malware scan,
    # PDF sanitization (if PDF)
    from middleware.upload_security import secure_upload
    sec_result = await secure_upload(
        file,
        max_size=10 * 1024 * 1024,  # 10 MB
        allowed_mimes=_RATE_SHEET_MIMES,
    )
    file_content = sec_result.file_bytes

    if sec_result.sanitization_log:
        logger.info(
            "Upload security for rate sheet %s: %s",
            file.filename,
            "; ".join(sec_result.sanitization_log),
        )

    # Calculate hash to check for duplicates
    parser_service = RateSheetParserService(db)
    file_hash = parser_service.calculate_file_hash(file_content)

    # Check for existing sheet with same hash
    existing = db.query(RateSheet).filter(RateSheet.file_hash == file_hash).first()
    if existing:
        return {
            'success': False,
            'error': 'Duplicate file - this rate sheet was already uploaded',
            'existing_sheet_id': existing.id,
            'existing_sheet': existing.to_dict(),
        }

    # Create rate sheet record
    user_id = current_user.id if current_user and hasattr(current_user, 'id') else None

    rate_sheet = RateSheet(
        filename=file.filename,
        file_hash=file_hash,
        status='pending',
        uploaded_by=user_id,
    )
    db.add(rate_sheet)
    db.commit()
    db.refresh(rate_sheet)

    # Parse in background if background tasks available
    if background_tasks:
        background_tasks.add_task(
            _parse_rate_sheet_background,
            db_url=os.getenv("DATABASE_URL"),
            file_content=file_content,
            filename=file.filename,
            rate_sheet_id=rate_sheet.id,
        )
    else:
        # Parse synchronously
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            parser_service.parse_rate_sheet(file_content, file.filename, rate_sheet.id)
        )

    return {
        'success': True,
        'rate_sheet_id': rate_sheet.id,
        'filename': file.filename,
        'status': 'processing',
        'message': 'Rate sheet uploaded and parsing started',
    }


async def _parse_rate_sheet_background(
    db_url: str,
    file_content: bytes,
    filename: str,
    rate_sheet_id: int,
):
    """Background task to parse rate sheet."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from services.rate_sheet_parser_service import RateSheetParserService

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        parser = RateSheetParserService(db)
        await parser.parse_rate_sheet(file_content, filename, rate_sheet_id)
    except Exception as e:
        logger.error(f"Background parsing failed for sheet {rate_sheet_id}: {e}")
    finally:
        db.close()


@router.get("/sheets")
async def list_rate_sheets(
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List uploaded rate sheets."""
    try:
        from models.rate_sheet import RateSheet

        query = db.query(RateSheet)

        if status:
            query = query.filter(RateSheet.status == status)

        total = query.count()

        sheets = query.order_by(RateSheet.created_at.desc()).offset(offset).limit(limit).all()

        return {
            'sheets': [sheet.to_dict() for sheet in sheets],
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except Exception as e:
        logger.warning(f"Error fetching rate sheets (table may not exist): {e}")
        return {'sheets': [], 'total': 0, 'limit': limit, 'offset': offset}


@router.get("/sheets/{sheet_id}")
async def get_rate_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
):
    """Get a single rate sheet by ID."""
    from models.rate_sheet import RateSheet

    sheet = db.query(RateSheet).filter(RateSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Rate sheet not found")

    return sheet.to_dict()


@router.get("/sheets/{sheet_id}/rates")
async def get_rate_sheet_rates(
    sheet_id: int,
    loan_type: Optional[str] = None,
    loan_term: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get parsed rates from a rate sheet."""
    from models.rate_sheet import RateSheet, RateSheetRate

    sheet = db.query(RateSheet).filter(RateSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Rate sheet not found")

    query = db.query(RateSheetRate).filter(RateSheetRate.rate_sheet_id == sheet_id)

    if loan_type:
        query = query.filter(RateSheetRate.loan_type == loan_type)
    if loan_term:
        query = query.filter(RateSheetRate.loan_term == loan_term)

    rates = query.order_by(RateSheetRate.rate.asc()).all()

    return {
        'sheet_id': sheet_id,
        'sheet_status': sheet.status,
        'lender_name': sheet.lender_name,
        'effective_date': sheet.effective_date.isoformat() if sheet.effective_date else None,
        'rates': [rate.to_dict() for rate in rates],
        'total': len(rates),
    }


@router.delete("/sheets/{sheet_id}")
async def delete_rate_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """Delete a rate sheet and its parsed rates."""
    from models.rate_sheet import RateSheet

    sheet = db.query(RateSheet).filter(RateSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Rate sheet not found")

    db.delete(sheet)
    db.commit()

    return {'success': True, 'message': f'Rate sheet {sheet_id} deleted'}


@router.post("/sheets/{sheet_id}/scan")
async def scan_for_opportunities(
    sheet_id: int,
    request: ScanOpportunitiesRequest = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """
    Scan funded loans against this rate sheet to find refinance opportunities.
    """
    from services.opportunity_detection_service import OpportunityDetectionService

    detector = OpportunityDetectionService(db)
    user_id = current_user.id if current_user and hasattr(current_user, 'id') else None

    result = await detector.scan_for_opportunities(
        rate_sheet_id=sheet_id,
        min_savings=request.min_savings if request else None,
        min_rate_drop=request.min_rate_drop if request else None,
        created_by=user_id,
    )

    return result


# =============================================================================
# OPPORTUNITY ENDPOINTS
# =============================================================================

@router.get("/opportunities")
async def list_opportunities(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    rate_sheet_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List refinance opportunities."""
    try:
        from services.opportunity_detection_service import OpportunityDetectionService

        detector = OpportunityDetectionService(db)
        return detector.get_opportunities(
            status=status,
            priority=priority,
            rate_sheet_id=rate_sheet_id,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.warning(f"Error fetching opportunities (table may not exist): {e}")
        return {'opportunities': [], 'total': 0, 'limit': limit, 'offset': offset}


@router.get("/opportunities/dashboard")
async def get_opportunities_dashboard(
    db: Session = Depends(get_db),
):
    """Get dashboard metrics for refinance opportunities."""
    try:
        from services.opportunity_detection_service import OpportunityDetectionService

        detector = OpportunityDetectionService(db)
        return detector.get_dashboard_metrics()
    except Exception as e:
        logger.warning(f"Error fetching opportunities dashboard (table may not exist): {e}")
        return {'total': 0, 'by_status': {}, 'by_priority': {}, 'recent': []}


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db),
):
    """Get a single opportunity by ID."""
    from services.opportunity_detection_service import OpportunityDetectionService

    detector = OpportunityDetectionService(db)
    opp = detector.get_opportunity(opportunity_id)

    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return opp


@router.patch("/opportunities/{opportunity_id}")
async def update_opportunity(
    opportunity_id: int,
    request: UpdateOpportunityRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """Update an opportunity's status or notes."""
    from services.opportunity_detection_service import OpportunityDetectionService

    detector = OpportunityDetectionService(db)
    result = detector.update_opportunity_status(
        opportunity_id=opportunity_id,
        status=request.status,
        notes=request.notes,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return result


# =============================================================================
# OUTREACH ENDPOINTS
# =============================================================================

@router.post("/opportunities/{opportunity_id}/outreach")
async def trigger_outreach(
    opportunity_id: int,
    request: OutreachRequest = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """
    Trigger outreach for a single opportunity.
    Sends SMS with savings info, then initiates AI call.
    """
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    result = await outreach.trigger_outreach_sequence(
        opportunity_id=opportunity_id,
        skip_sms=request.skip_sms if request else False,
    )

    return result


@router.post("/opportunities/{opportunity_id}/sms")
async def send_opportunity_sms(
    opportunity_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """Send SMS notification for an opportunity."""
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    result = await outreach.send_opportunity_sms(opportunity_id)

    return result


@router.post("/opportunities/{opportunity_id}/call")
async def initiate_opportunity_call(
    opportunity_id: int,
    custom_message: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """Initiate AI call for an opportunity."""
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    result = await outreach.initiate_opportunity_call(
        opportunity_id=opportunity_id,
        custom_message=custom_message,
    )

    return result


@router.post("/opportunities/bulk-outreach")
async def bulk_outreach(
    request: BulkOutreachRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """
    Trigger outreach for multiple opportunities.
    """
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    result = await outreach.bulk_outreach(
        opportunity_ids=request.opportunity_ids,
        skip_sms=request.skip_sms,
    )

    return result


@router.post("/opportunities/{opportunity_id}/opt-out")
async def mark_opted_out(
    opportunity_id: int,
    db: Session = Depends(get_db),
):
    """Mark an opportunity as opted out."""
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    success = outreach.mark_opted_out(opportunity_id)

    if not success:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {'success': True, 'status': 'opted_out'}


@router.post("/opportunities/{opportunity_id}/convert")
async def mark_converted(
    opportunity_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible()),
):
    """Mark an opportunity as converted."""
    from services.refinance_outreach_service import RefinanceOutreachService

    outreach = RefinanceOutreachService(db)
    success = outreach.mark_converted(opportunity_id, notes)

    if not success:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {'success': True, 'status': 'converted'}


# =============================================================================
# WEBHOOK ENDPOINT
# =============================================================================

@router.post("/webhooks/call-completed")
async def webhook_call_completed(
    request: Request,
    raw_body: bytes = Depends(require_vapi_webhook),
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for VAPI call completion.
    Updates opportunity status based on call outcome.
    Signature verification is handled by the require_vapi_webhook dependency.
    """
    call_data = json.loads(raw_body)
    from services.refinance_outreach_service import RefinanceOutreachService

    vapi_call_id = call_data.get('call_id') or call_data.get('id')
    if not vapi_call_id:
        raise HTTPException(status_code=400, detail="Missing call_id")

    # Idempotency check — deduplicate retried Vapi call-completed webhooks
    from middleware.webhook_idempotency import is_duplicate_webhook
    if is_duplicate_webhook("vapi", f"call-completed:{vapi_call_id}"):
        logger.info("Vapi call-completed webhook duplicate: call_id=%s", vapi_call_id)
        return {'success': True, 'status': 'duplicate'}

    outreach = RefinanceOutreachService(db)
    await outreach.handle_call_completed(vapi_call_id, call_data)

    return {'success': True}
