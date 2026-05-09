"""
Perennia AI - Team & Organization Tools
Tools for querying team members, org info, workflow roles, and user profiles.

IMPORTANT: User.first_name and User.last_name are EncryptedString columns.
All user queries MUST go through the ORM (db.query / db.get) to auto-decrypt.
Raw SQL text() queries will return garbled ciphertext for those fields.
"""

import logging
from typing import Optional

from sqlalchemy import and_, select, text

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool,
    ToolResult,
    get_db,
    get_tenant_context,
)


def _user_to_dict(user) -> dict:
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    name = f"{first} {last}".strip() or user.email or f"User #{user.id}"
    return {
        "user_id": user.id,
        "name": name,
        "email": user.email,
        "role": getattr(user, "role", None),
        "permission_role": getattr(user, "permission_role", None),
        "title": getattr(user, "title", None),
        "phone": getattr(user, "phone", None),
        "nmls": getattr(user, "nmls_number", None) or getattr(user, "nmls_id", None),
        "team_name": getattr(user, "team_name", None),
        "is_active": getattr(user, "is_active", True),
        "branch_id": getattr(user, "branch_id", None),
        "manager_id": getattr(user, "manager_id", None),
    }


# ── Team Member Tools ─────────────────────────────────────────────


@mortgage_tool(
    name="get_team_members",
    description="List all active team members in the organization. Returns names, roles, emails, titles, phone numbers, and NMLS IDs for every team member.",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Who's on my team?",
        "List all team members",
        "Show me the team",
        "Who works here?",
        "How many people are on the team?",
        "Tell me about our team",
    ],
)
def get_team_members(
    active_only: bool = True,
    role_filter: Optional[str] = None,
) -> ToolResult:
    """List all team members in the organization."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No organization context available")

    try:
        from database.models.core import User

        with get_db() as db:
            query = db.query(User).filter(User.organization_id == org_id)
            if active_only:
                query = query.filter(User.is_active.is_(True))
            if role_filter:
                query = query.filter(User.role.ilike(f"%{role_filter}%"))
            query = query.order_by(User.id.asc())

            users = query.all()

            if not users:
                return ToolResult.no_data("No team members found in this organization")

            members = [_user_to_dict(u) for u in users]

            role_summary = {}
            for m in members:
                r = m.get("role") or m.get("permission_role") or "unknown"
                role_summary[r] = role_summary.get(r, 0) + 1

            return ToolResult.success(
                data={
                    "team_members": members,
                    "total_count": len(members),
                    "role_breakdown": role_summary,
                },
                message=f"Found {len(members)} team member(s) in the organization",
            )
    except Exception as e:
        logger.error("get_team_members failed: %s", e)
        return ToolResult.error(f"Failed to load team members: {e}")


@mortgage_tool(
    name="get_user_profile",
    description="Get detailed profile information for a specific team member by name, email, or user ID. Includes role, title, phone, email, NMLS, team name, and manager.",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Tell me about Tim Loss",
        "What's John's email?",
        "Who is the loan officer?",
        "Get profile for user 5",
        "What's the NMLS number for our LO?",
    ],
    parameters={
        "search": "Name, email, or user ID to search for",
    },
)
def get_user_profile(
    search: str = "",
    user_id: Optional[int] = None,
) -> ToolResult:
    """Get detailed profile for a specific user."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No organization context available")

    if not search and not user_id:
        return ToolResult.error("Provide a name, email, or user_id to search for")

    try:
        from database.models.core import User

        with get_db() as db:
            if user_id:
                user = db.get(User, user_id)
                if user and user.organization_id == org_id:
                    profile = _user_to_dict(user)
                    # Resolve manager name
                    if user.manager_id:
                        mgr = db.get(User, user.manager_id)
                        if mgr:
                            mf = getattr(mgr, "first_name", "") or ""
                            ml = getattr(mgr, "last_name", "") or ""
                            profile["manager_name"] = f"{mf} {ml}".strip() or mgr.email
                    return ToolResult.success(data=profile)
                return ToolResult.no_data(f"No user found with ID {user_id}")

            # Search by name or email
            users = (
                db.query(User)
                .filter(
                    User.organization_id == org_id,
                    User.is_active.is_(True),
                )
                .all()
            )

            search_lower = search.lower().strip()
            matches = []
            for u in users:
                first = (getattr(u, "first_name", "") or "").lower()
                last = (getattr(u, "last_name", "") or "").lower()
                full = f"{first} {last}".strip()
                email = (u.email or "").lower()
                title = (getattr(u, "title", "") or "").lower()
                role = (getattr(u, "role", "") or "").lower()

                if (
                    search_lower in full
                    or search_lower in email
                    or search_lower in title
                    or search_lower in role
                    or full and full in search_lower
                ):
                    matches.append(u)

            if not matches:
                return ToolResult.no_data(f"No team member found matching '{search}'")

            profiles = []
            for u in matches:
                profile = _user_to_dict(u)
                if u.manager_id:
                    mgr = db.get(User, u.manager_id)
                    if mgr:
                        mf = getattr(mgr, "first_name", "") or ""
                        ml = getattr(mgr, "last_name", "") or ""
                        profile["manager_name"] = f"{mf} {ml}".strip() or mgr.email
                profiles.append(profile)

            if len(profiles) == 1:
                return ToolResult.success(data=profiles[0], message=f"Found team member: {profiles[0]['name']}")
            return ToolResult.success(
                data={"matches": profiles, "count": len(profiles)},
                message=f"Found {len(profiles)} team members matching '{search}'",
            )
    except Exception as e:
        logger.error("get_user_profile failed: %s", e)
        return ToolResult.error(f"Failed to load user profile: {e}")


