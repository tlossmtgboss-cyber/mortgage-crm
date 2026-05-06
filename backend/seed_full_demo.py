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
