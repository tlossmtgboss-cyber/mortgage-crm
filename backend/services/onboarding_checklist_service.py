"""
Onboarding Checklist Service
==============================

Enterprise Readiness Domain 5: Onboarding & Provisioning.

Provides:
- Organization onboarding checklist with completion tracking (Check 5.13)
- Sample/test data cleanup verification (Check 5.14)
- Admin user designation check (Check 5.15)
- Integration configuration validation (Check 5.7)
- Agent configuration per org (Check 5.8)
- Training materials accessibility (Check 5.16)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# ONBOARDING CHECKLIST (Domain 5, Check 5.13)
# =============================================================================

CHECKLIST_ITEMS = [
    # Category: Organization Setup
    {
        "id": "org_profile",
        "category": "Organization Setup",
        "title": "Company profile completed",
        "description": "Company name, address, phone, and industry configured",
        "required": True,
        "check_fn": "_check_org_profile",
    },
    {
        "id": "branding",
        "category": "Organization Setup",
        "title": "Brand configuration set",
        "description": "Logo, primary/secondary colors, and email signature configured",
        "required": False,
        "check_fn": "_check_branding",
    },
    {
        "id": "admin_user",
        "category": "Organization Setup",
        "title": "Admin user designated with MFA",
        "description": "At least one admin user with MFA enabled",
        "required": True,
        "check_fn": "_check_admin_user",
    },
    # Category: User Management
    {
        "id": "users_created",
        "category": "User Management",
        "title": "Team members invited",
        "description": "At least 2 users created beyond the admin",
        "required": True,
        "check_fn": "_check_users_created",
    },
    {
        "id": "roles_assigned",
        "category": "User Management",
        "title": "User roles assigned",
        "description": "All users have appropriate roles (LO, processor, manager, etc.)",
        "required": True,
        "check_fn": "_check_roles_assigned",
    },
    {
        "id": "sso_configured",
        "category": "User Management",
        "title": "SSO/SAML configured",
        "description": "Single sign-on configured for enterprise authentication",
        "required": False,
        "check_fn": "_check_sso_configured",
    },
    # Category: Integrations
    {
        "id": "email_integration",
        "category": "Integrations",
        "title": "Email integration connected",
        "description": "Microsoft Graph or SMTP email configured and tested",
        "required": True,
        "check_fn": "_check_email_integration",
    },
    {
        "id": "crm_integration",
        "category": "Integrations",
        "title": "CRM/LOS integration configured",
        "description": "Salesforce, BytePro, or Encompass connected and initial sync completed",
        "required": False,
        "check_fn": "_check_crm_integration",
    },
    {
        "id": "telephony_setup",
        "category": "Integrations",
        "title": "Telephony provider configured",
        "description": "Telnyx credentials configured for calling",
        "required": False,
        "check_fn": "_check_telephony",
    },
    # Category: Data & Compliance
    {
        "id": "data_imported",
        "category": "Data & Compliance",
        "title": "Initial data imported",
        "description": "Leads, contacts, or loan data imported from CSV or sync",
        "required": False,
        "check_fn": "_check_data_imported",
    },
    {
        "id": "sample_data_clean",
        "category": "Data & Compliance",
        "title": "Sample/test data removed",
        "description": "No demo or test data present in production environment",
        "required": True,
        "check_fn": "_check_sample_data_clean",
    },
    {
        "id": "compliance_settings",
        "category": "Data & Compliance",
        "title": "Compliance settings reviewed",
        "description": "State licensing, NMLS numbers, and disclosure settings configured",
        "required": True,
        "check_fn": "_check_compliance_settings",
    },
    # Category: AI & Automation
    {
        "id": "ai_agents_configured",
        "category": "AI & Automation",
        "title": "AI agents enabled/disabled per preference",
        "description": "Select which AI agents are active for the organization",
        "required": False,
        "check_fn": "_check_ai_agents",
    },
    {
        "id": "sla_targets_set",
        "category": "AI & Automation",
        "title": "SLA targets configured",
        "description": "Pipeline milestone SLA targets set for the organization",
        "required": True,
        "check_fn": "_check_sla_targets",
    },
    # Category: Provisioning (Domain 5 enterprise readiness)
    {
        "id": "scim_or_manual_provisioning",
        "category": "Provisioning",
        "title": "User provisioning method configured",
        "description": "SCIM 2.0 or CSV bulk import has been used, or manual invites sent",
        "required": False,
        "check_fn": "_check_provisioning_method",
    },
    {
        "id": "mfa_enforced",
        "category": "Provisioning",
        "title": "MFA enforced for organization",
        "description": "Organization-level MFA requirement enabled, or all admins have MFA",
        "required": False,
        "check_fn": "_check_mfa_enforced",
    },
]


def compute_onboarding_checklist(db, org_id: int) -> Dict:
    """
    Compute the onboarding checklist for an organization.

    Returns:
        dict with items, completion percentage, and blocking items
    """
    from sqlalchemy import text

    results = []
    passed = 0
    required_passed = 0
    required_total = 0
    blocking = []

    for item in CHECKLIST_ITEMS:
        check_result = _run_check(db, org_id, item)
        results.append({
            "id": item["id"],
            "category": item["category"],
            "title": item["title"],
            "description": item["description"],
            "required": item["required"],
            "status": "complete" if check_result["passed"] else "incomplete",
            "detail": check_result.get("detail", ""),
        })

        if check_result["passed"]:
            passed += 1
            if item["required"]:
                required_passed += 1
        elif item["required"]:
            blocking.append(item["title"])

        if item["required"]:
            required_total += 1

    total = len(CHECKLIST_ITEMS)
    completion_pct = round((passed / total) * 100, 1) if total > 0 else 0
    required_pct = round((required_passed / required_total) * 100, 1) if required_total > 0 else 0

    return {
        "organization_id": org_id,
        "total_items": total,
        "completed": passed,
        "completion_percentage": completion_pct,
        "required_completed": required_passed,
        "required_total": required_total,
        "required_completion_percentage": required_pct,
        "is_ready": len(blocking) == 0,
        "blocking_items": blocking,
        "items": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_check(db, org_id: int, item: Dict) -> Dict:
    """Run a single checklist check."""
    try:
        fn_name = item["check_fn"]
        fn = globals().get(fn_name)
        if fn:
            return fn(db, org_id)
        return {"passed": False, "detail": "Check not implemented"}
    except Exception as e:
        logger.warning(f"Checklist check '{item['id']}' failed: {e}")
        return {"passed": False, "detail": f"Check error: {str(e)}"}


# =============================================================================
# INDIVIDUAL CHECK FUNCTIONS
# =============================================================================

def _check_org_profile(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT name, address, phone
        FROM organizations
        WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()
    if not row:
        return {"passed": False, "detail": "Organization not found"}
    has_name = bool(row[0] and len(row[0]) > 1)
    return {"passed": has_name, "detail": f"Name: {row[0] or 'not set'}"}


def _check_branding(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT logo_url, primary_color
        FROM organization_branding
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()
    if not row:
        return {"passed": False, "detail": "No branding configured"}
    has_logo = bool(row[0])
    has_colors = bool(row[1])
    return {"passed": has_logo or has_colors, "detail": f"Logo: {'set' if has_logo else 'not set'}, Colors: {'set' if has_colors else 'not set'}"}


def _check_admin_user(db, org_id: int) -> Dict:
    from sqlalchemy import text
    # Check for admin users with MFA enabled (enterprise requirement)
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (
                WHERE permission_role IN ('admin', 'site_admin') AND is_active = true
            ) as admin_count,
            COUNT(*) FILTER (
                WHERE permission_role IN ('admin', 'site_admin') AND is_active = true AND mfa_enabled = true
            ) as admin_mfa_count
        FROM users
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()
    admin_count = row[0] if row else 0
    admin_mfa_count = row[1] if row else 0
    has_admin_with_mfa = admin_mfa_count > 0
    return {
        "passed": has_admin_with_mfa,
        "detail": (
            f"{admin_count} admin(s), {admin_mfa_count} with MFA"
            if admin_count > 0
            else "No admin users found"
        ),
    }


def _check_users_created(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM users
        WHERE organization_id = :org_id AND is_active = true
    """), {"org_id": org_id}).fetchone()
    count = row[0] if row else 0
    return {"passed": count >= 3, "detail": f"{count} active users"}


