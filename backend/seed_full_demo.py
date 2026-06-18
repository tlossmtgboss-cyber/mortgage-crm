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
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt as _bcrypt
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class _BcryptCompat:
    """Drop-in replacement providing .hash() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

pwd_context = _BcryptCompat()

# ---------------------------------------------------------------------------
# Config constants
# ---------------------------------------------------------------------------

ORG_NAME = "Summit Home Loans"
ORG_SLUG = "summit-home-loans"
DEMO_EMAIL = "demo@perenniaai.com"
# Demo password is read from the environment — never hardcoded. The seed
# script refuses to run unless DEMO_USER_PASSWORD is set (see main()).
DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "")
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


import re as _re

# Hardcoded allowlist of tables/columns this seed script is permitted to query.
# All callers pass string literals — this is defense-in-depth, not user-input
# sanitization.
_SEED_ALLOWED_TABLES = frozenset({
    "organizations", "users", "leads", "loans", "mum_clients",
    "referral_partners", "tasks", "documents", "activities",
    "scheduler_appointments", "availability_slots", "appointment_types",
    "scheduler_configs", "stage_history", "disclosure_events", "loan_fees",
    "compliance_alerts", "loan_team_members", "morning_briefings",
    "ai_tasks", "email_intakes", "attachment_intakes",
    "sms_conversations", "sms_messages", "call_records",
    "call_intelligence_records", "rate_monitor_alerts",
    "content_items", "content_campaigns", "notifications",
    "borrower_profiles", "borrower_applications",
})

_SEED_ALLOWED_COLUMNS = frozenset({
    "id", "slug", "email", "name", "loan_number", "client_name",
    "organization_id", "user_id", "owner_id",
})


def _validate_seed_identifier(name: str) -> str:
    """Validate that a SQL identifier is alphanumeric+underscore only."""
    if not _re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier in seed script: {name!r}")
    return name


def exists(conn, table: str, column: str, value) -> bool:
    """Return True if a row matching column=value exists in table.

    SAFETY: table and column come from hardcoded string literals at each call
    site within this seed script. Validated against allowlists and regex for
    defense-in-depth. The value uses :val bind parameter.
    """
    _validate_seed_identifier(table)
    _validate_seed_identifier(column)
    if table not in _SEED_ALLOWED_TABLES:
        raise ValueError(f"Seed script: table {table!r} not in allowlist")
    if column not in _SEED_ALLOWED_COLUMNS:
        raise ValueError(f"Seed script: column {column!r} not in allowlist")
    result = conn.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    return result.fetchone() is not None


def get_id(conn, table: str, column: str, value):
    """Return the id of the first row matching column=value, or None.

    SAFETY: table and column come from hardcoded string literals at each call
    site within this seed script. Validated against allowlists and regex for
    defense-in-depth. The value uses :val bind parameter.
    """
    _validate_seed_identifier(table)
    _validate_seed_identifier(column)
    if table not in _SEED_ALLOWED_TABLES:
        raise ValueError(f"Seed script: table {table!r} not in allowlist")
    if column not in _SEED_ALLOWED_COLUMNS:
        raise ValueError(f"Seed script: column {column!r} not in allowlist")
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
    """Create demo leads at various pipeline stages. Returns dict of email→lead_id."""

    DEMO_LEADS = [
        # --- NEW (3 leads, 0-7 days ago) ---
        {
            "first_name": "Tyler", "last_name": "Barnes",
            "email": "tyler.barnes@gmail.com", "phone": "+18432110101",
            "stage": "New", "source": "Zillow",
            "owner_key": "lo_sarah",
            "credit_score": 710, "annual_income": 92000,
            "loan_amount": 320000, "property_value": 375000, "down_payment": 55000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "1423 Meeting St", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 72, "dti": 0.34,
            "notes": "First-time buyer, pre-qualified with another lender. Wants to compare rates.",
            "days_ago": 2,
            "sentiment": "neutral",
            "next_action": "Call to introduce Aria and schedule discovery session",
        },
        {
            "first_name": "Priya", "last_name": "Nair",
            "email": "priya.nair@outlook.com", "phone": "+18432110102",
            "stage": "New", "source": "Facebook",
            "owner_key": "lo_marcus",
            "credit_score": 680, "annual_income": 78000,
            "loan_amount": 260000, "property_value": 295000, "down_payment": 35000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Condo",
            "address": "550 King St", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 58, "dti": 0.38,
            "notes": "Responded to Facebook ad for FHA programs. Asking about minimum down payment.",
            "days_ago": 5,
            "sentiment": "positive",
            "next_action": "Send FHA program overview and follow up call",
        },
        {
            "first_name": "Derek", "last_name": "Hollis",
            "email": "derek.hollis@yahoo.com", "phone": "+18432110103",
            "stage": "New", "source": "Website",
            "owner_key": "lo_sarah",
            "credit_score": 760, "annual_income": 145000,
            "loan_amount": 520000, "property_value": 610000, "down_payment": 90000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "844 Broad St", "city": "Charleston", "state": "SC", "zip_code": "29401",
            "ai_score": 88, "dti": 0.28,
            "notes": "High-intent buyer, used rate calculator on website. Relocating for work.",
            "days_ago": 1,
            "sentiment": "positive",
            "next_action": "Priority outreach — high AI score, complete pre-approval today",
        },
        # --- ATTEMPTED CONTACT (2 leads, 3-14 days ago) ---
        {
            "first_name": "Monique", "last_name": "Duval",
            "email": "monique.duval@gmail.com", "phone": "+18432110104",
            "stage": "Attempted Contact", "source": "Realtor.com",
            "owner_key": "lo_marcus",
            "credit_score": 640, "annual_income": 65000,
            "loan_amount": 215000, "property_value": 240000, "down_payment": 25000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Townhome",
            "address": "210 Ashley Ave", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 47, "dti": 0.41,
            "notes": "Left voicemail twice. Lead from Realtor.com listing inquiry. No response yet.",
            "days_ago": 8,
            "sentiment": "neutral",
            "next_action": "Try SMS outreach — voicemails not being returned",
        },
        {
            "first_name": "Carter", "last_name": "Webb",
            "email": "carter.webb@icloud.com", "phone": "+18432110105",
            "stage": "Attempted Contact", "source": "Cold Call",
            "owner_key": "lo_sarah",
            "credit_score": 695, "annual_income": 88000,
            "loan_amount": 310000, "property_value": 355000, "down_payment": 45000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "3301 Folly Rd", "city": "James Island", "state": "SC", "zip_code": "29412",
            "ai_score": 61, "dti": 0.36,
            "notes": "Cold outreach from expired listing. Showed interest but hasn't scheduled.",
            "days_ago": 11,
            "sentiment": "neutral",
            "next_action": "Send calendar link for 15-min discovery call via Aria",
        },
        # --- PROSPECT (3 leads, 14-30 days ago) ---
        {
            "first_name": "Brianna", "last_name": "Okafor",
            "email": "brianna.okafor@gmail.com", "phone": "+18432110106",
            "stage": "Prospect", "source": "Referral",
            "owner_key": "lo_sarah",
            "credit_score": 725, "annual_income": 112000,
            "loan_amount": 390000, "property_value": 445000, "down_payment": 55000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "120 Coleman Blvd", "city": "Mount Pleasant", "state": "SC", "zip_code": "29464",
            "ai_score": 77, "dti": 0.31,
            "notes": "Referred by realtor partner Jean Holloway. Ready to buy within 60 days.",
            "days_ago": 18,
            "sentiment": "positive",
            "next_action": "Send pre-approval checklist; follow up with income docs request",
        },
        {
            "first_name": "Nathan", "last_name": "Prescott",
            "email": "nathan.prescott@hotmail.com", "phone": "+18432110107",
            "stage": "Prospect", "source": "Zillow",
            "owner_key": "lo_marcus",
            "credit_score": 660, "annual_income": 74000,
            "loan_amount": 245000, "property_value": 275000, "down_payment": 30000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Condo",
            "address": "789 Rivers Ave", "city": "North Charleston", "state": "SC", "zip_code": "29407",
            "ai_score": 54, "dti": 0.40,
            "notes": "Browsing Zillow condos. Concerned about HOA impact on DTI.",
            "days_ago": 22,
            "sentiment": "neutral",
            "next_action": "Educate on FHA condo approval process and HOA add-back",
        },
        {
            "first_name": "Simone", "last_name": "Arceneaux",
            "email": "simone.arceneaux@gmail.com", "phone": "+18432110108",
            "stage": "Prospect", "source": "Website",
            "owner_key": "lo_sarah",
            "credit_score": 740, "annual_income": 130000,
            "loan_amount": 475000, "property_value": 550000, "down_payment": 75000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "2801 Savannah Hwy", "city": "West Ashley", "state": "SC", "zip_code": "29414",
            "ai_score": 82, "dti": 0.29,
            "notes": "Executive relocating from Atlanta. Has pre-approval from credit union but rates seem high.",
            "days_ago": 27,
            "sentiment": "positive",
            "next_action": "Rate comparison analysis — send side-by-side vs credit union offer",
        },
        # --- PRE-QUALIFIED (3 leads, 30-60 days ago) ---
        {
            "first_name": "Kevin", "last_name": "Albright",
            "email": "kevin.albright@gmail.com", "phone": "+18432110109",
            "stage": "Pre-Qualified", "source": "Referral",
            "owner_key": "lo_marcus",
            "credit_score": 718, "annual_income": 95000,
            "loan_amount": 335000, "property_value": 385000, "down_payment": 50000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "501 East Bay St", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 74, "dti": 0.33,
            "notes": "Pre-qualified at $335K. Shopping for homes in Park Circle. Agent relationship strong.",
            "days_ago": 38,
            "sentiment": "positive",
            "next_action": "Check in — has he found a property yet?",
        },
        {
            "first_name": "Jasmine", "last_name": "Winters",
            "email": "jasmine.winters@yahoo.com", "phone": "+18432110110",
            "stage": "Pre-Qualified", "source": "Zillow",
            "owner_key": "lo_sarah",
            "credit_score": 688, "annual_income": 82000,
            "loan_amount": 285000, "property_value": 320000, "down_payment": 35000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Townhome",
            "address": "1122 Calhoun St", "city": "Charleston", "state": "SC", "zip_code": "29401",
            "ai_score": 63, "dti": 0.37,
            "notes": "Pre-qual letter issued. Reviewing Wescott area townhomes with agent.",
            "days_ago": 45,
            "sentiment": "positive",
            "next_action": "Renew pre-qual letter expiring soon; confirm property search progress",
        },
        {
            "first_name": "Elijah", "last_name": "Fontaine",
            "email": "elijah.fontaine@gmail.com", "phone": "+18432110111",
            "stage": "Pre-Qualified", "source": "Facebook",
            "owner_key": "lo_marcus",
            "credit_score": 652, "annual_income": 70000,
            "loan_amount": 235000, "property_value": 265000, "down_payment": 30000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "88 Summerville Ave", "city": "Summerville", "state": "SC", "zip_code": "29483",
            "ai_score": 51, "dti": 0.42,
            "notes": "DTI at edge — needs spouse income verified. Pre-qual conditional on W2s.",
            "days_ago": 52,
            "sentiment": "neutral",
            "next_action": "Request spouse pay stubs and W2s to finalize qualification",
        },
        # --- PRE-APPROVED (2 leads, 45-75 days ago) ---
        {
            "first_name": "Vanessa", "last_name": "Hartley",
            "email": "vanessa.hartley@gmail.com", "phone": "+18432110112",
            "stage": "Pre-Approved", "source": "Referral",
            "owner_key": "lo_sarah",
            "credit_score": 748, "annual_income": 125000,
            "loan_amount": 450000, "property_value": 510000, "down_payment": 60000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "420 Ion Ave", "city": "Mount Pleasant", "state": "SC", "zip_code": "29464",
            "ai_score": 85, "dti": 0.28,
            "notes": "Full pre-approval issued. Under contract — closing target in 35 days. Referred by Bob Walsh at Sullivan's Realty.",
            "days_ago": 55,
            "sentiment": "positive",
            "next_action": "Order appraisal and open escrow; send disclosure package",
        },
        {
            "first_name": "Marcus", "last_name": "Delacroix",
            "email": "marcus.delacroix@icloud.com", "phone": "+18432110113",
            "stage": "Pre-Approved", "source": "Website",
            "owner_key": "lo_marcus",
            "credit_score": 730, "annual_income": 108000,
            "loan_amount": 380000, "property_value": 430000, "down_payment": 50000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "3050 Bohicket Rd", "city": "James Island", "state": "SC", "zip_code": "29412",
            "ai_score": 79, "dti": 0.32,
            "notes": "Pre-approved and actively touring homes. Second offer pending on James Island property.",
            "days_ago": 68,
            "sentiment": "positive",
            "next_action": "Follow up on offer outcome; ready to move to application immediately",
        },
        # --- APPLICATION (3 leads, 60-90 days ago) ---
        {
            "first_name": "Tanya", "last_name": "Morrison",
            "email": "tanya.morrison@gmail.com", "phone": "+18432110114",
            "stage": "Application", "source": "Realtor.com",
            "owner_key": "lo_sarah",
            "credit_score": 722, "annual_income": 98000,
            "loan_amount": 345000, "property_value": 395000, "down_payment": 50000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "714 Wentworth St", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 76, "dti": 0.34,
            "notes": "Application 80% complete. Missing 2022 tax returns. Processor Emily following up.",
            "days_ago": 65,
            "sentiment": "positive",
            "next_action": "Collect 2022 tax transcripts and push to processing queue",
        },
        {
            "first_name": "Roberto", "last_name": "Sandoval",
            "email": "roberto.sandoval@hotmail.com", "phone": "+18432110115",
            "stage": "Application", "source": "Referral",
            "owner_key": "lo_marcus",
            "credit_score": 695, "annual_income": 86000,
            "loan_amount": 295000, "property_value": 335000, "down_payment": 40000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Townhome",
            "address": "2200 Clements Ferry Rd", "city": "North Charleston", "state": "SC", "zip_code": "29492",
            "ai_score": 66, "dti": 0.39,
            "notes": "Full app submitted. FHA case number requested. Awaiting appraisal scheduling.",
            "days_ago": 75,
            "sentiment": "positive",
            "next_action": "Schedule FHA appraisal and order title search",
        },
        {
            "first_name": "Aisha", "last_name": "Coleman",
            "email": "aisha.coleman@gmail.com", "phone": "+18432110116",
            "stage": "Application", "source": "Zillow",
            "owner_key": "lo_sarah",
            "credit_score": 755, "annual_income": 140000,
            "loan_amount": 495000, "property_value": 570000, "down_payment": 75000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "100 Seagrass Ln", "city": "Mount Pleasant", "state": "SC", "zip_code": "29466",
            "ai_score": 91, "dti": 0.27,
            "notes": "Excellent profile. Under contract on new construction. Builder close is 60 days out.",
            "days_ago": 82,
            "sentiment": "positive",
            "next_action": "Lock rate when builder gives 45-day window; monitor market",
        },
        # --- LONG-TERM NURTURE (3 leads, 180-365 days ago) ---
        {
            "first_name": "Gregory", "last_name": "Tatum",
            "email": "gregory.tatum@yahoo.com", "phone": "+18432110117",
            "stage": "Long-Term Nurture", "source": "Cold Call",
            "owner_key": "lo_marcus",
            "credit_score": 635, "annual_income": 60000,
            "loan_amount": 195000, "property_value": 220000, "down_payment": 25000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "500 Dorchester Rd", "city": "Summerville", "state": "SC", "zip_code": "29485",
            "ai_score": 38, "dti": 0.44,
            "notes": "Not ready yet — saving for down payment. Target buy date is spring next year.",
            "days_ago": 210,
            "sentiment": "neutral",
            "next_action": "Monthly check-in; add to rate-watch drip campaign",
        },
        {
            "first_name": "Courtney", "last_name": "Langford",
            "email": "courtney.langford@gmail.com", "phone": "+18432110118",
            "stage": "Long-Term Nurture", "source": "Website",
            "owner_key": "lo_sarah",
            "credit_score": 668, "annual_income": 72000,
            "loan_amount": 240000, "property_value": 270000, "down_payment": 30000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Condo",
            "address": "330 Concord St", "city": "Charleston", "state": "SC", "zip_code": "29401",
            "ai_score": 44, "dti": 0.40,
            "notes": "Currently renting, lease ends in 9 months. Wants to buy but credit needs work first.",
            "days_ago": 260,
            "sentiment": "neutral",
            "next_action": "Send credit improvement guide; schedule 90-day credit review call",
        },
        {
            "first_name": "Antoine", "last_name": "Devereaux",
            "email": "antoine.devereaux@gmail.com", "phone": "+18432110119",
            "stage": "Long-Term Nurture", "source": "Referral",
            "owner_key": "lo_marcus",
            "credit_score": 610, "annual_income": 55000,
            "loan_amount": 175000, "property_value": 200000, "down_payment": 25000,
            "loan_type": "USDA", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "1800 Old Trolley Rd", "city": "Summerville", "state": "SC", "zip_code": "29485",
            "ai_score": 32, "dti": 0.46,
            "notes": "Referred by family member (existing client). Income is borderline USDA limits. Needs 12 months on-time payment history.",
            "days_ago": 340,
            "sentiment": "neutral",
            "next_action": "Annual portfolio review call; check if USDA income eligibility changed",
        },
        # --- CREDIT REPAIR (2 leads, 90-180 days ago) ---
        {
            "first_name": "Darnell", "last_name": "Pace",
            "email": "darnell.pace@gmail.com", "phone": "+18432110120",
            "stage": "Credit Repair", "source": "Facebook",
            "owner_key": "lo_sarah",
            "credit_score": 582, "annual_income": 68000,
            "loan_amount": 230000, "property_value": 260000, "down_payment": 30000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "611 Ashley Ave", "city": "Charleston", "state": "SC", "zip_code": "29403",
            "ai_score": 29, "dti": 0.45,
            "notes": "Two collections from medical bills dragging score below FHA minimum. On 6-month credit repair plan.",
            "days_ago": 115,
            "sentiment": "neutral",
            "next_action": "90-day credit check-in; confirm collections paid or negotiated",
        },
        {
            "first_name": "Shayla", "last_name": "Dupree",
            "email": "shayla.dupree@yahoo.com", "phone": "+18432110121",
            "stage": "Credit Repair", "source": "Realtor.com",
            "owner_key": "lo_marcus",
            "credit_score": 595, "annual_income": 75000,
            "loan_amount": 255000, "property_value": 290000, "down_payment": 35000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Townhome",
            "address": "4400 Ladson Rd", "city": "Summerville", "state": "SC", "zip_code": "29485",
            "ai_score": 35, "dti": 0.43,
            "notes": "Recent late payment from job loss 8 months ago. Score improving. May qualify in 3 months.",
            "days_ago": 155,
            "sentiment": "positive",
            "next_action": "Pull updated credit report next month; fast-track if score crosses 620",
        },
        # --- FUNDED (2 leads, 90-180 days ago) ---
        {
            "first_name": "Michelle", "last_name": "Osei",
            "email": "michelle.osei@gmail.com", "phone": "+18432110122",
            "stage": "Funded", "source": "Referral",
            "owner_key": "lo_sarah",
            "credit_score": 752, "annual_income": 118000,
            "loan_amount": 415000, "property_value": 475000, "down_payment": 60000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "205 Wando Park Blvd", "city": "Mount Pleasant", "state": "SC", "zip_code": "29466",
            "ai_score": 87, "dti": 0.30,
            "notes": "Closed on time. Client satisfaction: 5 stars. Requested referrals sent — introduced to 2 neighbors.",
            "days_ago": 102,
            "sentiment": "positive",
            "next_action": "Send 1-year refi check-in reminder; add to MUM portfolio",
        },
        {
            "first_name": "James", "last_name": "Beaumont",
            "email": "james.beaumont@icloud.com", "phone": "+18432110123",
            "stage": "Funded", "source": "Website",
            "owner_key": "lo_marcus",
            "credit_score": 738, "annual_income": 103000,
            "loan_amount": 360000, "property_value": 415000, "down_payment": 55000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "917 Long Point Rd", "city": "Mount Pleasant", "state": "SC", "zip_code": "29466",
            "ai_score": 81, "dti": 0.33,
            "notes": "VA loan converted to conventional at last minute — appraisal came in strong.",
            "days_ago": 160,
            "sentiment": "positive",
            "next_action": "Congratulations follow-up sent. Schedule 6-month rate review",
        },
        # --- DOES NOT QUALIFY (1 lead, ~120 days ago) ---
        {
            "first_name": "Roderick", "last_name": "Fulton",
            "email": "roderick.fulton@gmail.com", "phone": "+18432110124",
            "stage": "Does Not Qualify", "source": "Cold Call",
            "owner_key": "lo_marcus",
            "credit_score": 558, "annual_income": 42000,
            "loan_amount": 195000, "property_value": 220000, "down_payment": 25000,
            "loan_type": "FHA", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "2900 Azalea Dr", "city": "North Charleston", "state": "SC", "zip_code": "29405",
            "ai_score": 25, "dti": 0.52,
            "notes": "DTI too high and credit score below FHA minimum. Self-employed — 1099 income not sufficient. Advised to revisit in 18 months.",
            "days_ago": 120,
            "sentiment": "negative",
            "next_action": "No immediate action. Add to 18-month nurture reactivation sequence",
        },
        # --- WITHDRAWN (1 lead, ~60 days ago) ---
        {
            "first_name": "Lydia", "last_name": "Whitmore",
            "email": "lydia.whitmore@outlook.com", "phone": "+18432110125",
            "stage": "Withdrawn", "source": "Zillow",
            "owner_key": "lo_sarah",
            "credit_score": 700, "annual_income": 90000,
            "loan_amount": 315000, "property_value": 360000, "down_payment": 45000,
            "loan_type": "Conventional", "loan_purpose": "Purchase",
            "property_type": "Single Family",
            "address": "738 Johnnie Dodds Blvd", "city": "Mount Pleasant", "state": "SC", "zip_code": "29464",
            "ai_score": 59, "dti": 0.36,
            "notes": "Decided to stay in current home after spouse job change. May revisit in 1-2 years.",
            "days_ago": 60,
            "sentiment": "neutral",
            "next_action": "Set 12-month re-engagement reminder in CRM",
        },
    ]

    # Stage → milestone dates mapping
    STAGE_ORDER = [
        "New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved",
        "Application", "Long-Term Nurture", "Credit Repair", "Funded",
        "Does Not Qualify", "Withdrawn",
    ]
    STAGES_WITH_FIRST_CONTACT = {
        "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved",
        "Application", "Long-Term Nurture", "Credit Repair", "Funded",
        "Does Not Qualify", "Withdrawn",
    }
    STAGES_WITH_QUALIFICATION = {
        "Pre-Qualified", "Pre-Approved", "Application", "Funded",
    }
    STAGES_WITH_PREAPPROVAL = {"Pre-Approved", "Application", "Funded"}
    STAGES_WITH_APPLICATION = {"Application", "Funded"}
    STAGES_WITH_CLOSING = {"Funded"}

    lead_ids = {}

    for lead in DEMO_LEADS:
        existing = conn.execute(
            text("SELECT id FROM leads WHERE email = :email AND organization_id = :org_id LIMIT 1"),
            {"email": lead["email"], "org_id": org_id},
        ).fetchone()
        if existing:
            lead_ids[lead["email"]] = existing[0]
            continue

        created_at = days_ago(lead["days_ago"])
        owner_id = user_ids[lead["owner_key"]]
        name = f"{lead['first_name']} {lead['last_name']}"
        ltv = round(float(lead["loan_amount"]) / float(lead["property_value"]), 4) if lead.get("property_value") else None
        stage = lead["stage"]

        # Milestone dates
        d = lead["days_ago"]
        first_contact_date = days_ago(d - 2) if stage in STAGES_WITH_FIRST_CONTACT else None
        last_contact = days_ago(max(1, d - 5)) if stage in STAGES_WITH_FIRST_CONTACT else None
        qualification_date = days_ago(d - 5) if stage in STAGES_WITH_QUALIFICATION else None
        preapproval_date = days_ago(d - 8) if stage in STAGES_WITH_PREAPPROVAL else None
        application_date = days_ago(d - 10) if stage in STAGES_WITH_APPLICATION else None
        closing_date = days_ago(max(1, d - 20)) if stage in STAGES_WITH_CLOSING else None
        application_completed_date = days_ago(d - 15) if stage in STAGES_WITH_CLOSING else None

        result = conn.execute(
            text("""
                INSERT INTO leads (
                    organization_id, owner_id, name, first_name, last_name,
                    email, phone, stage, source,
                    credit_score, annual_income, loan_amount, property_value, down_payment,
                    loan_type, loan_purpose, ltv, dti,
                    property_type, address, city, state, zip_code,
                    ai_score, notes, sentiment, next_action,
                    created_at, lead_received_date, stage_changed_at,
                    first_contact_attempt_date, last_contact,
                    lead_qualification_date, preapproval_issued_date,
                    application_started_date, application_completed_date, closing_date
                ) VALUES (
                    :org_id, :owner_id, :name, :first_name, :last_name,
                    :email, :phone, :stage, :source,
                    :credit_score, :annual_income, :loan_amount, :property_value, :down_payment,
                    :loan_type, :loan_purpose, :ltv, :dti,
                    :property_type, :address, :city, :state, :zip_code,
                    :ai_score, :notes, :sentiment, :next_action,
                    :created_at, :created_at, :created_at,
                    :first_contact_date, :last_contact,
                    :qualification_date, :preapproval_date,
                    :application_date, :application_completed_date, :closing_date
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "owner_id": owner_id,
                "name": name,
                "first_name": lead["first_name"],
                "last_name": lead["last_name"],
                "email": lead["email"],
                "phone": lead["phone"],
                "stage": stage,
                "source": lead["source"],
                "credit_score": lead["credit_score"],
                "annual_income": lead["annual_income"],
                "loan_amount": lead["loan_amount"],
                "property_value": lead["property_value"],
                "down_payment": lead["down_payment"],
                "loan_type": lead["loan_type"],
                "loan_purpose": lead["loan_purpose"],
                "ltv": ltv,
                "dti": lead["dti"],
                "property_type": lead["property_type"],
                "address": lead["address"],
                "city": lead["city"],
                "state": lead["state"],
                "zip_code": lead["zip_code"],
                "ai_score": lead["ai_score"],
                "notes": lead["notes"],
                "sentiment": lead["sentiment"],
                "next_action": lead["next_action"],
                "created_at": created_at,
                "first_contact_date": first_contact_date,
                "last_contact": last_contact,
                "qualification_date": qualification_date,
                "preapproval_date": preapproval_date,
                "application_date": application_date,
                "application_completed_date": application_completed_date,
                "closing_date": closing_date,
            },
        )
        new_id = result.fetchone()[0]
        lead_ids[lead["email"]] = new_id

    conn.commit()
    print(f"✅ Seeded {len(lead_ids)} leads")
    return lead_ids


