"""Dialer API endpoints initialization"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import logging

from .provider import get_telephony_provider
from .dialer_engine import DialerEngine, click_to_dial
from .compliance import ComplianceChecker
from .websocket import ws_manager
from .schemas import (
    AgentTelephonySettingsUpdate,
    ClickToDialRequest,
    ClickToDialResponse,
    StartSessionRequest,
    StartSessionResponse,
    SessionStatusResponse,
    DispositionRequest,
    DispositionResponse,
    VerifyCallerIdRequest,
    VerifyCallerIdResponse,
    ComplianceCheckResponse,
    CallLogEntry,
    CallLogsResponse,
)

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Create router
router = APIRouter(prefix="/api/v1/dialer", tags=["dialer"])


# =============================================================================
# Dependency to get database session (to be injected from main app)
# =============================================================================

# Dependency container - stores references to main app's dependencies
class _Dependencies:
    db_func = None
    user_func = None

_deps = _Dependencies()


def set_dependencies(db_dependency, user_dependency):
    """
    Store references to main app's dependency functions.
    This must be called during app initialization before any routes are accessed.
    """
    _deps.db_func = db_dependency
    _deps.user_func = user_dependency


def get_db():
    """
    Database session dependency.
    Wraps the main app's get_db to yield a session.
    """
    if _deps.db_func is None:
        raise RuntimeError("Dependencies not set - call set_dependencies() first")
    # Call the main app's get_db generator
    gen = _deps.db_func()
    try:
        yield next(gen)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Current user dependency.
    Calls the main app's get_current_user with the required parameters.
    """
    if _deps.user_func is None:
        raise RuntimeError("Dependencies not set - call set_dependencies() first")

    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Call the main app's get_current_user
    return await _deps.user_func(token=token, request=request, db=db)


# =============================================================================
# Call Tasks Endpoint - Tasks available for Power Dialer
# =============================================================================

