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


