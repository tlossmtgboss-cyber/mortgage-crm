"""
Role-Based Report Access Control Middleware
Enterprise Readiness - Domain 9: Analytics (Check 9.6)

Provides role-based access scoping for analytics and reporting endpoints.
Ensures users can only see data appropriate to their role:
- Admin/Leadership: Full organization data
- Branch Manager/Regional Manager: Their branch data
- Loan Officer/Sales/Processing/Operations: Their own data only

Usage in route handlers:
    from middleware.report_access import get_report_scope, apply_scope_to_query

    scope = get_report_scope(current_user)
    query = apply_scope_to_query(query, scope, model=Loan)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Roles that can see all organization data
ORG_SCOPE_ROLES = (
    "admin",
    "site_admin",
    "platform_admin",
    "leadership",
)

# Roles that can see their branch data
BRANCH_SCOPE_ROLES = (
    "branch_manager",
    "regional_manager",
    "management",
)

# All other roles see only their own data


def get_report_scope(current_user) -> Dict[str, Any]:
    """
    Determine the data access scope based on the user's role.

    Args:
        current_user: Authenticated user object with permission_role,
                      organization_id, branch_id, and id attributes.

    Returns:
        Dict with scope type and filter parameters:
        - scope: 'org' | 'branch' | 'user'
        - org_id: Organization ID (always present)
        - branch_id: Branch ID (for branch scope)
        - user_id: User ID (for user scope)
    """
    role = getattr(current_user, "permission_role", "") or ""
    org_id = getattr(current_user, "organization_id", None)
    branch_id = getattr(current_user, "branch_id", None)
    user_id = getattr(current_user, "id", None)

    if role in ORG_SCOPE_ROLES:
        return {
            "scope": "org",
            "org_id": org_id,
            "role": role,
        }
    elif role in BRANCH_SCOPE_ROLES:
        return {
            "scope": "branch",
            "org_id": org_id,
            "branch_id": branch_id,
            "role": role,
        }
    else:
        # Default: user can only see their own data
        return {
            "scope": "user",
            "org_id": org_id,
            "user_id": user_id,
            "role": role,
        }


def apply_scope_to_lead_query(query, scope: Dict[str, Any], Lead):
    """
    Apply report scope filtering to a Lead query.

    Args:
        query: SQLAlchemy query object for Lead model.
        scope: Scope dict from get_report_scope().
        Lead: Lead model class.

    Returns:
        Filtered query.
    """
    # Always filter by organization
    org_id = scope.get("org_id")
    if org_id is not None and hasattr(Lead, "organization_id"):
        query = query.filter(Lead.organization_id == org_id)

    if scope["scope"] == "user":
        user_id = scope.get("user_id")
        if user_id is not None and hasattr(Lead, "owner_id"):
            query = query.filter(Lead.owner_id == user_id)
    elif scope["scope"] == "branch":
        branch_id = scope.get("branch_id")
        if branch_id is not None and hasattr(Lead, "branch_id"):
            query = query.filter(Lead.branch_id == branch_id)
    # org scope: org_id filter already applied above

    return query


def apply_scope_to_loan_query(query, scope: Dict[str, Any], Loan):
    """
    Apply report scope filtering to a Loan query.

    Args:
        query: SQLAlchemy query object for Loan model.
        scope: Scope dict from get_report_scope().
        Loan: Loan model class.

    Returns:
        Filtered query.
    """
    # Always filter by organization
    org_id = scope.get("org_id")
    if org_id is not None and hasattr(Loan, "organization_id"):
        query = query.filter(Loan.organization_id == org_id)

    if scope["scope"] == "user":
        user_id = scope.get("user_id")
        if user_id is not None and hasattr(Loan, "loan_officer_id"):
            query = query.filter(Loan.loan_officer_id == user_id)
    elif scope["scope"] == "branch":
        branch_id = scope.get("branch_id")
        if branch_id is not None and hasattr(Loan, "branch_id"):
            query = query.filter(Loan.branch_id == branch_id)
    # org scope: org_id filter already applied above

    return query


def apply_scope_to_milestone_query(query, scope: Dict[str, Any], MilestoneModel):
    """
    Apply report scope filtering to a milestone/SLA query.

    Args:
        query: SQLAlchemy query object for milestone model.
        scope: Scope dict from get_report_scope().
        MilestoneModel: Model class with organization_id and
                        optionally assigned_to_id.

    Returns:
        Filtered query.
    """
    org_id = scope.get("org_id")
    if org_id is not None and hasattr(MilestoneModel, "organization_id"):
        query = query.filter(MilestoneModel.organization_id == org_id)

    if scope["scope"] == "user":
        user_id = scope.get("user_id")
        if user_id is not None and hasattr(MilestoneModel, "assigned_to_id"):
            query = query.filter(MilestoneModel.assigned_to_id == user_id)

    return query


def get_scope_description(scope: Dict[str, Any]) -> str:
    """
    Get a human-readable description of the current scope.

    Args:
        scope: Scope dict from get_report_scope().

    Returns:
        Description string like "Organization-wide (admin)" or
        "Personal data only (loan_officer)".
    """
    scope_type = scope.get("scope", "user")
    role = scope.get("role", "unknown")

    if scope_type == "org":
        return f"Organization-wide ({role})"
    elif scope_type == "branch":
        branch_id = scope.get("branch_id", "unknown")
        return f"Branch {branch_id} ({role})"
    else:
        return f"Personal data only ({role})"
