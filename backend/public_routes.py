"""
Public Routes for Registration, Email Verification, and Onboarding

These endpoints don't require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
import logging
import os

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

from db import get_db

# ── Table / column / enum whitelists for dynamic SQL (prevent injection) ──
_ENUM_FIX_TABLES = frozenset({
    "leads", "loans", "documents", "disclosure_events", "loan_fees",
    "availability_slots", "scheduler_appointments", "scheduler_configs",
    "appointment_types", "tasks", "compliance_alerts", "referral_partners",
    "mum_clients",
})
_ENUM_FIX_COLUMNS = frozenset({
    "stage", "purpose", "match_status", "classification_status",
    "classified_doc_type", "classified_doc_category", "disclosure_type",
    "tolerance_category", "day_of_week", "priority", "meeting_mode",
    "meeting_type", "status", "default_meeting_mode", "routing_strategy",
    "default_mode", "type", "severity", "category",
    "doc_type", "doc_category",
})
_ENUM_FIX_TYPES = frozenset({
    "leadstage", "loanstage", "loanpurpose", "emailintakematchstatus",
    "attachmentclassificationstatus", "disclosuretype", "tolerancecategory",
    "dayofweek", "slotpriority", "meetingmode", "meetingtype",
    "appointmentstatus", "tasktype",
})
_DEMO_CLEANUP_TABLES = frozenset({
    "morning_briefings", "stage_history", "disclosure_events", "loan_fees",
    "compliance_alerts", "scheduler_appointments", "availability_slots",
    "appointment_types", "scheduler_configs",
    "loan_team_members", "mum_clients",
    "ai_tasks", "tasks", "activities", "documents",
    "email_intakes", "attachment_intakes",
    "loans", "leads", "referral_partners",
})
# from integrations.stripe_service import StripeService  # Disabled for now
from integrations.email_service import EmailService, VerificationTokenService

logger = logging.getLogger(__name__)

router = APIRouter()

# Use canonical token creation from auth module (RS256, jti, blacklist-compatible)
from auth.tokens import create_access_token

# Initialize services
# Stripe service disabled for now - using mock
class MockStripeService:
    """Mock Stripe service when Stripe is not configured"""

    PLANS = {
        "starter": {
            "name": "Starter",
            "price_monthly": 99,
            "stripe_price_id": "price_starter",
            "features": [
                "Up to 5 team members",
                "1,000 leads per month",
                "Basic AI assistant",
                "Email support",
                "Calendar integration",
                "Task automation"
            ],
            "user_limit": 5
        },
        "professional": {
            "name": "Professional",
            "price_monthly": 199,
            "stripe_price_id": "price_professional",
            "features": [
                "Up to 15 team members",
                "Unlimited leads",
                "Advanced AI assistant with workflow automation",
                "Priority support",
                "Calendar + Email + Teams integration",
                "Custom workflows",
                "SMS notifications",
                "Analytics & reporting"
            ],
            "user_limit": 15
        },
        "enterprise": {
            "name": "Enterprise",
            "price_monthly": 399,
            "stripe_price_id": "price_enterprise",
            "features": [
                "Unlimited team members",
                "Unlimited leads",
                "Full AI agent capabilities",
                "24/7 dedicated support",
                "All integrations",
                "Custom AI training",
                "White-label options",
                "API access",
                "Custom reporting"
            ],
            "user_limit": 999
        }
    }

    def get_plan_info(self, plan):
        return self.PLANS.get(plan)

    def create_customer(self, *args, **kwargs):
        return None

    def create_subscription(self, *args, **kwargs):
        return None

    def get_all_plans(self):
        return [
            {
                "key": key,
                **plan_info
            }
            for key, plan_info in self.PLANS.items()
        ]

    def verify_webhook_signature(self, *args, **kwargs):
        return None

stripe_service = MockStripeService()
email_service = EmailService()


# ============================================================================
# QUICK TEST/DEMO USER SETUP
# ============================================================================

@router.post("/api/v1/create-demo-user")
async def create_demo_user(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db),
):
    """
    Create or reset the demo@perenniaai.com account for App Store review.
    Requires ADMIN_API_KEY. Password is read from DEMO_USER_PASSWORD env var.
    Returns actual error details (bypasses production error sanitizer).
    """
    import os as _os
    import hmac as _hmac
    import traceback as _tb
    from fastapi.responses import JSONResponse as _JSONResponse
    _admin_api_key = _os.getenv("ADMIN_API_KEY")
    if not _admin_api_key or not _hmac.compare_digest(admin_key, _admin_api_key):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from main import get_password_hash
        from sqlalchemy import text as _text

        demo_email = "demo@perenniaai.com"
        demo_password = _os.getenv("DEMO_USER_PASSWORD", "")
        if not demo_password:
            raise HTTPException(status_code=500, detail="DEMO_USER_PASSWORD env var required")
        now = datetime.now(timezone.utc)
        org_slug = "summit-peak-demo-appstore"

        # Use raw SQL to avoid ORM column mismatch with production DB
        org_row = db.execute(_text("SELECT id FROM organizations WHERE slug = :s"), {"s": org_slug}).fetchone()
        if org_row:
            org_id = org_row[0]
        else:
            db.execute(_text("""
                INSERT INTO organizations (name, slug, domain, subscription_tier, is_active, created_at)
                VALUES (:name, :slug, :domain, :tier, TRUE, :now)
            """), {"name": "Summit Peak Mortgage", "slug": org_slug,
                   "domain": "summitpeakdemo.com", "tier": "professional", "now": now})
            org_id = db.execute(_text("SELECT id FROM organizations WHERE slug = :s"), {"s": org_slug}).scalar()

        hashed = get_password_hash(demo_password)

        user_row = db.execute(_text("SELECT id FROM users WHERE email = :e"), {"e": demo_email}).fetchone()
        if user_row:
            db.execute(_text(
                "UPDATE users SET hashed_password = :h, organization_id = :oid, is_active = TRUE, "
                "email_verified = TRUE, role = 'loan_officer', permission_role = 'sales' WHERE email = :e"
            ), {"h": hashed, "e": demo_email, "oid": org_id})
            db.commit()
            return {"status": "updated", "email": demo_email, "org_id": org_id}

        db.execute(_text("""
            INSERT INTO users (email, hashed_password, first_name, last_name, role, permission_role,
                              organization_id, is_active, email_verified, created_at)
            VALUES (:email, :hash, 'Demo', 'User', 'loan_officer', 'sales', :oid, TRUE, TRUE, :now)
        """), {"email": demo_email, "hash": hashed, "oid": org_id, "now": now})

        user_id = db.execute(_text("SELECT id FROM users WHERE email = :e"), {"e": demo_email}).scalar()

        # Subscription (upsert)
        sub_exists = db.execute(_text("SELECT id FROM subscriptions WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if not sub_exists:
            db.execute(_text("""
                INSERT INTO subscriptions (user_id, stripe_customer_id, stripe_subscription_id,
                                          status, current_period_start, current_period_end)
                VALUES (:uid, 'demo_customer', 'demo_subscription', 'active', :now, :end)
            """), {"uid": user_id, "now": now, "end": now + timedelta(days=365)})

        # Onboarding (upsert)
        ob_exists = db.execute(_text("SELECT id FROM onboarding_progress WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if not ob_exists:
            db.execute(_text("""
                INSERT INTO onboarding_progress (user_id, current_step, steps_completed, is_complete, completed_at)
                VALUES (:uid, 5, :steps, TRUE, :now)
            """), {"uid": user_id, "steps": "[1,2,3,4,5]", "now": now})

        db.commit()
        return {"status": "created", "email": demo_email, "org_id": org_id, "user_id": user_id}
    except Exception as e:
        db.rollback()
        return _JSONResponse(status_code=500, content={
            "status": "error",
            "error": str(e),
            "traceback": _tb.format_exc(),
        })


@router.post("/api/v1/seed-demo-data")
async def seed_demo_data(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db),
):
    """Seed full demo data (leads, loans, tasks, etc.) for the demo org.
    Requires ADMIN_API_KEY. Deletes existing demo data first, then recreates."""
    import os as _os
    import random as _random
    import traceback as _tb
    from datetime import date as _date, time as _time
    from fastapi.responses import JSONResponse as _JSONResponse

    _admin_api_key = _os.getenv("ADMIN_API_KEY")
    if not _admin_api_key or admin_key != _admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from sqlalchemy import text as _text
        now = datetime.now(timezone.utc)
        today = _date.today()
        org_slug = "summit-peak-demo-appstore"

        # Find org and demo user
        org_row = db.execute(_text("SELECT id FROM organizations WHERE slug = :s"), {"s": org_slug}).fetchone()
        if not org_row:
            return _JSONResponse(status_code=404, content={"error": "Demo org not found. Call create-demo-user first."})
        org_id = org_row[0]

        demo_row = db.execute(_text("SELECT id FROM users WHERE email = 'demo@perenniaai.com'"), {}).fetchone()
        if not demo_row:
            return _JSONResponse(status_code=404, content={"error": "Demo user not found."})
        demo_user_id = demo_row[0]

        # ── FIX ENUM COLUMNS (must run first, before any DML) ──
        # Some columns use PostgreSQL enum types that may be missing values.
        # Convert them to VARCHAR to avoid enum mismatch issues.
        enum_fixes = [
            ("activities", "type", "activitytype"),
            ("leads", "stage", "leadstage"),
            ("loans", "stage", "loanstage"),
            ("documents", "doc_type", "documenttype"),
            ("documents", "doc_category", "documentcategory"),
            ("documents", "match_status", "emailintakematchstatus"),
            ("documents", "classification_status", "attachmentclassificationstatus"),
            ("documents", "classified_doc_type", None),
            ("documents", "classified_doc_category", None),
            ("disclosure_events", "disclosure_type", "disclosuretype"),
            ("loan_fees", "tolerance_category", "tolerancecategory"),
            ("availability_slots", "day_of_week", "dayofweek"),
            ("availability_slots", "priority", "slotpriority"),
            ("scheduler_appointments", "meeting_mode", "meetingmode"),
            ("scheduler_appointments", "meeting_type", "meetingtype"),
            ("scheduler_appointments", "status", "appointmentstatus"),
            ("scheduler_configs", "default_meeting_mode", None),
            ("scheduler_configs", "routing_strategy", None),
            ("appointment_types", "meeting_type", None),
            ("appointment_types", "default_mode", None),
            ("appointment_types", "routing_strategy", None),
            ("tasks", "type", "tasktype"),
            ("compliance_alerts", "severity", None),
            ("compliance_alerts", "status", None),
            ("referral_partners", "category", None),
            ("referral_partners", "status", None),
            ("mum_clients", "status", None),
        ]
        # SAFETY: tbl, col, enum_name all come from the hardcoded enum_fixes list
        # above (never from user input). Each is additionally validated against
        # _ENUM_FIX_TABLES, _ENUM_FIX_COLUMNS, and _ENUM_FIX_TYPES frozensets.
        for tbl, col, enum_name in enum_fixes:
            if tbl not in _ENUM_FIX_TABLES:
                raise ValueError(f"Blocked SQL on non-whitelisted table: {tbl}")
            if col not in _ENUM_FIX_COLUMNS:
                raise ValueError(f"Blocked SQL on non-whitelisted column: {col}")
            try:
                nested = db.begin_nested()
                db.execute(_text(f"""
                    ALTER TABLE {tbl} ALTER COLUMN {col} TYPE VARCHAR(100) USING {col}::text
                """))
                nested.commit()
            except Exception:
                nested.rollback()
            if enum_name:
                if enum_name not in _ENUM_FIX_TYPES:
                    raise ValueError(f"Blocked SQL on non-whitelisted enum type: {enum_name}")
                try:
                    nested2 = db.begin_nested()
                    db.execute(_text(f"DROP TYPE IF EXISTS {enum_name}"))
                    nested2.commit()
                except Exception:
                    nested2.rollback()

        db.commit()

        # Clean existing demo data (order matters for FKs)
        # SAFETY: table names are hardcoded literals in the list below, validated
        # against _DEMO_CLEANUP_TABLES frozenset. org_id uses :oid bind parameter.
        for table in [
            "morning_briefings", "stage_history", "disclosure_events", "loan_fees",
            "compliance_alerts", "scheduler_appointments", "availability_slots",
            "appointment_types", "scheduler_configs",
            "loan_team_members", "mum_clients",
            "ai_tasks", "tasks", "activities", "documents",
            "email_intakes", "attachment_intakes",
            "loans", "leads", "referral_partners",
        ]:
            if table not in _DEMO_CLEANUP_TABLES:
                raise ValueError(f"Blocked SQL on non-whitelisted table: {table}")
            try:
                sp = db.begin_nested()
                db.execute(_text(f"DELETE FROM {table} WHERE organization_id = :oid"), {"oid": org_id})
                sp.commit()
            except Exception:
                sp.rollback()

        db.commit()

        # Get all user IDs in this org
        user_rows = db.execute(_text("SELECT id FROM users WHERE organization_id = :oid"), {"oid": org_id}).fetchall()
        lo_ids = [r[0] for r in user_rows[:3]] if len(user_rows) >= 3 else [demo_user_id]
        if demo_user_id not in lo_ids:
            lo_ids[0] = demo_user_id

        # ── LEADS ──
        leads_data = [
            ("Michael", "Thompson", "m.thompson@email.com", "512-555-1001", "New", "Website", 82, 740, 425000, "Purchase", "4521 Oak Valley Dr, Austin TX 78745", 0),
            ("Jennifer", "Davis", "j.davis@email.com", "512-555-1002", "New", "Zillow", 67, 695, 315000, "Purchase", "1823 Maple Creek Ln, Round Rock TX 78664", 0),
            ("Robert", "Wilson", "r.wilson@email.com", "512-555-1003", "Attempted Contact", "Referral", 75, 720, 550000, "Purchase", "9012 Cedar Ridge Ct, Lakeway TX 78734", 0),
            ("Emily", "Martinez", "e.martinez@email.com", "512-555-1004", "Prospect", "Realtor.com", 88, 780, 380000, "Purchase", "3456 Bluebonnet Blvd, Georgetown TX 78626", 0),
            ("David", "Anderson", "d.anderson@email.com", "512-555-1005", "Prospect", "Rate Quote", 91, 760, 475000, "Refinance", "7890 Barton Springs Rd, Austin TX 78704", 0),
            ("Lisa", "Taylor", "l.taylor@email.com", "512-555-1006", "Application", "Website", 85, 730, 290000, "Purchase", "2345 Pecan Park Way, Cedar Park TX 78613", 0),
            ("Christopher", "Brown", "c.brown@email.com", "512-555-1007", "Pre-Qualified", "Referral", 79, 710, 525000, "Purchase", "6789 Hill Country Dr, Dripping Springs TX 78620", 0),
            ("Amanda", "Jackson", "a.jackson@email.com", "512-555-1008", "Pre-Approved", "Zillow", 93, 790, 615000, "Purchase", "1234 Congress Ave, Austin TX 78701", 0),
            ("Daniel", "White", "d.white@email.com", "512-555-1009", "Under Contract", "LendingTree", 87, 755, 340000, "Purchase", "5678 Lamar Blvd, Austin TX 78751", 0),
            ("Jessica", "Harris", "j.harris@email.com", "512-555-1010", "Document Fulfillment", "Rate Quote", 90, 770, 460000, "Refinance", "3210 South 1st St, Austin TX 78704", 0),
            ("Matthew", "Lewis", "m.lewis@email.com", "512-555-1011", "Long-Term Nurture", "Website", 45, 640, 200000, "Purchase", None, 0),
            ("Ashley", "Clark", "a.clark@email.com", "512-555-1012", "Credit Repair", "Cold Call", 30, 580, 175000, "Purchase", None, 0),
            ("Ryan", "Walker", "r.walker@email.com", "512-555-1013", "Funded", "Referral", 95, 800, 520000, "Purchase", "8765 Bee Cave Rd, Austin TX 78746", 0),
            ("Nicole", "Robinson", "n.robinson@email.com", "512-555-1014", "Closed", "Website", 88, 745, 385000, "Purchase", "4321 Research Blvd, Austin TX 78759", 0),
            ("Brandon", "Young", "b.young@email.com", "512-555-1015", "Pre-Approved", "Realtor Referral", 86, 735, 295000, "Purchase", "9876 Parmer Ln, Austin TX 78727", 0),
            ("Stephanie", "King", "s.king@email.com", "512-555-1016", "Prospect", "Facebook Ad", 72, 700, 265000, "Purchase", "6543 Slaughter Ln, Austin TX 78748", 0),
            ("Tyler", "Scott", "t.scott@email.com", "512-555-1017", "New", "Instagram", 58, 680, 310000, "Purchase", None, 0),
            ("Megan", "Adams", "m.adams@email.com", "512-555-1018", "Attempted Contact", "Google Ads", 63, 690, 430000, "Refinance", "2109 East 7th St, Austin TX 78702", 0),
            ("Kevin", "Nelson", "k.nelson@email.com", "512-555-1019", "Application", "Rate Quote", 84, 725, 355000, "Purchase", "7654 Burnet Rd, Austin TX 78757", 0),
            ("Rachel", "Carter", "r.carter@email.com", "512-555-1020", "Pre-Qualified", "Referral", 77, 715, 490000, "Purchase", "3456 Westlake Dr, Austin TX 78746", 0),
        ]

        lead_ids = []
        for fn, ln, email, phone, stage, source, score, credit, amt, purpose, addr, _ in leads_data:
            created = now - timedelta(days=_random.randint(5, 90))
            last_contact = now - timedelta(days=_random.randint(0, 14)) if stage not in ("Long-Term Nurture", "Credit Repair") else now - timedelta(days=_random.randint(20, 45))
            db.execute(_text("""
                INSERT INTO leads (organization_id, first_name, last_name, name, email, phone, stage, source,
                    ai_score, credit_score, loan_amount, loan_purpose, property_address, property_type,
                    owner_id, created_at, updated_at, last_contact, annual_income, employment_status)
                VALUES (:oid, :fn, :ln, :name, :email, :phone, :stage, :source,
                    :score, :credit, :amt, :purpose, :addr, :ptype,
                    :owner, :created, :updated, :lc, :income, :emp)
            """), {"oid": org_id, "fn": fn, "ln": ln, "name": f"{fn} {ln}", "email": email, "phone": phone,
                   "stage": stage, "source": source, "score": score, "credit": credit, "amt": amt,
                   "purpose": purpose, "addr": addr, "ptype": "Single Family",
                   "owner": demo_user_id, "created": created, "updated": now, "lc": last_contact,
                   "income": _random.randint(75000, 200000), "emp": "Employed"})
            lid = db.execute(_text(
                "SELECT id FROM leads WHERE organization_id = :oid AND email = :e"
            ), {"oid": org_id, "e": email}).scalar()
            lead_ids.append(lid)

        # ── FORCE-CLEAN EXISTING LOANS by loan_number pattern ──
        # SAFETY: fk_table names are hardcoded literals in the list below, validated
        # against _DEMO_CLEANUP_TABLES frozenset for defense-in-depth. The subquery
        # uses :loan_pattern bind parameter to prevent SQL injection.
        _loan_subq = "SELECT id FROM loans WHERE loan_number LIKE :loan_pattern"
        _loan_pattern_param = {"loan_pattern": "SP-2026-%"}
        for fk_table in ["stage_history", "disclosure_events", "loan_fees", "compliance_alerts",
                         "documents", "activities", "loan_team_members", "scheduler_appointments"]:
            if fk_table not in _DEMO_CLEANUP_TABLES:
                raise ValueError(f"Blocked SQL on non-whitelisted table: {fk_table}")
            try:
                sp = db.begin_nested()
                db.execute(_text(f"DELETE FROM {fk_table} WHERE loan_id IN ({_loan_subq})"), _loan_pattern_param)
                sp.commit()
            except Exception:
                sp.rollback()
        try:
            sp = db.begin_nested()
            db.execute(_text("DELETE FROM loans WHERE loan_number LIKE :loan_pattern"), _loan_pattern_param)
            sp.commit()
        except Exception:
            sp.rollback()

        # ── LOANS ──
        loans_data = [
            ("SP-2026-001", "Amanda Jackson", "a.jackson@email.com", "PROCESSING", "conventional", 615000, 6.875, "1234 Congress Ave, Austin TX 78701", 35),
            ("SP-2026-002", "Daniel White", "d.white@email.com", "SUBMITTED", "fha", 340000, 6.625, "5678 Lamar Blvd, Austin TX 78751", 28),
            ("SP-2026-003", "Jessica Harris", "j.harris@email.com", "UNDERWRITING", "conventional", 460000, 6.750, "3210 South 1st St, Austin TX 78704", 25),
            ("SP-2026-004", "Lisa Taylor", "l.taylor@email.com", "APPLICATION", "conventional", 290000, 7.000, "2345 Pecan Park Way, Cedar Park TX 78613", 45),
            ("SP-2026-005", "Christopher Brown", "c.brown@email.com", "CONDITIONAL_APPROVAL", "jumbo", 525000, 7.125, "6789 Hill Country Dr, Dripping Springs TX 78620", 18),
            ("SP-2026-006", "Ryan Walker", "r.walker@email.com", "FUNDED", "conventional", 520000, 6.500, "8765 Bee Cave Rd, Austin TX 78746", -15),
            ("SP-2026-007", "Nicole Robinson", "n.robinson@email.com", "FUNDED", "fha", 385000, 6.375, "4321 Research Blvd, Austin TX 78759", -30),
            ("SP-2026-008", "Kevin Nelson", "k.nelson@email.com", "DISCLOSED", "conventional", 355000, 6.950, "7654 Burnet Rd, Austin TX 78757", 40),
            ("SP-2026-009", "David Anderson", "d.anderson@email.com", "CLEAR_TO_CLOSE", "conventional", 475000, 6.250, "7890 Barton Springs Rd, Austin TX 78704", 8),
            ("SP-2026-010", "Brandon Young", "b.young@email.com", "DOCS_OUT", "va", 295000, 6.125, "9876 Parmer Ln, Austin TX 78727", 5),
        ]

        loan_ids = []
        for ln_num, borrower, email, stage, ltype, amount, rate, prop, close_days in loans_data:
            closing = today + timedelta(days=close_days)
            app_date = closing - timedelta(days=_random.randint(30, 50))
            lock_date = app_date + timedelta(days=_random.randint(5, 15))
            lock_exp = lock_date + timedelta(days=45)
            funded_date = closing if close_days < 0 else None
            stage_changed = now - timedelta(days=_random.randint(1, 7))
            disc_sent = app_date + timedelta(days=2) if stage != "APPLICATION" else None
            uw_recv = app_date + timedelta(days=_random.randint(12, 18)) if stage in ("UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            approved = uw_recv + timedelta(days=_random.randint(3, 7)) if uw_recv and stage in ("CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            ctc_date = approved + timedelta(days=_random.randint(2, 5)) if approved and stage in ("CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            cd_sent = ctc_date - timedelta(days=4) if ctc_date else None

            db.execute(_text("""
                INSERT INTO loans (organization_id, loan_number, borrower_name, borrower_email,
                    stage, loan_type, amount, purchase_price, rate, term,
                    property_address, property_type, occupancy_type,
                    loan_officer_id, processor, closing_date, funded_date,
                    application_date, initial_disclosures_sent_date,
                    lock_date, lock_expiration_date,
                    uw_received_date, loan_approved_date, clear_to_close_date,
                    cd_sent_to_borrower_date,
                    stage_changed_at, created_at, updated_at,
                    loan_officer_name, program, lender)
                VALUES (:oid, :ln, :bn, :be, :stage, :lt, :amt, :pp, :rate, :term,
                    :addr, :pt, :ot, :lo, :proc, :close, :funded,
                    :app_date, :disc_sent, :lock, :lock_exp,
                    :uw_recv, :approved, :ctc, :cd_sent,
                    :sc, :created, :updated, :lo_name, :program, :lender)
                ON CONFLICT (loan_number) DO UPDATE SET
                    organization_id = EXCLUDED.organization_id,
                    borrower_name = EXCLUDED.borrower_name,
                    borrower_email = EXCLUDED.borrower_email,
                    stage = EXCLUDED.stage,
                    loan_type = EXCLUDED.loan_type,
                    amount = EXCLUDED.amount,
                    purchase_price = EXCLUDED.purchase_price,
                    rate = EXCLUDED.rate,
                    property_address = EXCLUDED.property_address,
                    loan_officer_id = EXCLUDED.loan_officer_id,
                    closing_date = EXCLUDED.closing_date,
                    funded_date = EXCLUDED.funded_date,
                    application_date = EXCLUDED.application_date,
                    stage_changed_at = EXCLUDED.stage_changed_at,
                    updated_at = EXCLUDED.updated_at
            """), {
                "oid": org_id, "ln": ln_num, "bn": borrower, "be": email,
                "stage": stage, "lt": ltype, "amt": amount, "pp": int(amount * 1.05),
                "rate": rate, "term": 360,
                "addr": prop, "pt": "single_family", "ot": "primary",
                "lo": demo_user_id, "proc": "Maria Gonzalez",
                "close": closing, "funded": funded_date,
                "app_date": app_date, "disc_sent": disc_sent,
                "lock": lock_date, "lock_exp": lock_exp,
                "uw_recv": uw_recv, "approved": approved, "ctc": ctc_date,
                "cd_sent": cd_sent,
                "sc": stage_changed, "created": now - timedelta(days=_random.randint(20, 60)),
                "updated": now, "lo_name": "Alex Morgan",
                "program": f"{ltype.upper()} 30yr Fixed", "lender": "Summit Peak Wholesale",
            })
            lid = db.execute(_text(
                "SELECT id FROM loans WHERE organization_id = :oid AND loan_number = :ln"
            ), {"oid": org_id, "ln": ln_num}).scalar()
            loan_ids.append(lid)

        # ── ACTIVITIES ──
        activity_templates = [
            ("Call", "Introductory call with borrower. Discussed loan options and timeline.", 12),
            ("Call", "Follow-up call to review documents needed for application.", 8),
            ("Email", "Sent pre-qualification letter and next steps checklist.", None),
            ("Email", "Rate lock confirmation sent to borrower.", None),
            ("Email", "Closing disclosure sent for e-signature.", None),
            ("Meeting", "In-person consultation to review loan scenarios and affordability.", 45),
            ("Meeting", "Video call to walk through application and collect initial docs.", 30),
            ("Note", "Borrower mentioned relocating from California. Tight timeline.", None),
            ("Note", "Appraisal came in above contract price. No issues.", None),
            ("SMS", "Sent reminder about upcoming document deadline.", None),
            ("Call", "Checked in on employment verification status.", 5),
            ("Email", "Sent monthly rate market update newsletter.", None),
            ("Note", "Processor flagged missing page 2 of bank statement.", None),
            ("Call", "Discussed rate lock options. Borrower wants to float.", 15),
            ("Meeting", "Pre-closing review with borrower and realtor.", 25),
        ]
        act_count = 0
        for lead_id in lead_ids[:10]:
            for _ in range(_random.randint(2, 5)):
                tpl = _random.choice(activity_templates)
                db.execute(_text("""
                    INSERT INTO activities (organization_id, type, content, lead_id, user_id, duration, created_at)
                    VALUES (:oid, :type, :content, :lid, :uid, :dur, :created)
                """), {"oid": org_id, "type": tpl[0], "content": tpl[1], "lid": lead_id,
                       "uid": demo_user_id, "dur": tpl[2],
                       "created": now - timedelta(days=_random.randint(0, 30), hours=_random.randint(0, 8))})
                act_count += 1
        for loan_id in loan_ids:
            for _ in range(_random.randint(3, 6)):
                tpl = _random.choice(activity_templates)
                db.execute(_text("""
                    INSERT INTO activities (organization_id, type, content, loan_id, user_id, duration, created_at)
                    VALUES (:oid, :type, :content, :lid, :uid, :dur, :created)
                """), {"oid": org_id, "type": tpl[0], "content": tpl[1], "lid": loan_id,
                       "uid": demo_user_id, "dur": tpl[2],
                       "created": now - timedelta(days=_random.randint(0, 25), hours=_random.randint(0, 8))})
                act_count += 1

        # ── TASKS ──
        tasks_data = [
            ("Follow up with Michael Thompson", "Call to discuss pre-approval options", "pending", "high", 1),
            ("Collect W-2s from Jennifer Davis", "Need 2024 and 2025 W-2 documents", "pending", "high", 2),
            ("Submit Amanda Jackson file to UW", "All docs collected, ready for submission", "in_progress", "high", 0),
            ("Order appraisal for Daniel White", "FHA appraisal — use approved appraiser list", "in_progress", "medium", 1),
            ("Rate lock decision for Jessica Harris", "Lock expires Friday — need borrower decision", "pending", "high", -1),
            ("Send closing disclosure to David Anderson", "CD ready, need 3-day waiting period", "completed", "high", -3),
            ("Schedule closing for Brandon Young", "VA loan — coordinate with title company", "in_progress", "medium", 3),
            ("Review conditions for Christopher Brown", "UW requested additional income verification", "pending", "high", 1),
            ("Send rate update to nurture leads", "Monthly rate market email to nurture list", "pending", "low", 5),
            ("Verify employment for Lisa Taylor", "VOE not received — follow up with employer", "in_progress", "medium", 0),
            ("Review appraisal for SP-2026-003", "Appraisal received — review before forwarding to UW", "pending", "medium", 2),
            ("Clear conditions on SP-2026-005", "2 remaining conditions: updated bank stmt + gift letter", "in_progress", "high", 0),
            ("Post-close follow-up call with Ryan Walker", "Funded last week — check in and ask for referral", "pending", "medium", 3),
            ("Update pipeline notes for Nicole Robinson", "Closed file — update pipeline and move to MUM", "completed", "low", -5),
            ("Prep weekly pipeline report", "Manager requested updated numbers by Friday", "pending", "medium", 4),
            ("Call Robert Wilson back", "Left voicemail 3 days ago — no response yet", "pending", "high", 0),
            ("Review title commitment for SP-2026-009", "Title came in — check for liens or exceptions", "in_progress", "high", 1),
            ("Schedule consultation with Emily Martinez", "Hot lead — score 88, referred by realtor", "pending", "high", 1),
            ("Send welcome packet to Kevin Nelson", "New application — send intro email and doc checklist", "completed", "medium", -2),
            ("Check credit supplement for SP-2026-002", "FHA requires credit supplement — order from bureau", "in_progress", "medium", 2),
        ]
        for title, desc, status, priority, due_offset in tasks_data:
            completed_at = now - timedelta(days=abs(due_offset)) if status == "completed" else None
            db.execute(_text("""
                INSERT INTO tasks (organization_id, title, description, status, priority, due_date,
                    owner_id, completed_at, created_at, updated_at)
                VALUES (:oid, :title, :desc, :status, :priority, :due,
                    :owner, :completed, :created, :updated)
            """), {"oid": org_id, "title": title, "desc": desc, "status": status, "priority": priority,
                   "due": today + timedelta(days=due_offset), "owner": demo_user_id,
                   "completed": completed_at, "created": now - timedelta(days=_random.randint(1, 10)), "updated": now})

        # ── DOCUMENTS ──
        doc_types_by_category = {
            "income": ["paystub", "w2", "tax_return"],
            "assets": ["bank_statement"],
            "credit": ["credit_report"],
            "property": ["appraisal", "purchase_contract", "title_commitment", "homeowners_insurance"],
            "identity": ["drivers_license"],
            "disclosures": ["loan_estimate", "closing_disclosure", "initial_disclosures"],
        }
        doc_count = 0
        for loan_id in loan_ids:
            for cat, dtypes in doc_types_by_category.items():
                for dt in dtypes:
                    if _random.random() < 0.75:
                        db.execute(_text("""
                            INSERT INTO documents (organization_id, loan_id, doc_type, doc_category, status,
                                filename, file_location, uploaded_at, source)
                            VALUES (:oid, :lid, :dt, :cat, :status, :fn, :floc, :uploaded, :src)
                        """), {"oid": org_id, "lid": loan_id, "dt": dt, "cat": cat,
                               "status": "active", "fn": f"{dt}_{loan_id}.pdf",
                               "floc": f"/docs/{org_id}/{loan_id}/{dt}.pdf",
                               "uploaded": now - timedelta(days=_random.randint(1, 20)),
                               "src": _random.choice(["borrower_upload", "email_intake", "los_sync"])})
                        doc_count += 1

        # ── COMPLIANCE ALERTS (table may not exist in production) ──
        alerts_count = 0
        try:
            _sp_ca = db.begin_nested()
            alerts_data = [
                ("LE_TIMING", "critical", "LE Deadline Approaching", "Loan Estimate must be sent within 3 business days of application", "open", loan_ids[3], 2),
                ("LOCK_EXPIRING", "high", "Rate Lock Expiring Soon", "Rate lock on SP-2026-005 expires in 3 days", "open", loan_ids[4], 3),
                ("MISSING_DOCUMENT", "medium", "Missing Bank Statement", "Page 2 of October bank statement not received", "open", loan_ids[0], 5),
                ("CD_TIMING", "high", "CD Delivery Deadline", "Closing Disclosure must be delivered 3 business days before closing", "open", loan_ids[8], 4),
                ("TRID_VIOLATION", "critical", "Potential TRID Timing Issue", "LE was sent 4 business days after application", "acknowledged", loan_ids[7], None),
                ("APPRAISAL_REVIEW", "medium", "Appraisal Below Contract Price", "Appraisal came in $15K below — may need renegotiation", "resolved", loan_ids[5], None),
                ("CONDITION_PAST_DUE", "high", "UW Condition Past Due", "Employment verification requested 10 days ago", "open", loan_ids[2], 1),
                ("RATE_CHANGE", "medium", "Rate Market Movement", "Rates moved +0.125% since lock", "resolved", loan_ids[6], None),
            ]
            for atype, severity, title, desc, status, lid, deadline_days in alerts_data:
                deadline = today + timedelta(days=deadline_days) if deadline_days else None
                resolved_at = now - timedelta(days=_random.randint(1, 5)) if status == "resolved" else None
                db.execute(_text("""
                    INSERT INTO compliance_alerts (organization_id, loan_id, alert_type, severity, title,
                        description, status, deadline_date, created_at, resolved_at)
                    VALUES (:oid, :lid, :atype, :sev, :title, :desc, :status, :deadline, :created, :resolved)
                """), {"oid": org_id, "lid": lid, "atype": atype, "sev": severity, "title": title,
                       "desc": desc, "status": status, "deadline": deadline,
                       "created": now - timedelta(days=_random.randint(1, 10)), "resolved": resolved_at})
                alerts_count += 1
            _sp_ca.commit()
        except Exception:
            _sp_ca.rollback()

        # ── REFERRAL PARTNERS (table may not exist) ──
        partners_count = 0
        try:
            _sp_rp = db.begin_nested()
            partners_data = [
                ("Laura Mitchell", "Mitchell Realty Group", "realtor", "laura@mitchellrealty.com", "512-555-2001", 12, 8, 6, 2850000, "gold"),
                ("Greg Hernandez", "Hernandez & Associates", "realtor", "greg@hernandezre.com", "512-555-2002", 8, 5, 3, 1650000, "silver"),
                ("Samantha Lee", "Capital Title Partners", "title_company", "sam@captitle.com", "512-555-2003", 6, 2, 4, 1900000, "silver"),
                ("Brian Cooper", "Cooper Insurance Agency", "insurance_agent", "brian@cooperins.com", "512-555-2004", 4, 3, 2, 890000, "bronze"),
                ("Angela Foster", "Austin Home Inspections", "home_inspector", "angela@austininspect.com", "512-555-2005", 3, 1, 1, 450000, "bronze"),
                ("Mark Sullivan", "Sullivan Financial Planning", "financial_advisor", "mark@sullivanfp.com", "512-555-2006", 5, 4, 3, 1400000, "silver"),
                ("Karen Phillips", "Lone Star Real Estate", "realtor", "karen@lonestarRE.com", "512-555-2007", 15, 10, 9, 4200000, "platinum"),
                ("Jason Rivera", "Rivera Homes", "builder", "jason@riverahomes.com", "512-555-2008", 7, 3, 4, 2100000, "silver"),
            ]
            for name, biz, cat, email, phone, ri, ro, cl, vol, tier in partners_data:
                db.execute(_text("""
                    INSERT INTO referral_partners (organization_id, name, business_name, category,
                        email, phone, referrals_in, referrals_out, closed_loans, volume,
                        status, loyalty_tier, owner_id, created_at)
                    VALUES (:oid, :name, :biz, :cat, :email, :phone, :ri, :ro, :cl, :vol,
                        :status, :tier, :owner, :created)
                """), {"oid": org_id, "name": name, "biz": biz, "cat": cat, "email": email,
                       "phone": phone, "ri": ri, "ro": ro, "cl": cl, "vol": vol,
                       "status": "active", "tier": tier, "owner": demo_user_id,
                       "created": now - timedelta(days=_random.randint(30, 365))})
                partners_count += 1
            _sp_rp.commit()
        except Exception:
            _sp_rp.rollback()

        # ── MUM CLIENTS (Portfolio — table may not exist) ──
        mum_count = 0
        try:
            _sp_mum = db.begin_nested()
            mum_data = [
                ("Ryan Walker", "r.walker@email.com", "512-555-1013", "SP-2026-006", 520000, 6.500, 15),
                ("Nicole Robinson", "n.robinson@email.com", "512-555-1014", "SP-2026-007", 385000, 6.375, 30),
                ("Patricia Nguyen", "p.nguyen@email.com", "512-555-3001", "SP-2025-048", 410000, 5.875, 180),
                ("Marcus Johnson", "m.johnson@email.com", "512-555-3002", "SP-2025-032", 550000, 6.125, 270),
                ("Catherine Park", "c.park@email.com", "512-555-3003", "SP-2025-015", 325000, 5.500, 365),
            ]
            for name, email, phone, ln, amt, rate, days_since in mum_data:
                close_date = today - timedelta(days=days_since)
                db.execute(_text("""
                    INSERT INTO mum_clients (organization_id, client_name, email, phone, loan_number,
                        original_close_date, closing_date, first_payment_date, days_since_funding,
                        original_rate, current_rate, original_loan_amount, current_loan_amount,
                        engagement_score, status, last_contact, user_id, created_at)
                    VALUES (:oid, :name, :email, :phone, :ln,
                        :close, :close, :fpp, :dsf,
                        :rate, :crate, :amt, :camt,
                        :escore, :status, :lc, :uid, :created)
                """), {"oid": org_id, "name": name, "email": email, "phone": phone, "ln": ln,
                       "close": close_date, "fpp": close_date + timedelta(days=30),
                       "dsf": days_since, "rate": rate, "crate": 6.750,
                       "amt": amt, "camt": int(amt * 0.98),
                       "escore": _random.randint(60, 95), "status": "active",
                       "lc": now - timedelta(days=_random.randint(5, 60)),
                       "uid": demo_user_id, "created": now - timedelta(days=days_since)})
                mum_count += 1
            _sp_mum.commit()
        except Exception:
            _sp_mum.rollback()

        # ── SCHEDULER CONFIG & APPOINTMENTS (tables may not exist) ──
        appts_count = 0
        try:
            _sp_sched = db.begin_nested()
            db.execute(_text("""
                INSERT INTO scheduler_configs (organization_id, user_id, config_name, timezone,
                    default_duration_minutes, min_notice_hours, max_advance_days,
                    max_meetings_per_day, is_active, created_at)
                VALUES (:oid, :uid, :name, :tz, :dur, :notice, :advance, :max, TRUE, :now)
            """), {"oid": org_id, "uid": demo_user_id, "name": "Default Schedule",
                   "tz": "America/Chicago", "dur": 30, "notice": 2, "advance": 30, "max": 8, "now": now})
            config_id = db.execute(_text(
                "SELECT id FROM scheduler_configs WHERE user_id = :uid ORDER BY id DESC LIMIT 1"
            ), {"uid": demo_user_id}).scalar()
            for dow in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
                db.execute(_text("""
                    INSERT INTO availability_slots (organization_id, config_id, user_id,
                        day_of_week, start_time, end_time, priority, is_active, created_at)
                    VALUES (:oid, :cid, :uid, :dow, :start, :end, :pri, TRUE, :now)
                """), {"oid": org_id, "cid": config_id, "uid": demo_user_id,
                       "dow": dow, "start": _time(9, 0), "end": _time(17, 0),
                       "pri": "standard", "now": now})
            appt_types = [
                ("discovery_call", "Discovery Call", 15),
                ("pre_approval_review", "Pre-Approval Review", 30),
                ("application_walkthrough", "Application Walkthrough", 45),
                ("rate_lock_consultation", "Rate Lock Consultation", 20),
                ("closing_prep", "Closing Preparation", 30),
                ("refinance_analysis", "Refinance Analysis", 30),
            ]
            appt_type_ids = {}
            for key, name, dur in appt_types:
                db.execute(_text("""
                    INSERT INTO appointment_types (organization_id, config_id, type_key, type_name,
                        default_duration_minutes, is_public, created_at)
                    VALUES (:oid, :cid, :key, :name, :dur, TRUE, :now)
                """), {"oid": org_id, "cid": config_id, "key": key, "name": name, "dur": dur, "now": now})
                atid = db.execute(_text(
                    "SELECT id FROM appointment_types WHERE config_id = :cid AND type_key = :key"
                ), {"cid": config_id, "key": key}).scalar()
                appt_type_ids[key] = atid
            appointments_data = [
                ("Discovery Call -- Michael Thompson", "m.thompson@email.com", "512-555-1001", "discovery_call", "booked", 2, 10, 15),
                ("Pre-Approval Review -- Emily Martinez", "e.martinez@email.com", "512-555-1004", "pre_approval_review", "confirmed", 3, 14, 30),
                ("Application Walkthrough -- Robert Wilson", "r.wilson@email.com", "512-555-1003", "application_walkthrough", "booked", 4, 9, 45),
                ("Closing Prep -- David Anderson", "d.anderson@email.com", "512-555-1005", "closing_prep", "confirmed", 1, 11, 30),
                ("Rate Lock -- Jessica Harris", "j.harris@email.com", "512-555-1010", "rate_lock_consultation", "booked", 5, 15, 20),
                ("Refinance Analysis -- Megan Adams", "m.adams@email.com", "512-555-1018", "refinance_analysis", "booked", 6, 10, 30),
                ("Discovery Call -- Tyler Scott", "t.scott@email.com", "512-555-1017", "discovery_call", "booked", 7, 13, 15),
                ("Pre-Approval -- Stephanie King", "s.king@email.com", "512-555-1016", "pre_approval_review", "confirmed", 2, 16, 30),
                ("Discovery Call -- Ryan Walker", "r.walker@email.com", "512-555-1013", "discovery_call", "completed", -20, 10, 15),
                ("Application -- Nicole Robinson", "n.robinson@email.com", "512-555-1014", "application_walkthrough", "completed", -30, 14, 45),
                ("Pre-Approval -- Amanda Jackson", "a.jackson@email.com", "512-555-1008", "pre_approval_review", "completed", -15, 11, 30),
                ("Closing Prep -- Brandon Young", "b.young@email.com", "512-555-1015", "closing_prep", "completed", -5, 9, 30),
                ("Discovery Call -- Jennifer Davis", "j.davis@email.com", "512-555-1002", "discovery_call", "no_show", -7, 10, 15),
            ]
            for title, email, phone, tkey, status, day_offset, hour, dur in appointments_data:
                sched_start = datetime.combine(today + timedelta(days=day_offset), _time(hour, 0), tzinfo=timezone.utc)
                sched_end = sched_start + timedelta(minutes=dur)
                completed_at = sched_end if status == "completed" else None
                db.execute(_text("""
                    INSERT INTO scheduler_appointments (organization_id, appointment_type_id, assigned_user_id,
                        title, scheduled_start, scheduled_end, duration_minutes, timezone,
                        meeting_mode, attendee_name, attendee_email, attendee_phone,
                        status, completed_at, created_at, updated_at)
                    VALUES (:oid, :atid, :uid, :title, :start, :end, :dur, :tz,
                        :mode, :aname, :aemail, :aphone, :status, :completed, :created, :updated)
                """), {"oid": org_id, "atid": appt_type_ids[tkey], "uid": demo_user_id,
                       "title": title, "start": sched_start, "end": sched_end, "dur": dur,
                       "tz": "America/Chicago", "mode": _random.choice(["video", "phone"]),
                       "aname": title.split(" -- ")[1] if " -- " in title else "Client",
                       "aemail": email, "aphone": phone, "status": status,
                       "completed": completed_at,
                       "created": sched_start - timedelta(days=_random.randint(1, 5)), "updated": now})
                appts_count += 1
            _sp_sched.commit()
        except Exception:
            _sp_sched.rollback()

        # ── STAGE HISTORY (table may not exist) ──
        sh_count = 0
        try:
            _sp_sh = db.begin_nested()
            stage_sequences = {
                "PROCESSING": ["APPLICATION", "DISCLOSED", "PROCESSING"],
                "SUBMITTED": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED"],
                "UNDERWRITING": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING"],
                "CONDITIONAL_APPROVAL": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL"],
                "CLEAR_TO_CLOSE": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE"],
                "DOCS_OUT": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT"],
                "FUNDED": ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED"],
                "DISCLOSED": ["APPLICATION", "DISCLOSED"],
                "APPLICATION": ["APPLICATION"],
            }
            for i, loan_id in enumerate(loan_ids):
                stage = loans_data[i][3]
                seq = stage_sequences.get(stage, [stage])
                base_date = now - timedelta(days=len(seq) * 4)
                for j in range(len(seq) - 1):
                    changed = base_date + timedelta(days=(j + 1) * _random.randint(2, 5))
                    db.execute(_text("""
                        INSERT INTO stage_history (organization_id, entity_type, entity_id,
                            from_stage, to_stage, changed_at, changed_by_id, created_at)
                        VALUES (:oid, :etype, :eid, :from_s, :to_s, :changed, :by, :changed)
                    """), {"oid": org_id, "etype": "loan", "eid": loan_id,
                           "from_s": seq[j], "to_s": seq[j + 1], "changed": changed,
                           "by": demo_user_id})
                    sh_count += 1
            _sp_sh.commit()
        except Exception:
            _sp_sh.rollback()

        # ── DISCLOSURE EVENTS (table may not exist) ──
        disc_count = 0
        try:
            _sp_de = db.begin_nested()
            for i, loan_id in enumerate(loan_ids):
                stage = loans_data[i][3]
                if stage == "APPLICATION":
                    continue
                db.execute(_text("""
                    INSERT INTO disclosure_events (organization_id, loan_id, disclosure_type,
                        sent_at, delivery_method, is_on_time, created_at)
                    VALUES (:oid, :lid, :dt, :sent, :dm, :ot, :created)
                """), {"oid": org_id, "lid": loan_id, "dt": "loan_estimate",
                       "sent": now - timedelta(days=_random.randint(15, 40)),
                       "dm": "email", "ot": True, "created": now - timedelta(days=_random.randint(15, 40))})
                disc_count += 1
                if stage in ("CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED"):
                    db.execute(_text("""
                        INSERT INTO disclosure_events (organization_id, loan_id, disclosure_type,
                            sent_at, delivery_method, is_on_time, created_at)
                        VALUES (:oid, :lid, :dt, :sent, :dm, :ot, :created)
                    """), {"oid": org_id, "lid": loan_id, "dt": "closing_disclosure",
                           "sent": now - timedelta(days=_random.randint(3, 10)),
                           "dm": "esign", "ot": True, "created": now - timedelta(days=_random.randint(3, 10))})
                    disc_count += 1
            _sp_de.commit()
        except Exception:
            _sp_de.rollback()

        # ── LOAN FEES (table may not exist) ──
        fee_count = 0
        try:
            _sp_lf = db.begin_nested()
            for loan_id in loan_ids[:7]:
                for fn, fc, tc, le, cd in [
                    ("Origination Fee", "origination", "zero", 2500, 2500),
                    ("Appraisal Fee", "appraisal", "zero", 550, 550),
                    ("Credit Report Fee", "credit", "zero", 75, 75),
                    ("Title Insurance", "title", "ten_percent", 1800, 1850),
                    ("Title Search", "title", "ten_percent", 350, 375),
                    ("Recording Fees", "government", "ten_percent", 125, 130),
                    ("Flood Certification", "other", "unlimited", 15, 20),
                    ("Homeowners Insurance", "insurance", "unlimited", 1400, 1450),
                ]:
                    db.execute(_text("""
                        INSERT INTO loan_fees (organization_id, loan_id, fee_name, fee_category,
                            tolerance_category, le_amount, cd_amount, created_at)
                        VALUES (:oid, :lid, :fn, :fc, :tc, :le, :cd, :now)
                    """), {"oid": org_id, "lid": loan_id, "fn": fn, "fc": fc, "tc": tc,
                           "le": le, "cd": cd, "now": now})
                    fee_count += 1
            _sp_lf.commit()
        except Exception:
            _sp_lf.rollback()

        db.commit()
        return {
            "status": "success",
            "data_seeded": {
                "leads": len(leads_data),
                "loans": len(loans_data),
                "activities": act_count,
                "tasks": len(tasks_data),
                "documents": doc_count,
                "compliance_alerts": alerts_count,
                "referral_partners": partners_count,
                "mum_clients": mum_count,
                "appointments": appts_count,
                "stage_history": sh_count,
                "disclosure_events": disc_count,
                "loan_fees": fee_count,
            }
        }
    except Exception as e:
        db.rollback()
        import traceback as _tb2
        return _JSONResponse(status_code=500, content={
            "status": "error", "error": str(e), "traceback": _tb2.format_exc()
        })


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    plan: str = "professional"  # starter, professional, enterprise


class EmailVerification(BaseModel):
    token: str


class OnboardingStepUpdate(BaseModel):
    step: int
    data: Dict


class TeamMemberCreate(BaseModel):
    name: str
    role: str
    responsibilities: str
    email: Optional[str] = None


class WorkflowCreate(BaseModel):
    name: str
    description: str
    steps: List[Dict]
    assigned_roles: List[str]


# ============================================================================
# REGISTRATION & EMAIL VERIFICATION
# ============================================================================

@router.get("/api/v1/migrate-database")
async def migrate_database(db: Session = Depends(get_db)):
    """Add missing onboarding_completed column to users table"""
    try:
        from sqlalchemy import text

        # Check if column exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users'
            AND column_name='onboarding_completed'
        """))

        if result.fetchone() is None:
            # Add the column
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE
            """))
            db.commit()
            return {
                "status": "success",
                "message": "Added onboarding_completed column to users table"
            }
        else:
            return {
                "status": "already_exists",
                "message": "Column already exists, no migration needed"
            }

    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "error": "Internal server error"
        }

@router.get("/api/v1/register-test")
async def register_test():
    """Test endpoint - DISABLED"""
    raise HTTPException(
        status_code=403,
        detail="Registration testing is disabled."
    )

@router.post("/api/v1/register")
async def register_user(registration: UserRegistration, db: Session = Depends(get_db)):
    """
    Register a new user - DISABLED

    Registration is disabled. Only @cmgfi.com users can access this system.
    Contact your system administrator for account access.
    """

    raise HTTPException(
        status_code=403,
        detail="Registration is disabled. This system is restricted to authorized @cmgfi.com users only. Please contact your administrator for access."
    )

    # Original registration code disabled below:
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == registration.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Validate plan (just to ensure valid plan key)
        plan_info = stripe_service.get_plan_info(registration.plan)
        if not plan_info:
            # Default to professional if invalid plan
            registration.plan = "professional"
            plan_info = stripe_service.get_plan_info("professional")

        logger.info("Starting registration for new user")

        # Create user in database (auto-verified and activated)
        _name_parts = (registration.full_name or '').strip().split(' ', 1)
        db_user = User(
            email=registration.email,
            hashed_password=get_password_hash(registration.password),
            first_name=_name_parts[0] if _name_parts else '',
            last_name=_name_parts[1] if len(_name_parts) > 1 else '',
            email_verified=True,  # Auto-verify all accounts
            is_active=True,  # Auto-activate all accounts
            user_metadata={
                "company_name": registration.company_name or "",
                "phone": registration.phone or "",
                "plan": registration.plan,
                "dev_mode": True
            }
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(f"User created with ID: {db_user.id}")

        # Create mock subscription record
        try:
            db_subscription = Subscription(
                user_id=db_user.id,
                stripe_customer_id=f"dev_customer_{db_user.id}",
                stripe_subscription_id=f"dev_sub_{db_user.id}",
                status="active",
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=365),
                trial_end=None
            )
            db.add(db_subscription)
            db.commit()
            logger.info(f"Subscription created for user {db_user.id}")
        except Exception as sub_error:
            logger.warning(f"Subscription creation failed (non-critical): {str(sub_error)}")
            # Continue even if subscription fails

        # Create onboarding progress
        try:
            onboarding = OnboardingProgress(
                user_id=db_user.id,
                current_step=1,
                steps_completed=[]
            )
            db.add(onboarding)
            db.commit()
            logger.info(f"Onboarding progress created for user {db_user.id}")
        except Exception as onboard_error:
            logger.warning(f"Onboarding creation failed (non-critical): {str(onboard_error)}")
            # Continue even if onboarding progress creation fails

        # Generate access token for immediate login
        try:
            access_token = create_access_token(data={"sub": db_user.email})
        except Exception as token_error:
            logger.error(f"Token generation failed: {str(token_error)}")
            raise HTTPException(status_code=500, detail="Failed to generate authentication token")

        logger.info("Registration successful for new user")

        return {
            "message": "Registration successful! Redirecting to dashboard...",
            "user_id": db_user.id,
            "email": db_user.email,
            "full_name": db_user.full_name,
            "access_token": access_token,
            "token_type": "bearer",
            "dev_mode": True,
            "redirect_to": "/dashboard"
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Registration failed with error: {str(e)}")
        logger.error(f"Full traceback: {error_details}")

        # Try to cleanup user if created
        try:
            if 'db_user' in locals() and db_user and hasattr(db_user, 'id'):
                db.query(User).filter(User.id == db_user.id).delete()
                db.commit()
                logger.info(f"Cleaned up user after failed registration")
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed: {str(cleanup_error)}")

        # Return user-friendly error message
        raise HTTPException(
            status_code=500,
            detail="We encountered an error creating your account. Please try again or contact support if the issue persists."
        )
    """


