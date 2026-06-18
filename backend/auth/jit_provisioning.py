"""
Just-In-Time (JIT) User Provisioning
Enterprise Readiness Check 5.11

Auto-creates user accounts when users authenticate via SSO for the first time.
Maps IdP groups/claims to CRM roles.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from database.models.core import User

logger = logging.getLogger(__name__)

# Group-to-role mapping (configurable per org in the future)
# These map common IdP group names to CRM permission roles.
DEFAULT_GROUP_ROLE_MAP = {
    # Admin groups
    "admins": "admin",
    "administrators": "admin",
    "site_admins": "site_admin",
    "site-admins": "site_admin",
    # Leadership
    "leadership": "leadership",
    "executives": "leadership",
    "management": "management",
    "managers": "management",
    # Processing / Operations
    "processing": "processing",
    "processors": "processing",
    "operations": "operations",
    "ops": "operations",
    # Sales (default)
    "loan_officers": "sales",
    "loan-officers": "sales",
    "sales": "sales",
    "originators": "sales",
}

# Map permission_role -> legacy role field for backward compatibility
PERMISSION_ROLE_TO_ROLE = {
    "admin": "admin",
    "site_admin": "site_admin",
    "leadership": "leadership",
    "management": "management",
    "sales": "loan_officer",
    "processing": "processor",
    "operations": "operations",
}


def provision_user_from_sso(
    db: Session,
    email: str,
    first_name: Optional[str],
    last_name: Optional[str],
    organization_id: int,
    sso_provider: str,  # 'saml' or 'oidc'
    sso_subject_id: str,
    groups: Optional[List[str]] = None,
    default_role: str = "loan_officer",
    default_permission_role: str = "sales",
) -> "User":
    """
    Create a new user from SSO attributes (JIT provisioning).

    Args:
        db: Database session.
        email: User's email address (from NameID or claims).
        first_name: User's first name.
        last_name: User's last name.
        organization_id: Organization to assign the user to.
        sso_provider: 'saml' or 'oidc'.
        sso_subject_id: Unique identifier from IdP (NameID or sub claim).
        groups: List of group names from IdP.
        default_role: Default legacy role if no group mapping matches.
        default_permission_role: Default permission role if no group mapping matches.

    Returns:
        The newly created User object.
    """
    # Lazy import to avoid circular dependency
    from database.models.core import User

    # Determine role from groups
    permission_role = default_permission_role
    if groups:
        permission_role = _map_groups_to_role(groups, default_permission_role)

    legacy_role = PERMISSION_ROLE_TO_ROLE.get(permission_role, default_role)

    # Generate a random password hash (user cannot login with password if SSO-only)
    # This ensures hashed_password is never NULL (required field)
    random_password_hash = f"$sso_provisioned${secrets.token_hex(32)}"

    user = User(
        email=email.lower().strip(),
        first_name=first_name or "",
        last_name=last_name or "",
        hashed_password=random_password_hash,
        role=legacy_role,
        permission_role=permission_role,
        organization_id=organization_id,
        is_active=True,
        email_verified=True,  # SSO already verified the email
        email_verified_at=datetime.now(timezone.utc),
        onboarding_completed=False,
        sso_provider=sso_provider,
        sso_subject_id=sso_subject_id,
        user_metadata={
            "provisioned_via": f"sso_{sso_provider}",
            "provisioned_at": datetime.now(timezone.utc).isoformat(),
            "idp_groups": groups or [],
        },
    )

    db.add(user)
    db.flush()  # Get the ID without committing

    logger.info(
        f"JIT provisioned user: email={email}, org_id={organization_id}, "
        f"role={legacy_role}, permission_role={permission_role}, "
        f"provider={sso_provider}"
    )

    # Auto-provision SchedulerConfig so the new user can use the calendar
    # immediately without hitting the seed-defaults endpoint manually.
    try:
        from services.scheduler_provisioning import auto_provision_scheduler_config
        asyncio.run(auto_provision_scheduler_config(
            user_id=user.id,
            organization_id=organization_id,
            db=db,
            user_email=email,
        ))
    except RuntimeError:
        # asyncio.run() raises RuntimeError when called inside an already-running
        # event loop (e.g. during tests with pytest-asyncio).  Fall back to
        # creating a new task on the running loop.
        try:
            from services.scheduler_provisioning import auto_provision_scheduler_config
            loop = asyncio.get_event_loop()
            loop.run_until_complete(auto_provision_scheduler_config(
                user_id=user.id,
                organization_id=organization_id,
                db=db,
                user_email=email,
            ))
        except Exception as _exc:
            logger.warning("JIT provisioning: scheduler auto-provision failed — %s", _exc)
    except Exception as _exc:
        logger.warning("JIT provisioning: scheduler auto-provision failed — %s", _exc)

    return user


def update_user_from_sso(
    db: Session,
    user: "User",
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    groups: Optional[List[str]] = None,
    sso_provider: Optional[str] = None,
    sso_subject_id: Optional[str] = None,
) -> "User":
    """
    Update an existing user's attributes from SSO on subsequent logins.

    Only updates fields that are provided and non-empty.
    Does NOT change role/permission_role if they were manually set by an admin.

    Args:
        db: Database session.
        user: Existing User object.
        first_name: Updated first name.
        last_name: Updated last name.
        groups: Updated group list.
        sso_provider: SSO provider type.
        sso_subject_id: SSO subject identifier.

    Returns:
        Updated User object.
    """
    if first_name and not user.first_name:
        user.first_name = first_name

    if last_name and not user.last_name:
        user.last_name = last_name

    if sso_provider and not user.sso_provider:
        user.sso_provider = sso_provider

    if sso_subject_id and not user.sso_subject_id:
        user.sso_subject_id = sso_subject_id

    # Update last activity
    user.last_activity_at = datetime.now(timezone.utc)

    db.flush()
    return user


def _map_groups_to_role(groups: List[str], default: str = "sales") -> str:
    """
    Map IdP group names to a CRM permission role.

    Uses the highest-privilege match (admin > site_admin > ... > sales).

    Args:
        groups: List of group names from IdP.
        default: Default role if no mapping matches.

    Returns:
        Permission role string.
    """
    # Priority order (highest first)
    role_priority = ["admin", "site_admin", "leadership", "management", "operations", "processing", "sales"]

    best_role = None
    best_priority = len(role_priority)  # lowest priority = highest index

    for group in groups:
        group_lower = group.lower().strip()
        mapped = DEFAULT_GROUP_ROLE_MAP.get(group_lower)
        if mapped and mapped in role_priority:
            idx = role_priority.index(mapped)
            if idx < best_priority:
                best_priority = idx
                best_role = mapped

    return best_role or default