@router.get("/call-tasks")
async def get_call_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get tasks that can be called via Power Dialer.

    Returns tasks that:
    1. Have call/phone-related titles or categories
    2. Are pending/in-progress (not completed)
    3. Have associated leads or loans with phone numbers

    Response includes phone numbers from related Lead/Loan entities.
    """
    from database.enums import TaskType
    from database.models import Task, AITask, Lead, Loan
    from sqlalchemy import or_, and_

    org_id = getattr(current_user, 'organization_id', None)

    # Call-related keywords to identify phone tasks
    call_keywords = ['call', 'phone', 'contact', 'dial', 'reach out', 'follow up', 'follow-up', 'callback', 'ring']

    # Build case-insensitive search conditions for task titles
    call_title_conditions = [Task.title.ilike(f'%{kw}%') for kw in call_keywords]
    call_title_conditions.extend([Task.description.ilike(f'%{kw}%') for kw in call_keywords])

    # Query Task model first (primary tasks)
    tasks_query = db.query(Task).filter(
        Task.owner_id == current_user.id,
        Task.status.in_(['pending', 'in_progress', 'In Progress']),
        or_(*call_title_conditions)
    ).order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())

    # Also get AITask items that look like call tasks
    ai_call_conditions = [AITask.title.ilike(f'%{kw}%') for kw in call_keywords]
    ai_call_conditions.extend([AITask.description.ilike(f'%{kw}%') for kw in call_keywords])

    ai_tasks_query = db.query(AITask).filter(
        AITask.assigned_to_id == current_user.id,
        AITask.type.in_([TaskType.HUMAN_NEEDED, TaskType.AWAITING_REVIEW, TaskType.IN_PROGRESS]),
        or_(*ai_call_conditions)
    ).order_by(AITask.due_date.asc().nullslast(), AITask.created_at.desc())

    # Process tasks and add phone information
    call_tasks = []

    # Process regular tasks
    for task in tasks_query.offset(skip).limit(limit).all():
        phone = None
        contact_name = None
        entity_type = None
        entity_id = None

        # Get phone from Lead (scoped to org)
        if task.lead_id:
            try:
                lead_q = db.query(Lead).filter(Lead.id == task.lead_id)
                if org_id:
                    lead_q = lead_q.filter(Lead.organization_id == org_id)
                lead = lead_q.first()
                if lead and lead.phone:
                    phone = lead.phone
                    contact_name = lead.name
                    entity_type = 'lead'
                    entity_id = lead.id
            except LookupError:
                # Handle enum mismatch errors gracefully
                pass

        # Get phone from Loan if not found in Lead (scoped to org)
        if not phone and task.loan_id:
            try:
                loan_q = db.query(Loan).filter(Loan.id == task.loan_id)
                if org_id:
                    loan_q = loan_q.filter(Loan.organization_id == org_id)
                loan = loan_q.first()
                if loan and loan.borrower_phone:
                    phone = loan.borrower_phone
                    contact_name = loan.borrower_name
                    entity_type = 'loan'
                    entity_id = loan.id
            except LookupError:
                # Handle enum mismatch errors (e.g., 'Processing' vs 'PROCESSING')
                pass

        # Also check related_contact_name for phone hint
        if not phone and task.related_contact_name:
            contact_name = task.related_contact_name

        # Only include if we have a phone number
        if phone:
            call_tasks.append({
                'id': task.id,
                'task_type': 'task',
                'title': task.title,
                'description': task.description,
                'priority': task.priority,
                'status': task.status,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'contact_name': contact_name,
                'contact_phone': phone,
                'lead_id': task.lead_id,
                'loan_id': task.loan_id,
                'lead_name': contact_name if entity_type == 'lead' else None,
                'loan_borrower_name': contact_name if entity_type == 'loan' else None,
                'lead_phone': phone if entity_type == 'lead' else None,
                'loan_borrower_phone': phone if entity_type == 'loan' else None,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'created_at': task.created_at.isoformat() if task.created_at else None
            })

    # Process AI tasks if we need more
    remaining_limit = limit - len(call_tasks)
    if remaining_limit > 0:
        for ai_task in ai_tasks_query.limit(remaining_limit).all():
            phone = None
            contact_name = ai_task.borrower_name
            entity_type = None
            entity_id = None

            # Get phone from Lead (scoped to org)
            if ai_task.lead_id:
                try:
                    lead_q = db.query(Lead).filter(Lead.id == ai_task.lead_id)
                    if org_id:
                        lead_q = lead_q.filter(Lead.organization_id == org_id)
                    lead = lead_q.first()
                    if lead and lead.phone:
                        phone = lead.phone
                        contact_name = lead.name
                        entity_type = 'lead'
                        entity_id = lead.id
                except LookupError:
                    # Handle enum mismatch errors gracefully
                    pass

            # Get phone from Loan (scoped to org)
            if not phone and ai_task.loan_id:
                try:
                    loan_q = db.query(Loan).filter(Loan.id == ai_task.loan_id)
                    if org_id:
                        loan_q = loan_q.filter(Loan.organization_id == org_id)
                    loan = loan_q.first()
                    if loan and loan.borrower_phone:
                        phone = loan.borrower_phone
                        contact_name = loan.borrower_name
                        entity_type = 'loan'
                        entity_id = loan.id
                except LookupError:
                    # Handle enum mismatch errors (e.g., 'Processing' vs 'PROCESSING')
                    pass

            # Only include if we have a phone number
            if phone:
                call_tasks.append({
                    'id': ai_task.id,
                    'task_type': 'ai_task',
                    'title': ai_task.title,
                    'description': ai_task.description,
                    'priority': ai_task.priority,
                    'status': ai_task.type.value if ai_task.type else None,
                    'due_date': ai_task.due_date.isoformat() if ai_task.due_date else None,
                    'contact_name': contact_name,
                    'contact_phone': phone,
                    'lead_id': ai_task.lead_id,
                    'loan_id': ai_task.loan_id,
                    'lead_name': contact_name if entity_type == 'lead' else None,
                    'loan_borrower_name': contact_name if entity_type == 'loan' else None,
                    'lead_phone': phone if entity_type == 'lead' else None,
                    'loan_borrower_phone': phone if entity_type == 'loan' else None,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'created_at': ai_task.created_at.isoformat() if ai_task.created_at else None
                })

    # Also include workflow tasks that have phone enabled
    from workflow_config_routes import get_all_workflow_tasks_logic
    try:
        workflow_tasks = get_all_workflow_tasks_logic(db, current_user, days_ahead=14)
        for wf_task in workflow_tasks:
            # Only include tasks where phone is the preferred method (phone is first in communication_methods)
            methods = wf_task.get('communication_methods', [])
            if 'phone' not in methods:
                continue
            # Phone should be the preferred method (first in list or only method)
            if methods and methods[0] != 'phone':
                continue

            phone = None
            contact_name = wf_task.get('client_name')
            entity_type = wf_task.get('client_type')
            entity_id = wf_task.get('client_id')

            # Get phone from Lead or Loan (scoped to org)
            if entity_type == 'lead' and entity_id:
                try:
                    lead_q = db.query(Lead).filter(Lead.id == entity_id)
                    if org_id:
                        lead_q = lead_q.filter(Lead.organization_id == org_id)
                    lead = lead_q.first()
                    if lead and lead.phone:
                        phone = lead.phone
                except Exception as e:
                    logger.exception(f"Failed to fetch lead phone for entity_id={entity_id}: {e}")
            elif entity_type == 'loan' and entity_id:
                try:
                    loan_q = db.query(Loan).filter(Loan.id == entity_id)
                    if org_id:
                        loan_q = loan_q.filter(Loan.organization_id == org_id)
                    loan = loan_q.first()
                    if loan and loan.borrower_phone:
                        phone = loan.borrower_phone
                except Exception as e:
                    logger.exception(f"Failed to fetch loan borrower phone for entity_id={entity_id}: {e}")

            # Only include if we have a phone number
            if phone:
                call_tasks.append({
                    'id': wf_task.get('id'),
                    'task_type': 'workflow',
                    'title': wf_task.get('title'),
                    'description': wf_task.get('description'),
                    'priority': wf_task.get('urgency', 'medium'),
                    'status': wf_task.get('status', 'pending'),
                    'due_date': wf_task.get('due_date'),
                    'contact_name': contact_name,
                    'contact_phone': phone,
                    'lead_id': entity_id if entity_type == 'lead' else None,
                    'loan_id': entity_id if entity_type == 'loan' else None,
                    'lead_name': contact_name if entity_type == 'lead' else None,
                    'loan_borrower_name': contact_name if entity_type == 'loan' else None,
                    'lead_phone': phone if entity_type == 'lead' else None,
                    'loan_borrower_phone': phone if entity_type == 'loan' else None,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'workflow_name': wf_task.get('workflow_name'),
                    'workflow_color': wf_task.get('workflow_color'),
                    'days_until_due': wf_task.get('days_until_due'),
                    'created_at': None
                })
    except Exception as e:
        logger.warning(f"Could not fetch workflow tasks for Power Dialer: {e}")

    return {
        'tasks': call_tasks,
        'total': len(call_tasks),
        'skip': skip,
        'limit': limit
    }


@router.get("/callable-contacts")
async def get_callable_contacts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get ALL contacts that can be called (leads and loans with phone numbers).

    This is useful when there are no call-specific tasks but you want to
    make outbound calls to leads/loans.

    Returns leads and loan borrowers that have phone numbers.
    """
    from database.models import Lead, Loan
    from sqlalchemy import and_

    org_id = getattr(current_user, 'organization_id', None)
    contacts = []

    try:
        # Get leads with phone numbers assigned to current user (scoped to org)
        leads_query = db.query(Lead).filter(
            Lead.owner_id == current_user.id,
            Lead.phone.isnot(None)
        )
        if org_id:
            leads_query = leads_query.filter(Lead.organization_id == org_id)
        leads_query = leads_query.order_by(Lead.created_at.desc())

        for lead in leads_query.offset(skip).limit(limit).all():
            # Skip empty phone numbers
            if not lead.phone or lead.phone.strip() == '':
                continue
            contacts.append({
                'id': f'lead-{lead.id}',
                'entity_type': 'lead',
                'entity_id': lead.id,
                'contact_name': lead.name,
                'contact_phone': lead.phone,
                'contact_email': lead.email,
                'stage': lead.stage.value if lead.stage else None,
                'last_contact': lead.last_contact.isoformat() if lead.last_contact else None,
                'source': lead.source,
                'lead_id': lead.id,
                'loan_id': None
            })
    except Exception as e:
        logger.error(f"Error fetching leads: {e}")

    # Get loans with borrower phone numbers if we need more
    remaining = limit - len(contacts)
    if remaining > 0:
        try:
            loans_query = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.borrower_phone.isnot(None)
            )
            if org_id:
                loans_query = loans_query.filter(Loan.organization_id == org_id)
            loans_query = loans_query.order_by(Loan.created_at.desc())

            for loan in loans_query.limit(remaining).all():
                # Skip empty phone numbers
                if not loan.borrower_phone or loan.borrower_phone.strip() == '':
                    continue
                contacts.append({
                    'id': f'loan-{loan.id}',
                    'entity_type': 'loan',
                    'entity_id': loan.id,
                    'contact_name': loan.borrower_name,
                    'contact_phone': loan.borrower_phone,
                    'contact_email': loan.borrower_email,
                    'stage': loan.stage.value if loan.stage else None,
                    'last_contact': None,
                    'loan_number': loan.loan_number,
                    'lead_id': None,
                    'loan_id': loan.id
                })
        except Exception as e:
            logger.error(f"Error fetching loans: {e}")

    return {
        'contacts': contacts,
        'total': len(contacts),
        'skip': skip,
        'limit': limit
    }