@router.post("/api/v1/verify-email")
async def verify_email(verification: EmailVerification, db: Session = Depends(get_db)):
    """
    Verify user's email address with token
    """
    # Lazy import to avoid circular dependency
    from database.models import User

    user_id = VerificationTokenService.verify_token(db, verification.token)

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    # Update user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified = True
    user.is_active = True
    db.commit()

    # Send welcome email
    email_service.send_welcome_email(user.email, user.full_name)

    logger.info(f"Email verified for user ID: {user.id}")

    return {
        "message": "Email verified successfully!",
        "email": user.email,
        "redirect_to": "/onboarding"
    }


@router.post("/api/v1/resend-verification")
async def resend_verification(email: EmailStr, db: Session = Depends(get_db)):
    """
    Resend verification email
    """
    # Lazy import to avoid circular dependency
    from database.models import User

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    # Generate new token
    verification_token = VerificationTokenService.create_verification_token(
        db, user.id, user.email
    )

    # Send email
    email_service.send_verification_email(
        user.email,
        verification_token,
        user.full_name
    )

    return {"message": "Verification email sent"}


# ============================================================================
# SUBSCRIPTION PLANS
# ============================================================================

@router.get("/api/v1/plans")
async def get_subscription_plans():
    """
    Get all available subscription plans
    """
    return {
        "plans": stripe_service.get_all_plans()
    }


