"""
Seed Demo Account for Apple App Store Review
=============================================
Creates an isolated organization with a demo user and fully populated sample data.

Usage:
    cd backend
    python scripts/seed_demo_account.py

Credentials:
    Email:    demo@perenniaai.com
    Password: (set via DEMO_USER_PASSWORD env var)
"""
from __future__ import annotations

import os
import sys
import random
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt as _bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


class _BcryptCompat:
    """Drop-in replacement providing .hash() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

pwd_context = _BcryptCompat()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
else:
    engine = None
    Session = None

# ─── Constants ───────────────────────────────────────────────────────────────

DEMO_EMAIL = "demo@perenniaai.com"
DEMO_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "Password1!")
ORG_NAME = "Summit Peak Mortgage"
ORG_SLUG = "summit-peak-demo-appstore"

NOW = datetime.now(timezone.utc)
TODAY = date.today()


def main(external_session=None):
    db = external_session or Session()
    try:
        # Check if demo org already exists
        existing = db.execute(text("SELECT id FROM organizations WHERE slug = :s"), {"s": ORG_SLUG}).fetchone()
        if existing:
            print(f"Demo org already exists (id={existing[0]}). Deleting and recreating...")
            _nuke_demo_org(db, existing[0])
            db.commit()

        # ── 1. Organization ──────────────────────────────────────────────
        db.execute(text("""
            INSERT INTO organizations (name, slug, domain, subscription_tier, is_active, timezone, created_at)
            VALUES (:name, :slug, :domain, :tier, TRUE, :tz, :now)
        """), {"name": ORG_NAME, "slug": ORG_SLUG, "domain": "summitpeakdemo.com",
               "tier": "professional", "tz": "America/Chicago", "now": NOW})
        org_id = db.execute(text("SELECT id FROM organizations WHERE slug = :s"), {"s": ORG_SLUG}).scalar()
        print(f"  Created organization: {ORG_NAME} (id={org_id})")

        # ── 2. Branch ────────────────────────────────────────────────────
        db.execute(text("""
            INSERT INTO branches (name, organization_id, nmls_id, company, created_at)
            VALUES (:name, :oid, :nmls, :co, :now)
        """), {"name": "Austin Main Office", "oid": org_id, "nmls": "1234567", "co": ORG_NAME, "now": NOW})
        branch_id = db.execute(text(
            "SELECT id FROM branches WHERE organization_id = :oid ORDER BY id DESC LIMIT 1"
        ), {"oid": org_id}).scalar()

        # ── 3. Users ─────────────────────────────────────────────────────
        demo_hash = pwd_context.hash(DEMO_PASSWORD)

        users = [
            # (email, first, last, role, permission_role, nmls, title, is_demo_user)
            (DEMO_EMAIL, "Alex", "Morgan", "loan_officer", "sales", "ML-987654", "Senior Loan Officer", True),
            ("sarah.chen@summitpeakdemo.com", "Sarah", "Chen", "loan_officer", "sales", "ML-112233", "Loan Officer", False),
            ("james.brooks@summitpeakdemo.com", "James", "Brooks", "loan_officer", "sales", "ML-445566", "Loan Officer", False),
            ("maria.gonzalez@summitpeakdemo.com", "Maria", "Gonzalez", "processor", "processing", None, "Loan Processor", False),
            ("kevin.wright@summitpeakdemo.com", "Kevin", "Wright", "processor", "processing", None, "Senior Processor", False),
            ("diana.patel@summitpeakdemo.com", "Diana", "Patel", "underwriter", "operations", None, "Underwriter", False),
            ("tom.reeves@summitpeakdemo.com", "Tom", "Reeves", "management", "management", "ML-778899", "Branch Manager", False),
        ]

        user_ids = {}
        for email, first, last, role, perm, nmls, title, is_demo in users:
            pw = demo_hash if is_demo else pwd_context.hash("TeamMember2026!")
            db.execute(text("""
                INSERT INTO users (email, hashed_password, first_name, last_name, role, permission_role,
                    organization_id, branch_id, nmls_number, title, is_active, onboarding_completed,
                    email_verified, timezone, briefing_enabled, briefing_hour, created_at)
                VALUES (:email, :pw, :fn, :ln, :role, :perm, :oid, :bid, :nmls, :title,
                    TRUE, TRUE, TRUE, :tz, TRUE, 7, :now)
            """), {"email": email, "pw": pw, "fn": first, "ln": last, "role": role, "perm": perm,
                   "oid": org_id, "bid": branch_id, "nmls": nmls, "title": title, "tz": "America/Chicago", "now": NOW})
            uid = db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).scalar()
            user_ids[email] = uid

        demo_user_id = user_ids[DEMO_EMAIL]
        lo_ids = [user_ids[DEMO_EMAIL], user_ids["sarah.chen@summitpeakdemo.com"], user_ids["james.brooks@summitpeakdemo.com"]]
        print(f"  Created {len(users)} users (demo user id={demo_user_id})")

        # Set Tom as manager of LOs
        for lo_email in [DEMO_EMAIL, "sarah.chen@summitpeakdemo.com", "james.brooks@summitpeakdemo.com"]:
            db.execute(text("UPDATE users SET manager_id = :mid WHERE id = :uid"),
                       {"mid": user_ids["tom.reeves@summitpeakdemo.com"], "uid": user_ids[lo_email]})

        # ── 4. Subscription ──────────────────────────────────────────────
        # Give the demo user a long-lived active subscription
        plan_id = db.execute(text("SELECT id FROM subscription_plans WHERE is_active = TRUE LIMIT 1")).scalar()
        if plan_id:
            for uid in user_ids.values():
                db.execute(text("""
                    INSERT INTO subscriptions (user_id, plan_id, status, current_period_start, current_period_end, trial_end, created_at)
                    VALUES (:uid, :pid, :status, :start, :end, :trial, :now)
                """), {"uid": uid, "pid": plan_id, "status": "active",
                       "start": NOW, "end": NOW + timedelta(days=365), "trial": NOW + timedelta(days=365), "now": NOW})
            print(f"  Created subscriptions for all users")
        else:
            print("  Skipped subscriptions (no active plans found)")

        # ── 5. Leads ─────────────────────────────────────────────────────
        leads_data = [
            # (first, last, email, phone, stage, source, score, credit, loan_amt, purpose, property_addr, owner_idx)
            ("Michael", "Thompson", "m.thompson@email.com", "512-555-1001", "New", "Website", 82, 740, 425000, "Purchase", "4521 Oak Valley Dr, Austin TX 78745", 0),
            ("Jennifer", "Davis", "j.davis@email.com", "512-555-1002", "New", "Zillow", 67, 695, 315000, "Purchase", "1823 Maple Creek Ln, Round Rock TX 78664", 0),
            ("Robert", "Wilson", "r.wilson@email.com", "512-555-1003", "Attempted Contact", "Referral", 75, 720, 550000, "Purchase", "9012 Cedar Ridge Ct, Lakeway TX 78734", 0),
            ("Emily", "Martinez", "e.martinez@email.com", "512-555-1004", "Prospect", "Realtor.com", 88, 780, 380000, "Purchase", "3456 Bluebonnet Blvd, Georgetown TX 78626", 0),
            ("David", "Anderson", "d.anderson@email.com", "512-555-1005", "Prospect", "Rate Quote", 91, 760, 475000, "Refinance", "7890 Barton Springs Rd, Austin TX 78704", 0),
            ("Lisa", "Taylor", "l.taylor@email.com", "512-555-1006", "Application", "Website", 85, 730, 290000, "Purchase", "2345 Pecan Park Way, Cedar Park TX 78613", 1),
            ("Christopher", "Brown", "c.brown@email.com", "512-555-1007", "Pre-Qualified", "Referral", 79, 710, 525000, "Purchase", "6789 Hill Country Dr, Dripping Springs TX 78620", 1),
            ("Amanda", "Jackson", "a.jackson@email.com", "512-555-1008", "Pre-Approved", "Zillow", 93, 790, 615000, "Purchase", "1234 Congress Ave, Austin TX 78701", 0),
            ("Daniel", "White", "d.white@email.com", "512-555-1009", "Under Contract", "LendingTree", 87, 755, 340000, "Purchase", "5678 Lamar Blvd, Austin TX 78751", 0),
            ("Jessica", "Harris", "j.harris@email.com", "512-555-1010", "Document Fulfillment", "Rate Quote", 90, 770, 460000, "Refinance", "3210 South 1st St, Austin TX 78704", 2),
            ("Matthew", "Lewis", "m.lewis@email.com", "512-555-1011", "Long-Term Nurture", "Website", 45, 640, 200000, "Purchase", None, 1),
            ("Ashley", "Clark", "a.clark@email.com", "512-555-1012", "Credit Repair", "Cold Call", 30, 580, 175000, "Purchase", None, 2),
            ("Ryan", "Walker", "r.walker@email.com", "512-555-1013", "Funded", "Referral", 95, 800, 520000, "Purchase", "8765 Bee Cave Rd, Austin TX 78746", 0),
            ("Nicole", "Robinson", "n.robinson@email.com", "512-555-1014", "Closed", "Website", 88, 745, 385000, "Purchase", "4321 Research Blvd, Austin TX 78759", 0),
            ("Brandon", "Young", "b.young@email.com", "512-555-1015", "Pre-Approved", "Realtor Referral", 86, 735, 295000, "Purchase", "9876 Parmer Ln, Austin TX 78727", 2),
            ("Stephanie", "King", "s.king@email.com", "512-555-1016", "Prospect", "Facebook Ad", 72, 700, 265000, "Purchase", "6543 Slaughter Ln, Austin TX 78748", 1),
            ("Tyler", "Scott", "t.scott@email.com", "512-555-1017", "New", "Instagram", 58, 680, 310000, "Purchase", None, 0),
            ("Megan", "Adams", "m.adams@email.com", "512-555-1018", "Attempted Contact", "Google Ads", 63, 690, 430000, "Refinance", "2109 East 7th St, Austin TX 78702", 0),
            ("Kevin", "Nelson", "k.nelson@email.com", "512-555-1019", "Application", "Rate Quote", 84, 725, 355000, "Purchase", "7654 Burnet Rd, Austin TX 78757", 2),
            ("Rachel", "Carter", "r.carter@email.com", "512-555-1020", "Pre-Qualified", "Referral", 77, 715, 490000, "Purchase", "3456 Westlake Dr, Austin TX 78746", 1),
        ]

        lead_ids = []
        for i, (fn, ln, email, phone, stage, source, score, credit, amt, purpose, addr, oi) in enumerate(leads_data):
            created = NOW - timedelta(days=random.randint(5, 90))
            last_contact = NOW - timedelta(days=random.randint(0, 14)) if stage not in ("Long-Term Nurture", "Credit Repair") else NOW - timedelta(days=random.randint(20, 45))
            db.execute(text("""
                INSERT INTO leads (organization_id, first_name, last_name, name, email, phone, stage, source,
                    ai_score, credit_score, loan_amount, loan_purpose, property_address, property_type,
                    owner_id, created_at, updated_at, last_contact, annual_income, employment_status)
                VALUES (:oid, :fn, :ln, :name, :email, :phone, :stage, :source,
                    :score, :credit, :amt, :purpose, :addr, :ptype,
                    :owner, :created, :updated, :lc, :income, :emp)
            """), {"oid": org_id, "fn": fn, "ln": ln, "name": f"{fn} {ln}", "email": email, "phone": phone,
                   "stage": stage, "source": source, "score": score, "credit": credit, "amt": amt,
                   "purpose": purpose, "addr": addr, "ptype": "Single Family",
                   "owner": lo_ids[oi], "created": created, "updated": NOW, "lc": last_contact,
                   "income": random.randint(75000, 200000), "emp": "Employed"})
            lid = db.execute(text(
                "SELECT id FROM leads WHERE organization_id = :oid AND email = :e"
            ), {"oid": org_id, "e": email}).scalar()
            lead_ids.append(lid)

        print(f"  Created {len(leads_data)} leads")

        # ── 6. Loans ─────────────────────────────────────────────────────
        loans_data = [
            # (loan_num, borrower, email, stage, type, amount, rate, property, lo_idx, closing_days_from_now)
            ("SP-2026-001", "Amanda Jackson", "a.jackson@email.com", "PROCESSING", "conventional", 615000, 6.875, "1234 Congress Ave, Austin TX 78701", 0, 35),
            ("SP-2026-002", "Daniel White", "d.white@email.com", "SUBMITTED", "fha", 340000, 6.625, "5678 Lamar Blvd, Austin TX 78751", 0, 28),
            ("SP-2026-003", "Jessica Harris", "j.harris@email.com", "UNDERWRITING", "conventional", 460000, 6.750, "3210 South 1st St, Austin TX 78704", 2, 25),
            ("SP-2026-004", "Lisa Taylor", "l.taylor@email.com", "APPLICATION", "conventional", 290000, 7.000, "2345 Pecan Park Way, Cedar Park TX 78613", 1, 45),
            ("SP-2026-005", "Christopher Brown", "c.brown@email.com", "CONDITIONAL_APPROVAL", "jumbo", 525000, 7.125, "6789 Hill Country Dr, Dripping Springs TX 78620", 1, 18),
            ("SP-2026-006", "Ryan Walker", "r.walker@email.com", "FUNDED", "conventional", 520000, 6.500, "8765 Bee Cave Rd, Austin TX 78746", 0, -15),
            ("SP-2026-007", "Nicole Robinson", "n.robinson@email.com", "FUNDED", "fha", 385000, 6.375, "4321 Research Blvd, Austin TX 78759", 0, -30),
            ("SP-2026-008", "Kevin Nelson", "k.nelson@email.com", "DISCLOSED", "conventional", 355000, 6.950, "7654 Burnet Rd, Austin TX 78757", 2, 40),
            ("SP-2026-009", "David Anderson", "d.anderson@email.com", "CLEAR_TO_CLOSE", "conventional", 475000, 6.250, "7890 Barton Springs Rd, Austin TX 78704", 0, 8),
            ("SP-2026-010", "Brandon Young", "b.young@email.com", "DOCS_OUT", "va", 295000, 6.125, "9876 Parmer Ln, Austin TX 78727", 2, 5),
        ]

        loan_ids = []
        for ln_num, borrower, email, stage, ltype, amount, rate, prop, oi, close_days in loans_data:
            closing = TODAY + timedelta(days=close_days) if close_days > 0 else TODAY + timedelta(days=close_days)
            app_date = closing - timedelta(days=random.randint(30, 50))
            lock_date = app_date + timedelta(days=random.randint(5, 15))
            lock_exp = lock_date + timedelta(days=45)
            funded_date = closing if close_days < 0 else None
            stage_changed = NOW - timedelta(days=random.randint(1, 7))

            # SLA milestone dates
            disc_sent = app_date + timedelta(days=2) if stage not in ("APPLICATION",) else None
            uw_recv = app_date + timedelta(days=random.randint(12, 18)) if stage in ("UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            approved = uw_recv + timedelta(days=random.randint(3, 7)) if uw_recv and stage in ("CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            ctc_date = approved + timedelta(days=random.randint(2, 5)) if approved and stage in ("CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED") else None
            cd_sent = ctc_date - timedelta(days=4) if ctc_date else None

            db.execute(text("""
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
            """), {
                "oid": org_id, "ln": ln_num, "bn": borrower, "be": email,
                "stage": stage, "lt": ltype, "amt": amount, "pp": int(amount * 1.05),
                "rate": rate, "term": 360,
                "addr": prop, "pt": "single_family", "ot": "primary",
                "lo": lo_ids[oi], "proc": "Maria Gonzalez",
                "close": closing, "funded": funded_date,
                "app_date": app_date, "disc_sent": disc_sent,
                "lock": lock_date, "lock_exp": lock_exp,
                "uw_recv": uw_recv, "approved": approved, "ctc": ctc_date,
                "cd_sent": cd_sent,
                "sc": stage_changed, "created": NOW - timedelta(days=random.randint(20, 60)),
                "updated": NOW, "lo_name": "Alex Morgan" if oi == 0 else "Sarah Chen" if oi == 1 else "James Brooks",
                "program": f"{ltype.upper()} 30yr Fixed", "lender": "Summit Peak Wholesale",
            })
            lid = db.execute(text(
                "SELECT id FROM loans WHERE organization_id = :oid AND loan_number = :ln"
            ), {"oid": org_id, "ln": ln_num}).scalar()
            loan_ids.append(lid)

        print(f"  Created {len(loans_data)} loans")

        # ── 7. Activities ────────────────────────────────────────────────
        activity_templates = [
            ("Call", "Introductory call with borrower. Discussed loan options and timeline.", 12),
            ("Call", "Follow-up call to review documents needed for application.", 8),
            ("Email", "Sent pre-qualification letter and next steps checklist.", None),
            ("Email", "Rate lock confirmation sent to borrower.", None),
            ("Email", "Closing disclosure sent for e-signature.", None),
            ("Meeting", "In-person consultation to review loan scenarios and affordability.", 45),
            ("Meeting", "Video call to walk through application and collect initial docs.", 30),
            ("Note", "Borrower mentioned relocating from California. Tight timeline — needs to close by month end.", None),
            ("Note", "Appraisal came in above contract price. No issues.", None),
            ("SMS", "Sent reminder about upcoming document deadline.", None),
            ("Call", "Checked in on employment verification status.", 5),
            ("Email", "Sent monthly rate market update newsletter.", None),
            ("Note", "Processor flagged missing page 2 of bank statement. Requested from borrower.", None),
            ("Call", "Discussed rate lock options. Borrower wants to float for now.", 15),
            ("Meeting", "Pre-closing review with borrower and realtor. All clear.", 25),
        ]

        act_count = 0
        for lead_id in lead_ids[:10]:
            for _ in range(random.randint(2, 5)):
                tpl = random.choice(activity_templates)
                days_ago = random.randint(0, 30)
                db.execute(text("""
                    INSERT INTO activities (organization_id, type, content, lead_id, user_id, duration, created_at)
                    VALUES (:oid, :type, :content, :lid, :uid, :dur, :created)
                """), {"oid": org_id, "type": tpl[0], "content": tpl[1], "lid": lead_id,
                       "uid": random.choice(lo_ids), "dur": tpl[2], "created": NOW - timedelta(days=days_ago, hours=random.randint(0, 8))})
                act_count += 1

        for loan_id in loan_ids:
            for _ in range(random.randint(3, 6)):
                tpl = random.choice(activity_templates)
                days_ago = random.randint(0, 25)
                db.execute(text("""
                    INSERT INTO activities (organization_id, type, content, loan_id, user_id, duration, created_at)
                    VALUES (:oid, :type, :content, :lid, :uid, :dur, :created)
                """), {"oid": org_id, "type": tpl[0], "content": tpl[1], "lid": loan_id,
                       "uid": random.choice(lo_ids), "dur": tpl[2], "created": NOW - timedelta(days=days_ago, hours=random.randint(0, 8))})
                act_count += 1

        print(f"  Created {act_count} activities")

        # ── 8. Tasks ─────────────────────────────────────────────────────
        tasks_data = [
            ("Follow up with Michael Thompson", "Call to discuss pre-approval options", "pending", "high", 0, 1),
            ("Collect W-2s from Jennifer Davis", "Need 2024 and 2025 W-2 documents", "pending", "high", 3, 2),
            ("Submit Amanda Jackson file to UW", "All docs collected, ready for submission", "in_progress", "high", 0, 0),
            ("Order appraisal for Daniel White", "FHA appraisal — use approved appraiser list", "in_progress", "medium", 0, 1),
            ("Rate lock decision for Jessica Harris", "Lock expires Friday — need borrower decision", "pending", "high", 2, -1),
            ("Send closing disclosure to David Anderson", "CD ready, need 3-day waiting period before close", "completed", "high", 0, -3),
            ("Schedule closing for Brandon Young", "VA loan — coordinate with title company", "in_progress", "medium", 2, 3),
            ("Review conditions for Christopher Brown", "UW requested additional income verification", "pending", "high", 1, 1),
            ("Send rate update to nurture leads", "Monthly rate market email to long-term nurture list", "pending", "low", 0, 5),
            ("Verify employment for Lisa Taylor", "VOE not received — follow up with employer", "in_progress", "medium", 1, 0),
            ("Review appraisal for SP-2026-003", "Appraisal received — review before forwarding to UW", "pending", "medium", 2, 2),
            ("Clear conditions on SP-2026-005", "2 remaining conditions: updated bank stmt + gift letter", "in_progress", "high", 1, 0),
            ("Post-close follow-up call with Ryan Walker", "Funded last week — check in and ask for referral", "pending", "medium", 0, 3),
            ("Update CRM notes for Nicole Robinson", "Closed file — update pipeline and move to MUM", "completed", "low", 0, -5),
            ("Prep weekly pipeline report for Tom", "Manager requested updated numbers by Friday", "pending", "medium", 0, 4),
            ("Call Robert Wilson back", "Left voicemail 3 days ago — no response yet", "pending", "high", 0, 0),
            ("Review title commitment for SP-2026-009", "Title came in — check for liens or exceptions", "in_progress", "high", 0, 1),
            ("Schedule pre-approval consultation with Emily Martinez", "Hot lead — score 88, referred by realtor", "pending", "high", 0, 1),
            ("Send welcome packet to Kevin Nelson", "New application — send intro email and doc checklist", "completed", "medium", 2, -2),
            ("Check credit supplement for SP-2026-002", "FHA requires credit supplement — order from bureau", "in_progress", "medium", 0, 2),
        ]

        for title, desc, status, priority, lo_idx, due_offset in tasks_data:
            completed_at = NOW - timedelta(days=abs(due_offset)) if status == "completed" else None
            db.execute(text("""
                INSERT INTO tasks (organization_id, title, description, status, priority, due_date,
                    owner_id, completed_at, created_at, updated_at)
                VALUES (:oid, :title, :desc, :status, :priority, :due,
                    :owner, :completed, :created, :updated)
            """), {"oid": org_id, "title": title, "desc": desc, "status": status, "priority": priority,
                   "due": TODAY + timedelta(days=due_offset), "owner": lo_ids[lo_idx],
                   "completed": completed_at, "created": NOW - timedelta(days=random.randint(1, 10)), "updated": NOW})

        print(f"  Created {len(tasks_data)} tasks")

        # ── 9. Documents ─────────────────────────────────────────────────
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
                    # Not all loans have all docs
                    if random.random() < 0.75:
                        db.execute(text("""
                            INSERT INTO documents (organization_id, loan_id, doc_type, doc_category, status,
                                filename, uploaded_at, source, created_at)
                            VALUES (:oid, :lid, :dt, :cat, :status, :fn, :uploaded, :src, :created)
                        """), {"oid": org_id, "lid": loan_id, "dt": dt, "cat": cat,
                               "status": "active", "fn": f"{dt}_{loan_id}.pdf",
                               "uploaded": NOW - timedelta(days=random.randint(1, 20)),
                               "src": random.choice(["borrower_upload", "email_intake", "los_sync"]),
                               "created": NOW - timedelta(days=random.randint(1, 20))})
                        doc_count += 1

        print(f"  Created {doc_count} documents")

        # ── 10. Compliance Alerts ────────────────────────────────────────
        alerts_data = [
            ("LE_TIMING", "critical", "LE Deadline Approaching", "Loan Estimate must be sent within 3 business days of application", "open", loan_ids[3], 2),
            ("LOCK_EXPIRING", "high", "Rate Lock Expiring Soon", "Rate lock on SP-2026-005 expires in 3 days — extend or close", "open", loan_ids[4], 3),
            ("MISSING_DOCUMENT", "medium", "Missing Bank Statement", "Page 2 of October bank statement not received", "open", loan_ids[0], 5),
            ("CD_TIMING", "high", "CD Delivery Deadline", "Closing Disclosure must be delivered 3 business days before closing", "open", loan_ids[8], 4),
            ("TRID_VIOLATION", "critical", "Potential TRID Timing Issue", "LE was sent 4 business days after application — review for compliance", "acknowledged", loan_ids[7], None),
            ("APPRAISAL_REVIEW", "medium", "Appraisal Below Contract Price", "Appraisal came in $15K below — may need renegotiation", "resolved", loan_ids[5], None),
            ("CONDITION_PAST_DUE", "high", "UW Condition Past Due", "Employment verification requested 10 days ago — still outstanding", "open", loan_ids[2], 1),
            ("RATE_CHANGE", "medium", "Rate Market Movement", "Rates moved +0.125% since lock — monitor for borrower impact", "resolved", loan_ids[6], None),
        ]

        for atype, severity, title, desc, status, lid, deadline_days in alerts_data:
            deadline = TODAY + timedelta(days=deadline_days) if deadline_days else None
            resolved_at = NOW - timedelta(days=random.randint(1, 5)) if status == "resolved" else None
            db.execute(text("""
                INSERT INTO compliance_alerts (organization_id, loan_id, alert_type, severity, title,
                    description, status, deadline_date, created_at, resolved_at)
                VALUES (:oid, :lid, :atype, :sev, :title, :desc, :status, :deadline, :created, :resolved)
            """), {"oid": org_id, "lid": lid, "atype": atype, "sev": severity, "title": title,
                   "desc": desc, "status": status, "deadline": deadline,
                   "created": NOW - timedelta(days=random.randint(1, 10)), "resolved": resolved_at})

        print(f"  Created {len(alerts_data)} compliance alerts")

        # ── 11. Referral Partners ────────────────────────────────────────
        partners_data = [
            ("Laura", "Mitchell", "Mitchell Realty Group", "realtor", "laura@mitchellrealty.com", "512-555-2001", 12, 8, 6, 2850000, "gold"),
            ("Greg", "Hernandez", "Hernandez & Associates", "realtor", "greg@hernandezre.com", "512-555-2002", 8, 5, 3, 1650000, "silver"),
            ("Samantha", "Lee", "Capital Title Partners", "title_company", "sam@captitle.com", "512-555-2003", 6, 2, 4, 1900000, "silver"),
            ("Brian", "Cooper", "Cooper Insurance Agency", "insurance_agent", "brian@cooperins.com", "512-555-2004", 4, 3, 2, 890000, "bronze"),
            ("Angela", "Foster", "Austin Home Inspections", "home_inspector", "angela@austininspect.com", "512-555-2005", 3, 1, 1, 450000, "bronze"),
            ("Mark", "Sullivan", "Sullivan Financial Planning", "financial_advisor", "mark@sullivanfp.com", "512-555-2006", 5, 4, 3, 1400000, "silver"),
            ("Karen", "Phillips", "Lone Star Real Estate", "realtor", "karen@lonestarRE.com", "512-555-2007", 15, 10, 9, 4200000, "platinum"),
            ("Jason", "Rivera", "Rivera Homes", "builder", "jason@riverahomes.com", "512-555-2008", 7, 3, 4, 2100000, "silver"),
        ]

        partner_ids = []
        for fn, ln, biz, cat, email, phone, refs_in, refs_out, closed, vol, tier in partners_data:
            db.execute(text("""
                INSERT INTO referral_partners (organization_id, name, business_name, category,
                    email, phone, referrals_in, referrals_out, closed_loans, volume,
                    status, loyalty_tier, owner_id, created_at)
                VALUES (:oid, :name, :biz, :cat, :email, :phone, :ri, :ro, :cl, :vol,
                    :status, :tier, :owner, :created)
            """), {"oid": org_id, "name": f"{fn} {ln}", "biz": biz, "cat": cat, "email": email,
                   "phone": phone, "ri": refs_in, "ro": refs_out, "cl": closed, "vol": vol,
                   "status": "active", "tier": tier, "owner": random.choice(lo_ids),
                   "created": NOW - timedelta(days=random.randint(30, 365))})
            pid = db.execute(text(
                "SELECT id FROM referral_partners WHERE organization_id = :oid AND email = :e"
            ), {"oid": org_id, "e": email}).scalar()
            partner_ids.append(pid)

        print(f"  Created {len(partners_data)} referral partners")

        # ── 12. Loan Team Members ────────────────────────────────────────
        team_count = 0
        for i, loan_id in enumerate(loan_ids[:8]):
            # Realtor
            db.execute(text("""
                INSERT INTO loan_team_members (loan_id, name, role, email, phone, company,
                    is_employee, referral_partner_id, organization_id, created_at)
                VALUES (:lid, :name, :role, :email, :phone, :co, FALSE, :rpid, :oid, :now)
            """), {"lid": loan_id, "name": partners_data[i % 3][0] + " " + partners_data[i % 3][1],
                   "role": "Realtor", "email": partners_data[i % 3][4], "phone": partners_data[i % 3][5],
                   "co": partners_data[i % 3][2], "rpid": partner_ids[i % 3], "oid": org_id, "now": NOW})
            # Title agent
            db.execute(text("""
                INSERT INTO loan_team_members (loan_id, name, role, email, phone, company,
                    is_employee, organization_id, created_at)
                VALUES (:lid, :name, :role, :email, :phone, :co, FALSE, :oid, :now)
            """), {"lid": loan_id, "name": "Samantha Lee", "role": "Title Agent",
                   "email": "sam@captitle.com", "phone": "512-555-2003", "co": "Capital Title Partners",
                   "oid": org_id, "now": NOW})
            team_count += 2

        print(f"  Created {team_count} loan team members")

        # ── 13. Disclosure Events ────────────────────────────────────────
        disc_count = 0
        for i, loan_id in enumerate(loan_ids):
            stage = loans_data[i][3]
            if stage == "APPLICATION":
                continue
            # Initial LE
            db.execute(text("""
                INSERT INTO disclosure_events (organization_id, loan_id, disclosure_type,
                    sent_at, delivery_method, is_on_time, created_at)
                VALUES (:oid, :lid, :dt, :sent, :dm, :ot, :created)
            """), {"oid": org_id, "lid": loan_id, "dt": "loan_estimate",
                   "sent": NOW - timedelta(days=random.randint(15, 40)),
                   "dm": "email", "ot": True, "created": NOW - timedelta(days=random.randint(15, 40))})
            disc_count += 1

            if stage in ("CLEAR_TO_CLOSE", "DOCS_OUT", "FUNDED"):
                db.execute(text("""
                    INSERT INTO disclosure_events (organization_id, loan_id, disclosure_type,
                        sent_at, delivery_method, is_on_time, created_at)
                    VALUES (:oid, :lid, :dt, :sent, :dm, :ot, :created)
                """), {"oid": org_id, "lid": loan_id, "dt": "closing_disclosure",
                       "sent": NOW - timedelta(days=random.randint(3, 10)),
                       "dm": "esign", "ot": True, "created": NOW - timedelta(days=random.randint(3, 10))})
                disc_count += 1

        print(f"  Created {disc_count} disclosure events")

        # ── 14. Loan Fees ────────────────────────────────────────────────
        fee_count = 0
        for loan_id in loan_ids[:7]:
            fees = [
                ("Origination Fee", "origination", "zero", 2500, 2500),
                ("Appraisal Fee", "appraisal", "zero", 550, 550),
                ("Credit Report Fee", "credit", "zero", 75, 75),
                ("Title Insurance", "title", "ten_percent", 1800, 1850),
                ("Title Search", "title", "ten_percent", 350, 375),
                ("Recording Fees", "government", "ten_percent", 125, 130),
                ("Flood Certification", "other", "unlimited", 15, 20),
                ("Homeowners Insurance", "insurance", "unlimited", 1400, 1450),
            ]
            for fn, fc, tc, le, cd in fees:
                db.execute(text("""
                    INSERT INTO loan_fees (organization_id, loan_id, fee_name, fee_category,
                        tolerance_category, le_amount, cd_amount, created_at)
                    VALUES (:oid, :lid, :fn, :fc, :tc, :le, :cd, :now)
                """), {"oid": org_id, "lid": loan_id, "fn": fn, "fc": fc, "tc": tc,
                       "le": le, "cd": cd, "now": NOW})
                fee_count += 1

        print(f"  Created {fee_count} loan fees")

        # ── 15. Scheduler Config & Appointments ──────────────────────────
        # Scheduler config for demo user
        db.execute(text("""
            INSERT INTO scheduler_configs (organization_id, user_id, config_name, timezone,
                default_duration_minutes, min_notice_hours, max_advance_days,
                max_meetings_per_day, is_active, created_at)
            VALUES (:oid, :uid, :name, :tz, :dur, :notice, :advance, :max, TRUE, :now)
        """), {"oid": org_id, "uid": demo_user_id, "name": "Default Schedule",
               "tz": "America/Chicago", "dur": 30, "notice": 2, "advance": 30, "max": 8, "now": NOW})
        config_id = db.execute(text(
            "SELECT id FROM scheduler_configs WHERE user_id = :uid ORDER BY id DESC LIMIT 1"
        ), {"uid": demo_user_id}).scalar()

        # Availability slots (Mon-Fri 9am-5pm)
        for dow in range(1, 6):  # Mon=1 through Fri=5
            db.execute(text("""
                INSERT INTO availability_slots (organization_id, config_id, user_id,
                    day_of_week, start_time, end_time, priority, is_active, created_at)
                VALUES (:oid, :cid, :uid, :dow, :start, :end, :pri, TRUE, :now)
            """), {"oid": org_id, "cid": config_id, "uid": demo_user_id,
                   "dow": dow, "start": time(9, 0), "end": time(17, 0),
                   "pri": "standard", "now": NOW})

        # Appointment types
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
            db.execute(text("""
                INSERT INTO scheduler_appointment_types (organization_id, config_id, type_key, type_name,
                    default_duration_minutes, is_public, created_at)
                VALUES (:oid, :cid, :key, :name, :dur, TRUE, :now)
            """), {"oid": org_id, "cid": config_id, "key": key, "name": name, "dur": dur, "now": NOW})
            atid = db.execute(text(
                "SELECT id FROM scheduler_appointment_types WHERE config_id = :cid AND type_key = :key"
            ), {"cid": config_id, "key": key}).scalar()
            appt_type_ids[key] = atid

        # Sample appointments
        appointments_data = [
            ("Discovery Call — Michael Thompson", "m.thompson@email.com", "512-555-1001", "discovery_call", "booked", 2, 10, 15),
            ("Pre-Approval Review — Emily Martinez", "e.martinez@email.com", "512-555-1004", "pre_approval_review", "confirmed", 3, 14, 30),
            ("Application Walkthrough — Robert Wilson", "r.wilson@email.com", "512-555-1003", "application_walkthrough", "booked", 4, 9, 45),
            ("Closing Prep — David Anderson", "d.anderson@email.com", "512-555-1005", "closing_prep", "confirmed", 1, 11, 30),
            ("Rate Lock Consultation — Jessica Harris", "j.harris@email.com", "512-555-1010", "rate_lock_consultation", "booked", 5, 15, 20),
            ("Refinance Analysis — Megan Adams", "m.adams@email.com", "512-555-1018", "refinance_analysis", "booked", 6, 10, 30),
            ("Discovery Call — Tyler Scott", "t.scott@email.com", "512-555-1017", "discovery_call", "booked", 7, 13, 15),
            ("Pre-Approval — Stephanie King", "s.king@email.com", "512-555-1016", "pre_approval_review", "confirmed", 2, 16, 30),
            # Past appointments
            ("Discovery Call — Ryan Walker", "r.walker@email.com", "512-555-1013", "discovery_call", "completed", -20, 10, 15),
            ("Application — Nicole Robinson", "n.robinson@email.com", "512-555-1014", "application_walkthrough", "completed", -30, 14, 45),
            ("Pre-Approval — Amanda Jackson", "a.jackson@email.com", "512-555-1008", "pre_approval_review", "completed", -15, 11, 30),
            ("Closing Prep — Brandon Young", "b.young@email.com", "512-555-1015", "closing_prep", "completed", -5, 9, 30),
            ("Discovery Call — Jennifer Davis", "j.davis@email.com", "512-555-1002", "discovery_call", "no_show", -7, 10, 15),
        ]

        for title, email, phone, tkey, status, day_offset, hour, dur in appointments_data:
            sched_start = datetime.combine(TODAY + timedelta(days=day_offset), time(hour, 0), tzinfo=timezone.utc)
            sched_end = sched_start + timedelta(minutes=dur)
            completed_at = sched_end if status == "completed" else None
            db.execute(text("""
                INSERT INTO appointments (organization_id, appointment_type_id, assigned_user_id,
                    title, scheduled_start, scheduled_end, duration_minutes, timezone,
                    meeting_mode, attendee_name, attendee_email, attendee_phone,
                    status, completed_at, created_at, updated_at)
                VALUES (:oid, :atid, :uid, :title, :start, :end, :dur, :tz,
                    :mode, :aname, :aemail, :aphone, :status, :completed, :created, :updated)
            """), {"oid": org_id, "atid": appt_type_ids[tkey], "uid": demo_user_id,
                   "title": title, "start": sched_start, "end": sched_end, "dur": dur,
                   "tz": "America/Chicago", "mode": random.choice(["video", "phone"]),
                   "aname": title.split(" — ")[1] if " — " in title else "Client",
                   "aemail": email, "aphone": phone, "status": status,
                   "completed": completed_at,
                   "created": sched_start - timedelta(days=random.randint(1, 5)), "updated": NOW})

        print(f"  Created {len(appointments_data)} appointments")

        # ── 16. MUM Clients (Post-Close Portfolio) ───────────────────────
        mum_data = [
            ("Ryan Walker", "r.walker@email.com", "512-555-1013", "SP-2026-006", 520000, 6.500, 15),
            ("Nicole Robinson", "n.robinson@email.com", "512-555-1014", "SP-2026-007", 385000, 6.375, 30),
            ("Patricia Nguyen", "p.nguyen@email.com", "512-555-3001", "SP-2025-048", 410000, 5.875, 180),
            ("Marcus Johnson", "m.johnson@email.com", "512-555-3002", "SP-2025-032", 550000, 6.125, 270),
            ("Catherine Park", "c.park@email.com", "512-555-3003", "SP-2025-015", 325000, 5.500, 365),
        ]

        for name, email, phone, ln, amt, rate, days_since in mum_data:
            close_date = TODAY - timedelta(days=days_since)
            db.execute(text("""
                INSERT INTO mum_clients (organization_id, client_name, email, phone, loan_number,
                    original_close_date, closing_date, first_payment_date, days_since_funding,
                    original_rate, current_rate, original_loan_amount, current_loan_amount,
                    engagement_score, status, last_contact, owner_id, created_at, updated_at)
                VALUES (:oid, :name, :email, :phone, :ln,
                    :close, :close, :fpp, :dsf,
                    :rate, :crate, :amt, :camt,
                    :escore, :status, :lc, :owner, :created, :updated)
            """), {"oid": org_id, "name": name, "email": email, "phone": phone, "ln": ln,
                   "close": close_date, "fpp": close_date + timedelta(days=30),
                   "dsf": days_since, "rate": rate, "crate": 6.750,
                   "amt": amt, "camt": int(amt * 0.98),
                   "escore": random.randint(60, 95), "status": "active",
                   "lc": NOW - timedelta(days=random.randint(5, 60)),
                   "owner": demo_user_id, "created": NOW - timedelta(days=days_since), "updated": NOW})

        print(f"  Created {len(mum_data)} MUM clients")

        # ── 17. Stage History ────────────────────────────────────────────
        sh_count = 0
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
            base_date = NOW - timedelta(days=len(seq) * 4)
            for j in range(len(seq) - 1):
                changed = base_date + timedelta(days=(j + 1) * random.randint(2, 5))
                db.execute(text("""
                    INSERT INTO stage_history (organization_id, entity_type, entity_id,
                        from_stage, to_stage, changed_at, changed_by_id, created_at)
                    VALUES (:oid, :etype, :eid, :from, :to, :changed, :by, :changed)
                """), {"oid": org_id, "etype": "loan", "eid": loan_id,
                       "from": seq[j], "to": seq[j + 1], "changed": changed,
                       "by": random.choice(lo_ids)})
                sh_count += 1

        print(f"  Created {sh_count} stage history records")

        # ── Done ─────────────────────────────────────────────────────────
        db.commit()
        print()
        print("=" * 60)
        print("  DEMO ACCOUNT READY")
        print("=" * 60)
        print(f"  Email:    {DEMO_EMAIL}")
        print(f"  Password: {DEMO_PASSWORD}")
        print(f"  Org:      {ORG_NAME} (id={org_id})")
        print(f"  User:     Alex Morgan (id={demo_user_id})")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        if external_session is None:
            sys.exit(1)
        raise
    finally:
        if external_session is None:
            db.close()


_NUKE_SAFE_TABLES = frozenset({
    "morning_briefings", "stage_history", "disclosure_events", "loan_fees",
    "compliance_alerts", "appointments", "availability_slots",
    "scheduler_appointment_types", "scheduler_configs",
    "loan_team_members", "mum_clients",
    "ai_tasks", "tasks", "activities", "documents",
    "email_intakes", "attachment_intakes",
    "loans", "leads", "referral_partners",
    "subscriptions", "api_keys", "branches",
})


def _nuke_demo_org(db, org_id):
    """Delete all data for the demo org (clean slate)."""
    # Order matters for FK constraints
    tables = [
        "morning_briefings", "stage_history", "disclosure_events", "loan_fees",
        "compliance_alerts", "appointments", "availability_slots",
        "scheduler_appointment_types", "scheduler_configs",
        "loan_team_members", "mum_clients",
        "ai_tasks", "tasks", "activities", "documents",
        "email_intakes", "attachment_intakes",
        "loans", "leads", "referral_partners",
        "subscriptions", "api_keys", "branches",
    ]
    for table in tables:
        if table not in _NUKE_SAFE_TABLES:
            raise ValueError(f"Blocked SQL on non-whitelisted table: {table}")
        try:
            db.execute(text("SAVEPOINT nuke_sp"))
            db.execute(text(f"DELETE FROM {table} WHERE organization_id = :oid"), {"oid": org_id})
            db.execute(text("RELEASE SAVEPOINT nuke_sp"))
        except Exception as _exc:  # noqa: BLE001
            db.execute(text("ROLLBACK TO SAVEPOINT nuke_sp"))

    # Users (delete subscriptions first via user_id)
    try:
        db.execute(text("SAVEPOINT nuke_users_sp"))
        user_ids = [r[0] for r in db.execute(text("SELECT id FROM users WHERE organization_id = :oid"), {"oid": org_id}).fetchall()]
        for uid in user_ids:
            db.execute(text("DELETE FROM subscriptions WHERE user_id = :uid"), {"uid": uid})
        db.execute(text("RELEASE SAVEPOINT nuke_users_sp"))
    except Exception as _exc:  # noqa: BLE001
        db.execute(text("ROLLBACK TO SAVEPOINT nuke_users_sp"))

    db.execute(text("DELETE FROM users WHERE organization_id = :oid"), {"oid": org_id})
    db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": org_id})
    print(f"  Cleaned up old demo org (id={org_id})")


if __name__ == "__main__":
    main()
