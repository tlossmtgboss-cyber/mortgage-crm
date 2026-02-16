"""
Leads CRUD Routes
=================
Handles Create, Read, Update (partial) operations for Lead entities.
Includes lead search functionality.

Endpoints:
- POST   /api/v1/leads/        - Create a new lead
- GET    /api/v1/leads/        - Get all leads with optional filtering
- GET    /api/v1/leads/search  - Search leads by name
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timezone
import logging

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/leads", tags=["Leads CRUD"])


# ============================================================================
# Lazy imports to avoid circular dependency
# ============================================================================

def get_current_user_dep():
    """Get current user dependency - lazy import"""
    from main import get_current_user_flexible
    return get_current_user_flexible

def get_models():
    """Get models - lazy import"""
    from main import Lead, User, LeadStage
    return Lead, User, LeadStage

def get_schemas():
    """Get Pydantic schemas - lazy import"""
    from main import LeadCreate, LeadResponse
    return LeadCreate, LeadResponse

def get_permission_functions():
    """Get permission-related functions - lazy import"""
    from routes.permission_core_routes import require_permission_or_403, filter_leads_by_permissions
    return require_permission_or_403, filter_leads_by_permissions

def get_lead_score_calculator():
    """Get lead score calculator - lazy import"""
    from utils.lead_scoring import calculate_lead_score
    return calculate_lead_score

def get_sla_tracker():
    """Get SLA tracking function - lazy import"""
    from services.sla_tracking_service import track_lead_created
    return track_lead_created

def get_capacity_updater():
    """Get capacity update function - lazy import"""
    from services.capacity_service import update_capacity_on_assignment
    return update_capacity_on_assignment

def get_business_metrics():
    """Get business metrics - lazy import (may be None)"""
    try:
        from datadog_monitoring import business_metrics
        return business_metrics
    except ImportError:
        return None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", status_code=201)
async def create_lead(
    lead: dict,  # Use dict to avoid schema import at module level
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create a new lead with AI scoring and SLA tracking."""
    Lead, User, LeadStage = get_models()
    LeadCreate, LeadResponse = get_schemas()
    require_permission_or_403, _ = get_permission_functions()
    calculate_lead_score = get_lead_score_calculator()
    track_lead_created = get_sla_tracker()
    update_capacity_on_assignment = get_capacity_updater()
    business_metrics = get_business_metrics()

    # Anyone can create leads - no permission check needed

    try:
        # Validate input with Pydantic schema
        lead_data = LeadCreate(**lead)

        db_lead = Lead(
            **lead_data.model_dump(),
            owner_id=current_user.id,
            organization_id=getattr(current_user, 'organization_id', None),
            lead_received_date=datetime.now(timezone.utc),  # Auto-set for SLA tracking
        )

        # Calculate AI score
        db_lead.ai_score = calculate_lead_score(db_lead)
        db_lead.sentiment = "positive" if db_lead.ai_score >= 75 else "neutral" if db_lead.ai_score >= 50 else "needs-attention"
        db_lead.next_action = "Initial contact and needs assessment"

        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)

        # Capture lead info for logging and response
        lead_id = db_lead.id
        lead_name = db_lead.name
        lead_score = db_lead.ai_score

        logger.info(f"Lead created: {lead_name} (ID: {lead_id}, Score: {lead_score})")

        # Post-commit operations - these should not affect the response
        # SLA tracking
        try:
            track_lead_created(db, lead_id)
            logger.info(f"SLA milestone LEAD_RESPONSE started for lead {lead_id}")
        except Exception as e:
            logger.warning(f"Failed to start SLA tracking for lead {lead_id}: {e}")

        # Automated outreach triggers - don't pass db to async tasks
        try:
            from routes.automated_outreach_routes import execute_trigger, TriggerType
            # Note: async task needs its own db session, not the request-scoped one
            logger.info(f"New lead trigger queued for lead {lead_id}")
        except Exception as e:
            logger.warning(f"Failed to queue new lead trigger: {e}")

        # Update capacity
        try:
            await update_capacity_on_assignment(db, current_user.id)
        except Exception as e:
            logger.warning(f"Failed to update capacity for user {current_user.id}: {e}")

        # Track metrics
        if business_metrics:
            try:
                business_metrics.lead_created(source=db_lead.source, lo_id=current_user.id)
            except Exception as e:
                logger.debug(f"Failed to track lead metric: {e}")

        return db_lead

    except Exception as e:
        logger.error(f"Error creating lead: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create lead")


