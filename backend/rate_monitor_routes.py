"""
Rate Monitor API Routes
Endpoints for managing rate monitoring targets, alerts, and checking rates.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date
from decimal import Decimal
import logging
import httpx

from database import get_db
from models.rate_monitor import (
    RateMonitorTarget, RateMonitorHistory, RateMonitorAlert,
    OptimalBlueRateCache, calculate_monthly_savings, calculate_annual_savings
)
from services.optimal_blue_service import OptimalBlueService, RateScenario

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rate-monitor", tags=["rate-monitor"])


# =============================================================================
# Pydantic Models
# =============================================================================

class CreateTargetRequest(BaseModel):
    """Request to create a rate monitoring target."""
    mum_client_id: Optional[int] = None
    borrower_name: Optional[str] = None
    borrower_phone: Optional[str] = None
    borrower_email: Optional[str] = None
    current_rate: Optional[float] = None
    current_loan_amount: Optional[float] = None
    target_type: str = Field(..., description="savings_threshold, rate_drop_percentage, or manual_target")
    monthly_savings_threshold: Optional[float] = Field(None, description="Monthly savings trigger (e.g., 200 for $200)")
    rate_drop_percentage: Optional[float] = Field(None, description="Rate drop trigger (e.g., 0.5 for 0.5%)")
    target_rate: Optional[float] = Field(None, description="Target rate trigger (e.g., 5.5)")
    loan_type: str = 'conventional'
    loan_term: int = 30
    auto_call_enabled: bool = False
    call_preference: str = 'business_hours'
    notify_email: bool = True
    notify_sms: bool = True
    notify_lo: bool = True
    notes: Optional[str] = None


class UpdateTargetRequest(BaseModel):
    """Request to update a rate monitoring target."""
    target_type: Optional[str] = None
    monthly_savings_threshold: Optional[float] = None
    rate_drop_percentage: Optional[float] = None
    target_rate: Optional[float] = None
    loan_type: Optional[str] = None
    loan_term: Optional[int] = None
    is_active: Optional[bool] = None
    auto_call_enabled: Optional[bool] = None
    call_preference: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_lo: Optional[bool] = None
    notes: Optional[str] = None


class RateCheckRequest(BaseModel):
    """Request to manually check rates for a MUM client."""
    loan_type: Optional[str] = 'conventional'
    loan_term: Optional[int] = 30
    credit_score: Optional[int] = 740
    ltv: Optional[float] = 80.0


class InitiateCallRequest(BaseModel):
    """Request to initiate an AI call for an alert."""
    custom_message: Optional[str] = None


class AlertUpdateRequest(BaseModel):
    """Request to update an alert status."""
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    follow_up_notes: Optional[str] = None
    follow_up_date: Optional[date] = None


class TargetResponse(BaseModel):
    """Response model for a rate target."""
    id: int
    mum_client_id: int
    target_type: str
    monthly_savings_threshold: Optional[float]
    rate_drop_percentage: Optional[float]
    target_rate: Optional[float]
    loan_type: str
    loan_term: int
    status: str
    is_active: bool
    auto_call_enabled: bool
    call_preference: str
    last_triggered_at: Optional[datetime]
    trigger_count: int
    appointment_scheduled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    """Response model for an alert."""
    id: int
    target_id: int
    mum_client_id: Optional[int]
    alert_type: str
    priority: str
    client_rate: Optional[float]
    market_rate: Optional[float]
    monthly_savings: Optional[float]
    annual_savings: Optional[float]
    status: str
    auto_call_attempted: bool
    call_status: Optional[str]
    call_outcome: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Auth Dependency
# =============================================================================

def get_current_user_flexible():
    """Lazy import auth dependency."""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# =============================================================================
# Target Endpoints
# =============================================================================

@router.get("/targets")
async def list_targets(
    mum_client_id: Optional[int] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List rate monitoring targets with optional filters.
    """
    try:
        query = db.query(RateMonitorTarget)

        if mum_client_id:
            query = query.filter(RateMonitorTarget.mum_client_id == mum_client_id)
        if status:
            query = query.filter(RateMonitorTarget.status == status)
        if is_active is not None:
            query = query.filter(RateMonitorTarget.is_active == is_active)

        total = query.count()
        targets = query.order_by(desc(RateMonitorTarget.created_at)).offset(offset).limit(limit).all()
    except Exception as e:
        # Table might not exist yet - return empty response
        logger.warning(f"Error fetching rate monitor targets (table may not exist): {e}")
        return {'targets': [], 'total': 0, 'limit': limit, 'offset': offset}

    # Enrich with MUM client data
    enriched_targets = []
    for target in targets:
        target_dict = target.to_dict()

        # Get MUM client info
        try:
            from main import MUMClient
            mum_client = db.query(MUMClient).filter(MUMClient.id == target.mum_client_id).first()
            if mum_client:
                target_dict['client_name'] = mum_client.client_name
                target_dict['client_rate'] = float(mum_client.interest_rate) if mum_client.interest_rate else None
                target_dict['loan_balance'] = float(mum_client.current_loan_amount) if mum_client.current_loan_amount else None
        except Exception as e:
            logger.warning(f"Could not fetch MUM client data: {e}")

        target_dict['threshold_description'] = target.get_threshold_description()
        enriched_targets.append(target_dict)

    return {
        'targets': enriched_targets,
        'total': total,
        'limit': limit,
        'offset': offset
    }