# ============================================================================
# STRIPE WEBHOOKS
# ============================================================================

@router.post("/api/v1/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhook events
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe_service.verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Bad request")

    # Handle different event types
    event_type = event['type']

    if event_type == 'checkout.session.completed':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_checkout_completed(event['data']['object'], db)

    elif event_type == 'customer.subscription.created':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_created(event['data']['object'], db)

    elif event_type == 'customer.subscription.updated':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_updated(event['data']['object'], db)

    elif event_type == 'customer.subscription.deleted':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_deleted(event['data']['object'], db)

    elif event_type == 'invoice.payment_succeeded':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_payment_succeeded(event['data']['object'], db)

    elif event_type == 'invoice.payment_failed':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_payment_failed(event['data']['object'], db)

    return {"status": "success"}


# ============================================================================
# ONBOARDING
# ============================================================================

@router.get("/api/v1/onboarding/progress")
async def get_onboarding_progress(user_id: int, db: Session = Depends(get_db)):
    """
    Get onboarding progress for a user
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    return {
        "current_step": progress.current_step,
        "steps_completed": progress.steps_completed,
        "is_complete": progress.is_complete,
        "team_members_added": progress.team_members_added,
        "workflows_generated": progress.workflows_generated
    }


@router.post("/api/v1/onboarding/step")
async def update_onboarding_step(
    user_id: int,
    step_update: OnboardingStepUpdate,
    db: Session = Depends(get_db)
):
    """
    Update onboarding step progress
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    # Update step
    if step_update.step not in progress.steps_completed:
        progress.steps_completed.append(step_update.step)

    # Move to next step
    if step_update.step >= progress.current_step:
        progress.current_step = min(step_update.step + 1, 5)

    # Check if all steps completed
    if len(progress.steps_completed) >= 5:
        progress.is_complete = True
        progress.completed_at = datetime.now(timezone.utc)

    progress.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Onboarding step updated",
        "current_step": progress.current_step,
        "is_complete": progress.is_complete
    }