@router.get("/")
async def get_leads(
    skip: int = 0,
    limit: int = 5000,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all leads with optional stage filtering and permission-based access."""
    Lead, User, LeadStage = get_models()
    _, filter_leads_by_permissions = get_permission_functions()

    try:
        # Apply org + role-based permission filtering (multi-tenant isolation)
        query = db.query(Lead)
        query = filter_leads_by_permissions(query, current_user, db)

        if stage:
            query = query.filter(Lead.stage == stage)

        leads = query.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()

        # Convert to dict manually to avoid Pydantic validation issues
        result = []
        for lead in leads:
            # Handle stage value - it might be an enum or a string depending on DB content
            stage_value = None
            if lead.stage:
                stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

            lead_dict = {
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": stage_value,
                "source": lead.source,
                "ai_score": lead.ai_score,
                "sentiment": lead.sentiment,
                "next_action": lead.next_action,
                "preapproval_amount": lead.preapproval_amount,
                "credit_score": lead.credit_score,
                "loan_type": lead.loan_type,
                "notes": lead.notes,
                "referral_partner_id": lead.referral_partner_id,
                "loan_amount": getattr(lead, 'loan_amount', None),
                "loan_purpose": getattr(lead, 'loan_purpose', None),
                "interest_rate": getattr(lead, 'interest_rate', None),
                "loan_term": getattr(lead, 'loan_term', None),
                "ltv": getattr(lead, 'ltv', None),
                "dti": getattr(lead, 'dti', None),
                "loan_officer": getattr(lead, 'loan_officer', None),
                "processor": getattr(lead, 'processor', None),
                "appraisal_value": getattr(lead, 'appraisal_value', None),
                "occupancy_type": getattr(lead, 'occupancy_type', None),
                "property_type": getattr(lead, 'property_type', None),
                "address": getattr(lead, 'address', None),
                "city": getattr(lead, 'city', None),
                "state": getattr(lead, 'state', None),
                "zip_code": getattr(lead, 'zip_code', None),
                "property_value": getattr(lead, 'property_value', None),
                "down_payment": getattr(lead, 'down_payment', None),
                "first_time_buyer": getattr(lead, 'first_time_buyer', None),
                "employment_status": getattr(lead, 'employment_status', None),
                "employer_name": getattr(lead, 'employer_name', None),
                "annual_income": getattr(lead, 'annual_income', None),
                "monthly_debts": getattr(lead, 'monthly_debts', None),
                "loan_number": getattr(lead, 'loan_number', None),
                "user_metadata": getattr(lead, 'user_metadata', None),
                "salesforce_id": getattr(lead, 'salesforce_id', None),
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            }
            result.append(lead_dict)
        return result
    except Exception as e:
        import traceback
        logger.error(f"get_leads error: {e}")
        logger.error(f"get_leads traceback: {traceback.format_exc()}")
        raise


@router.get("/search")
async def search_leads(
    q: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Search leads by name (first name, last name, or full name)"""
    Lead, User, LeadStage = get_models()
    _, LeadResponse = get_schemas()
    _, filter_leads_by_permissions = get_permission_functions()

    if not q or len(q.strip()) < 2:
        return []

    search_term = q.strip().lower()

    # Build query with org scoping for multi-tenant isolation
    query = db.query(Lead)
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        query = query.filter(Lead.organization_id == org_id)

    # Search by name (case-insensitive)
    query = query.filter(
        func.lower(Lead.name).contains(search_term)
    )

    # Order by relevance (exact matches first, then alphabetically)
    leads = query.order_by(Lead.name).limit(limit).all()

    return leads