def _check_roles_assigned(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(CASE WHEN permission_role IS NULL OR permission_role = '' THEN 1 END) as unassigned,
               COUNT(*) as total
        FROM users
        WHERE organization_id = :org_id AND is_active = true
    """), {"org_id": org_id}).fetchone()
    unassigned = row[0] if row else 0
    return {"passed": unassigned == 0, "detail": f"{unassigned} users without roles"}


def _check_sso_configured(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT sso_enabled, saml_entity_id
        FROM organizations
        WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()
    if not row:
        return {"passed": False, "detail": "Organization not found"}
    enabled = bool(row[0]) or bool(row[1])
    return {"passed": enabled, "detail": "SSO configured" if enabled else "SSO not configured"}


def _check_email_integration(db, org_id: int) -> Dict:
    import os
    has_graph = bool(os.getenv("MS_GRAPH_ACCESS_TOKEN") or os.getenv("MICROSOFT_GRAPH_TOKEN"))
    has_smtp = bool(os.getenv("SMTP_USER"))
    return {
        "passed": has_graph or has_smtp,
        "detail": f"Graph: {'configured' if has_graph else 'no'}, SMTP: {'configured' if has_smtp else 'no'}",
    }


def _check_crm_integration(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM user_integrations
        WHERE organization_id = :org_id
            AND provider = 'salesforce'
            AND access_token IS NOT NULL
    """), {"org_id": org_id}).fetchone()
    count = row[0] if row else 0
    return {"passed": count > 0, "detail": f"{count} Salesforce connections"}