# ── Workflow Role Tools ────────────────────────────────────────────


@mortgage_tool(
    name="get_workflow_role_assignments",
    description="Get workflow role assignments — which team members are assigned to roles like Loan Officer, Production Assistant, Processor, Underwriter, Closer, etc. Shows the team structure and who handles what.",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Who is assigned to what role?",
        "What are the workflow role assignments?",
        "Who is the processor?",
        "Who handles underwriting?",
        "Show team role assignments",
        "What roles are set up?",
    ],
)
def get_workflow_role_assignments() -> ToolResult:
    """Get all workflow role assignments for the organization."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No organization context available")

    try:
        from database.models.core import User

        with get_db() as db:
            # Get role assignments (role names are plain text, safe for raw SQL)
            rows = db.execute(text("""
                SELECT dra.user_id, r.name as role_name, r.description as role_description
                FROM default_role_assignments dra
                JOIN roles r ON r.id = dra.role_id
                WHERE dra.organization_id = :org_id
                  AND r.is_active = true
                ORDER BY r.name, dra.user_id
            """), {"org_id": org_id}).fetchall()

            if not rows:
                return ToolResult.no_data("No workflow role assignments found. Roles can be configured in Settings > Team Roles.")

            # Resolve user names via ORM (EncryptedString safe)
            user_ids = {row[0] for row in rows if row[0] is not None}
            user_map = {}
            if user_ids:
                users = db.query(User).filter(User.id.in_(user_ids)).all()
                for u in users:
                    first = getattr(u, "first_name", "") or ""
                    last = getattr(u, "last_name", "") or ""
                    user_map[u.id] = {
                        "name": f"{first} {last}".strip() or u.email,
                        "email": u.email,
                    }

            assignments = []
            for row in rows:
                uid, role_name, role_desc = row[0], row[1], row[2]
                user_info = user_map.get(uid, {})
                assignments.append({
                    "role": role_name,
                    "role_description": role_desc,
                    "user_id": uid,
                    "user_name": user_info.get("name", "Unassigned"),
                    "user_email": user_info.get("email"),
                })

            # Group by role
            by_role = {}
            for a in assignments:
                role = a["role"]
                if role not in by_role:
                    by_role[role] = {"role": role, "description": a["role_description"], "members": []}
                by_role[role]["members"].append({
                    "user_id": a["user_id"],
                    "name": a["user_name"],
                    "email": a["user_email"],
                })

            return ToolResult.success(
                data={
                    "roles": list(by_role.values()),
                    "total_assignments": len(assignments),
                    "total_roles": len(by_role),
                },
                message=f"Found {len(assignments)} role assignment(s) across {len(by_role)} role(s)",
            )
    except Exception as e:
        logger.error("get_workflow_role_assignments failed: %s", e)
        return ToolResult.error(f"Failed to load role assignments: {e}")


# ── Organization Tools ─────────────────────────────────────────────


@mortgage_tool(
    name="get_organization_info",
    description="Get organization details including name, slug, timezone, subscription tier, and settings. Tells you about the company/organization.",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "What organization am I in?",
        "Tell me about our company",
        "What's our org name?",
        "What subscription tier are we on?",
        "What timezone is the org set to?",
    ],
)
def get_organization_info() -> ToolResult:
    """Get organization details."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No organization context available")

    try:
        from database.models.core import Organization

        with get_db() as db:
            org = db.get(Organization, org_id)
            if not org:
                return ToolResult.no_data("Organization not found")

            return ToolResult.success(
                data={
                    "id": org.id,
                    "name": org.name,
                    "slug": getattr(org, "slug", None),
                    "domain": getattr(org, "domain", None),
                    "timezone": getattr(org, "timezone", None),
                    "subscription_tier": getattr(org, "subscription_tier", None),
                    "is_active": getattr(org, "is_active", True),
                },
                message=f"Organization: {org.name}",
            )
    except Exception as e:
        logger.error("get_organization_info failed: %s", e)
        return ToolResult.error(f"Failed to load organization info: {e}")