def seed_loans(conn, org_id, user_ids, lead_ids):
    """Create demo loans (10 active, 5 funded). Returns dict of loan_number→loan_id."""

    DEMO_LOANS = [
        # --- APPLICATION (2) ---
        {
            "loan_number": "SHL-2026-0001",
            "lead_email": "tanya.morrison@gmail.com",
            "stage": "APPLICATION",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 345000,
            "purchase_price": 395000,
            "down_payment": 50000,
            "rate": 6.875,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 398000,
            "days_ago": 65,
            "closing_days_from_now": 55,
            "lock_days_ago": 60,
            "lock_term_days": 60,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 12,
            "sla_status": "on-track",
            "risk_score": 22,
        },
        {
            "loan_number": "SHL-2026-0002",
            "lead_email": "roberto.sandoval@hotmail.com",
            "stage": "APPLICATION",
            "loan_type": "FHA",
            "loan_purpose": "Purchase",
            "amount": 295000,
            "purchase_price": 335000,
            "down_payment": 40000,
            "rate": 6.625,
            "term": 360,
            "property_type": "Townhome",
            "appraisal_value": 338000,
            "days_ago": 75,
            "closing_days_from_now": 48,
            "lock_days_ago": 70,
            "lock_term_days": 60,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 8,
            "sla_status": "on-track",
            "risk_score": 31,
        },
        # --- PROCESSING (2) ---
        {
            "loan_number": "SHL-2026-0003",
            "lead_email": "vanessa.hartley@gmail.com",
            "stage": "PROCESSING",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 450000,
            "purchase_price": 510000,
            "down_payment": 60000,
            "rate": 6.750,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 515000,
            "days_ago": 55,
            "closing_days_from_now": 35,
            "lock_days_ago": 50,
            "lock_term_days": 45,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 9,
            "sla_status": "on-track",
            "risk_score": 18,
        },
        {
            "loan_number": "SHL-2026-0004",
            "lead_email": "aisha.coleman@gmail.com",
            "stage": "PROCESSING",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 495000,
            "purchase_price": 570000,
            "down_payment": 75000,
            "rate": 6.875,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 575000,
            "days_ago": 82,
            "closing_days_from_now": 42,
            "lock_days_ago": 75,
            "lock_term_days": 60,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 14,
            "sla_status": "on-track",
            "risk_score": 12,
        },
        # --- SUBMITTED (1) ---
        {
            "loan_number": "SHL-2026-0005",
            "lead_email": "marcus.delacroix@icloud.com",
            "stage": "SUBMITTED",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 380000,
            "purchase_price": 430000,
            "down_payment": 50000,
            "rate": 6.999,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 435000,
            "days_ago": 68,
            "closing_days_from_now": 28,
            "lock_days_ago": 65,
            "lock_term_days": 45,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 5,
            "sla_status": "on-track",
            "risk_score": 20,
        },
        # --- UNDERWRITING (2) ---
        {
            "loan_number": "SHL-2026-0006",
            "lead_email": "kevin.albright@gmail.com",
            "stage": "UNDERWRITING",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 335000,
            "purchase_price": 385000,
            "down_payment": 50000,
            "rate": 7.000,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 390000,
            "days_ago": 38,
            "closing_days_from_now": 22,
            "lock_days_ago": 35,
            "lock_term_days": 30,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 7,
            "sla_status": "on-track",
            "risk_score": 24,
        },
        {
            "loan_number": "SHL-2026-0007",
            "lead_email": "jasmine.winters@yahoo.com",
            "stage": "UNDERWRITING",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 285000,
            "purchase_price": 320000,
            "down_payment": 35000,
            "rate": 6.875,
            "term": 360,
            "property_type": "Townhome",
            "appraisal_value": 323000,
            "days_ago": 45,
            "closing_days_from_now": 18,
            "lock_days_ago": 42,
            "lock_term_days": 30,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 6,
            "sla_status": "at-risk",
            "risk_score": 38,
        },
        # --- CONDITIONAL_APPROVAL (1) ---
        {
            "loan_number": "SHL-2026-0008",
            "lead_email": "brianna.okafor@gmail.com",
            "stage": "CONDITIONAL_APPROVAL",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 390000,
            "purchase_price": 445000,
            "down_payment": 55000,
            "rate": 6.750,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 450000,
            "days_ago": 18,
            "closing_days_from_now": 14,
            "lock_days_ago": 15,
            "lock_term_days": 21,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 3,
            "sla_status": "on-track",
            "risk_score": 15,
        },
        # --- CLEAR_TO_CLOSE (1) ---
        {
            "loan_number": "SHL-2026-0009",
            "lead_email": "elijah.fontaine@gmail.com",
            "stage": "CLEAR_TO_CLOSE",
            "loan_type": "FHA",
            "loan_purpose": "Purchase",
            "amount": 235000,
            "purchase_price": 265000,
            "down_payment": 30000,
            "rate": 6.625,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 268000,
            "days_ago": 52,
            "closing_days_from_now": 5,
            "lock_days_ago": 48,
            "lock_term_days": 30,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 2,
            "sla_status": "on-track",
            "risk_score": 10,
        },
        # --- CLOSING (1) ---
        {
            "loan_number": "SHL-2026-0010",
            "lead_email": "simone.arceneaux@gmail.com",
            "stage": "CLOSING",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 475000,
            "purchase_price": 550000,
            "down_payment": 75000,
            "rate": 6.500,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 555000,
            "days_ago": 27,
            "closing_days_from_now": 2,
            "lock_days_ago": 24,
            "lock_term_days": 30,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 1,
            "sla_status": "on-track",
            "risk_score": 8,
        },
        # --- FUNDED (5) ---
        {
            "loan_number": "SHL-2026-0011",
            "lead_email": "michelle.osei@gmail.com",
            "stage": "FUNDED",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 415000,
            "purchase_price": 475000,
            "down_payment": 60000,
            "rate": 7.125,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 478000,
            "days_ago": 102,
            "funded_days_ago": 95,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 0,
            "sla_status": "on-track",
            "risk_score": 0,
        },
        {
            "loan_number": "SHL-2026-0012",
            "lead_email": "james.beaumont@icloud.com",
            "stage": "FUNDED",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 360000,
            "purchase_price": 415000,
            "down_payment": 55000,
            "rate": 7.250,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 418000,
            "days_ago": 160,
            "funded_days_ago": 152,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 0,
            "sla_status": "on-track",
            "risk_score": 0,
        },
        {
            "loan_number": "SHL-2026-0013",
            "lead_email": "tyler.barnes@gmail.com",
            "stage": "FUNDED",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 320000,
            "purchase_price": 375000,
            "down_payment": 55000,
            "rate": 6.875,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 378000,
            "days_ago": 210,
            "funded_days_ago": 200,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 0,
            "sla_status": "on-track",
            "risk_score": 0,
        },
        {
            "loan_number": "SHL-2026-0014",
            "lead_email": "carter.webb@icloud.com",
            "stage": "FUNDED",
            "loan_type": "Conventional",
            "loan_purpose": "Purchase",
            "amount": 310000,
            "purchase_price": 355000,
            "down_payment": 45000,
            "rate": 7.125,
            "term": 360,
            "property_type": "Single Family",
            "appraisal_value": 358000,
            "days_ago": 265,
            "funded_days_ago": 255,
            "processor_name": "Emily Park",
            "underwriter_name": "James Mitchell",
            "days_in_stage": 0,
            "sla_status": "on-track",
            "risk_score": 0,
        },
        {
            "loan_number": "SHL-2026-0015",
            "lead_email": "nathan.prescott@hotmail.com",
            "stage": "FUNDED",
            "loan_type": "FHA",
            "loan_purpose": "Purchase",
            "amount": 245000,
            "purchase_price": 275000,
            "down_payment": 30000,
            "rate": 6.750,
            "term": 360,
            "property_type": "Condo",
            "appraisal_value": 278000,
            "days_ago": 330,
            "funded_days_ago": 320,
            "processor_name": "Emily Park",
            "underwriter_name": "Rachel Kim",
            "days_in_stage": 0,
            "sla_status": "on-track",
            "risk_score": 0,
        },
    ]

    loan_ids = {}

    for loan in DEMO_LOANS:
        if exists(conn, "loans", "loan_number", loan["loan_number"]):
            loan_ids[loan["loan_number"]] = get_id(conn, "loans", "loan_number", loan["loan_number"])
            print(f"⏭️  Loan exists: {loan['loan_number']}")
            continue

        lead_id = lead_ids.get(loan["lead_email"])
        lead_row = None
        if lead_id:
            lead_row = conn.execute(
                text("""
                    SELECT name, email, phone, owner_id, address, city, state, zip_code
                    FROM leads WHERE id = :lid
                """),
                {"lid": lead_id},
            ).fetchone()

        borrower_name = lead_row[0] if lead_row else loan["lead_email"]
        borrower_email = lead_row[1] if lead_row else None
        borrower_phone = lead_row[2] if lead_row else None
        loan_officer_id = lead_row[3] if lead_row else user_ids.get("manager")
        prop_address = lead_row[4] if lead_row else None
        prop_city = lead_row[5] if lead_row else "Charleston"
        prop_state = lead_row[6] if lead_row else "SC"
        prop_zip = lead_row[7] if lead_row else "29403"

        created_at = days_ago(loan["days_ago"])
        application_date = days_ago(loan["days_ago"] - 2)
        stage_changed_at = days_ago(loan.get("days_in_stage", 0))

        # Lock dates (only for non-funded active loans that have a lock)
        lock_date = None
        lock_expiration_date = None
        if loan.get("lock_days_ago") is not None and loan["stage"] != "FUNDED":
            lock_date = days_ago(loan["lock_days_ago"])
            lock_expiration_date = lock_date + timedelta(days=loan.get("lock_term_days", 30))

        # Closing date
        closing_date = None
        if loan["stage"] != "FUNDED" and loan.get("closing_days_from_now") is not None:
            closing_date = days_from_now(loan["closing_days_from_now"])

        # Funded date (only for FUNDED loans)
        funded_date = None
        if loan["stage"] == "FUNDED" and loan.get("funded_days_ago") is not None:
            funded_date = days_ago(loan["funded_days_ago"])
            closing_date = funded_date

        amount = Decimal(str(loan["amount"]))
        purchase_price = Decimal(str(loan["purchase_price"]))
        down_payment = Decimal(str(loan["down_payment"]))
        rate = Decimal(str(loan["rate"]))
        appraisal_value = Decimal(str(loan["appraisal_value"]))
        ltv = round(float(amount) / float(appraisal_value), 4)

        result = conn.execute(
            text("""
                INSERT INTO loans (
                    organization_id, loan_number,
                    borrower_name, borrower_email, borrower_phone,
                    stage, loan_type, loan_purpose,
                    amount, purchase_price, down_payment,
                    rate, term,
                    property_address, property_city, property_state, property_zip,
                    property_type,
                    loan_officer_id, processor, underwriter,
                    closing_date, funded_date,
                    lock_date, lock_expiration_date,
                    appraisal_value, ltv,
                    days_in_stage, sla_status, risk_score,
                    application_date, stage_changed_at, created_at
                ) VALUES (
                    :org_id, :loan_number,
                    :borrower_name, :borrower_email, :borrower_phone,
                    :stage, :loan_type, :loan_purpose,
                    :amount, :purchase_price, :down_payment,
                    :rate, :term,
                    :property_address, :property_city, :property_state, :property_zip,
                    :property_type,
                    :loan_officer_id, :processor, :underwriter,
                    :closing_date, :funded_date,
                    :lock_date, :lock_expiration_date,
                    :appraisal_value, :ltv,
                    :days_in_stage, :sla_status, :risk_score,
                    :application_date, :stage_changed_at, :created_at
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "loan_number": loan["loan_number"],
                "borrower_name": borrower_name,
                "borrower_email": borrower_email,
                "borrower_phone": borrower_phone,
                "stage": loan["stage"],
                "loan_type": loan["loan_type"],
                "loan_purpose": loan["loan_purpose"],
                "amount": amount,
                "purchase_price": purchase_price,
                "down_payment": down_payment,
                "rate": rate,
                "term": loan.get("term", 360),
                "property_address": prop_address,
                "property_city": prop_city,
                "property_state": prop_state,
                "property_zip": prop_zip,
                "property_type": loan["property_type"],
                "loan_officer_id": loan_officer_id,
                "processor": loan.get("processor_name"),
                "underwriter": loan.get("underwriter_name"),
                "closing_date": closing_date,
                "funded_date": funded_date,
                "lock_date": lock_date,
                "lock_expiration_date": lock_expiration_date,
                "appraisal_value": appraisal_value,
                "ltv": ltv,
                "days_in_stage": loan.get("days_in_stage", 0),
                "sla_status": loan.get("sla_status", "on-track"),
                "risk_score": loan.get("risk_score", 0),
                "application_date": application_date,
                "stage_changed_at": stage_changed_at,
                "created_at": created_at,
            },
        )
        new_id = result.fetchone()[0]
        loan_ids[loan["loan_number"]] = new_id
        print(f"✅ Created loan: {loan['loan_number']} — {loan['stage']} — {borrower_name}")

    conn.commit()
    print(f"✅ Seeded {len(loan_ids)} loans")
    return loan_ids


def seed_mum_clients(conn, org_id, user_ids):
    """Create MUM (Mortgage Under Management) clients. Returns list of mum_ids."""

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # Helper: compute remaining balance after m payments using standard amortization
    def amortized_balance(principal, annual_rate_pct, term_months, months_elapsed):
        r = annual_rate_pct / 12 / 100
        n = term_months
        m = min(months_elapsed, n)
        if r == 0:
            return Decimal(str(round(principal * (1 - m / n), 2)))
        monthly = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
        remaining = principal * ((1 + r) ** n - (1 + r) ** m) / ((1 + r) ** n - 1)
        return Decimal(str(round(remaining, 2)))

    # Helper: property value after annualized appreciation
    def appreciated_value(original, years, annual_pct):
        val = original * (1 + annual_pct / 100) ** years
        return Decimal(str(round(val, 2)))

    # fmt: (client_name, email, phone, loan_number, close_year_ago, rate, original_amount,
    #        appraisal, appreciation_pct, engagement_score, status, property_state, property_zip,
    #        owner_key, loan_officer_name, loan_officer_email, notes)
    MUM_CLIENTS = [
        # 10 years ago — 2016, ~3.5%
        {
            "client_name": "Robert & Patricia Donovan",
            "email": "robert.donovan@gmail.com",
            "phone": "+18431110001",
            "loan_number": "MUM-2016-0001",
            "close_years_ago": 10,
            "rate": 3.500,
            "original_amount": 285000,
            "appraisal": 320000,
            "appreciation_pct": 4.5,
            "engagement_score": 82,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29403",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Long-term portfolio client. Equity-rich — potential cash-out refi candidate.",
        },
        # 9 years ago — 2017, ~4.0%
        {
            "client_name": "Marcus & Diane Ellison",
            "email": "marcus.ellison@yahoo.com",
            "phone": "+18431110002",
            "loan_number": "MUM-2017-0001",
            "close_years_ago": 9,
            "rate": 4.000,
            "original_amount": 340000,
            "appraisal": 385000,
            "appreciation_pct": 4.0,
            "engagement_score": 74,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29464",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "Annual rate review upcoming. Rate is competitive — low refi urgency.",
        },
        # 8 years ago — 2018, ~4.5%
        {
            "client_name": "Jennifer Castillo",
            "email": "jennifer.castillo@outlook.com",
            "phone": "+18431110003",
            "loan_number": "MUM-2018-0001",
            "close_years_ago": 8,
            "rate": 4.500,
            "original_amount": 215000,
            "appraisal": 245000,
            "appreciation_pct": 3.5,
            "engagement_score": 68,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29412",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Single borrower. Exploring investment property — referral opportunity.",
        },
        # 8 years ago — 2018, ~4.5%
        {
            "client_name": "Thomas & Keisha Whitfield",
            "email": "thomas.whitfield@icloud.com",
            "phone": "+18431110004",
            "loan_number": "MUM-2018-0002",
            "close_years_ago": 8,
            "rate": 4.500,
            "original_amount": 420000,
            "appraisal": 475000,
            "appreciation_pct": 5.0,
            "engagement_score": 88,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29466",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "High-value portfolio. Referred two neighbors this year.",
        },
        # 7 years ago — 2019, ~3.75%
        {
            "client_name": "Angela & Derek Pope",
            "email": "angela.pope@gmail.com",
            "phone": "+18431110005",
            "loan_number": "MUM-2019-0001",
            "close_years_ago": 7,
            "rate": 3.750,
            "original_amount": 310000,
            "appraisal": 355000,
            "appreciation_pct": 4.0,
            "engagement_score": 77,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29485",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Pre-pandemic rate. Very unlikely to refi. Focus on referral relationship.",
        },
        # 6 years ago — 2020, ~2.75%  (ultra-low rate era)
        {
            "client_name": "Daniel & Renee Huang",
            "email": "daniel.huang@gmail.com",
            "phone": "+18431110006",
            "loan_number": "MUM-2020-0001",
            "close_years_ago": 6,
            "rate": 2.750,
            "original_amount": 395000,
            "appraisal": 440000,
            "appreciation_pct": 5.5,
            "engagement_score": 91,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29464",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "Pandemic-era rate. Will never voluntarily refi — high equity. Strong referral source.",
        },
        # 5 years ago — 2021, ~3.0%
        {
            "client_name": "Stephanie & Carlos Moreno",
            "email": "stephanie.moreno@hotmail.com",
            "phone": "+18431110007",
            "loan_number": "MUM-2021-0001",
            "close_years_ago": 5,
            "rate": 3.000,
            "original_amount": 455000,
            "appraisal": 510000,
            "appreciation_pct": 5.0,
            "engagement_score": 85,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29403",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Excellent equity position. Exploring HELOC for home improvement project.",
        },
        # 3 years ago — 2023, ~6.75% (rate spike era)
        {
            "client_name": "Brian & Monica Tanner",
            "email": "brian.tanner@gmail.com",
            "phone": "+18431110008",
            "loan_number": "MUM-2023-0001",
            "close_years_ago": 3,
            "rate": 6.750,
            "original_amount": 375000,
            "appraisal": 420000,
            "appreciation_pct": 3.0,
            "engagement_score": 62,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29401",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "High rate — strong refi candidate when market dips below 6%. Set rate alert.",
        },
        # 3 years ago — 2023, ~6.75%
        {
            "client_name": "Lauren Fitzgerald",
            "email": "lauren.fitzgerald@yahoo.com",
            "phone": "+18431110009",
            "loan_number": "MUM-2023-0002",
            "close_years_ago": 3,
            "rate": 6.875,
            "original_amount": 270000,
            "appraisal": 305000,
            "appreciation_pct": 3.5,
            "engagement_score": 58,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29407",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "First-time buyer who stretched at peak rates. Monitoring for refi window.",
        },
        # 2 years ago — 2024, ~6.5%
        {
            "client_name": "Kenneth & Paula Osei",
            "email": "kenneth.osei@gmail.com",
            "phone": "+18431110010",
            "loan_number": "MUM-2024-0001",
            "close_years_ago": 2,
            "rate": 6.500,
            "original_amount": 480000,
            "appraisal": 535000,
            "appreciation_pct": 4.0,
            "engagement_score": 71,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29466",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "Jumbo-adjacent loan. Would benefit from rate drop of 75+ bps. Track market.",
        },
        # 2 years ago — 2024, ~6.5%
        {
            "client_name": "Nadia & Paul Bergeron",
            "email": "nadia.bergeron@icloud.com",
            "phone": "+18431110011",
            "loan_number": "MUM-2024-0002",
            "close_years_ago": 2,
            "rate": 6.625,
            "original_amount": 325000,
            "appraisal": 365000,
            "appreciation_pct": 3.5,
            "engagement_score": 65,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29414",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Asked about rental property strategy. Potential investor referral pipeline.",
        },
        # 1 year ago — 2025, ~6.875%
        {
            "client_name": "Terrence & Alicia Watkins",
            "email": "terrence.watkins@gmail.com",
            "phone": "+18431110012",
            "loan_number": "MUM-2025-0001",
            "close_years_ago": 1,
            "rate": 6.875,
            "original_amount": 350000,
            "appraisal": 390000,
            "appreciation_pct": 4.0,
            "engagement_score": 55,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29483",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "Recent borrower. Monitoring rate market for 12-month refi opportunity.",
        },
        # 1 year ago — 2025, ~6.875%
        {
            "client_name": "Victoria & Sam Nguyen",
            "email": "victoria.nguyen@outlook.com",
            "phone": "+18431110013",
            "loan_number": "MUM-2025-0002",
            "close_years_ago": 1,
            "rate": 6.750,
            "original_amount": 415000,
            "appraisal": 460000,
            "appreciation_pct": 3.5,
            "engagement_score": 60,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29464",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Dual-income household. Good candidate for rate alert subscription.",
        },
        # 4 years ago — 2022, ~5.5% (rising rate era)
        {
            "client_name": "Harold & Christine Vance",
            "email": "harold.vance@gmail.com",
            "phone": "+18431110014",
            "loan_number": "MUM-2022-0001",
            "close_years_ago": 4,
            "rate": 5.500,
            "original_amount": 295000,
            "appraisal": 330000,
            "appreciation_pct": 4.0,
            "engagement_score": 70,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29412",
            "owner_key": "lo_marcus",
            "loan_officer_name": "Marcus Johnson",
            "loan_officer_email": "marcus.johnson@summithomeloans.com",
            "notes": "Rate elevated vs 2020-2021 cohort. Refi if market hits 4.75%.",
        },
        # 4 years ago — 2022, ~5.5%
        {
            "client_name": "Crystal & James Bowman",
            "email": "crystal.bowman@yahoo.com",
            "phone": "+18431110015",
            "loan_number": "MUM-2022-0002",
            "close_years_ago": 4,
            "rate": 5.625,
            "original_amount": 260000,
            "appraisal": 295000,
            "appreciation_pct": 4.5,
            "engagement_score": 67,
            "status": "active",
            "property_state": "SC",
            "property_zip": "29405",
            "owner_key": "lo_sarah",
            "loan_officer_name": "Sarah Chen",
            "loan_officer_email": "sarah.chen@summithomeloans.com",
            "notes": "Exploring refinance as rates have dropped from peak. Watching closely.",
        },
    ]

    mum_ids = []

    for client in MUM_CLIENTS:
        if exists(conn, "mum_clients", "email", client["email"]):
            existing_id = get_id(conn, "mum_clients", "email", client["email"])
            mum_ids.append(existing_id)
            print(f"⏭️  MUM client exists: {client['email']}")
            continue

        years_ago = client["close_years_ago"]
        close_date = NOW - timedelta(days=int(years_ago * 365.25))
        first_payment_date = close_date + timedelta(days=45)
        months_elapsed = int(years_ago * 12)

        original_amount = client["original_amount"]
        rate = client["rate"]
        term = 360

        current_balance = amortized_balance(original_amount, rate, term, months_elapsed)
        current_property_value = appreciated_value(
            client["appraisal"], years_ago, client["appreciation_pct"]
        )
        estimated_equity = current_property_value - current_balance
        current_ltv = round(float(current_balance) / float(current_property_value), 4)

        refi_opportunity = rate > 6.0
        if refi_opportunity:
            # Rough estimated savings: difference in monthly payment vs 5.5% market rate
            market_rate = 5.5
            r_curr = rate / 12 / 100
            r_mkt = market_rate / 12 / 100
            months_remaining = term - months_elapsed
            balance_f = float(current_balance)
            monthly_curr = balance_f * r_curr * (1 + r_curr) ** months_remaining / ((1 + r_curr) ** months_remaining - 1)
            monthly_mkt = balance_f * r_mkt * (1 + r_mkt) ** months_remaining / ((1 + r_mkt) ** months_remaining - 1)
            estimated_savings = Decimal(str(round((monthly_curr - monthly_mkt) * 12, 2)))  # annual savings
        else:
            estimated_savings = None

        refi_score = max(0, min(100, int((rate - 3.0) * 15 + (years_ago * 2))))
        owner_id = lo_sarah_id if client["owner_key"] == "lo_sarah" else lo_marcus_id
        last_contact = NOW - timedelta(days=random.randint(15, 90))
        next_touchpoint = NOW + timedelta(days=random.randint(14, 45))

        result = conn.execute(
            text("""
                INSERT INTO mum_clients (
                    organization_id, client_name, email, phone,
                    loan_number, original_close_date, closing_date, first_payment_date,
                    interest_rate, original_loan_amount, current_loan_amount,
                    appraisal_value_at_closing, current_property_value,
                    original_rate, current_rate, loan_balance,
                    refinance_opportunity, estimated_savings,
                    engagement_score, status, notes,
                    last_contact, next_touchpoint,
                    loan_officer, loan_officer_email,
                    user_id, term,
                    estimated_equity, current_ltv, refi_score,
                    property_state, property_zip, created_at
                ) VALUES (
                    :org_id, :client_name, :email, :phone,
                    :loan_number, :original_close_date, :closing_date, :first_payment_date,
                    :interest_rate, :original_loan_amount, :current_loan_amount,
                    :appraisal_value_at_closing, :current_property_value,
                    :original_rate, :current_rate, :loan_balance,
                    :refinance_opportunity, :estimated_savings,
                    :engagement_score, :status, :notes,
                    :last_contact, :next_touchpoint,
                    :loan_officer, :loan_officer_email,
                    :user_id, :term,
                    :estimated_equity, :current_ltv, :refi_score,
                    :property_state, :property_zip, :created_at
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "client_name": client["client_name"],
                "email": client["email"],
                "phone": client["phone"],
                "loan_number": client["loan_number"],
                "original_close_date": close_date,
                "closing_date": close_date,
                "first_payment_date": first_payment_date,
                "interest_rate": Decimal(str(rate)),
                "original_loan_amount": Decimal(str(original_amount)),
                "current_loan_amount": current_balance,
                "appraisal_value_at_closing": Decimal(str(client["appraisal"])),
                "current_property_value": current_property_value,
                "original_rate": Decimal(str(rate)),
                "current_rate": Decimal(str(rate)),
                "loan_balance": current_balance,
                "refinance_opportunity": refi_opportunity,
                "estimated_savings": estimated_savings,
                "engagement_score": client["engagement_score"],
                "status": client["status"],
                "notes": client["notes"],
                "last_contact": last_contact,
                "next_touchpoint": next_touchpoint,
                "loan_officer": client["loan_officer_name"],
                "loan_officer_email": client["loan_officer_email"],
                "user_id": owner_id,
                "term": term,
                "estimated_equity": estimated_equity,
                "current_ltv": Decimal(str(current_ltv)),
                "refi_score": refi_score,
                "property_state": client["property_state"],
                "property_zip": client["property_zip"],
                "created_at": close_date,
            },
        )
        new_id = result.fetchone()[0]
        mum_ids.append(new_id)
        print(f"✅ Created MUM client: {client['client_name']} ({client['loan_number']}, rate={rate}%)")

    conn.commit()
    print(f"✅ Seeded {len(mum_ids)} MUM clients")
    return mum_ids


def seed_referral_partners(conn, org_id, user_ids, lead_ids):
    """Create referral partners linked to leads. Returns dict of partner name→ID."""

    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    PARTNERS = [
        {
            "name": "Jennifer Walsh",
            "business_name": "RE/MAX Charleston",
            "contact_name": "Jennifer Walsh",
            "category": "realtor",
            "company": "RE/MAX Charleston",
            "type": "realtor",
            "email": "jennifer.walsh@remax.com",
            "phone": "+18431220001",
            "referrals_in": 18,
            "referrals_out": 5,
            "closed_loans": 12,
            "volume": Decimal("4200000.00"),
            "loyalty_tier": "gold",
            "title": "Realtor / Team Lead",
            "street_address": "1122 East Bay St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29403",
            "owner_id": lo_sarah_id,
            "notes": "Top-producing gold partner. Refers luxury buyers regularly. Monthly lunch relationship.",
        },
        {
            "name": "Amanda Foster",
            "business_name": "Lowcountry Homes",
            "contact_name": "Amanda Foster",
            "category": "realtor",
            "company": "Lowcountry Homes",
            "type": "realtor",
            "email": "amanda.foster@lowcountryhomes.com",
            "phone": "+18431220002",
            "referrals_in": 15,
            "referrals_out": 4,
            "closed_loans": 9,
            "volume": Decimal("3100000.00"),
            "loyalty_tier": "gold",
            "title": "Senior Realtor",
            "street_address": "850 Coleman Blvd",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_sarah_id,
            "notes": "Specializes in Mt Pleasant. Strong first-time buyer pipeline.",
        },
        {
            "name": "Nicole Williams",
            "business_name": "Keller Williams Mt Pleasant",
            "contact_name": "Nicole Williams",
            "category": "realtor",
            "company": "Keller Williams Mt Pleasant",
            "type": "realtor",
            "email": "nicole.williams@kwmtp.com",
            "phone": "+18431220003",
            "referrals_in": 12,
            "referrals_out": 3,
            "closed_loans": 7,
            "volume": Decimal("2500000.00"),
            "loyalty_tier": "gold",
            "title": "Realtor",
            "street_address": "1050 Johnnie Dodds Blvd",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_marcus_id,
            "notes": "Rising star in the Mt Pleasant market. Strong social media presence.",
        },
        {
            "name": "Robert Chen",
            "business_name": "Edward Jones",
            "contact_name": "Robert Chen",
            "category": "financial_advisor",
            "company": "Edward Jones",
            "type": "financial_advisor",
            "email": "robert.chen@edwardjones.com",
            "phone": "+18431220004",
            "referrals_in": 8,
            "referrals_out": 6,
            "closed_loans": 5,
            "volume": Decimal("1800000.00"),
            "loyalty_tier": "silver",
            "title": "Financial Advisor",
            "street_address": "470 King St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29403",
            "owner_id": lo_sarah_id,
            "notes": "Mutual referral relationship. Refers HNW clients who need large purchase loans.",
        },
        {
            "name": "Maria Rodriguez",
            "business_name": "Lowcountry Builders",
            "contact_name": "Maria Rodriguez",
            "category": "builder",
            "company": "Lowcountry Builders",
            "type": "builder",
            "email": "maria.rodriguez@lowcountrybuilders.com",
            "phone": "+18431220005",
            "referrals_in": 6,
            "referrals_out": 2,
            "closed_loans": 3,
            "volume": Decimal("1200000.00"),
            "loyalty_tier": "silver",
            "title": "Sales Director",
            "street_address": "3000 Ashley River Rd",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29414",
            "owner_id": lo_marcus_id,
            "notes": "New construction pipeline. Prefers lenders with 60-day lock programs.",
        },
        {
            "name": "David Kim",
            "business_name": "Kim & Associates",
            "contact_name": "David Kim",
            "category": "attorney",
            "company": "Kim & Associates",
            "type": "attorney",
            "email": "david.kim@kimassociates.com",
            "phone": "+18431220006",
            "referrals_in": 4,
            "referrals_out": 8,
            "closed_loans": 2,
            "volume": Decimal("700000.00"),
            "loyalty_tier": "bronze",
            "title": "Real Estate Attorney",
            "street_address": "150 Meeting St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29401",
            "owner_id": lo_sarah_id,
            "notes": "Handles estate and probate sales. Low volume but high-quality referrals.",
        },
        {
            "name": "Lisa Thompson",
            "business_name": "Allstate Insurance",
            "contact_name": "Lisa Thompson",
            "category": "insurance_agent",
            "company": "Allstate Insurance",
            "type": "insurance_agent",
            "email": "lisa.thompson@allstate.com",
            "phone": "+18431220007",
            "referrals_in": 3,
            "referrals_out": 5,
            "closed_loans": 1,
            "volume": Decimal("350000.00"),
            "loyalty_tier": "bronze",
            "title": "Insurance Agent",
            "street_address": "2200 Ashley Phosphate Rd",
            "city": "North Charleston",
            "state": "SC",
            "zip_code": "29405",
            "owner_id": lo_marcus_id,
            "notes": "Bundling opportunity — refers clients who need home insurance plus mortgage.",
        },
        {
            "name": "Michael Brown",
            "business_name": "Brown CPA Group",
            "contact_name": "Michael Brown",
            "category": "cpa",
            "company": "Brown CPA Group",
            "type": "cpa",
            "email": "michael.brown@browncpa.com",
            "phone": "+18431220008",
            "referrals_in": 2,
            "referrals_out": 3,
            "closed_loans": 1,
            "volume": Decimal("280000.00"),
            "loyalty_tier": "bronze",
            "title": "CPA / Tax Advisor",
            "street_address": "500 Wingo Way",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_sarah_id,
            "notes": "Self-employed client referrals. Educating on bank statement loan programs.",
        },
    ]

    partner_ids = {}

    for partner in PARTNERS:
        if exists(conn, "referral_partners", "email", partner["email"]):
            existing_id = get_id(conn, "referral_partners", "email", partner["email"])
            partner_ids[partner["name"]] = existing_id
            print(f"⏭️  Referral partner exists: {partner['name']}")
            continue

        last_interaction = NOW - timedelta(days=random.randint(7, 45))

        result = conn.execute(
            text("""
                INSERT INTO referral_partners (
                    organization_id, name, business_name, contact_name,
                    category, company, type, phone, email,
                    referrals_in, referrals_out, closed_loans, volume,
                    status, loyalty_tier, last_interaction, notes,
                    street_address, city, state, zip_code,
                    title, created_at, owner_id
                ) VALUES (
                    :org_id, :name, :business_name, :contact_name,
                    :category, :company, :type, :phone, :email,
                    :referrals_in, :referrals_out, :closed_loans, :volume,
                    :status, :loyalty_tier, :last_interaction, :notes,
                    :street_address, :city, :state, :zip_code,
                    :title, :created_at, :owner_id
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "name": partner["name"],
                "business_name": partner["business_name"],
                "contact_name": partner["contact_name"],
                "category": partner["category"],
                "company": partner["company"],
                "type": partner["type"],
                "phone": partner["phone"],
                "email": partner["email"],
                "referrals_in": partner["referrals_in"],
                "referrals_out": partner["referrals_out"],
                "closed_loans": partner["closed_loans"],
                "volume": partner["volume"],
                "status": "active",
                "loyalty_tier": partner["loyalty_tier"],
                "last_interaction": last_interaction,
                "notes": partner["notes"],
                "street_address": partner["street_address"],
                "city": partner["city"],
                "state": partner["state"],
                "zip_code": partner["zip_code"],
                "title": partner["title"],
                "created_at": NOW - timedelta(days=random.randint(90, 730)),
                "owner_id": partner["owner_id"],
            },
        )
        new_id = result.fetchone()[0]
        partner_ids[partner["name"]] = new_id
        print(f"✅ Created referral partner: {partner['name']} ({partner['loyalty_tier']}, {partner['category']})")

    conn.commit()

    # Link 3-5 leads to gold-tier partners (skip leads already sourced as Referral)
    gold_partners = [
        ("Jennifer Walsh", "brianna.okafor@gmail.com"),
        ("Amanda Foster", "vanessa.hartley@gmail.com"),
        ("Nicole Williams", "roberto.sandoval@hotmail.com"),
        ("Jennifer Walsh", "michelle.osei@gmail.com"),
        ("Amanda Foster", "kevin.albright@gmail.com"),
    ]
    linked = 0
    for partner_name, lead_email in gold_partners:
        partner_id = partner_ids.get(partner_name)
        lead_id = lead_ids.get(lead_email) if lead_ids else None
        if not partner_id or not lead_id:
            continue

        # Only update if the lead exists and source is not already 'Referral'
        update_result = conn.execute(
            text("""
                UPDATE leads
                SET referral_partner_id = :partner_id, source = 'Referral'
                WHERE id = :lead_id
                  AND organization_id = :org_id
                  AND (source IS NULL OR source != 'Referral')
            """),
            {"partner_id": partner_id, "lead_id": lead_id, "org_id": org_id},
        )
        if update_result.rowcount:
            linked += 1
            print(f"✅ Linked lead {lead_email} → partner {partner_name}")

    conn.commit()
    print(f"✅ Seeded {len(partner_ids)} referral partners, linked {linked} leads")
    return partner_ids


def seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo tasks across users, leads, and loans."""

    # Convenience aliases
    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    processor_id = user_ids.get("processor")
    uw_rachel_id = user_ids.get("uw_rachel")
    uw_james_id = user_ids.get("uw_james")
    ops_id = user_ids.get("ops")

    # Lead/loan id helpers (safe get)
    def lid(email):
        return lead_ids.get(email)

    def lnid(loan_number):
        return loan_ids.get(loan_number)

    # task spec:
    # (title, description, priority, status, due_offset_days, owner_id,
    #  lead_email_or_None, loan_number_or_None, related_contact_name, completed_days_ago)
    # due_offset_days: negative = past (overdue), 0 = today, positive = future
    # completed_days_ago: None unless status='completed'

    TASKS = [
        # ---- OVERDUE (5, due 1-5 days ago, status=pending) ----
        {
            "title": "Follow up with Tanya Morrison — rate lock expiring",
            "description": "Rate lock on SHL-2026-0001 expires soon. Call to discuss extension options and current market.",
            "priority": "high",
            "status": "pending",
            "due_days": -1,
            "owner_id": lo_sarah_id,
            "lead_email": "tanya.morrison@gmail.com",
            "loan_number": "SHL-2026-0001",
            "contact_name": "Tanya Morrison",
        },
        {
            "title": "Request W-2 from Roberto Sandoval",
            "description": "2024 W-2 still missing from file. FHA case number cannot be ordered without full income docs.",
            "priority": "high",
            "status": "pending",
            "due_days": -2,
            "owner_id": processor_id,
            "lead_email": "roberto.sandoval@hotmail.com",
            "loan_number": "SHL-2026-0002",
            "contact_name": "Roberto Sandoval",
        },
        {
            "title": "Call Carter Webb — 7 days no contact",
            "description": "Lead from cold call on expired listing. No response to 3 voicemails and 1 SMS. Try email.",
            "priority": "medium",
            "status": "pending",
            "due_days": -3,
            "owner_id": lo_sarah_id,
            "lead_email": "carter.webb@icloud.com",
            "loan_number": None,
            "contact_name": "Carter Webb",
        },
        {
            "title": "Update Salesforce records for Q1 funded loans",
            "description": "Q1 funded loans (SHL-2026-0011 through SHL-2026-0015) need Salesforce sync and closed-loan disposition.",
            "priority": "low",
            "status": "pending",
            "due_days": -4,
            "owner_id": ops_id,
            "lead_email": None,
            "loan_number": None,
            "contact_name": None,
        },
        {
            "title": "Review appraisal for Kevin Albright",
            "description": "Appraisal returned at $390K vs $385K purchase price. Review for LTV impact and send summary to UW.",
            "priority": "high",
            "status": "pending",
            "due_days": -5,
            "owner_id": uw_rachel_id,
            "lead_email": "kevin.albright@gmail.com",
            "loan_number": "SHL-2026-0006",
            "contact_name": "Kevin Albright",
        },

        # ---- DUE TODAY (8, due_days=0, status pending or in_progress) ----
        {
            "title": "Send pre-approval letter to Vanessa Hartley",
            "description": "Updated pre-approval letter needed — original expired. Borrower's agent is waiting.",
            "priority": "high",
            "status": "in_progress",
            "due_days": 0,
            "owner_id": lo_sarah_id,
            "lead_email": "vanessa.hartley@gmail.com",
            "loan_number": "SHL-2026-0003",
            "contact_name": "Vanessa Hartley",
        },
        {
            "title": "Complete conditions review for Brianna Okafor",
            "description": "Conditional approval issued. 3 remaining conditions: HOI binder, title commitment update, gift letter.",
            "priority": "high",
            "status": "in_progress",
            "due_days": 0,
            "owner_id": uw_rachel_id,
            "lead_email": "brianna.okafor@gmail.com",
            "loan_number": "SHL-2026-0008",
            "contact_name": "Brianna Okafor",
        },
        {
            "title": "Submit loan file to underwriting — Aisha Coleman",
            "description": "All docs collected. File ready for UW submission. Processor to do final checklist and submit today.",
            "priority": "high",
            "status": "pending",
            "due_days": 0,
            "owner_id": processor_id,
            "lead_email": "aisha.coleman@gmail.com",
            "loan_number": "SHL-2026-0004",
            "contact_name": "Aisha Coleman",
        },
        {
            "title": "Schedule closing for Elijah Fontaine",
            "description": "CTC issued. Coordinate closing date with title company and borrower. Target: 5 days from now.",
            "priority": "high",
            "status": "in_progress",
            "due_days": 0,
            "owner_id": lo_marcus_id,
            "lead_email": "elijah.fontaine@gmail.com",
            "loan_number": "SHL-2026-0009",
            "contact_name": "Elijah Fontaine",
        },
        {
            "title": "Follow up with Priya Nair — FHA program overview",
            "description": "New Facebook lead asking about FHA minimum down payment. Send program overview and schedule discovery call.",
            "priority": "medium",
            "status": "pending",
            "due_days": 0,
            "owner_id": lo_marcus_id,
            "lead_email": "priya.nair@outlook.com",
            "loan_number": None,
            "contact_name": "Priya Nair",
        },
        {
            "title": "Weekly team pipeline meeting",
            "description": "Weekly pipeline review: discuss at-risk loans (SHL-2026-0007), rate lock expirations, and upcoming closings.",
            "priority": "medium",
            "status": "pending",
            "due_days": 0,
            "owner_id": manager_id,
            "lead_email": None,
            "loan_number": None,
            "contact_name": None,
        },
        {
            "title": "Send rate comparison to Simone Arceneaux",
            "description": "Borrower has existing pre-approval from a credit union at 7.1%. Prepare side-by-side rate comparison.",
            "priority": "medium",
            "status": "pending",
            "due_days": 0,
            "owner_id": lo_sarah_id,
            "lead_email": "simone.arceneaux@gmail.com",
            "loan_number": "SHL-2026-0010",
            "contact_name": "Simone Arceneaux",
        },
        {
            "title": "Order title search for Roberto Sandoval",
            "description": "Full app submitted for SHL-2026-0002. Title company needs to be engaged and order placed today.",
            "priority": "medium",
            "status": "pending",
            "due_days": 0,
            "owner_id": processor_id,
            "lead_email": "roberto.sandoval@hotmail.com",
            "loan_number": "SHL-2026-0002",
            "contact_name": "Roberto Sandoval",
        },

        # ---- UPCOMING (10, due 1-7 days from now, status=pending) ----
        {
            "title": "Confirm closing docs for Simone Arceneaux",
            "description": "Closing on SHL-2026-0010 in 2 days. Confirm all closing docs are signed and title is clear.",
            "priority": "high",
            "status": "pending",
            "due_days": 1,
            "owner_id": lo_sarah_id,
            "lead_email": "simone.arceneaux@gmail.com",
            "loan_number": "SHL-2026-0010",
            "contact_name": "Simone Arceneaux",
        },
        {
            "title": "Priority outreach — Derek Hollis pre-approval",
            "description": "High AI score (88). Relocating buyer — website lead. Complete pre-approval today before lead goes cold.",
            "priority": "high",
            "status": "pending",
            "due_days": 1,
            "owner_id": lo_sarah_id,
            "lead_email": "derek.hollis@yahoo.com",
            "loan_number": None,
            "contact_name": "Derek Hollis",
        },
        {
            "title": "Review appraisal for Jasmine Winters",
            "description": "Appraisal at $323K vs $320K purchase price. File is at-risk (risk score 38). UW review before CTC.",
            "priority": "high",
            "status": "pending",
            "due_days": 2,
            "owner_id": uw_james_id,
            "lead_email": "jasmine.winters@yahoo.com",
            "loan_number": "SHL-2026-0007",
            "contact_name": "Jasmine Winters",
        },
        {
            "title": "Follow up with Marcus Delacroix — second offer outcome",
            "description": "Second offer pending on James Island property. Call to find out offer decision and prepare to move fast.",
            "priority": "medium",
            "status": "pending",
            "due_days": 2,
            "owner_id": lo_marcus_id,
            "lead_email": "marcus.delacroix@icloud.com",
            "loan_number": "SHL-2026-0005",
            "contact_name": "Marcus Delacroix",
        },
        {
            "title": "Send pre-approval checklist to Brianna Okafor",
            "description": "Referred lead ready to buy in 60 days. Send income doc checklist and schedule application appointment.",
            "priority": "medium",
            "status": "pending",
            "due_days": 3,
            "owner_id": lo_sarah_id,
            "lead_email": "brianna.okafor@gmail.com",
            "loan_number": None,
            "contact_name": "Brianna Okafor",
        },
        {
            "title": "Request spouse pay stubs — Elijah Fontaine",
            "description": "DTI at edge case. Spouse W-2 and recent pay stubs needed to finalize qualification.",
            "priority": "medium",
            "status": "pending",
            "due_days": 3,
            "owner_id": lo_marcus_id,
            "lead_email": "elijah.fontaine@gmail.com",
            "loan_number": None,
            "contact_name": "Elijah Fontaine",
        },
        {
            "title": "Collect 2022 tax transcripts — Tanya Morrison",
            "description": "Application 80% complete. 2022 tax transcripts needed to push file to processing queue.",
            "priority": "medium",
            "status": "pending",
            "due_days": 4,
            "owner_id": processor_id,
            "lead_email": "tanya.morrison@gmail.com",
            "loan_number": "SHL-2026-0001",
            "contact_name": "Tanya Morrison",
        },
        {
            "title": "Monthly check-in — Gregory Tatum (nurture)",
            "description": "Long-term nurture lead saving for down payment. Monthly contact call to maintain relationship.",
            "priority": "low",
            "status": "pending",
            "due_days": 5,
            "owner_id": lo_marcus_id,
            "lead_email": "gregory.tatum@yahoo.com",
            "loan_number": None,
            "contact_name": "Gregory Tatum",
        },
        {
            "title": "Pipeline SLA audit — at-risk loans",
            "description": "Review all loans with risk_score > 25. Identify stalled files and assign corrective actions.",
            "priority": "medium",
            "status": "pending",
            "due_days": 5,
            "owner_id": manager_id,
            "lead_email": None,
            "loan_number": None,
            "contact_name": None,
        },
        {
            "title": "Send credit improvement guide — Courtney Langford",
            "description": "Currently renting, lease ends in 9 months. Send credit improvement guide and schedule 90-day review.",
            "priority": "low",
            "status": "pending",
            "due_days": 7,
            "owner_id": lo_sarah_id,
            "lead_email": "courtney.langford@gmail.com",
            "loan_number": None,
            "contact_name": "Courtney Langford",
        },

        # ---- COMPLETED (7, completed within last 7 days) ----
        {
            "title": "Send FHA program overview to Priya Nair",
            "description": "Sent FHA overview PDF with min down payment breakdown. Borrower confirmed receipt.",
            "priority": "medium",
            "status": "completed",
            "due_days": -6,
            "completed_days": 5,
            "owner_id": lo_marcus_id,
            "lead_email": "priya.nair@outlook.com",
            "loan_number": None,
            "contact_name": "Priya Nair",
        },
        {
            "title": "Lock rate for Vanessa Hartley — SHL-2026-0003",
            "description": "Rate locked at 6.750% for 45 days. Confirmation sent to borrower and agent.",
            "priority": "high",
            "status": "completed",
            "due_days": -5,
            "completed_days": 4,
            "owner_id": lo_sarah_id,
            "lead_email": "vanessa.hartley@gmail.com",
            "loan_number": "SHL-2026-0003",
            "contact_name": "Vanessa Hartley",
        },
        {
            "title": "Order appraisal for Brianna Okafor",
            "description": "Appraisal ordered through AMC. Estimated turnaround 7-10 business days. AMC confirmation #AP-8847.",
            "priority": "high",
            "status": "completed",
            "due_days": -4,
            "completed_days": 3,
            "owner_id": processor_id,
            "lead_email": "brianna.okafor@gmail.com",
            "loan_number": "SHL-2026-0008",
            "contact_name": "Brianna Okafor",
        },
        {
            "title": "Verify employment — Jasmine Winters",
            "description": "VOE completed via The Work Number. Employer confirmed at $82K/year base. Uploaded to file.",
            "priority": "medium",
            "status": "completed",
            "due_days": -3,
            "completed_days": 2,
            "owner_id": processor_id,
            "lead_email": "jasmine.winters@yahoo.com",
            "loan_number": "SHL-2026-0007",
            "contact_name": "Jasmine Winters",
        },
        {
            "title": "Issue CTC — Elijah Fontaine SHL-2026-0009",
            "description": "All conditions cleared. Clear-to-close issued by underwriting. Closing disclosure sent to borrower.",
            "priority": "high",
            "status": "completed",
            "due_days": -2,
            "completed_days": 1,
            "owner_id": uw_james_id,
            "lead_email": "elijah.fontaine@gmail.com",
            "loan_number": "SHL-2026-0009",
            "contact_name": "Elijah Fontaine",
        },
        {
            "title": "Send 6-month rate review to Michelle Osei",
            "description": "Post-close touchpoint sent. Congratulations follow-up with equity summary and refi market watch.",
            "priority": "low",
            "status": "completed",
            "due_days": -1,
            "completed_days": 1,
            "owner_id": lo_sarah_id,
            "lead_email": "michelle.osei@gmail.com",
            "loan_number": "SHL-2026-0011",
            "contact_name": "Michelle Osei",
        },
        {
            "title": "Branch compliance review — Q1 HMDA data",
            "description": "HMDA data for Q1 2026 reviewed and validated. No reportable anomalies. Submitted to compliance officer.",
            "priority": "medium",
            "status": "completed",
            "due_days": -2,
            "completed_days": 1,
            "owner_id": ops_id,
            "lead_email": None,
            "loan_number": None,
            "contact_name": None,
        },
    ]

    inserted = 0
    skipped = 0

    for task in TASKS:
        # Idempotency: check by title + owner_id
        owner_id = task["owner_id"]
        existing = conn.execute(
            text("""
                SELECT id FROM tasks
                WHERE title = :title AND owner_id = :owner_id AND organization_id = :org_id
                LIMIT 1
            """),
            {"title": task["title"], "owner_id": owner_id, "org_id": org_id},
        ).fetchone()
        if existing:
            skipped += 1
            continue

        lead_id = lid(task.get("lead_email")) if task.get("lead_email") else None
        loan_id = lnid(task.get("loan_number")) if task.get("loan_number") else None

        due_date = days_from_now(task["due_days"]) if task["due_days"] >= 0 else days_ago(-task["due_days"])

        completed_at = None
        if task["status"] == "completed":
            completed_at = days_ago(task.get("completed_days", 1))

        created_at = days_ago(max(1, -task["due_days"] + 2)) if task["due_days"] < 0 else days_ago(7)

        conn.execute(
            text("""
                INSERT INTO tasks (
                    organization_id, title, description, status, priority,
                    due_date, owner_id, lead_id, loan_id,
                    related_contact_name, completed_at, created_at
                ) VALUES (
                    :org_id, :title, :description, :status, :priority,
                    :due_date, :owner_id, :lead_id, :loan_id,
                    :contact_name, :completed_at, :created_at
                )
            """),
            {
                "org_id": org_id,
                "title": task["title"],
                "description": task.get("description"),
                "status": task["status"],
                "priority": task["priority"],
                "due_date": due_date,
                "owner_id": owner_id,
                "lead_id": lead_id,
                "loan_id": loan_id,
                "contact_name": task.get("contact_name"),
                "completed_at": completed_at,
                "created_at": created_at,
            },
        )
        inserted += 1

    conn.commit()
    print(f"✅ Seeded {inserted} tasks ({skipped} already existed)")


def seed_documents(conn, org_id, user_ids, loan_ids):
    """Create demo document records for loans."""

    processor_id = user_ids.get("processor")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # Map loan_number → (lead_email, lo_id, stage, days_ago_created, is_purchase)
    LOAN_META = {
        "SHL-2026-0001": ("tanya.morrison@gmail.com",  lo_sarah_id,  "APPLICATION",          65,  True),
        "SHL-2026-0002": ("roberto.sandoval@hotmail.com", lo_marcus_id, "APPLICATION",        75,  True),
        "SHL-2026-0003": ("vanessa.hartley@gmail.com",  lo_sarah_id,  "PROCESSING",           55,  True),
        "SHL-2026-0004": ("aisha.coleman@gmail.com",    lo_sarah_id,  "PROCESSING",           82,  True),
        "SHL-2026-0005": ("marcus.delacroix@icloud.com", lo_marcus_id, "SUBMITTED",           68,  True),
        "SHL-2026-0006": ("kevin.albright@gmail.com",   lo_marcus_id, "UNDERWRITING",         38,  True),
        "SHL-2026-0007": ("jasmine.winters@yahoo.com",  lo_sarah_id,  "UNDERWRITING",         45,  True),
        "SHL-2026-0008": ("brianna.okafor@gmail.com",   lo_sarah_id,  "CONDITIONAL_APPROVAL", 18,  True),
        "SHL-2026-0009": ("elijah.fontaine@gmail.com",  lo_marcus_id, "CLEAR_TO_CLOSE",       52,  True),
        "SHL-2026-0010": ("simone.arceneaux@gmail.com", lo_sarah_id,  "CLOSING",              27,  True),
        "SHL-2026-0011": ("michelle.osei@gmail.com",    lo_sarah_id,  "FUNDED",               102, True),
        "SHL-2026-0012": ("james.beaumont@icloud.com",  lo_marcus_id, "FUNDED",               160, True),
        "SHL-2026-0013": ("tyler.barnes@gmail.com",     lo_sarah_id,  "FUNDED",               210, True),
        "SHL-2026-0014": ("carter.webb@icloud.com",     lo_sarah_id,  "FUNDED",               265, True),
        "SHL-2026-0015": ("nathan.prescott@hotmail.com", lo_marcus_id, "FUNDED",              330, True),
    }

    # Stage ordering for deciding which docs to include
    STAGE_ORDER = [
        "APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING",
        "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED",
    ]

    def stage_index(stage):
        try:
            return STAGE_ORDER.index(stage)
        except ValueError:
            return 0

    # Document spec: (doc_type_value, filename_template, notes, min_stage_idx)
    # min_stage_idx: stage must be >= this index to include this doc
    DOC_SPECS = [
        # Always present from APPLICATION onward
        ("Driver's License",      "{ln}-drivers-license.pdf",      "Government-issued ID — front and back",                         0),
        ("W2",                    "{ln}-w2-2024.pdf",              "2024 W-2 — primary borrower",                                   0),
        ("Paystub",               "{ln}-paystub-current.pdf",      "Most recent 30-day pay stubs",                                  0),
        ("Bank Statement",        "{ln}-bank-stmt-90day.pdf",      "90-day bank statements — checking and savings",                 0),
        ("Purchase Contract",     "{ln}-purchase-contract.pdf",    "Executed purchase and sale agreement",                          0),
        # Added during PROCESSING
        ("Tax Return (1040)",     "{ln}-1040-2023.pdf",            "2023 federal tax return — IRS transcript",                      1),
        ("Initial Disclosures",   "{ln}-initial-disclosures.pdf",  "TRID initial disclosure package — signed",                     1),
        ("Loan Estimate",         "{ln}-loan-estimate.pdf",        "TRID Loan Estimate — borrower acknowledged",                   1),
        # Added after UNDERWRITING submission
        ("Appraisal",             "{ln}-appraisal-report.pdf",     "Full URAR appraisal report from licensed appraiser",           2),
        ("Credit Report",         "{ln}-credit-report.pdf",        "Tri-merge credit report — all bureaus",                        2),
        ("Title Commitment",      "{ln}-title-commitment.pdf",     "Preliminary title commitment — Schedule A & B",                 3),
        ("Homeowners Insurance",  "{ln}-hoi-binder.pdf",           "Homeowners insurance binder — coverage confirmed",              3),
        # Closing docs
        ("Closing Disclosure",    "{ln}-closing-disclosure.pdf",   "TRID Closing Disclosure — borrower signed 3-day waiting period", 5),
    ]

    inserted = 0
    skipped = 0

    for loan_number, (lead_email, lo_id, stage, loan_days_ago, is_purchase) in LOAN_META.items():
        loan_id = loan_ids.get(loan_number)
        if not loan_id:
            continue

        # Fetch the lead_id for borrower_id linkage
        lead_row = conn.execute(
            text("SELECT id FROM leads WHERE email = :email AND organization_id = :org_id LIMIT 1"),
            {"email": lead_email, "org_id": org_id},
        ).fetchone()
        borrower_id = lead_row[0] if lead_row else None

        s_idx = stage_index(stage)
        uploader_id = processor_id if processor_id else lo_id

        for (doc_type_val, filename_tmpl, notes, min_stage_idx) in DOC_SPECS:
            if s_idx < min_stage_idx:
                continue

            # Skip Purchase Contract for non-purchase (all are purchase here, but guard)
            if doc_type_val == "Purchase Contract" and not is_purchase:
                continue

            filename = filename_tmpl.replace("{ln}", loan_number.lower())
            type_slug = doc_type_val.lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")
            file_location = f"https://docs.summithomeloans.com/demo/{loan_number}/{type_slug}.pdf"

            # Idempotency: check by loan_id + doc_type
            existing = conn.execute(
                text("""
                    SELECT id FROM documents
                    WHERE loan_id = :loan_id AND doc_type = :doc_type
                    LIMIT 1
                """),
                {"loan_id": loan_id, "doc_type": doc_type_val},
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Realistic upload date: somewhere between loan creation and now
            # Earlier docs uploaded closer to loan creation; later docs more recent
            upload_offset = max(1, loan_days_ago - (min_stage_idx * 5) - random.randint(1, 5))
            uploaded_at = days_ago(upload_offset)

            file_size = random.randint(50000, 5000000)

            conn.execute(
                text("""
                    INSERT INTO documents (
                        organization_id, borrower_id, loan_id,
                        doc_type, filename, original_filename,
                        file_location, file_size, mime_type,
                        source, status, notes,
                        uploaded_at, uploaded_by_user_id
                    ) VALUES (
                        :org_id, :borrower_id, :loan_id,
                        :doc_type, :filename, :original_filename,
                        :file_location, :file_size, :mime_type,
                        :source, :status, :notes,
                        :uploaded_at, :uploaded_by_user_id
                    )
                """),
                {
                    "org_id": org_id,
                    "borrower_id": borrower_id,
                    "loan_id": loan_id,
                    "doc_type": doc_type_val,
                    "filename": filename,
                    "original_filename": filename,
                    "file_location": file_location,
                    "file_size": file_size,
                    "mime_type": "application/pdf",
                    "source": "MANUAL_UPLOAD",
                    "status": "active",
                    "notes": notes,
                    "uploaded_at": uploaded_at,
                    "uploaded_by_user_id": uploader_id,
                },
            )
            inserted += 1

    conn.commit()
    print(f"✅ Seeded {inserted} documents ({skipped} already existed)")


def seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo calendar events and appointments.

    Creates:
    - 1 SchedulerConfig (team-level)
    - 4 SchedulerAppointmentTypes
    - 2 BookingLinks (one per LO)
    - 10 AvailabilitySlots (Mon-Fri for Sarah + Marcus)
    - 3 BlockedTimes
    - 20 Appointments
    """
    from datetime import time as _time

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    manager_id = user_ids.get("manager")

    # ------------------------------------------------------------------
    # 1. SchedulerConfig
    # ------------------------------------------------------------------
    config_id = get_id(conn, "scheduler_configs", "organization_id", org_id)
    if config_id:
        print("⏭️  SchedulerConfig exists")
    else:
        result = conn.execute(
            text("""
                INSERT INTO scheduler_configs
                    (organization_id, config_name, timezone,
                     default_duration_minutes, min_duration_minutes, max_duration_minutes,
                     min_notice_hours, max_advance_days, max_meetings_per_day,
                     is_active, setup_completed, created_at, updated_at)
                VALUES
                    (:org_id, :config_name, :tz,
                     :default_dur, :min_dur, :max_dur,
                     :min_notice, :max_advance, :max_per_day,
                     :is_active, :setup_completed, :now, :now)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "config_name": "Summit Home Loans — Default Schedule",
                "tz": "America/New_York",
                "default_dur": 30,
                "min_dur": 15,
                "max_dur": 120,
                "min_notice": 2,
                "max_advance": 60,
                "max_per_day": 8,
                "is_active": True,
                "setup_completed": True,
                "now": NOW,
            },
        )
        config_id = result.fetchone()[0]
        conn.commit()
        print(f"✅ Created SchedulerConfig (id={config_id})")

    # ------------------------------------------------------------------
    # 2. SchedulerAppointmentType (table: appointment_types)
    # ------------------------------------------------------------------
    APPT_TYPES = [
        {
            "type_key": "consultation",
            "type_name": "Initial Consultation",
            "duration": 30,
            "meeting_type": "discovery_call",
            "color": "#3b82f6",
            "public_slug": "consultation",
        },
        {
            "type_key": "document_review",
            "type_name": "Document Review",
            "duration": 15,
            "meeting_type": "document_review",
            "color": "#f59e0b",
            "public_slug": "document-review",
        },
        {
            "type_key": "closing_prep",
            "type_name": "Closing Prep Meeting",
            "duration": 60,
            "meeting_type": "closing_prep",
            "color": "#10b981",
            "public_slug": "closing-prep",
        },
        {
            "type_key": "team_sync",
            "type_name": "Team Meeting",
            "duration": 30,
            "meeting_type": "team_sync",
            "color": "#8b5cf6",
            "public_slug": "team-sync",
        },
    ]

    appt_type_ids = {}
    for at in APPT_TYPES:
        existing_id = conn.execute(
            text("""
                SELECT id FROM appointment_types
                WHERE organization_id = :org_id AND type_key = :type_key
                LIMIT 1
            """),
            {"org_id": org_id, "type_key": at["type_key"]},
        ).fetchone()
        if existing_id:
            appt_type_ids[at["type_key"]] = existing_id[0]
            print(f"⏭️  AppointmentType exists: {at['type_key']}")
            continue

        result = conn.execute(
            text("""
                INSERT INTO appointment_types
                    (organization_id, config_id, type_key, type_name,
                     default_duration_minutes, meeting_type,
                     is_active, is_public, color, public_slug, created_at, updated_at)
                VALUES
                    (:org_id, :config_id, :type_key, :type_name,
                     :duration, :meeting_type,
                     :is_active, :is_public, :color, :public_slug, :now, :now)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "config_id": config_id,
                "type_key": at["type_key"],
                "type_name": at["type_name"],
                "duration": at["duration"],
                "meeting_type": at["meeting_type"],
                "is_active": True,
                "is_public": True,
                "color": at["color"],
                "public_slug": at["public_slug"],
                "now": NOW,
            },
        )
        new_id = result.fetchone()[0]
        appt_type_ids[at["type_key"]] = new_id
        conn.commit()
        print(f"✅ Created AppointmentType: {at['type_name']} (id={new_id})")

    # ------------------------------------------------------------------
    # 3. BookingLinks (table: scheduler_booking_links)
    # ------------------------------------------------------------------
    BOOKING_LINKS = [
        {"slug": "sarah-chen-book", "name": "Book with Sarah Chen", "user_id": lo_sarah_id},
        {"slug": "marcus-johnson-book", "name": "Book with Marcus Johnson", "user_id": lo_marcus_id},
    ]
    booking_link_ids = {}
    for bl in BOOKING_LINKS:
        existing_id = conn.execute(
            text("""
                SELECT id FROM scheduler_booking_links
                WHERE organization_id = :org_id AND slug = :slug
                LIMIT 1
            """),
            {"org_id": org_id, "slug": bl["slug"]},
        ).fetchone()
        if existing_id:
            booking_link_ids[bl["slug"]] = existing_id[0]
            print(f"⏭️  BookingLink exists: {bl['slug']}")
            continue

        result = conn.execute(
            text("""
                INSERT INTO scheduler_booking_links
                    (organization_id, user_id, slug, link_name,
                     is_public, is_active, created_at, updated_at)
                VALUES
                    (:org_id, :user_id, :slug, :link_name,
                     :is_public, :is_active, :now, :now)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "user_id": bl["user_id"],
                "slug": bl["slug"],
                "link_name": bl["name"],
                "is_public": True,
                "is_active": True,
                "now": NOW,
            },
        )
        new_id = result.fetchone()[0]
        booking_link_ids[bl["slug"]] = new_id
        conn.commit()
        print(f"✅ Created BookingLink: {bl['slug']} (id={new_id})")

    # ------------------------------------------------------------------
    # 4. AvailabilitySlots (Mon-Fri 9-17 for each LO)
    # ------------------------------------------------------------------
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    slot_count = 0
    for user_id in [lo_sarah_id, lo_marcus_id]:
        if not user_id:
            continue
        for day in DAYS:
            existing = conn.execute(
                text("""
                    SELECT id FROM availability_slots
                    WHERE organization_id = :org_id
                      AND user_id = :user_id
                      AND day_of_week = :day
                    LIMIT 1
                """),
                {"org_id": org_id, "user_id": user_id, "day": day},
            ).fetchone()
            if existing:
                continue

            conn.execute(
                text("""
                    INSERT INTO availability_slots
                        (organization_id, config_id, user_id, day_of_week,
                         start_time, end_time, is_recurring, is_active,
                         created_at, updated_at)
                    VALUES
                        (:org_id, :config_id, :user_id, :day,
                         :start_time, :end_time, :is_recurring, :is_active,
                         :now, :now)
                """),
                {
                    "org_id": org_id,
                    "config_id": config_id,
                    "user_id": user_id,
                    "day": day,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "is_recurring": True,
                    "is_active": True,
                    "now": NOW,
                },
            )
            slot_count += 1

    conn.commit()
    if slot_count:
        print(f"✅ Created {slot_count} availability slots")
    else:
        print("⏭️  Availability slots already exist")

    # ------------------------------------------------------------------
    # 5. BlockedTimes (table: scheduler_blocked_times)
    # ------------------------------------------------------------------
    # Next Monday (days until Monday from today)
    today_weekday = TODAY.weekday()  # 0=Mon, 6=Sun
    days_until_monday = (7 - today_weekday) % 7 or 7
    next_monday = days_from_now(days_until_monday)

    BLOCKED = [
        {
            "title": "PTO — Sarah Chen",
            "block_type": "pto",
            "user_id": lo_sarah_id,
            "start_datetime": next_monday.replace(hour=0, minute=0, second=0, microsecond=0),
            "end_datetime": next_monday.replace(hour=23, minute=59, second=59, microsecond=0),
        },
        {
            "title": "Team Lunch",
            "block_type": "custom",
            "user_id": None,  # company-wide
            "start_datetime": NOW.replace(hour=12, minute=0, second=0, microsecond=0),
            "end_datetime": NOW.replace(hour=13, minute=0, second=0, microsecond=0),
        },
        {
            "title": "Branch All-Hands",
            "block_type": "meeting",
            "user_id": None,
            "start_datetime": days_from_now(3).replace(hour=9, minute=0, second=0, microsecond=0),
            "end_datetime": days_from_now(3).replace(hour=10, minute=0, second=0, microsecond=0),
        },
    ]

    blocked_count = 0
    for bt in BLOCKED:
        existing = conn.execute(
            text("""
                SELECT id FROM scheduler_blocked_times
                WHERE organization_id = :org_id AND title = :title
                LIMIT 1
            """),
            {"org_id": org_id, "title": bt["title"]},
        ).fetchone()
        if existing:
            print(f"⏭️  BlockedTime exists: {bt['title']}")
            continue

        conn.execute(
            text("""
                INSERT INTO scheduler_blocked_times
                    (organization_id, user_id, title, block_type,
                     start_datetime, end_datetime, is_active, created_at, updated_at)
                VALUES
                    (:org_id, :user_id, :title, :block_type,
                     :start_dt, :end_dt, :is_active, :now, :now)
            """),
            {
                "org_id": org_id,
                "user_id": bt["user_id"],
                "title": bt["title"],
                "block_type": bt["block_type"],
                "start_dt": bt["start_datetime"],
                "end_dt": bt["end_datetime"],
                "is_active": True,
                "now": NOW,
            },
        )
        blocked_count += 1

    conn.commit()
    if blocked_count:
        print(f"✅ Created {blocked_count} blocked times")
    else:
        print("⏭️  Blocked times already exist")

    # ------------------------------------------------------------------
    # 6. Appointments (20 total)
    # ------------------------------------------------------------------
    # Build a lead lookup list for linking
    # Spread: 5 past week completed, 5 this week confirmed, 10 next 2 weeks booked
    consultation_type_id = appt_type_ids.get("consultation")
    doc_review_type_id = appt_type_ids.get("document_review")
    closing_prep_type_id = appt_type_ids.get("closing_prep")
    team_sync_type_id = appt_type_ids.get("team_sync")

    APPOINTMENTS = [
        # --- Past week (completed) ---
        {
            "title": "Initial Consultation — Tyler Barnes",
            "type_id": consultation_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "tyler.barnes@gmail.com",
            "loan_number": None,
            "meeting_type": "discovery_call",
            "meeting_mode": "video",
            "start_offset": -6,
            "start_hour": 10,
            "duration": 30,
            "attendee_name": "Tyler Barnes",
            "attendee_email": "tyler.barnes@gmail.com",
            "attendee_phone": "+18432110101",
            "status": "completed",
        },
        {
            "title": "Document Review — Vanessa Hartley",
            "type_id": doc_review_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "vanessa.hartley@gmail.com",
            "loan_number": "SHL-2026-0003",
            "meeting_type": "document_review",
            "meeting_mode": "video",
            "start_offset": -5,
            "start_hour": 14,
            "duration": 15,
            "attendee_name": "Vanessa Hartley",
            "attendee_email": "vanessa.hartley@gmail.com",
            "attendee_phone": "+18432110112",
            "status": "completed",
        },
        {
            "title": "Closing Prep — Elijah Fontaine",
            "type_id": closing_prep_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "elijah.fontaine@gmail.com",
            "loan_number": "SHL-2026-0009",
            "meeting_type": "closing_prep",
            "meeting_mode": "in_person",
            "start_offset": -4,
            "start_hour": 11,
            "duration": 60,
            "attendee_name": "Elijah Fontaine",
            "attendee_email": "elijah.fontaine@gmail.com",
            "attendee_phone": "+18432110111",
            "status": "completed",
        },
        {
            "title": "Initial Consultation — Priya Nair",
            "type_id": consultation_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "priya.nair@outlook.com",
            "loan_number": None,
            "meeting_type": "discovery_call",
            "meeting_mode": "phone",
            "start_offset": -3,
            "start_hour": 9,
            "duration": 30,
            "attendee_name": "Priya Nair",
            "attendee_email": "priya.nair@outlook.com",
            "attendee_phone": "+18432110102",
            "status": "completed",
        },
        {
            "title": "Team Sync — Weekly Pipeline Review",
            "type_id": team_sync_type_id,
            "user_id": manager_id,
            "lead_email": None,
            "loan_number": None,
            "meeting_type": "team_sync",
            "meeting_mode": "video",
            "start_offset": -2,
            "start_hour": 8,
            "duration": 30,
            "attendee_name": "Summit Home Loans Team",
            "attendee_email": "demo@perenniaai.com",
            "attendee_phone": None,
            "status": "completed",
        },
        # --- This week (confirmed) ---
        {
            "title": "Document Review — Tanya Morrison",
            "type_id": doc_review_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "tanya.morrison@gmail.com",
            "loan_number": "SHL-2026-0001",
            "meeting_type": "document_review",
            "meeting_mode": "video",
            "start_offset": 1,
            "start_hour": 10,
            "duration": 15,
            "attendee_name": "Tanya Morrison",
            "attendee_email": "tanya.morrison@gmail.com",
            "attendee_phone": "+18432110114",
            "status": "confirmed",
        },
        {
            "title": "Closing Prep — Simone Arceneaux",
            "type_id": closing_prep_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "simone.arceneaux@gmail.com",
            "loan_number": "SHL-2026-0010",
            "meeting_type": "closing_prep",
            "meeting_mode": "in_person",
            "start_offset": 2,
            "start_hour": 15,
            "duration": 60,
            "attendee_name": "Simone Arceneaux",
            "attendee_email": "simone.arceneaux@gmail.com",
            "attendee_phone": "+18432110108",
            "status": "confirmed",
        },
        {
            "title": "Initial Consultation — Derek Hollis",
            "type_id": consultation_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "derek.hollis@yahoo.com",
            "loan_number": None,
            "meeting_type": "discovery_call",
            "meeting_mode": "video",
            "start_offset": 2,
            "start_hour": 11,
            "duration": 30,
            "attendee_name": "Derek Hollis",
            "attendee_email": "derek.hollis@yahoo.com",
            "attendee_phone": "+18432110103",
            "status": "confirmed",
        },
        {
            "title": "Document Review — Roberto Sandoval",
            "type_id": doc_review_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "roberto.sandoval@hotmail.com",
            "loan_number": "SHL-2026-0002",
            "meeting_type": "document_review",
            "meeting_mode": "video",
            "start_offset": 3,
            "start_hour": 13,
            "duration": 15,
            "attendee_name": "Roberto Sandoval",
            "attendee_email": "roberto.sandoval@hotmail.com",
            "attendee_phone": "+18432110115",
            "status": "confirmed",
        },
        {
            "title": "Pre-Approval Review — Marcus Delacroix",
            "type_id": consultation_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "marcus.delacroix@icloud.com",
            "loan_number": "SHL-2026-0005",
            "meeting_type": "pre_approval_review",
            "meeting_mode": "video",
            "start_offset": 4,
            "start_hour": 10,
            "duration": 30,
            "attendee_name": "Marcus Delacroix",
            "attendee_email": "marcus.delacroix@icloud.com",
            "attendee_phone": "+18432110113",
            "status": "confirmed",
        },
        # --- Next 2 weeks (booked) ---
        {
            "title": "Initial Consultation — Brianna Okafor",
            "type_id": consultation_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "brianna.okafor@gmail.com",
            "loan_number": "SHL-2026-0008",
            "meeting_type": "discovery_call",
            "meeting_mode": "video",
            "start_offset": 6,
            "start_hour": 9,
            "duration": 30,
            "attendee_name": "Brianna Okafor",
            "attendee_email": "brianna.okafor@gmail.com",
            "attendee_phone": "+18432110106",
            "status": "booked",
        },
        {
            "title": "Closing Prep — Kevin Albright",
            "type_id": closing_prep_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "kevin.albright@gmail.com",
            "loan_number": "SHL-2026-0006",
            "meeting_type": "closing_prep",
            "meeting_mode": "in_person",
            "start_offset": 7,
            "start_hour": 14,
            "duration": 60,
            "attendee_name": "Kevin Albright",
            "attendee_email": "kevin.albright@gmail.com",
            "attendee_phone": "+18432110109",
            "status": "booked",
        },
        {
            "title": "Document Review — Aisha Coleman",
            "type_id": doc_review_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "aisha.coleman@gmail.com",
            "loan_number": "SHL-2026-0004",
            "meeting_type": "document_review",
            "meeting_mode": "video",
            "start_offset": 8,
            "start_hour": 11,
            "duration": 15,
            "attendee_name": "Aisha Coleman",
            "attendee_email": "aisha.coleman@gmail.com",
            "attendee_phone": "+18432110116",
            "status": "booked",
        },
        {
            "title": "Initial Consultation — Monique Duval",
            "type_id": consultation_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "monique.duval@gmail.com",
            "loan_number": None,
            "meeting_type": "discovery_call",
            "meeting_mode": "phone",
            "start_offset": 8,
            "start_hour": 15,
            "duration": 30,
            "attendee_name": "Monique Duval",
            "attendee_email": "monique.duval@gmail.com",
            "attendee_phone": "+18432110104",
            "status": "booked",
        },
        {
            "title": "Pre-Approval Review — Jasmine Winters",
            "type_id": consultation_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "jasmine.winters@yahoo.com",
            "loan_number": "SHL-2026-0007",
            "meeting_type": "pre_approval_review",
            "meeting_mode": "video",
            "start_offset": 9,
            "start_hour": 10,
            "duration": 30,
            "attendee_name": "Jasmine Winters",
            "attendee_email": "jasmine.winters@yahoo.com",
            "attendee_phone": "+18432110110",
            "status": "booked",
        },
        {
            "title": "Team Sync — Weekly Pipeline Review",
            "type_id": team_sync_type_id,
            "user_id": manager_id,
            "lead_email": None,
            "loan_number": None,
            "meeting_type": "team_sync",
            "meeting_mode": "video",
            "start_offset": 9,
            "start_hour": 8,
            "duration": 30,
            "attendee_name": "Summit Home Loans Team",
            "attendee_email": "demo@perenniaai.com",
            "attendee_phone": None,
            "status": "booked",
        },
        {
            "title": "Closing Prep — Brianna Okafor",
            "type_id": closing_prep_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "brianna.okafor@gmail.com",
            "loan_number": "SHL-2026-0008",
            "meeting_type": "closing_prep",
            "meeting_mode": "in_person",
            "start_offset": 11,
            "start_hour": 14,
            "duration": 60,
            "attendee_name": "Brianna Okafor",
            "attendee_email": "brianna.okafor@gmail.com",
            "attendee_phone": "+18432110106",
            "status": "booked",
        },
        {
            "title": "Initial Consultation — Carter Webb",
            "type_id": consultation_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "carter.webb@icloud.com",
            "loan_number": None,
            "meeting_type": "discovery_call",
            "meeting_mode": "phone",
            "start_offset": 12,
            "start_hour": 9,
            "duration": 30,
            "attendee_name": "Carter Webb",
            "attendee_email": "carter.webb@icloud.com",
            "attendee_phone": "+18432110105",
            "status": "booked",
        },
        {
            "title": "Document Review — Vanessa Hartley",
            "type_id": doc_review_type_id,
            "user_id": lo_sarah_id,
            "lead_email": "vanessa.hartley@gmail.com",
            "loan_number": "SHL-2026-0003",
            "meeting_type": "document_review",
            "meeting_mode": "video",
            "start_offset": 13,
            "start_hour": 11,
            "duration": 15,
            "attendee_name": "Vanessa Hartley",
            "attendee_email": "vanessa.hartley@gmail.com",
            "attendee_phone": "+18432110112",
            "status": "booked",
        },
        {
            "title": "Rate Lock Discussion — Marcus Delacroix",
            "type_id": consultation_type_id,
            "user_id": lo_marcus_id,
            "lead_email": "marcus.delacroix@icloud.com",
            "loan_number": "SHL-2026-0005",
            "meeting_type": "rate_lock_discussion",
            "meeting_mode": "phone",
            "start_offset": 14,
            "start_hour": 13,
            "duration": 30,
            "attendee_name": "Marcus Delacroix",
            "attendee_email": "marcus.delacroix@icloud.com",
            "attendee_phone": "+18432110113",
            "status": "booked",
        },
    ]

    appt_inserted = 0
    appt_skipped = 0
    for appt in APPOINTMENTS:
        # Check by title + approximate start day (avoid dupe on re-run)
        start_dt = days_from_now(appt["start_offset"]).replace(
            hour=appt["start_hour"], minute=0, second=0, microsecond=0
        )
        existing = conn.execute(
            text("""
                SELECT id FROM scheduler_appointments
                WHERE organization_id = :org_id
                  AND title = :title
                  AND DATE(scheduled_start) = DATE(:start_dt)
                LIMIT 1
            """),
            {"org_id": org_id, "title": appt["title"], "start_dt": start_dt},
        ).fetchone()
        if existing:
            appt_skipped += 1
            continue

        lead_id = lead_ids.get(appt["lead_email"]) if appt["lead_email"] else None
        loan_id = None
        if appt["loan_number"]:
            loan_id = get_id(conn, "loans", "loan_number", appt["loan_number"])

        end_dt = start_dt + timedelta(minutes=appt["duration"])
        completed_at = end_dt if appt["status"] == "completed" else None

        conn.execute(
            text("""
                INSERT INTO scheduler_appointments
                    (organization_id, appointment_type_id, assigned_user_id,
                     lead_id, loan_id, title, meeting_type, meeting_mode,
                     scheduled_start, scheduled_end, duration_minutes, timezone,
                     attendee_name, attendee_email, attendee_phone,
                     status, completed_at, created_at, updated_at)
                VALUES
                    (:org_id, :type_id, :user_id,
                     :lead_id, :loan_id, :title, :meeting_type, :meeting_mode,
                     :start_dt, :end_dt, :duration, :tz,
                     :attendee_name, :attendee_email, :attendee_phone,
                     :status, :completed_at, :now, :now)
            """),
            {
                "org_id": org_id,
                "type_id": appt["type_id"],
                "user_id": appt["user_id"],
                "lead_id": lead_id,
                "loan_id": loan_id,
                "title": appt["title"],
                "meeting_type": appt["meeting_type"],
                "meeting_mode": appt["meeting_mode"],
                "start_dt": start_dt,
                "end_dt": end_dt,
                "duration": appt["duration"],
                "tz": "America/New_York",
                "attendee_name": appt["attendee_name"],
                "attendee_email": appt["attendee_email"],
                "attendee_phone": appt["attendee_phone"],
                "status": appt["status"],
                "completed_at": completed_at,
                "now": NOW,
            },
        )
        appt_inserted += 1

    conn.commit()
    print(f"✅ Seeded {appt_inserted} appointments ({appt_skipped} already existed)")


def seed_sms_conversations(conn, org_id, user_ids, lead_ids):
    """Create demo SMS conversation threads (10 threads with 3-8 messages each)."""

    TELNYX_NUMBER = "+18438838956"

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # Conversation definitions: each entry maps to one lead
    # lead_email, assigned LO, category, messages (list of dicts)
    CONVERSATIONS = [
        # --- Scheduling (3 threads) ---
        {
            "lead_email": "derek.hollis@yahoo.com",
            "lead_phone": "+18432110103",
            "lead_name": "Derek Hollis",
            "user_id": lo_sarah_id,
            "days_ago_start": 2,
            "messages": [
                {"dir": "inbound",  "text": "Hi! This is Derek Hollis. I filled out a form on your website — I'm interested in getting pre-approved.",  "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Derek! Great to hear from you. I'm Sarah Chen, your loan officer at Summit Home Loans. I'd love to schedule a quick 30-minute discovery call. Are you available Thursday?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Thursday works for me. What time?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "How about 11 AM Eastern? I can send a Zoom link.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Perfect. See you then!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Appointment confirmed for Thursday at 11 AM. You'll receive a calendar invite shortly. Looking forward to it!", "ai": True, "offset_hours": 3},
            ],
        },
        {
            "lead_email": "carter.webb@icloud.com",
            "lead_phone": "+18432110105",
            "lead_name": "Carter Webb",
            "user_id": lo_sarah_id,
            "days_ago_start": 5,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, I saw your listing on Zillow. I'm curious about rates right now.", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Carter! Happy to help. 30-year fixed is running around 6.875% today for well-qualified buyers. Would you like to hop on a quick call to see what you'd qualify for?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "That sounds good. Can we do a call Friday morning?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Friday morning works great. I have 9 AM open. Shall I book that?", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Yes please!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Done! I've booked Friday at 9 AM. I'll send you a few questions to review beforehand so we can make the most of our time.", "ai": True, "offset_hours": 4},
                {"dir": "inbound",  "text": "Sounds great, thanks!", "ai": False, "offset_hours": 5},
            ],
        },
        {
            "lead_email": "monique.duval@gmail.com",
            "lead_phone": "+18432110104",
            "lead_name": "Monique Duval",
            "user_id": lo_marcus_id,
            "days_ago_start": 3,
            "messages": [
                {"dir": "outbound", "text": "Hi Monique, this is Aria from Summit Home Loans following up on your Realtor.com inquiry. Are you available for a quick 15-minute call this week?", "ai": True, "offset_hours": 0},
                {"dir": "inbound",  "text": "Sorry, been really busy. Can we do next week?", "ai": False, "offset_hours": 4},
                {"dir": "outbound", "text": "No problem at all! I have Monday at 2 PM or Tuesday at 10 AM open. Which works better?", "ai": True, "offset_hours": 4},
                {"dir": "inbound",  "text": "Monday at 2 works.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Perfect! Booked for Monday at 2 PM. Marcus Johnson will be on the call — he specializes in FHA programs and can walk you through your options.", "ai": True, "offset_hours": 5},
            ],
        },
        # --- Document requests (2 threads) ---
        {
            "lead_email": "tanya.morrison@gmail.com",
            "lead_phone": "+18432110114",
            "lead_name": "Tanya Morrison",
            "user_id": lo_sarah_id,
            "days_ago_start": 4,
            "messages": [
                {"dir": "outbound", "text": "Hi Tanya, Sarah here. Your loan application is looking great! I just need your 2022 tax returns to complete the file. Can you upload them to your borrower portal?", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "I don't have digital copies. Can I bring them in?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Of course! You can scan them with your phone camera in the portal app — it works really well. Or drop by the office any time. We're at 123 Meeting St.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Just uploaded them through the app. Did you get them?", "ai": False, "offset_hours": 6},
                {"dir": "outbound", "text": "Got them! I can see both 2021 and 2022 returns uploaded successfully. I'll have Emily start processing right away. You're on track for your closing date!", "ai": True, "offset_hours": 6},
            ],
        },
        {
            "lead_email": "roberto.sandoval@hotmail.com",
            "lead_phone": "+18432110115",
            "lead_name": "Roberto Sandoval",
            "user_id": lo_marcus_id,
            "days_ago_start": 6,
            "messages": [
                {"dir": "outbound", "text": "Hi Roberto, Marcus here. We're moving along nicely on your FHA loan. The appraiser needs access to the property next Tuesday — can you confirm with the listing agent?", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "Done, agent says Tuesday between 10-12 works.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Perfect, I'll get the appraiser scheduled. Also, can you send your latest pay stub? We need the most current one in the file.", "ai": True, "offset_hours": 3},
                {"dir": "inbound",  "text": "Just sent it via email.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Got it, thank you! Everything looks on track. I'll update you after the appraisal comes back.", "ai": True, "offset_hours": 6},
                {"dir": "inbound",  "text": "Appreciate it. This is exciting!", "ai": False, "offset_hours": 7},
            ],
        },
        # --- Status updates (2 threads) ---
        {
            "lead_email": "kevin.albright@gmail.com",
            "lead_phone": "+18432110109",
            "lead_name": "Kevin Albright",
            "user_id": lo_marcus_id,
            "days_ago_start": 7,
            "messages": [
                {"dir": "outbound", "text": "Hi Kevin! Great news — your loan has been submitted to underwriting. This stage typically takes 5-7 business days.", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "That's awesome! How long does underwriting usually take?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "For conventional loans like yours, usually 5-7 business days. Your file looks clean so we're optimistic. I'll text you as soon as we hear back.", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Thanks! The seller is getting anxious about the timeline.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Totally understandable. You're on track — your closing date isn't at risk. If the seller needs a letter of assurance, I can provide that today.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Yes please, that would help a lot!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Done! Just emailed you and the listing agent a status letter. You're in great shape, Kevin.", "ai": True, "offset_hours": 3},
            ],
        },
        {
            "lead_email": "brianna.okafor@gmail.com",
            "lead_phone": "+18432110106",
            "lead_name": "Brianna Okafor",
            "user_id": lo_sarah_id,
            "days_ago_start": 2,
            "messages": [
                {"dir": "outbound", "text": "Hi Brianna! Excellent news — you've received a Conditional Approval. We just need two items: letter of explanation for the gap in employment (2022) and one more month of bank statements.", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "Great news! What's a letter of explanation?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "It's just a brief note explaining what happened — for example, 'I was between jobs for 3 months while relocating from Atlanta.' A few sentences is all we need. Want me to send a template?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Yes please, that would be super helpful.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Template sent to your email! Once you upload both items to the portal, Emily will have them reviewed within 24 hours and you'll be Clear to Close.", "ai": True, "offset_hours": 2},
            ],
        },
        # --- Rate inquiries (2 threads) ---
        {
            "lead_email": "simone.arceneaux@gmail.com",
            "lead_phone": "+18432110108",
            "lead_name": "Simone Arceneaux",
            "user_id": lo_sarah_id,
            "days_ago_start": 1,
            "messages": [
                {"dir": "inbound",  "text": "Hi, what are rates looking like today? My closing is in 2 days.", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Simone! Great timing. 30-year conventional is at 6.500% today for your loan profile — that's an excellent rate. You're already locked, so you're good. Want to confirm your final numbers?", "ai": True, "offset_hours": 0},
                {"dir": "inbound",  "text": "Yes! What's my final monthly payment?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "Your principal and interest is $3,003/month. Add taxes and insurance and your total PITI is approximately $3,580/month. The CD with exact figures will be sent 3 days before closing.", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Perfect. I'm so excited! See you at closing.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "We're excited for you too, Simone! See you Thursday. Don't forget to bring your photo ID and a cashier's check for $76,420 (closing costs + down payment).", "ai": False, "offset_hours": 2},
            ],
        },
        {
            "lead_email": "jasmine.winters@yahoo.com",
            "lead_phone": "+18432110110",
            "lead_name": "Jasmine Winters",
            "user_id": lo_sarah_id,
            "days_ago_start": 8,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, rates have been moving a lot. Should I lock in now?", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Jasmine! Great question. Today's rate for your loan is 6.875%. The 30-day trend is flat-to-slightly-higher. Your float window closes in 18 days. I'd recommend locking now — want me to start the lock process?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Will rates drop before my closing?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Rates could move either direction — nobody knows for sure. What I can tell you is that 6.875% is a solid rate historically, and locking protects you from upside risk. Floating is a gamble. The peace of mind is worth it.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "OK let's lock it in.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Rate locked at 6.875% for 30 days! I'll send the lock confirmation email now. You're protected through your closing date.", "ai": True, "offset_hours": 3},
            ],
        },
        # --- General (1 thread) ---
        {
            "lead_email": "michelle.osei@gmail.com",
            "lead_phone": "+18432110122",
            "lead_name": "Michelle Osei",
            "user_id": lo_sarah_id,
            "days_ago_start": 10,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, just wanted to say thank you for everything. The closing went so smoothly!", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Michelle, congratulations!! 🎉 It was such a pleasure working with you. Enjoy your new home — you deserve it!", "ai": False, "offset_hours": 1},
                {"dir": "inbound",  "text": "We love it already. Do you happen to have any referrals for a good contractor?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "I know a few great ones in Charleston! I'll send you my preferred vendor list. Also, if you know anyone looking to buy, I'd love an introduction — referrals mean the world to us.", "ai": False, "offset_hours": 2},
                {"dir": "inbound",  "text": "Of course! My neighbor is actually looking right now. I'll have them reach out.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "That's wonderful, thank you so much Michelle! I'll reach out to them right away. Have fun in the new home!", "ai": False, "offset_hours": 4},
                {"dir": "inbound",  "text": "Thanks Sarah! Reach out anytime.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Will do! Enjoy every minute. 🏠", "ai": False, "offset_hours": 6},
            ],
        },
    ]

    conv_inserted = 0
    conv_skipped = 0
    msg_inserted = 0

    for convo in CONVERSATIONS:
        lead_id = lead_ids.get(convo["lead_email"])

        # Check if conversation already exists for this lead
        existing_conv = conn.execute(
            text("""
                SELECT id FROM sms_conversations
                WHERE organization_id = :org_id
                  AND phone_number = :phone
                LIMIT 1
            """),
            {"org_id": org_id, "phone": convo["lead_phone"]},
        ).fetchone()

        if existing_conv:
            conv_skipped += 1
            continue

        # Timestamps for conversation
        conv_start = days_ago(convo["days_ago_start"])
        last_msg_offset = max(m["offset_hours"] for m in convo["messages"])
        last_msg_at = conv_start + timedelta(hours=last_msg_offset)

        # Insert conversation
        result = conn.execute(
            text("""
                INSERT INTO sms_conversations
                    (organization_id, phone_number, user_id, lead_id,
                     contact_name, is_active, ai_enabled,
                     last_message_at, message_count, created_at, updated_at)
                VALUES
                    (:org_id, :phone, :user_id, :lead_id,
                     :contact_name, :is_active, :ai_enabled,
                     :last_msg_at, :msg_count, :now, :now)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "phone": convo["lead_phone"],
                "user_id": convo["user_id"],
                "lead_id": lead_id,
                "contact_name": convo["lead_name"],
                "is_active": True,
                "ai_enabled": True,
                "last_msg_at": last_msg_at,
                "msg_count": len(convo["messages"]),
                "now": conv_start,
            },
        )
        conv_id = result.fetchone()[0]
        conv_inserted += 1

        # Insert messages
        for i, msg in enumerate(convo["messages"]):
            msg_at = conv_start + timedelta(hours=msg["offset_hours"])
            from_num = convo["lead_phone"] if msg["dir"] == "inbound" else TELNYX_NUMBER
            to_num = TELNYX_NUMBER if msg["dir"] == "inbound" else convo["lead_phone"]
            status = "read" if msg["dir"] == "inbound" else "delivered"

            conn.execute(
                text("""
                    INSERT INTO sms_messages
                        (organization_id, user_id, lead_id, conversation_id,
                         to_number, from_number, message, direction, status,
                         ai_generated, delivery_status, created_at)
                    VALUES
                        (:org_id, :user_id, :lead_id, :conv_id,
                         :to_num, :from_num, :message, :direction, :status,
                         :ai_gen, :delivery_status, :created_at)
                """),
                {
                    "org_id": org_id,
                    "user_id": convo["user_id"],
                    "lead_id": lead_id,
                    "conv_id": conv_id,
                    "to_num": to_num,
                    "from_num": from_num,
                    "message": msg["text"],
                    "direction": msg["dir"],
                    "status": status,
                    "ai_gen": msg["ai"],
                    "delivery_status": "delivered" if msg["dir"] == "outbound" else "received",
                    "created_at": msg_at,
                },
            )
            msg_inserted += 1

    conn.commit()
    print(f"✅ Seeded {conv_inserted} SMS conversations, {msg_inserted} messages ({conv_skipped} conversations already existed)")


def seed_call_intelligence(conn, org_id, user_ids, lead_ids):
    """Create demo VapiCall records with AI analysis (8 calls)."""

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    manager_id = user_ids.get("manager")

    CALLS = [
        # --- Inbound (AI receptionist) ---
        {
            "vapi_call_id": "demo-call-001",
            "phone_number": "+18432110103",
            "caller_name": "Derek Hollis",
            "direction": "inbound",
            "days_ago": 6,
            "hour": 10,
            "duration": 247,
            "lead_email": "derek.hollis@yahoo.com",
            "sentiment": "positive",
            "intent": "inquiry",
            "ci_extractions_count": 4,
            "ci_tasks_created": 2,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria, your AI assistant. How can I help you today?\n"
                "Caller: Hi, my name is Derek Hollis. I'm looking to get pre-approved for a home purchase.\n"
                "Aria: Wonderful, Derek! Congratulations on taking that step. I'd love to help. Are you looking to buy in the Charleston area?\n"
                "Caller: Yes, primarily around the historic district. We have our eye on a few properties in the $550,000 range.\n"
                "Aria: That's a beautiful area! Just to get a general sense — do you have an idea of your credit score range and annual household income?\n"
                "Caller: My score is around 760 and I make about $145,000 a year.\n"
                "Aria: You sound like an excellent candidate for a conventional loan! I'd love to connect you with Sarah Chen, one of our senior loan officers. She has deep experience with high-end Charleston properties. Are you available for a 30-minute call later this week?\n"
                "Caller: Thursday morning works for me.\n"
                "Aria: Perfect! I'm booking you with Sarah on Thursday at 11 AM. You'll receive a confirmation text and calendar invite shortly.\n"
                "Caller: Great, thanks!\n"
                "Aria: My pleasure, Derek. Is there anything else I can help with today?\n"
                "Caller: No, that's all. Thanks so much.\n"
                "Aria: You're welcome! We look forward to helping you find your dream home. Have a wonderful day!"
            ),
            "summary": (
                "Inbound inquiry from Derek Hollis, a high-credit (760) buyer with $145K income seeking pre-approval for a $550K purchase "
                "in Charleston's historic district. AI receptionist Aria captured key qualification data and booked a consultation with "
                "Sarah Chen for Thursday at 11 AM. Task created: follow up with pre-approval checklist and income doc request."
            ),
        },
        {
            "vapi_call_id": "demo-call-002",
            "phone_number": "+18432110109",
            "caller_name": "Kevin Albright",
            "direction": "inbound",
            "days_ago": 4,
            "hour": 14,
            "duration": 183,
            "lead_email": "kevin.albright@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 1,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria. How can I assist you?\n"
                "Caller: Hi, I'm Kevin Albright. I wanted to check on the status of my loan — it's with Marcus Johnson.\n"
                "Aria: Hi Kevin! Let me pull up your file. Your loan SHL-2026-0006 is currently in Underwriting. It was submitted 7 days ago.\n"
                "Caller: How long does underwriting usually take?\n"
                "Aria: For a conventional loan with a strong profile like yours, typically 5-7 business days. You're right on track.\n"
                "Caller: Any conditions yet?\n"
                "Aria: No conditions have been flagged as of today. Marcus will call you as soon as the underwriter's decision comes in.\n"
                "Caller: OK great. I also wanted to ask about bringing my brother as a co-borrower. Is it too late?\n"
                "Aria: That's a great question — it could affect the timeline. I'm going to flag this for Marcus and have him call you back today. Is your cell phone the best number?\n"
                "Caller: Yes, same number I'm calling from.\n"
                "Aria: Perfect. I've sent Marcus a priority message. Anything else I can help with?\n"
                "Caller: No, that's it. Thanks!\n"
                "Aria: My pleasure! Have a great afternoon, Kevin."
            ),
            "summary": (
                "Kevin Albright called to check on his underwriting status for loan SHL-2026-0006. AI confirmed loan is in underwriting "
                "with no conditions flagged at day 7. Kevin raised a potential co-borrower addition (his brother) — a time-sensitive "
                "question that could affect the loan structure. AI created a priority task for Marcus Johnson to call back same day."
            ),
        },
        {
            "vapi_call_id": "demo-call-003",
            "phone_number": "+18432110116",
            "caller_name": "Aisha Coleman",
            "direction": "inbound",
            "days_ago": 2,
            "hour": 11,
            "duration": 312,
            "lead_email": "aisha.coleman@gmail.com",
            "sentiment": "positive",
            "intent": "inquiry",
            "ci_extractions_count": 5,
            "ci_tasks_created": 3,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria. How can I help?\n"
                "Caller: Hi, I'm Aisha Coleman. I'm under contract on a new construction home and I wanted to know about rate lock options.\n"
                "Aria: Hi Aisha! Congratulations on being under contract! New construction rate locks work a bit differently. How far out is your projected closing?\n"
                "Caller: The builder says 60 days, but it could be 45.\n"
                "Aria: Got it. For that window, you'd typically want a 60-day lock, which is available but carries a slight premium over a standard 30-day lock. Current rates for your loan type are around 6.875% on a 60-day lock.\n"
                "Caller: What about a float-to-lock option? My builder mentioned that.\n"
                "Aria: Great question! A float-down lock lets you start locked in and drop if rates fall by a certain threshold — usually 0.25%. I want to make sure Sarah gives you accurate numbers on that. Want me to schedule a call?\n"
                "Caller: Yes, please.\n"
                "Aria: I'll book Sarah for tomorrow at 2 PM to walk you through all rate lock options. I'll also send you a rate lock comparison document tonight.\n"
                "Caller: Also, the builder is asking for a copy of my pre-approval letter. Can you resend it?\n"
                "Aria: Absolutely. I'll have Sarah email the updated letter to you within the hour.\n"
                "Caller: Perfect. You've been so helpful!\n"
                "Aria: My pleasure, Aisha! Looking forward to getting you to the closing table."
            ),
            "summary": (
                "Aisha Coleman called with questions about rate lock options for her new construction purchase (60-day projected close). "
                "She asked about float-to-lock options and requested a pre-approval letter resend. AI scheduled a rate lock strategy call "
                "with Sarah for tomorrow at 2 PM, created tasks for: rate lock comparison doc, pre-approval letter resend, and follow-up "
                "after builder confirms closing window."
            ),
        },
        # --- Outbound (LO follow-up) ---
        {
            "vapi_call_id": "demo-call-004",
            "phone_number": "+18432110106",
            "caller_name": "Brianna Okafor",
            "direction": "outbound",
            "days_ago": 3,
            "hour": 10,
            "duration": 268,
            "lead_email": "brianna.okafor@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 2,
            "transcript": (
                "Sarah Chen: Hi Brianna, this is Sarah Chen from Summit Home Loans. Is now a good time?\n"
                "Brianna: Yes! I was just going to call you.\n"
                "Sarah Chen: Great minds! I'm calling because your loan received a Conditional Approval from underwriting — congratulations!\n"
                "Brianna: Oh wow, that's amazing news!\n"
                "Sarah Chen: It really is. We just need two items to get to Clear to Close: a letter of explanation for your 2022 employment gap, and one more month of bank statements.\n"
                "Brianna: How long of a letter?\n"
                "Sarah Chen: Just a few sentences. I'll send you a template that takes about 5 minutes to fill out.\n"
                "Brianna: That's easy. And the bank statement — which account?\n"
                "Sarah Chen: Your Chase checking account ending in 4821. Just the most recent statement.\n"
                "Brianna: I can have both to you by tomorrow.\n"
                "Sarah Chen: That would be perfect! With that turnaround, you'll likely have your CTC in 3-4 days and we can target your original closing date.\n"
                "Brianna: You have no idea how relieved I am. I've been so nervous about this.\n"
                "Sarah Chen: This is completely normal — you're in great shape. I'll send that template right now and text you a reminder tomorrow morning.\n"
                "Brianna: Thank you so much, Sarah. You're the best!\n"
                "Sarah Chen: You're going to be in your new home before you know it. Talk soon!"
            ),
            "summary": (
                "Sarah Chen called Brianna Okafor to deliver Conditional Approval news. Conditions are: letter of explanation for 2022 "
                "employment gap and one month of Chase checking statements (account ending 4821). Brianna committed to providing both "
                "by tomorrow. Tasks created: send letter of explanation template to Brianna, set follow-up reminder for tomorrow morning. "
                "Closing timeline remains on track."
            ),
        },
        {
            "vapi_call_id": "demo-call-005",
            "phone_number": "+18432110107",
            "caller_name": "Nathan Prescott",
            "direction": "outbound",
            "days_ago": 10,
            "hour": 13,
            "duration": 195,
            "lead_email": "nathan.prescott@hotmail.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 2,
            "ci_tasks_created": 1,
            "transcript": (
                "Marcus Johnson: Hi Nathan, this is Marcus Johnson from Summit Home Loans. How are you doing?\n"
                "Nathan: Good, thanks.\n"
                "Marcus Johnson: I wanted to follow up on your pre-qualification — it's been about 3 weeks and I wanted to check in on your property search.\n"
                "Nathan: Yeah, we've seen a few condos but nothing's clicked yet. The HOA fees are killing the DTI.\n"
                "Marcus Johnson: That's a really common concern with FHA condo loans. The good news is HOA fees are actually factored into the debt-to-income calculation up front, so there are no surprises. Have you seen any that felt close?\n"
                "Nathan: There's one on Rivers Ave at $279,000. HOA is $240 a month.\n"
                "Marcus Johnson: Let me run those numbers real quick... At your income level with FHA, a $279K price and $240 HOA gets you to about 44% DTI — that's right at the FHA threshold. It's workable, especially if you can get seller concessions on closing costs.\n"
                "Nathan: Interesting. How fast could you get a pre-approval letter if we wanted to make an offer?\n"
                "Marcus Johnson: I can have a property-specific letter to you within 2 hours of you saying go. Want to schedule a quick call when you're ready to move forward?\n"
                "Nathan: Yeah, I'll call you when we decide.\n"
                "Marcus Johnson: Perfect. I'll send you a breakdown on that specific property by email today. Good talking to you, Nathan."
            ),
            "summary": (
                "Marcus Johnson followed up with Nathan Prescott who has been actively touring FHA-eligible condos. Nathan identified a "
                "specific property at $279K with $240/month HOA — Marcus calculated a 44% DTI which is at the FHA limit but workable "
                "with seller concessions. Task created: send property-specific DTI analysis email for the Rivers Ave unit. Nathan will "
                "call when ready to make an offer."
            ),
        },
        {
            "vapi_call_id": "demo-call-006",
            "phone_number": "+18432110114",
            "caller_name": "Tanya Morrison",
            "direction": "outbound",
            "days_ago": 5,
            "hour": 15,
            "duration": 221,
            "lead_email": "tanya.morrison@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 2,
            "transcript": (
                "Sarah Chen: Hi Tanya! Sarah Chen here. Got a minute?\n"
                "Tanya: Of course! I was hoping you'd call.\n"
                "Sarah Chen: I wanted to let you know that Emily has started processing your file. Everything looks really solid. The one item we're still waiting on is your 2022 tax returns.\n"
                "Tanya: I know, I know. I keep forgetting to pull them. Can I get them from the IRS directly?\n"
                "Sarah Chen: Yes, the fastest way is the IRS Get Transcript portal — it takes about 10 minutes and you can download a PDF. I'll text you the link right now.\n"
                "Tanya: Perfect. I'll do it tonight.\n"
                "Sarah Chen: Wonderful! Once we have that, Emily can complete processing and submit to underwriting. That keeps you on track for your 55-day close.\n"
                "Tanya: I'm actually getting nervous — this is my first house!\n"
                "Sarah Chen: That's so exciting! First-time buyer nerves are totally normal. I'm with you every step of the way. The hard part is behind you.\n"
                "Tanya: Thank you, Sarah. You've been so helpful.\n"
                "Sarah Chen: My job is to make this easy for you! I'll text the IRS link now. Call me if you have any questions tonight.\n"
                "Tanya: Will do. Talk soon!"
            ),
            "summary": (
                "Sarah Chen followed up with first-time buyer Tanya Morrison regarding missing 2022 tax returns blocking processing. "
                "Tanya agreed to retrieve them tonight via IRS Get Transcript portal. Sarah committed to texting the IRS portal link "
                "immediately. Tasks created: send IRS transcript link via SMS, check-in tomorrow if returns not received. File on "
                "track for 55-day close pending this single document."
            ),
        },
        # --- Voicemail drops (outbound, short) ---
        {
            "vapi_call_id": "demo-call-007",
            "phone_number": "+18432110117",
            "caller_name": "Gregory Tatum",
            "direction": "outbound",
            "days_ago": 14,
            "hour": 10,
            "duration": 28,
            "lead_email": "gregory.tatum@yahoo.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 0,
            "ci_tasks_created": 1,
            "transcript": (
                "[Voicemail Drop]\n"
                "Hi Gregory, this is Marcus Johnson from Summit Home Loans. I wanted to check in and see how your savings plan is going. "
                "Last time we spoke you were targeting spring for your purchase — that window is coming up fast! "
                "Give me a call at your convenience and let's see if we can get a game plan together. "
                "My number is 843-100-5003. Have a great day!"
            ),
            "summary": (
                "Voicemail drop to Gregory Tatum, a long-term nurture lead who is saving for a down payment with a spring purchase target. "
                "Call duration indicates message went to voicemail as intended. Task created: follow-up SMS in 3 days if no callback."
            ),
        },
        {
            "vapi_call_id": "demo-call-008",
            "phone_number": "+18432110118",
            "caller_name": "Courtney Langford",
            "direction": "outbound",
            "days_ago": 20,
            "hour": 11,
            "duration": 31,
            "lead_email": "courtney.langford@gmail.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 0,
            "ci_tasks_created": 1,
            "transcript": (
                "[Voicemail Drop]\n"
                "Hi Courtney, this is Sarah Chen from Summit Home Loans. I'm reaching out because your lease renewal is coming up and I wanted "
                "to see where you are on the credit improvement plan we discussed. If your score has crossed 640, we may be able to get you "
                "pre-qualified sooner than expected! Give me a call at 843-100-5002 and let's take a look. Looking forward to hearing from you!"
            ),
            "summary": (
                "Voicemail drop to Courtney Langford, a credit repair lead with a lease ending in approximately 9 months. Sarah prompted "
                "Courtney to check in on her credit score progress — a 640 threshold would enable pre-qualification. Short duration "
                "confirms voicemail delivery. Task created: re-attempt call in 2 weeks if no response."
            ),
        },
    ]

    inserted = 0
    skipped = 0

    for call in CALLS:
        if exists(conn, "vapi_calls", "vapi_call_id", call["vapi_call_id"]):
            skipped += 1
            continue

        lead_id = lead_ids.get(call["lead_email"])
        started_at = days_ago(call["days_ago"]).replace(
            hour=call["hour"], minute=0, second=0, microsecond=0
        )
        ended_at = started_at + timedelta(seconds=call["duration"])

        conn.execute(
            text("""
                INSERT INTO vapi_calls
                    (organization_id, vapi_call_id, phone_number, caller_name,
                     direction, status, started_at, ended_at, duration,
                     transcript, summary, sentiment, intent,
                     lead_id, ci_processed, ci_extractions_count, ci_tasks_created,
                     created_at, updated_at)
                VALUES
                    (:org_id, :vapi_call_id, :phone, :caller_name,
                     :direction, :status, :started_at, :ended_at, :duration,
                     :transcript, :summary, :sentiment, :intent,
                     :lead_id, :ci_processed, :ci_extractions, :ci_tasks,
                     :now, :now)
            """),
            {
                "org_id": org_id,
                "vapi_call_id": call["vapi_call_id"],
                "phone": call["phone_number"],
                "caller_name": call["caller_name"],
                "direction": call["direction"],
                "status": "completed",
                "started_at": started_at,
                "ended_at": ended_at,
                "duration": call["duration"],
                "transcript": call["transcript"],
                "summary": call["summary"],
                "sentiment": call["sentiment"],
                "intent": call["intent"],
                "lead_id": lead_id,
                "ci_processed": True,
                "ci_extractions": call["ci_extractions_count"],
                "ci_tasks": call["ci_tasks_created"],
                "now": NOW,
            },
        )
        inserted += 1

    conn.commit()
    print(f"✅ Seeded {inserted} call intelligence records ({skipped} already existed)")


def seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create activity log entries and stage history for leads and loans."""

    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    processor_id = user_ids.get("processor")
    uw_rachel_id = user_ids.get("uw_rachel")
    uw_james_id = user_ids.get("uw_james")

    # ------------------------------------------------------------------
    # Lead activity specs
    # (email, stage, days_ago, owner_id, activities list)
    # activities: list of (type, content, offset_days_from_created, duration, sentiment)
    # ------------------------------------------------------------------
    LEAD_ACTIVITIES = [
        # --- NEW leads (1-2 activities each) ---
        {
            "email": "tyler.barnes@gmail.com",
            "stage": "New",
            "days_ago": 2,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",  "Inbound inquiry from Zillow — discussed purchase timeline and rate expectations. Left message about pre-approval process.", 0, "12 min", "neutral"),
                ("Note",  "First-time buyer previously pre-qualified with another lender. Wants rate comparison. AI score 72. Follow up with discovery call.", 0, None, "neutral"),
            ],
        },
        {
            "email": "priya.nair@outlook.com",
            "stage": "New",
            "days_ago": 5,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",  "Initial call — responded to Facebook FHA ad. Asking about minimum down payment requirements. Confirmed 3.5% FHA option.", 0, "8 min", "positive"),
                ("Email", "Sent FHA program overview PDF with down payment breakdown and credit score requirements.", 1, None, "positive"),
            ],
        },
        {
            "email": "derek.hollis@yahoo.com",
            "stage": "New",
            "days_ago": 1,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Note",  "High-priority website lead (AI score 88). Relocating for work from Atlanta. Used rate calculator — strong purchase intent. Schedule discovery call today.", 0, None, "positive"),
                ("SMS",   "Hi Derek — this is Sarah Chen at Summit Home Loans. I saw your inquiry on our website. I'd love to walk you through your options. When works for a quick call?", 0, None, "positive"),
            ],
        },
        # --- ATTEMPTED CONTACT leads (2-3 activities) ---
        {
            "email": "monique.duval@gmail.com",
            "stage": "Attempted Contact",
            "days_ago": 8,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",  "Left voicemail #1 — introduced Summit Home Loans and FHA programs. No callback.", 0, "2 min", "neutral"),
                ("Call",  "Left voicemail #2 — referenced Realtor.com listing inquiry. Offered free pre-qualification.", 2, "2 min", "neutral"),
                ("SMS",   "Hi Monique — Marcus Johnson from Summit Home Loans. Reaching out re: the home on Ashley Ave. Happy to help with financing. Reply to connect!", 3, None, "neutral"),
            ],
        },
        {
            "email": "carter.webb@icloud.com",
            "stage": "Attempted Contact",
            "days_ago": 11,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",  "Cold outreach from expired listing database — Carter showed interest in rate info but hasn't scheduled a call yet.", 0, "5 min", "neutral"),
                ("Call",  "Follow-up call — no answer. Left voicemail referencing our pre-approval process.", 3, "2 min", "neutral"),
                ("Email", "Sent calendar link for 15-min discovery call. Subject: 'Get Your Rate — 5 Minutes, No Obligation'.", 4, None, "neutral"),
            ],
        },
        # --- PROSPECT leads (3-5 activities) ---
        {
            "email": "brianna.okafor@gmail.com",
            "stage": "Prospect",
            "days_ago": 18,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Initial contact — referral from Jean Holloway at RE/MAX. Warm introduction. Discussed purchase goals and 60-day timeline.", 0, "18 min", "positive"),
                ("Email",  "Sent pre-approval checklist with income document requirements and credit score guidance.", 2, None, "positive"),
                ("Meeting","Discovery Zoom call — reviewed income ($112K), assets, and purchase target ($390K–$445K). Excellent profile for conventional 10% down.", 4, "28 min", "positive"),
                ("Note",   "Referred by realtor partner Jean Holloway. High-quality lead — ready to move. Begin pre-qual process.", 4, None, "positive"),
            ],
        },
        {
            "email": "nathan.prescott@hotmail.com",
            "stage": "Prospect",
            "days_ago": 22,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Initial Zillow lead call — browsing condos in North Charleston. Concerned about HOA impact on DTI.", 0, "14 min", "neutral"),
                ("Email",  "Sent FHA condo approval process guide and HOA add-back explanation.", 2, None, "neutral"),
                ("Call",   "Follow-up call — discussed condo HOA dues and impact on qualifying payment. Nathan still researching communities.", 5, "11 min", "neutral"),
            ],
        },
        {
            "email": "simone.arceneaux@gmail.com",
            "stage": "Prospect",
            "days_ago": 27,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Website lead — executive relocating from Atlanta. Currently has credit union pre-approval at 7.1%. Wants rate comparison.", 0, "22 min", "positive"),
                ("Email",  "Sent side-by-side rate comparison analysis vs credit union offer. Summit savings: ~$87/month at 6.500%.", 2, None, "positive"),
                ("Meeting","Rate strategy call — walked through conventional 30yr fixed at 6.500% vs ARM options. Simone prefers fixed.", 4, "35 min", "positive"),
                ("Note",   "High-value prospect — $475K loan target, relocating for senior exec role. Closing within 45 days. Rate lock ready.", 5, None, "positive"),
            ],
        },
        # --- PRE-QUALIFIED leads (3-5 activities) ---
        {
            "email": "kevin.albright@gmail.com",
            "stage": "Pre-Qualified",
            "days_ago": 38,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral introduction from realtor partner. Kevin searching for single-family in Park Circle area.", 0, "16 min", "positive"),
                ("Email",  "Sent income doc checklist — W-2, paystubs, bank statements requested.", 3, None, "positive"),
                ("Document","Received 2024 W-2, two recent paystubs, and 90-day bank statements. All documents complete.", 7, None, "positive"),
                ("Meeting","Pre-qualification review call — $335K pre-qual approved. DTI at 33%. Letter issued.", 10, "25 min", "positive"),
                ("Call",   "Check-in call — Kevin actively touring Park Circle. No offer yet but expects to find property in 2-3 weeks.", 20, "9 min", "positive"),
            ],
        },
        {
            "email": "jasmine.winters@yahoo.com",
            "stage": "Pre-Qualified",
            "days_ago": 45,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow inquiry — Jasmine looking at townhomes in Wescott area. First-time buyer.", 0, "13 min", "positive"),
                ("Email",  "Sent pre-qual income doc checklist. Highlighted conventional loan with 10% down option.", 2, None, "positive"),
                ("Document","Received all income docs — 2024 W-2, pay stubs, 60-day bank statements.", 8, None, "positive"),
                ("Meeting","Pre-qualification call — $285K approved at 37% DTI. Pre-qual letter issued.", 12, "20 min", "positive"),
                ("Note",   "Pre-qual letter expires in 30 days. Need to follow up on property search progress. Wescott townhomes selling quickly.", 20, None, "positive"),
            ],
        },
        {
            "email": "elijah.fontaine@gmail.com",
            "stage": "Pre-Qualified",
            "days_ago": 52,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Facebook lead — Elijah looking at FHA purchase in Summerville area. DTI concern with spouse income.", 0, "17 min", "neutral"),
                ("Email",  "Sent FHA qualification requirements and request for spouse's income documentation.", 3, None, "neutral"),
                ("Call",   "Follow-up — spouse W-2 not yet available. Elijah working on gathering docs.", 10, "8 min", "neutral"),
                ("Note",   "Conditional pre-qual pending spouse income verification. W-2 and pay stubs needed. DTI at 42% — borderline.", 15, None, "neutral"),
            ],
        },
        # --- PRE-APPROVED leads (5-7 activities) ---
        {
            "email": "vanessa.hartley@gmail.com",
            "stage": "Pre-Approved",
            "days_ago": 55,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Referral from Bob Walsh at Sullivan's Realty — Vanessa needs pre-approval letter fast. Under contract.", 0, "20 min", "positive"),
                ("Email",  "Sent income doc checklist — priority request.", 1, None, "positive"),
                ("Document","Received complete doc package: W-2, paystubs, bank statements, tax returns. Quick turnaround.", 3, None, "positive"),
                ("Meeting","Pre-approval underwriting review — $450K approved, DTI 28%, credit 748. Full pre-approval issued.", 5, "30 min", "positive"),
                ("Call",   "Confirmed pre-approval and reviewed rate lock strategy. Loan amount locked at 6.750% for 45 days.", 8, "12 min", "positive"),
                ("Email",  "Pre-approval letter emailed to borrower and Bob Walsh at Sullivan's Realty. Appraisal ordered.", 10, None, "positive"),
            ],
        },
        {
            "email": "marcus.delacroix@icloud.com",
            "stage": "Pre-Approved",
            "days_ago": 68,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Website lead — Marcus actively touring homes, second offer pending on James Island property.", 0, "18 min", "positive"),
                ("Email",  "Sent pre-approval income doc checklist. Marcus has strong financials.", 2, None, "positive"),
                ("Document","Received full income package — W-2, pay stubs, bank statements, and 2023 tax returns.", 5, None, "positive"),
                ("Meeting","Pre-approval review — $380K approved at 32% DTI. Rate quoted at 6.999%.", 8, "25 min", "positive"),
                ("Call",   "Discussed rate lock timing with Marcus — waiting for offer acceptance before locking.", 12, "10 min", "positive"),
                ("Note",   "Second offer outcome unknown. Marcus will call when offer is accepted. Pre-approval letter valid 60 days.", 15, None, "positive"),
            ],
        },
        # --- APPLICATION leads (5-8 activities) ---
        {
            "email": "tanya.morrison@gmail.com",
            "stage": "Application",
            "days_ago": 65,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Realtor.com lead — Tanya found home on Wentworth St. Ready to apply. Under contract.", 0, "22 min", "positive"),
                ("Email",  "Sent full application link and income doc checklist.", 1, None, "positive"),
                ("Document","Received W-2, paystubs, bank statements. Missing 2022 tax return — follow up scheduled.", 5, None, "positive"),
                ("Meeting","Initial application review — 80% complete. 2022 tax transcripts still needed.", 8, "30 min", "positive"),
                ("Call",   "Follow-up on missing tax transcripts. Tanya ordered IRS transcript. Should arrive in 3 days.", 10, "9 min", "positive"),
                ("SMS",    "Hi Tanya — just checking in on the IRS transcript. Any update? Happy to order directly if easier!", 14, None, "positive"),
                ("Note",   "Application at 80%. Missing 2022 tax transcripts causing delay. Rate lock on SHL-2026-0001 expires soon.", 15, None, "neutral"),
            ],
        },
        {
            "email": "roberto.sandoval@hotmail.com",
            "stage": "Application",
            "days_ago": 75,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral lead — Roberto ready to buy townhome in North Charleston. FHA loan requested.", 0, "19 min", "positive"),
                ("Email",  "Sent FHA application link and doc checklist.", 1, None, "positive"),
                ("Document","Received most income docs. Still missing 2024 W-2 from employer.", 7, None, "positive"),
                ("Meeting","Application review meeting — full app submitted except missing W-2. FHA case number requested.", 12, "28 min", "positive"),
                ("Call",   "Followed up on missing W-2 — Roberto's employer needs 5 days to process. Appraisal scheduling initiated.", 15, "10 min", "positive"),
                ("Email",  "Title search ordered. Appraisal scheduled for next week.", 18, None, "positive"),
                ("Note",   "FHA case number requested. Appraisal scheduled. Waiting on W-2. Emily Park tracking doc status.", 20, None, "positive"),
            ],
        },
        {
            "email": "aisha.coleman@gmail.com",
            "stage": "Application",
            "days_ago": 82,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow lead — Aisha under contract on new construction in Mount Pleasant. Builder close in 60 days.", 0, "24 min", "positive"),
                ("Email",  "Sent full application package. Highlighted 60-day lock option for new construction.", 2, None, "positive"),
                ("Document","Received complete doc package: W-2, tax returns, paystubs, bank statements, gift letter.", 6, None, "positive"),
                ("Meeting","Application review — excellent profile (score 91, DTI 27%). Lock rate when builder gives 45-day window.", 10, "35 min", "positive"),
                ("Call",   "Spoke with Aisha — builder confirmed 45-day close window. Initiating rate lock discussion.", 15, "12 min", "positive"),
                ("Email",  "Rate lock options sent — 45-day at 6.875% vs 60-day at 7.000%. Recommend 45-day to save.", 18, None, "positive"),
                ("Note",   "All docs received. File ready for UW submission. Builder close confirmed. Lock ASAP.", 20, None, "positive"),
            ],
        },
        # --- LONG-TERM NURTURE leads (2-3 activities) ---
        {
            "email": "gregory.tatum@yahoo.com",
            "stage": "Long-Term Nurture",
            "days_ago": 210,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Cold outreach — Gregory interested in buying but saving for down payment. Target: spring next year.", 0, "11 min", "neutral"),
                ("Email",  "Added to rate-watch drip campaign. Sent market update and savings goal worksheet.", 30, None, "neutral"),
                ("Call",   "Monthly check-in call — Gregory saving steadily. Credit score holding at 635. Not ready yet.", 90, "8 min", "neutral"),
            ],
        },
        {
            "email": "courtney.langford@gmail.com",
            "stage": "Long-Term Nurture",
            "days_ago": 260,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Website inquiry — Courtney renting, lease ends in 9 months. Credit needs work first.", 0, "13 min", "neutral"),
                ("Email",  "Sent credit improvement guide and 90-day credit review plan.", 5, None, "neutral"),
                ("Call",   "90-day credit check-in — score improved from 668 to 682. Still needs more time.", 90, "10 min", "neutral"),
            ],
        },
        {
            "email": "antoine.devereaux@gmail.com",
            "stage": "Long-Term Nurture",
            "days_ago": 340,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral from family member (existing client) — Antoine interested in USDA loan. Needs 12-month payment history.", 0, "14 min", "neutral"),
                ("Email",  "Sent USDA eligibility information and income limit guide for Summerville area.", 7, None, "neutral"),
                ("Call",   "Annual review call — payment history improving. USDA income limit updated — Antoine now qualifies. Follow up in 6 months.", 180, "12 min", "neutral"),
            ],
        },
        # --- CREDIT REPAIR leads (2-3 activities) ---
        {
            "email": "darnell.pace@gmail.com",
            "stage": "Credit Repair",
            "days_ago": 115,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Facebook lead — two medical collections dragging score below 580 FHA minimum. On 6-month repair plan.", 0, "16 min", "neutral"),
                ("Email",  "Sent credit repair guide and referral to credit counseling partner.", 5, None, "neutral"),
                ("Call",   "90-day check-in — one collection paid, one disputed. Score now 594. Two months from FHA eligibility.", 60, "10 min", "neutral"),
            ],
        },
        {
            "email": "shayla.dupree@yahoo.com",
            "stage": "Credit Repair",
            "days_ago": 155,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Realtor.com lead — recent late payment from job loss 8 months ago. Score improving from 595.", 0, "14 min", "positive"),
                ("Email",  "Sent credit recovery roadmap — dispute process, rapid rescore timeline, FHA threshold targets.", 7, None, "positive"),
                ("Note",   "Score trending up — check next month. If crosses 620, fast-track pre-qualification.", 60, None, "positive"),
            ],
        },
        # --- FUNDED leads (8-10 activities) ---
        {
            "email": "michelle.osei@gmail.com",
            "stage": "Funded",
            "days_ago": 102,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Referral from Bob Walsh — Michelle ready to buy in Mt Pleasant. Strong financials.", 0, "20 min", "positive"),
                ("Email",  "Sent pre-approval checklist. Priority file.", 1, None, "positive"),
                ("Document","Received complete income package — all docs in order.", 5, None, "positive"),
                ("Meeting","Pre-approval underwriting — $415K approved. DTI 30%, credit 752.", 8, "30 min", "positive"),
                ("Call",   "Discussed rate lock — 7.125% for 30 days. Lock executed.", 15, "12 min", "positive"),
                ("Document","Appraisal received — $478K, above purchase price. Clean report.", 25, None, "positive"),
                ("Call",   "UW conditions cleared — CTC issued. Closing scheduled for 5 days out.", 40, "15 min", "positive"),
                ("Meeting","Closing prep — reviewed closing disclosure, wire instructions, and what to bring.", 45, "45 min", "positive"),
                ("Call",   "Post-closing call — Michelle closed on time. 5-star satisfaction. Introduced to two neighbors for referrals.", 50, "10 min", "positive"),
                ("Note",   "Funded! Closed on time. Client satisfaction: 5 stars. Added to MUM portfolio. Referral pipeline active.", 52, None, "positive"),
            ],
        },
        {
            "email": "james.beaumont@icloud.com",
            "stage": "Funded",
            "days_ago": 160,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Website lead — James looking at single-family in Mt Pleasant. Had VA loan but switching to conventional.", 0, "18 min", "positive"),
                ("Email",  "Sent conventional loan doc checklist and program comparison vs VA.", 2, None, "positive"),
                ("Document","Full income package received.", 6, None, "positive"),
                ("Meeting","Pre-approval review — $360K approved. James prefers conventional due to appraisal flexibility.", 10, "25 min", "positive"),
                ("Call",   "Rate lock discussion — 7.250% for 30 days. Lock executed after offer accepted.", 18, "11 min", "positive"),
                ("Document","Appraisal came in strong at $418K vs $415K purchase. No value issues.", 28, None, "positive"),
                ("Call",   "All UW conditions cleared. CTC issued. Closing set for next week.", 45, "14 min", "positive"),
                ("Meeting","Closing prep meeting — all docs signed and wire instructions confirmed.", 52, "40 min", "positive"),
                ("Call",   "Post-closing congratulations call. James thrilled — VA loan conversion paid off.", 55, "9 min", "positive"),
                ("Note",   "Funded! VA loan converted to conventional at last minute — appraisal came in strong. Scheduled 6-month rate review.", 58, None, "positive"),
            ],
        },
        # --- DOES NOT QUALIFY / WITHDRAWN (1-2 activities each) ---
        {
            "email": "roderick.fulton@gmail.com",
            "stage": "Does Not Qualify",
            "days_ago": 120,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Cold outreach — DTI too high (52%), credit below FHA minimum (558), self-employed 1099. Cannot qualify at this time.", 0, "15 min", "negative"),
                ("Email",  "Sent detailed explanation of qualification gaps and 18-month action plan: credit improvement, debt paydown, stable income documentation.", 2, None, "neutral"),
            ],
        },
        {
            "email": "lydia.whitmore@outlook.com",
            "stage": "Withdrawn",
            "days_ago": 60,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow lead — Lydia qualified and pre-approved but spouse changed jobs. Decided to stay in current home.", 0, "16 min", "neutral"),
                ("Note",   "Lead withdrawn — spouse job change made move impractical. Set 12-month re-engagement reminder.", 2, None, "neutral"),
            ],
        },
    ]

    act_inserted = 0
    act_skipped = 0

    for lead_spec in LEAD_ACTIVITIES:
        lead_id = lead_ids.get(lead_spec["email"])
        if not lead_id:
            continue

        created_base = days_ago(lead_spec["days_ago"])
        owner_id = lead_spec["owner_id"]

        for (act_type, content, offset_days, duration, sentiment) in lead_spec["activities"]:
            act_ts = created_base + timedelta(days=offset_days)

            # Idempotency: check by lead_id + type + truncated content prefix
            content_prefix = content[:80]
            existing = conn.execute(
                text("""
                    SELECT id FROM activities
                    WHERE lead_id = :lead_id
                      AND type = :type
                      AND LEFT(content, 80) = :prefix
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"lead_id": lead_id, "type": act_type, "prefix": content_prefix, "org_id": org_id},
            ).fetchone()
            if existing:
                act_skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO activities
                        (organization_id, type, content, lead_id, user_id,
                         duration, sentiment, created_at)
                    VALUES
                        (:org_id, :type, :content, :lead_id, :user_id,
                         :duration, :sentiment, :created_at)
                """),
                {
                    "org_id": org_id,
                    "type": act_type,
                    "content": content,
                    "lead_id": lead_id,
                    "user_id": owner_id,
                    "duration": duration,
                    "sentiment": sentiment,
                    "created_at": act_ts,
                },
            )
            act_inserted += 1

    conn.commit()

    # ------------------------------------------------------------------
    # Loan activities (2-5 per loan)
    # ------------------------------------------------------------------
    LOAN_ACTIVITY_SPECS = [
        # loan_number, days_ago, lo_id, [(type, content, offset_days)]
        ("SHL-2026-0001", 65, lo_sarah_id, [
            ("Document", "Full application package received — W-2, paystubs, bank statements. Missing 2022 tax transcripts.", 0),
            ("Call",     "Discussed loan structure and timeline with Tanya. Rate locked at 6.875% for 60 days.", 5),
            ("Note",     "Application 80% complete. Emily Park following up on 2022 tax return IRS transcript.", 12),
        ]),
        ("SHL-2026-0002", 75, lo_marcus_id, [
            ("Document", "FHA application submitted. W-2 still outstanding — employer processing delay noted.", 0),
            ("Call",     "FHA case number requested. Appraisal scheduling initiated for next week.", 8),
            ("Email",    "Title search ordered with Charleston Title Group. Confirmation #TL-4421.", 12),
            ("Note",     "Full app submitted. Awaiting W-2 and appraisal. Emily Park on processor duty.", 20),
        ]),
        ("SHL-2026-0003", 55, lo_sarah_id, [
            ("Document", "Rate locked at 6.750% — 45-day lock executed. Lock confirmation sent to borrower and agent.", 0),
            ("Document", "Appraisal ordered via AMC. Confirmation #AP-8801. ETA 7-10 business days.", 5),
            ("Call",     "Processing status update — all docs complete. File moved to UW queue.", 15),
        ]),
        ("SHL-2026-0004", 82, lo_sarah_id, [
            ("Document", "Complete income package received. Excellent file — ready for UW submission.", 0),
            ("Call",     "Rate lock strategy discussion — 45-day at 6.875%. Builder gave 45-day window.", 10),
            ("Email",    "Rate lock executed. Builder confirmed construction timeline. File submitted to UW.", 18),
            ("Note",     "Clean file. All docs in order. UW submission imminent.", 22),
        ]),
        ("SHL-2026-0005", 68, lo_marcus_id, [
            ("Document", "File submitted to underwriting. All income docs and appraisal complete.", 0),
            ("Call",     "Submission confirmation sent to Marcus Delacroix. UW turnaround expected 5-7 days.", 5),
            ("Note",     "Submitted to UW. Waiting on UW review. Marcus Delacroix second offer pending on another property.", 10),
        ]),
        ("SHL-2026-0006", 38, lo_marcus_id, [
            ("Document", "Appraisal returned — $390K vs $385K purchase price. LTV improves slightly.", 0),
            ("Call",     "Rachel Kim reviewing appraisal and income analysis. Identified one condition: HOA cert needed.", 7),
            ("Note",     "In UW review. Risk score 24. On track for CTC within 5 days pending HOA cert.", 12),
        ]),
        ("SHL-2026-0007", 45, lo_sarah_id, [
            ("Document", "Appraisal came in at $323K — tight vs $320K purchase. LTV acceptable at 88%.", 0),
            ("Call",     "James Mitchell (UW) flagged DTI concern. Requested updated pay stub for income verification.", 6),
            ("Note",     "At-risk file (risk score 38). DTI borderline at 37%. James Mitchell reviewing — CTC delayed pending VOE update.", 14),
        ]),
        ("SHL-2026-0008", 18, lo_sarah_id, [
            ("Call",     "Conditional approval issued by Rachel Kim. 3 conditions: HOI binder, title update, gift letter.", 0),
            ("Email",    "Conditions list sent to Brianna Okafor. HOI binder needed from State Farm agent.", 2),
            ("Document", "HOI binder received from State Farm. Two conditions remaining.", 4),
        ]),
        ("SHL-2026-0009", 52, lo_marcus_id, [
            ("Document", "All UW conditions cleared by James Mitchell. CTC issued.", 0),
            ("Call",     "Closing disclosure prepared and sent to Elijah Fontaine. 3-day waiting period started.", 2),
            ("Email",    "Closing scheduled with Charleston Title Group for 5 days from now. Wire instructions sent.", 3),
        ]),
        ("SHL-2026-0010", 27, lo_sarah_id, [
            ("Document", "Closing disclosure delivered — 3-day waiting period complete. Closing set for 2 days from now.", 0),
            ("Call",     "Final walkthrough confirmed with Simone Arceneaux. All docs signed and wire instructions verified.", 2),
            ("Note",     "Closing in 2 days. All conditions clear. Title confirmed. Funding imminent.", 3),
        ]),
        ("SHL-2026-0011", 102, lo_sarah_id, [
            ("Document", "Funded — wire confirmed from title. Loan disbursed to seller.", 0),
            ("Call",     "Post-close call with Michelle Osei. 5-star satisfaction. Sent referral request.", 5),
            ("Note",     "Funded on time. Michelle Osei added to MUM portfolio. 2 referrals in pipeline.", 7),
        ]),
        ("SHL-2026-0012", 160, lo_marcus_id, [
            ("Document", "Funded — conventional loan. VA conversion handled smoothly. Appraisal came in strong.", 0),
            ("Call",     "Post-close congratulations to James Beaumont. Scheduled 6-month rate review.", 8),
            ("Note",     "Funded. James Beaumont in MUM portfolio. 6-month rate check scheduled.", 10),
        ]),
        ("SHL-2026-0013", 210, lo_sarah_id, [
            ("Document", "Funded — first-time buyer success. Tyler Barnes closed conventional 10% down.", 0),
            ("Call",     "Post-close call — Tyler thrilled with his new home. Requested referral introduction email.", 5),
        ]),
        ("SHL-2026-0014", 265, lo_sarah_id, [
            ("Document", "Funded — Carter Webb conventional loan. Clean file and on-time close.", 0),
            ("Note",     "Carter Webb funded. Added to MUM portfolio. Monitoring for 1-year refi opportunity.", 5),
        ]),
        ("SHL-2026-0015", 330, lo_marcus_id, [
            ("Document", "Funded — Nathan Prescott FHA condo loan. HOA condo certification obtained.", 0),
            ("Call",     "Post-close call with Nathan. Happy with purchase. Condo community love it.", 5),
        ]),
    ]

    for (loan_number, loan_days_ago, lo_id, acts) in LOAN_ACTIVITY_SPECS:
        loan_id = loan_ids.get(loan_number)
        if not loan_id:
            continue

        base_ts = days_ago(loan_days_ago)
        for (act_type, content, offset_days) in acts:
            act_ts = base_ts + timedelta(days=offset_days)
            content_prefix = content[:80]

            existing = conn.execute(
                text("""
                    SELECT id FROM activities
                    WHERE loan_id = :loan_id
                      AND type = :type
                      AND LEFT(content, 80) = :prefix
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "type": act_type, "prefix": content_prefix, "org_id": org_id},
            ).fetchone()
            if existing:
                act_skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO activities
                        (organization_id, type, content, loan_id, user_id,
                         duration, sentiment, created_at)
                    VALUES
                        (:org_id, :type, :content, :loan_id, :user_id,
                         :duration, :sentiment, :created_at)
                """),
                {
                    "org_id": org_id,
                    "type": act_type,
                    "content": content,
                    "loan_id": loan_id,
                    "user_id": lo_id,
                    "duration": None,
                    "sentiment": "positive",
                    "created_at": act_ts,
                },
            )
            act_inserted += 1

    conn.commit()
    print(f"✅ Seeded {act_inserted} activity records ({act_skipped} already existed)")

    # ------------------------------------------------------------------
    # Stage History
    # ------------------------------------------------------------------

    # Lead stage progression paths
    LEAD_STAGE_PATHS = {
        # email: (days_ago, owner_id, [stages in order])
        "tyler.barnes@gmail.com":      (2,   lo_sarah_id,   ["New"]),
        "priya.nair@outlook.com":      (5,   lo_marcus_id,  ["New"]),
        "derek.hollis@yahoo.com":      (1,   lo_sarah_id,   ["New"]),
        "monique.duval@gmail.com":     (8,   lo_marcus_id,  ["New", "Attempted Contact"]),
        "carter.webb@icloud.com":      (11,  lo_sarah_id,   ["New", "Attempted Contact"]),
        "brianna.okafor@gmail.com":    (18,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect"]),
        "nathan.prescott@hotmail.com": (22,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect"]),
        "simone.arceneaux@gmail.com":  (27,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect"]),
        "kevin.albright@gmail.com":    (38,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "jasmine.winters@yahoo.com":   (45,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "elijah.fontaine@gmail.com":   (52,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "vanessa.hartley@gmail.com":   (55,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved"]),
        "marcus.delacroix@icloud.com": (68,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved"]),
        "tanya.morrison@gmail.com":    (65,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "roberto.sandoval@hotmail.com":(75,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "aisha.coleman@gmail.com":     (82,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "gregory.tatum@yahoo.com":     (210, lo_marcus_id,  ["New", "Long-Term Nurture"]),
        "courtney.langford@gmail.com": (260, lo_sarah_id,   ["New", "Long-Term Nurture"]),
        "antoine.devereaux@gmail.com": (340, lo_marcus_id,  ["New", "Long-Term Nurture"]),
        "darnell.pace@gmail.com":      (115, lo_sarah_id,   ["New", "Credit Repair"]),
        "shayla.dupree@yahoo.com":     (155, lo_marcus_id,  ["New", "Credit Repair"]),
        "michelle.osei@gmail.com":     (102, lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Funded"]),
        "james.beaumont@icloud.com":   (160, lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Funded"]),
        "roderick.fulton@gmail.com":   (120, lo_marcus_id,  ["New", "Does Not Qualify"]),
        "lydia.whitmore@outlook.com":  (60,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Withdrawn"]),
    }

    sh_inserted = 0
    sh_skipped = 0

    for email, (total_days_ago, owner_id, stages) in LEAD_STAGE_PATHS.items():
        lead_id = lead_ids.get(email)
        if not lead_id:
            continue

        # Space stages evenly across the lead's age, 3-7 days apart
        n_transitions = len(stages)
        # Spread: allocate days across transitions
        if n_transitions == 1:
            # Only one stage: just the initial entry
            offsets = [0]
        else:
            step = max(3, total_days_ago // (n_transitions + 1))
            offsets = [total_days_ago - (i * step) for i in range(n_transitions)]
            # Clamp so last one is at least 1 day ago
            offsets = [max(1, o) for o in offsets]

        prev_stage = None
        prev_ts = None

        for idx, stage in enumerate(stages):
            changed_at = days_ago(offsets[idx])

            # Duration in previous stage (days)
            if prev_ts is not None:
                dur = int((changed_at - prev_ts).days)
            else:
                dur = None

            # Idempotency: check by lead_id + to_stage
            existing = conn.execute(
                text("""
                    SELECT id FROM stage_history
                    WHERE lead_id = :lead_id
                      AND to_stage = :to_stage
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"lead_id": lead_id, "to_stage": stage, "org_id": org_id},
            ).fetchone()
            if existing:
                sh_skipped += 1
            else:
                conn.execute(
                    text("""
                        INSERT INTO stage_history
                            (organization_id, entity_type, entity_id, lead_id,
                             from_stage, to_stage, changed_at, changed_by_id,
                             duration_in_previous_stage)
                        VALUES
                            (:org_id, 'lead', :entity_id, :lead_id,
                             :from_stage, :to_stage, :changed_at, :changed_by_id,
                             :duration)
                    """),
                    {
                        "org_id": org_id,
                        "entity_id": lead_id,
                        "lead_id": lead_id,
                        "from_stage": prev_stage,
                        "to_stage": stage,
                        "changed_at": changed_at,
                        "changed_by_id": owner_id,
                        "duration": dur,
                    },
                )
                sh_inserted += 1

            prev_stage = stage
            prev_ts = changed_at

    conn.commit()

    # Loan stage history
    LOAN_STAGE_PATHS = {
        # loan_number: (days_ago, lo_id, [stages in order])
        "SHL-2026-0001": (65,  lo_sarah_id,   ["APPLICATION"]),
        "SHL-2026-0002": (75,  lo_marcus_id,  ["APPLICATION"]),
        "SHL-2026-0003": (55,  lo_sarah_id,   ["APPLICATION", "PROCESSING"]),
        "SHL-2026-0004": (82,  lo_sarah_id,   ["APPLICATION", "PROCESSING"]),
        "SHL-2026-0005": (68,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED"]),
        "SHL-2026-0006": (38,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING"]),
        "SHL-2026-0007": (45,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING"]),
        "SHL-2026-0008": (18,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL"]),
        "SHL-2026-0009": (52,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE"]),
        "SHL-2026-0010": (27,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING"]),
        "SHL-2026-0011": (102, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0012": (160, lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0013": (210, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0014": (265, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0015": (330, lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
    }

    for loan_number, (total_days_ago, lo_id, stages) in LOAN_STAGE_PATHS.items():
        loan_id = loan_ids.get(loan_number)
        if not loan_id:
            continue

        n = len(stages)
        step = max(4, total_days_ago // (n + 1))
        offsets = [total_days_ago - (i * step) for i in range(n)]
        offsets = [max(1, o) for o in offsets]

        prev_stage = None
        prev_ts = None

        for idx, stage in enumerate(stages):
            changed_at = days_ago(offsets[idx])
            dur = int((changed_at - prev_ts).days) if prev_ts is not None else None

            existing = conn.execute(
                text("""
                    SELECT id FROM stage_history
                    WHERE loan_id = :loan_id
                      AND to_stage = :to_stage
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "to_stage": stage, "org_id": org_id},
            ).fetchone()
            if existing:
                sh_skipped += 1
            else:
                conn.execute(
                    text("""
                        INSERT INTO stage_history
                            (organization_id, entity_type, entity_id, loan_id,
                             from_stage, to_stage, changed_at, changed_by_id,
                             duration_in_previous_stage)
                        VALUES
                            (:org_id, 'loan', :entity_id, :loan_id,
                             :from_stage, :to_stage, :changed_at, :changed_by_id,
                             :duration)
                    """),
                    {
                        "org_id": org_id,
                        "entity_id": loan_id,
                        "loan_id": loan_id,
                        "from_stage": prev_stage,
                        "to_stage": stage,
                        "changed_at": changed_at,
                        "changed_by_id": lo_id,
                        "duration": dur,
                    },
                )
                sh_inserted += 1

            prev_stage = stage
            prev_ts = changed_at

    conn.commit()
    print(f"✅ Seeded {sh_inserted} stage history records ({sh_skipped} already existed)")


def seed_ai_metrics(conn, org_id):
    """Create demo AI usage metrics and performance data (30-day snapshots)."""

    apd_inserted = 0
    apd_skipped = 0
    amd_inserted = 0
    amd_skipped = 0

    for day_idx in range(30):
        # day_idx 0 = 30 days ago, day_idx 29 = yesterday
        snap_date = date_ago(30 - day_idx)
        t = day_idx / 29.0  # 0.0 → 1.0 (normalized trend position)

        # --- AIPerformanceDaily ---
        existing_apd = conn.execute(
            text("""
                SELECT id FROM ai_performance_daily
                WHERE date = :snap_date AND agent_name = 'aria' AND organization_id = :org_id
                LIMIT 1
            """),
            {"snap_date": snap_date, "org_id": org_id},
        ).fetchone()
        if existing_apd:
            apd_skipped += 1
        else:
            total_actions = int(8 + t * 12 + random.uniform(-1.5, 1.5))
            total_actions = max(8, total_actions)
            autonomous = int(total_actions * random.uniform(0.55, 0.70))
            approved = int((total_actions - autonomous) * random.uniform(0.70, 0.90))
            rejected = (total_actions - autonomous) - approved
            successful = int(total_actions * (0.82 + t * 0.13 + random.uniform(-0.02, 0.02)))
            successful = min(successful, total_actions)
            failed = total_actions - successful
            success_rate = round(successful / total_actions, 4) if total_actions else 0
            avg_confidence = round(0.78 + t * 0.14 + random.uniform(-0.02, 0.02), 4)
            avg_confidence = min(0.97, max(0.75, avg_confidence))
            avg_impact = round(0.65 + t * 0.20 + random.uniform(-0.03, 0.03), 4)
            avg_impact = min(0.95, max(0.60, avg_impact))
            biz_value = round(total_actions * successful * random.uniform(18.0, 35.0), 2)

            conn.execute(
                text("""
                    INSERT INTO ai_performance_daily
                        (date, organization_id, agent_name,
                         total_actions, autonomous_actions, approved_actions,
                         rejected_actions, successful_actions, failed_actions,
                         success_rate, avg_confidence_score, avg_impact_score,
                         total_business_value, created_at)
                    VALUES
                        (:snap_date, :org_id, 'aria',
                         :total_actions, :autonomous_actions, :approved_actions,
                         :rejected_actions, :successful_actions, :failed_actions,
                         :success_rate, :avg_confidence_score, :avg_impact_score,
                         :total_business_value, :now)
                """),
                {
                    "snap_date": snap_date,
                    "org_id": org_id,
                    "total_actions": total_actions,
                    "autonomous_actions": autonomous,
                    "approved_actions": approved,
                    "rejected_actions": rejected,
                    "successful_actions": successful,
                    "failed_actions": failed,
                    "success_rate": success_rate,
                    "avg_confidence_score": avg_confidence,
                    "avg_impact_score": avg_impact,
                    "total_business_value": biz_value,
                    "now": NOW,
                },
            )
            apd_inserted += 1

        # --- AIMetricsDaily ---
        existing_amd = conn.execute(
            text("""
                SELECT id FROM ai_metrics_daily
                WHERE date = :snap_date AND organization_id = :org_id
                LIMIT 1
            """),
            {"snap_date": snap_date, "org_id": org_id},
        ).fetchone()
        if existing_amd:
            amd_skipped += 1
        else:
            tasks_total = int(10 + t * 15 + random.uniform(-2, 2))
            tasks_total = max(10, tasks_total)
            automation_rate = round(0.60 + t * 0.25 + random.uniform(-0.03, 0.03), 4)
            automation_rate = min(0.90, max(0.55, automation_rate))
            tasks_auto = int(tasks_total * automation_rate)
            tasks_escalated = tasks_total - tasks_auto
            escalation_rate = round(1.0 - automation_rate, 4)
            avg_resolution = round(180.0 - t * 60.0 + random.uniform(-15, 15), 2)
            avg_resolution = max(60.0, avg_resolution)
            time_saved = round(tasks_auto * (300.0 - t * 60.0), 2)
            ai_improvement = round(95.0 + t * 20.0 + random.uniform(-2, 2), 2)
            ai_improvement = min(120.0, max(90.0, ai_improvement))

            conn.execute(
                text("""
                    INSERT INTO ai_metrics_daily
                        (date, organization_id,
                         tasks_total, tasks_auto_completed, tasks_escalated_to_humans,
                         automation_rate, escalation_rate,
                         avg_ai_resolution_time_seconds, total_time_saved_seconds,
                         ai_improvement_index, created_at)
                    VALUES
                        (:snap_date, :org_id,
                         :tasks_total, :tasks_auto, :tasks_escalated,
                         :automation_rate, :escalation_rate,
                         :avg_resolution, :time_saved,
                         :ai_improvement, :now)
                """),
                {
                    "snap_date": snap_date,
                    "org_id": org_id,
                    "tasks_total": tasks_total,
                    "tasks_auto": tasks_auto,
                    "tasks_escalated": tasks_escalated,
                    "automation_rate": automation_rate,
                    "escalation_rate": escalation_rate,
                    "avg_resolution": avg_resolution,
                    "time_saved": time_saved,
                    "ai_improvement": ai_improvement,
                    "now": NOW,
                },
            )
            amd_inserted += 1

    conn.commit()
    print(f"✅ Seeded {apd_inserted} AI performance daily rows ({apd_skipped} existed)")
    print(f"✅ Seeded {amd_inserted} AI metrics daily rows ({amd_skipped} existed)")


def seed_rate_monitor(conn, org_id, mum_ids, loan_ids):
    """Create rate market data, rate locks, and refi opportunities."""

    # ------------------------------------------------------------------
    # 1. RateMarketData — 30 days of snapshots
    # ------------------------------------------------------------------
    rmd_inserted = 0
    rmd_skipped = 0

    BASE_30YR   = Decimal("6.750")
    BASE_15YR   = Decimal("6.125")
    BASE_ARM51  = Decimal("6.000")
    BASE_FHA30  = Decimal("6.375")
    BASE_VA30   = Decimal("6.250")
    BASE_T10    = Decimal("4.250")
    SPREAD      = Decimal("2.500")

    # Slight downward trend over 30 days (up to -0.125 total)
    TREND_DOWN  = Decimal("0.125")

    for day_idx in range(30):
        snap_date = date_ago(30 - day_idx)
        trend_frac = Decimal(str(day_idx / 29.0))

        # Daily variance ±0.0625
        def jitter():
            return Decimal(str(round(random.uniform(-0.0625, 0.0625), 3)))

        r30  = BASE_30YR  - (trend_frac * TREND_DOWN) + jitter()
        r15  = BASE_15YR  - (trend_frac * TREND_DOWN) + jitter()
        r51  = BASE_ARM51 - (trend_frac * TREND_DOWN) + jitter()
        rfha = BASE_FHA30 - (trend_frac * TREND_DOWN) + jitter()
        rva  = BASE_VA30  - (trend_frac * TREND_DOWN) + jitter()
        t10  = BASE_T10   - (trend_frac * Decimal("0.050")) + jitter()
        spread = (r30 - t10).quantize(Decimal("0.001"))

        # Clamp to sane ranges (3 decimal places)
        def clamp(val, lo, hi):
            return max(Decimal(str(lo)), min(Decimal(str(hi)), val)).quantize(Decimal("0.001"))

        r30  = clamp(r30,  5.500, 8.000)
        r15  = clamp(r15,  5.000, 7.500)
        r51  = clamp(r51,  4.750, 7.500)
        rfha = clamp(rfha, 5.250, 7.750)
        rva  = clamp(rva,  5.125, 7.625)
        t10  = clamp(t10,  3.500, 5.500)
        spread = clamp(spread, 1.500, 3.500)

        # 7-day and 30-day trend labels
        if day_idx < 7:
            trend_7day = "stable"
        elif day_idx < 15:
            trend_7day = "declining"
        else:
            trend_7day = "declining"

        trend_30day = "declining"
        volatility_score = round(random.uniform(0.15, 0.45), 2)
        change_30yr = clamp(r30 - BASE_30YR, -0.500, 0.500)

        existing = conn.execute(
            text("""
                SELECT id FROM rate_market_data
                WHERE organization_id = :org_id AND snapshot_date = :snap_date
                LIMIT 1
            """),
            {"org_id": org_id, "snap_date": snap_date},
        ).fetchone()
        if existing:
            rmd_skipped += 1
            continue

        conn.execute(
            text("""
                INSERT INTO rate_market_data
                    (organization_id, snapshot_date, source,
                     rate_30yr_fixed, rate_15yr_fixed, rate_arm_5_1,
                     rate_fha_30yr, rate_va_30yr,
                     treasury_10yr, spread_to_treasury,
                     trend_7day, trend_30day, volatility_score,
                     change_30yr, created_at)
                VALUES
                    (:org_id, :snap_date, 'fred',
                     :r30, :r15, :r51,
                     :rfha, :rva,
                     :t10, :spread,
                     :trend_7day, :trend_30day, :volatility_score,
                     :change_30yr, :now)
            """),
            {
                "org_id": org_id,
                "snap_date": snap_date,
                "r30": r30,
                "r15": r15,
                "r51": r51,
                "rfha": rfha,
                "rva": rva,
                "t10": t10,
                "spread": spread,
                "trend_7day": trend_7day,
                "trend_30day": trend_30day,
                "volatility_score": volatility_score,
                "change_30yr": change_30yr,
                "now": NOW,
            },
        )
        rmd_inserted += 1

    conn.commit()
    print(f"✅ Seeded {rmd_inserted} rate market data rows ({rmd_skipped} existed)")

    # ------------------------------------------------------------------
    # 2. RateLock — 5 rate locks on active loans
    # ------------------------------------------------------------------
    # Loans: SHL-2026-0003 (PROCESSING), SHL-2026-0005 (SUBMITTED),
    #        SHL-2026-0006 (UNDERWRITING), SHL-2026-0008 (CONDITIONAL_APPROVAL),
    #        SHL-2026-0009 (CLEAR_TO_CLOSE)
    RATE_LOCKS = [
        {
            "loan_number": "SHL-2026-0003",
            "lead_email": "vanessa.hartley@gmail.com",
            "status": "locked",
            "lock_type": "standard",
            "lock_period_days": 45,
            "rate_locked": Decimal("6.750"),
            "lock_days_ago": 50,
            "ai_recommendation": "lock",
            "ai_lock_score": 82,
            "ai_reasoning": "Rate trending upward — locking in 6.750% protects borrower from potential 25bp increase. 45-day window aligns with closing timeline.",
            "market_rate_at_lock": Decimal("6.750"),
        },
        {
            "loan_number": "SHL-2026-0005",
            "lead_email": "marcus.delacroix@icloud.com",
            "status": "locked",
            "lock_type": "standard",
            "lock_period_days": 45,
            "rate_locked": Decimal("6.999"),
            "lock_days_ago": 65,
            "ai_recommendation": "strong_lock",
            "ai_lock_score": 91,
            "ai_reasoning": "Market volatility elevated. Borrower credit profile strong. Locking at 6.999% ahead of expected Fed commentary reduces risk.",
            "market_rate_at_lock": Decimal("7.000"),
        },
        {
            "loan_number": "SHL-2026-0006",
            "lead_email": "kevin.albright@gmail.com",
            "status": "expired",
            "lock_type": "standard",
            "lock_period_days": 30,
            "rate_locked": Decimal("7.000"),
            "lock_days_ago": 45,
            "ai_recommendation": "lock",
            "ai_lock_score": 75,
            "ai_reasoning": "Short lock to match UW timeline. Monitor for extension if UW takes longer than 21 days.",
            "market_rate_at_lock": Decimal("7.000"),
        },
        {
            "loan_number": "SHL-2026-0008",
            "lead_email": "brianna.okafor@gmail.com",
            "status": "monitoring",
            "lock_type": "float_down",
            "lock_period_days": 21,
            "rate_locked": Decimal("6.750"),
            "lock_days_ago": 15,
            "ai_recommendation": "hold",
            "ai_lock_score": 68,
            "ai_reasoning": "Rate declining slightly. Float-down option purchased — monitor for 25bp improvement before CTC to exercise float-down.",
            "market_rate_at_lock": Decimal("6.750"),
        },
        {
            "loan_number": "SHL-2026-0009",
            "lead_email": "elijah.fontaine@gmail.com",
            "status": "monitoring",
            "lock_type": "standard",
            "lock_period_days": 30,
            "rate_locked": Decimal("6.625"),
            "lock_days_ago": 48,
            "ai_recommendation": "lock",
            "ai_lock_score": 88,
            "ai_reasoning": "CTC issued. Closing in 5 days. Rate at 6.625% is excellent for FHA. Lock secured — no action needed.",
            "market_rate_at_lock": Decimal("6.625"),
        },
    ]

    rl_inserted = 0
    rl_skipped = 0

    for rl in RATE_LOCKS:
        loan_id = loan_ids.get(rl["loan_number"])
        if not loan_id:
            continue

        lead_id = conn.execute(
            text("SELECT id FROM leads WHERE email = :email AND organization_id = :org_id LIMIT 1"),
            {"email": rl["lead_email"], "org_id": org_id},
        ).fetchone()
        lead_id = lead_id[0] if lead_id else None

        existing = conn.execute(
            text("""
                SELECT id FROM rate_locks
                WHERE loan_id = :loan_id AND organization_id = :org_id
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()
        if existing:
            rl_skipped += 1
            continue

        lock_date = days_ago(rl["lock_days_ago"])
        lock_exp = lock_date + timedelta(days=rl["lock_period_days"])

        conn.execute(
            text("""
                INSERT INTO rate_locks
                    (organization_id, loan_id, lead_id,
                     status, lock_type, lock_period_days,
                     rate_locked, lock_date, lock_expiration_date,
                     ai_recommendation, ai_lock_score, ai_reasoning,
                     market_rate_at_lock, created_at)
                VALUES
                    (:org_id, :loan_id, :lead_id,
                     :status, :lock_type, :lock_period_days,
                     :rate_locked, :lock_date, :lock_expiration_date,
                     :ai_recommendation, :ai_lock_score, :ai_reasoning,
                     :market_rate_at_lock, :now)
            """),
            {
                "org_id": org_id,
                "loan_id": loan_id,
                "lead_id": lead_id,
                "status": rl["status"],
                "lock_type": rl["lock_type"],
                "lock_period_days": rl["lock_period_days"],
                "rate_locked": rl["rate_locked"],
                "lock_date": lock_date,
                "lock_expiration_date": lock_exp,
                "ai_recommendation": rl["ai_recommendation"],
                "ai_lock_score": rl["ai_lock_score"],
                "ai_reasoning": rl["ai_reasoning"],
                "market_rate_at_lock": rl["market_rate_at_lock"],
                "now": NOW,
            },
        )
        rl_inserted += 1

    conn.commit()
    print(f"✅ Seeded {rl_inserted} rate locks ({rl_skipped} existed)")

    # ------------------------------------------------------------------
    # 3. RefiOpportunity — 5 opportunities linked to MUM clients
    # ------------------------------------------------------------------
    # Clients with high rates (>6%): Brian & Monica Tanner (6.750), Lauren Fitzgerald (6.875),
    # Kenneth & Paula Osei (6.500), Nadia & Paul Bergeron (6.625), Terrence & Alicia Watkins (6.875)
    REFI_OPPS = [
        {
            "mum_idx": 7,   # Brian Tanner — 6.750%, 3 years ago, $375K
            "opportunity_type": "rate_reduction",
            "refi_score": 78,
            "original_rate": Decimal("6.750"),
            "current_balance": Decimal("362000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.125"),
            "estimated_home_value": Decimal("434500.00"),
            "estimated_monthly_savings": Decimal("32.00"),
            "estimated_total_savings": Decimal("11520.00"),
            "break_even_months": 96,
            "status": "identified",
            "identified_at": days_ago(15),
            "contacted_at": None,
            "outreach_count": 0,
        },
        {
            "mum_idx": 8,   # Lauren Fitzgerald — 6.875%, 3 years ago, $270K
            "opportunity_type": "rate_reduction",
            "refi_score": 82,
            "original_rate": Decimal("6.875"),
            "current_balance": Decimal("259000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.250"),
            "estimated_home_value": Decimal("316100.00"),
            "estimated_monthly_savings": Decimal("42.00"),
            "estimated_total_savings": Decimal("15120.00"),
            "break_even_months": 72,
            "status": "contacted",
            "identified_at": days_ago(30),
            "contacted_at": days_ago(20),
            "outreach_count": 2,
        },
        {
            "mum_idx": 9,   # Kenneth Osei — 6.500%, 2 years ago, $480K
            "opportunity_type": "rate_reduction",
            "refi_score": 70,
            "original_rate": Decimal("6.500"),
            "current_balance": Decimal("464000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("-0.125"),
            "estimated_home_value": Decimal("577800.00"),
            "estimated_monthly_savings": Decimal("-32.00"),
            "estimated_total_savings": Decimal("-11520.00"),
            "break_even_months": 999,
            "status": "identified",
            "identified_at": days_ago(10),
            "contacted_at": None,
            "outreach_count": 0,
        },
        {
            "mum_idx": 10,  # Nadia Bergeron — 6.625%, 2 years ago, $325K
            "opportunity_type": "cash_out",
            "refi_score": 65,
            "original_rate": Decimal("6.625"),
            "current_balance": Decimal("313000.00"),
            "current_market_rate": Decimal("6.700"),
            "rate_advantage": Decimal("-0.075"),
            "estimated_home_value": Decimal("390300.00"),
            "estimated_monthly_savings": Decimal("0.00"),
            "estimated_total_savings": Decimal("0.00"),
            "break_even_months": 0,
            "status": "interested",
            "identified_at": days_ago(45),
            "contacted_at": days_ago(35),
            "outreach_count": 3,
        },
        {
            "mum_idx": 11,  # Terrence Watkins — 6.875%, 1 year ago, $350K
            "opportunity_type": "rate_reduction",
            "refi_score": 86,
            "original_rate": Decimal("6.875"),
            "current_balance": Decimal("344000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.250"),
            "estimated_home_value": Decimal("405600.00"),
            "estimated_monthly_savings": Decimal("57.00"),
            "estimated_total_savings": Decimal("20520.00"),
            "break_even_months": 60,
            "status": "contacted",
            "identified_at": days_ago(20),
            "contacted_at": days_ago(10),
            "outreach_count": 1,
        },
    ]

    ro_inserted = 0
    ro_skipped = 0

    for opp in REFI_OPPS:
        mum_idx = opp["mum_idx"]
        if mum_idx >= len(mum_ids):
            continue
        mum_id = mum_ids[mum_idx]

        existing = conn.execute(
            text("""
                SELECT id FROM refi_opportunities
                WHERE mum_client_id = :mum_id AND organization_id = :org_id
                LIMIT 1
            """),
            {"mum_id": mum_id, "org_id": org_id},
        ).fetchone()
        if existing:
            ro_skipped += 1
            continue

        conn.execute(
            text("""
                INSERT INTO refi_opportunities
                    (organization_id, mum_client_id,
                     opportunity_type, refi_score,
                     original_rate, current_balance,
                     current_market_rate, rate_advantage,
                     estimated_home_value, estimated_monthly_savings,
                     estimated_total_savings, break_even_months,
                     status, identified_at, contacted_at, outreach_count,
                     created_at)
                VALUES
                    (:org_id, :mum_id,
                     :opportunity_type, :refi_score,
                     :original_rate, :current_balance,
                     :current_market_rate, :rate_advantage,
                     :estimated_home_value, :estimated_monthly_savings,
                     :estimated_total_savings, :break_even_months,
                     :status, :identified_at, :contacted_at, :outreach_count,
                     :now)
            """),
            {
                "org_id": org_id,
                "mum_id": mum_id,
                "opportunity_type": opp["opportunity_type"],
                "refi_score": opp["refi_score"],
                "original_rate": opp["original_rate"],
                "current_balance": opp["current_balance"],
                "current_market_rate": opp["current_market_rate"],
                "rate_advantage": opp["rate_advantage"],
                "estimated_home_value": opp["estimated_home_value"],
                "estimated_monthly_savings": opp["estimated_monthly_savings"],
                "estimated_total_savings": opp["estimated_total_savings"],
                "break_even_months": opp["break_even_months"],
                "status": opp["status"],
                "identified_at": opp["identified_at"],
                "contacted_at": opp["contacted_at"],
                "outreach_count": opp["outreach_count"],
                "now": NOW,
            },
        )
        ro_inserted += 1

    conn.commit()
    print(f"✅ Seeded {ro_inserted} refi opportunities ({ro_skipped} existed)")


def seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create workflow automation records and compliance checks."""
    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # -------------------------------------------------------------------------
    # 1. Workflows
    # -------------------------------------------------------------------------
    WORKFLOWS = [
        {
            "name": "Lead Nurture",
            "description": "Automated multi-touch nurture sequence for new leads",
            "workflow_type": "lead_nurture",
            "steps": [
                {"step": 1, "action": "send_sms", "delay_hours": 0, "message": "Hi {first_name}, thanks for your interest! I'm {lo_name} — happy to answer any mortgage questions."},
                {"step": 2, "action": "send_email", "delay_hours": 24, "template": "intro_email"},
                {"step": 3, "action": "create_task", "delay_hours": 48, "task": "Follow-up call"},
                {"step": 4, "action": "send_sms", "delay_hours": 120, "message": "Hi {first_name}, just checking in — did you have a chance to review the info I sent?"},
                {"step": 5, "action": "create_task", "delay_hours": 168, "task": "7-day follow-up"},
            ],
        },
        {
            "name": "Underwriting Checklist",
            "description": "Document collection and status checklist for underwriting stage",
            "workflow_type": "underwriting",
            "steps": [
                {"step": 1, "action": "request_document", "doc_type": "w2", "message": "Please upload your W-2 for the past 2 years"},
                {"step": 2, "action": "request_document", "doc_type": "paystub", "message": "Please upload your two most recent pay stubs"},
                {"step": 3, "action": "request_document", "doc_type": "bank_statement", "message": "Please upload 2 months of bank statements"},
                {"step": 4, "action": "notify_processor", "delay_hours": 0, "message": "All documents collected — ready for UW review"},
            ],
        },
        {
            "name": "Post-Closing Follow-Up",
            "description": "Relationship maintenance sequence after loan closes",
            "workflow_type": "post_closing",
            "steps": [
                {"step": 1, "action": "send_email", "delay_days": 1, "template": "congratulations_email"},
                {"step": 2, "action": "create_task", "delay_days": 7, "task": "1-week check-in call"},
                {"step": 3, "action": "send_email", "delay_days": 30, "template": "one_month_checkup"},
                {"step": 4, "action": "create_task", "delay_days": 180, "task": "6-month rate review"},
                {"step": 5, "action": "send_email", "delay_days": 365, "template": "annual_review"},
            ],
        },
    ]

    workflow_ids = []
    for wf in WORKFLOWS:
        existing = conn.execute(
            text("SELECT id FROM workflows WHERE name = :name AND organization_id = :org_id LIMIT 1"),
            {"name": wf["name"], "org_id": org_id},
        ).fetchone()
        if existing:
            workflow_ids.append(existing[0])
            continue
        result = conn.execute(
            text("""
                INSERT INTO workflows
                    (organization_id, user_id, name, description, workflow_type,
                     steps, is_active, created_at)
                VALUES
                    (:org_id, :user_id, :name, :description, :workflow_type,
                     :steps, :is_active, :created_at)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "user_id": manager_id,
                "name": wf["name"],
                "description": wf["description"],
                "workflow_type": wf["workflow_type"],
                "steps": json.dumps(wf["steps"]),
                "is_active": True,
                "created_at": days_ago(90),
            },
        )
        wf_id = result.fetchone()[0]
        workflow_ids.append(wf_id)
    conn.commit()
    print(f"✅ Seeded {len(WORKFLOWS)} workflows")

    # -------------------------------------------------------------------------
    # 2. Workflow executions — only if scheduled_workflows table exists
    # -------------------------------------------------------------------------
    has_scheduled = conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduled_workflows')")
    ).scalar()

    if has_scheduled:
        for i, wf_id in enumerate(workflow_ids[:2]):
            already = conn.execute(
                text("SELECT id FROM workflow_executions WHERE workflow_id = :wid LIMIT 1"),
                {"wid": wf_id},
            ).fetchone()
            if already:
                continue
            started = days_ago(random.randint(5, 30))
            completed = started + timedelta(hours=random.randint(1, 6))
            conn.execute(
                text("""
                    INSERT INTO workflow_executions
                        (organization_id, workflow_id, user_id, status,
                         started_at, completed_at, targets_processed, targets_succeeded,
                         trigger_type, created_at)
                    VALUES
                        (:org_id, :workflow_id, :user_id, :status,
                         :started_at, :completed_at, :targets_processed, :targets_succeeded,
                         :trigger_type, :created_at)
                """),
                {
                    "org_id": org_id,
                    "workflow_id": wf_id,
                    "user_id": manager_id,
                    "status": "completed",
                    "started_at": started,
                    "completed_at": completed,
                    "targets_processed": random.randint(8, 20),
                    "targets_succeeded": random.randint(6, 8),
                    "trigger_type": "manual",
                    "created_at": started,
                },
            )
        conn.commit()
        print("✅ Seeded workflow executions")
    else:
        print("⏭️  Skipping workflow_executions — scheduled_workflows table not found")

    # -------------------------------------------------------------------------
    # 3. Audit logs (50 entries over 90 days)
    # -------------------------------------------------------------------------
    audit_count = conn.execute(
        text("SELECT COUNT(*) FROM audit_logs WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if audit_count and audit_count >= 50:
        print("⏭️  Audit logs exist")
    else:
        all_user_ids = [manager_id, lo_sarah_id, lo_marcus_id]
        all_lead_ids = list(lead_ids.values())[:10]
        all_loan_ids = list(loan_ids.values())[:10]

        change_types = ["login", "create", "update", "delete", "permission_grant", "export"]
        entity_types = ["user", "lead", "loan", "task", "document"]

        random.seed(42)
        for i in range(50):
            change_type = random.choice(change_types)
            entity_type = random.choice(entity_types)
            actor_id = random.choice(all_user_ids)

            if entity_type == "lead" and all_lead_ids:
                entity_id = str(random.choice(all_lead_ids))
            elif entity_type == "loan" and all_loan_ids:
                entity_id = str(random.choice(all_loan_ids))
            else:
                entity_id = str(random.choice(all_user_ids))

            ts = days_ago(random.randint(0, 90))
            conn.execute(
                text("""
                    INSERT INTO audit_logs
                        (organization_id, user_id, change_type, entity_type, entity_id,
                         ip_address, timestamp, reason)
                    VALUES
                        (:org_id, :user_id, :change_type, :entity_type, :entity_id,
                         :ip_address, :timestamp, :reason)
                """),
                {
                    "org_id": org_id,
                    "user_id": actor_id,
                    "change_type": change_type,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "ip_address": f"192.168.1.{random.randint(1, 254)}",
                    "timestamp": ts,
                    "reason": f"Demo: {change_type} on {entity_type}",
                },
            )
        conn.commit()
        print("✅ Seeded 50 audit log entries")

    # -------------------------------------------------------------------------
    # 4. Disclosure events (10 across active/funded loans)
    # -------------------------------------------------------------------------
    disc_count = conn.execute(
        text("SELECT COUNT(*) FROM disclosure_events WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if disc_count and disc_count >= 10:
        print("⏭️  Disclosure events exist")
    else:
        disclosure_loan_numbers = [
            "SHL-2026-0001", "SHL-2026-0002", "SHL-2026-0003", "SHL-2026-0004",
            "SHL-2026-0005", "SHL-2026-0006", "SHL-2026-0007", "SHL-2026-0011",
            "SHL-2026-0012", "SHL-2026-0015",
        ]
        disc_types = [
            ("loan_estimate", 3), ("loan_estimate", 8), ("revised_le", 2),
            ("loan_estimate", 5), ("loan_estimate", 7),
            ("closing_disclosure", 1), ("closing_disclosure", 3),
            ("closing_disclosure", 10), ("closing_disclosure", 15), ("revised_cd", 2),
        ]

        for idx, loan_number in enumerate(disclosure_loan_numbers):
            loan_id = loan_ids.get(loan_number)
            if not loan_id:
                continue
            disc_type, days_before_close = disc_types[idx]
            prepared_at = days_ago(days_before_close + 3)
            sent_at = days_ago(days_before_close + 1)
            received_at = days_ago(days_before_close)
            deadline = date_from_now(3) if days_before_close <= 2 else date_ago(days_before_close - 3)
            is_on_time = days_before_close >= 3

            conn.execute(
                text("""
                    INSERT INTO disclosure_events
                        (organization_id, loan_id, disclosure_type,
                         prepared_at, sent_at, received_at, deadline_date,
                         is_on_time, delivery_method, created_by_id, created_at)
                    VALUES
                        (:org_id, :loan_id, :disclosure_type,
                         :prepared_at, :sent_at, :received_at, :deadline_date,
                         :is_on_time, :delivery_method, :created_by_id, :created_at)
                """),
                {
                    "org_id": org_id,
                    "loan_id": loan_id,
                    "disclosure_type": disc_type,
                    "prepared_at": prepared_at,
                    "sent_at": sent_at,
                    "received_at": received_at,
                    "deadline_date": deadline,
                    "is_on_time": is_on_time,
                    "delivery_method": "email",
                    "created_by_id": manager_id,
                    "created_at": prepared_at,
                },
            )
        conn.commit()
        print("✅ Seeded 10 disclosure events")

    # -------------------------------------------------------------------------
    # 5. Compliance alerts (5: 2 resolved, 3 pending)
    # -------------------------------------------------------------------------
    alert_count = conn.execute(
        text("SELECT COUNT(*) FROM compliance_alerts WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if alert_count and alert_count >= 5:
        print("⏭️  Compliance alerts exist")
    else:
        # Grab some loan/lead ids for linking
        loan_id_0001 = loan_ids.get("SHL-2026-0001")
        loan_id_0003 = loan_ids.get("SHL-2026-0003")
        loan_id_0007 = loan_ids.get("SHL-2026-0007")
        lead_id_chase = list(lead_ids.values())[0] if lead_ids else None

        ALERTS = [
            # Resolved
            {
                "loan_id": loan_id_0001, "lead_id": None,
                "alert_type": "le_deadline", "severity": "high",
                "title": "Loan Estimate deadline approaching",
                "description": "LE must be delivered within 3 business days of application",
                "deadline_date": date_ago(5), "days_remaining": 0,
                "status": "resolved", "resolved_at": days_ago(6),
                "resolution_notes": "LE delivered on time via email",
            },
            {
                "loan_id": loan_id_0003, "lead_id": None,
                "alert_type": "document_expiry", "severity": "medium",
                "title": "Appraisal expiring in 30 days",
                "description": "Appraisal report will expire before projected closing date",
                "deadline_date": date_from_now(30), "days_remaining": 30,
                "status": "resolved", "resolved_at": days_ago(2),
                "resolution_notes": "Closing rescheduled to be within appraisal validity window",
            },
            # Pending
            {
                "loan_id": loan_id_0007, "lead_id": None,
                "alert_type": "rate_lock_expiry", "severity": "critical",
                "title": "Rate lock expiring in 3 days",
                "description": "Rate lock on SHL-2026-0007 expires before closing",
                "deadline_date": date_from_now(3), "days_remaining": 3,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
            {
                "loan_id": None, "lead_id": lead_id_chase,
                "alert_type": "tcpa_violation", "severity": "high",
                "title": "TCPA consent not on file",
                "description": "Outbound call attempted without verified TCPA consent record",
                "deadline_date": date_from_now(7), "days_remaining": 7,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
            {
                "loan_id": loan_id_0001, "lead_id": None,
                "alert_type": "cd_deadline", "severity": "high",
                "title": "Closing Disclosure 3-day waiting period",
                "description": "CD must be received by borrower 3 business days before closing",
                "deadline_date": date_from_now(2), "days_remaining": 2,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
        ]

        for alert in ALERTS:
            conn.execute(
                text("""
                    INSERT INTO compliance_alerts
                        (organization_id, loan_id, lead_id, alert_type, severity,
                         title, description, deadline_date, days_remaining,
                         status, resolved_at, resolved_by_id, resolution_notes, created_at)
                    VALUES
                        (:org_id, :loan_id, :lead_id, :alert_type, :severity,
                         :title, :description, :deadline_date, :days_remaining,
                         :status, :resolved_at, :resolved_by_id, :resolution_notes, :created_at)
                """),
                {
                    "org_id": org_id,
                    "loan_id": alert["loan_id"],
                    "lead_id": alert["lead_id"],
                    "alert_type": alert["alert_type"],
                    "severity": alert["severity"],
                    "title": alert["title"],
                    "description": alert["description"],
                    "deadline_date": alert["deadline_date"],
                    "days_remaining": alert["days_remaining"],
                    "status": alert["status"],
                    "resolved_at": alert["resolved_at"],
                    "resolved_by_id": manager_id if alert["resolved_at"] else None,
                    "resolution_notes": alert["resolution_notes"],
                    "created_at": days_ago(10),
                },
            )
        conn.commit()
        print("✅ Seeded 5 compliance alerts")

    # -------------------------------------------------------------------------
    # 6. Smart docs consent records (8)
    # -------------------------------------------------------------------------
    consent_count = conn.execute(
        text("SELECT COUNT(*) FROM smart_docs_consent_records WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if consent_count and consent_count >= 8:
        print("⏭️  Smart docs consent records exist")
    else:
        lead_phones = [
            (lead_ids.get("tyler.barnes@gmail.com"), "+18432110101"),
            (lead_ids.get("priya.nair@outlook.com"), "+18432110102"),
            (lead_ids.get("derek.hollis@yahoo.com"), "+18432110103"),
            (lead_ids.get("vanessa.hartley@gmail.com"), "+18432110112"),
            (lead_ids.get("tanya.morrison@gmail.com"), "+18432110114"),
            (lead_ids.get("roberto.sandoval@hotmail.com"), "+18432110115"),
            (lead_ids.get("aisha.coleman@gmail.com"), "+18432110116"),
            (lead_ids.get("michelle.osei@gmail.com"), "+18432110122"),
        ]
        channels = ["sms", "voice", "sms", "sms", "voice", "sms", "sms", "voice"]
        sources = [
            "sms_opt_in", "borrower_portal", "sms_opt_in", "borrower_portal",
            "sms_opt_in", "borrower_portal", "sms_opt_in", "borrower_portal",
        ]

        for idx, (borrower_id, phone) in enumerate(lead_phones):
            if not phone:
                continue
            conn.execute(
                text("""
                    INSERT INTO smart_docs_consent_records
                        (organization_id, borrower_id, phone, channel,
                         consent_given, consent_source, consented_at, created_at)
                    VALUES
                        (:org_id, :borrower_id, :phone, :channel,
                         :consent_given, :consent_source, :consented_at, :created_at)
                """),
                {
                    "org_id": org_id,
                    "borrower_id": borrower_id,
                    "phone": phone,
                    "channel": channels[idx],
                    "consent_given": True,
                    "consent_source": sources[idx],
                    "consented_at": days_ago(random.randint(1, 30)),
                    "created_at": days_ago(random.randint(1, 30)),
                },
            )
        conn.commit()
        print("✅ Seeded 8 smart docs consent records")


def seed_borrower_portal(conn, org_id, lead_ids, loan_ids):
    """Create borrower portal sessions and document requests."""
    # Gather some active loan leads for linking
    active_lead_entries = [
        ("tanya.morrison@gmail.com", "SHL-2026-0001", "Tanya", "Morrison"),
        ("roberto.sandoval@hotmail.com", "SHL-2026-0002", "Roberto", "Sandoval"),
        ("vanessa.hartley@gmail.com", "SHL-2026-0003", "Vanessa", "Hartley"),
        ("aisha.coleman@gmail.com", "SHL-2026-0004", "Aisha", "Coleman"),
        ("marcus.delacroix@icloud.com", "SHL-2026-0005", "Marcus", "Delacroix"),
    ]
    providers = ["email", "email", "google", "email", "apple"]

    # -------------------------------------------------------------------------
    # 1. Borrower profiles (5)
    # -------------------------------------------------------------------------
    profile_ids = {}
    for idx, (email, loan_number, first, last) in enumerate(active_lead_entries):
        existing = conn.execute(
            text("SELECT id FROM borrower_profiles WHERE email = :email AND organization_id = :org_id LIMIT 1"),
            {"email": email, "org_id": org_id},
        ).fetchone()
        if existing:
            profile_ids[email] = existing[0]
            continue

        provider = providers[idx]
        profile_uuid = str(uuid.uuid4())
        conn.execute(
            text("""
                INSERT INTO borrower_profiles
                    (id, organization_id, email, first_name, last_name,
                     provider, provider_user_id,
                     communication_consent, marketing_consent, consent_captured_at, created_at)
                VALUES
                    (:id, :org_id, :email, :first_name, :last_name,
                     :provider, :provider_user_id,
                     :comm_consent, :mkt_consent, :consent_captured_at, :created_at)
            """),
            {
                "id": profile_uuid,
                "org_id": org_id,
                "email": email,
                "first_name": first,
                "last_name": last,
                "provider": provider,
                "provider_user_id": str(uuid.uuid4()),
                "comm_consent": True,
                "mkt_consent": idx % 2 == 0,
                "consent_captured_at": days_ago(random.randint(5, 60)),
                "created_at": days_ago(random.randint(5, 60)),
            },
        )
        profile_ids[email] = profile_uuid

    conn.commit()
    print(f"✅ Seeded {len(active_lead_entries)} borrower profiles")

    # -------------------------------------------------------------------------
    # 2. Borrower applications (5)
    # -------------------------------------------------------------------------
    # status/step combos: 2 submitted, 1 in_progress, 1 draft, 1 approved
    APP_SPECS = [
        {"status": "submitted",  "step": "credit_auth",  "progress": 100, "email": "tanya.morrison@gmail.com",           "loan": "SHL-2026-0001"},
        {"status": "submitted",  "step": "credit_auth",  "progress": 100, "email": "roberto.sandoval@hotmail.com",        "loan": "SHL-2026-0002"},
        {"status": "in_progress","step": "income",       "progress": 60,  "email": "vanessa.hartley@gmail.com",           "loan": "SHL-2026-0003"},
        {"status": "draft",      "step": "personal_info","progress": 20,  "email": "aisha.coleman@gmail.com",             "loan": "SHL-2026-0004"},
        {"status": "approved",   "step": "credit_auth",  "progress": 100, "email": "marcus.delacroix@icloud.com",         "loan": "SHL-2026-0005"},
    ]

    app_ids = {}
    for spec in APP_SPECS:
        email = spec["email"]
        lead_id = lead_ids.get(email)
        loan_id = loan_ids.get(spec["loan"])
        profile_id = profile_ids.get(email)

        # Look up owner_id from lead
        owner_row = conn.execute(
            text("SELECT owner_id, first_name, last_name FROM leads WHERE id = :lid LIMIT 1"),
            {"lid": lead_id},
        ).fetchone() if lead_id else None
        owner_id = owner_row[0] if owner_row else None
        first_name = owner_row[1] if owner_row else ""
        last_name = owner_row[2] if owner_row else ""

        existing = conn.execute(
            text("SELECT id FROM borrower_applications WHERE lead_id = :lid LIMIT 1"),
            {"lid": lead_id},
        ).fetchone() if lead_id else None
        if existing:
            app_ids[email] = existing[0]
            continue

        pub_token = secrets.token_hex(32)
        started_at = days_ago(random.randint(5, 30))
        submitted_at = started_at + timedelta(days=1) if spec["status"] in ("submitted", "approved") else None

        result = conn.execute(
            text("""
                INSERT INTO borrower_applications
                    (public_token, borrower_profile_id, lead_id, loan_id,
                     owner_id, organization_id, status, current_step,
                     progress_percentage, borrower_first_name, borrower_last_name, borrower_email,
                     started_at, submitted_at, created_at)
                VALUES
                    (:public_token, :borrower_profile_id, :lead_id, :loan_id,
                     :owner_id, :org_id, :status, :current_step,
                     :progress_percentage, :borrower_first_name, :borrower_last_name, :borrower_email,
                     :started_at, :submitted_at, :created_at)
                RETURNING id
            """),
            {
                "public_token": pub_token,
                "borrower_profile_id": profile_id,
                "lead_id": lead_id,
                "loan_id": loan_id,
                "owner_id": owner_id,
                "org_id": org_id,
                "status": spec["status"],
                "current_step": spec["step"],
                "progress_percentage": spec["progress"],
                "borrower_first_name": first_name,
                "borrower_last_name": last_name,
                "borrower_email": email,
                "started_at": started_at,
                "submitted_at": submitted_at,
                "created_at": started_at,
            },
        )
        app_id = result.fetchone()[0]
        app_ids[email] = app_id

    conn.commit()
    print(f"✅ Seeded {len(APP_SPECS)} borrower applications")

    # -------------------------------------------------------------------------
    # 3. Application events (3-5 per application)
    # -------------------------------------------------------------------------
    events_inserted = 0
    for email, app_id in app_ids.items():
        existing_count = conn.execute(
            text("SELECT COUNT(*) FROM application_events WHERE application_id = :aid"),
            {"aid": app_id},
        ).scalar()
        if existing_count and existing_count >= 3:
            continue

        event_chain = [
            ("application_started", "application_started", None, days_ago(20)),
            ("step_started", "step_completed", "personal_info", days_ago(19)),
            ("step_completed", "step_completed", "property", days_ago(18)),
            ("step_started", "step_completed", "income", days_ago(17)),
            ("application_submitted", "application_submitted", None, days_ago(16)),
        ]
        for ev_type, _ev, step, ts in event_chain[:random.randint(3, 5)]:
            conn.execute(
                text("""
                    INSERT INTO application_events
                        (application_id, event_type, event_data, step, created_at)
                    VALUES
                        (:app_id, :event_type, :event_data, :step, :created_at)
                """),
                {
                    "app_id": app_id,
                    "event_type": ev_type,
                    "event_data": json.dumps({"step": step, "email": email}),
                    "step": step,
                    "created_at": ts,
                },
            )
            events_inserted += 1

    conn.commit()
    print(f"✅ Seeded {events_inserted} application events")

    # -------------------------------------------------------------------------
    # 4. Co-borrower invitations (2: 1 accepted, 1 pending)
    # -------------------------------------------------------------------------
    inv_count = conn.execute(
        text("""
            SELECT COUNT(*) FROM coborrower_invitations
            WHERE application_id = ANY(:ids)
        """),
        {"ids": list(app_ids.values())[:2]},
    ).scalar()

    if inv_count and inv_count >= 2:
        print("⏭️  Coborrower invitations exist")
    else:
        app_list = list(app_ids.values())
        if len(app_list) >= 2:
            invitations = [
                {
                    "application_id": app_list[0],
                    "email": "coborrower1@gmail.com",
                    "first_name": "Jordan",
                    "relationship_type": "spouse",
                    "status": "accepted",
                    "sent_at": days_ago(10),
                    "completed_at": days_ago(8),
                },
                {
                    "application_id": app_list[1],
                    "email": "coborrower2@gmail.com",
                    "first_name": "Taylor",
                    "relationship_type": "co_borrower",
                    "status": "pending",
                    "sent_at": days_ago(3),
                    "completed_at": None,
                },
            ]
            for inv in invitations:
                conn.execute(
                    text("""
                        INSERT INTO coborrower_invitations
                            (application_id, invitation_token, email, first_name,
                             relationship_type, status, sent_at, completed_at, created_at)
                        VALUES
                            (:app_id, :invitation_token, :email, :first_name,
                             :relationship_type, :status, :sent_at, :completed_at, :created_at)
                    """),
                    {
                        "app_id": inv["application_id"],
                        "invitation_token": secrets.token_hex(32),
                        "email": inv["email"],
                        "first_name": inv["first_name"],
                        "relationship_type": inv["relationship_type"],
                        "status": inv["status"],
                        "sent_at": inv["sent_at"],
                        "completed_at": inv["completed_at"],
                        "created_at": inv["sent_at"],
                    },
                )
            conn.commit()
            print("✅ Seeded 2 coborrower invitations")


def seed_content_and_campaigns(conn, org_id, user_ids, lead_ids):
    """Create content pieces and marketing campaign records."""
    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")

    # -------------------------------------------------------------------------
    # 1. Aria campaigns (2)
    # -------------------------------------------------------------------------
    CAMPAIGNS = [
        {
            "name": "Rate Drop Alert — May 2026",
            "description": "Notify eligible prospects of a 25bps rate improvement",
            "filter_criteria": {"min_loan_amount": 250000, "stages": ["Pre-Qualified", "Prospect"], "loan_type": "Conventional"},
            "message_template": "Hi {first_name}! Rates just dropped 0.25% — you could save ${monthly_savings}/mo on your {loan_amount} purchase. Want to lock in before rates move? Reply YES or call us.",
            "status": "completed",
            "recipient_count": 15,
            "sent_count": 15,
            "replied_count": 6,
            "booked_count": 3,
            "created_at": days_ago(14),
            "completed_at": days_ago(13),
        },
        {
            "name": "Spring Home Buying Season — Outreach",
            "description": "Holiday greeting and market update for nurture list",
            "filter_criteria": {"stages": ["Long-Term Nurture", "Credit Repair"], "min_days_since_contact": 30},
            "message_template": "Hi {first_name}, spring buying season is here! Rates and inventory are moving fast. Let's connect before you miss your window — reply CALL to schedule time with {lo_name}.",
            "status": "sending",
            "recipient_count": 10,
            "sent_count": 7,
            "replied_count": 2,
            "booked_count": 1,
            "created_at": days_ago(1),
            "completed_at": None,
        },
    ]

    campaign_ids = []
    for camp in CAMPAIGNS:
        existing = conn.execute(
            text("SELECT id FROM aria_campaigns WHERE name = :name AND organization_id = :org_id LIMIT 1"),
            {"name": camp["name"], "org_id": org_id},
        ).fetchone()
        if existing:
            campaign_ids.append(existing[0])
            continue

        result = conn.execute(
            text("""
                INSERT INTO aria_campaigns
                    (organization_id, created_by_user_id, name, description,
                     filter_criteria, message_template, status,
                     recipient_count, sent_count, replied_count, booked_count,
                     created_at, completed_at)
                VALUES
                    (:org_id, :created_by, :name, :description,
                     :filter_criteria, :message_template, :status,
                     :recipient_count, :sent_count, :replied_count, :booked_count,
                     :created_at, :completed_at)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "created_by": manager_id,
                "name": camp["name"],
                "description": camp["description"],
                "filter_criteria": json.dumps(camp["filter_criteria"]),
                "message_template": camp["message_template"],
                "status": camp["status"],
                "recipient_count": camp["recipient_count"],
                "sent_count": camp["sent_count"],
                "replied_count": camp["replied_count"],
                "booked_count": camp["booked_count"],
                "created_at": camp["created_at"],
                "completed_at": camp["completed_at"],
            },
        )
        campaign_ids.append(result.fetchone()[0])

    conn.commit()
    print(f"✅ Seeded {len(CAMPAIGNS)} Aria campaigns")

    # -------------------------------------------------------------------------
    # 2. Campaign recipients
    # -------------------------------------------------------------------------
    RECIPIENT_LEADS = [
        ("brianna.okafor@gmail.com", "+18432110106", "Brianna"),
        ("kevin.albright@gmail.com", "+18432110109", "Kevin"),
        ("jasmine.winters@yahoo.com", "+18432110110", "Jasmine"),
        ("elijah.fontaine@gmail.com", "+18432110111", "Elijah"),
        ("gregory.tatum@yahoo.com", "+18432110117", "Gregory"),
        ("courtney.langford@gmail.com", "+18432110118", "Courtney"),
        ("antoine.devereaux@gmail.com", "+18432110119", "Antoine"),
        ("darnell.pace@gmail.com", "+18432110120", "Darnell"),
    ]

    recip_inserted = 0
    for c_idx, camp_id in enumerate(campaign_ids):
        existing_count = conn.execute(
            text("SELECT COUNT(*) FROM aria_campaign_recipients WHERE campaign_id = :cid"),
            {"cid": camp_id},
        ).scalar()
        if existing_count and existing_count > 0:
            continue

        for r_idx, (email, phone, first_name) in enumerate(RECIPIENT_LEADS):
            lead_id = lead_ids.get(email)
            if c_idx == 0:
                status = "replied" if r_idx < 6 else "sent"
                sent_at = days_ago(13)
                replied_at = days_ago(12) if status == "replied" else None
            else:
                status = "sent" if r_idx < 7 else "pending"
                sent_at = days_ago(1) if status == "sent" else None
                replied_at = days_ago(1) if r_idx < 2 else None

            conn.execute(
                text("""
                    INSERT INTO aria_campaign_recipients
                        (campaign_id, lead_id, phone, email, first_name,
                         status, sent_at, replied_at)
                    VALUES
                        (:camp_id, :lead_id, :phone, :email, :first_name,
                         :status, :sent_at, :replied_at)
                """),
                {
                    "camp_id": camp_id,
                    "lead_id": lead_id,
                    "phone": phone,
                    "email": email,
                    "first_name": first_name,
                    "status": status,
                    "sent_at": sent_at,
                    "replied_at": replied_at,
                },
            )
            recip_inserted += 1

    conn.commit()
    print(f"✅ Seeded {recip_inserted} campaign recipients")

    # -------------------------------------------------------------------------
    # 3. Drip sequences (2)
    # -------------------------------------------------------------------------
    DRIP_SEQUENCES = [
        {
            "name": "New Lead Nurture — 5 Touch",
            "description": "Automated 5-step nurture for new leads over 14 days",
            "trigger_event": "lead_created",
            "steps": [
                {"day": 0,  "action": "sms",   "message": "Hi {first_name}! I'm {lo_name} — just saw your inquiry. When's a good time to chat about your home purchase goals?"},
                {"day": 1,  "action": "email",  "template": "intro_value_prop"},
                {"day": 3,  "action": "sms",    "message": "Hi {first_name}, just following up — did you get my email? Happy to answer any questions!"},
                {"day": 7,  "action": "email",  "template": "mortgage_guide"},
                {"day": 14, "action": "task",   "task": "Manual follow-up call if no response"},
            ],
            "is_active": True,
            "total_enrolled": 28,
            "total_completed": 19,
            "created_at": days_ago(60),
        },
        {
            "name": "Post-Close Follow-Up — 3 Touch",
            "description": "Relationship maintenance after loan funding",
            "trigger_event": "loan_funded",
            "steps": [
                {"day": 1,   "action": "email",  "template": "congratulations"},
                {"day": 30,  "action": "sms",    "message": "Hi {first_name}, hope you're settling in well! Let me know if you ever need anything — I'm always here. – {lo_name}"},
                {"day": 365, "action": "email",  "template": "annual_review_offer"},
            ],
            "is_active": True,
            "total_enrolled": 12,
            "total_completed": 8,
            "created_at": days_ago(90),
        },
    ]

    drip_inserted = 0
    for drip in DRIP_SEQUENCES:
        existing = conn.execute(
            text("SELECT id FROM drip_sequences WHERE name = :name AND organization_id = :org_id LIMIT 1"),
            {"name": drip["name"], "org_id": org_id},
        ).fetchone()
        if existing:
            continue
        conn.execute(
            text("""
                INSERT INTO drip_sequences
                    (organization_id, created_by_id, name, description, trigger_event,
                     steps, is_active, total_enrolled, total_completed, created_at)
                VALUES
                    (:org_id, :created_by, :name, :description, :trigger_event,
                     :steps, :is_active, :total_enrolled, :total_completed, :created_at)
            """),
            {
                "org_id": org_id,
                "created_by": lo_sarah_id,
                "name": drip["name"],
                "description": drip["description"],
                "trigger_event": drip["trigger_event"],
                "steps": json.dumps(drip["steps"]),
                "is_active": drip["is_active"],
                "total_enrolled": drip["total_enrolled"],
                "total_completed": drip["total_completed"],
                "created_at": drip["created_at"],
            },
        )
        drip_inserted += 1

    conn.commit()
    print(f"✅ Seeded {drip_inserted} drip sequences")


def seed_team_chat(conn, org_id, user_ids):
    """Create team chat channel messages."""
    # -------------------------------------------------------------------------
    # Check if client_files table exists
    # -------------------------------------------------------------------------
    has_client_files = conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'client_files')")
    ).scalar()

    if not has_client_files:
        print("⏭️  Skipping team chat — client_files table not found")
        return

    # Check if there are any client_files records
    cf_row = conn.execute(
        text("SELECT id FROM client_files WHERE organization_id = :org_id LIMIT 1"),
        {"org_id": org_id},
    ).fetchone()

    if not cf_row:
        print("⏭️  Skipping team chat — no client_files records found")
        return

    client_file_id = str(cf_row[0])
    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    processor_id = user_ids.get("processor")

    # -------------------------------------------------------------------------
    # Create team chat channel
    # -------------------------------------------------------------------------
    channel_id_str = str(uuid.uuid4())
    existing_channel = conn.execute(
        text("SELECT id FROM team_chat_channels WHERE client_file_id = :cfid LIMIT 1"),
        {"cfid": client_file_id},
    ).fetchone()

    if existing_channel:
        channel_id_str = str(existing_channel[0])
        print("⏭️  Team chat channel exists")
    else:
        conn.execute(
            text("""
                INSERT INTO team_chat_channels
                    (id, organization_id, client_file_id, created_at)
                VALUES
                    (:id, :org_id, :client_file_id, :created_at)
            """),
            {
                "id": channel_id_str,
                "org_id": org_id,
                "client_file_id": client_file_id,
                "created_at": days_ago(10),
            },
        )
        conn.commit()
        print(f"✅ Created team chat channel (id={channel_id_str})")

    # -------------------------------------------------------------------------
    # Create team chat messages
    # -------------------------------------------------------------------------
    msg_count = conn.execute(
        text("SELECT COUNT(*) FROM team_chat_messages WHERE channel_id = :cid"),
        {"cid": channel_id_str},
    ).scalar()

    if msg_count and msg_count >= 3:
        print("⏭️  Team chat messages exist")
        return

    MESSAGES = [
        {
            "author_user_id": lo_sarah_id,
            "author_kind": "human",
            "body": "Just got off the phone — borrower confirmed they're uploading W-2s today.",
            "created_at": days_ago(9),
        },
        {
            "author_user_id": processor_id,
            "author_kind": "human",
            "body": "Got it! I'll watch for the upload and move this to UW once I have all three docs.",
            "created_at": days_ago(8),
        },
        {
            "author_user_id": manager_id,
            "author_kind": "human",
            "body": "Great teamwork. @Emily let me know if the appraisal comes back below value — we may need to renegotiate.",
            "created_at": days_ago(7),
        },
        {
            "author_user_id": None,
            "author_kind": "system",
            "body": "Loan stage changed: PROCESSING → SUBMITTED",
            "created_at": days_ago(6),
        },
        {
            "author_user_id": lo_sarah_id,
            "author_kind": "human",
            "body": "Submitted to UW. Rachel has it — estimated 48-hour turnaround.",
            "created_at": days_ago(5),
        },
    ]

    for msg in MESSAGES:
        msg_id = str(uuid.uuid4())
        conn.execute(
            text("""
                INSERT INTO team_chat_messages
                    (id, organization_id, channel_id, client_file_id,
                     author_kind, author_user_id, body,
                     mentioned_user_ids, attachments, created_at)
                VALUES
                    (:id, :org_id, :channel_id, :client_file_id,
                     :author_kind, :author_user_id, :body,
                     :mentioned_user_ids, :attachments, :created_at)
            """),
            {
                "id": msg_id,
                "org_id": org_id,
                "channel_id": channel_id_str,
                "client_file_id": client_file_id,
                "author_kind": msg["author_kind"],
                "author_user_id": msg["author_user_id"],
                "body": msg["body"],
                "mentioned_user_ids": "{}",
                "attachments": "[]",
                "created_at": msg["created_at"],
            },
        )

    conn.commit()
    print(f"✅ Seeded {len(MESSAGES)} team chat messages")


def seed_notifications(conn, org_id, user_ids):
    """Create demo in-app notification records."""
    manager_id = user_ids.get("manager")
    if not manager_id:
        print("⚠️  No manager user — skipping notifications")
        return

    # -------------------------------------------------------------------------
    # 1. In-app notifications (15 for manager, spread over last 24 hours)
    # -------------------------------------------------------------------------
    notif_count = conn.execute(
        text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid AND organization_id = :org_id"),
        {"uid": manager_id, "org_id": org_id},
    ).scalar()

    if notif_count and notif_count >= 15:
        print("⏭️  Notifications exist")
    else:
        NOTIFICATIONS = [
            {
                "type": "new_lead",
                "title": "New Lead Assigned",
                "message": "Derek Hollis submitted a rate inquiry via your website — high AI score (88).",
                "link": "/leads",
                "is_read": False,
                "minutes_ago": 15,
            },
            {
                "type": "document_uploaded",
                "title": "Document Uploaded",
                "message": "Tanya Morrison uploaded W-2 (2024) for loan SHL-2026-0001.",
                "link": "/loans/SHL-2026-0001",
                "is_read": False,
                "minutes_ago": 45,
            },
            {
                "type": "rate_lock_expiring",
                "title": "Rate Lock Expiring Soon",
                "message": "Rate lock on SHL-2026-0007 (Jasmine Winters) expires in 3 days.",
                "link": "/loans/SHL-2026-0007",
                "is_read": False,
                "minutes_ago": 90,
            },
            {
                "type": "task_overdue",
                "title": "Task Overdue",
                "message": "Follow-up call with Carter Webb is 2 days overdue.",
                "link": "/tasks",
                "is_read": True,
                "minutes_ago": 120,
            },
            {
                "type": "loan_stage_changed",
                "title": "Loan Stage Updated",
                "message": "SHL-2026-0005 (Marcus Delacroix) moved to SUBMITTED by Emily Park.",
                "link": "/loans/SHL-2026-0005",
                "is_read": False,
                "minutes_ago": 180,
            },
            {
                "type": "compliance_alert",
                "title": "Compliance Alert",
                "message": "CD 3-day waiting period applies to SHL-2026-0001 — closing in 2 days.",
                "link": "/compliance",
                "is_read": False,
                "minutes_ago": 210,
            },
            {
                "type": "appointment_reminder",
                "title": "Appointment in 30 Minutes",
                "message": "Discovery call with Brianna Okafor starts at 2:00 PM.",
                "link": "/calendar",
                "is_read": True,
                "minutes_ago": 270,
            },
            {
                "type": "team_activity",
                "title": "Team Activity",
                "message": "Sarah Chen closed 2 new applications this week — great work!",
                "link": "/team",
                "is_read": True,
                "minutes_ago": 360,
            },
            {
                "type": "new_lead",
                "title": "New Lead Assigned",
                "message": "Priya Nair responded to your Facebook ad — FHA inquiry.",
                "link": "/leads",
                "is_read": True,
                "minutes_ago": 420,
            },
            {
                "type": "document_uploaded",
                "title": "Document Uploaded",
                "message": "Roberto Sandoval uploaded Bank Statements (Jan–Feb) for SHL-2026-0002.",
                "link": "/loans/SHL-2026-0002",
                "is_read": True,
                "minutes_ago": 480,
            },
            {
                "type": "loan_stage_changed",
                "title": "Loan Stage Updated",
                "message": "SHL-2026-0008 (Brianna Okafor) reached CONDITIONAL_APPROVAL.",
                "link": "/loans/SHL-2026-0008",
                "is_read": True,
                "minutes_ago": 540,
            },
            {
                "type": "team_activity",
                "title": "AI Campaign Complete",
                "message": "Rate Drop Alert campaign finished — 6/15 replied, 3 appointments booked.",
                "link": "/campaigns",
                "is_read": True,
                "minutes_ago": 600,
            },
            {
                "type": "task_overdue",
                "title": "Task Overdue",
                "message": "Request tax transcripts for Elijah Fontaine is 1 day overdue.",
                "link": "/tasks",
                "is_read": True,
                "minutes_ago": 720,
            },
            {
                "type": "appointment_reminder",
                "title": "Upcoming Appointment",
                "message": "Rate review call with Kevin Albright is tomorrow at 10:00 AM.",
                "link": "/calendar",
                "is_read": True,
                "minutes_ago": 900,
            },
            {
                "type": "compliance_alert",
                "title": "TCPA Consent Missing",
                "message": "Outbound call blocked — TCPA consent not on file for Monique Duval.",
                "link": "/compliance",
                "is_read": True,
                "minutes_ago": 1200,
            },
        ]

        for notif in NOTIFICATIONS:
            ts = NOW - timedelta(minutes=notif["minutes_ago"])
            conn.execute(
                text("""
                    INSERT INTO notifications
                        (organization_id, user_id, type, title, message,
                         link, is_read, created_at)
                    VALUES
                        (:org_id, :user_id, :type, :title, :message,
                         :link, :is_read, :created_at)
                """),
                {
                    "org_id": org_id,
                    "user_id": manager_id,
                    "type": notif["type"],
                    "title": notif["title"],
                    "message": notif["message"],
                    "link": notif["link"],
                    "is_read": notif["is_read"],
                    "created_at": ts,
                },
            )

        conn.commit()
        print("✅ Seeded 15 notifications")

    # -------------------------------------------------------------------------
    # 2. System alerts (5)
    # -------------------------------------------------------------------------
    sys_alert_count = conn.execute(
        text("SELECT COUNT(*) FROM system_alerts"),
    ).scalar()

    if sys_alert_count and sys_alert_count >= 5:
        print("⏭️  System alerts exist")
    else:
        SYSTEM_ALERTS = [
            {
                "alert_type": "integration_health",
                "severity": "warning",
                "title": "Microsoft Graph Token Expired",
                "message": "Email integration for demo@perenniaai.com requires re-authentication.",
                "suggested_action": "Navigate to Settings > Integrations and reconnect Microsoft 365.",
                "is_resolved": True,
                "resolved_at": days_ago(1),
                "created_at": days_ago(2),
            },
            {
                "alert_type": "rate_threshold",
                "severity": "info",
                "title": "Rate Threshold Breach — 30-Year Conventional",
                "message": "30-year conventional rates crossed below 6.75% — 8 clients eligible for refi review.",
                "suggested_action": "Run Aria rate-drop campaign for eligible MUM portfolio clients.",
                "is_resolved": False,
                "resolved_at": None,
                "created_at": days_ago(1),
            },
            {
                "alert_type": "sla_warning",
                "severity": "warning",
                "title": "SLA Warning — Underwriting Turnaround",
                "message": "2 loans in UNDERWRITING have exceeded the 7-day SLA target.",
                "suggested_action": "Escalate SHL-2026-0007 and SHL-2026-0006 with underwriting team.",
                "is_resolved": False,
                "resolved_at": None,
                "created_at": days_ago(3),
            },
            {
                "alert_type": "storage_usage",
                "severity": "info",
                "title": "Document Storage at 78% Capacity",
                "message": "Organization document storage is approaching the plan limit.",
                "suggested_action": "Archive closed loan documents or upgrade storage tier.",
                "is_resolved": True,
                "resolved_at": days_ago(5),
                "created_at": days_ago(7),
            },
            {
                "alert_type": "scheduled_maintenance",
                "severity": "info",
                "title": "Scheduled Maintenance — Completed",
                "message": "Database maintenance window completed successfully. All services nominal.",
                "suggested_action": None,
                "is_resolved": True,
                "resolved_at": days_ago(10),
                "created_at": days_ago(10),
            },
        ]

        for alert in SYSTEM_ALERTS:
            conn.execute(
                text("""
                    INSERT INTO system_alerts
                        (alert_type, severity, title, message,
                         suggested_action, is_resolved, resolved_at, created_at)
                    VALUES
                        (:alert_type, :severity, :title, :message,
                         :suggested_action, :is_resolved, :resolved_at, :created_at)
                """),
                {
                    "alert_type": alert["alert_type"],
                    "severity": alert["severity"],
                    "title": alert["title"],
                    "message": alert["message"],
                    "suggested_action": alert["suggested_action"],
                    "is_resolved": alert["is_resolved"],
                    "resolved_at": alert["resolved_at"],
                    "created_at": alert["created_at"],
                },
            )

        conn.commit()
        print("✅ Seeded 5 system alerts")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main():
    # SECURITY: never seed demo accounts (with their fixed password) in production,
    # and refuse to run without an explicitly configured demo password.
    environment = os.environ.get("ENVIRONMENT", os.environ.get("RAILWAY_ENVIRONMENT", "development"))
    if environment.lower() in ("production", "prod"):
        print("ERROR: Refusing to run demo seed in production (ENVIRONMENT=production).")
        sys.exit(1)
    if not DEMO_PASSWORD:
        print("ERROR: DEMO_USER_PASSWORD environment variable is required to seed the demo account.")
        sys.exit(1)

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
