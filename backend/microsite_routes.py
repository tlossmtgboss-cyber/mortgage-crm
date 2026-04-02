"""
Microsite Routes - Public endpoints for Loan Officer microsites and lead capture

These endpoints don't require authentication and support:
- Public LO profile retrieval by slug or ID
- Lead submission from microsite forms
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import logging
import os

# Lazy import for get_db to avoid circular dependency with main.py
def get_db():
    """Wrapper for get_db to avoid circular import with main.py."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1/public", tags=["Microsite"])


# ============================================================================
# Pydantic Models
# ============================================================================

class LOProfileResponse(BaseModel):
    """Public loan officer profile response"""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    nmls_id: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    avatar_url: Optional[str] = None
    slug: Optional[str] = None

    class Config:
        from_attributes = True


class MicrositeLeadCreate(BaseModel):
    """Lead submission from microsite"""
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    property_type: Optional[str] = None
    loan_type: Optional[str] = "purchase"
    estimated_value: Optional[str] = None
    down_payment: Optional[str] = None
    credit_score_range: Optional[str] = None
    timeline: Optional[str] = None
    message: Optional[str] = None

    # Attribution
    source: Optional[str] = "microsite"
    loan_officer_id: Optional[int] = None
    referral_source: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class MicrositeLeadResponse(BaseModel):
    """Response after lead submission"""
    success: bool
    message: str
    lead_id: Optional[int] = None


# ============================================================================
# Public Routes
# ============================================================================

@router.get("/loan-officer/{identifier}", response_model=LOProfileResponse)
async def get_lo_profile(
    identifier: str,
    db: Session = Depends(get_db)
):
    """
    Get public loan officer profile by slug or ID.

    This endpoint is used by the LO microsite to display the loan officer's
    public profile information.
    """
    try:
        # Try to import User model
        from database.models import User

        # First try to find by slug
        user = db.query(User).filter(
            User.slug == identifier,
            User.is_active == True
        ).first()

        # If not found by slug, try by ID
        if not user:
            try:
                user_id = int(identifier)
                user = db.query(User).filter(
                    User.id == user_id,
                    User.is_active == True
                ).first()
            except ValueError:
                pass

        if not user:
            raise HTTPException(status_code=404, detail="Loan officer profile not found")

        # Build response with available fields
        return LOProfileResponse(
            id=user.id,
            first_name=getattr(user, 'first_name', None),
            last_name=getattr(user, 'last_name', None),
            name=getattr(user, 'name', None) or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            email=user.email,
            phone=getattr(user, 'phone', None),
            company=getattr(user, 'company', None),
            nmls_id=getattr(user, 'nmls_id', None),
            bio=getattr(user, 'bio', None),
            photo_url=getattr(user, 'photo_url', None),
            avatar_url=getattr(user, 'avatar_url', None),
            slug=getattr(user, 'slug', None)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching LO profile: {e}")
        raise HTTPException(status_code=500, detail="Error fetching profile")


@router.post("/leads", response_model=MicrositeLeadResponse)
async def submit_microsite_lead(
    lead_data: MicrositeLeadCreate,
    db: Session = Depends(get_db)
):
    """
    Submit a lead from the microsite lead capture form.

    This creates a new lead in the system with proper attribution
    to the loan officer whose microsite generated the lead.
    """
    try:
        # Try to import Lead model
        from database.models import Lead

        # Check if Lead model has the required fields
        lead_dict = {
            'first_name': lead_data.first_name,
            'last_name': lead_data.last_name,
            'email': lead_data.email,
            'phone': lead_data.phone,
            'source': lead_data.source or 'microsite',
            'status': 'new',
            'created_at': datetime.now(timezone.utc),
        }

        # Add optional fields if they exist on the model
        optional_fields = [
            'property_type', 'loan_type', 'estimated_value', 'down_payment',
            'credit_score_range', 'timeline', 'message', 'loan_officer_id',
            'referral_source', 'utm_source', 'utm_medium', 'utm_campaign'
        ]

        for field in optional_fields:
            value = getattr(lead_data, field, None)
            if value is not None:
                # Check if the Lead model has this attribute
                if hasattr(Lead, field):
                    lead_dict[field] = value

        # If loan_officer_id is provided, also set assigned_to
        if lead_data.loan_officer_id and hasattr(Lead, 'assigned_to'):
            lead_dict['assigned_to'] = lead_data.loan_officer_id

        # Create the lead
        new_lead = Lead(**lead_dict)
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

        logger.info(f"New microsite lead created: {new_lead.id} for LO: {lead_data.loan_officer_id}")

        # Send notification email to LO (async, don't block)
        try:
            if lead_data.loan_officer_id:
                from database.models import User
                lo = db.query(User).filter(User.id == lead_data.loan_officer_id).first()
                if lo and lo.email:
                    # Import and send notification email
                    try:
                        from email_service import send_lead_notification_email
                        import asyncio

                        # Get LO name
                        lo_name = getattr(lo, 'name', None) or \
                                  f"{getattr(lo, 'first_name', '')} {getattr(lo, 'last_name', '')}".strip() or \
                                  "Loan Officer"

                        # Build lead name
                        lead_name = f"{lead_data.first_name} {lead_data.last_name}"

                        # Send notification (run async in background)
                        asyncio.create_task(send_lead_notification_email(
                            to_email=lo.email,
                            lo_name=lo_name,
                            lead_name=lead_name,
                            lead_email=lead_data.email,
                            lead_phone=lead_data.phone,
                            loan_type=lead_data.loan_type or "purchase",
                            source=lead_data.source or "microsite",
                            message=lead_data.message,
                            lead_id=new_lead.id
                        ))
                        logger.info(f"Lead notification email queued for LO {lo.email}")
                    except Exception as email_err:
                        logger.warning(f"Could not send LO notification email: {email_err}")
        except Exception as e:
            logger.warning(f"Could not send LO notification: {e}")

        return MicrositeLeadResponse(
            success=True,
            message="Thank you! Your information has been submitted. We'll be in touch soon.",
            lead_id=new_lead.id
        )

    except Exception as e:
        logger.error(f"Error creating microsite lead: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="There was an error submitting your information. Please try again."
        )


@router.get("/loan-officers", response_model=List[LOProfileResponse])
async def list_loan_officers(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    List public loan officer profiles.

    This can be used for a directory page or search functionality.
    """
    try:
        from database.models import User

        # Query active users who are loan officers
        query = db.query(User).filter(
            User.is_active == True
        )

        # Try to filter by role if the field exists
        if hasattr(User, 'role'):
            query = query.filter(User.role == 'loan_officer')

        users = query.limit(limit).all()

        results = []
        for user in users:
            results.append(LOProfileResponse(
                id=user.id,
                first_name=getattr(user, 'first_name', None),
                last_name=getattr(user, 'last_name', None),
                name=getattr(user, 'name', None) or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
                email=user.email,
                phone=getattr(user, 'phone', None),
                company=getattr(user, 'company', None),
                nmls_id=getattr(user, 'nmls_id', None),
                bio=getattr(user, 'bio', None),
                photo_url=getattr(user, 'photo_url', None),
                avatar_url=getattr(user, 'avatar_url', None),
                slug=getattr(user, 'slug', None)
            ))

        return results

    except Exception as e:
        logger.error(f"Error listing loan officers: {e}")
        raise HTTPException(status_code=500, detail="Error fetching loan officers")
