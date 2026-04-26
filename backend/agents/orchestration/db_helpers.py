"""
Database Helpers for Agent Orchestration

Provides helper functions for fetching organization and user data
for dynamic company name injection and white-label functionality.
"""

from typing import Dict, Optional, Any
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def get_organization_for_agent(
    db: Session,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get organization details for agent white-labeling.

    Uses the central company_name_resolver for the customer-facing name,
    ensuring consistency across voice, email, docs, and agent prompts.

    Args:
        db: Database session
        organization_id: Organization ID (primary lookup)
        user_id: User ID (fallback lookup via user's organization)

    Returns:
        Organization dict with branding info:
        {
            "id": int,
            "name": str,
            "brand_name": str,        # What agents say
            "display_name": str,      # What customers see
            "website": str,
            "phone": str,
            "agent_personas": dict,   # Custom agent names per org
            "custom_prompts": dict,   # Org-specific prompt overrides
        }
    """
    from services.company_name_resolver import resolve_company_name

    # Default organization fallback
    fallback_name = resolve_company_name(db, organization_id)
    default_org = {
        "id": None,
        "name": fallback_name,
        "brand_name": fallback_name,
        "display_name": fallback_name,
        "website": None,
        "phone": None,
        "agent_personas": {},
        "custom_prompts": {},
    }

    try:
        org = None

        # Try to get organization by ID
        if organization_id:
            from database.models import Organization
            org = db.query(Organization).filter(
                Organization.id == organization_id,
                Organization.is_active == True
            ).first()

        # Fallback: Get organization via user
        if not org and user_id:
            from database.models import User, Organization
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.organization_id:
                org = db.query(Organization).filter(
                    Organization.id == user.organization_id,
                    Organization.is_active == True
                ).first()

        if not org:
            logger.warning(f"Organization not found: org_id={organization_id}, user_id={user_id}")
            return default_org

        # Resolve the canonical customer-facing name via central resolver
        company_name = resolve_company_name(db, org.id)

        # Extract branding info from organization
        settings = org.settings or {}

        return {
            "id": org.id,
            "name": company_name,
            "brand_name": company_name,
            "display_name": company_name,
            "website": settings.get("website"),
            "phone": settings.get("phone") or settings.get("support_phone"),
            "agent_personas": settings.get("agent_personas", {}),
            "custom_prompts": settings.get("custom_prompts", {}),
            "logo_url": settings.get("logo_url"),
            "primary_color": settings.get("primary_color"),
        }

    except Exception as e:
        logger.error(f"Error fetching organization: {e}", exc_info=True)
        return default_org


def get_user_profile_for_agent(
    db: Session,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    contact_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get user/lead profile for agent personalization.

    Args:
        db: Database session
        user_id: Internal user ID
        lead_id: Lead ID
        contact_id: Contact ID

    Returns:
        User profile dict:
        {
            "id": int,
            "first_name": str,
            "last_name": str,
            "email": str,
            "phone": str,
            "organization_id": int,
            "metadata": dict,
        }
    """
    default_profile = {
        "id": None,
        "first_name": "there",
        "last_name": "",
        "email": "",
        "phone": "",
        "organization_id": None,
        "metadata": {},
    }

    try:
        # Try to get lead
        if lead_id:
            from database.models import Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                return {
                    "id": lead.id,
                    "first_name": lead.first_name or "there",
                    "last_name": lead.last_name or "",
                    "email": lead.email or "",
                    "phone": lead.phone or "",
                    "organization_id": lead.organization_id,
                    "loan_purpose": getattr(lead, "loan_purpose", None),
                    "property_type": getattr(lead, "property_type", None),
                    "metadata": {},
                }

        # Try to get contact (using Lead model - no separate Contact model exists)
        if contact_id:
            from database.models import Lead as Contact
            contact = db.query(Contact).filter(Contact.id == contact_id).first()
            if contact:
                return {
                    "id": contact.id,
                    "first_name": contact.first_name or "there",
                    "last_name": contact.last_name or "",
                    "email": contact.email or "",
                    "phone": contact.phone or "",
                    "organization_id": getattr(contact, "organization_id", None),
                    "metadata": {},
                }

        # Try to get user (for internal users)
        if user_id:
            from database.models import User
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return {
                    "id": user.id,
                    "first_name": user.first_name or user.name or "there",
                    "last_name": user.last_name or "",
                    "email": user.email or "",
                    "phone": getattr(user, "phone", ""),
                    "organization_id": user.organization_id,
                    "metadata": {},
                }

        return default_profile

    except Exception as e:
        logger.error(f"Error fetching user profile: {e}", exc_info=True)
        return default_profile


def get_organization_with_user(
    db: Session,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get both organization and user profile in one call.

    Args:
        db: Database session
        user_id: Internal user ID
        lead_id: Lead ID
        organization_id: Organization ID (optional, will be inferred from user/lead)

    Returns:
        {
            "user": {...user profile...},
            "organization": {...organization branding...}
        }
    """
    # Get user profile
    user_profile = get_user_profile_for_agent(
        db,
        user_id=user_id,
        lead_id=lead_id
    )

    # Get organization (use explicit org_id or infer from user profile)
    org_id = organization_id or user_profile.get("organization_id")
    organization = get_organization_for_agent(db, organization_id=org_id)

    return {
        "user": user_profile,
        "organization": organization,
    }


def update_organization_branding(
    db: Session,
    organization_id: int,
    brand_name: Optional[str] = None,
    display_name: Optional[str] = None,
    website: Optional[str] = None,
    phone: Optional[str] = None,
    agent_personas: Optional[Dict] = None,
) -> bool:
    """
    Update organization branding settings for agents.

    Args:
        db: Database session
        organization_id: Organization ID
        brand_name: Company name agents should use
        display_name: Company name for customer-facing displays
        website: Company website
        phone: Company phone
        agent_personas: Custom agent names/roles for this org

    Returns:
        True if updated successfully
    """
    try:
        from database.models import Organization
        org = db.query(Organization).filter(Organization.id == organization_id).first()

        if not org:
            logger.error(f"Organization {organization_id} not found")
            return False

        # Initialize settings if None
        if org.settings is None:
            org.settings = {}

        # Update settings
        if brand_name is not None:
            org.settings["brand_name"] = brand_name
        if display_name is not None:
            org.settings["display_name"] = display_name
        if website is not None:
            org.settings["website"] = website
        if phone is not None:
            org.settings["phone"] = phone
        if agent_personas is not None:
            org.settings["agent_personas"] = agent_personas

        db.commit()
        logger.info(f"Updated branding for organization {organization_id}")
        return True

    except Exception as e:
        logger.error(f"Error updating organization branding: {e}", exc_info=True)
        db.rollback()
        return False


def get_agent_persona_for_org(
    db: Session,
    organization_id: int,
    agent_id: str
) -> Dict[str, str]:
    """
    Get custom agent persona for a specific organization.

    Args:
        db: Database session
        organization_id: Organization ID
        agent_id: Agent identifier (e.g., "lead_agent")

    Returns:
        {"name": "CustomName", "role": "Custom Role"} or empty dict
    """
    org = get_organization_for_agent(db, organization_id=organization_id)
    personas = org.get("agent_personas", {})
    return personas.get(agent_id, {})