@router.post("/api/v1/onboarding/upload-documents")
async def upload_onboarding_documents(
    user_id: int,
    files: List[str],  # File paths or base64 encoded content
    db: Session = Depends(get_db)
):
    """
    Handle document uploads during onboarding

    In production, this would use file upload and storage (S3, etc.)
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    # Store document references
    if not progress.uploaded_documents:
        progress.uploaded_documents = []

    progress.uploaded_documents.extend(files)
    progress.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": f"{len(files)} documents uploaded successfully",
        "total_documents": len(progress.uploaded_documents)
    }


@router.post("/api/v1/onboarding/team-member")
async def add_team_member(
    user_id: int,
    team_member: TeamMemberCreate,
    db: Session = Depends(get_db)
):
    """
    Add a team member during onboarding
    """
    # Lazy import to avoid circular dependency
    from database.models import TeamMember, OnboardingProgress

    db_member = TeamMember(
        user_id=user_id,
        name=team_member.name,
        role=team_member.role,
        responsibilities=team_member.responsibilities,
        email=team_member.email,
        status="pending"
    )
    db.add(db_member)

    # Update onboarding progress
    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()
    if progress:
        progress.team_members_added += 1

    db.commit()

    return {
        "message": "Team member added",
        "member_id": db_member.id
    }


def _get_default_workflows():
    """Return default workflows when AI generation fails"""
    return [
        {
            "name": "Lead to Application Workflow",
            "description": "Automated workflow for moving leads through the application process",
            "steps": [
                {"order": 1, "name": "Initial Contact", "assigned_role": "Loan Officer"},
                {"order": 2, "name": "Pre-qualification", "assigned_role": "Loan Officer"},
                {"order": 3, "name": "Application Submission", "assigned_role": "Processor"},
                {"order": 4, "name": "Document Collection", "assigned_role": "Processor"},
                {"order": 5, "name": "Underwriting", "assigned_role": "Underwriter"}
            ]
        },
        {
            "name": "Client Onboarding Workflow",
            "description": "Workflow for onboarding new clients",
            "steps": [
                {"order": 1, "name": "Welcome Email", "assigned_role": "System"},
                {"order": 2, "name": "Initial Consultation", "assigned_role": "Loan Officer"},
                {"order": 3, "name": "Document Request", "assigned_role": "Processor"},
                {"order": 4, "name": "Credit Pull", "assigned_role": "Loan Officer"}
            ]
        }
    ]


@router.post("/api/v1/onboarding/generate-workflows")
async def generate_workflows(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Use AI to generate workflows from uploaded documents and team structure

    This is a placeholder - actual implementation would use OpenAI to parse
    documents and generate custom workflows
    """
    # Lazy import to avoid circular dependency
    from database.models import TeamMember, OnboardingProgress, Workflow

    # Get team members
    team_members = db.query(TeamMember).filter(TeamMember.user_id == user_id).all()

    # Get uploaded documents from onboarding progress
    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress or not progress.uploaded_documents:
        raise HTTPException(status_code=400, detail="No documents uploaded for workflow generation")

    # Generate workflows using Claude AI
    import httpx
    import json

    team_roles = list(set([m.role for m in team_members])) if team_members else ["Loan Officer", "Processor"]
    documents_info = json.dumps(progress.uploaded_documents) if isinstance(progress.uploaded_documents, list) else str(progress.uploaded_documents)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": f"""Based on the following mortgage company information, generate 2-3 custom workflows.

