"""
Analytics Agents

Periodic analytics and reporting autonomous agents:
1. weekly_production_report — Weekly Monday, org-wide production summary
2. monthly_pipeline_review — 1st of month, month-end pipeline snapshot
3. conversion_funnel_analyzer — Daily, analyze lead-to-close conversion funnel
4. marketing_roi_calculator — Weekly Friday, ROI per lead source
5. team_leaderboard — Weekly Friday, generate team rankings
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
)
ACTIVE_PIPELINE_FILTER = (
    "l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')"
)
FUNDED_FILTER = "l.stage = 'FUNDED'"
FALLOUT_STAGES = "'CANCELLED','DENIED','WITHDRAWN'"

# Stage ordering for funnel analysis (loan stages)
LOAN_STAGE_ORDER = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
    "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED",
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
]

# SLA targets in days per stage (industry benchmarks)
STAGE_SLA_DAYS = {
    "APPLICATION": 3,
    "DISCLOSED": 5,
    "PROCESSING": 7,
    "SUBMITTED": 3,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 3,
    "CONDITIONAL_APPROVAL": 7,
    "APPROVED": 5,
    "SUSPENDED": 10,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "CLOSING": 5,
    "DOCS": 3,
    "DOCS_OUT": 3,
}

# Historical conversion rates by stage for projection (reasonable defaults)
DEFAULT_STAGE_CONVERSION = {
    "APPLICATION": 0.85,
    "DISCLOSED": 0.90,
    "PROCESSING": 0.88,
    "SUBMITTED": 0.90,
    "UNDERWRITING": 0.82,
    "UW_RECEIVED": 0.85,
    "CONDITIONAL_APPROVAL": 0.90,
    "APPROVED": 0.95,
    "CTC": 0.97,
    "CLEAR_TO_CLOSE": 0.98,
    "CLOSING": 0.99,
    "DOCS": 0.99,
    "DOCS_OUT": 0.99,
}


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division avoiding ZeroDivisionError."""
    return (numerator / denominator) if denominator else default


def _pct(numerator: float, denominator: float) -> float:
    """Return percentage with one decimal, safe from divide-by-zero."""
    return round(_safe_div(numerator * 100, denominator), 1)


