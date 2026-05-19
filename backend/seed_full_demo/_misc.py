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


