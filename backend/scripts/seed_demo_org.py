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
    from database.models.communication import Activity
    from database.models.compliance import ComplianceAlert
    from database.models.document import Document
    from database.models.morning_briefing import MorningBriefing
    from database.models.demo_data import DemoDataRecord
    from database.models.scheduler import Appointment as SchedulerAppointment
    from database.enums import ActivityType, DocumentType, DocumentCategory

    counts: Dict[str, int] = {}
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
    except Exception:
        logger.exception("Failed to seed leads")
        savepoint.rollback()
        counts["leads"] = 0

    # ------------------------------------------------------------------
    # 2. LOANS (15)
    # ------------------------------------------------------------------
    loan_ids: List[int] = []
    try:
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

                # Calculate SLA dates based on stage progression
                app_date = _past_date(45)
                sla_dates: Dict[str, Any] = {"application_date": app_date}

                stage_order = [
                    "APPLICATION", "PROCESSING", "SUBMITTED",
                    "UNDERWRITING", "APPROVED", "CTC",
                    "CLEAR_TO_CLOSE", "DOCS_OUT",
                ]
                current_idx = stage_order.index(stage)

                if current_idx >= 1:  # PROCESSING
                    sla_dates["initial_disclosures_sent_date"] = app_date + timedelta(days=2)
                    sla_dates["initial_disclosures_signed_date"] = app_date + timedelta(days=4)
                if current_idx >= 2:  # SUBMITTED
                    sla_dates["uw_received_date"] = app_date + timedelta(days=10)
                if current_idx >= 4:  # APPROVED
                    sla_dates["loan_approved_date"] = app_date + timedelta(days=18)
                if current_idx >= 6:  # CLEAR_TO_CLOSE
                    sla_dates["clear_to_close_date"] = app_date + timedelta(days=22)
                    sla_dates["cd_sent_to_borrower_date"] = app_date + timedelta(days=21)
                if current_idx >= 7:  # DOCS_OUT
                    sla_dates["docs_out_date"] = app_date + timedelta(days=25)

                loan = Loan(
                    organization_id=organization_id,
                    loan_number=f"DEMO-{year}-{loan_seq:04d}",
                    borrower_name=f"{first} {last}",
                    borrower_email=_random_email(first, last),
                    borrower_phone=_random_phone(),
                    amount=amount,
                    rate=rate,
                    loan_type=loan_type,
                    stage=stage,
                    property_address=f"{random.choice(STREETS)}, {city}, {state_code} {zipcode}",
                    property_city=city,
                    property_state=state_code,
                    property_zip=zipcode,
                    loan_officer_id=user_id,
                    loan_purpose=random.choice(LOAN_PURPOSES),
                    property_type=random.choice(PROPERTY_TYPES),
                    stage_changed_at=_past_date(5),
                    closing_date=datetime.now(timezone.utc) + timedelta(days=random.randint(10, 45)),
                    lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=random.randint(15, 60)),
                    created_at=app_date,
                    **sla_dates,
                )
                db.add(loan)
                db.flush()
                loan_ids.append(loan.id)
                _track(db, organization_id, "loan", loan.id)
        savepoint.commit()
        counts["loans"] = len(loan_ids)
        logger.info("Seeded %d demo loans", len(loan_ids))
    except Exception:
        logger.exception("Failed to seed loans")
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
    except Exception:
        logger.exception("Failed to seed activities")
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
    except Exception:
        logger.exception("Failed to seed appointments")
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
    except Exception:
        logger.exception("Failed to seed compliance alerts")
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
    except Exception:
        logger.exception("Failed to seed documents")
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
        briefing = MorningBriefing(
            organization_id=organization_id,
            user_id=user_id,
            briefing_date=date.today(),
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
    except Exception:
        logger.exception("Failed to seed morning briefing")
        savepoint.rollback()
        counts["morning_briefings"] = 0

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
}


def clear_demo_data(db: Session, organization_id: int) -> Dict[str, Any]:
    """
    Remove all demo-seeded data for an organization by looking up
    DemoDataRecord tracking entries.

    Returns a summary dict with counts of deleted entities.
    """
    from database.models.demo_data import DemoDataRecord
    from database.models.lead_loan import Lead, Loan
    from database.models.communication import Activity
    from database.models.compliance import ComplianceAlert
    from database.models.document import Document
    from database.models.morning_briefing import MorningBriefing
    from database.models.scheduler import Appointment as SchedulerAppointment

    model_map = {
        "lead": Lead,
        "loan": Loan,
        "activity": Activity,
        "appointment": SchedulerAppointment,
        "compliance_alert": ComplianceAlert,
        "document": Document,
        "morning_briefing": MorningBriefing,
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
        "morning_briefing", "document", "compliance_alert",
        "appointment", "activity", "loan", "lead",
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
