"""Auto-extracted from seed_full_demo.py — mechanical decomposition (no logic changes)."""
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from ._shared import (
    NOW,
    TODAY,
    ORG_NAME,
    ORG_SLUG,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    pwd_context,
    days_ago,
    days_from_now,
    date_ago,
    date_from_now,
    exists,
    get_id,
)


def seed_users(conn, org_id, branch_id):
    """Create the demo user and teammates. Returns dict of user_ids."""
    TEAM = [
        {
            "email": "demo@perenniaai.com",
            "first_name": "Alex",
            "last_name": "Rivera",
            "role": "manager",
            "permission_role": "admin",
            "title": "Branch Manager / SVP",
            "phone": "+18431005001",
            "nmls": "MLO-100501",
            "has_password": True,
            "key": "manager",
        },
        {
            "email": "sarah.chen@summithomeloans.com",
            "first_name": "Sarah",
            "last_name": "Chen",
            "role": "loan_officer",
            "permission_role": "sales",
            "title": "Senior Loan Officer",
            "phone": "+18431005002",
            "nmls": "MLO-100502",
            "key": "lo_sarah",
        },
        {
            "email": "marcus.johnson@summithomeloans.com",
            "first_name": "Marcus",
            "last_name": "Johnson",
            "role": "loan_officer",
            "permission_role": "sales",
            "title": "Loan Officer",
            "phone": "+18431005003",
            "nmls": "MLO-100503",
            "key": "lo_marcus",
        },
        {
            "email": "emily.park@summithomeloans.com",
            "first_name": "Emily",
            "last_name": "Park",
            "role": "processor",
            "permission_role": "processing",
            "title": "Senior Loan Processor",
            "phone": "+18431005004",
            "nmls": "MLO-100504",
            "key": "processor",
        },
        {
            "email": "rachel.kim@summithomeloans.com",
            "first_name": "Rachel",
            "last_name": "Kim",
            "role": "underwriter",
            "permission_role": "sales",
            "title": "Senior Underwriter",
            "phone": "+18431005005",
            "nmls": "MLO-100505",
            "key": "uw_rachel",
        },
        {
            "email": "james.mitchell@summithomeloans.com",
            "first_name": "James",
            "last_name": "Mitchell",
            "role": "underwriter",
            "permission_role": "sales",
            "title": "Underwriter",
            "phone": "+18431005006",
            "nmls": "MLO-100506",
            "key": "uw_james",
        },
        {
            "email": "david.torres@summithomeloans.com",
            "first_name": "David",
            "last_name": "Torres",
            "role": "operations",
            "permission_role": "operations",
            "title": "Operations Manager",
            "phone": "+18431005007",
            "nmls": "MLO-100507",
            "key": "ops",
        },
    ]

    user_ids = {}

    # First pass: insert users (no manager_id yet)
    for member in TEAM:
        existing_id = get_id(conn, "users", "email", member["email"])
        if existing_id:
            user_ids[member["key"]] = existing_id
            print(f"⏭️  User exists: {member['email']}")
            continue

        if member.get("has_password"):
            hashed = pwd_context.hash(DEMO_PASSWORD)
        else:
            hashed = pwd_context.hash("NOLOGIN-" + member["email"])

        result = conn.execute(
            text("""
                INSERT INTO users
                    (email, hashed_password, first_name, last_name, role, permission_role,
                     branch_id, organization_id, is_active, phone, nmls_number, title,
                     timezone, email_verified, onboarding_completed, created_at)
                VALUES
                    (:email, :hashed_password, :first_name, :last_name, :role, :permission_role,
                     :branch_id, :org_id, :is_active, :phone, :nmls_number, :title,
                     :timezone, :email_verified, :onboarding_completed, :now)
                RETURNING id
            """),
            {
                "email": member["email"],
                "hashed_password": hashed,
                "first_name": member["first_name"],
                "last_name": member["last_name"],
                "role": member["role"],
                "permission_role": member["permission_role"],
                "branch_id": branch_id,
                "org_id": org_id,
                "is_active": True,
                "phone": member.get("phone"),
                "nmls_number": member.get("nmls"),
                "title": member.get("title"),
                "timezone": "America/New_York",
                "email_verified": True,
                "onboarding_completed": True,
                "now": NOW,
            },
        )
        user_id = result.fetchone()[0]
        user_ids[member["key"]] = user_id
        print(f"✅ Created user: {member['email']} (id={user_id})")

    conn.commit()

    # Second pass: set manager_id for non-manager users
    manager_id = user_ids.get("manager")
    if manager_id:
        for member in TEAM:
            if member["key"] == "manager":
                continue
            uid = user_ids.get(member["key"])
            if uid:
                conn.execute(
                    text("UPDATE users SET manager_id = :mgr WHERE id = :uid"),
                    {"mgr": manager_id, "uid": uid},
                )
        conn.commit()
        print(f"✅ Set manager_id={manager_id} for team members")

    return user_ids


def seed_impersonation_permissions(conn, user_ids):
    """Grant impersonation permissions between users."""
    manager_user_id = user_ids.get("manager")
    if not manager_user_id:
        print("⚠️  No manager user id — skipping impersonation permissions")
        return

    # Find or create employee record for manager
    emp_row = conn.execute(
        text("SELECT id FROM employees WHERE user_id = :uid LIMIT 1"),
        {"uid": manager_user_id},
    ).fetchone()

    if emp_row:
        employee_id = emp_row[0]
    else:
        emp_result = conn.execute(
            text("""
                INSERT INTO employees
                    (user_id, first_name, last_name, email, employment_status, hire_date, created_at)
                VALUES
                    (:user_id, 'Alex', 'Rivera', 'demo@perenniaai.com',
                     'active', CURRENT_DATE, CURRENT_TIMESTAMP)
                RETURNING id
            """),
            {"user_id": manager_user_id},
        )
        employee_id = emp_result.fetchone()[0]
        conn.commit()
        print(f"✅ Created employee record for manager (id={employee_id})")

    # All permissions to grant
    permissions = [
        "team.impersonate",
        "team.view_all",
        "team.manage_permissions",
        "leads.view_all",
        "clients.view_all",
        "loans.view_all",
        "reports.view_all",
        "settings.view",
    ]

    for perm_key in permissions:
        existing = conn.execute(
            text("""
                SELECT id, granted FROM employee_permissions
                WHERE employee_id = :emp_id AND permission_key = :perm_key
                LIMIT 1
            """),
            {"emp_id": employee_id, "perm_key": perm_key},
        ).fetchone()

        if existing:
            if not existing[1]:
                conn.execute(
                    text("""
                        UPDATE employee_permissions
                        SET granted = true, granted_at = CURRENT_TIMESTAMP, granted_by = :mgr
                        WHERE id = :perm_id
                    """),
                    {"mgr": manager_user_id, "perm_id": existing[0]},
                )
        else:
            conn.execute(
                text("""
                    INSERT INTO employee_permissions
                        (employee_id, permission_key, granted, granted_by, granted_at, inherited_from)
                    VALUES
                        (:emp_id, :perm_key, true, :granted_by, CURRENT_TIMESTAMP, 'none')
                """),
                {
                    "emp_id": employee_id,
                    "perm_key": perm_key,
                    "granted_by": manager_user_id,
                },
            )

    conn.commit()
    print(f"✅ Granted {len(permissions)} impersonation permissions to manager (employee_id={employee_id})")


