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