Team Roles Available: {', '.join(team_roles)}
Uploaded Documents: {documents_info[:2000]}

Generate workflows as a JSON array. Each workflow should have:
- name: descriptive workflow name
- description: brief description
- steps: array of {{ "order": number, "name": step name, "assigned_role": role from team }}

Focus on mortgage industry workflows like:
- Lead qualification and conversion
- Loan processing pipeline
- Document collection
- Closing coordination

Return ONLY valid JSON, no markdown or explanation."""
                    }],
                },
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result["content"][0]["text"]

                # Try to parse AI-generated workflows
                try:
                    # Clean up response if needed
                    ai_response = ai_response.strip()
                    if ai_response.startswith("```"):
                        ai_response = ai_response.split("```")[1]
                        if ai_response.startswith("json"):
                            ai_response = ai_response[4:]
                    sample_workflows = json.loads(ai_response)
                except json.JSONDecodeError:
                    logger.warning("AI returned invalid JSON, using default workflows")
                    sample_workflows = _get_default_workflows()
            else:
                logger.warning(f"AI API returned {response.status_code}, using default workflows")
                sample_workflows = _get_default_workflows()

    except Exception as e:
        logger.error(f"AI workflow generation failed: {e}, using defaults")
        sample_workflows = _get_default_workflows()

    created_workflows = []
    for workflow_data in sample_workflows:
        db_workflow = Workflow(
            user_id=user_id,
            name=workflow_data["name"],
            description=workflow_data["description"],
            steps=workflow_data["steps"],
            assigned_roles=[step["assigned_role"] for step in workflow_data["steps"]],
            automation_rules={},
            created_by_ai=True
        )
        db.add(db_workflow)
        created_workflows.append(db_workflow)

    # Update progress
    if progress:
        progress.workflows_generated = len(created_workflows)
        progress.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": f"{len(created_workflows)} workflows generated",
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "steps_count": len(w.steps)
            }
            for w in created_workflows
        ]
    }


# ============================================================================
# PUBLIC QUESTIONNAIRES (Landing Pages)
# ============================================================================

class MortgagePlannerSubmission(BaseModel):
    """Schema for Mortgage Planner Questionnaire submission"""
    name: str
    email: EmailStr
    phone: str
    isVeteran: str
    hasOwnedHomeBefore: str
    currentHousingStatus: str
    previousMortgageType: Optional[str] = None
    currentMonthlyPayment: Optional[str] = None
    mortgageImportance: List[str]
    personalGoals: List[str]
    financialPhilosophy: str
    hasTaxDeferredRetirement: str
    hasFinancialPlanner: str
    financialPlannerRating: Optional[str] = None
    hasAccountant: str
    accountantRating: Optional[str] = None
    hasLifeInsuranceAgent: str
    lifeInsuranceAgentRating: Optional[str] = None
    hasEstatePlanner: str
    estatePlannerRating: Optional[str] = None
    loan_officer_id: Optional[str] = None
    source: Optional[str] = None
    submitted_at: Optional[str] = None


@router.post("/api/v1/questionnaire/mortgage-planner")
async def submit_mortgage_planner_questionnaire(
    submission: MortgagePlannerSubmission,
    db: Session = Depends(get_db)
):
    """
    Handle Mortgage Planning Questionnaire submissions.

    This endpoint:
    1. Creates or updates a lead with the questionnaire data
    2. Creates circle_contacts for trusted professionals the borrower has
    3. Creates tasks to get introductions to excellent-rated professionals
    4. Creates tasks to make referrals when borrower needs professionals
    """
    from database.models import Lead, Task
    from sqlalchemy import text

    try:
        # Determine the loan officer ID (default to demo user ID 1 if not specified)
        loan_officer_id = int(submission.loan_officer_id) if submission.loan_officer_id else 1

        # Check if lead already exists by email
        existing_lead = db.query(Lead).filter(Lead.email == submission.email).first()

        if existing_lead:
            # Update existing lead
            lead = existing_lead
            lead.name = submission.name
            lead.phone = submission.phone
        else:
            # Create new lead
            from database.enums import LeadStage
            lead = Lead(
                name=submission.name,
                email=submission.email,
                phone=submission.phone,
                owner_id=loan_officer_id,
                source="Mortgage Planner Questionnaire",
                stage=LeadStage.NEW
            )
            db.add(lead)
            db.flush()  # Get the lead ID

            from services.client_file_service import ensure_client_file
            ensure_client_file(db, lead)

        # Store questionnaire responses in lead metadata
        lead.notes = f"""