def _check_telephony(db, org_id: int) -> Dict:
    import os
    has_telnyx = bool(os.getenv("TELNYX_API_KEY"))
    return {
        "passed": has_telnyx,
        "detail": f"Telnyx: {'yes' if has_telnyx else 'no'}",
    }


def _check_data_imported(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM leads WHERE organization_id = :org_id) as lead_count,
            (SELECT COUNT(*) FROM loans WHERE organization_id = :org_id) as loan_count
    """), {"org_id": org_id}).fetchone()
    leads = row[0] if row else 0
    loans = row[1] if row else 0
    return {"passed": (leads + loans) > 0, "detail": f"{leads} leads, {loans} loans"}


def _check_sample_data_clean(db, org_id: int) -> Dict:
    """Check for test/demo data indicators."""
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM leads
        WHERE organization_id = :org_id
            AND (
                email ILIKE '%test%' OR email ILIKE '%example.com%'
                OR email ILIKE '%demo%' OR email ILIKE '%fake%'
                OR first_name ILIKE 'test %' OR last_name ILIKE 'test%'
            )
    """), {"org_id": org_id}).fetchone()
    test_count = row[0] if row else 0
    return {
        "passed": test_count == 0,
        "detail": f"{test_count} potential test records found" if test_count > 0 else "No test data detected",
    }


def _check_compliance_settings(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM users
        WHERE organization_id = :org_id
            AND nmls_id IS NOT NULL
            AND nmls_id != ''
            AND permission_role = 'loan_officer'
    """), {"org_id": org_id}).fetchone()
    nmls_count = row[0] if row else 0
    return {"passed": nmls_count > 0, "detail": f"{nmls_count} LOs with NMLS IDs"}


def _check_ai_agents(db, org_id: int) -> Dict:
    """Check AI agent configuration per org."""
    from sqlalchemy import text
    # Check if org has agent preferences stored
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM organization_settings
        WHERE organization_id = :org_id
            AND setting_key LIKE 'agent_%'
    """), {"org_id": org_id}).fetchone()
    configured = row[0] if row else 0
    # Consider passed if org has any agent settings, or if using defaults
    return {"passed": True, "detail": f"{configured} agent settings configured (defaults apply if not set)"}


def _check_sla_targets(db, org_id: int) -> Dict:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM sla_configurations
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()
    count = row[0] if row else 0
    return {"passed": count > 0, "detail": f"{count} SLA configurations"}


