"""
Shared Data Access Layer (DAL)

Repository-pattern functions for the most commonly duplicated database queries
across the codebase. Provides consistent, tenant-isolated lookups for core
entities: Loan, Lead, User, Organization, and Appointment.

Each function accepts a SQLAlchemy session and returns the model instance(s) or
None. Tenant isolation is applied automatically when org_id is provided.

Usage:
    from services.data_access import get_loan_by_id, get_lead_by_email

    loan = get_loan_by_id(db, loan_id=42, org_id=current_user.organization_id)
    lead = get_lead_by_email(db, email="borrower@example.com", org_id=1)

NOTE: This module is additive only. Existing callers are NOT refactored to use
these functions yet — this establishes the shared layer for incremental adoption.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

from services.workflow_constants import TERMINAL_LOAN_STAGES


# =============================================================================
# Internal helpers
# =============================================================================

def _ensure_models():
    """
    Lazy-import models to avoid circular imports at module load time.
    Returns a namespace dict with the five core model classes.
    """
    # These imports are deferred so that this module can be imported early
    # in the application lifecycle without triggering model-registration issues.
    from database.models.lead_loan import Lead, Loan
    from database.models.core import Organization, User
    from database.models.scheduler import Appointment

    return {
        "Lead": Lead,
        "Loan": Loan,
        "User": User,
        "Organization": Organization,
        "Appointment": Appointment,
    }


# =============================================================================
# LOAN LOOKUPS
# =============================================================================

def get_loan_by_id(
    db: Session,
    loan_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a single Loan by primary key.

    Args:
        db: Active SQLAlchemy session.
        loan_id: Loan primary key (integer).
        org_id: If provided, enforces tenant isolation by requiring
                the loan's organization_id to match.

    Returns:
        Loan instance or None if not found / not in tenant scope.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = db.query(Loan).filter(Loan.id == loan_id)
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.first()


def get_loan_by_number(
    db: Session,
    loan_number: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a single Loan by its unique loan_number string.

    Args:
        db: Active SQLAlchemy session.
        loan_number: The loan number (e.g. "2024-001234").
        org_id: Optional tenant isolation filter.

    Returns:
        Loan instance or None.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = db.query(Loan).filter(Loan.loan_number == loan_number)
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.first()


def get_loans_by_stage(
    db: Session,
    stage: str,
    org_id: Optional[int] = None,
    lo_id: Optional[int] = None,
    limit: int = 50,
) -> List[object]:
    """
    Fetch loans filtered by pipeline stage.

    Args:
        db: Active SQLAlchemy session.
        stage: Loan stage string (e.g. "PROCESSING", "UNDERWRITING").
               Compared case-sensitively against the stage column.
        org_id: Optional tenant isolation filter.
        lo_id: Optional loan officer filter.
        limit: Maximum rows to return (default 50).

    Returns:
        List of Loan instances (may be empty).
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = db.query(Loan).filter(Loan.stage == stage)
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)
    if lo_id is not None:
        query = query.filter(Loan.loan_officer_id == lo_id)

    return query.order_by(Loan.stage_changed_at.desc()).limit(limit).all()


def get_active_loans_for_lo(
    db: Session,
    lo_id: int,
    org_id: Optional[int] = None,
) -> List[object]:
    """
    Fetch all active (non-terminal) loans assigned to a loan officer.

    Terminal stages excluded: FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN,
    DOES_NOT_QUALIFY.

    Args:
        db: Active SQLAlchemy session.
        lo_id: Loan officer user ID (users.id).
        org_id: Optional tenant isolation filter.

    Returns:
        List of active Loan instances for the LO.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = (
        db.query(Loan)
        .filter(
            Loan.loan_officer_id == lo_id,
            Loan.stage.notin_(TERMINAL_LOAN_STAGES),
        )
    )
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.order_by(Loan.stage_changed_at.desc()).all()


def get_loan_by_salesforce_id(
    db: Session,
    salesforce_id: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Loan by its Salesforce external ID.

    Args:
        db: Active SQLAlchemy session.
        salesforce_id: The Salesforce record ID string.
        org_id: Optional tenant isolation filter.

    Returns:
        Loan instance or None.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = db.query(Loan).filter(Loan.salesforce_id == salesforce_id)
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.first()


def get_loan_by_encompass_id(
    db: Session,
    encompass_loan_id: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Loan by its Encompass LOS loan ID.

    Args:
        db: Active SQLAlchemy session.
        encompass_loan_id: The Encompass loan identifier string.
        org_id: Optional tenant isolation filter.

    Returns:
        Loan instance or None.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = db.query(Loan).filter(Loan.encompass_loan_id == encompass_loan_id)
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.first()


# =============================================================================
# LEAD LOOKUPS
# =============================================================================

def get_lead_by_id(
    db: Session,
    lead_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a single Lead by primary key.

    Args:
        db: Active SQLAlchemy session.
        lead_id: Lead primary key (integer).
        org_id: Optional tenant isolation filter.

    Returns:
        Lead instance or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = db.query(Lead).filter(Lead.id == lead_id)
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()


def get_lead_by_email(
    db: Session,
    email: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Lead by email address. Returns the first match.

    NOTE: Email is not unique across tenants; always pass org_id in
    multi-tenant contexts to avoid cross-tenant data leakage.

    Args:
        db: Active SQLAlchemy session.
        email: Email address to match (case-sensitive in DB).
        org_id: Optional tenant isolation filter (strongly recommended).

    Returns:
        Lead instance or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = db.query(Lead).filter(Lead.email == email)
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()


def get_lead_by_phone(
    db: Session,
    phone: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Lead by phone number. Returns the first match.

    Args:
        db: Active SQLAlchemy session.
        phone: Phone number string to match.
        org_id: Optional tenant isolation filter (strongly recommended).

    Returns:
        Lead instance or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = db.query(Lead).filter(Lead.phone == phone)
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()


def get_leads_by_owner(
    db: Session,
    owner_id: int,
    org_id: Optional[int] = None,
    stage: Optional[str] = None,
    limit: int = 100,
) -> List[object]:
    """
    Fetch leads assigned to a specific owner (loan officer).

    Args:
        db: Active SQLAlchemy session.
        owner_id: The owner user ID (users.id → leads.owner_id).
        org_id: Optional tenant isolation filter.
        stage: Optional stage filter (e.g. "New", "Contacted").
        limit: Maximum rows to return (default 100).

    Returns:
        List of Lead instances.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = db.query(Lead).filter(Lead.owner_id == owner_id)
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)
    if stage is not None:
        query = query.filter(Lead.stage == stage)

    return query.order_by(Lead.created_at.desc()).limit(limit).all()