# =============================================================================
# Agent Settings Endpoints
# =============================================================================

@router.get("/settings")
async def get_dialer_settings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get agent's telephony/dialer settings"""
    # Import models from main
    from database.models import AgentTelephonySettings, VerifiedCallerId

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == current_user.id
    ).first()

    if not settings:
        # Create default settings
        settings = AgentTelephonySettings(
            user_id=current_user.id,
            dialer_enabled=True,
            max_calls_per_day=100,
            auto_advance=True,
            pause_between_calls=3
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    # Get verified caller IDs
    caller_ids = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.user_id == current_user.id,
        VerifiedCallerId.verification_status == "verified"
    ).all()

    return {
        "user_id": settings.user_id,
        "cell_phone": settings.cell_phone,
        "business_caller_id": settings.business_caller_id,
        "dialer_enabled": settings.dialer_enabled,
        "max_calls_per_day": settings.max_calls_per_day,
        "auto_advance": settings.auto_advance,
        "pause_between_calls": settings.pause_between_calls,
        "verified_caller_ids": [
            {"phone": c.phone_number, "name": c.friendly_name, "is_default": c.phone_number == settings.business_caller_id}
            for c in caller_ids
        ]
    }


@router.put("/settings")
async def update_dialer_settings(
    settings_update: AgentTelephonySettingsUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update agent's telephony/dialer settings"""
    from database.models import AgentTelephonySettings

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = AgentTelephonySettings(user_id=current_user.id)
        db.add(settings)

    # Update fields that were provided
    update_data = settings_update.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_data.items():
        if value is not None and field not in _protected:
            setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    return {"success": True, "message": "Settings updated"}


# =============================================================================
# Caller ID Verification
# =============================================================================

@router.post("/verify-caller-id")
async def verify_caller_id(
    request: VerifyCallerIdRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start caller ID verification process"""
    from database.models import VerifiedCallerId

    provider = get_telephony_provider()
    result = provider.verify_caller_id(request.phone_number, request.friendly_name)

    if result.get("success"):
        # Save pending verification
        caller_id = VerifiedCallerId(
            user_id=current_user.id,
            phone_number=request.phone_number,
            friendly_name=request.friendly_name,
            provider_sid=result.get("call_sid"),
            verification_status="pending"
        )
        db.add(caller_id)
        db.commit()

    return result


@router.get("/verified-caller-ids")
async def list_verified_caller_ids(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all verified caller IDs for the agent"""
    from database.models import VerifiedCallerId

    caller_ids = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.user_id == current_user.id
    ).all()

    return {"caller_ids": caller_ids}


@router.post("/setup-demo-caller-id")
async def setup_demo_caller_id(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Set up a demo verified caller ID for testing.
    This bypasses telephony provider verification for demo/testing purposes.
    """
    from database.models import VerifiedCallerId, AgentTelephonySettings

    try:
        # Check if user already has a verified caller ID
        existing = db.query(VerifiedCallerId).filter(
            VerifiedCallerId.user_id == current_user.id,
            VerifiedCallerId.verification_status == "verified"
        ).first()

        if existing:
            # Also ensure settings are updated
            settings = db.query(AgentTelephonySettings).filter(
                AgentTelephonySettings.user_id == current_user.id
            ).first()
            if settings and not settings.business_caller_id:
                settings.business_caller_id = existing.phone_number
                db.commit()

            return {
                "success": True,
                "message": f"Already have verified caller ID: {existing.phone_number}",
                "caller_id": existing.phone_number
            }

        # Create a demo verified caller ID
        demo_phone = "+18434169589"  # Demo telephony number
        caller_id = VerifiedCallerId(
            user_id=current_user.id,
            phone_number=demo_phone,
            friendly_name="Demo Business Line",
            provider_sid="demo_sid_for_testing",
            verification_status="verified"
        )
        db.add(caller_id)

        # Also update the user's settings to use this caller ID
        settings = db.query(AgentTelephonySettings).filter(
            AgentTelephonySettings.user_id == current_user.id
        ).first()

        if settings:
            settings.business_caller_id = demo_phone
        else:
            settings = AgentTelephonySettings(
                user_id=current_user.id,
                business_caller_id=demo_phone,
                dialer_enabled=True
            )
            db.add(settings)

        db.commit()

        return {
            "success": True,
            "message": "Demo caller ID created and configured",
            "caller_id": demo_phone
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error setting up demo caller ID: {e}")
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/check-verification/{phone_number}")
async def check_verification_status(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Check and update verification status for a caller ID"""
    from database.models import VerifiedCallerId

    # Normalize phone number
    normalized = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not normalized.startswith("+"):
        normalized = "+1" + normalized.lstrip("1")

    # Check with telephony provider
    provider = get_telephony_provider()
    result = provider.check_caller_id_verification(normalized)

    if result.get("verified"):
        # Update our record
        caller_id = db.query(VerifiedCallerId).filter(
            VerifiedCallerId.user_id == current_user.id,
            VerifiedCallerId.phone_number == normalized
        ).first()

        if caller_id:
            caller_id.verification_status = "verified"
            caller_id.provider_sid = result.get("sid")
            db.commit()
            return {
                "success": True,
                "verified": True,
                "phone_number": normalized,
                "message": "Caller ID verified successfully!"
            }
        else:
            # Create new verified record if not exists
            new_caller_id = VerifiedCallerId(
                user_id=current_user.id,
                phone_number=normalized,
                friendly_name=result.get("friendly_name", "Verified Number"),
                provider_sid=result.get("sid"),
                verification_status="verified"
            )
            db.add(new_caller_id)
            db.commit()
            return {
                "success": True,
                "verified": True,
                "phone_number": normalized,
                "message": "Caller ID verified and saved!"
            }

    return {
        "success": True,
        "verified": False,
        "phone_number": normalized,
        "message": "Verification not yet complete. Please answer the verification call and enter the validation code."
    }


# =============================================================================
# Click-to-Dial
# =============================================================================

@router.post("/click-to-dial", response_model=ClickToDialResponse)
async def api_click_to_dial(
    request: ClickToDialRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Initiate a single click-to-dial call"""
    import os
    from sqlalchemy import func
    from datetime import datetime, timedelta, timezone
    from database.models import CallLog

    # Rate limit: max 10 click-to-dial calls per minute per user
    organization_id = getattr(current_user, 'organization_id', None)
    rate_q = db.query(func.count(CallLog.id)).filter(
        CallLog.agent_id == current_user.id,
        CallLog.created_at >= datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    if organization_id:
        rate_q = rate_q.filter(CallLog.organization_id == organization_id)
    recent_calls = rate_q.scalar() or 0
    if recent_calls >= 10:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 10 calls per minute")

    base_url = os.getenv("BASE_URL", "https://app.perenniaai.com")

    result = click_to_dial(
        db_session=db,
        agent_id=current_user.id,
        phone_number=request.phone_number,
        contact_name=request.contact_name,
        base_url=base_url,
        lead_id=request.lead_id,
        loan_id=request.loan_id,
        task_id=request.task_id,
        organization_id=organization_id,
    )

    return ClickToDialResponse(
        success=result.get("success", False),
        call_sid=result.get("call_sid"),
        contact_name=request.contact_name,
        contact_phone=request.phone_number,
        error=result.get("error")
    )


# =============================================================================
# Dialer Sessions
# =============================================================================

@router.post("/sessions", response_model=StartSessionResponse)
async def create_dialer_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new power dialer session"""
    import os
    base_url = os.getenv("BASE_URL", "https://app.perenniaai.com")

    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.create_session(request.task_ids, base_url)

    return StartSessionResponse(
        success=result.get("success", False),
        session_id=result.get("session_id"),
        status=result.get("status"),
        total_tasks=result.get("total_tasks", 0),
        error=result.get("error")
    )


@router.get("/sessions/active")
async def get_active_session(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get the agent's currently active dialer session"""
    from database.enums import DialerSessionStatus
    from database.models import DialerSession

    org_id = getattr(current_user, 'organization_id', None)
    session_q = db.query(DialerSession).filter(
        DialerSession.agent_id == current_user.id,
        DialerSession.status == DialerSessionStatus.ACTIVE
    )
    if org_id:
        session_q = session_q.filter(DialerSession.organization_id == org_id)
    session = session_q.first()

    if not session:
        return {"active_session": None}

    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    return {"active_session": engine.get_session_status(session.id)}


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get status of a specific dialer session"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    status = engine.get_session_status(session_id)

    if not status:
        raise HTTPException(status_code=404, detail="Session not found")

    return status


@router.get("/sessions/{session_id}/next-task")
async def get_next_task(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get the next pending task in a session"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    task = engine.get_next_task(session_id)

    if not task:
        return {"next_task": None, "message": "No more pending tasks"}

    return {"next_task": task}


@router.post("/sessions/{session_id}/call/{task_id}")
async def initiate_session_call(
    session_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Initiate a call for a specific task in the session"""
    import os
    base_url = os.getenv("BASE_URL", "https://app.perenniaai.com")

    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.initiate_call(session_id, task_id, base_url)

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to initiate call")
        )

    return result


@router.post("/sessions/{session_id}/tasks/{task_id}/disposition", response_model=DispositionResponse)
async def set_task_disposition(
    session_id: int,
    task_id: int,
    request: DispositionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Set disposition for a completed call"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.set_disposition(
        session_id=session_id,
        task_id=task_id,
        disposition=request.disposition,
        notes=request.notes,
        schedule_callback=request.schedule_callback
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return DispositionResponse(
        success=True,
        task_id=task_id,
        disposition=request.disposition
    )


@router.post("/sessions/{session_id}/tasks/{task_id}/skip")
async def skip_session_task(
    session_id: int,
    task_id: int,
    reason: str = "manual_skip",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Skip a task in the session"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.skip_task(session_id, task_id, reason)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/pause")
async def pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Pause an active dialer session"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.pause_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Resume a paused dialer session"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.resume_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Stop a dialer session completely"""
    engine = DialerEngine(db, current_user.id, organization_id=getattr(current_user, 'organization_id', None))
    result = engine.stop_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# =============================================================================
# Compliance Endpoints
# =============================================================================

@router.get("/compliance/check", response_model=ComplianceCheckResponse)
async def check_compliance(
    phone_number: str = Query(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Run compliance checks for a phone number"""
    compliance = ComplianceChecker(db)
    result = compliance.full_compliance_check(phone_number, current_user.id)

    return ComplianceCheckResponse(**result)


@router.post("/dnc/add")
async def add_to_dnc(
    phone_number: str,
    reason: str = "customer_request",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a phone number to the Do Not Call list"""
    compliance = ComplianceChecker(db)
    success = compliance.add_to_dnc(phone_number, reason, current_user.id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add to DNC list")

    return {"success": True, "message": f"Added {phone_number} to DNC list"}


@router.delete("/dnc/{phone_number}")
async def remove_from_dnc(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a phone number from the Do Not Call list"""
    compliance = ComplianceChecker(db)
    success = compliance.remove_from_dnc(phone_number)

    return {"success": success, "message": "Removed from DNC list" if success else "Number not found on DNC list"}


# =============================================================================
# Call Logs
# =============================================================================

@router.get("/call-logs", response_model=CallLogsResponse)
async def get_call_logs(
    skip: int = 0,
    limit: int = 50,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get call history for the agent"""
    from database.models import CallLog

    org_id = getattr(current_user, 'organization_id', None)
    query = db.query(CallLog).filter(CallLog.agent_id == current_user.id)
    if org_id:
        query = query.filter(CallLog.organization_id == org_id)

    if lead_id:
        query = query.filter(CallLog.lead_id == lead_id)
    if loan_id:
        query = query.filter(CallLog.loan_id == loan_id)

    total = query.count()
    logs = query.order_by(CallLog.created_at.desc()).offset(skip).limit(limit).all()

    return CallLogsResponse(
        call_logs=[CallLogEntry.model_validate(log) for log in logs],
        total=total
    )


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/{agent_id}")
async def websocket_dialer(websocket: WebSocket, agent_id: str):
    """
    WebSocket connection for real-time dialer updates

    Clients should connect with their agent_id to receive:
    - Call status updates (ringing, answered, completed)
    - Session progress updates
    - Disposition prompts
    - Error notifications
    """
    await ws_manager.connect(websocket, agent_id)
    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            data = await websocket.receive_text()
            # Echo back acknowledgment
            await websocket.send_json({"type": "ack", "message": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, agent_id)
        logger.info(f"WebSocket disconnected for agent {agent_id}")
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
        ws_manager.disconnect(websocket, agent_id)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status for monitoring"""
    return {
        "connected_agents": ws_manager.get_connected_agents(),
        "total_connections": sum(len(conns) for conns in ws_manager.active_connections.values())
    }


# =============================================================================
# Telnyx Webhook Endpoints (TeXML/TwiML)
# =============================================================================

from fastapi.responses import Response

@router.post("/twiml/click-to-dial")
@router.get("/twiml/click-to-dial")
async def twiml_click_to_dial(
    request: Request,
    destination: Optional[str] = None,
    contact_name: Optional[str] = None
):
    """
    TwiML endpoint for click-to-dial calls.

    When Telnyx connects to the agent's phone, this tells Telnyx to:
    1. Say a brief message with contact name
    2. Dial the destination number (the contact)

    The flow is:
    - Telnyx calls agent's cell phone
    - Agent answers
    - This TeXML plays and dials the contact
    - Agent and contact are bridged together
    """
    # Get form data from Telnyx
    form_data = await request.form()
    from_number = form_data.get("From", "")  # The Telnyx number (caller ID)

    logger.info(f"TwiML click-to-dial: destination={destination}, contact={contact_name}, from={from_number}")

    if not destination:
        # Fallback error
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Sorry, no destination number was provided.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Announce the contact name if provided
    announcement = f"Connecting you to {contact_name}." if contact_name else "Connecting your call."

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{announcement}</Say>
    <Dial callerId="{from_number}" timeout="30">
        <Number>{destination}</Number>
    </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/twiml/outbound")
@router.get("/twiml/outbound")
async def twiml_outbound(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None
):
    """
    TwiML endpoint for power dialer outbound calls.

    Similar to click-to-dial but includes session tracking.
    """
    form_data = await request.form()
    to_number = form_data.get("To", "")
    from_number = form_data.get("From", "")

    logger.info(f"TwiML outbound: session={session_id}, task={task_id}, To={to_number}")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Connecting your call.</Say>
    <Dial callerId="{from_number}" timeout="30" action="/api/v1/dialer/webhook/dial-status?session_id={session_id}&amp;task_id={task_id}">
        <Number>{to_number}</Number>
    </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/webhook/click-to-dial-status")
async def webhook_click_to_dial_status(
    request: Request,
    agent_id: Optional[int] = None
):
    """
    Status callback for click-to-dial calls.

    Telnyx calls this when the call status changes (ringing, answered, completed, etc.)
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", "0")

    logger.info(f"Click-to-dial status: agent={agent_id}, sid={call_sid}, status={call_status}, duration={duration}")

    # Send WebSocket notification if agent is connected
    if agent_id:
        try:
            await ws_manager.send_to_agent(str(agent_id), {
                "type": "call_status",
                "call_sid": call_sid,
                "status": call_status,
                "duration": int(duration) if duration else 0
            })
        except Exception as e:
            logger.error(f"WebSocket notification error: {e}")

    return {"success": True}


@router.post("/webhook/status")
async def webhook_call_status(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Status callback for power dialer session calls.

    Updates session state based on call progress.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", "0")
    answered_by = form_data.get("AnsweredBy", "")

    logger.info(f"Dialer status: session={session_id}, task={task_id}, status={call_status}")

    if session_id and task_id:
        try:
            engine = DialerEngine(db, current_user.id if current_user else 0, organization_id=getattr(current_user, 'organization_id', None) if current_user else None)
            engine.handle_call_status(
                session_id=session_id,
                task_id=task_id,
                call_sid=call_sid,
                status=call_status,
                duration=int(duration) if duration else 0,
                answered_by=answered_by
            )
        except Exception as e:
            logger.error(f"Error handling call status: {e}")

    return {"success": True}


@router.post("/webhook/dial-status")
async def webhook_dial_status(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None
):
    """
    Dial action callback - called when the <Dial> verb completes.

    This is different from status callback - it's called when the actual
    dial attempt finishes (answered, busy, no-answer, etc.)
    """
    form_data = await request.form()
    dial_call_status = form_data.get("DialCallStatus", "")
    dial_call_duration = form_data.get("DialCallDuration", "0")

    logger.info(f"Dial completed: session={session_id}, task={task_id}, status={dial_call_status}")

    # Return TwiML to hang up after dial completes
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# Call Recording Webhook - Sends to Conversation Intelligence
# =============================================================================

@router.post("/webhook/recording-complete")
async def webhook_recording_complete(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Recording status callback - called when call recording is complete.

    Receives the recording URL from Telnyx and sends it to the
    Conversation Intelligence pipeline for transcription, analysis,
    and QA scoring.
    """
    import asyncio
    from datetime import datetime, timezone

    form_data = await request.form()

    # Extract recording details from Telnyx webhook
    recording_sid = form_data.get("RecordingSid", "")
    recording_url = form_data.get("RecordingUrl", "")
    recording_status = form_data.get("RecordingStatus", "")
    recording_duration = form_data.get("RecordingDuration", "0")
    call_sid = form_data.get("CallSid", "")

    logger.info(f"📼 Recording complete: call={call_sid}, recording={recording_sid}, duration={recording_duration}s")

    if recording_status != "completed" or not recording_url:
        logger.warning(f"Recording not ready: status={recording_status}")
        return {"success": False, "message": "Recording not ready"}

    try:
        # Get call details from session/task if available
        call_metadata = {
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "duration_seconds": int(recording_duration) if recording_duration else 0,
            "session_id": session_id,
            "task_id": task_id,
            "source": "power_dialer"
        }

        # Get lead/loan info if task_id is provided
        if task_id:
            from database.models import DialerSessionTask
            task = db.query(DialerSessionTask).filter(
                DialerSessionTask.id == task_id
            ).first()
            if task:
                call_metadata["lead_id"] = task.lead_id
                call_metadata["loan_id"] = task.loan_id
                call_metadata["contact_name"] = task.contact_name
                call_metadata["contact_phone"] = task.contact_phone

        # Send to Conversation Intelligence pipeline
        asyncio.create_task(
            process_call_recording_for_ci(
                recording_url=f"{recording_url}.mp3",  # Telnyx provides MP3 format
                recording_sid=recording_sid,
                call_metadata=call_metadata,
                db=db
            )
        )

        return {"success": True, "message": "Recording queued for CI analysis"}

    except Exception as e:
        logger.error(f"Error processing recording webhook: {e}")
        return {"success": False, "error": "Internal server error"}


async def process_call_recording_for_ci(
    recording_url: str,
    recording_sid: str,
    call_metadata: dict,
    db: Session
):
    """
    Process a call recording through the Conversation Intelligence pipeline.

    1. Create a CI Call Recording record
    2. Transcribe the recording
    3. Analyze with AI
    4. Generate QA scores
    5. Create task for review
    """
    import os
    import uuid
    from datetime import datetime, timezone

    logger.info(f"🎯 Processing recording {recording_sid} for CI analysis...")

    try:
        # Import CI models and services
        from models.conversation_intelligence_models import (
            CICallRecording, CICallTranscription, CICallAnalysis,
            CIQAScorecard, RecordingStatus
        )
        from services.ci_transcription_service import CITranscriptionService
        from services.ci_analysis_service import CIAnalysisService

        # Get agent info from session
        agent_user_id = None
        lead_id = call_metadata.get("lead_id")
        loan_id = call_metadata.get("loan_id")

        if call_metadata.get("session_id"):
            from database.models import DialerSession
            session = db.query(DialerSession).filter(
                DialerSession.id == call_metadata["session_id"]
            ).first()
            if session:
                agent_user_id = session.agent_id

        # Create CI Call Recording record
        recording = CICallRecording(
            id=uuid.uuid4(),
            external_call_id=call_metadata.get("call_sid"),
            call_type="outbound",
            direction="outbound",
            agent_user_id=agent_user_id,
            lead_id=lead_id,
            loan_id=loan_id,
            phone_to=call_metadata.get("contact_phone"),
            started_at=datetime.now(timezone.utc),
            duration_seconds=call_metadata.get("duration_seconds", 0),
            recording_url=recording_url,
            status=RecordingStatus.RECORDED.value,
            transcription_status="pending",
            analysis_status="pending",
            qa_status="pending",
            metadata={
                "source": "power_dialer",
                "recording_sid": recording_sid,
                "contact_name": call_metadata.get("contact_name"),
                "session_id": call_metadata.get("session_id"),
                "task_id": call_metadata.get("task_id")
            }
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)

        logger.info(f"Created CI recording record: {recording.id}")

        # Step 1: Transcribe the recording
        try:
            transcription_service = CITranscriptionService()
            transcript = await transcription_service.transcribe_from_url(recording_url)

            if transcript:
                # Create transcription record
                transcription = CICallTranscription(
                    id=uuid.uuid4(),
                    recording_id=recording.id,
                    provider="whisper",
                    full_text=transcript,
                    word_count=len(transcript.split()),
                    language="en"
                )
                db.add(transcription)

                recording.transcription_status = "completed"
                db.commit()
                logger.info(f"Transcription complete: {len(transcript)} characters")

                # Step 2: Analyze the call
                try:
                    analysis_service = CIAnalysisService(db)
                    analysis_result = await analysis_service.analyze_call(
                        transcript=transcript,
                        recording_id=str(recording.id),
                        call_type="sales_call",
                        agent_id=agent_user_id
                    )

                    if analysis_result:
                        # Create analysis record
                        analysis = CICallAnalysis(
                            id=uuid.uuid4(),
                            recording_id=recording.id,
                            summary=analysis_result.get("summary"),
                            call_disposition=analysis_result.get("disposition"),
                            customer_sentiment=analysis_result.get("sentiment"),
                            coaching_opportunities=analysis_result.get("coaching_notes")
                        )
                        db.add(analysis)

                        # Create scorecard if QA score is available
                        qa_score = analysis_result.get("qa_score")
                        if qa_score is not None:
                            grade = "A" if qa_score >= 90 else "B" if qa_score >= 80 else "C" if qa_score >= 70 else "D" if qa_score >= 60 else "F"
                            scorecard = CIQAScorecard(
                                id=uuid.uuid4(),
                                recording_id=recording.id,
                                scoring_method="auto",
                                percentage_score=qa_score,
                                grade=grade,
                                status="completed"
                            )
                            db.add(scorecard)

                            # Create task for QA review if score needs attention
                            if qa_score < 70:
                                await create_qa_review_task(
                                    recording=recording,
                                    qa_score=qa_score,
                                    agent_id=agent_user_id,
                                    coaching_notes=analysis_result.get("coaching_notes"),
                                    db=db
                                )

                        recording.analysis_status = "completed"
                        recording.qa_status = "completed"
                        recording.status = RecordingStatus.ANALYZED.value
                        db.commit()
                        logger.info(f"Analysis complete: QA score = {qa_score}")

                except Exception as e:
                    logger.error(f"Analysis failed: {e}")
                    recording.analysis_status = "failed"
                    db.commit()

            else:
                recording.transcription_status = "failed"
                recording.status = RecordingStatus.FAILED.value
                db.commit()
                logger.error(f"Transcription failed for recording {recording_sid}")

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            recording.transcription_status = "failed"
            recording.status = RecordingStatus.FAILED.value
            db.commit()

    except Exception as e:
        logger.error(f"Error in CI pipeline for recording {recording_sid}: {e}")


async def create_qa_review_task(
    recording,
    qa_score: float,
    agent_id: int,
    coaching_notes: str,
    db: Session
):
    """Create a task for the manager to review a call that needs coaching."""
    from datetime import datetime, timezone

    try:
        from database.models import AITask, User

        # Get agent's manager
        agent = db.query(User).filter(User.id == agent_id).first() if agent_id else None
        manager_id = agent.manager_id if agent and agent.manager_id else agent_id

        duration = recording.duration_seconds or 0
        duration_str = f"{duration // 60}:{duration % 60:02d}"

        # Create review task
        task = AITask(
            user_id=manager_id,
            task_type="call_qa_review",
            title=f"Review Call: QA Score {qa_score:.0f}%",
            description=f"""A recorded call requires QA review.

**Agent:** {agent.name if agent else 'Unknown'}
**Call Duration:** {duration_str}
**QA Score:** {qa_score:.0f}%

**Coaching Notes:**
{coaching_notes or 'No coaching notes generated.'}

Please review the call recording and provide feedback to the agent.""",
            status="pending",
            priority="high",
            metadata={
                "recording_id": str(recording.id),
                "recording_url": recording.recording_url,
                "qa_score": qa_score,
                "agent_id": agent_id
            },
            created_at=datetime.now(timezone.utc)
        )
        db.add(task)
        db.commit()

        logger.info(f"Created QA review task for recording {recording.id}")

    except Exception as e:
        logger.error(f"Error creating QA review task: {e}")
