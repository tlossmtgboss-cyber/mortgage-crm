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