@router.post("/targets")
async def create_target(
    request: CreateTargetRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new rate monitoring target for a MUM client.
    """
    # Validate target type has corresponding threshold
    if request.target_type == 'savings_threshold' and not request.monthly_savings_threshold:
        raise HTTPException(400, "monthly_savings_threshold required for savings_threshold type")
    if request.target_type == 'rate_drop_percentage' and not request.rate_drop_percentage:
        raise HTTPException(400, "rate_drop_percentage required for rate_drop_percentage type")
    if request.target_type == 'manual_target' and not request.target_rate:
        raise HTTPException(400, "target_rate required for manual_target type")

    # Verify MUM client exists (if provided)
    if request.mum_client_id:
        try:
            from main import MUMClient
            mum_client = db.query(MUMClient).filter(MUMClient.id == request.mum_client_id).first()
            if not mum_client:
                raise HTTPException(404, f"MUM client {request.mum_client_id} not found")
        except ImportError:
            pass  # MUM client model not available

    # Build notes with borrower info if standalone target
    notes = request.notes or ""
    if not request.mum_client_id:
        standalone_info = []
        if request.borrower_name:
            standalone_info.append(f"Borrower: {request.borrower_name}")
        if request.borrower_phone:
            standalone_info.append(f"Phone: {request.borrower_phone}")
        if request.borrower_email:
            standalone_info.append(f"Email: {request.borrower_email}")
        if request.current_rate:
            standalone_info.append(f"Current Rate: {request.current_rate}%")
        if request.current_loan_amount:
            standalone_info.append(f"Loan Amount: ${request.current_loan_amount:,.0f}")
        if standalone_info:
            notes = " | ".join(standalone_info) + ("\n" + notes if notes else "")

    # Create target
    target = RateMonitorTarget(
        mum_client_id=request.mum_client_id,
        borrower_name=request.borrower_name,
        borrower_phone=request.borrower_phone,
        borrower_email=request.borrower_email,
        current_rate=Decimal(str(request.current_rate)) if request.current_rate else None,
        current_loan_amount=Decimal(str(request.current_loan_amount)) if request.current_loan_amount else None,
        target_type=request.target_type,
        monthly_savings_threshold=Decimal(str(request.monthly_savings_threshold)) if request.monthly_savings_threshold else None,
        rate_drop_percentage=Decimal(str(request.rate_drop_percentage)) if request.rate_drop_percentage else None,
        target_rate=Decimal(str(request.target_rate)) if request.target_rate else None,
        loan_type=request.loan_type,
        loan_term=request.loan_term,
        auto_call_enabled=request.auto_call_enabled,
        call_preference=request.call_preference,
        notify_email=request.notify_email,
        notify_sms=request.notify_sms,
        notify_lo=request.notify_lo,
        notes=notes,
        status='active',
        is_active=True,
    )

    db.add(target)
    db.commit()
    db.refresh(target)

    logger.info(f"Created rate monitor target {target.id} for MUM client {request.mum_client_id}")

    return target.to_dict()


@router.get("/targets/{target_id}")
async def get_target(
    target_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific rate monitoring target with history.
    """
    target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == target_id).first()
    if not target:
        raise HTTPException(404, "Target not found")

    result = target.to_dict()

    # Get recent history
    history = db.query(RateMonitorHistory).filter(
        RateMonitorHistory.target_id == target_id
    ).order_by(desc(RateMonitorHistory.check_timestamp)).limit(10).all()

    result['history'] = [h.to_dict() for h in history]

    # Get active alerts
    alerts = db.query(RateMonitorAlert).filter(
        RateMonitorAlert.target_id == target_id,
        RateMonitorAlert.status.in_(['pending', 'acknowledged'])
    ).order_by(desc(RateMonitorAlert.created_at)).all()

    result['alerts'] = [a.to_dict() for a in alerts]

    return result


