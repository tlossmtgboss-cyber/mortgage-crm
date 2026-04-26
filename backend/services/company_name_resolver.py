"""
Company Name Resolver

Single source of truth for resolving an organization's customer-facing name.
Used by voice agents, emails, documents, calendar invites, and SMS.

Resolution order:
1. organization_branding.company_name (white-label override)
2. Organization.settings["brand_name"] or settings["display_name"]
3. Organization.name
4. COMPANY_NAME environment variable
5. Hardcoded fallback
"""

import logging
import os
from functools import lru_cache
from time import time
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FALLBACK = os.getenv("COMPANY_NAME", "The Tim Loss Team")

# TTL cache: org names rarely change, avoid hitting DB on every call
_cache: dict = {}  # {org_id: (name, timestamp)}
_CACHE_TTL = 300  # 5 minutes


def resolve_company_name(
    db: Session,
    organization_id: Optional[int] = None,
) -> str:
    """
    Resolve the customer-facing company name for an organization.

    Args:
        db: Active SQLAlchemy session
        organization_id: The org to resolve. Returns fallback if None.

    Returns:
        The company name string to use in customer-facing contexts.
    """
    if not organization_id:
        return _FALLBACK

    # Check cache
    cached = _cache.get(organization_id)
    if cached and (time() - cached[1]) < _CACHE_TTL:
        return cached[0]

    name = _resolve_from_db(db, organization_id)
    _cache[organization_id] = (name, time())
    return name


def invalidate_cache(organization_id: Optional[int] = None):
    """Clear cached company name. Call when branding is updated."""
    if organization_id:
        _cache.pop(organization_id, None)
    else:
        _cache.clear()


def _resolve_from_db(db: Session, org_id: int) -> str:
    """DB resolution: branding table → org settings → org name → fallback."""
    from sqlalchemy import text

    try:
        # 1. Check organization_branding table (white-label override)
        row = db.execute(text(
            "SELECT company_name FROM organization_branding "
            "WHERE organization_id = :org_id"
        ), {"org_id": org_id}).fetchone()

        if row and row[0]:
            return row[0]

        # 2. Check Organization record (name + settings JSON)
        org_row = db.execute(text(
            "SELECT name, settings FROM organizations "
            "WHERE id = :org_id AND is_active = true"
        ), {"org_id": org_id}).fetchone()

        if org_row:
            # 2a. Check settings JSON for brand_name/display_name
            settings = org_row[1] if org_row[1] else {}
            if isinstance(settings, dict):
                brand = settings.get("brand_name") or settings.get("display_name")
                if brand:
                    return brand

            # 2b. Fall back to org.name
            if org_row[0]:
                return org_row[0]

    except Exception as e:
        logger.warning(f"Error resolving company name for org {org_id}: {e}")

    return _FALLBACK


def resolve_company_name_from_context(db: Session) -> str:
    """
    Resolve company name using the request-scoped org_id from contextvars.
    Use this in code paths where org_id isn't explicitly passed.
    """
    try:
        from middleware.request_context import get_org_id
        org_id_str = get_org_id()
        org_id = int(org_id_str) if org_id_str else None
        return resolve_company_name(db, org_id)
    except (ValueError, TypeError):
        return _FALLBACK