MORTGAGE PLANNER QUESTIONNAIRE RESPONSES
========================================
Submitted: {submission.submitted_at or datetime.now(timezone.utc).isoformat()}

PERSONAL INFORMATION
- Name: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}
- Veteran: {submission.isVeteran}

HOME OWNERSHIP HISTORY
- Previously owned home: {submission.hasOwnedHomeBefore}
- Current status: {submission.currentHousingStatus}
- Previous mortgage type: {submission.previousMortgageType or 'N/A'}
- Current monthly payment: ${submission.currentMonthlyPayment or 'N/A'}

MORTGAGE PRIORITIES
{chr(10).join(['- ' + p for p in submission.mortgageImportance])}

PERSONAL GOALS
{chr(10).join(['- ' + g for g in submission.personalGoals])}

FINANCIAL PHILOSOPHY
- {submission.financialPhilosophy}

PROFESSIONAL NETWORK (Circle of Cashflow)
- Tax-deferred retirement plan: {submission.hasTaxDeferredRetirement}
- Financial Planner: {submission.hasFinancialPlanner} (Rating: {submission.financialPlannerRating or 'N/A'})
- Accountant: {submission.hasAccountant} (Rating: {submission.accountantRating or 'N/A'})
- Life Insurance Agent: {submission.hasLifeInsuranceAgent} (Rating: {submission.lifeInsuranceAgentRating or 'N/A'})
- Estate Planner: {submission.hasEstatePlanner} (Rating: {submission.estatePlannerRating or 'N/A'})
"""

        # Track professionals for circle contacts and tasks
        missing_professionals = []
        excellent_professionals = []
        circle_contacts_created = []

        # Professional mapping: (has_field, rating_field, type_name, icon)
        professionals = [
            ('hasFinancialPlanner', 'financialPlannerRating', 'Financial Advisor', '💼'),
            ('hasAccountant', 'accountantRating', 'Accountant', '📊'),
            ('hasLifeInsuranceAgent', 'lifeInsuranceAgentRating', 'Life Insurance Agent', '🛡️'),
            ('hasEstatePlanner', 'estatePlannerRating', 'Estate Planner', '📜'),
        ]

        for has_field, rating_field, type_name, icon in professionals:
            has_professional = getattr(submission, has_field)
            rating = getattr(submission, rating_field)

            if has_professional == 'No':
                # Borrower needs this professional - create referral task
                missing_professionals.append(type_name)
            elif has_professional == 'Yes':
                # Skip circle_contacts creation for now - table may not exist
                # If rated Excellent, create task to get introduction
                if rating == 'Excellent':
                    excellent_professionals.append(type_name)

        # Create tasks using raw SQL to avoid column mismatch issues
        # (The ORM model may have columns that don't exist in production DB)

        # Create tasks for excellent-rated professionals (get introductions)
        for prof_type in excellent_professionals:
            intro_description = f"""{submission.name} has rated their {prof_type} as "Excellent" in their Mortgage Planner Questionnaire.

