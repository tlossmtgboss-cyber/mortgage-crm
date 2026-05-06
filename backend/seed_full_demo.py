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