# ── CRM Summary Tools ─────────────────────────────────────────────


@mortgage_tool(
    name="get_crm_summary",
    description="Get a high-level summary of all CRM data: total leads, loans, pipeline value, team size, recent activity. Use this to answer general questions about the state of the business.",
    agent_roles=["all"],
    risk_level="low",
    examples=[
        "Give me an overview of the CRM",
        "What data do we have?",
        "How many leads and loans do we have?",
        "Summary of the business",
        "What's the current state of things?",
    ],
)
def get_crm_summary() -> ToolResult:
    """Get a high-level summary of all CRM data."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No organization context available")

    try:
        from database.models.core import User

        with get_db() as db:
            # Team count
            team_count = (
                db.query(User)
                .filter(User.organization_id == org_id, User.is_active.is_(True))
                .count()
            )

            # Lead counts
            lead_data = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE stage IN ('New', 'NEW', 'new')) as new_leads,
                    COUNT(*) FILTER (WHERE stage IN ('Contacted', 'CONTACTED', 'contacted')) as contacted,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as last_7_days
                FROM leads
                WHERE organization_id = :org_id
            """), {"org_id": org_id}).fetchone()

            # Loan counts and pipeline
            loan_data = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE')) as active_pipeline,
                    COUNT(*) FILTER (WHERE stage = 'FUNDED') as funded,
                    COALESCE(SUM(CASE WHEN stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE') THEN amount ELSE 0 END), 0) as pipeline_volume,
                    COALESCE(SUM(CASE WHEN stage = 'FUNDED' THEN amount ELSE 0 END), 0) as funded_volume
                FROM loans
                WHERE organization_id = :org_id
            """), {"org_id": org_id}).fetchone()

            # Task counts
            task_data = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'overdue' OR (due_date < NOW() AND status != 'completed')) as overdue
                FROM tasks
                WHERE organization_id = :org_id
            """), {"org_id": org_id}).fetchone()

            # Referral partner count
            partner_count = db.execute(text("""
                SELECT COUNT(*) FROM referral_partners WHERE organization_id = :org_id
            """), {"org_id": org_id}).scalar() or 0

            summary = {
                "team": {
                    "active_members": team_count,
                },
                "leads": {
                    "total": lead_data[0] if lead_data else 0,
                    "new": lead_data[1] if lead_data else 0,
                    "contacted": lead_data[2] if lead_data else 0,
                    "added_last_7_days": lead_data[3] if lead_data else 0,
                },
                "loans": {
                    "total": loan_data[0] if loan_data else 0,
                    "active_pipeline": loan_data[1] if loan_data else 0,
                    "funded": loan_data[2] if loan_data else 0,
                    "pipeline_volume": float(loan_data[3]) if loan_data else 0,
                    "funded_volume": float(loan_data[4]) if loan_data else 0,
                },
                "tasks": {
                    "total": task_data[0] if task_data else 0,
                    "pending": task_data[1] if task_data else 0,
                    "overdue": task_data[2] if task_data else 0,
                },
                "referral_partners": partner_count,
            }

            return ToolResult.success(
                data=summary,
                message=(
                    f"CRM Summary: {team_count} team members, "
                    f"{summary['leads']['total']} leads, "
                    f"{summary['loans']['active_pipeline']} active loans in pipeline"
                ),
            )
    except Exception as e:
        logger.error("get_crm_summary failed: %s", e)
        return ToolResult.error(f"Failed to load CRM summary: {e}")