ACTION REQUIRED:
Ask {submission.name} for an introduction to their {prof_type}. This is a great opportunity to:
- Build your professional network
- Potentially receive referrals
- Create reciprocal referral relationships

CONTACT INFO:
- Client: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}

Suggested approach: Mention that you work with many clients who need a {prof_type}, and you'd love to connect with professionals your clients trust.
"""
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
                VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
            """), {
                "title": f"Get Introduction to {submission.name}'s {prof_type}",
                "description": intro_description,
                "priority": "high",
                "status": "pending",
                "owner_id": loan_officer_id,
                "lead_id": lead.id,
                "due_date": datetime.now(timezone.utc) + timedelta(days=7),
                "related_type": "introduction_request",
                "related_contact_name": submission.name
            })

        # Create tasks for missing professionals (make referrals)
        if missing_professionals:
            referral_description = f"""{submission.name} needs the following professionals based on their Mortgage Planner Questionnaire:

PROFESSIONALS NEEDED:
{chr(10).join(['- ' + p for p in missing_professionals])}

ACTION REQUIRED:
Connect {submission.name} with trusted partners from your network. This builds:
- Client loyalty and trust
- Reciprocal referral relationships with partners
- Complete client service experience

CONTACT INFO:
- Client: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}

Track which partners you introduce and follow up on the outcomes for your Circle of Cashflow records.
"""
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
                VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
            """), {
                "title": f"Make Referrals for {submission.name}",
                "description": referral_description,
                "priority": "medium",
                "status": "pending",
                "owner_id": loan_officer_id,
                "lead_id": lead.id,
                "due_date": datetime.now(timezone.utc) + timedelta(days=3),
                "related_type": "referral_opportunity",
                "related_contact_name": submission.name
            })

        # Create review task for questionnaire
        review_description = f"""Review {submission.name}'s Mortgage Planner Questionnaire responses.

CONTACT INFO:
- Email: {submission.email}
- Phone: {submission.phone}

KEY PRIORITIES:
{chr(10).join(['- ' + p for p in submission.mortgageImportance[:3]])}

FINANCIAL PHILOSOPHY: {submission.financialPhilosophy}

CIRCLE OF CASHFLOW STATUS:
- Excellent-rated professionals to get introductions: {len(excellent_professionals)}
- Missing professionals to refer: {len(missing_professionals)}
- Circle contacts created: {len(circle_contacts_created)}
"""
        db.execute(text("""
            INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
            VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
        """), {
            "title": f"Review Questionnaire - {submission.name}",
            "description": review_description,
            "priority": "high",
            "status": "pending",
            "owner_id": loan_officer_id,
            "lead_id": lead.id,
            "due_date": datetime.now(timezone.utc) + timedelta(days=1),
            "related_type": "questionnaire",
            "related_contact_name": submission.name
        })

        db.commit()

        logger.info(f"Mortgage Planner Questionnaire submitted for {submission.name} (Lead ID: {lead.id})")
        logger.info(f"  - Circle contacts created: {circle_contacts_created}")
        logger.info(f"  - Introduction tasks for: {excellent_professionals}")
        logger.info(f"  - Referral opportunities: {missing_professionals}")

        return {
            "success": True,
            "message": "Questionnaire submitted successfully",
            "lead_id": lead.id,
            "circle_contacts_created": circle_contacts_created,
            "introduction_opportunities": excellent_professionals,
            "referral_opportunities": missing_professionals
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing Mortgage Planner Questionnaire: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process questionnaire. Please try again."
        )


# ============================================================================
# PUBLIC PARTNER SEARCH (for borrower intake forms)
# ============================================================================

class PartnerSearchResult(BaseModel):
    """Public partner info for autocomplete"""
    id: int
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    partner_type: Optional[str] = None


@router.get("/api/v1/public/partners/search", response_model=List[PartnerSearchResult])
async def search_partners_public(
    q: str = "",
    partner_type: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Public endpoint to search referral partners by name/company for borrower intake forms.
    This allows applicants to find and select their real estate agent from the CRM database.

    Parameters:
    - q: Search query (matches name, company, or email)
    - partner_type: Optional filter by type (e.g., "Realtor", "Builder", "Insurance Agent")
    - limit: Maximum results to return (default 10)
    """
    try:
        from database.models import ReferralPartner
        from sqlalchemy import or_, func

        # Include active partners and those with null/unknown status
        query = db.query(ReferralPartner).filter(
            or_(
                ReferralPartner.status == "active",
                ReferralPartner.status.is_(None),
                ReferralPartner.status == ""
            )
        )

        # Filter by partner type if specified
        if partner_type:
            query = query.filter(
                func.lower(ReferralPartner.type).contains(partner_type.lower())
            )

        # Search by name, company, or email if query provided
        if q and len(q) >= 2:
            search_term = q.lower()
            query = query.filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.email).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            )

        # Order by name and limit results
        partners = query.order_by(ReferralPartner.name).limit(limit).all()

        # Return sanitized results (only public info)
        return [
            PartnerSearchResult(
                id=p.id,
                name=p.name or p.contact_name or "Unknown",
                company=p.company,
                email=p.email,
                phone=p.phone,
                partner_type=p.type
            )
            for p in partners
        ]

    except Exception as e:
        logger.error(f"Error searching partners: {str(e)}")
        # Return empty list on error (don't fail the form)
        return []


