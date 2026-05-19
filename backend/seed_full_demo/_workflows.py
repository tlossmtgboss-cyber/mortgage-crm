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


def seed_rate_monitor(conn, org_id, mum_ids, loan_ids):
    """Create rate market data, rate locks, and refi opportunities."""

    # ------------------------------------------------------------------
    # 1. RateMarketData — 30 days of snapshots
    # ------------------------------------------------------------------
    rmd_inserted = 0
    rmd_skipped = 0

    BASE_30YR   = Decimal("6.750")
    BASE_15YR   = Decimal("6.125")
    BASE_ARM51  = Decimal("6.000")
    BASE_FHA30  = Decimal("6.375")
    BASE_VA30   = Decimal("6.250")
    BASE_T10    = Decimal("4.250")
    SPREAD      = Decimal("2.500")

    # Slight downward trend over 30 days (up to -0.125 total)
    TREND_DOWN  = Decimal("0.125")

    for day_idx in range(30):
        snap_date = date_ago(30 - day_idx)
        trend_frac = Decimal(str(day_idx / 29.0))

        # Daily variance ±0.0625
        def jitter():
            return Decimal(str(round(random.uniform(-0.0625, 0.0625), 3)))

        r30  = BASE_30YR  - (trend_frac * TREND_DOWN) + jitter()
        r15  = BASE_15YR  - (trend_frac * TREND_DOWN) + jitter()
        r51  = BASE_ARM51 - (trend_frac * TREND_DOWN) + jitter()
        rfha = BASE_FHA30 - (trend_frac * TREND_DOWN) + jitter()
        rva  = BASE_VA30  - (trend_frac * TREND_DOWN) + jitter()
        t10  = BASE_T10   - (trend_frac * Decimal("0.050")) + jitter()
        spread = (r30 - t10).quantize(Decimal("0.001"))

        # Clamp to sane ranges (3 decimal places)
        def clamp(val, lo, hi):
            return max(Decimal(str(lo)), min(Decimal(str(hi)), val)).quantize(Decimal("0.001"))

        r30  = clamp(r30,  5.500, 8.000)
        r15  = clamp(r15,  5.000, 7.500)
        r51  = clamp(r51,  4.750, 7.500)
        rfha = clamp(rfha, 5.250, 7.750)
        rva  = clamp(rva,  5.125, 7.625)
        t10  = clamp(t10,  3.500, 5.500)
        spread = clamp(spread, 1.500, 3.500)

        # 7-day and 30-day trend labels
        if day_idx < 7:
            trend_7day = "stable"
        elif day_idx < 15:
            trend_7day = "declining"
        else:
            trend_7day = "declining"

        trend_30day = "declining"
        volatility_score = round(random.uniform(0.15, 0.45), 2)
        change_30yr = clamp(r30 - BASE_30YR, -0.500, 0.500)

        existing = conn.execute(
            text("""
                SELECT id FROM rate_market_data
                WHERE organization_id = :org_id AND snapshot_date = :snap_date
                LIMIT 1
            """),
            {"org_id": org_id, "snap_date": snap_date},
        ).fetchone()
        if existing:
            rmd_skipped += 1
            continue

        conn.execute(
            text("""
                INSERT INTO rate_market_data
                    (organization_id, snapshot_date, source,
                     rate_30yr_fixed, rate_15yr_fixed, rate_arm_5_1,
                     rate_fha_30yr, rate_va_30yr,
                     treasury_10yr, spread_to_treasury,
                     trend_7day, trend_30day, volatility_score,
                     change_30yr, created_at)
                VALUES
                    (:org_id, :snap_date, 'fred',
                     :r30, :r15, :r51,
                     :rfha, :rva,
                     :t10, :spread,
                     :trend_7day, :trend_30day, :volatility_score,
                     :change_30yr, :now)
            """),
            {
                "org_id": org_id,
                "snap_date": snap_date,
                "r30": r30,
                "r15": r15,
                "r51": r51,
                "rfha": rfha,
                "rva": rva,
                "t10": t10,
                "spread": spread,
                "trend_7day": trend_7day,
                "trend_30day": trend_30day,
                "volatility_score": volatility_score,
                "change_30yr": change_30yr,
                "now": NOW,
            },
        )
        rmd_inserted += 1

    conn.commit()
    print(f"✅ Seeded {rmd_inserted} rate market data rows ({rmd_skipped} existed)")

    # ------------------------------------------------------------------
    # 2. RateLock — 5 rate locks on active loans
    # ------------------------------------------------------------------
    # Loans: SHL-2026-0003 (PROCESSING), SHL-2026-0005 (SUBMITTED),
    #        SHL-2026-0006 (UNDERWRITING), SHL-2026-0008 (CONDITIONAL_APPROVAL),
    #        SHL-2026-0009 (CLEAR_TO_CLOSE)
    RATE_LOCKS = [
        {
            "loan_number": "SHL-2026-0003",
            "lead_email": "vanessa.hartley@gmail.com",
            "status": "locked",
            "lock_type": "standard",
            "lock_period_days": 45,
            "rate_locked": Decimal("6.750"),
            "lock_days_ago": 50,
            "ai_recommendation": "lock",
            "ai_lock_score": 82,
            "ai_reasoning": "Rate trending upward — locking in 6.750% protects borrower from potential 25bp increase. 45-day window aligns with closing timeline.",
            "market_rate_at_lock": Decimal("6.750"),
        },
        {
            "loan_number": "SHL-2026-0005",
            "lead_email": "marcus.delacroix@icloud.com",
            "status": "locked",
            "lock_type": "standard",
            "lock_period_days": 45,
            "rate_locked": Decimal("6.999"),
            "lock_days_ago": 65,
            "ai_recommendation": "strong_lock",
            "ai_lock_score": 91,
            "ai_reasoning": "Market volatility elevated. Borrower credit profile strong. Locking at 6.999% ahead of expected Fed commentary reduces risk.",
            "market_rate_at_lock": Decimal("7.000"),
        },
        {
            "loan_number": "SHL-2026-0006",
            "lead_email": "kevin.albright@gmail.com",
            "status": "expired",
            "lock_type": "standard",
            "lock_period_days": 30,
            "rate_locked": Decimal("7.000"),
            "lock_days_ago": 45,
            "ai_recommendation": "lock",
            "ai_lock_score": 75,
            "ai_reasoning": "Short lock to match UW timeline. Monitor for extension if UW takes longer than 21 days.",
            "market_rate_at_lock": Decimal("7.000"),
        },
        {
            "loan_number": "SHL-2026-0008",
            "lead_email": "brianna.okafor@gmail.com",
            "status": "monitoring",
            "lock_type": "float_down",
            "lock_period_days": 21,
            "rate_locked": Decimal("6.750"),
            "lock_days_ago": 15,
            "ai_recommendation": "hold",
            "ai_lock_score": 68,
            "ai_reasoning": "Rate declining slightly. Float-down option purchased — monitor for 25bp improvement before CTC to exercise float-down.",
            "market_rate_at_lock": Decimal("6.750"),
        },
        {
            "loan_number": "SHL-2026-0009",
            "lead_email": "elijah.fontaine@gmail.com",
            "status": "monitoring",
            "lock_type": "standard",
            "lock_period_days": 30,
            "rate_locked": Decimal("6.625"),
            "lock_days_ago": 48,
            "ai_recommendation": "lock",
            "ai_lock_score": 88,
            "ai_reasoning": "CTC issued. Closing in 5 days. Rate at 6.625% is excellent for FHA. Lock secured — no action needed.",
            "market_rate_at_lock": Decimal("6.625"),
        },
    ]

    rl_inserted = 0
    rl_skipped = 0

    for rl in RATE_LOCKS:
        loan_id = loan_ids.get(rl["loan_number"])
        if not loan_id:
            continue

        lead_id = conn.execute(
            text("SELECT id FROM leads WHERE email = :email AND organization_id = :org_id LIMIT 1"),
            {"email": rl["lead_email"], "org_id": org_id},
        ).fetchone()
        lead_id = lead_id[0] if lead_id else None

        existing = conn.execute(
            text("""
                SELECT id FROM rate_locks
                WHERE loan_id = :loan_id AND organization_id = :org_id
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()
        if existing:
            rl_skipped += 1
            continue

        lock_date = days_ago(rl["lock_days_ago"])
        lock_exp = lock_date + timedelta(days=rl["lock_period_days"])

        conn.execute(
            text("""
                INSERT INTO rate_locks
                    (organization_id, loan_id, lead_id,
                     status, lock_type, lock_period_days,
                     rate_locked, lock_date, lock_expiration_date,
                     ai_recommendation, ai_lock_score, ai_reasoning,
                     market_rate_at_lock, created_at)
                VALUES
                    (:org_id, :loan_id, :lead_id,
                     :status, :lock_type, :lock_period_days,
                     :rate_locked, :lock_date, :lock_expiration_date,
                     :ai_recommendation, :ai_lock_score, :ai_reasoning,
                     :market_rate_at_lock, :now)
            """),
            {
                "org_id": org_id,
                "loan_id": loan_id,
                "lead_id": lead_id,
                "status": rl["status"],
                "lock_type": rl["lock_type"],
                "lock_period_days": rl["lock_period_days"],
                "rate_locked": rl["rate_locked"],
                "lock_date": lock_date,
                "lock_expiration_date": lock_exp,
                "ai_recommendation": rl["ai_recommendation"],
                "ai_lock_score": rl["ai_lock_score"],
                "ai_reasoning": rl["ai_reasoning"],
                "market_rate_at_lock": rl["market_rate_at_lock"],
                "now": NOW,
            },
        )
        rl_inserted += 1

    conn.commit()
    print(f"✅ Seeded {rl_inserted} rate locks ({rl_skipped} existed)")

    # ------------------------------------------------------------------
    # 3. RefiOpportunity — 5 opportunities linked to MUM clients
    # ------------------------------------------------------------------
    # Clients with high rates (>6%): Brian & Monica Tanner (6.750), Lauren Fitzgerald (6.875),
    # Kenneth & Paula Osei (6.500), Nadia & Paul Bergeron (6.625), Terrence & Alicia Watkins (6.875)
    REFI_OPPS = [
        {
            "mum_idx": 7,   # Brian Tanner — 6.750%, 3 years ago, $375K
            "opportunity_type": "rate_reduction",
            "refi_score": 78,
            "original_rate": Decimal("6.750"),
            "current_balance": Decimal("362000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.125"),
            "estimated_home_value": Decimal("434500.00"),
            "estimated_monthly_savings": Decimal("32.00"),
            "estimated_total_savings": Decimal("11520.00"),
            "break_even_months": 96,
            "status": "identified",
            "identified_at": days_ago(15),
            "contacted_at": None,
            "outreach_count": 0,
        },
        {
            "mum_idx": 8,   # Lauren Fitzgerald — 6.875%, 3 years ago, $270K
            "opportunity_type": "rate_reduction",
            "refi_score": 82,
            "original_rate": Decimal("6.875"),
            "current_balance": Decimal("259000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.250"),
            "estimated_home_value": Decimal("316100.00"),
            "estimated_monthly_savings": Decimal("42.00"),
            "estimated_total_savings": Decimal("15120.00"),
            "break_even_months": 72,
            "status": "contacted",
            "identified_at": days_ago(30),
            "contacted_at": days_ago(20),
            "outreach_count": 2,
        },
        {
            "mum_idx": 9,   # Kenneth Osei — 6.500%, 2 years ago, $480K
            "opportunity_type": "rate_reduction",
            "refi_score": 70,
            "original_rate": Decimal("6.500"),
            "current_balance": Decimal("464000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("-0.125"),
            "estimated_home_value": Decimal("577800.00"),
            "estimated_monthly_savings": Decimal("-32.00"),
            "estimated_total_savings": Decimal("-11520.00"),
            "break_even_months": 999,
            "status": "identified",
            "identified_at": days_ago(10),
            "contacted_at": None,
            "outreach_count": 0,
        },
        {
            "mum_idx": 10,  # Nadia Bergeron — 6.625%, 2 years ago, $325K
            "opportunity_type": "cash_out",
            "refi_score": 65,
            "original_rate": Decimal("6.625"),
            "current_balance": Decimal("313000.00"),
            "current_market_rate": Decimal("6.700"),
            "rate_advantage": Decimal("-0.075"),
            "estimated_home_value": Decimal("390300.00"),
            "estimated_monthly_savings": Decimal("0.00"),
            "estimated_total_savings": Decimal("0.00"),
            "break_even_months": 0,
            "status": "interested",
            "identified_at": days_ago(45),
            "contacted_at": days_ago(35),
            "outreach_count": 3,
        },
        {
            "mum_idx": 11,  # Terrence Watkins — 6.875%, 1 year ago, $350K
            "opportunity_type": "rate_reduction",
            "refi_score": 86,
            "original_rate": Decimal("6.875"),
            "current_balance": Decimal("344000.00"),
            "current_market_rate": Decimal("6.625"),
            "rate_advantage": Decimal("0.250"),
            "estimated_home_value": Decimal("405600.00"),
            "estimated_monthly_savings": Decimal("57.00"),
            "estimated_total_savings": Decimal("20520.00"),
            "break_even_months": 60,
            "status": "contacted",
            "identified_at": days_ago(20),
            "contacted_at": days_ago(10),
            "outreach_count": 1,
        },
    ]

    ro_inserted = 0
    ro_skipped = 0

    for opp in REFI_OPPS:
        mum_idx = opp["mum_idx"]
        if mum_idx >= len(mum_ids):
            continue
        mum_id = mum_ids[mum_idx]

        existing = conn.execute(
            text("""
                SELECT id FROM refi_opportunities
                WHERE mum_client_id = :mum_id AND organization_id = :org_id
                LIMIT 1
            """),
            {"mum_id": mum_id, "org_id": org_id},
        ).fetchone()
        if existing:
            ro_skipped += 1
            continue

        conn.execute(
            text("""
                INSERT INTO refi_opportunities
                    (organization_id, mum_client_id,
                     opportunity_type, refi_score,
                     original_rate, current_balance,
                     current_market_rate, rate_advantage,
                     estimated_home_value, estimated_monthly_savings,
                     estimated_total_savings, break_even_months,
                     status, identified_at, contacted_at, outreach_count,
                     created_at)
                VALUES
                    (:org_id, :mum_id,
                     :opportunity_type, :refi_score,
                     :original_rate, :current_balance,
                     :current_market_rate, :rate_advantage,
                     :estimated_home_value, :estimated_monthly_savings,
                     :estimated_total_savings, :break_even_months,
                     :status, :identified_at, :contacted_at, :outreach_count,
                     :now)
            """),
            {
                "org_id": org_id,
                "mum_id": mum_id,
                "opportunity_type": opp["opportunity_type"],
                "refi_score": opp["refi_score"],
                "original_rate": opp["original_rate"],
                "current_balance": opp["current_balance"],
                "current_market_rate": opp["current_market_rate"],
                "rate_advantage": opp["rate_advantage"],
                "estimated_home_value": opp["estimated_home_value"],
                "estimated_monthly_savings": opp["estimated_monthly_savings"],
                "estimated_total_savings": opp["estimated_total_savings"],
                "break_even_months": opp["break_even_months"],
                "status": opp["status"],
                "identified_at": opp["identified_at"],
                "contacted_at": opp["contacted_at"],
                "outreach_count": opp["outreach_count"],
                "now": NOW,
            },
        )
        ro_inserted += 1

    conn.commit()
    print(f"✅ Seeded {ro_inserted} refi opportunities ({ro_skipped} existed)")


def seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create workflow automation records and compliance checks."""
    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # -------------------------------------------------------------------------
    # 1. Workflows
    # -------------------------------------------------------------------------
    WORKFLOWS = [
        {
            "name": "Lead Nurture",
            "description": "Automated multi-touch nurture sequence for new leads",
            "workflow_type": "lead_nurture",
            "steps": [
                {"step": 1, "action": "send_sms", "delay_hours": 0, "message": "Hi {first_name}, thanks for your interest! I'm {lo_name} — happy to answer any mortgage questions."},
                {"step": 2, "action": "send_email", "delay_hours": 24, "template": "intro_email"},
                {"step": 3, "action": "create_task", "delay_hours": 48, "task": "Follow-up call"},
                {"step": 4, "action": "send_sms", "delay_hours": 120, "message": "Hi {first_name}, just checking in — did you have a chance to review the info I sent?"},
                {"step": 5, "action": "create_task", "delay_hours": 168, "task": "7-day follow-up"},
            ],
        },
        {
            "name": "Underwriting Checklist",
            "description": "Document collection and status checklist for underwriting stage",
            "workflow_type": "underwriting",
            "steps": [
                {"step": 1, "action": "request_document", "doc_type": "w2", "message": "Please upload your W-2 for the past 2 years"},
                {"step": 2, "action": "request_document", "doc_type": "paystub", "message": "Please upload your two most recent pay stubs"},
                {"step": 3, "action": "request_document", "doc_type": "bank_statement", "message": "Please upload 2 months of bank statements"},
                {"step": 4, "action": "notify_processor", "delay_hours": 0, "message": "All documents collected — ready for UW review"},
            ],
        },
        {
            "name": "Post-Closing Follow-Up",
            "description": "Relationship maintenance sequence after loan closes",
            "workflow_type": "post_closing",
            "steps": [
                {"step": 1, "action": "send_email", "delay_days": 1, "template": "congratulations_email"},
                {"step": 2, "action": "create_task", "delay_days": 7, "task": "1-week check-in call"},
                {"step": 3, "action": "send_email", "delay_days": 30, "template": "one_month_checkup"},
                {"step": 4, "action": "create_task", "delay_days": 180, "task": "6-month rate review"},
                {"step": 5, "action": "send_email", "delay_days": 365, "template": "annual_review"},
            ],
        },
    ]

    workflow_ids = []
    for wf in WORKFLOWS:
        existing = conn.execute(
            text("SELECT id FROM workflows WHERE name = :name AND organization_id = :org_id LIMIT 1"),
            {"name": wf["name"], "org_id": org_id},
        ).fetchone()
        if existing:
            workflow_ids.append(existing[0])
            continue
        result = conn.execute(
            text("""
                INSERT INTO workflows
                    (organization_id, user_id, name, description, workflow_type,
                     steps, is_active, created_at)
                VALUES
                    (:org_id, :user_id, :name, :description, :workflow_type,
                     :steps, :is_active, :created_at)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "user_id": manager_id,
                "name": wf["name"],
                "description": wf["description"],
                "workflow_type": wf["workflow_type"],
                "steps": json.dumps(wf["steps"]),
                "is_active": True,
                "created_at": days_ago(90),
            },
        )
        wf_id = result.fetchone()[0]
        workflow_ids.append(wf_id)
    conn.commit()
    print(f"✅ Seeded {len(WORKFLOWS)} workflows")

    # -------------------------------------------------------------------------
    # 2. Workflow executions — only if scheduled_workflows table exists
    # -------------------------------------------------------------------------
    has_scheduled = conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduled_workflows')")
    ).scalar()

    if has_scheduled:
        for i, wf_id in enumerate(workflow_ids[:2]):
            already = conn.execute(
                text("SELECT id FROM workflow_executions WHERE workflow_id = :wid LIMIT 1"),
                {"wid": wf_id},
            ).fetchone()
            if already:
                continue
            started = days_ago(random.randint(5, 30))
            completed = started + timedelta(hours=random.randint(1, 6))
            conn.execute(
                text("""
                    INSERT INTO workflow_executions
                        (organization_id, workflow_id, user_id, status,
                         started_at, completed_at, targets_processed, targets_succeeded,
                         trigger_type, created_at)
                    VALUES
                        (:org_id, :workflow_id, :user_id, :status,
                         :started_at, :completed_at, :targets_processed, :targets_succeeded,
                         :trigger_type, :created_at)
                """),
                {
                    "org_id": org_id,
                    "workflow_id": wf_id,
                    "user_id": manager_id,
                    "status": "completed",
                    "started_at": started,
                    "completed_at": completed,
                    "targets_processed": random.randint(8, 20),
                    "targets_succeeded": random.randint(6, 8),
                    "trigger_type": "manual",
                    "created_at": started,
                },
            )
        conn.commit()
        print("✅ Seeded workflow executions")
    else:
        print("⏭️  Skipping workflow_executions — scheduled_workflows table not found")

    # -------------------------------------------------------------------------
    # 3. Audit logs (50 entries over 90 days)
    # -------------------------------------------------------------------------
    audit_count = conn.execute(
        text("SELECT COUNT(*) FROM audit_logs WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if audit_count and audit_count >= 50:
        print("⏭️  Audit logs exist")
    else:
        all_user_ids = [manager_id, lo_sarah_id, lo_marcus_id]
        all_lead_ids = list(lead_ids.values())[:10]
        all_loan_ids = list(loan_ids.values())[:10]

        change_types = ["login", "create", "update", "delete", "permission_grant", "export"]
        entity_types = ["user", "lead", "loan", "task", "document"]

        random.seed(42)
        for i in range(50):
            change_type = random.choice(change_types)
            entity_type = random.choice(entity_types)
            actor_id = random.choice(all_user_ids)

            if entity_type == "lead" and all_lead_ids:
                entity_id = str(random.choice(all_lead_ids))
            elif entity_type == "loan" and all_loan_ids:
                entity_id = str(random.choice(all_loan_ids))
            else:
                entity_id = str(random.choice(all_user_ids))

            ts = days_ago(random.randint(0, 90))
            conn.execute(
                text("""
                    INSERT INTO audit_logs
                        (organization_id, user_id, change_type, entity_type, entity_id,
                         ip_address, timestamp, reason)
                    VALUES
                        (:org_id, :user_id, :change_type, :entity_type, :entity_id,
                         :ip_address, :timestamp, :reason)
                """),
                {
                    "org_id": org_id,
                    "user_id": actor_id,
                    "change_type": change_type,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "ip_address": f"192.168.1.{random.randint(1, 254)}",
                    "timestamp": ts,
                    "reason": f"Demo: {change_type} on {entity_type}",
                },
            )
        conn.commit()
        print("✅ Seeded 50 audit log entries")

    # -------------------------------------------------------------------------
    # 4. Disclosure events (10 across active/funded loans)
    # -------------------------------------------------------------------------
    disc_count = conn.execute(
        text("SELECT COUNT(*) FROM disclosure_events WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if disc_count and disc_count >= 10:
        print("⏭️  Disclosure events exist")
    else:
        disclosure_loan_numbers = [
            "SHL-2026-0001", "SHL-2026-0002", "SHL-2026-0003", "SHL-2026-0004",
            "SHL-2026-0005", "SHL-2026-0006", "SHL-2026-0007", "SHL-2026-0011",
            "SHL-2026-0012", "SHL-2026-0015",
        ]
        disc_types = [
            ("loan_estimate", 3), ("loan_estimate", 8), ("revised_le", 2),
            ("loan_estimate", 5), ("loan_estimate", 7),
            ("closing_disclosure", 1), ("closing_disclosure", 3),
            ("closing_disclosure", 10), ("closing_disclosure", 15), ("revised_cd", 2),
        ]

        for idx, loan_number in enumerate(disclosure_loan_numbers):
            loan_id = loan_ids.get(loan_number)
            if not loan_id:
                continue
            disc_type, days_before_close = disc_types[idx]
            prepared_at = days_ago(days_before_close + 3)
            sent_at = days_ago(days_before_close + 1)
            received_at = days_ago(days_before_close)
            deadline = date_from_now(3) if days_before_close <= 2 else date_ago(days_before_close - 3)
            is_on_time = days_before_close >= 3

            conn.execute(
                text("""
                    INSERT INTO disclosure_events
                        (organization_id, loan_id, disclosure_type,
                         prepared_at, sent_at, received_at, deadline_date,
                         is_on_time, delivery_method, created_by_id, created_at)
                    VALUES
                        (:org_id, :loan_id, :disclosure_type,
                         :prepared_at, :sent_at, :received_at, :deadline_date,
                         :is_on_time, :delivery_method, :created_by_id, :created_at)
                """),
                {
                    "org_id": org_id,
                    "loan_id": loan_id,
                    "disclosure_type": disc_type,
                    "prepared_at": prepared_at,
                    "sent_at": sent_at,
                    "received_at": received_at,
                    "deadline_date": deadline,
                    "is_on_time": is_on_time,
                    "delivery_method": "email",
                    "created_by_id": manager_id,
                    "created_at": prepared_at,
                },
            )
        conn.commit()
        print("✅ Seeded 10 disclosure events")

    # -------------------------------------------------------------------------
    # 5. Compliance alerts (5: 2 resolved, 3 pending)
    # -------------------------------------------------------------------------
    alert_count = conn.execute(
        text("SELECT COUNT(*) FROM compliance_alerts WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if alert_count and alert_count >= 5:
        print("⏭️  Compliance alerts exist")
    else:
        # Grab some loan/lead ids for linking
        loan_id_0001 = loan_ids.get("SHL-2026-0001")
        loan_id_0003 = loan_ids.get("SHL-2026-0003")
        loan_id_0007 = loan_ids.get("SHL-2026-0007")
        lead_id_chase = list(lead_ids.values())[0] if lead_ids else None

        ALERTS = [
            # Resolved
            {
                "loan_id": loan_id_0001, "lead_id": None,
                "alert_type": "le_deadline", "severity": "high",
                "title": "Loan Estimate deadline approaching",
                "description": "LE must be delivered within 3 business days of application",
                "deadline_date": date_ago(5), "days_remaining": 0,
                "status": "resolved", "resolved_at": days_ago(6),
                "resolution_notes": "LE delivered on time via email",
            },
            {
                "loan_id": loan_id_0003, "lead_id": None,
                "alert_type": "document_expiry", "severity": "medium",
                "title": "Appraisal expiring in 30 days",
                "description": "Appraisal report will expire before projected closing date",
                "deadline_date": date_from_now(30), "days_remaining": 30,
                "status": "resolved", "resolved_at": days_ago(2),
                "resolution_notes": "Closing rescheduled to be within appraisal validity window",
            },
            # Pending
            {
                "loan_id": loan_id_0007, "lead_id": None,
                "alert_type": "rate_lock_expiry", "severity": "critical",
                "title": "Rate lock expiring in 3 days",
                "description": "Rate lock on SHL-2026-0007 expires before closing",
                "deadline_date": date_from_now(3), "days_remaining": 3,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
            {
                "loan_id": None, "lead_id": lead_id_chase,
                "alert_type": "tcpa_violation", "severity": "high",
                "title": "TCPA consent not on file",
                "description": "Outbound call attempted without verified TCPA consent record",
                "deadline_date": date_from_now(7), "days_remaining": 7,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
            {
                "loan_id": loan_id_0001, "lead_id": None,
                "alert_type": "cd_deadline", "severity": "high",
                "title": "Closing Disclosure 3-day waiting period",
                "description": "CD must be received by borrower 3 business days before closing",
                "deadline_date": date_from_now(2), "days_remaining": 2,
                "status": "open", "resolved_at": None,
                "resolution_notes": None,
            },
        ]

        for alert in ALERTS:
            conn.execute(
                text("""
                    INSERT INTO compliance_alerts
                        (organization_id, loan_id, lead_id, alert_type, severity,
                         title, description, deadline_date, days_remaining,
                         status, resolved_at, resolved_by_id, resolution_notes, created_at)
                    VALUES
                        (:org_id, :loan_id, :lead_id, :alert_type, :severity,
                         :title, :description, :deadline_date, :days_remaining,
                         :status, :resolved_at, :resolved_by_id, :resolution_notes, :created_at)
                """),
                {
                    "org_id": org_id,
                    "loan_id": alert["loan_id"],
                    "lead_id": alert["lead_id"],
                    "alert_type": alert["alert_type"],
                    "severity": alert["severity"],
                    "title": alert["title"],
                    "description": alert["description"],
                    "deadline_date": alert["deadline_date"],
                    "days_remaining": alert["days_remaining"],
                    "status": alert["status"],
                    "resolved_at": alert["resolved_at"],
                    "resolved_by_id": manager_id if alert["resolved_at"] else None,
                    "resolution_notes": alert["resolution_notes"],
                    "created_at": days_ago(10),
                },
            )
        conn.commit()
        print("✅ Seeded 5 compliance alerts")

    # -------------------------------------------------------------------------
    # 6. Smart docs consent records (8)
    # -------------------------------------------------------------------------
    consent_count = conn.execute(
        text("SELECT COUNT(*) FROM smart_docs_consent_records WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).scalar()

    if consent_count and consent_count >= 8:
        print("⏭️  Smart docs consent records exist")
    else:
        lead_phones = [
            (lead_ids.get("tyler.barnes@gmail.com"), "+18432110101"),
            (lead_ids.get("priya.nair@outlook.com"), "+18432110102"),
            (lead_ids.get("derek.hollis@yahoo.com"), "+18432110103"),
            (lead_ids.get("vanessa.hartley@gmail.com"), "+18432110112"),
            (lead_ids.get("tanya.morrison@gmail.com"), "+18432110114"),
            (lead_ids.get("roberto.sandoval@hotmail.com"), "+18432110115"),
            (lead_ids.get("aisha.coleman@gmail.com"), "+18432110116"),
            (lead_ids.get("michelle.osei@gmail.com"), "+18432110122"),
        ]
        channels = ["sms", "voice", "sms", "sms", "voice", "sms", "sms", "voice"]
        sources = [
            "sms_opt_in", "borrower_portal", "sms_opt_in", "borrower_portal",
            "sms_opt_in", "borrower_portal", "sms_opt_in", "borrower_portal",
        ]

        for idx, (borrower_id, phone) in enumerate(lead_phones):
            if not phone:
                continue
            conn.execute(
                text("""
                    INSERT INTO smart_docs_consent_records
                        (organization_id, borrower_id, phone, channel,
                         consent_given, consent_source, consented_at, created_at)
                    VALUES
                        (:org_id, :borrower_id, :phone, :channel,
                         :consent_given, :consent_source, :consented_at, :created_at)
                """),
                {
                    "org_id": org_id,
                    "borrower_id": borrower_id,
                    "phone": phone,
                    "channel": channels[idx],
                    "consent_given": True,
                    "consent_source": sources[idx],
                    "consented_at": days_ago(random.randint(1, 30)),
                    "created_at": days_ago(random.randint(1, 30)),
                },
            )
        conn.commit()
        print("✅ Seeded 8 smart docs consent records")


