#!/usr/bin/env python3
"""
Full Demo Seed Script — Perennia AI
====================================
Creates a comprehensive demo account for product presentations.
Populates Summit Home Loans org with realistic data across all CRM modules:
  - Organization, branch, users (demo LO + teammates)
  - Leads, loans, MUM clients, referral partners
  - Tasks, documents, calendar events
  - SMS conversations, call intelligence records
  - Activity history, AI metrics, rate monitor alerts
  - Workflows, compliance records, borrower portal data
  - Content/campaigns, team chat, notifications

Usage:
    DATABASE_URL=<url> python3 seed_full_demo.py

The script is idempotent: re-running skips rows that already exist.
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Config constants
# ---------------------------------------------------------------------------

ORG_NAME = "Summit Home Loans"
ORG_SLUG = "summit-home-loans"
DEMO_EMAIL = "demo@perenniaai.com"
DEMO_PASSWORD = "Password1!"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def days_ago(n: int) -> datetime:
    """Return a UTC datetime n days before NOW."""
    return NOW - timedelta(days=n)


def days_from_now(n: int) -> datetime:
    """Return a UTC datetime n days after NOW."""
    return NOW + timedelta(days=n)


def date_ago(n: int):
    """Return a date n days before TODAY."""
    return TODAY - timedelta(days=n)


def date_from_now(n: int):
    """Return a date n days after TODAY."""
    return TODAY + timedelta(days=n)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_engine():
    """Build a SQLAlchemy engine from DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)
    # Railway / Heroku use postgres:// — SQLAlchemy 1.4+ requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, echo=False)


def exists(conn, table: str, column: str, value) -> bool:
    """Return True if a row matching column=value exists in table."""
    result = conn.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    return result.fetchone() is not None


def get_id(conn, table: str, column: str, value):
    """Return the id of the first row matching column=value, or None."""
    result = conn.execute(
        text(f"SELECT id FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    row = result.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Seed functions — stubs (to be implemented in subsequent tasks)
# ---------------------------------------------------------------------------


def seed_organization(conn):
    """Create the demo organization. Returns org_id."""
    existing_id = get_id(conn, "organizations", "slug", ORG_SLUG)
    if existing_id:
        print("⏭️  Organization exists")
        return existing_id

    result = conn.execute(
        text("""
            INSERT INTO organizations
                (name, slug, subscription_tier, timezone, is_active,
                 booking_slug, booking_primary_color, created_at, updated_at)
            VALUES
                (:name, :slug, :tier, :tz, :active,
                 :booking_slug, :booking_color, :now, :now)
            RETURNING id
        """),
        {
            "name": ORG_NAME,
            "slug": ORG_SLUG,
            "tier": "enterprise",
            "tz": "America/New_York",
            "active": True,
            "booking_slug": ORG_SLUG,
            "booking_color": "#1a73e8",
            "now": NOW,
        },
    )
    org_id = result.fetchone()[0]
    conn.commit()
    print(f"✅ Created organization (id={org_id})")
    return org_id


def seed_branch(conn, org_id):
    """Create the demo branch. Returns branch_id."""
    existing_id = get_id(conn, "branches", "nmls_id", "789012")
    if existing_id:
        return existing_id

    result = conn.execute(
        text("""
            INSERT INTO branches
                (name, company, nmls_id, organization_id, created_at)
            VALUES
                (:name, :company, :nmls_id, :org_id, :now)
            RETURNING id
        """),
        {
            "name": "Charleston HQ",
            "company": ORG_NAME,
            "nmls_id": "789012",
            "org_id": org_id,
            "now": NOW,
        },
    )
    branch_id = result.fetchone()[0]
    conn.commit()
    print(f"✅ Created branch (id={branch_id})")
    return branch_id


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


def seed_leads(conn, org_id, user_ids):
    """Create demo leads at various pipeline stages. Returns list of lead_ids."""
    pass


def seed_loans(conn, org_id, user_ids, lead_ids):
    """Create demo active loans. Returns list of loan_ids."""
    pass


def seed_mum_clients(conn, org_id, user_ids):
    """Create MUM (Mortgage Under Management) clients. Returns list of mum_ids."""
    pass


def seed_referral_partners(conn, org_id, user_ids, lead_ids):
    """Create referral partners linked to leads. Returns list of partner_ids."""
    pass


def seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo tasks across users, leads, and loans."""
    pass


def seed_documents(conn, org_id, user_ids, loan_ids):
    """Create demo document records for loans."""
    pass


def seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo calendar events and appointments."""
    pass


def seed_sms_conversations(conn, org_id, user_ids, lead_ids):
    """Create demo SMS conversation threads."""
    pass


def seed_call_intelligence(conn, org_id, user_ids, lead_ids):
    """Create demo call records with AI analysis."""
    pass


def seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create activity log entries for leads and loans."""
    pass


def seed_ai_metrics(conn, org_id):
    """Create demo AI usage metrics and performance data."""
    pass


def seed_rate_monitor(conn, org_id, mum_ids, loan_ids):
    """Create rate monitor alerts and rate watch records."""
    pass


def seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create workflow automation records and compliance checks."""
    pass


def seed_borrower_portal(conn, org_id, lead_ids, loan_ids):
    """Create borrower portal sessions and document requests."""
    pass


def seed_content_and_campaigns(conn, org_id, user_ids, lead_ids):
    """Create content pieces and marketing campaign records."""
    pass


def seed_team_chat(conn, org_id, user_ids):
    """Create team chat channel messages."""
    pass


def seed_notifications(conn, org_id, user_ids):
    """Create demo in-app notification records."""
    pass


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main():
    print("🔌 Connecting...")
    engine = get_engine()

    with engine.connect() as conn:
        print("✅ Connected")

        org_id = seed_organization(conn)
        branch_id = seed_branch(conn, org_id)
        user_ids = seed_users(conn, org_id, branch_id)
        seed_impersonation_permissions(conn, user_ids)
        lead_ids = seed_leads(conn, org_id, user_ids)
        loan_ids = seed_loans(conn, org_id, user_ids, lead_ids)
        mum_ids = seed_mum_clients(conn, org_id, user_ids)
        partner_ids = seed_referral_partners(conn, org_id, user_ids, lead_ids)
        seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_documents(conn, org_id, user_ids, loan_ids)
        seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_sms_conversations(conn, org_id, user_ids, lead_ids)
        seed_call_intelligence(conn, org_id, user_ids, lead_ids)
        seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_ai_metrics(conn, org_id)
        seed_rate_monitor(conn, org_id, mum_ids, loan_ids)
        seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_borrower_portal(conn, org_id, lead_ids, loan_ids)
        seed_content_and_campaigns(conn, org_id, user_ids, lead_ids)
        seed_team_chat(conn, org_id, user_ids)
        seed_notifications(conn, org_id, user_ids)

    print("\n🎉 Demo seed complete!")
    print(f"   Org  : {ORG_NAME} (slug: {ORG_SLUG})")
    print(f"   Login: {DEMO_EMAIL}")
    print(f"   Pass : {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