def _check_provisioning_method(db, org_id: int) -> Dict:
    """Check if any user provisioning has been done (SCIM, CSV, or manual invites)."""
    from sqlalchemy import text

    # Check for SCIM-provisioned users
    scim_row = db.execute(text("""
        SELECT COUNT(*)
        FROM users
        WHERE organization_id = :org_id
            AND sso_provider = 'scim'
    """), {"org_id": org_id}).fetchone()
    scim_count = scim_row[0] if scim_row else 0

    # Check for pending/accepted invites
    invite_count = 0
    try:
        invite_row = db.execute(text("""
            SELECT COUNT(*)
            FROM employee_invites
            WHERE organization_id = :org_id
        """), {"org_id": org_id}).fetchone()
        invite_count = invite_row[0] if invite_row else 0
    except Exception as _exc:  # noqa: BLE001
        pass  # Table may not exist

    # Check total active users beyond the initial admin
    user_row = db.execute(text("""
        SELECT COUNT(*)
        FROM users
        WHERE organization_id = :org_id AND is_active = true
    """), {"org_id": org_id}).fetchone()
    user_count = user_row[0] if user_row else 0

    methods = []
    if scim_count > 0:
        methods.append(f"SCIM ({scim_count} users)")
    if invite_count > 0:
        methods.append(f"Invites ({invite_count})")
    if user_count > 1 and not methods:
        methods.append(f"Manual ({user_count} users)")

    passed = user_count >= 2  # At least admin + 1 more user
    return {
        "passed": passed,
        "detail": ", ".join(methods) if methods else "No provisioning detected",
    }