def get_lead_by_loan_number(
    db: Session,
    loan_number: str,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Lead that has been linked to a loan_number.

    Args:
        db: Active SQLAlchemy session.
        loan_number: The loan number string (leads.loan_number).
        org_id: Optional tenant isolation filter.

    Returns:
        Lead instance or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = db.query(Lead).filter(Lead.loan_number == loan_number)
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()


# =============================================================================
# USER LOOKUPS
# =============================================================================

def get_user_by_id(
    db: Session,
    user_id: int,
) -> Optional[object]:
    """
    Fetch a User by primary key.

    Args:
        db: Active SQLAlchemy session.
        user_id: User primary key (integer).

    Returns:
        User instance or None.
    """
    m = _ensure_models()
    User = m["User"]

    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(
    db: Session,
    email: str,
) -> Optional[object]:
    """
    Fetch a User by unique email address.

    Args:
        db: Active SQLAlchemy session.
        email: Email address (unique column on users table).

    Returns:
        User instance or None.
    """
    m = _ensure_models()
    User = m["User"]

    return db.query(User).filter(User.email == email).first()


def get_users_by_org(
    db: Session,
    org_id: int,
    active_only: bool = True,
) -> List[object]:
    """
    Fetch all users belonging to an organization.

    Args:
        db: Active SQLAlchemy session.
        org_id: Organization primary key.
        active_only: If True (default), only return users where is_active=True.

    Returns:
        List of User instances.
    """
    m = _ensure_models()
    User = m["User"]

    query = db.query(User).filter(User.organization_id == org_id)
    if active_only:
        query = query.filter(User.is_active == True)  # noqa: E712 (SQLAlchemy requires ==)

    return query.order_by(User.last_name, User.first_name).all()


# =============================================================================
# ORGANIZATION LOOKUPS
# =============================================================================

def get_organization_by_id(
    db: Session,
    org_id: int,
) -> Optional[object]:
    """
    Fetch an Organization by primary key.

    Args:
        db: Active SQLAlchemy session.
        org_id: Organization primary key (integer).

    Returns:
        Organization instance or None.
    """
    m = _ensure_models()
    Organization = m["Organization"]

    return db.query(Organization).filter(Organization.id == org_id).first()


def get_organization_by_slug(
    db: Session,
    slug: str,
) -> Optional[object]:
    """
    Fetch an Organization by its URL-friendly slug.

    Args:
        db: Active SQLAlchemy session.
        slug: URL slug (unique column on organizations table).

    Returns:
        Organization instance or None.
    """
    m = _ensure_models()
    Organization = m["Organization"]

    return db.query(Organization).filter(Organization.slug == slug).first()


def get_organization_by_booking_slug(
    db: Session,
    booking_slug: str,
) -> Optional[object]:
    """
    Fetch an Organization by its public booking page slug.

    Args:
        db: Active SQLAlchemy session.
        booking_slug: Booking page slug (unique column on organizations table).

    Returns:
        Organization instance or None.
    """
    m = _ensure_models()
    Organization = m["Organization"]

    return (
        db.query(Organization)
        .filter(Organization.booking_slug == booking_slug)
        .first()
    )


# =============================================================================
# APPOINTMENT LOOKUPS
# =============================================================================

def get_appointment_by_id(
    db: Session,
    appointment_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a scheduler Appointment by primary key.

    The Appointment model lives at database.models.scheduler.Appointment
    (table: scheduler_appointments).

    Args:
        db: Active SQLAlchemy session.
        appointment_id: Appointment primary key (integer).
        org_id: Optional tenant isolation filter.

    Returns:
        Appointment instance or None.
    """
    m = _ensure_models()
    Appointment = m["Appointment"]

    query = db.query(Appointment).filter(Appointment.id == appointment_id)
    if org_id is not None:
        query = query.filter(Appointment.organization_id == org_id)

    return query.first()


def get_appointments_for_user(
    db: Session,
    user_id: int,
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    upcoming_only: bool = False,
) -> List[object]:
    """
    Fetch appointments assigned to a specific user.

    Args:
        db: Active SQLAlchemy session.
        user_id: The assigned user ID (users.id).
        org_id: Optional tenant isolation filter.
        status: Optional status filter (e.g. "booked", "confirmed").
                Should match AppointmentStatus enum values.
        upcoming_only: If True, only return appointments with
                       scheduled_start > now.

    Returns:
        List of Appointment instances ordered by scheduled_start ascending.
    """
    from datetime import datetime, timezone

    m = _ensure_models()
    Appointment = m["Appointment"]

    query = db.query(Appointment).filter(Appointment.assigned_user_id == user_id)
    if org_id is not None:
        query = query.filter(Appointment.organization_id == org_id)
    if status is not None:
        query = query.filter(Appointment.status == status)
    if upcoming_only:
        query = query.filter(Appointment.scheduled_start > datetime.now(timezone.utc))

    return query.order_by(Appointment.scheduled_start.asc()).all()


def get_appointments_for_lead(
    db: Session,
    lead_id: int,
    org_id: Optional[int] = None,
) -> List[object]:
    """
    Fetch all appointments linked to a specific lead.

    Args:
        db: Active SQLAlchemy session.
        lead_id: The lead ID (leads.id).
        org_id: Optional tenant isolation filter.

    Returns:
        List of Appointment instances ordered by scheduled_start descending.
    """
    m = _ensure_models()
    Appointment = m["Appointment"]

    query = db.query(Appointment).filter(Appointment.lead_id == lead_id)
    if org_id is not None:
        query = query.filter(Appointment.organization_id == org_id)

    return query.order_by(Appointment.scheduled_start.desc()).all()


def get_appointments_for_loan(
    db: Session,
    loan_id: int,
    org_id: Optional[int] = None,
) -> List[object]:
    """
    Fetch all appointments linked to a specific loan.

    Args:
        db: Active SQLAlchemy session.
        loan_id: The loan ID (loans.id).
        org_id: Optional tenant isolation filter.

    Returns:
        List of Appointment instances ordered by scheduled_start descending.
    """
    m = _ensure_models()
    Appointment = m["Appointment"]

    query = db.query(Appointment).filter(Appointment.loan_id == loan_id)
    if org_id is not None:
        query = query.filter(Appointment.organization_id == org_id)

    return query.order_by(Appointment.scheduled_start.desc()).all()


# =============================================================================
# CONVENIENCE / CROSS-ENTITY LOOKUPS
# =============================================================================

def get_loan_with_officer(
    db: Session,
    loan_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Loan with the loan_officer relationship eagerly loaded.

    Avoids the N+1 problem when the caller needs both loan and LO data.

    Args:
        db: Active SQLAlchemy session.
        loan_id: Loan primary key.
        org_id: Optional tenant isolation filter.

    Returns:
        Loan instance (with .loan_officer populated) or None.
    """
    m = _ensure_models()
    Loan = m["Loan"]

    query = (
        db.query(Loan)
        .options(joinedload(Loan.loan_officer))
        .filter(Loan.id == loan_id)
    )
    if org_id is not None:
        query = query.filter(Loan.organization_id == org_id)

    return query.first()


def get_lead_with_owner(
    db: Session,
    lead_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Lead with the owner (assigned LO) relationship eagerly loaded.

    Args:
        db: Active SQLAlchemy session.
        lead_id: Lead primary key.
        org_id: Optional tenant isolation filter.

    Returns:
        Lead instance (with .owner populated) or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = (
        db.query(Lead)
        .options(joinedload(Lead.owner))
        .filter(Lead.id == lead_id)
    )
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()


def get_lead_with_activities(
    db: Session,
    lead_id: int,
    org_id: Optional[int] = None,
) -> Optional[object]:
    """
    Fetch a Lead with activities eagerly loaded.

    Args:
        db: Active SQLAlchemy session.
        lead_id: Lead primary key.
        org_id: Optional tenant isolation filter.

    Returns:
        Lead instance (with .activities populated) or None.
    """
    m = _ensure_models()
    Lead = m["Lead"]

    query = (
        db.query(Lead)
        .options(joinedload(Lead.activities))
        .filter(Lead.id == lead_id)
    )
    if org_id is not None:
        query = query.filter(Lead.organization_id == org_id)

    return query.first()