def _insert_activity(
    db: Session,
    organization_id: int,
    content: str,
    report_type: str,
    report_data: Optional[Dict[str, Any]] = None,
    gateway=None,
) -> None:
    """Insert a System activity with optional structured JSON in user_metadata."""
    def _do():
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, user_metadata, created_at, organization_id)
            VALUES (NULL, 'System', :content, :metadata, CURRENT_TIMESTAMP, :org_id)
        """), {
            "content": content[:4000],
            "metadata": json.dumps(report_data) if report_data else None,
            "org_id": organization_id,
        })
    if gateway:
        gateway.propose(
            "create_activity", _do,
            target_entity=None,
            target_id=None,
            description=content[:200],
        )
    else:
        _do()


def _insert_task(
    db: Session,
    organization_id: int,
    title: str,
    description: str,
    priority: str = "medium",
    assigned_to_id: Optional[int] = None,
    due_days: int = 3,
    gateway=None,
) -> None:
    """Insert a task with deduplication (no duplicate within 48h)."""
    existing = db.execute(text("""
        SELECT id FROM tasks
        WHERE organization_id = :org_id
          AND title = :title
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '48 hours'
        LIMIT 1
    """), {"org_id": organization_id, "title": title}).fetchone()

    if not existing:
        def _do():
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, due_date,
                                   owner_id, created_at, organization_id)
                VALUES (:title, :desc, :priority, 'pending',
                        CURRENT_DATE + :due_days, :owner_id, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": title[:255],
                "desc": description[:2000],
                "priority": priority,
                "due_days": due_days,
                "owner_id": str(assigned_to_id) if assigned_to_id else None,
                "org_id": organization_id,
            })
        if gateway:
            gateway.propose(
                "create_task", _do,
                target_entity=None,
                target_id=None,
                description=title[:200],
            )
        else:
            _do()


# ---------------------------------------------------------------------------
# 1. Weekly Production Report
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="weekly_production_report",
    description="Generate org-wide weekly production summary",
    frequency=AgentFrequency.WEEKLY_MONDAY,
    max_runtime_seconds=120,
)
def weekly_production_report(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Comprehensive weekly production report with per-LO breakdown,
    week-over-week trends, pull-through rates, and top performer recognition."""
    actions = 0
    notifications = 0

    # ------------------------------------------------------------------
    # Per-LO production: this week, last week, and 4-week averages
    # ------------------------------------------------------------------
    lo_data = db.execute(text("""
        SELECT
            u.id as lo_id,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name,
            -- This week (last 7 days)
            COUNT(CASE WHEN l.stage = 'FUNDED'
                        AND l.stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as funded_this_week,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                              AND l.stage_changed_at >= CURRENT_DATE - 7
                         THEN l.amount END), 0) as funded_vol_this_week,
            -- Last week (8-14 days ago)
            COUNT(CASE WHEN l.stage = 'FUNDED'
                        AND l.stage_changed_at >= CURRENT_DATE - 14
                        AND l.stage_changed_at < CURRENT_DATE - 7 THEN 1 END) as funded_last_week,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                              AND l.stage_changed_at >= CURRENT_DATE - 14
                              AND l.stage_changed_at < CURRENT_DATE - 7
                         THEN l.amount END), 0) as funded_vol_last_week,
            -- 4-week funded (for weekly average)
            COUNT(CASE WHEN l.stage = 'FUNDED'
                        AND l.stage_changed_at >= CURRENT_DATE - 28 THEN 1 END) as funded_4wk,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                              AND l.stage_changed_at >= CURRENT_DATE - 28
                         THEN l.amount END), 0) as funded_vol_4wk,
            -- Active pipeline
            COUNT(CASE WHEN l.stage NOT IN (
                'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
            ) THEN 1 END) as active_pipeline_count,
            COALESCE(SUM(CASE WHEN l.stage NOT IN (
                'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
            ) THEN l.amount END), 0) as active_pipeline_vol,
            -- Pull-through denominator (funded + fallout this week)
            COUNT(CASE WHEN l.stage IN ('CANCELLED','DENIED','WITHDRAWN')
                        AND l.stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as fallout_this_week,
            -- Average days to close for loans funded this week
            AVG(CASE WHEN l.stage = 'FUNDED'
                      AND l.stage_changed_at >= CURRENT_DATE - 7
                      AND l.application_date IS NOT NULL
                 THEN EXTRACT(DAY FROM (l.stage_changed_at - l.application_date))
            END) as avg_days_to_close
        FROM users u
        LEFT JOIN loans l ON l.loan_officer_id = u.id AND l.organization_id = :org_id
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'branch_manager')
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY funded_vol_this_week DESC
    """), {"org_id": organization_id}).fetchall()

    # ------------------------------------------------------------------
    # Lead-to-application conversion (org-wide, last 7 days)
    # ------------------------------------------------------------------
    lead_conv = db.execute(text("""
        SELECT
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as new_leads,
            COUNT(CASE WHEN stage IN ('Application', 'Converted')
                        AND created_at >= CURRENT_DATE - 7 THEN 1 END) as to_app
        FROM leads WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    new_leads = lead_conv[0] or 0
    to_app = lead_conv[1] or 0
    lead_to_app_rate = _pct(to_app, new_leads)

    # ------------------------------------------------------------------
    # Build per-LO report and find top performer / most improved
    # ------------------------------------------------------------------
    lo_reports: List[Dict[str, Any]] = []
    org_funded = 0
    org_funded_vol = 0.0
    org_pipeline_count = 0
    org_pipeline_vol = 0.0
    top_performer_id: Optional[int] = None
    top_performer_name = ""
    top_funded_vol = 0.0
    best_improvement = -999999.0
    most_improved_name = ""
    most_improved_id: Optional[int] = None

    for row in lo_data:
        lo_id = row[0]
        lo_name = row[1]
        funded_tw = row[2] or 0
        funded_vol_tw = float(row[3] or 0)
        funded_lw = row[4] or 0
        funded_vol_lw = float(row[5] or 0)
        funded_4wk = row[6] or 0
        funded_vol_4wk = float(row[7] or 0)
        pipeline_count = row[8] or 0
        pipeline_vol = float(row[9] or 0)
        fallout_tw = row[10] or 0
        avg_dtc = round(float(row[11]), 1) if row[11] else None

        four_wk_avg_count = round(funded_4wk / 4, 1)
        four_wk_avg_vol = round(funded_vol_4wk / 4, 2)
        pull_through = _pct(funded_tw, funded_tw + fallout_tw)
        wow_vol_change = funded_vol_tw - funded_vol_lw

        org_funded += funded_tw
        org_funded_vol += funded_vol_tw
        org_pipeline_count += pipeline_count
        org_pipeline_vol += pipeline_vol

        lo_report = {
            "lo_id": lo_id,
            "lo_name": lo_name,
            "funded_count": funded_tw,
            "funded_volume": funded_vol_tw,
            "funded_last_week_count": funded_lw,
            "funded_last_week_volume": funded_vol_lw,
            "four_week_avg_count": four_wk_avg_count,
            "four_week_avg_volume": four_wk_avg_vol,
            "active_pipeline_count": pipeline_count,
            "active_pipeline_volume": pipeline_vol,
            "pull_through_rate": pull_through,
            "avg_days_to_close": avg_dtc,
            "wow_volume_change": wow_vol_change,
        }
        lo_reports.append(lo_report)

        if funded_vol_tw > top_funded_vol:
            top_funded_vol = funded_vol_tw
            top_performer_id = lo_id
            top_performer_name = lo_name

        if wow_vol_change > best_improvement and funded_vol_lw > 0:
            best_improvement = wow_vol_change
            most_improved_name = lo_name
            most_improved_id = lo_id

    # ------------------------------------------------------------------
    # Org-wide pull-through
    # ------------------------------------------------------------------
    org_pt = db.execute(text("""
        SELECT
            COUNT(CASE WHEN stage = 'FUNDED'
                        AND stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as funded,
            COUNT(CASE WHEN stage IN ('CANCELLED','DENIED','WITHDRAWN')
                        AND stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as fallout
        FROM loans WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()
    org_pull_through = _pct(org_pt[0] or 0, (org_pt[0] or 0) + (org_pt[1] or 0))

    # ------------------------------------------------------------------
    # Org-wide avg days to close
    # ------------------------------------------------------------------
    org_dtc = db.execute(text("""
        SELECT AVG(EXTRACT(DAY FROM (stage_changed_at - application_date)))
        FROM loans
        WHERE organization_id = :org_id
          AND stage = 'FUNDED'
          AND stage_changed_at >= CURRENT_DATE - 7
          AND application_date IS NOT NULL
    """), {"org_id": organization_id}).fetchone()
    org_avg_dtc = round(float(org_dtc[0]), 1) if org_dtc and org_dtc[0] else None

    # ------------------------------------------------------------------
    # Build structured report
    # ------------------------------------------------------------------
    report = {
        "report_type": "weekly_production",
        "period": "last_7_days",
        "org_totals": {
            "funded_count": org_funded,
            "funded_volume": org_funded_vol,
            "active_pipeline_count": org_pipeline_count,
            "active_pipeline_volume": org_pipeline_vol,
            "pull_through_rate": org_pull_through,
            "avg_days_to_close": org_avg_dtc,
            "new_leads": new_leads,
            "lead_to_app_rate": lead_to_app_rate,
        },
        "lo_breakdown": lo_reports,
        "top_performer": {
            "lo_id": top_performer_id,
            "lo_name": top_performer_name,
            "funded_volume": top_funded_vol,
        },
        "most_improved": {
            "lo_id": most_improved_id,
            "lo_name": most_improved_name,
            "wow_volume_change": best_improvement if most_improved_id else 0,
        },
    }

    summary = (
        f"Weekly production: {org_funded} funded (${org_funded_vol:,.0f}), "
        f"{org_pipeline_count} active pipeline (${org_pipeline_vol:,.0f}), "
        f"pull-through {org_pull_through}%, "
        f"avg close {org_avg_dtc or 'N/A'}d, "
        f"{new_leads} new leads ({lead_to_app_rate}% to app). "
        f"Top: {top_performer_name or 'N/A'}"
    )

    _insert_activity(db, organization_id, f"[Weekly Report] {summary}", "weekly_production", report, gateway=gateway)
    actions += 1

    # Create congratulations task for top performer
    if top_performer_id and top_funded_vol > 0:
        _insert_task(
            db, organization_id,
            title=f"Recognize top performer: {top_performer_name}",
            description=(
                f"{top_performer_name} led the team this week with "
                f"${top_funded_vol:,.0f} in funded volume. "
                f"Consider public recognition or incentive."
            ),
            priority="low",
            due_days=1,
            gateway=gateway,
        )
        actions += 1
        notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Weekly production report commit failed: {e}")

    return {"summary": summary, "actions_taken": actions, "notifications_sent": notifications}


# ---------------------------------------------------------------------------
# 2. Monthly Pipeline Review
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="monthly_pipeline_review",
    description="Month-end pipeline snapshot and trend analysis",
    frequency=AgentFrequency.MONTHLY_FIRST,
    max_runtime_seconds=120,
)
def monthly_pipeline_review(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Full pipeline review: stage distribution, month-over-month trends,
    health score, bottleneck detection, funding projections, aging analysis,
    and management action items."""
    actions = 0

    # ------------------------------------------------------------------
    # Stage distribution with avg days-in-stage
    # ------------------------------------------------------------------
    stage_dist = db.execute(text("""
        SELECT
            l.stage,
            COUNT(*) as cnt,
            COALESCE(SUM(l.amount), 0) as vol,
            AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at))) as avg_days_in_stage,
            COUNT(CASE WHEN l.stage_changed_at < CURRENT_TIMESTAMP - INTERVAL '14 days' THEN 1 END) as aged_count
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')
        GROUP BY l.stage
        ORDER BY
            CASE l.stage
                WHEN 'APPLICATION' THEN 1 WHEN 'DISCLOSED' THEN 2
                WHEN 'PROCESSING' THEN 3 WHEN 'SUBMITTED' THEN 4
                WHEN 'UNDERWRITING' THEN 5 WHEN 'UW_RECEIVED' THEN 6
                WHEN 'CONDITIONAL_APPROVAL' THEN 7 WHEN 'APPROVED' THEN 8
                WHEN 'SUSPENDED' THEN 9 WHEN 'CTC' THEN 10
                WHEN 'CLEAR_TO_CLOSE' THEN 11 WHEN 'CLOSING' THEN 12
                WHEN 'DOCS' THEN 13 WHEN 'DOCS_OUT' THEN 14
                ELSE 99
            END
    """), {"org_id": organization_id}).fetchall()

    # ------------------------------------------------------------------
    # This month vs last month funded
    # ------------------------------------------------------------------
    month_compare = db.execute(text("""
        SELECT
            -- Last month
            COUNT(CASE WHEN stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                        AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as last_month_funded,
            COALESCE(SUM(CASE WHEN stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                              AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE)
                         THEN amount END), 0) as last_month_vol,
            -- Two months ago
            COUNT(CASE WHEN stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '2 months'
                        AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                   THEN 1 END) as prev_month_funded,
            COALESCE(SUM(CASE WHEN stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '2 months'
                              AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                         THEN amount END), 0) as prev_month_vol,
            -- Last month fallout
            COUNT(CASE WHEN stage IN ('CANCELLED','DENIED','WITHDRAWN')
                        AND stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                        AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as last_month_fallout,
            -- Last month new apps
            COUNT(CASE WHEN created_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                        AND created_at < DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as last_month_new_apps,
            -- Avg days to close last month
            AVG(CASE WHEN stage = 'FUNDED'
                      AND stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
                      AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE)
                      AND application_date IS NOT NULL
                 THEN EXTRACT(DAY FROM (stage_changed_at - application_date)) END) as avg_dtc_last_month
        FROM loans WHERE organization_id = :org_id AND stage = 'FUNDED'
            OR (organization_id = :org_id AND stage IN ('CANCELLED','DENIED','WITHDRAWN'))
            OR (organization_id = :org_id)
    """), {"org_id": organization_id}).fetchone()

    last_funded = month_compare[0] or 0
    last_vol = float(month_compare[1] or 0)
    prev_funded = month_compare[2] or 0
    prev_vol = float(month_compare[3] or 0)
    last_fallout = month_compare[4] or 0
    last_new_apps = month_compare[5] or 0
    avg_dtc = round(float(month_compare[6]), 1) if month_compare[6] else None

    mom_funded_change = _pct(last_funded - prev_funded, prev_funded) if prev_funded else 0
    mom_vol_change = _pct(last_vol - prev_vol, prev_vol) if prev_vol else 0

    # ------------------------------------------------------------------
    # Pipeline health score (0-100)
    # Weighted: 35% conversion, 25% velocity, 25% fallout, 15% volume trend
    # ------------------------------------------------------------------
    conversion_rate = _pct(last_funded, last_new_apps) if last_new_apps else 50
    fallout_rate = _pct(last_fallout, last_funded + last_fallout) if (last_funded + last_fallout) else 0
    velocity_score = max(0, min(100, 100 - ((avg_dtc or 45) - 30)))  # 30d = 100, 60d+ = 0

    conversion_component = min(conversion_rate, 100) * 0.35
    velocity_component = velocity_score * 0.25
    fallout_component = max(0, 100 - fallout_rate) * 0.25
    trend_component = min(100, max(0, 50 + mom_vol_change)) * 0.15

    health_score = round(conversion_component + velocity_component + fallout_component + trend_component)

    # ------------------------------------------------------------------
    # Bottleneck detection: stages with highest avg days vs SLA
    # ------------------------------------------------------------------
    stages_report: List[Dict[str, Any]] = []
    bottleneck_stage = None
    worst_sla_ratio = 0.0
    total_pipeline_count = 0
    total_pipeline_vol = 0.0
    total_aged = 0

    for row in stage_dist:
        stage_name = row[0]
        cnt = row[1] or 0
        vol = float(row[2] or 0)
        avg_days = round(float(row[3] or 0), 1)
        aged = row[4] or 0

        sla_target = STAGE_SLA_DAYS.get(stage_name, 7)
        sla_ratio = _safe_div(avg_days, sla_target, 0)
        past_sla = aged

        total_pipeline_count += cnt
        total_pipeline_vol += vol
        total_aged += aged

        stage_info = {
            "stage": stage_name,
            "count": cnt,
            "volume": vol,
            "avg_days_in_stage": avg_days,
            "sla_target_days": sla_target,
            "sla_ratio": round(sla_ratio, 2),
            "past_sla_count": past_sla,
        }
        stages_report.append(stage_info)

        if sla_ratio > worst_sla_ratio and cnt >= 2:
            worst_sla_ratio = sla_ratio
            bottleneck_stage = stage_name

    # ------------------------------------------------------------------
    # Funding projection: apply historical conversion rates to pipeline
    # ------------------------------------------------------------------
    projected_fundings = 0
    projected_volume = 0.0
    for stage_info in stages_report:
        stage_name = stage_info["stage"]
        conv_rate = DEFAULT_STAGE_CONVERSION.get(stage_name, 0.5)
        # Multiply through remaining stages to funding
        remaining_stages = [s for s in LOAN_STAGE_ORDER if LOAN_STAGE_ORDER.index(s) > LOAN_STAGE_ORDER.index(stage_name)] if stage_name in LOAN_STAGE_ORDER else []
        cumulative_rate = conv_rate
        for rs in remaining_stages:
            if rs != "FUNDED":
                cumulative_rate *= DEFAULT_STAGE_CONVERSION.get(rs, 0.9)

        proj_count = stage_info["count"] * cumulative_rate
        proj_vol = stage_info["volume"] * cumulative_rate
        projected_fundings += proj_count
        projected_volume += proj_vol

    projected_fundings = round(projected_fundings)
    projected_volume = round(projected_volume, 2)

    # ------------------------------------------------------------------
    # Action items
    # ------------------------------------------------------------------
    action_items: List[str] = []

    if bottleneck_stage and worst_sla_ratio > 1.5:
        bottleneck_info = next((s for s in stages_report if s["stage"] == bottleneck_stage), None)
        action_items.append(
            f"BOTTLENECK: {bottleneck_stage} averaging "
            f"{bottleneck_info['avg_days_in_stage']}d vs {bottleneck_info['sla_target_days']}d SLA "
            f"({bottleneck_info['count']} loans). Investigate process delays."
        )
        _insert_task(
            db, organization_id,
            title=f"Pipeline bottleneck: {bottleneck_stage}",
            description=action_items[-1],
            priority="high",
            due_days=3,
            gateway=gateway,
        )
        actions += 1

    if total_aged > 0:
        pct_aged = _pct(total_aged, total_pipeline_count)
        action_items.append(
            f"AGING: {total_aged} loans ({pct_aged}%) past SLA. "
            f"Review and escalate stale files."
        )
        if pct_aged > 25:
            _insert_task(
                db, organization_id,
                title=f"Pipeline aging alert: {total_aged} loans past SLA",
                description=(
                    f"{pct_aged}% of active pipeline is past SLA targets. "
                    f"Schedule pipeline scrub meeting with team."
                ),
                priority="high",
                due_days=2,
                gateway=gateway,
            )
            actions += 1

    if fallout_rate > 20:
        action_items.append(
            f"FALLOUT: {fallout_rate}% fallout rate last month. "
            f"Analyze denial reasons and improve pre-qualification."
        )

    if mom_vol_change < -15:
        action_items.append(
            f"DECLINE: Volume dropped {abs(mom_vol_change)}% month-over-month. "
            f"Review lead generation and conversion efforts."
        )

    # ------------------------------------------------------------------
    # Build structured report
    # ------------------------------------------------------------------
    report = {
        "report_type": "monthly_pipeline_review",
        "period": "last_calendar_month",
        "last_month": {
            "funded_count": last_funded,
            "funded_volume": last_vol,
            "fallout_count": last_fallout,
            "new_applications": last_new_apps,
            "avg_days_to_close": avg_dtc,
        },
        "month_over_month": {
            "funded_change_pct": mom_funded_change,
            "volume_change_pct": mom_vol_change,
            "prev_month_funded": prev_funded,
            "prev_month_volume": prev_vol,
        },
        "current_pipeline": {
            "total_count": total_pipeline_count,
            "total_volume": total_pipeline_vol,
            "stages": stages_report,
            "aged_past_sla": total_aged,
        },
        "health_score": health_score,
        "bottleneck": bottleneck_stage,
        "projection": {
            "next_month_funded_count": projected_fundings,
            "next_month_funded_volume": projected_volume,
        },
        "action_items": action_items,
    }

    summary = (
        f"Monthly review: Last month {last_funded} funded (${last_vol:,.0f}), "
        f"MoM {mom_vol_change:+.1f}%. Pipeline: {total_pipeline_count} loans "
        f"(${total_pipeline_vol:,.0f}), health {health_score}/100. "
        f"Projected next month: {projected_fundings} loans (${projected_volume:,.0f}). "
        f"Bottleneck: {bottleneck_stage or 'none'}. {len(action_items)} action items."
    )

    _insert_activity(db, organization_id, f"[Monthly Review] {summary}", "monthly_pipeline_review", report, gateway=gateway)
    actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Monthly pipeline review commit failed: {e}")

    return {"summary": summary, "actions_taken": actions, "notifications_sent": 0}


# ---------------------------------------------------------------------------
# 3. Conversion Funnel Analyzer
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="conversion_funnel_analyzer",
    description="Daily lead-to-close conversion funnel analysis",
    frequency=AgentFrequency.DAILY_6PM,
    max_runtime_seconds=90,
)
def conversion_funnel_analyzer(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Full funnel analysis: stage-to-stage conversion, drop-off detection,
    per-source and per-LO comparison, velocity tracking, and 7d vs 30d trends."""
    actions = 0

    # ------------------------------------------------------------------
    # Lead funnel (7-day and 30-day windows)
    # ------------------------------------------------------------------
    lead_funnel = db.execute(text("""
        SELECT
            -- 30-day counts
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 30 THEN 1 END) as new_30d,
            COUNT(CASE WHEN last_contact IS NOT NULL
                        AND created_at >= CURRENT_DATE - 30 THEN 1 END) as contacted_30d,
            COUNT(CASE WHEN stage IN ('Qualified','Application','Converted')
                        AND created_at >= CURRENT_DATE - 30 THEN 1 END) as qualified_30d,
            COUNT(CASE WHEN stage IN ('Application','Converted')
                        AND created_at >= CURRENT_DATE - 30 THEN 1 END) as application_30d,
            -- 7-day counts
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as new_7d,
            COUNT(CASE WHEN last_contact IS NOT NULL
                        AND created_at >= CURRENT_DATE - 7 THEN 1 END) as contacted_7d,
            COUNT(CASE WHEN stage IN ('Qualified','Application','Converted')
                        AND created_at >= CURRENT_DATE - 7 THEN 1 END) as qualified_7d,
            COUNT(CASE WHEN stage IN ('Application','Converted')
                        AND created_at >= CURRENT_DATE - 7 THEN 1 END) as application_7d
        FROM leads WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    # ------------------------------------------------------------------
    # Loan funnel stages (30-day and 7-day)
    # ------------------------------------------------------------------
    loan_funnel = db.execute(text("""
        SELECT
            -- 30d
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 30 THEN 1 END) as apps_30d,
            COUNT(CASE WHEN stage IN ('DISCLOSED','PROCESSING','SUBMITTED','UNDERWRITING',
                'UW_RECEIVED','CONDITIONAL_APPROVAL','APPROVED','SUSPENDED','CTC',
                'CLEAR_TO_CLOSE','CLOSING','DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 30 THEN 1 END) as disclosed_30d,
            COUNT(CASE WHEN stage IN ('PROCESSING','SUBMITTED','UNDERWRITING','UW_RECEIVED',
                'CONDITIONAL_APPROVAL','APPROVED','SUSPENDED','CTC','CLEAR_TO_CLOSE',
                'CLOSING','DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 30 THEN 1 END) as processing_30d,
            COUNT(CASE WHEN stage IN ('UNDERWRITING','UW_RECEIVED','CONDITIONAL_APPROVAL',
                'APPROVED','SUSPENDED','CTC','CLEAR_TO_CLOSE','CLOSING','DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 30 THEN 1 END) as uw_30d,
            COUNT(CASE WHEN stage IN ('APPROVED','CTC','CLEAR_TO_CLOSE','CLOSING',
                'DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 30 THEN 1 END) as approved_30d,
            COUNT(CASE WHEN stage IN ('CTC','CLEAR_TO_CLOSE','CLOSING','DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 30 THEN 1 END) as ctc_30d,
            COUNT(CASE WHEN stage = 'FUNDED'
                AND stage_changed_at >= CURRENT_DATE - 30 THEN 1 END) as funded_30d,
            -- 7d
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as apps_7d,
            COUNT(CASE WHEN stage IN ('DISCLOSED','PROCESSING','SUBMITTED','UNDERWRITING',
                'UW_RECEIVED','CONDITIONAL_APPROVAL','APPROVED','SUSPENDED','CTC',
                'CLEAR_TO_CLOSE','CLOSING','DOCS','DOCS_OUT','FUNDED')
                AND created_at >= CURRENT_DATE - 7 THEN 1 END) as disclosed_7d,
            COUNT(CASE WHEN stage = 'FUNDED'
                AND stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as funded_7d
        FROM loans WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchall()[0]

    # Build funnel stages with conversion rates
    funnel_30d = [
        ("New Lead", lead_funnel[0] or 0),
        ("Contacted", lead_funnel[1] or 0),
        ("Qualified", lead_funnel[2] or 0),
        ("Application", loan_funnel[0] or 0),
        ("Disclosed", loan_funnel[1] or 0),
        ("Processing", loan_funnel[2] or 0),
        ("Underwriting", loan_funnel[3] or 0),
        ("Approved", loan_funnel[4] or 0),
        ("CTC", loan_funnel[5] or 0),
        ("Funded", loan_funnel[6] or 0),
    ]

    funnel_7d = [
        ("New Lead", lead_funnel[4] or 0),
        ("Contacted", lead_funnel[5] or 0),
        ("Qualified", lead_funnel[6] or 0),
        ("Application", loan_funnel[7] or 0),
        ("Disclosed", loan_funnel[8] or 0),
        ("Funded", loan_funnel[9] or 0),
    ]

    # Stage-to-stage conversion and drop-off
    funnel_analysis: List[Dict[str, Any]] = []
    biggest_leak_stage = None
    biggest_leak_dropoff = 0.0

    for i, (stage_name, count) in enumerate(funnel_30d):
        prev_count = funnel_30d[i - 1][1] if i > 0 else count
        conv_rate = _pct(count, prev_count) if i > 0 else 100.0
        dropoff = round(100 - conv_rate, 1) if i > 0 else 0.0

        funnel_analysis.append({
            "stage": stage_name,
            "count_30d": count,
            "conversion_from_prev": conv_rate,
            "dropoff_pct": dropoff,
        })

        if i > 0 and dropoff > biggest_leak_dropoff and prev_count >= 5:
            biggest_leak_dropoff = dropoff
            biggest_leak_stage = f"{funnel_30d[i-1][0]} -> {stage_name}"

    # ------------------------------------------------------------------
    # Funnel by lead source (top 10 sources)
    # ------------------------------------------------------------------
    source_funnel = db.execute(text("""
        SELECT
            COALESCE(ld.source, 'Unknown') as src,
            COUNT(DISTINCT ld.id) as total_leads,
            COUNT(DISTINCT CASE WHEN ld.last_contact IS NOT NULL THEN ld.id END) as contacted,
            COUNT(DISTINCT CASE WHEN ld.stage IN ('Qualified','Application','Converted') THEN ld.id END) as qualified,
            COUNT(DISTINCT CASE WHEN ld.loan_number IS NOT NULL THEN ld.id END) as to_loan,
            COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) as funded
        FROM leads ld
        LEFT JOIN loans lo ON lo.loan_number = ld.loan_number AND lo.organization_id = ld.organization_id
        WHERE ld.organization_id = :org_id
          AND ld.created_at >= CURRENT_DATE - 90
        GROUP BY ld.source
        HAVING COUNT(DISTINCT ld.id) >= 3
        ORDER BY COUNT(DISTINCT ld.id) DESC
        LIMIT 10
    """), {"org_id": organization_id}).fetchall()

    source_analysis: List[Dict[str, Any]] = []
    best_source = None
    best_source_conv = 0.0
    worst_source = None
    worst_source_conv = 100.0

    for row in source_funnel:
        src = row[0]
        total = row[1] or 0
        contacted = row[2] or 0
        qualified = row[3] or 0
        to_loan = row[4] or 0
        funded = row[5] or 0

        contact_rate = _pct(contacted, total)
        qualify_rate = _pct(qualified, total)
        fund_rate = _pct(funded, total)

        source_analysis.append({
            "source": src,
            "total_leads": total,
            "contacted": contacted,
            "contact_rate": contact_rate,
            "qualified": qualified,
            "qualify_rate": qualify_rate,
            "to_loan": to_loan,
            "funded": funded,
            "fund_rate": fund_rate,
        })

        if total >= 5:
            if fund_rate > best_source_conv:
                best_source_conv = fund_rate
                best_source = src
            if fund_rate < worst_source_conv:
                worst_source_conv = fund_rate
                worst_source = src

    # ------------------------------------------------------------------
    # Funnel by LO (top 15)
    # ------------------------------------------------------------------
    lo_funnel = db.execute(text("""
        SELECT
            u.id as lo_id,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name,
            COUNT(DISTINCT ld.id) as assigned_leads,
            COUNT(DISTINCT CASE WHEN ld.last_contact IS NOT NULL THEN ld.id END) as contacted,
            COUNT(DISTINCT CASE WHEN ld.loan_number IS NOT NULL THEN ld.id END) as to_loan,
            COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) as funded
        FROM users u
        LEFT JOIN leads ld ON ld.owner_id = u.id AND ld.organization_id = :org_id
            AND ld.created_at >= CURRENT_DATE - 90
        LEFT JOIN loans lo ON lo.loan_number = ld.loan_number AND lo.organization_id = :org_id
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'branch_manager')
        GROUP BY u.id, u.first_name, u.last_name
        HAVING COUNT(DISTINCT ld.id) >= 1
        ORDER BY COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) DESC
        LIMIT 15
    """), {"org_id": organization_id}).fetchall()

    lo_analysis: List[Dict[str, Any]] = []
    for row in lo_funnel:
        lo_id = row[0]
        lo_name = row[1]
        assigned = row[2] or 0
        contacted = row[3] or 0
        to_loan = row[4] or 0
        funded = row[5] or 0

        contact_rate = _pct(contacted, assigned)
        conv_rate = _pct(funded, assigned)

        lo_analysis.append({
            "lo_id": lo_id,
            "lo_name": lo_name,
            "assigned_leads": assigned,
            "contacted": contacted,
            "contact_rate": contact_rate,
            "to_loan": to_loan,
            "funded": funded,
            "conversion_rate": conv_rate,
        })

    # ------------------------------------------------------------------
    # Funnel velocity: avg time between stages
    # ------------------------------------------------------------------
    velocity = db.execute(text("""
        SELECT
            AVG(CASE WHEN application_date IS NOT NULL AND created_at IS NOT NULL
                THEN EXTRACT(DAY FROM (application_date - created_at)) END) as app_to_disc,
            AVG(CASE WHEN application_date IS NOT NULL AND stage_changed_at IS NOT NULL
                     AND stage = 'FUNDED'
                THEN EXTRACT(DAY FROM (stage_changed_at - application_date)) END) as app_to_funded,
            AVG(CASE WHEN closing_date IS NOT NULL AND application_date IS NOT NULL
                THEN EXTRACT(DAY FROM (closing_date - application_date)) END) as app_to_close
        FROM loans
        WHERE organization_id = :org_id
          AND created_at >= CURRENT_DATE - 90
    """), {"org_id": organization_id}).fetchone()

    velocity_data = {
        "avg_days_created_to_app": round(float(velocity[0]), 1) if velocity[0] else None,
        "avg_days_app_to_funded": round(float(velocity[1]), 1) if velocity[1] else None,
        "avg_days_app_to_close": round(float(velocity[2]), 1) if velocity[2] else None,
    }

    # ------------------------------------------------------------------
    # Create tasks for high drop-off stages
    # ------------------------------------------------------------------
    for stage_info in funnel_analysis:
        if stage_info["dropoff_pct"] > 30 and stage_info["count_30d"] > 0:
            prev_idx = next(
                (i for i, s in enumerate(funnel_analysis) if s["stage"] == stage_info["stage"]),
                0
            )
            if prev_idx > 0:
                from_stage = funnel_analysis[prev_idx - 1]["stage"]
                _insert_task(
                    db, organization_id,
                    title=f"Funnel leak: {stage_info['dropoff_pct']}% drop at {from_stage} -> {stage_info['stage']}",
                    description=(
                        f"30-day funnel shows {stage_info['dropoff_pct']}% drop-off "
                        f"between {from_stage} ({funnel_analysis[prev_idx - 1]['count_30d']}) "
                        f"and {stage_info['stage']} ({stage_info['count_30d']}). "
                        f"Investigate causes and implement process improvements."
                    ),
                    priority="high",
                    due_days=3,
                    gateway=gateway,
                )
                actions += 1

    # ------------------------------------------------------------------
    # Build report
    # ------------------------------------------------------------------
    report = {
        "report_type": "conversion_funnel",
        "funnel_30d": funnel_analysis,
        "funnel_7d": [{"stage": s, "count": c} for s, c in funnel_7d],
        "biggest_leak": {
            "transition": biggest_leak_stage,
            "dropoff_pct": biggest_leak_dropoff,
        },
        "by_source": source_analysis,
        "best_source": {"source": best_source, "fund_rate": best_source_conv},
        "worst_source": {"source": worst_source, "fund_rate": worst_source_conv},
        "by_lo": lo_analysis,
        "velocity": velocity_data,
    }

    new_30d = funnel_30d[0][1]
    funded_30d_count = funnel_30d[-1][1]
    overall_conv = _pct(funded_30d_count, new_30d)

    summary = (
        f"30d funnel: {new_30d} leads -> {funded_30d_count} funded ({overall_conv}% overall). "
        f"Biggest leak: {biggest_leak_stage or 'none'} ({biggest_leak_dropoff}% drop). "
        f"Best source: {best_source or 'N/A'} ({best_source_conv}%), "
        f"worst: {worst_source or 'N/A'} ({worst_source_conv}%). "
        f"Velocity: {velocity_data['avg_days_app_to_funded'] or 'N/A'}d app-to-fund."
    )

    _insert_activity(db, organization_id, f"[Funnel] {summary}", "conversion_funnel", report, gateway=gateway)
    actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Conversion funnel commit failed: {e}")

    return {"summary": summary, "actions_taken": actions, "notifications_sent": 0}


# ---------------------------------------------------------------------------
# 4. Marketing ROI Calculator
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="marketing_roi_calculator",
    description="Calculate ROI per lead source for marketing spend optimization",
    frequency=AgentFrequency.WEEKLY_FRIDAY,
    max_runtime_seconds=90,
)
def marketing_roi_calculator(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Marketing ROI analysis: cost-per-acquisition, time-to-conversion by source,
    revenue per source, contact rates, trend detection (rising/dying sources),
    and budget reallocation recommendations."""
    actions = 0

    # ------------------------------------------------------------------
    # Per-source metrics (90-day window) with 4-week trend
    # ------------------------------------------------------------------
    sources = db.execute(text("""
        SELECT
            COALESCE(ld.source, 'Unknown') as src,
            -- All-time (90d)
            COUNT(DISTINCT ld.id) as total_leads,
            COUNT(DISTINCT CASE WHEN ld.last_contact IS NOT NULL THEN ld.id END) as contacted,
            COUNT(DISTINCT CASE WHEN ld.stage IN ('Qualified','Application','Converted') THEN ld.id END) as qualified,
            COUNT(DISTINCT CASE WHEN ld.loan_number IS NOT NULL THEN ld.id END) as to_loan,
            COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) as funded,
            COALESCE(SUM(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.amount END), 0) as funded_vol,
            -- Avg time from lead to funding
            AVG(CASE WHEN lo.stage = 'FUNDED' AND lo.stage_changed_at IS NOT NULL
                THEN EXTRACT(DAY FROM (lo.stage_changed_at - ld.created_at)) END) as avg_days_to_fund,
            -- Week 1 (this week leads)
            COUNT(DISTINCT CASE WHEN ld.created_at >= CURRENT_DATE - 7 THEN ld.id END) as leads_w1,
            -- Week 2
            COUNT(DISTINCT CASE WHEN ld.created_at >= CURRENT_DATE - 14
                                 AND ld.created_at < CURRENT_DATE - 7 THEN ld.id END) as leads_w2,
            -- Week 3
            COUNT(DISTINCT CASE WHEN ld.created_at >= CURRENT_DATE - 21
                                 AND ld.created_at < CURRENT_DATE - 14 THEN ld.id END) as leads_w3,
            -- Week 4
            COUNT(DISTINCT CASE WHEN ld.created_at >= CURRENT_DATE - 28
                                 AND ld.created_at < CURRENT_DATE - 21 THEN ld.id END) as leads_w4
        FROM leads ld
        LEFT JOIN loans lo ON lo.loan_number = ld.loan_number AND lo.organization_id = ld.organization_id
        WHERE ld.organization_id = :org_id
          AND ld.created_at >= CURRENT_DATE - 90
        GROUP BY ld.source
        ORDER BY COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) DESC,
                 COUNT(DISTINCT ld.id) DESC
    """), {"org_id": organization_id}).fetchall()

    source_reports: List[Dict[str, Any]] = []
    rising_sources: List[str] = []
    dying_sources: List[str] = []
    best_efficient: Optional[Dict[str, Any]] = None
    worst_efficient: Optional[Dict[str, Any]] = None
    best_eff_rate = 0.0
    worst_eff_rate = 100.0

    for row in sources:
        src = row[0]
        total = row[1] or 0
        contacted = row[2] or 0
        qualified = row[3] or 0
        to_loan = row[4] or 0
        funded = row[5] or 0
        funded_vol = float(row[6] or 0)
        avg_days = round(float(row[7]), 1) if row[7] else None
        w1 = row[8] or 0
        w2 = row[9] or 0
        w3 = row[10] or 0
        w4 = row[11] or 0

        contact_rate = _pct(contacted, total)
        conv_rate = _pct(funded, total)
        leads_per_fund = round(_safe_div(total, funded, 0), 1)  # cost-per-acquisition proxy

        # 4-week trend: compare last 2 weeks avg vs previous 2 weeks avg
        recent_avg = (w1 + w2) / 2
        older_avg = (w3 + w4) / 2
        trend_pct = _pct(recent_avg - older_avg, older_avg) if older_avg > 0 else 0

        # Classify trend
        trend = "stable"
        if trend_pct > 25 and total >= 5:
            trend = "rising"
            rising_sources.append(src)
        elif trend_pct < -25 and total >= 5:
            trend = "dying"
            dying_sources.append(src)

        source_report = {
            "source": src,
            "total_leads": total,
            "contacted": contacted,
            "contact_rate": contact_rate,
            "qualified": qualified,
            "to_loan": to_loan,
            "funded": funded,
            "funded_volume": funded_vol,
            "conversion_rate": conv_rate,
            "leads_per_funded": leads_per_fund,
            "avg_days_to_fund": avg_days,
            "weekly_trend": [w4, w3, w2, w1],
            "trend_pct": trend_pct,
            "trend": trend,
        }
        source_reports.append(source_report)

        # Efficiency ranking (require meaningful volume: 10+ leads)
        if total >= 10:
            if conv_rate > best_eff_rate:
                best_eff_rate = conv_rate
                best_efficient = {"source": src, "conversion_rate": conv_rate, "total_leads": total}
            if conv_rate < worst_eff_rate:
                worst_eff_rate = conv_rate
                worst_efficient = {"source": src, "conversion_rate": conv_rate, "total_leads": total}

    # ------------------------------------------------------------------
    # Ranked by efficiency (conversion rate, minimum 10 leads)
    # ------------------------------------------------------------------
    efficient_sources = sorted(
        [s for s in source_reports if s["total_leads"] >= 10],
        key=lambda x: x["conversion_rate"],
        reverse=True,
    )

    # ------------------------------------------------------------------
    # Budget reallocation tasks
    # ------------------------------------------------------------------
    if worst_efficient and best_efficient and worst_efficient["source"] != best_efficient["source"]:
        _insert_task(
            db, organization_id,
            title="Marketing: reallocate budget from underperforming source",
            description=(
                f"Consider shifting budget from '{worst_efficient['source']}' "
                f"({worst_efficient['conversion_rate']}% conv, {worst_efficient['total_leads']} leads) "
                f"to '{best_efficient['source']}' "
                f"({best_efficient['conversion_rate']}% conv, {best_efficient['total_leads']} leads). "
                f"Potential to improve overall ROI significantly."
            ),
            priority="medium",
            due_days=5,
            gateway=gateway,
        )
        actions += 1

    if dying_sources:
        _insert_task(
            db, organization_id,
            title=f"Marketing: declining sources detected ({len(dying_sources)})",
            description=(
                f"The following sources show declining lead volume over 4 weeks: "
                f"{', '.join(dying_sources)}. "
                f"Evaluate whether to invest more or redirect spend."
            ),
            priority="medium",
            due_days=5,
            gateway=gateway,
        )
        actions += 1

    if rising_sources:
        _insert_task(
            db, organization_id,
            title=f"Marketing: capitalize on rising sources ({len(rising_sources)})",
            description=(
                f"The following sources are gaining momentum: "
                f"{', '.join(rising_sources)}. "
                f"Consider increasing investment while traction is strong."
            ),
            priority="medium",
            due_days=5,
            gateway=gateway,
        )
        actions += 1

    # ------------------------------------------------------------------
    # Build report
    # ------------------------------------------------------------------
    total_leads_all = sum(s["total_leads"] for s in source_reports)
    total_funded_all = sum(s["funded"] for s in source_reports)
    total_vol_all = sum(s["funded_volume"] for s in source_reports)

    report = {
        "report_type": "marketing_roi",
        "period": "90_days",
        "totals": {
            "total_leads": total_leads_all,
            "total_funded": total_funded_all,
            "total_funded_volume": total_vol_all,
            "overall_conversion": _pct(total_funded_all, total_leads_all),
        },
        "sources": source_reports,
        "efficiency_ranking": [
            {"rank": i + 1, "source": s["source"], "conversion_rate": s["conversion_rate"]}
            for i, s in enumerate(efficient_sources[:10])
        ],
        "best_efficient": best_efficient,
        "worst_efficient": worst_efficient,
        "rising_sources": rising_sources,
        "dying_sources": dying_sources,
    }

    top_sources_summary = "; ".join(
        f"{s['source']}: {s['total_leads']}L/{s['funded']}F ({s['conversion_rate']}%)"
        for s in source_reports[:5]
    )

    summary = (
        f"90d ROI: {total_leads_all} leads, {total_funded_all} funded "
        f"(${total_vol_all:,.0f}). "
        f"Best: {best_efficient['source'] if best_efficient else 'N/A'} "
        f"({best_eff_rate}%), "
        f"worst: {worst_efficient['source'] if worst_efficient else 'N/A'} "
        f"({worst_eff_rate}%). "
        f"Rising: {', '.join(rising_sources) or 'none'}. "
        f"Dying: {', '.join(dying_sources) or 'none'}. "
        f"Top: {top_sources_summary}"
    )

    _insert_activity(db, organization_id, f"[Marketing ROI] {summary}", "marketing_roi", report, gateway=gateway)
    actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Marketing ROI commit failed: {e}")

    return {"summary": summary, "actions_taken": actions, "notifications_sent": 0}


# ---------------------------------------------------------------------------
# 5. Team Leaderboard
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="team_leaderboard",
    description="Generate weekly team rankings by production volume",
    frequency=AgentFrequency.WEEKLY_FRIDAY,
    max_runtime_seconds=60,
)
def team_leaderboard(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Multi-dimensional leaderboard: composite scoring, streak tracking,
    per-LO strengths, coaching/recognition task generation."""
    actions = 0
    notifications = 0

    # ------------------------------------------------------------------
    # Per-LO metrics for this week + last week (for streak/improvement)
    # ------------------------------------------------------------------
    lo_metrics = db.execute(text("""
        SELECT
            u.id as lo_id,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name,
            -- Funded this week
            COUNT(CASE WHEN l.stage = 'FUNDED'
                        AND l.stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as funded_count,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                              AND l.stage_changed_at >= CURRENT_DATE - 7
                         THEN l.amount END), 0) as funded_vol,
            -- Active pipeline
            COUNT(CASE WHEN l.stage NOT IN (
                'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
            ) THEN 1 END) as pipeline_count,
            COALESCE(SUM(CASE WHEN l.stage NOT IN (
                'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
            ) THEN l.amount END), 0) as pipeline_vol,
            -- Pull-through (this month for meaningful sample)
            COUNT(CASE WHEN l.stage = 'FUNDED'
                        AND l.stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as month_funded,
            COUNT(CASE WHEN l.stage IN ('CANCELLED','DENIED','WITHDRAWN')
                        AND l.stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as month_fallout,
            -- Avg days to close (this month)
            AVG(CASE WHEN l.stage = 'FUNDED'
                      AND l.stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE)
                      AND l.application_date IS NOT NULL
                 THEN EXTRACT(DAY FROM (l.stage_changed_at - l.application_date)) END) as avg_dtc,
            -- Funded last week (for improvement tracking)
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                              AND l.stage_changed_at >= CURRENT_DATE - 14
                              AND l.stage_changed_at < CURRENT_DATE - 7
                         THEN l.amount END), 0) as funded_vol_last_week,
            -- Contact activity this week
            (SELECT COUNT(*) FROM activities a
             WHERE a.user_id = u.id AND a.organization_id = :org_id
               AND a.created_at >= CURRENT_DATE - 7) as activity_count
        FROM users u
        LEFT JOIN loans l ON l.loan_officer_id = u.id AND l.organization_id = :org_id
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'branch_manager')
        GROUP BY u.id, u.first_name, u.last_name
    """), {"org_id": organization_id}).fetchall()

    if not lo_metrics:
        return {"summary": "No active LOs found", "actions_taken": 0, "notifications_sent": 0}

    # ------------------------------------------------------------------
    # Fetch last week's rankings from last activity (for streak/improvement)
    # ------------------------------------------------------------------
    last_rankings = db.execute(text("""
        SELECT user_metadata
        FROM activities
        WHERE organization_id = :org_id
          AND type = 'System'
          AND content LIKE '%[Leaderboard]%'
          AND created_at < CURRENT_DATE
        ORDER BY created_at DESC
        LIMIT 1
    """), {"org_id": organization_id}).fetchone()

    prev_rankings: Dict[int, int] = {}  # lo_id -> previous rank
    prev_top_performer_id: Optional[int] = None
    prev_streak: Dict[int, int] = {}  # lo_id -> streak count

    if last_rankings and last_rankings[0]:
        try:
            prev_data = json.loads(last_rankings[0]) if isinstance(last_rankings[0], str) else last_rankings[0]
            for entry in prev_data.get("rankings", []):
                prev_rankings[entry.get("lo_id")] = entry.get("rank", 99)
                if entry.get("rank") == 1:
                    prev_top_performer_id = entry.get("lo_id")
                prev_streak[entry.get("lo_id")] = entry.get("streak", 0)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    # ------------------------------------------------------------------
    # Calculate composite scores and build rankings
    # ------------------------------------------------------------------
    # Find maximums for normalization
    max_funded_vol = max((float(r[3] or 0) for r in lo_metrics), default=1) or 1
    max_pipeline_vol = max((float(r[5] or 0) for r in lo_metrics), default=1) or 1
    max_dtc = max((float(r[8] or 60) for r in lo_metrics if r[8]), default=60) or 60

    lo_scores: List[Dict[str, Any]] = []

    for row in lo_metrics:
        lo_id = row[0]
        lo_name = row[1]
        funded_count = row[2] or 0
        funded_vol = float(row[3] or 0)
        pipeline_count = row[4] or 0
        pipeline_vol = float(row[5] or 0)
        month_funded = row[6] or 0
        month_fallout = row[7] or 0
        avg_dtc = float(row[8]) if row[8] else None
        funded_vol_lw = float(row[9] or 0)
        activity_count = row[10] or 0

        pull_through = _pct(month_funded, month_funded + month_fallout)

        # Normalized scores (0-100)
        vol_score = _safe_div(funded_vol, max_funded_vol) * 100
        pt_score = pull_through  # already 0-100
        pipeline_score = _safe_div(pipeline_vol, max_pipeline_vol) * 100
        speed_score = max(0, 100 - _safe_div((avg_dtc or 45), max_dtc) * 100) if avg_dtc else 50

        # Composite: 40% volume, 25% pull-through, 20% pipeline, 15% speed
        composite = round(
            vol_score * 0.40
            + pt_score * 0.25
            + pipeline_score * 0.20
            + speed_score * 0.15,
            1
        )

        # Determine strength
        strengths: List[str] = []
        if avg_dtc and avg_dtc <= 30:
            strengths.append("Fastest closer")
        if pull_through >= 85:
            strengths.append("Best conversion")
        if pipeline_vol >= max_pipeline_vol * 0.8 and max_pipeline_vol > 0:
            strengths.append("Largest pipeline")
        if activity_count >= 50:
            strengths.append("Most active")
        if funded_count >= 3:
            strengths.append("High volume")

        lo_scores.append({
            "lo_id": lo_id,
            "lo_name": lo_name,
            "funded_count": funded_count,
            "funded_volume": funded_vol,
            "pipeline_count": pipeline_count,
            "pipeline_volume": pipeline_vol,
            "pull_through_rate": pull_through,
            "avg_days_to_close": round(avg_dtc, 1) if avg_dtc else None,
            "activity_count": activity_count,
            "composite_score": composite,
            "component_scores": {
                "volume": round(vol_score, 1),
                "pull_through": round(pt_score, 1),
                "pipeline": round(pipeline_score, 1),
                "speed": round(speed_score, 1),
            },
            "strengths": strengths,
            "funded_vol_last_week": funded_vol_lw,
        })

    # Sort by composite score
    lo_scores.sort(key=lambda x: x["composite_score"], reverse=True)

    # Assign ranks, streaks, improvement
    most_improved_name = ""
    most_improved_jump = 0

    for rank, entry in enumerate(lo_scores, 1):
        lo_id = entry["lo_id"]
        entry["rank"] = rank

        # Streak tracking
        if rank == 1 and lo_id == prev_top_performer_id:
            entry["streak"] = prev_streak.get(lo_id, 0) + 1
        elif rank == 1:
            entry["streak"] = 1
        else:
            entry["streak"] = 0

        # Rank improvement
        prev_rank = prev_rankings.get(lo_id, rank)
        entry["prev_rank"] = prev_rank
        entry["rank_change"] = prev_rank - rank  # positive = improved

        if entry["rank_change"] > most_improved_jump:
            most_improved_jump = entry["rank_change"]
            most_improved_name = entry["lo_name"]

    # ------------------------------------------------------------------
    # Coaching and recognition tasks
    # ------------------------------------------------------------------
    num_los = len(lo_scores)
    top_quartile_cutoff = max(1, num_los // 4)
    bottom_quartile_cutoff = num_los - top_quartile_cutoff

    for entry in lo_scores:
        rank = entry["rank"]

        if rank <= top_quartile_cutoff and entry["funded_volume"] > 0:
            # Recognition for top quartile
            _insert_task(
                db, organization_id,
                title=f"Recognize: {entry['lo_name']} ranked #{rank}",
                description=(
                    f"{entry['lo_name']} ranked #{rank} with composite score "
                    f"{entry['composite_score']}: ${entry['funded_volume']:,.0f} funded, "
                    f"{entry['pull_through_rate']}% pull-through, "
                    f"pipeline ${entry['pipeline_volume']:,.0f}. "
                    f"Strengths: {', '.join(entry['strengths']) or 'consistent performer'}."
                    f"{' Streak: ' + str(entry['streak']) + ' weeks at #1!' if entry.get('streak', 0) > 1 else ''}"
                ),
                priority="low",
                assigned_to_id=entry["lo_id"],
                due_days=1,
                gateway=gateway,
            )
            actions += 1
            notifications += 1

        elif rank > bottom_quartile_cutoff and num_los >= 4:
            # Coaching for bottom quartile
            weak_areas: List[str] = []
            scores = entry["component_scores"]
            if scores["volume"] < 25:
                weak_areas.append("funded volume")
            if scores["pull_through"] < 50:
                weak_areas.append("pull-through rate")
            if scores["pipeline"] < 25:
                weak_areas.append("pipeline building")
            if scores["speed"] < 30:
                weak_areas.append("closing speed")

            _insert_task(
                db, organization_id,
                title=f"Coaching: {entry['lo_name']} (rank #{rank}/{num_los})",
                description=(
                    f"{entry['lo_name']} ranked #{rank}/{num_los} (score {entry['composite_score']}). "
                    f"Focus areas: {', '.join(weak_areas) or 'overall performance'}. "
                    f"Current: ${entry['funded_volume']:,.0f} funded, "
                    f"{entry['pipeline_count']} in pipeline, "
                    f"{entry['activity_count']} activities this week."
                ),
                priority="medium",
                due_days=3,
                gateway=gateway,
            )
            actions += 1

    # ------------------------------------------------------------------
    # Build report
    # ------------------------------------------------------------------
    top_3 = lo_scores[:3]
    top_performer = lo_scores[0] if lo_scores else None

    report = {
        "report_type": "team_leaderboard",
        "period": "current_week",
        "scoring_weights": {
            "funded_volume": 0.40,
            "pull_through_rate": 0.25,
            "pipeline_volume": 0.20,
            "closing_speed": 0.15,
        },
        "rankings": lo_scores,
        "top_performer": {
            "lo_id": top_performer["lo_id"],
            "lo_name": top_performer["lo_name"],
            "composite_score": top_performer["composite_score"],
            "streak": top_performer.get("streak", 0),
        } if top_performer else None,
        "most_improved": {
            "lo_name": most_improved_name,
            "rank_jump": most_improved_jump,
        } if most_improved_jump > 0 else None,
        "team_size": num_los,
    }

    ranking_lines = [
        f"#{e['rank']} {e['lo_name']} ({e['composite_score']}pts, ${e['funded_volume']:,.0f})"
        for e in top_3
    ]
    streak_note = ""
    if top_performer and top_performer.get("streak", 0) > 1:
        streak_note = f" {top_performer['lo_name']} {top_performer['streak']}-week streak!"

    summary = (
        f"Leaderboard ({num_los} LOs): {'; '.join(ranking_lines)}. "
        f"Most improved: {most_improved_name or 'N/A'} (+{most_improved_jump} ranks). "
        f"{streak_note}"
    ).strip()

    _insert_activity(db, organization_id, f"[Leaderboard] {summary}", "team_leaderboard", report, gateway=gateway)
    actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Team leaderboard commit failed: {e}")

    return {"summary": summary, "actions_taken": actions, "notifications_sent": notifications}