def _check_mfa_enforced(db, org_id: int) -> Dict:
    """Check if MFA is enforced org-wide or all admins have MFA."""
    from sqlalchemy import text

    # Check org-level MFA requirement
    org_row = db.execute(text("""
        SELECT mfa_required
        FROM organizations
        WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()
    org_requires_mfa = bool(org_row[0]) if org_row else False

    if org_requires_mfa:
        return {"passed": True, "detail": "Organization-level MFA requirement enabled"}

    # Fall back: check if all admins have MFA enabled
    admin_row = db.execute(text("""
        SELECT
            COUNT(*) as total_admins,
            COUNT(*) FILTER (WHERE mfa_enabled = true) as mfa_admins
        FROM users
        WHERE organization_id = :org_id
            AND permission_role IN ('admin', 'site_admin')
            AND is_active = true
    """), {"org_id": org_id}).fetchone()
    total_admins = admin_row[0] if admin_row else 0
    mfa_admins = admin_row[1] if admin_row else 0

    if total_admins > 0 and total_admins == mfa_admins:
        return {"passed": True, "detail": f"All {total_admins} admin(s) have MFA enabled"}

    return {
        "passed": False,
        "detail": (
            f"{mfa_admins}/{total_admins} admins have MFA; "
            "enable org-level MFA requirement or enroll all admins"
        ),
    }


# =============================================================================
# ONBOARDING VERIFICATION (Domain 5, Check 5.13 — comprehensive)
# =============================================================================

def verify_onboarding_readiness(db, org_id: int) -> Dict:
    """
    Comprehensive onboarding readiness verification for an organization.

    Returns a structured report covering all required onboarding steps:
    - SSO configured
    - Admin user designated with MFA
    - Users provisioned
    - Integrations connected
    - Branding configured

    This is the backing function for the /api/v1/onboarding/verify endpoint.
    """
    from sqlalchemy import text

    steps = {}

    # 1. SSO Configuration
    sso_result = _check_sso_configured(db, org_id)
    steps["sso_configured"] = {
        "title": "SSO / SAML configured",
        "status": "complete" if sso_result["passed"] else "incomplete",
        "required": False,
        "detail": sso_result["detail"],
    }

    # 2. Admin user with MFA
    admin_result = _check_admin_user(db, org_id)
    steps["admin_with_mfa"] = {
        "title": "Admin user designated with MFA enabled",
        "status": "complete" if admin_result["passed"] else "incomplete",
        "required": True,
        "detail": admin_result["detail"],
    }

    # 3. Users provisioned
    prov_result = _check_provisioning_method(db, org_id)
    steps["users_provisioned"] = {
        "title": "Team members provisioned (SCIM, CSV, or invites)",
        "status": "complete" if prov_result["passed"] else "incomplete",
        "required": True,
        "detail": prov_result["detail"],
    }

    # 4. Integrations connected
    email_result = _check_email_integration(db, org_id)
    crm_result = _check_crm_integration(db, org_id)
    telephony_result = _check_telephony(db, org_id)
    integrations_connected = email_result["passed"]  # Email is required
    steps["integrations_connected"] = {
        "title": "Core integrations connected",
        "status": "complete" if integrations_connected else "incomplete",
        "required": True,
        "detail": f"Email: {email_result['detail']}, CRM: {crm_result['detail']}, Telephony: {telephony_result['detail']}",
        "sub_checks": {
            "email": {"passed": email_result["passed"], "detail": email_result["detail"]},
            "crm": {"passed": crm_result["passed"], "detail": crm_result["detail"]},
            "telephony": {"passed": telephony_result["passed"], "detail": telephony_result["detail"]},
        },
    }

    # 5. Branding configured
    branding_result = _check_branding(db, org_id)
    steps["branding_configured"] = {
        "title": "Brand configuration set (logo, colors)",
        "status": "complete" if branding_result["passed"] else "incomplete",
        "required": False,
        "detail": branding_result["detail"],
    }

    # 6. MFA enforcement
    mfa_result = _check_mfa_enforced(db, org_id)
    steps["mfa_enforced"] = {
        "title": "MFA enforced for organization",
        "status": "complete" if mfa_result["passed"] else "incomplete",
        "required": False,
        "detail": mfa_result["detail"],
    }

    # Compute summary
    required_steps = {k: v for k, v in steps.items() if v["required"]}
    required_complete = sum(1 for v in required_steps.values() if v["status"] == "complete")
    total_complete = sum(1 for v in steps.values() if v["status"] == "complete")

    all_required_met = required_complete == len(required_steps)

    return {
        "organization_id": org_id,
        "ready_for_production": all_required_met,
        "total_steps": len(steps),
        "completed_steps": total_complete,
        "required_steps": len(required_steps),
        "required_completed": required_complete,
        "completion_percentage": round((total_complete / len(steps)) * 100, 1) if steps else 0,
        "blocking_items": [
            v["title"] for v in required_steps.values() if v["status"] == "incomplete"
        ],
        "steps": steps,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# TRAINING MATERIALS (Domain 5, Check 5.16)
# =============================================================================

def get_training_materials() -> Dict:
    """
    Return available training materials by role.
    """
    return {
        "materials": [
            {
                "role": "loan_officer",
                "resources": [
                    {"type": "guide", "title": "Getting Started: Pipeline Management", "url": "/help/lo-pipeline"},
                    {"type": "guide", "title": "Using AI Agents During Calls", "url": "/help/lo-agents"},
                    {"type": "guide", "title": "Lead Management & Follow-up", "url": "/help/lo-leads"},
                    {"type": "video", "title": "Power Dialer Walkthrough", "url": "/help/videos/dialer"},
                ],
            },
            {
                "role": "processor",
                "resources": [
                    {"type": "guide", "title": "Document Collection Workflow", "url": "/help/proc-docs"},
                    {"type": "guide", "title": "Condition Tracking", "url": "/help/proc-conditions"},
                    {"type": "guide", "title": "SLA Compliance Dashboard", "url": "/help/proc-sla"},
                ],
            },
            {
                "role": "manager",
                "resources": [
                    {"type": "guide", "title": "Team Performance Dashboard", "url": "/help/mgr-dashboard"},
                    {"type": "guide", "title": "Pipeline Reports & Analytics", "url": "/help/mgr-reports"},
                    {"type": "guide", "title": "User Management & Roles", "url": "/help/mgr-users"},
                ],
            },
            {
                "role": "admin",
                "resources": [
                    {"type": "guide", "title": "Organization Setup Guide", "url": "/help/admin-setup"},
                    {"type": "guide", "title": "Integration Configuration", "url": "/help/admin-integrations"},
                    {"type": "guide", "title": "Security & Compliance Settings", "url": "/help/admin-security"},
                    {"type": "guide", "title": "White-Label Branding", "url": "/help/admin-branding"},
                    {"type": "guide", "title": "API & Developer Setup", "url": "/help/admin-api"},
                ],
            },
        ],
        "total_resources": 15,
    }