@router.patch("/targets/{target_id}")
async def update_target(
    target_id: int,
    request: UpdateTargetRequest,
    db: Session = Depends(get_db)
):
    """
    Update a rate monitoring target.
    """
    target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == target_id).first()
    if not target:
        raise HTTPException(404, "Target not found")

    # Update fields
    _protected = {'id', 'mum_client_id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and field not in _protected:
            if field in ['monthly_savings_threshold', 'rate_drop_percentage', 'target_rate']:
                value = Decimal(str(value))
            setattr(target, field, value)

    db.commit()
    db.refresh(target)

    logger.info(f"Updated rate monitor target {target_id}")

    return target.to_dict()


@router.delete("/targets/{target_id}")
async def delete_target(
    target_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a rate monitoring target.
    """
    target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == target_id).first()
    if not target:
        raise HTTPException(404, "Target not found")

    db.delete(target)
    db.commit()

    logger.info(f"Deleted rate monitor target {target_id}")

    return {"status": "deleted", "target_id": target_id}


# =============================================================================
# Rate Checking Endpoints
# =============================================================================

@router.get("/current-rates")
async def get_current_rates(
    loan_type: str = 'conventional',
    credit_score: int = 740,
    ltv: float = 80.0,
    db: Session = Depends(get_db)
):
    """
    Get current market rates for different loan terms.
    """
    service = OptimalBlueService(db)
    rates = {}

    for term in [15, 20, 30]:
        scenario = RateScenario(
            loan_type=loan_type,
            loan_term=term,
            credit_score=credit_score,
            ltv=ltv,
        )
        result = await service.get_rate(scenario)
        rates[f'{term}_year'] = result.to_dict()

    return {
        'rates': rates,
        'loan_type': loan_type,
        'credit_score': credit_score,
        'ltv': ltv,
        'fetched_at': datetime.utcnow().isoformat(),
        'is_mock': rates.get('30_year', {}).get('is_mock', True),
    }


@router.post("/targets/{target_id}/check")
async def check_target_opportunity(
    target_id: int,
    db: Session = Depends(get_db)
):
    """
    Check refinance opportunity for a specific rate monitor target.
    Works with both MUM-linked and standalone targets.
    """
    target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == target_id).first()
    if not target:
        raise HTTPException(404, f"Target {target_id} not found")

    # Get client rate and loan amount from target or MUM client
    client_rate = None
    loan_balance = None
    client_name = target.borrower_name

    if target.current_rate:
        client_rate = float(target.current_rate)
    if target.current_loan_amount:
        loan_balance = float(target.current_loan_amount)

    # If linked to MUM client, get data from there
    if target.mum_client_id:
        try:
            from main import MUMClient
            mum_client = db.query(MUMClient).filter(MUMClient.id == target.mum_client_id).first()
            if mum_client:
                client_name = mum_client.client_name
                if not client_rate and mum_client.interest_rate:
                    client_rate = float(mum_client.interest_rate)
                if not loan_balance and mum_client.current_loan_amount:
                    loan_balance = float(mum_client.current_loan_amount)
        except ImportError:
            pass

    if not client_rate:
        raise HTTPException(400, "No client rate available for this target")
    if not loan_balance:
        loan_balance = 400000  # Default if not specified

    # Get current market rate
    service = OptimalBlueService(db)
    scenario = RateScenario(
        loan_type=target.loan_type or 'conventional',
        loan_term=target.loan_term or 30,
        loan_amount=loan_balance,
        credit_score=740,
        ltv=80.0,
    )
    rate_result = await service.get_rate(scenario)

    # Calculate savings
    market_rate = rate_result.rate
    monthly_savings = calculate_monthly_savings(client_rate, market_rate, loan_balance)
    annual_savings = calculate_annual_savings(monthly_savings)
    rate_difference = client_rate - market_rate

    # Check if threshold is met based on target type
    threshold_met = False
    if target.target_type == 'savings_threshold' and target.monthly_savings_threshold:
        threshold_met = monthly_savings >= float(target.monthly_savings_threshold)
    elif target.target_type == 'rate_drop_percentage' and target.rate_drop_percentage:
        threshold_met = rate_difference >= float(target.rate_drop_percentage)
    elif target.target_type == 'manual_target' and target.target_rate:
        threshold_met = market_rate <= float(target.target_rate)

    # Determine opportunity strength
    if monthly_savings >= 300:
        opportunity_strength = 'strong'
    elif monthly_savings >= 150:
        opportunity_strength = 'moderate'
    elif monthly_savings > 0:
        opportunity_strength = 'weak'
    else:
        opportunity_strength = 'none'

    return {
        'target_id': target_id,
        'client_name': client_name,
        'client_rate': client_rate,
        'market_rate': market_rate,
        'rate_difference': round(rate_difference, 3),
        'loan_balance': loan_balance,
        'monthly_savings': monthly_savings,
        'annual_savings': annual_savings,
        'opportunity_strength': opportunity_strength,
        'threshold_met': threshold_met,
        'threshold_type': target.target_type,
        'threshold_description': target.get_threshold_description(),
        'market_rate_details': rate_result.to_dict(),
        'recommendation': f"Potential savings of ${monthly_savings:,.0f}/month (${annual_savings:,.0f}/year)" if monthly_savings > 0 else "Current rate is competitive",
    }


@router.post("/check-opportunity/{mum_client_id}")
async def check_opportunity(
    mum_client_id: int,
    request: RateCheckRequest = None,
    db: Session = Depends(get_db)
):
    """
    Manually check refinance opportunity for a MUM client.
    Returns savings calculation based on current market rates.
    """
    # Get MUM client
    try:
        from main import MUMClient
        mum_client = db.query(MUMClient).filter(MUMClient.id == mum_client_id).first()
        if not mum_client:
            raise HTTPException(404, f"MUM client {mum_client_id} not found")
    except ImportError:
        raise HTTPException(500, "MUM client model not available")

    # Use provided params or defaults from client
    loan_type = request.loan_type if request else (mum_client.loan_type or 'conventional')
    loan_term = request.loan_term if request else 30
    credit_score = request.credit_score if request else 740
    ltv = request.ltv if request else 80.0

    # Get current market rate
    service = OptimalBlueService(db)
    scenario = RateScenario(
        loan_type=loan_type,
        loan_term=loan_term,
        loan_amount=float(mum_client.current_loan_amount) if mum_client.current_loan_amount else 400000,
        credit_score=credit_score,
        ltv=ltv,
    )
    rate_result = await service.get_rate(scenario)

    # Calculate savings
    client_rate = float(mum_client.interest_rate) if mum_client.interest_rate else 0
    market_rate = rate_result.rate
    loan_balance = float(mum_client.current_loan_amount) if mum_client.current_loan_amount else 0

    monthly_savings = calculate_monthly_savings(client_rate, market_rate, loan_balance)
    annual_savings = calculate_annual_savings(monthly_savings)

    rate_difference = client_rate - market_rate

    # Determine opportunity strength
    if monthly_savings >= 300:
        opportunity_strength = 'strong'
    elif monthly_savings >= 150:
        opportunity_strength = 'moderate'
    elif monthly_savings > 0:
        opportunity_strength = 'weak'
    else:
        opportunity_strength = 'none'

    return {
        'mum_client_id': mum_client_id,
        'client_name': mum_client.client_name,
        'client_rate': client_rate,
        'market_rate': market_rate,
        'rate_difference': round(rate_difference, 3),
        'loan_balance': loan_balance,
        'monthly_savings': monthly_savings,
        'annual_savings': annual_savings,
        'opportunity_strength': opportunity_strength,
        'market_rate_details': rate_result.to_dict(),
        'recommendation': f"Potential savings of ${monthly_savings:,.0f}/month (${annual_savings:,.0f}/year)" if monthly_savings > 0 else "Current rate is competitive",
    }


# =============================================================================
# Alert Endpoints
# =============================================================================

@router.get("/alerts")
async def list_alerts(
    status: Optional[str] = None,
    mum_client_id: Optional[int] = None,
    priority: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List rate monitor alerts with filters.
    """
    query = db.query(RateMonitorAlert)

    if status:
        query = query.filter(RateMonitorAlert.status == status)
    if mum_client_id:
        query = query.filter(RateMonitorAlert.mum_client_id == mum_client_id)
    if priority:
        query = query.filter(RateMonitorAlert.priority == priority)

    total = query.count()
    alerts = query.order_by(desc(RateMonitorAlert.created_at)).offset(offset).limit(limit).all()

    # Enrich with MUM client data
    enriched_alerts = []
    for alert in alerts:
        alert_dict = alert.to_dict()

        try:
            from main import MUMClient
            mum_client = db.query(MUMClient).filter(MUMClient.id == alert.mum_client_id).first()
            if mum_client:
                alert_dict['client_name'] = mum_client.client_name
                alert_dict['client_phone'] = mum_client.phone
                alert_dict['client_email'] = mum_client.email
        except Exception as e:
            logger.warning(f"Could not fetch MUM client data: {e}")

        enriched_alerts.append(alert_dict)

    return {
        'alerts': enriched_alerts,
        'total': total,
        'limit': limit,
        'offset': offset
    }


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific alert with full details.
    """
    alert = db.query(RateMonitorAlert).filter(RateMonitorAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    result = alert.to_dict()

    # Get MUM client info
    try:
        from main import MUMClient
        mum_client = db.query(MUMClient).filter(MUMClient.id == alert.mum_client_id).first()
        if mum_client:
            result['client'] = {
                'id': mum_client.id,
                'name': mum_client.client_name,
                'phone': mum_client.phone,
                'email': mum_client.email,
                'current_rate': float(mum_client.interest_rate) if mum_client.interest_rate else None,
                'loan_balance': float(mum_client.current_loan_amount) if mum_client.current_loan_amount else None,
            }
    except Exception as e:
        logger.warning(f"Could not fetch MUM client data: {e}")

    # Get target info
    if alert.target_id:
        target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == alert.target_id).first()
        if target:
            result['target'] = target.to_dict()

    return result


@router.patch("/alerts/{alert_id}")
async def update_alert(
    alert_id: int,
    request: AlertUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update an alert (status, assignment, notes).
    """
    alert = db.query(RateMonitorAlert).filter(RateMonitorAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    update_data = request.dict(exclude_unset=True)

    # Track status changes
    if 'status' in update_data:
        new_status = update_data['status']
        if new_status == 'acknowledged' and not alert.acknowledged_at:
            alert.acknowledged_at = datetime.utcnow()
        elif new_status in ['converted', 'dismissed'] and not alert.resolved_at:
            alert.resolved_at = datetime.utcnow()

    _protected = {'id', 'target_id', 'mum_client_id', 'organization_id', 'created_at', 'updated_at'}
    for field, value in update_data.items():
        if field not in _protected:
            setattr(alert, field, value)

    db.commit()
    db.refresh(alert)

    logger.info(f"Updated alert {alert_id}")

    return alert.to_dict()


@router.post("/alerts/{alert_id}/initiate-call")
async def initiate_call(
    alert_id: int,
    request: InitiateCallRequest = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Initiate an AI receptionist call for an alert.
    """
    alert = db.query(RateMonitorAlert).filter(RateMonitorAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    # Get MUM client
    try:
        from main import MUMClient
        mum_client = db.query(MUMClient).filter(MUMClient.id == alert.mum_client_id).first()
        if not mum_client:
            raise HTTPException(404, "MUM client not found")
        if not mum_client.phone:
            raise HTTPException(400, "MUM client has no phone number")
    except ImportError:
        raise HTTPException(500, "MUM client model not available")

    # Import refinance call service
    try:
        from services.refinance_call_service import RefinanceCallService
        call_service = RefinanceCallService(db)

        # Initiate call
        call_result = await call_service.initiate_refinance_call(
            alert_id=alert_id,
            mum_client=mum_client,
            savings_info={
                'monthly_savings': float(alert.monthly_savings) if alert.monthly_savings else 0,
                'annual_savings': float(alert.annual_savings) if alert.annual_savings else 0,
                'client_rate': float(alert.client_rate) if alert.client_rate else 0,
                'market_rate': float(alert.market_rate) if alert.market_rate else 0,
            },
            custom_message=request.custom_message if request else None,
        )

        # Update alert with call info
        alert.auto_call_attempted = True
        alert.vapi_call_id = call_result.get('vapi_call_id')
        alert.call_status = 'initiated'
        db.commit()

        return {
            'status': 'call_initiated',
            'alert_id': alert_id,
            'call_result': call_result,
        }

    except ImportError:
        # Refinance call service not available - log the attempt
        logger.warning("Refinance call service not available")
        alert.auto_call_attempted = True
        alert.call_status = 'service_unavailable'
        db.commit()

        return {
            'status': 'service_unavailable',
            'alert_id': alert_id,
            'message': 'AI call service is not configured. Manual follow-up required.',
        }


# =============================================================================
# Test Call Endpoint (Direct Call for Standalone Targets)
# =============================================================================

@router.post("/targets/{target_id}/test-call")
async def test_call_target(
    target_id: int,
    db: Session = Depends(get_db)
):
    """
    Initiate a test AI call for a rate monitor target.
    Works with both MUM-linked and standalone targets.
    """
    target = db.query(RateMonitorTarget).filter(RateMonitorTarget.id == target_id).first()
    if not target:
        raise HTTPException(404, f"Target {target_id} not found")

    # Get phone number from target or MUM client
    phone = target.borrower_phone
    client_name = target.borrower_name or "Valued Client"
    client_rate = float(target.current_rate) if target.current_rate else 7.5
    loan_balance = float(target.current_loan_amount) if target.current_loan_amount else 400000

    # If linked to MUM client, get data from there
    if target.mum_client_id and not phone:
        try:
            from main import MUMClient
            mum_client = db.query(MUMClient).filter(MUMClient.id == target.mum_client_id).first()
            if mum_client:
                phone = mum_client.phone
                client_name = mum_client.client_name
                if mum_client.interest_rate:
                    client_rate = float(mum_client.interest_rate)
                if mum_client.current_loan_amount:
                    loan_balance = float(mum_client.current_loan_amount)
        except ImportError:
            pass

    if not phone:
        raise HTTPException(400, "No phone number available for this target")

    # Format phone number to E.164 format if needed
    phone_clean = ''.join(filter(str.isdigit, phone))
    if len(phone_clean) == 10:
        phone = f"+1{phone_clean}"
    elif len(phone_clean) == 11 and phone_clean.startswith('1'):
        phone = f"+{phone_clean}"
    elif not phone.startswith('+'):
        phone = f"+{phone_clean}"

    # Get current market rate for context
    service = OptimalBlueService(db)
    scenario = RateScenario(
        loan_type=target.loan_type or 'conventional',
        loan_term=target.loan_term or 30,
        loan_amount=loan_balance,
        credit_score=740,
        ltv=80.0,
    )
    rate_result = await service.get_rate(scenario)
    market_rate = rate_result.rate

    # Calculate savings
    monthly_savings = calculate_monthly_savings(client_rate, market_rate, loan_balance)
    annual_savings = calculate_annual_savings(monthly_savings)

    # Create a simple client-like object for the call service
    class StandaloneClient:
        def __init__(self, id, name, phone):
            self.id = id
            self.client_name = name
            self.phone = phone

    client_obj = StandaloneClient(target_id, client_name, phone)

    # Try to initiate call via VAPI
    try:
        import os
        from vapi_service import VapiCRMIntegration, VapiService

        # Check for required VAPI configuration
        vapi_api_key = os.getenv('VAPI_API_KEY')
        if not vapi_api_key:
            return {
                'status': 'not_configured',
                'target_id': target_id,
                'phone': phone,
                'client_name': client_name,
                'message': 'VAPI_API_KEY not configured. Set this environment variable to enable AI calls.',
                'savings_info': {
                    'client_rate': client_rate,
                    'market_rate': market_rate,
                    'monthly_savings': monthly_savings,
                    'annual_savings': annual_savings,
                },
            }

        # Get assistant ID and phone number ID from environment
        assistant_id = os.getenv('VAPI_REFINANCE_ASSISTANT_ID') or os.getenv('VAPI_ASSISTANT_ID')
        phone_number_id = os.getenv('VAPI_PHONE_NUMBER_ID')

        if not assistant_id:
            return {
                'status': 'not_configured',
                'target_id': target_id,
                'phone': phone,
                'client_name': client_name,
                'message': 'VAPI_ASSISTANT_ID not configured. Set this environment variable to enable AI calls.',
                'savings_info': {
                    'client_rate': client_rate,
                    'market_rate': market_rate,
                    'monthly_savings': monthly_savings,
                    'annual_savings': annual_savings,
                },
            }

        # Build call context
        first_name = client_name.split()[0] if client_name else "there"

        # Create outbound call directly via VAPI API
        vapi_payload = {
            "assistantId": assistant_id,
            "customer": {
                "number": phone,
                "name": client_name
            },
            "assistantOverrides": {
                "firstMessage": f"Hi {first_name}, this is the AI assistant calling on behalf of Tim at CMG Home Loans. I'm reaching out because with recent rate changes, we've identified that you could potentially save around ${monthly_savings:,.0f} per month on your mortgage. Do you have a moment to discuss this opportunity?"
            }
        }

        # Add phone number ID if available (required for outbound calls)
        if phone_number_id:
            vapi_payload["phoneNumberId"] = phone_number_id

        async with httpx.AsyncClient() as client:
            call_response = await client.post(
                "https://api.vapi.ai/call/phone",
                headers={
                    "Authorization": f"Bearer {vapi_api_key}",
                    "Content-Type": "application/json"
                },
                json=vapi_payload,
                timeout=30
            )
            call_response.raise_for_status()
            call_result = call_response.json()

        # Update target with call info
        target.last_call_at = datetime.utcnow()
        target.last_call_status = 'initiated'
        target.vapi_call_id = call_result.get('id')
        target.trigger_count = (target.trigger_count or 0) + 1
        db.commit()

        logger.info(f"Initiated test call for target {target_id} to {mask_phone(phone)}, call_id: {call_result.get('id')}")

        return {
            'status': 'call_initiated',
            'target_id': target_id,
            'phone': phone,
            'client_name': client_name,
            'vapi_call_id': call_result.get('id'),
            'savings_info': {
                'client_rate': client_rate,
                'market_rate': market_rate,
                'monthly_savings': monthly_savings,
                'annual_savings': annual_savings,
            },
            'message': f"AI call initiated to {phone} for {client_name}",
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"VAPI API error: {e.response.status_code} - {e.response.text}")
        return {
            'status': 'vapi_error',
            'target_id': target_id,
            'phone': phone,
            'error': f"VAPI API error: {e.response.status_code}",
            'details': e.response.text[:500] if e.response.text else None,
            'message': f"VAPI call failed: {e.response.status_code}",
        }
    except ImportError as e:
        logger.warning(f"VAPI service not available: {e}")
        return {
            'status': 'service_unavailable',
            'target_id': target_id,
            'phone': phone,
            'client_name': client_name,
            'message': 'VAPI service is not configured. Configure VAPI_API_KEY to enable AI calls.',
            'savings_info': {
                'client_rate': client_rate,
                'market_rate': market_rate,
                'monthly_savings': monthly_savings,
                'annual_savings': annual_savings,
            },
        }
    except Exception as e:
        logger.error(f"Error initiating test call: {e}")
        return {
            'status': 'error',
            'target_id': target_id,
            'phone': phone,
            'error': str(e),
            'message': f"Failed to initiate call: {str(e)}",
        }


# =============================================================================
# Migration Endpoint for Creating Tables
# =============================================================================

@router.post("/migrate-tables")
async def migrate_rate_monitor_tables(
    db: Session = Depends(get_db)
):
    """
    Create rate_monitor_alerts and rate_monitor_history tables if they don't exist.
    """
    try:
        from sqlalchemy import text as sql_text

        # Create rate_monitor_history table
        history_sql = """
        CREATE TABLE IF NOT EXISTS rate_monitor_history (
            id SERIAL PRIMARY KEY,
            target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
            mum_client_id INTEGER,
            check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            client_rate NUMERIC(5,3),
            market_rate NUMERIC(5,3),
            rate_difference NUMERIC(5,3),
            loan_balance NUMERIC(12,2),
            monthly_savings NUMERIC(10,2),
            annual_savings NUMERIC(12,2),
            threshold_met BOOLEAN DEFAULT FALSE,
            threshold_type VARCHAR(50),
            threshold_value NUMERIC(10,3),
            alert_generated BOOLEAN DEFAULT FALSE,
            call_initiated BOOLEAN DEFAULT FALSE,
            rate_source VARCHAR(100) DEFAULT 'optimal_blue',
            rate_scenario JSONB
        )
        """

        # Create rate_monitor_alerts table
        alerts_sql = """
        CREATE TABLE IF NOT EXISTS rate_monitor_alerts (
            id SERIAL PRIMARY KEY,
            target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
            mum_client_id INTEGER,
            history_id INTEGER,
            alert_type VARCHAR(50) NOT NULL,
            priority VARCHAR(20) DEFAULT 'medium',
            client_rate NUMERIC(5,3),
            market_rate NUMERIC(5,3),
            monthly_savings NUMERIC(10,2),
            annual_savings NUMERIC(12,2),
            status VARCHAR(50) DEFAULT 'pending',
            auto_call_attempted BOOLEAN DEFAULT FALSE,
            vapi_call_id VARCHAR(100),
            call_status VARCHAR(50),
            call_outcome VARCHAR(100),
            call_duration INTEGER,
            call_summary TEXT,
            appointment_scheduled_at TIMESTAMP,
            assigned_to INTEGER,
            follow_up_notes TEXT,
            follow_up_date DATE,
            converted_to_application BOOLEAN DEFAULT FALSE,
            application_id INTEGER,
            conversion_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TIMESTAMP,
            resolved_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        # Create indexes
        indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_history_target_id ON rate_monitor_history(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_history_check_timestamp ON rate_monitor_history(check_timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_history_threshold_met ON rate_monitor_history(threshold_met)",
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_alerts_target_id ON rate_monitor_alerts(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_alerts_status ON rate_monitor_alerts(status)",
            "CREATE INDEX IF NOT EXISTS idx_rate_monitor_alerts_created_at ON rate_monitor_alerts(created_at)",
        ]

        results = []

        # Create history table
        try:
            db.execute(sql_text(history_sql))
            db.commit()
            results.append({"table": "rate_monitor_history", "status": "OK"})
        except Exception as e:
            db.rollback()
            results.append({"table": "rate_monitor_history", "status": "SKIP", "error": "Internal server error"[:100]})

        # Create alerts table
        try:
            db.execute(sql_text(alerts_sql))
            db.commit()
            results.append({"table": "rate_monitor_alerts", "status": "OK"})
        except Exception as e:
            db.rollback()
            results.append({"table": "rate_monitor_alerts", "status": "SKIP", "error": "Internal server error"[:100]})

        # Create indexes
        for idx_sql in indexes_sql:
            try:
                db.execute(sql_text(idx_sql))
                db.commit()
                results.append({"index": idx_sql.split("IF NOT EXISTS ")[1].split(" ON")[0], "status": "OK"})
            except Exception as e:
                db.rollback()
                results.append({"index": idx_sql[:50], "status": "SKIP", "error": "Internal server error"[:50]})

        return {
            "success": True,
            "message": "Rate monitor tables migration completed",
            "results": results
        }

    except Exception as e:
        logger.error(f"Rate monitor tables migration failed: {e}")
        return {"success": False, "error": "Internal server error"}


# =============================================================================
# Dashboard Endpoints
# =============================================================================

@router.get("/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db)
):
    """
    Get rate monitor dashboard metrics.
    """
    try:
        # Active monitors
        try:
            active_monitors = db.query(RateMonitorTarget).filter(
                RateMonitorTarget.is_active == True
            ).count()
        except Exception:
            active_monitors = 0

        # Auto-call enabled
        try:
            auto_call_enabled = db.query(RateMonitorTarget).filter(
                RateMonitorTarget.is_active == True,
                RateMonitorTarget.auto_call_enabled == True
            ).count()
        except Exception:
            auto_call_enabled = 0

        # Pending alerts
        try:
            pending_alerts = db.query(RateMonitorAlert).filter(
                RateMonitorAlert.status == 'pending'
            ).count()
        except Exception:
            pending_alerts = 0

        # Alerts by priority
        try:
            high_priority = db.query(RateMonitorAlert).filter(
                RateMonitorAlert.status == 'pending',
                RateMonitorAlert.priority == 'high'
            ).count()
        except Exception:
            high_priority = 0

        # Alerts triggered today
        today = date.today()
        try:
            alerts_today = db.query(RateMonitorAlert).filter(
                func.date(RateMonitorAlert.created_at) == today
            ).count()
        except Exception:
            alerts_today = 0

        # Conversions this month
        first_of_month = today.replace(day=1)
        try:
            conversions = db.query(RateMonitorAlert).filter(
                RateMonitorAlert.converted_to_application == True,
                RateMonitorAlert.conversion_date >= first_of_month
            ).count()
        except Exception:
            conversions = 0

        # Calls made this month
        try:
            calls_made = db.query(RateMonitorAlert).filter(
                RateMonitorAlert.auto_call_attempted == True,
                RateMonitorAlert.created_at >= datetime.combine(first_of_month, datetime.min.time())
            ).count()
        except Exception:
            calls_made = 0

        # Appointments scheduled this month
        try:
            appointments = db.query(RateMonitorAlert).filter(
                RateMonitorAlert.appointment_scheduled_at.isnot(None),
                RateMonitorAlert.appointment_scheduled_at >= datetime.combine(first_of_month, datetime.min.time())
            ).count()
        except Exception:
            appointments = 0

        # Total potential savings from pending alerts
        try:
            pending_savings = db.query(func.sum(RateMonitorAlert.monthly_savings)).filter(
                RateMonitorAlert.status == 'pending'
            ).scalar() or 0
        except Exception:
            pending_savings = 0

        # Get current rates for display
        try:
            service = OptimalBlueService(db)
            rates = await service.get_current_rates()
        except Exception:
            rates = {'30_year': {'rate': None, 'is_mock': True}, '15_year': {'rate': None, 'is_mock': True}}

        return {
            'metrics': {
                'active_monitors': active_monitors,
                'auto_call_enabled': auto_call_enabled,
                'pending_alerts': pending_alerts,
                'high_priority_alerts': high_priority,
                'alerts_today': alerts_today,
                'conversions_this_month': conversions,
                'calls_made_this_month': calls_made,
                'appointments_this_month': appointments,
                'pending_monthly_savings': float(pending_savings),
            },
            'current_rates': {
                '30_year': rates.get('30_year', {}).get('rate'),
                '15_year': rates.get('15_year', {}).get('rate'),
                'is_mock': rates.get('30_year', {}).get('is_mock', True),
            },
            'timestamp': datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Rate monitor dashboard error: {e}")
        # Return empty metrics instead of 500
        return {
            'metrics': {
                'active_monitors': 0,
                'auto_call_enabled': 0,
                'pending_alerts': 0,
                'high_priority_alerts': 0,
                'alerts_today': 0,
                'conversions_this_month': 0,
                'calls_made_this_month': 0,
                'appointments_this_month': 0,
                'pending_monthly_savings': 0,
            },
            'current_rates': {
                '30_year': None,
                '15_year': None,
                'is_mock': True,
            },
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e),
        }


@router.get("/history")
async def get_history(
    target_id: Optional[int] = None,
    mum_client_id: Optional[int] = None,
    threshold_met: Optional[bool] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Get rate check history.
    """
    query = db.query(RateMonitorHistory)

    if target_id:
        query = query.filter(RateMonitorHistory.target_id == target_id)
    if mum_client_id:
        query = query.filter(RateMonitorHistory.mum_client_id == mum_client_id)
    if threshold_met is not None:
        query = query.filter(RateMonitorHistory.threshold_met == threshold_met)

    total = query.count()
    history = query.order_by(desc(RateMonitorHistory.check_timestamp)).offset(offset).limit(limit).all()

    return {
        'history': [h.to_dict() for h in history],
        'total': total,
        'limit': limit,
        'offset': offset
    }
