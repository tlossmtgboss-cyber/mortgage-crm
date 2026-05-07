"""
Demo Data Seeder for Sales Demos

Seeds an organization with realistic mortgage CRM data for demo purposes.
Every created entity is tracked via DemoDataRecord for clean removal.

Usage:
    from scripts.seed_demo_org import seed_demo_data, clear_demo_data

    # Seed
    result = seed_demo_data(db, organization_id=1, user_id=1)

    # Cleanup
    result = clear_demo_data(db, organization_id=1)
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name pools — clearly fictional but realistic-sounding
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Avery", "Jordan", "Morgan", "Taylor", "Casey",
    "Riley", "Quinn", "Harper", "Sage", "Emery",
    "Dakota", "Finley", "Rowan", "Cameron", "Reese",
    "Blake", "Skyler", "Kendall", "Peyton", "Sawyer",
    "Parker", "Ellis", "Wren", "Marley", "Haven",
]

LAST_NAMES = [
    "Demoworth", "Sampleson", "Testfield", "Showcroft", "Trialton",
    "Demosky", "Mockwell", "Previewson", "Sandbox", "Trialhaven",
    "Demova", "Showcrest", "Sampleford", "Testworth", "Mockridge",
    "Preville", "Trialworth", "Demohart", "Samplecrest", "Testbrook",
    "Mockton", "Showcroft", "Demofield", "Sandford", "Trialmere",
]

STREETS = [
    "123 Oak Lane", "456 Maple Drive", "789 Elm Street",
    "321 Pine Avenue", "654 Cedar Court", "987 Birch Boulevard",
    "111 Willow Way", "222 Spruce Circle", "333 Aspen Place",
    "444 Hickory Road", "555 Walnut Terrace", "666 Chestnut Lane",
    "777 Redwood Drive", "888 Sycamore Path", "999 Magnolia Court",
]

CITIES_STATES = [
    ("Austin", "TX", "78701"), ("Denver", "CO", "80202"),
    ("Charlotte", "NC", "28202"), ("Phoenix", "AZ", "85001"),
    ("Nashville", "TN", "37201"), ("Tampa", "FL", "33602"),
    ("Raleigh", "NC", "27601"), ("Dallas", "TX", "75201"),
    ("Orlando", "FL", "32801"), ("Atlanta", "GA", "30301"),
    ("San Antonio", "TX", "78201"), ("Scottsdale", "AZ", "85251"),
    ("Boise", "ID", "83702"), ("Savannah", "GA", "31401"),
    ("Charleston", "SC", "29401"),
]

LEAD_SOURCES = ["website", "referral", "zillow", "realtor.com", "rate_quote"]
LEAD_STAGES = ["New", "Attempted Contact", "Pre-Qualified", "Long-Term Nurture", "Disclosed"]
LOAN_TYPES = ["conventional", "fha", "va"]
PROPERTY_TYPES = ["single_family", "condo", "townhouse"]
LOAN_PURPOSES = ["purchase", "refinance", "cash_out_refinance"]

ACTIVITY_CONTENTS = {
    "Call": [
        "Called borrower to discuss pre-approval timeline. Left voicemail.",
        "Spoke with borrower — confirmed employment details and income docs needed.",
        "Follow-up call re: rate lock decision. Borrower wants to float for now.",
        "Discussed DTI ratio and potential loan programs. Borrower interested in FHA.",
        "Checked in on document collection progress. Missing bank statements.",
        "Called to confirm closing date and final walk-through schedule.",
        "Discussed appraisal results with borrower. Value came in at ask price.",
        "Quick call to answer borrower questions about PMI removal timeline.",
    ],
    "Email": [
        "Sent pre-approval letter and next steps checklist.",
        "Emailed rate comparison worksheet — conventional vs FHA vs VA options.",
        "Followed up on missing W-2 documents. Deadline approaching.",
        "Sent closing disclosure for review — 3-day waiting period starts.",
        "Emailed updated loan estimate after rate lock confirmation.",
        "Sent welcome packet with borrower portal login instructions.",
        "Provided market update and current rate snapshot.",
        "Sent document upload reminder — 2 items still outstanding.",
    ],
    "Meeting": [
        "Initial consultation — reviewed borrower goals, timeline, and budget.",
        "Pre-approval review meeting. Discussed credit improvement strategies.",
        "Application walkthrough — completed 1003 together on screen share.",
        "Closing prep meeting — reviewed CD, wiring instructions, and timeline.",
    ],
    "Note": [
        "Borrower mentioned potential co-signer if DTI is too high.",
        "Realtor confirmed seller willing to extend closing by 5 days if needed.",
        "Processor flagged gap in employment history — need explanation letter.",
        "Underwriter requesting additional asset documentation — 60-day statements.",
        "Title company reported clean title search — no liens or encumbrances.",
        "Appraisal ordered through AMC — scheduled for next Tuesday.",
    ],
    "SMS": [
        "Hi! Just a reminder to upload your bank statements by Friday. Let me know if you need help!",
        "Great news — your rate lock is confirmed at 6.25%! I'll send details via email.",
        "Quick update: appraisal came in at value. We're on track for closing!",
        "Don't forget our call tomorrow at 10am to review your loan options.",
    ],
}

# Loan stages for the pipeline distribution
LOAN_STAGE_DISTRIBUTION = [
    ("APPLICATION", 3),
    ("PROCESSING", 2),
    ("SUBMITTED", 2),
    ("UNDERWRITING", 2),
    ("APPROVED", 2),
    ("CTC", 2),
    ("CLEAR_TO_CLOSE", 1),
    ("DOCS_OUT", 1),
]


def _random_phone() -> str:
    return f"+1555{random.randint(1000000, 9999999)}"


def _random_email(first: str, last: str) -> str:
    return f"{first.lower()}.{last.lower()}@demo-example.com"


def _past_date(max_days_ago: int = 30) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=random.randint(1, max_days_ago))


def _future_date(max_days_ahead: int = 7) -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        days=random.randint(1, max_days_ahead),
        hours=random.choice([9, 10, 11, 13, 14, 15, 16]),
    )


def _track(db: Session, org_id: int, entity_type: str, entity_id: int) -> None:
    """Record a demo entity for cleanup tracking."""
    from database.models.demo_data import DemoDataRecord
    db.add(DemoDataRecord(
        organization_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id,
    ))


# ===========================================================================
# MAIN SEEDER
# ===========================================================================

def seed_demo_data(db: Session, organization_id: int, user_id: int) -> Dict[str, Any]:
    """
    Seed realistic demo data into the given organization.

    Returns a summary dict with counts of created entities.
    """
    from database.models.lead_loan import Lead, Loan
    from database.models.communication import Activity, CalendarEvent
    from database.models.compliance import ComplianceAlert
    from database.models.document import Document
    from database.models.morning_briefing import MorningBriefing
    from database.models.demo_data import DemoDataRecord
    from database.models.scheduler import Appointment as SchedulerAppointment
    from database.models.referral import MUMClient, ReferralPartner
    from database.models.task import Task
    from database.models.doc_notification import DocNotification
    from database.models.sms_conversation import SMSAIConversation, SMSAIConversationMessage
    from database.enums import ActivityType, DocumentType, DocumentCategory

    counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    year = datetime.now().year

    # Ensure the demo_data_records table exists
    from db import engine as _engine
    DemoDataRecord.__table__.create(_engine, checkfirst=True)

    # ------------------------------------------------------------------
    # 1. LEADS (25)
    # ------------------------------------------------------------------
    lead_ids: List[int] = []
    try:
        savepoint = db.begin_nested()
        for i in range(25):
            first = FIRST_NAMES[i]
            last = LAST_NAMES[i]
            stage = LEAD_STAGES[i % len(LEAD_STAGES)]
            source = LEAD_SOURCES[i % len(LEAD_SOURCES)]
            city, state, zipcode = CITIES_STATES[i % len(CITIES_STATES)]

            lead = Lead(
                organization_id=organization_id,
                name=f"{first} {last}",
                first_name=first,
                last_name=last,
                email=_random_email(first, last),
                phone=_random_phone(),
                stage=stage,
                source=source,
                owner_id=user_id,
                ai_score=random.randint(30, 95),
                loan_amount=Decimal(random.randrange(150000, 750000, 25000)),
                credit_score=random.randint(620, 800),
                loan_purpose=random.choice(LOAN_PURPOSES),
                property_type=random.choice(PROPERTY_TYPES),
                city=city,
                state=state,
                zip_code=zipcode,
                address=random.choice(STREETS),
                created_at=_past_date(60),
                last_contact=_past_date(10),
            )
            db.add(lead)
            db.flush()
            lead_ids.append(lead.id)
            _track(db, organization_id, "lead", lead.id)
        savepoint.commit()
        counts["leads"] = len(lead_ids)
        logger.info("Seeded %d demo leads", len(lead_ids))
    except Exception as e:
        logger.exception("Failed to seed leads")
        errors["leads"] = str(e)
        savepoint.rollback()
        counts["leads"] = 0

    # ------------------------------------------------------------------
    # 2. LOANS (15)
    # ------------------------------------------------------------------
    loan_ids: List[int] = []
    try:
        from sqlalchemy import text as _text
        savepoint = db.begin_nested()
        loan_seq = 0
        for stage, count in LOAN_STAGE_DISTRIBUTION:
            for _ in range(count):
                loan_seq += 1
                first = FIRST_NAMES[loan_seq % len(FIRST_NAMES)]
                last = LAST_NAMES[loan_seq % len(LAST_NAMES)]
                city, state_code, zipcode = CITIES_STATES[loan_seq % len(CITIES_STATES)]
                amount = Decimal(random.randrange(200000, 800000, 25000))
                rate = Decimal(str(round(random.uniform(5.5, 7.5), 3)))
                loan_type = random.choice(LOAN_TYPES)
                app_date = _past_date(45)
                loan_num = f"DEMO-{year}-{loan_seq:04d}"

                result = db.execute(_text("""
                    INSERT INTO loans (organization_id, loan_number, borrower_name,
                        borrower_email, borrower_phone, amount, rate, loan_type,
                        stage, property_city, property_state, property_zip,
                        loan_officer_id, created_at)
                    VALUES (:org, :ln, :bn, :be, :bp, :amt, :rate, :lt,
                        :stage, :city, :state, :zip, :lo, :ca)
                    ON CONFLICT (loan_number) DO UPDATE SET stage = :stage
                    RETURNING id
                """), {
                    "org": organization_id, "ln": loan_num,
                    "bn": f"{first} {last}", "be": _random_email(first, last),
                    "bp": _random_phone(), "amt": float(amount), "rate": float(rate),
                    "lt": loan_type, "stage": stage, "city": city,
                    "state": state_code, "zip": zipcode, "lo": user_id,
                    "ca": app_date,
                })
                loan_id = result.fetchone()[0]
                loan_ids.append(loan_id)
                _track(db, organization_id, "loan", loan_id)
        savepoint.commit()
        counts["loans"] = len(loan_ids)
        logger.info("Seeded %d demo loans", len(loan_ids))
    except Exception as e:
        logger.exception("Failed to seed loans")
        errors["loans"] = str(e)
        savepoint.rollback()
        counts["loans"] = 0

    # ------------------------------------------------------------------
    # 3. ACTIVITIES (50)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        activity_count = 0
        activity_type_map = {
            "Call": ActivityType.CALL,
            "Email": ActivityType.EMAIL,
            "Meeting": ActivityType.MEETING,
            "Note": ActivityType.NOTE,
            "SMS": ActivityType.SMS,
        }
        for i in range(50):
            atype_name = random.choice(list(ACTIVITY_CONTENTS.keys()))
            content = random.choice(ACTIVITY_CONTENTS[atype_name])
            target_lead_id = random.choice(lead_ids) if lead_ids else None

            activity = Activity(
                organization_id=organization_id,
                user_id=user_id,
                type=activity_type_map[atype_name],
                content=content,
                lead_id=target_lead_id,
                created_at=_past_date(30),
            )
            db.add(activity)
            db.flush()
            _track(db, organization_id, "activity", activity.id)
            activity_count += 1
        savepoint.commit()
        counts["activities"] = activity_count
        logger.info("Seeded %d demo activities", activity_count)
    except Exception as e:
        logger.exception("Failed to seed activities")
        errors["activities"] = str(e)
        savepoint.rollback()
        counts["activities"] = 0

    # ------------------------------------------------------------------
    # 4. APPOINTMENTS (8)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        appt_count = 0
        meeting_configs = [
            ("Discovery Call — {name}", "discovery_call", 30),
            ("Pre-Approval Review — {name}", "pre_approval_review", 45),
            ("Application Walkthrough — {name}", "application_walkthrough", 60),
            ("Document Review — {name}", "document_review", 30),
            ("Rate Lock Discussion — {name}", "rate_lock_discussion", 30),
            ("Closing Prep — {name}", "closing_prep", 45),
            ("Discovery Call — {name}", "discovery_call", 30),
            ("Pre-Approval Review — {name}", "pre_approval_review", 45),
        ]
        for i in range(8):
            title_tpl, mtype, duration = meeting_configs[i]
            first = FIRST_NAMES[i]
            last = LAST_NAMES[i]
            name = f"{first} {last}"
            start = _future_date(7)
            # Ensure business hours (9am-4pm)
            start = start.replace(hour=random.choice([9, 10, 11, 13, 14, 15, 16]), minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=duration)

            appt = SchedulerAppointment(
                organization_id=organization_id,
                assigned_user_id=user_id,
                created_by_user_id=user_id,
                title=title_tpl.format(name=name),
                description=f"Scheduled {mtype.replace('_', ' ')} with {name}",
                scheduled_start=start,
                scheduled_end=end,
                duration_minutes=duration,
                attendee_name=name,
                attendee_email=_random_email(first, last),
                attendee_phone=_random_phone(),
                status="booked",
                lead_id=lead_ids[i] if i < len(lead_ids) else None,
            )
            db.add(appt)
            db.flush()
            _track(db, organization_id, "appointment", appt.id)
            appt_count += 1
        savepoint.commit()
        counts["appointments"] = appt_count
        logger.info("Seeded %d demo appointments", appt_count)
    except Exception as e:
        logger.exception("Failed to seed appointments")
        errors["appointments"] = str(e)
        savepoint.rollback()
        counts["appointments"] = 0

    # ------------------------------------------------------------------
    # 5. COMPLIANCE ALERTS (5)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        alert_count = 0
        alert_defs = [
            # 2 open
            {
                "alert_type": "trid_le_deadline",
                "severity": "critical",
                "title": "LE Delivery Deadline Approaching",
                "description": "Initial Loan Estimate must be delivered within 3 business days of application.",
                "status": "open",
                "deadline_date": date.today() + timedelta(days=1),
                "days_remaining": 1,
            },
            {
                "alert_type": "tolerance_violation",
                "severity": "medium",
                "title": "Fee Tolerance Warning — Title Insurance",
                "description": "Title insurance fee increased 8% from LE to CD. Approaching 10% aggregate threshold.",
                "status": "open",
                "deadline_date": date.today() + timedelta(days=5),
                "days_remaining": 5,
            },
            # 3 resolved
            {
                "alert_type": "adverse_action_deadline",
                "severity": "high",
                "title": "Adverse Action Notice Deadline",
                "description": "ECOA requires adverse action notice within 30 days of denial.",
                "status": "resolved",
                "resolved_at": _past_date(5),
                "resolution_notes": "Notice sent via certified mail on time.",
            },
            {
                "alert_type": "trid_le_deadline",
                "severity": "critical",
                "title": "LE Delivery Deadline — Resolved",
                "description": "Initial LE delivered within deadline window.",
                "status": "resolved",
                "resolved_at": _past_date(10),
                "resolution_notes": "LE sent day 2 of 3-day window.",
            },
            {
                "alert_type": "tolerance_violation",
                "severity": "medium",
                "title": "Origination Fee Tolerance Resolved",
                "description": "Origination fee corrected. Lender credit applied.",
                "status": "resolved",
                "resolved_at": _past_date(15),
                "resolution_notes": "Cure amount of $125 credited at closing.",
            },
        ]

        from sqlalchemy import text as _text
        table_exists = db.execute(_text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'compliance_alerts')"
        )).scalar()
        if not table_exists:
            raise RuntimeError("compliance_alerts table does not exist — skipping")
        for i, adef in enumerate(alert_defs):
            target_loan_id = loan_ids[i] if i < len(loan_ids) else (loan_ids[0] if loan_ids else None)
            alert = ComplianceAlert(
                organization_id=organization_id,
                loan_id=target_loan_id,
                **adef,
            )
            db.add(alert)
            db.flush()
            _track(db, organization_id, "compliance_alert", alert.id)
            alert_count += 1
        savepoint.commit()
        counts["compliance_alerts"] = alert_count
        logger.info("Seeded %d demo compliance alerts", alert_count)
    except Exception as e:
        logger.exception("Failed to seed compliance alerts")
        errors["compliance_alerts"] = str(e)
        savepoint.rollback()
        counts["compliance_alerts"] = 0

    # ------------------------------------------------------------------
    # 6. DOCUMENTS (3 per active loan)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        doc_count = 0
        doc_templates = [
            (DocumentType.PAYSTUB, DocumentCategory.INCOME, "paystubs_jan2026.pdf"),
            (DocumentType.W2, DocumentCategory.INCOME, "w2_2025.pdf"),
            (DocumentType.BANK_STATEMENT, DocumentCategory.ASSETS, "bank_stmt_q1_2026.pdf"),
            (DocumentType.CREDIT_REPORT, DocumentCategory.CREDIT, "credit_report.pdf"),
            (DocumentType.APPRAISAL, DocumentCategory.PROPERTY, "appraisal_report.pdf"),
        ]
        for loan_id in loan_ids:
            selected_docs = random.sample(doc_templates, 3)
            for dtype, dcat, fname in selected_docs:
                doc = Document(
                    organization_id=organization_id,
                    loan_id=loan_id,
                    doc_type=dtype,
                    doc_category=dcat,
                    filename=fname,
                    original_filename=fname,
                    file_location=f"demo://documents/{loan_id}/{fname}",
                    source="MANUAL_UPLOAD",
                    status="active",
                    uploaded_at=_past_date(20),
                    uploaded_by_user_id=user_id,
                )
                db.add(doc)
                db.flush()
                _track(db, organization_id, "document", doc.id)
                doc_count += 1
        savepoint.commit()
        counts["documents"] = doc_count
        logger.info("Seeded %d demo documents", doc_count)
    except Exception as e:
        logger.exception("Failed to seed documents")
        errors["documents"] = str(e)
        savepoint.rollback()
        counts["documents"] = 0

    # ------------------------------------------------------------------
    # 7. MORNING BRIEFING (1 for today)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        briefing_data = {
            "pipeline_snapshot": {
                "active_loans": len(loan_ids),
                "total_volume": 4_250_000,
                "closing_this_week": 2,
                "avg_days_in_stage": 4.2,
            },
            "urgent_items": [
                {"type": "lock_expiring", "loan": "DEMO-2026-0012", "days_remaining": 2},
                {"type": "condition_due", "loan": "DEMO-2026-0005", "description": "Bank statements needed"},
            ],
            "todays_appointments": [
                {"time": "10:00 AM", "type": "Discovery Call", "contact": "Avery Demoworth"},
                {"time": "2:00 PM", "type": "Pre-Approval Review", "contact": "Jordan Sampleson"},
            ],
            "compliance_alerts": {
                "open": 2,
                "critical": 1,
            },
            "lead_activity": {
                "new_leads_24h": 3,
                "follow_ups_due": 5,
                "hot_leads": 2,
            },
        }
        from sqlalchemy import text as _text
        existing = db.execute(_text(
            "SELECT id FROM morning_briefings WHERE user_id = :uid AND briefing_date = :d"
        ), {"uid": user_id, "d": date.today()}).fetchone()
        if existing:
            savepoint.commit()
            counts["morning_briefings"] = 1
            logger.info("Morning briefing already exists for today — reusing")
        briefing = MorningBriefing(
            organization_id=organization_id,
            user_id=user_id,
            briefing_date=date.today() + timedelta(days=1) if existing else date.today(),
            briefing_level="individual",
            status="delivered",
            briefing_data=briefing_data,
            ai_narrative=(
                "Good morning! You have 15 active loans in your pipeline totaling $4.25M. "
                "Two loans are approaching closing this week. A rate lock on DEMO-2026-0012 "
                "expires in 2 days — consider discussing extension options with the borrower. "
                "You have 2 appointments today and 5 follow-up calls due. "
                "There is 1 critical compliance alert requiring immediate attention: "
                "an LE delivery deadline on a recent application."
            ),
            created_at=datetime.now(timezone.utc),
        )
        db.add(briefing)
        db.flush()
        _track(db, organization_id, "morning_briefing", briefing.id)
        savepoint.commit()
        counts["morning_briefings"] = 1
        logger.info("Seeded 1 demo morning briefing")
    except Exception as e:
        logger.exception("Failed to seed morning briefing")
        errors["morning_briefings"] = str(e)
        savepoint.rollback()
        counts["morning_briefings"] = 0

    # ------------------------------------------------------------------
    # 8. MUM CLIENTS (15)
    # ------------------------------------------------------------------
    mum_ids: List[int] = []
    try:
        savepoint = db.begin_nested()
        for i in range(15):
            first = FIRST_NAMES[i]
            last = LAST_NAMES[i]
            city, state_code, zipcode = CITIES_STATES[i % len(CITIES_STATES)]
            orig_amount = Decimal(random.randrange(200000, 700000, 25000))
            rate = Decimal(str(round(random.uniform(3.5, 6.5), 3)))
            appraisal = orig_amount + Decimal(random.randrange(10000, 60000, 5000))
            current_value = appraisal + Decimal(random.randrange(-10000, 40000, 5000))
            months_since = random.randint(6, 48)
            principal_paid = orig_amount * Decimal("0.01") * months_since
            current_balance = orig_amount - principal_paid
            close_dt = datetime.now(timezone.utc) - timedelta(days=months_since * 30)
            first_pmt = close_dt + timedelta(days=45)

            mum = MUMClient(
                organization_id=organization_id,
                user_id=user_id,
                client_name=f"{first} {last}",
                email=_random_email(first, last),
                phone=_random_phone(),
                loan_number=f"SP-{year}-MUM-{i+1:03d}",
                closing_date=close_dt,
                first_payment_date=first_pmt,
                interest_rate=rate,
                original_loan_amount=orig_amount,
                current_loan_amount=current_balance,
                appraisal_value_at_closing=appraisal,
                current_property_value=current_value,
                original_rate=rate,
                current_rate=rate,
                loan_balance=current_balance,
                term=360,
                status="active",
                property_state=state_code,
                property_zip=zipcode,
                engagement_score=random.randint(20, 95),
                refinance_opportunity=rate > Decimal("5.5"),
                last_contact=_past_date(30),
                created_at=close_dt,
            )
            db.add(mum)
            db.flush()
            mum_ids.append(mum.id)
            _track(db, organization_id, "mum_client", mum.id)
        savepoint.commit()
        counts["mum_clients"] = len(mum_ids)
        logger.info("Seeded %d demo MUM clients", len(mum_ids))
    except Exception as e:
        logger.exception("Failed to seed MUM clients")
        errors["mum_clients"] = str(e)
        savepoint.rollback()
        counts["mum_clients"] = 0

    # ------------------------------------------------------------------
    # 9. TASKS (30)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        task_count = 0
        task_defs = [
            ("Call back Sarah re: pre-approval docs", "high", "pending", 2),
            ("Review appraisal report — 123 Oak Lane", "high", "pending", 1),
            ("Submit conditions to underwriter", "high", "in_progress", 0),
            ("Send rate lock confirmation to borrower", "medium", "pending", 3),
            ("Follow up on title search delay", "medium", "pending", 2),
            ("Update CRM notes from morning calls", "low", "completed", -1),
            ("Order flood cert — Elm Street property", "medium", "pending", 4),
            ("Prepare closing disclosure for review", "high", "in_progress", 1),
            ("Check credit supplement results", "medium", "pending", 2),
            ("Send welcome email to new lead", "low", "pending", 1),
            ("Schedule discovery call — Quinn Sandford", "medium", "pending", 3),
            ("Upload VOE letter to loan file", "high", "pending", 0),
            ("Review DTI calculations before submission", "high", "in_progress", 1),
            ("Confirm wire instructions with title company", "high", "pending", 2),
            ("Set up borrower portal access", "low", "completed", -2),
            ("Run AUS — check DU findings", "high", "pending", 1),
            ("Request updated bank statements (60-day)", "medium", "pending", 3),
            ("Review HOI declaration page", "medium", "pending", 2),
            ("Follow up with realtor on contract extension", "medium", "pending", 4),
            ("Send pre-qual letter to agent", "low", "pending", 1),
            ("Verify income docs for self-employed borrower", "high", "in_progress", 0),
            ("Schedule final walk-through", "medium", "pending", 5),
            ("Confirm closing date with all parties", "high", "pending", 2),
            ("Prepare loan comparison worksheet", "medium", "completed", -3),
            ("Call borrower re: rate float-down option", "medium", "pending", 1),
            ("Review compliance checklist pre-submission", "high", "pending", 0),
            ("Send birthday card to past client", "low", "pending", 7),
            ("Check lock expiration — DEMO-2026-0012", "high", "pending", 1),
            ("Submit extension request for rate lock", "high", "in_progress", 0),
            ("Update pipeline report for team meeting", "medium", "pending", 2),
        ]
        for i, (title, priority, status, due_offset) in enumerate(task_defs):
            target_lead_id = lead_ids[i % len(lead_ids)] if lead_ids else None
            target_loan_id = loan_ids[i % len(loan_ids)] if loan_ids and i < 20 else None
            due = datetime.now(timezone.utc) + timedelta(days=due_offset) if due_offset >= 0 else None
            completed_at = _past_date(abs(due_offset)) if status == "completed" else None

            task = Task(
                organization_id=organization_id,
                title=title,
                priority=priority,
                status=status,
                owner_id=user_id,
                lead_id=target_lead_id,
                loan_id=target_loan_id,
                due_date=due,
                completed_at=completed_at,
                created_at=_past_date(7),
            )
            db.add(task)
            db.flush()
            _track(db, organization_id, "task", task.id)
            task_count += 1
        savepoint.commit()
        counts["tasks"] = task_count
        logger.info("Seeded %d demo tasks", task_count)
    except Exception as e:
        logger.exception("Failed to seed tasks")
        errors["tasks"] = str(e)
        savepoint.rollback()
        counts["tasks"] = 0

    # ------------------------------------------------------------------
    # 10. CALENDAR EVENTS (12)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        cal_count = 0
        cal_events = [
            ("Discovery Call — Avery Demoworth", "call", 30, 1),
            ("Pre-Approval Review — Jordan Sampleson", "meeting", 45, 1),
            ("Application Walkthrough — Morgan Testfield", "meeting", 60, 2),
            ("Rate Lock Discussion — Taylor Showcroft", "call", 30, 2),
            ("Document Review — Casey Trialton", "meeting", 30, 3),
            ("Closing Prep — Riley Demosky", "meeting", 45, 3),
            ("Team Pipeline Review", "meeting", 60, 4),
            ("Appraisal Follow-Up — Quinn Sandbox", "call", 15, 4),
            ("Borrower Check-In — Harper Trialhaven", "call", 20, 5),
            ("CD Review — Sage Demova", "meeting", 30, 5),
            ("Weekly Office Meeting", "meeting", 60, 7),
            ("Training: New Compliance Updates", "meeting", 90, 7),
        ]
        for i, (title, etype, duration, day_offset) in enumerate(cal_events):
            hour = random.choice([9, 10, 11, 13, 14, 15, 16])
            start = (datetime.now(timezone.utc) + timedelta(days=day_offset)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(minutes=duration)

            from sqlalchemy import text as _text
            result = db.execute(_text("""
                INSERT INTO calendar_events (user_id, title, description, start_time,
                    end_time, event_type, status, lead_id, loan_id)
                VALUES (:uid, :title, :desc, :st, :et, :etype, :status, :lid, :loid)
                RETURNING id
            """), {
                "uid": user_id, "title": title,
                "desc": f"Scheduled {etype} — {duration} min",
                "st": start, "et": end, "etype": etype, "status": "scheduled",
                "lid": lead_ids[i % len(lead_ids)] if lead_ids and i < 10 else None,
                "loid": loan_ids[i % len(loan_ids)] if loan_ids and i < 6 else None,
            })
            event_id = result.fetchone()[0]
            _track(db, organization_id, "calendar_event", event_id)
            cal_count += 1
        savepoint.commit()
        counts["calendar_events"] = cal_count
        logger.info("Seeded %d demo calendar events", cal_count)
    except Exception as e:
        logger.exception("Failed to seed calendar events")
        errors["calendar_events"] = str(e)
        savepoint.rollback()
        counts["calendar_events"] = 0

    # ------------------------------------------------------------------
    # 11. NOTIFICATIONS (10)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        notif_count = 0
        notif_defs = [
            ("DOC_UPLOADED", "New Document Uploaded", "urgent", "Paystubs uploaded by borrower — review needed.", True),
            ("CONDITION_ADDED", "New Underwriting Condition", "critical", "Underwriter added condition: 60-day bank statements required.", True),
            ("SLA_WARNING", "SLA Deadline Approaching", "warning", "Loan DEMO-2026-0003 approaching 48-hour disclosure deadline.", True),
            ("DOC_APPROVED", "Document Approved", "info", "W-2 for Jordan Sampleson has been approved.", False),
            ("FRAUD_ALERT", "Potential Fraud Flag", "critical", "Income document flagged — inconsistent employer name detected.", True),
            ("DOC_EXPIRING", "Document Expiring Soon", "warning", "Credit report for Morgan Testfield expires in 5 days.", True),
            ("CONDITION_CLEARED", "Condition Cleared", "info", "Appraisal condition cleared for DEMO-2026-0007.", False),
            ("DOC_CLASSIFIED", "Auto-Classification Complete", "info", "3 uploaded documents automatically classified.", False),
            ("SIGNATURE_COMPLETED", "E-Signature Completed", "info", "Initial disclosures signed by Taylor Showcroft.", False),
            ("PACKAGE_READY", "Loan Package Ready", "info", "Submission package for DEMO-2026-0010 is complete.", False),
        ]
        from sqlalchemy import text as _text
        table_exists = db.execute(_text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'smart_docs_notifications')"
        )).scalar()
        if not table_exists:
            raise RuntimeError("smart_docs_notifications table does not exist — skipping")
        for i, (ntype, title, severity, body, unread) in enumerate(notif_defs):
            target_loan_id = loan_ids[i % len(loan_ids)] if loan_ids else None
            notif = DocNotification(
                organization_id=organization_id,
                user_id=user_id,
                loan_id=target_loan_id,
                notification_type=ntype,
                title=title,
                severity=severity,
                body=body,
                is_read=not unread,
                read_at=_past_date(2) if not unread else None,
                delivery_channels=["in_app"],
                created_at=_past_date(5),
            )
            db.add(notif)
            db.flush()
            _track(db, organization_id, "notification", notif.id)
            notif_count += 1
        savepoint.commit()
        counts["notifications"] = notif_count
        logger.info("Seeded %d demo notifications", notif_count)
    except Exception as e:
        logger.exception("Failed to seed notifications")
        errors["notifications"] = str(e)
        savepoint.rollback()
        counts["notifications"] = 0

    # ------------------------------------------------------------------
    # 12. SMS CONVERSATIONS (5)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        sms_count = 0
        sms_convos = [
            ("+15551001001", "active", "qualifying", [
                ("inbound", "Hi, I saw your ad about rates. What are current rates for a 30-year fixed?"),
                ("outbound", "Hi! Thanks for reaching out. Current 30-year fixed rates are around 6.25-6.5% depending on credit and down payment. Would you like to discuss your specific situation?"),
                ("inbound", "Yes, I have a 740 credit score and looking to put 20% down on a $400K home"),
                ("outbound", "Great credit score! With 20% down on $400K, you'd qualify for excellent rates. Let me run some numbers — can we schedule a quick 15-min call this week?"),
            ]),
            ("+15551001002", "active", "scheduling", [
                ("inbound", "I got your voicemail. Can we talk tomorrow?"),
                ("outbound", "Absolutely! I have openings at 10am and 2pm tomorrow. Which works better for you?"),
                ("inbound", "2pm works great"),
                ("outbound", "Perfect, I've got you down for 2pm tomorrow. I'll send a calendar invite shortly. Talk then!"),
            ]),
            ("+15551001003", "active", "nurture", [
                ("inbound", "Just checking — any changes in rates this week?"),
                ("outbound", "Rates ticked down slightly — 30yr fixed around 6.375% today. Still a good time if you're ready to lock. Want me to send an updated comparison?"),
                ("inbound", "Sure, send it over"),
                ("outbound", "Done! Just emailed you an updated rate sheet with conventional, FHA, and VA options. Let me know if any questions come up."),
            ]),
            ("+15551001004", "closed", "greeting", [
                ("outbound", "Hi! This is Demo from Summit Peak Mortgage. I wanted to follow up on your rate quote request. Do you have a few minutes?"),
                ("inbound", "Sorry, not interested right now"),
                ("outbound", "No problem at all! If your situation changes, feel free to reach out anytime. Have a great day!"),
            ]),
            ("+15551001005", "active", "qualifying", [
                ("inbound", "My lease ends in 3 months and I want to buy. Where do I start?"),
                ("outbound", "Great timing! First step is getting pre-approved so you know your budget. I'll need about 15 min to review your finances. Can you share your approximate income and any monthly debts?"),
                ("inbound", "Income is about 85K, car payment $350/mo, student loans $200/mo"),
                ("outbound", "That's a solid start! Based on those numbers, you'd likely qualify in the $280-320K range. Let's set up a pre-approval call — I'll need W-2s and bank statements. Want to do a quick Zoom this week?"),
            ]),
        ]
        from sqlalchemy import text as _text
        for i, (phone, status, stage, messages) in enumerate(sms_convos):
            target_lead_id = lead_ids[i % len(lead_ids)] if lead_ids else None
            result = db.execute(_text("""
                INSERT INTO sms_ai_conversations (id, phone_number, organization_id,
                    lead_id, status, current_stage, message_count, last_message_at, created_at)
                VALUES (:id, :phone, :org, :lid, :status, :stage, :mc, :lm, :ca)
                RETURNING id
            """), {
                "id": str(random.randint(100000, 999999)),
                "phone": phone, "org": organization_id, "lid": target_lead_id,
                "status": status, "stage": stage, "mc": len(messages),
                "lm": _past_date(3), "ca": _past_date(10),
            })
            convo_id = result.fetchone()[0]
            _track(db, organization_id, "sms_conversation", convo_id)

            for j, (direction, content) in enumerate(messages):
                db.execute(_text("""
                    INSERT INTO sms_ai_conversation_messages (id, conversation_id,
                        direction, content, ai_generated, created_at)
                    VALUES (:id, :cid, :dir, :content, :ai, :ca)
                """), {
                    "id": str(random.randint(100000, 999999)),
                    "cid": convo_id, "dir": direction, "content": content,
                    "ai": direction == "outbound", "ca": _past_date(10 - j),
                })

            sms_count += 1
        db.flush()
        savepoint.commit()
        counts["sms_conversations"] = sms_count
        logger.info("Seeded %d demo SMS conversations", sms_count)
    except Exception as e:
        logger.exception("Failed to seed SMS conversations")
        errors["sms_conversations"] = str(e)
        savepoint.rollback()
        counts["sms_conversations"] = 0

    # ------------------------------------------------------------------
    # 13. REFERRAL PARTNERS (8)
    # ------------------------------------------------------------------
    try:
        savepoint = db.begin_nested()
        partner_count = 0
        partner_defs = [
            ("Sarah Mitchell Realty", "Sarah Mitchell", "realtor", "broker", 12, 8, 5, Decimal("1250000")),
            ("James Rivera — Keller Williams", "James Rivera", "realtor", "agent", 8, 5, 3, Decimal("750000")),
            ("Chen & Associates CPA", "Michael Chen", "financial_advisor", "individual", 4, 2, 2, Decimal("500000")),
            ("Peak Insurance Group", "Lisa Thompson", "insurance", "team", 6, 3, 2, Decimal("600000")),
            ("David Park — RE/MAX", "David Park", "realtor", "agent", 10, 7, 4, Decimal("980000")),
            ("Martinez Law — Real Estate", "Ana Martinez", "attorney", "individual", 3, 1, 1, Decimal("350000")),
            ("NextGen Builders Inc.", "Tom Wheeler", "builder", "team", 5, 4, 3, Decimal("1100000")),
            ("Coastal Title Services", "Jennifer Lee", "title_company", "individual", 7, 6, 4, Decimal("920000")),
        ]
        for i, (biz_name, contact, category, pcat, refs_in, refs_out, closed, vol) in enumerate(partner_defs):
            city, state_code, zipcode = CITIES_STATES[i % len(CITIES_STATES)]
            partner = ReferralPartner(
                organization_id=organization_id,
                owner_id=user_id,
                name=biz_name,
                business_name=biz_name,
                contact_name=contact,
                category=category,
                partner_category=pcat,
                phone=_random_phone(),
                email=f"{contact.split()[0].lower()}@demo-partner.com",
                referrals_in=refs_in,
                referrals_out=refs_out,
                closed_loans=closed,
                volume=vol,
                reciprocity_score=round(refs_out / max(refs_in, 1) * 100, 1),
                status="active",
                loyalty_tier="gold" if closed >= 4 else ("silver" if closed >= 2 else "bronze"),
                city=city,
                state=state_code,
                zip_code=zipcode,
                last_interaction=_past_date(14),
                created_at=_past_date(90),
            )
            db.add(partner)
            db.flush()
            _track(db, organization_id, "referral_partner", partner.id)
            partner_count += 1
        savepoint.commit()
        counts["referral_partners"] = partner_count
        logger.info("Seeded %d demo referral partners", partner_count)
    except Exception as e:
        logger.exception("Failed to seed referral partners")
        errors["referral_partners"] = str(e)
        savepoint.rollback()
        counts["referral_partners"] = 0

    # ------------------------------------------------------------------
    # Commit everything
    # ------------------------------------------------------------------
    db.commit()

    total = sum(counts.values())
    logger.info("Demo data seeding complete: %d total entities for org %d", total, organization_id)
    return {
        "organization_id": organization_id,
        "seeded_by_user_id": user_id,
        "counts": counts,
        "errors": errors,
        "total": total,
    }


# ===========================================================================
# CLEANUP
# ===========================================================================

# Map entity_type -> (model_class_import_path, table)
_ENTITY_MODEL_MAP = {
    "lead": ("database.models.lead_loan", "Lead"),
    "loan": ("database.models.lead_loan", "Loan"),
    "activity": ("database.models.communication", "Activity"),
    "appointment": ("database.models.scheduler", "Appointment"),
    "compliance_alert": ("database.models.compliance", "ComplianceAlert"),
    "document": ("database.models.document", "Document"),
    "morning_briefing": ("database.models.morning_briefing", "MorningBriefing"),
    "mum_client": ("database.models.referral", "MUMClient"),
    "task": ("database.models.task", "Task"),
    "calendar_event": ("database.models.communication", "CalendarEvent"),
    "notification": ("database.models.doc_notification", "DocNotification"),
    "sms_conversation": ("database.models.sms_conversation", "SMSAIConversation"),
    "referral_partner": ("database.models.referral", "ReferralPartner"),
}


def clear_demo_data(db: Session, organization_id: int) -> Dict[str, Any]:
    """
    Remove all demo-seeded data for an organization by looking up
    DemoDataRecord tracking entries.

    Returns a summary dict with counts of deleted entities.
    """
    from database.models.demo_data import DemoDataRecord
    from database.models.lead_loan import Lead, Loan
    from database.models.communication import Activity, CalendarEvent
    from database.models.compliance import ComplianceAlert
    from database.models.document import Document
    from database.models.morning_briefing import MorningBriefing
    from database.models.scheduler import Appointment as SchedulerAppointment
    from database.models.referral import MUMClient, ReferralPartner
    from database.models.task import Task
    from database.models.doc_notification import DocNotification
    from database.models.sms_conversation import SMSAIConversation

    model_map = {
        "lead": Lead,
        "loan": Loan,
        "activity": Activity,
        "appointment": SchedulerAppointment,
        "compliance_alert": ComplianceAlert,
        "document": Document,
        "morning_briefing": MorningBriefing,
        "mum_client": MUMClient,
        "task": Task,
        "calendar_event": CalendarEvent,
        "notification": DocNotification,
        "sms_conversation": SMSAIConversation,
        "referral_partner": ReferralPartner,
    }

    # Get all tracking records for this org
    records = (
        db.query(DemoDataRecord)
        .filter(DemoDataRecord.organization_id == organization_id)
        .all()
    )

    if not records:
        return {
            "organization_id": organization_id,
            "counts": {},
            "total": 0,
            "message": "No demo data found for this organization",
        }

    # Group by entity type
    by_type: Dict[str, list] = {}
    for rec in records:
        by_type.setdefault(rec.entity_type, []).append(rec.entity_id)

    counts: Dict[str, int] = {}

    # Delete in dependency order: documents/activities first, then loans/leads last
    delete_order = [
        "notification", "sms_conversation", "calendar_event",
        "morning_briefing", "document", "compliance_alert",
        "task", "appointment", "activity", "referral_partner",
        "mum_client", "loan", "lead",
    ]

    for entity_type in delete_order:
        entity_ids = by_type.get(entity_type, [])
        if not entity_ids:
            continue

        model_cls = model_map.get(entity_type)
        if model_cls is None:
            logger.warning("Unknown entity type in demo data: %s", entity_type)
            continue

        try:
            deleted = (
                db.query(model_cls)
                .filter(model_cls.id.in_(entity_ids))
                .delete(synchronize_session="fetch")
            )
            counts[entity_type] = deleted
            logger.info("Deleted %d demo %s records", deleted, entity_type)
        except Exception:
            logger.exception("Failed to delete demo %s records", entity_type)
            db.rollback()
            counts[entity_type] = 0

    # Remove all tracking records
    tracking_deleted = (
        db.query(DemoDataRecord)
        .filter(DemoDataRecord.organization_id == organization_id)
        .delete(synchronize_session="fetch")
    )

    db.commit()

    total = sum(counts.values())
    logger.info(
        "Demo data cleanup complete: %d entities + %d tracking records deleted for org %d",
        total, tracking_deleted, organization_id,
    )
    return {
        "organization_id": organization_id,
        "counts": counts,
        "total": total,
        "tracking_records_removed": tracking_deleted,
    }