@router.get("/api/v1/public/partners/realtors", response_model=List[PartnerSearchResult])
async def get_realtors_public(
    q: str = "",
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Public endpoint to search specifically for realtors/real estate agents.
    Now also includes all active partners with empty/unknown types to be more inclusive.
    """
    try:
        from database.models import ReferralPartner
        from sqlalchemy import or_, func

        # Include realtor-type partners AND partners with empty/unknown types
        query = db.query(ReferralPartner).filter(
            or_(
                ReferralPartner.status == "active",
                ReferralPartner.status.is_(None)
            ),
            or_(
                func.lower(ReferralPartner.type).contains("realtor"),
                func.lower(ReferralPartner.type).contains("real estate"),
                func.lower(ReferralPartner.type).contains("agent"),
                ReferralPartner.type.is_(None),
                ReferralPartner.type == "",
                func.lower(ReferralPartner.type) == "other"
            )
        )

        # Search by name, company, or email if query provided
        if q and len(q) >= 2:
            search_term = q.lower()
            query = query.filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            )

        partners = query.order_by(ReferralPartner.name).limit(limit).all()

        return [
            PartnerSearchResult(
                id=p.id,
                name=p.name or p.contact_name or "Unknown",
                company=p.company,
                email=p.email,
                phone=p.phone,
                partner_type=p.type
            )
            for p in partners
        ]

    except Exception as e:
        logger.error(f"Error searching realtors: {str(e)}")
        return []


# ============================================================================
# ACCOUNT VERIFICATION ENDPOINTS
# ============================================================================

class ResendEmailRequest(BaseModel):
    email: EmailStr
    user_id: Optional[int] = None


class SendPhoneCodeRequest(BaseModel):
    phone: str
    method: str = "text"  # "text" or "email"
    user_id: Optional[int] = None


class VerifyPhoneRequest(BaseModel):
    phone: str
    code: str
    user_id: Optional[int] = None


# Store verification codes in memory (in production, use Redis or database)
verification_codes: Dict[str, Dict] = {}


@router.post("/api/v1/verification/resend-email")
async def resend_email_verification(
    request: ResendEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Resend email verification link
    """
    try:
        import random
        import string

        # Generate verification token
        token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))

        # Store token (expires in 24 hours)
        verification_codes[f"email_{request.email}"] = {
            "token": token,
            "expires": datetime.now(timezone.utc) + timedelta(hours=24),
            "type": "email"
        }

        # Send actual verification email
        from services.notification_service import NotificationService
        notification_service = NotificationService()

        verification_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/verify-email?token={token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #f8f9fa; border-radius: 8px; padding: 30px; text-align: center;">
                <h2 style="color: #333;">Verify Your Email</h2>
                <p style="color: #666;">Please click the button below to verify your email address.</p>
                <a href="{verification_url}"
                   style="display: inline-block; background: #218D8D; color: white; padding: 12px 30px;
                          border-radius: 6px; text-decoration: none; margin: 20px 0;">
                    Verify Email
                </a>
                <p style="color: #999; font-size: 12px; margin-top: 20px;">
                    This link will expire in 24 hours.
                </p>
            </div>
        </body>
        </html>
        """

        result = notification_service.send_email(
            to_email=request.email,
            subject="Verify Your Email Address",
            html_content=html_content
        )

        logger.info(f"Email verification sent: {result}")

        return {
            "success": result.get("success", False),
            "message": "Verification email sent" if result.get("success") else "Failed to send verification email"
        }

    except Exception as e:
        logger.error(f"Error resending email verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification email")


@router.post("/api/v1/verification/send-phone-code")
async def send_phone_verification_code(
    request: SendPhoneCodeRequest,
    db: Session = Depends(get_db)
):
    """
    Send phone verification code via SMS or email
    """
    try:
        import random

        # Generate 6-digit code
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Store code (expires in 10 minutes)
        verification_codes[f"phone_{request.phone}"] = {
            "code": code,
            "expires": datetime.now(timezone.utc) + timedelta(minutes=10),
            "method": request.method
        }

        # Send actual SMS or email with code
        from services.notification_service import NotificationService
        notification_service = NotificationService()

        if request.method == "text":
            # Send SMS
            message = f"Your verification code is: {code}. This code expires in 10 minutes."
            result = notification_service.send_sms(
                to_phone=request.phone,
                message=message
            )
        else:
            # Send via email (method == "email")
            # Would need email address - for now just log
            logger.info(f"Phone verification code sent to {mask_phone(request.phone)}")
            result = {"success": True, "dry_run": True}

        logger.info(f"Phone verification sent to {mask_phone(request.phone)}: {result}")

        return {
            "success": result.get("success", False),
            "message": f"Verification code sent via {request.method}" if result.get("success") else "Failed to send verification code"
        }

    except Exception as e:
        logger.error(f"Error sending phone verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification code")


@router.post("/api/v1/verification/verify-phone")
async def verify_phone_code(
    request: VerifyPhoneRequest,
    db: Session = Depends(get_db)
):
    """
    Verify phone with the submitted code
    """
    try:
        stored = verification_codes.get(f"phone_{request.phone}")

        if not stored:
            raise HTTPException(status_code=400, detail="No verification code found. Please request a new code.")

        if datetime.now(timezone.utc) > stored["expires"]:
            # Clean up expired code
            del verification_codes[f"phone_{request.phone}"]
            raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

        if stored["code"] != request.code:
            raise HTTPException(status_code=400, detail="Invalid verification code")

        # Code verified - clean up
        del verification_codes[f"phone_{request.phone}"]

        # Update user's phone verification status if user_id provided
        if request.user_id:
            from models import User
            user = db.query(User).filter(User.id == request.user_id).first()
            if user:
                user.phone_verified = True
                user.phone_verified_at = datetime.now(timezone.utc)
                db.commit()

        return {
            "success": True,
            "message": "Phone verified successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying phone: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify phone")


@router.get("/api/v1/verification/check-email/{token}")
async def check_email_verification(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Check if email verification token is valid (called when user clicks email link)
    """
    try:
        # Find token in verification_codes
        for key, data in verification_codes.items():
            import hmac as _hmac
            if key.startswith("email_") and _hmac.compare_digest(data.get("token") or "", token):
                if datetime.now(timezone.utc) > data["expires"]:
                    del verification_codes[key]
                    return {"valid": False, "message": "Token expired"}

                # Mark email as verified
                email = key.replace("email_", "")
                del verification_codes[key]

                # Update user if found
                from models import User
                user = db.query(User).filter(User.email == email).first()
                if user:
                    user.email_verified = True
                    user.email_verified_at = datetime.now(timezone.utc)
                    db.commit()

                return {"valid": True, "email": email, "message": "Email verified"}

        return {"valid": False, "message": "Invalid token"}

    except Exception as e:
        logger.error(f"Error checking email verification: {str(e)}")
        return {"valid": False, "message": "Verification failed"}


# debug/token-info endpoint REMOVED — was unauthenticated and exposed


# =============================================================================
# SMS OPT-IN (PUBLIC)
# =============================================================================

class SMSOptInRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str  # E.164 format: +1XXXXXXXXXX
    email: Optional[str] = None
    sms_consent: bool = False
    consent_text: Optional[str] = None
    consent_source: str = "web_form"
    consent_page_url: Optional[str] = None


@router.post("/api/v1/public/sms-opt-in")
async def public_sms_opt_in(request: SMSOptInRequest, req: Request, db: Session = Depends(get_db)):
    """
    Public endpoint for SMS opt-in from the website consent form.
    Records TCPA consent and creates/updates a lead record.
    """
    import re

    # Validate phone format
    phone_digits = re.sub(r"\D", "", request.phone)
    if len(phone_digits) == 11 and phone_digits.startswith("1"):
        phone_digits = phone_digits[1:]
    if len(phone_digits) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number. Please provide a 10-digit US number.")

    e164_phone = f"+1{phone_digits}"

    try:
        # Log the consent for audit trail — leads and tcpa_consents tables
        # require organization_id (NOT NULL) which public endpoints don't have.
        # The consent is recorded in server logs with IP and timestamp until
        # the lead is claimed by a loan officer and linked to an organization.
        ip_address = req.client.host if req.client else "unknown"
        user_agent = req.headers.get("user-agent", "unknown")
        logger.info(
            f"SMS opt-in: name={request.first_name} {request.last_name}, "
            f"phone={mask_phone(e164_phone)}, email={request.email or 'N/A'}, "
            f"consent={request.sms_consent}, source={request.consent_source}, "
            f"ip={ip_address}, ua={user_agent[:100]}"
        )

        return {
            "status": "success",
            "message": "You have been opted in to receive SMS updates. Reply STOP at any time to unsubscribe.",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"SMS opt-in error: {e}")
        raise HTTPException(status_code=500, detail="Unable to process your request. Please try again.")
# token metadata (workspace, scope, expiry) to anyone with a token value.


# ─── Contact Form ────────────────────────────────────────────────────────────

class ContactFormRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    subject: str = "other"
    message: str


@router.post("/api/v1/public/contact")
async def public_contact_form(request: ContactFormRequest, req: Request, db: Session = Depends(get_db)):
    """
    Public endpoint for the website contact form.
    Sends notification to admin@perenniaai.com and creates a lead record.
    """
    import re

    # Basic validation
    if len(request.message.strip()) < 5:
        raise HTTPException(status_code=400, detail="Please provide a message.")

    # Sanitize phone if provided
    e164_phone = None
    if request.phone:
        phone_digits = re.sub(r"\D", "", request.phone)
        if len(phone_digits) == 11 and phone_digits.startswith("1"):
            phone_digits = phone_digits[1:]
        if len(phone_digits) == 10:
            e164_phone = f"+1{phone_digits}"

    subject_labels = {
        "demo": "Demo Request",
        "pricing": "Pricing Inquiry",
        "support": "Support Request",
        "partnership": "Partnership Inquiry",
        "other": "General Inquiry",
    }
    subject_label = subject_labels.get(request.subject, "General Inquiry")

    try:
        # Send notification email to admin
        try:
            email_service = EmailService()
            admin_email = os.getenv("CONTACT_FORM_EMAIL", "admin@perenniaai.com")

            email_body = f"""
New contact form submission from www.perenniaai.com:

Name: {request.first_name} {request.last_name}
Email: {request.email}
Phone: {e164_phone or 'Not provided'}
Company: {request.company or 'Not provided'}
Subject: {subject_label}

Message:
{request.message}

---
Submitted from: {req.headers.get('referer', 'Unknown')}
IP: {req.client.host if req.client else 'Unknown'}
"""

            await email_service.send_email(
                to_email=admin_email,
                subject=f"[Perennia AI] {subject_label} from {request.first_name} {request.last_name}",
                body=email_body,
            )
        except Exception as e:
            logger.warning(f"Failed to send contact form notification email: {e}")

        # Create a lead record
        try:
            from sqlalchemy import text

            db.execute(
                text("""
                    INSERT INTO leads (first_name, last_name, email, phone, source, stage, notes, created_at)
                    VALUES (:first_name, :last_name, :email, :phone, 'website_contact', 'New', :notes, :now)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "first_name": request.first_name,
                    "last_name": request.last_name,
                    "email": request.email,
                    "phone": e164_phone,
                    "notes": f"[{subject_label}] {request.message[:500]}",
                    "now": datetime.now(timezone.utc),
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Lead create during contact form failed (non-blocking): {e}")

        logger.info(f"Contact form submission from {request.email} ({subject_label})")

        return {
            "status": "success",
            "message": "Thank you for reaching out. We'll get back to you within one business day.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Contact form error: {e}")
        raise HTTPException(status_code=500, detail="Unable to process your request. Please try again.")


# =============================================================================
# NEWSLETTER SUBSCRIPTION
# =============================================================================

class NewsletterRequest(BaseModel):
    email: EmailStr


@router.post("/api/v1/public/newsletter")
async def public_newsletter_subscribe(request: NewsletterRequest, req: Request, db: Session = Depends(get_db)):
    """
    Public endpoint for newsletter subscription from the website footer.
    Stores the subscriber email and sends a welcome confirmation.
    """
    try:
        from sqlalchemy import text

        # Upsert into newsletter_subscribers table (create if not exists)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                subscribed_at TIMESTAMPTZ DEFAULT NOW(),
                unsubscribed_at TIMESTAMPTZ,
                source TEXT DEFAULT 'website_footer',
                is_active BOOLEAN DEFAULT TRUE
            )
        """))

        db.execute(
            text("""
                INSERT INTO newsletter_subscribers (email, subscribed_at, source, is_active)
                VALUES (:email, :now, 'website_footer', TRUE)
                ON CONFLICT (email) DO UPDATE SET
                    is_active = TRUE,
                    subscribed_at = :now,
                    unsubscribed_at = NULL
            """),
            {"email": request.email, "now": datetime.now(timezone.utc)},
        )
        db.commit()

        # Send welcome email (non-blocking)
        try:
            email_service = EmailService()
            await email_service.send_email(
                to_email=request.email,
                subject="Welcome to Perennia AI Updates",
                body=f"""Thanks for subscribing to Perennia AI updates!

You'll receive the latest mortgage industry insights, product updates, and tips for loan officers.

If you ever want to unsubscribe, just reply to any email or contact us at admin@perenniaai.com.

— The Perennia AI Team
www.perenniaai.com
""",
            )
        except Exception as e:
            logger.debug(f"Newsletter welcome email skipped: {e}")

        # Also notify admin
        try:
            admin_email = os.getenv("CONTACT_FORM_EMAIL", "admin@perenniaai.com")
            email_service = EmailService()
            await email_service.send_email(
                to_email=admin_email,
                subject=f"[Perennia AI] New newsletter subscriber: {request.email}",
                body=f"New newsletter subscription from {request.email}\nSource: website footer\nIP: {req.client.host if req.client else 'Unknown'}",
            )
        except Exception:
            pass

        logger.info(f"Newsletter subscription: {request.email}")
        return {"status": "success", "message": "You're subscribed!"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Newsletter subscription error: {e}")
        raise HTTPException(status_code=500, detail="Unable to subscribe. Please try again.")
