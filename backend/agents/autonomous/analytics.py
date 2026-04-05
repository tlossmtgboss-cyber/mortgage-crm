"""
Analytics Agents

Periodic analytics and reporting autonomous agents:
1. weekly_production_report — Weekly Monday, org-wide production summary
2. monthly_pipeline_review — 1st of month, month-end pipeline snapshot
3. conversion_funnel_analyzer — Daily, analyze lead-to-close conversion funnel
4. marketing_roi_calculator — Weekly Friday, ROI per lead source
5. team_leaderboard — Weekly Friday, generate team rankings
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


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
) -> Dict[str, Any]:
    """Capture last week's production metrics."""

    stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN l.created_at >= CURRENT_DATE - 7 THEN 1 END) as new_apps,
            COUNT(CASE WHEN l.stage = 'FUNDED' AND l.stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as funded,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' AND l.stage_changed_at >= CURRENT_DATE - 7 THEN l.amount END), 0) as funded_volume,
            COUNT(CASE WHEN l.stage IN ('DENIED','CANCELLED','WITHDRAWN') AND l.stage_changed_at >= CURRENT_DATE - 7 THEN 1 END) as fallout,
            COUNT(*) FILTER (WHERE l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')) as active_pipeline
        FROM loans l
        WHERE l.organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    lead_stats = db.execute(text("""
        SELECT COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as new_leads,
               COUNT(*) FILTER (WHERE stage NOT IN ('Closed','Dead','Disqualified')) as active_leads
        FROM leads WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    summary = (
        f"Weekly production: {stats[1]} funded (${float(stats[2] or 0):,.0f}), "
        f"{stats[0]} new apps, {stats[3]} fallout, {stats[4]} active pipeline, "
        f"{lead_stats[0]} new leads, {lead_stats[1]} active leads"
    )

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": f"[Weekly Report] {summary}", "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Weekly production report commit failed: {e}")

    return {"summary": summary, "actions_taken": 1, "notifications_sent": 0}


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
) -> Dict[str, Any]:
    """Capture month-end pipeline state for historical comparison."""

    # Stage distribution
    stage_dist = db.execute(text("""
        SELECT stage, COUNT(*) as cnt, COALESCE(SUM(amount), 0) as vol
        FROM loans
        WHERE organization_id = :org_id
          AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
        GROUP BY stage ORDER BY cnt DESC
    """), {"org_id": organization_id}).fetchall()

    stages = "; ".join(f"{r[0]}: {r[1]} (${float(r[2]):,.0f})" for r in stage_dist)

    # Last month funded
    last_month = db.execute(text("""
        SELECT COUNT(*), COALESCE(SUM(amount), 0)
        FROM loans
        WHERE organization_id = :org_id AND stage = 'FUNDED'
          AND stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
          AND stage_changed_at < DATE_TRUNC('month', CURRENT_DATE)
    """), {"org_id": organization_id}).fetchone()

    summary = (
        f"Monthly review: Last month funded {last_month[0]} loans (${float(last_month[1]):,.0f}). "
        f"Current pipeline: {stages}"
    )

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": f"[Monthly Review] {summary}", "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Monthly pipeline review commit failed: {e}")

    return {"summary": summary, "actions_taken": 1, "notifications_sent": 0}


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
) -> Dict[str, Any]:
    """Analyze conversion rates at each stage of the funnel."""
    actions = 0

    funnel = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM leads WHERE organization_id = :org_id AND created_at >= CURRENT_DATE - 30) as new_leads_30d,
            (SELECT COUNT(*) FROM leads WHERE organization_id = :org_id AND last_contact IS NOT NULL AND created_at >= CURRENT_DATE - 30) as contacted_30d,
            (SELECT COUNT(*) FROM leads WHERE organization_id = :org_id AND stage IN ('Qualified','Application') AND created_at >= CURRENT_DATE - 30) as qualified_30d,
            (SELECT COUNT(*) FROM loans WHERE organization_id = :org_id AND created_at >= CURRENT_DATE - 30) as applications_30d,
            (SELECT COUNT(*) FROM loans WHERE organization_id = :org_id AND stage IN ('APPROVED','CTC','CLEAR_TO_CLOSE','DOCS','DOCS_OUT','CLOSING') AND created_at >= CURRENT_DATE - 30) as approved_30d,
            (SELECT COUNT(*) FROM loans WHERE organization_id = :org_id AND stage = 'FUNDED' AND stage_changed_at >= CURRENT_DATE - 30) as funded_30d
    """), {"org_id": organization_id}).fetchone()

    new_leads = funnel[0] or 0
    contacted = funnel[1] or 0
    qualified = funnel[2] or 0
    apps = funnel[3] or 0
    approved = funnel[4] or 0
    funded = funnel[5] or 0

    # Detect bottlenecks (>50% drop at any stage)
    if new_leads > 5:
        contact_rate = (contacted / new_leads * 100) if new_leads else 0
        if contact_rate < 50:
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, due_date,
                                   created_at, organization_id)
                VALUES ('Funnel bottleneck: Low contact rate', :desc,
                        'high', 'pending', CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
            """), {
                "desc": f"Only {contact_rate:.0f}% of new leads contacted in 30 days ({contacted}/{new_leads}). Review speed-to-lead and assignment.",
                "org_id": organization_id,
            })
            actions += 1

    summary = (
        f"30d funnel: {new_leads} leads -> {contacted} contacted -> {qualified} qualified -> "
        f"{apps} apps -> {approved} approved -> {funded} funded"
    )

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": f"[Funnel] {summary}", "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Conversion funnel commit failed: {e}")

    return {"summary": summary, "actions_taken": actions + 1, "notifications_sent": 0}


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
) -> Dict[str, Any]:
    """Analyze lead source performance and funded-per-source metrics."""

    sources = db.execute(text("""
        SELECT
            COALESCE(ld.source, 'Unknown') as source,
            COUNT(DISTINCT ld.id) as total_leads,
            COUNT(DISTINCT CASE WHEN ld.stage IN ('Qualified','Application','Converted') THEN ld.id END) as qualified,
            COUNT(DISTINCT l.id) as loans_created,
            COUNT(DISTINCT CASE WHEN l.stage = 'FUNDED' THEN l.id END) as funded,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' THEN l.amount END), 0) as funded_volume
        FROM leads ld
        LEFT JOIN loans l ON l.loan_number LIKE 'APP-' || LPAD(ld.id::text, 6, '0')
        WHERE ld.organization_id = :org_id
          AND ld.created_at >= CURRENT_DATE - 90
        GROUP BY ld.source
        ORDER BY funded_volume DESC
    """), {"org_id": organization_id}).fetchall()

    source_lines = []
    for s in sources[:10]:
        conv = (s[4] / s[1] * 100) if s[1] else 0
        source_lines.append(f"{s[0]}: {s[1]} leads, {s[4]} funded (${float(s[5]):,.0f}), {conv:.1f}% conv")

    summary = f"90d source ROI: " + "; ".join(source_lines[:5]) if source_lines else "No lead source data"

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": f"[Marketing ROI] {summary}", "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Marketing ROI commit failed: {e}")

    return {"summary": summary, "actions_taken": 1, "notifications_sent": 0}


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
) -> Dict[str, Any]:
    """Rank LOs by funded volume this month."""

    rankings = db.execute(text("""
        SELECT CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               COUNT(CASE WHEN l.stage = 'FUNDED' AND l.stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as funded_count,
               COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' AND l.stage_changed_at >= DATE_TRUNC('month', CURRENT_DATE) THEN l.amount END), 0) as funded_vol,
               COUNT(*) FILTER (WHERE l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')) as active_pipeline
        FROM users u
        LEFT JOIN loans l ON l.loan_officer_id = u.id AND l.organization_id = :org_id
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'branch_manager')
        GROUP BY u.first_name, u.last_name
        ORDER BY funded_vol DESC
    """), {"org_id": organization_id}).fetchall()

    lines = []
    for i, r in enumerate(rankings[:10], 1):
        lines.append(f"#{i} {r[0]}: {r[1]} funded (${float(r[2]):,.0f}), {r[3]} active")

    summary = "Leaderboard: " + "; ".join(lines[:5]) if lines else "No production data"

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": f"[Leaderboard] {summary}", "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Team leaderboard commit failed: {e}")

    return {"summary": summary, "actions_taken": 1, "notifications_sent": 0}
