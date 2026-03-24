"""
Morning Briefing Service

Gathers pipeline data, generates AI narratives, and renders briefings
for individual contributors, managers, and leadership.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# SLA targets in days (same as CLAUDE.md pipeline tools)
SLA_TARGETS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "APPROVED": 3,
    "CONDITIONAL_APPROVAL": 3,
    "CLEAR_TO_CLOSE": 3,
    "CTC": 3,
    "DOCS_OUT": 5,
}

TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY",
)

LEADERSHIP_ROLES = ("leadership", "admin", "site_admin", "platform_admin")
MANAGER_ROLES = ("management", "branch_manager", "regional_manager")


@dataclass
class BriefingContext:
    """All data needed to generate a briefing."""
    user_id: int
    user_name: str
    organization_id: int
    briefing_date: date
    level: str  # individual, manager, leadership

    # Individual data
    pipeline: Dict[str, Any] = field(default_factory=dict)
    at_risk: List[Dict[str, Any]] = field(default_factory=list)
    stale_leads: List[Dict[str, Any]] = field(default_factory=list)
    appointments: List[Dict[str, Any]] = field(default_factory=list)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    yesterday: Dict[str, Any] = field(default_factory=dict)

    # Team/org data (manager and leadership only)
    team: Optional[Dict[str, Any]] = None


class MorningBriefingService:
    """Generates morning briefings at all hierarchy levels."""

    # ------------------------------------------------------------------
    # Level detection
    # ------------------------------------------------------------------

    @staticmethod
    def determine_level(user: Any) -> str:
        """Determine briefing level from user role and direct reports."""
        role = getattr(user, "permission_role", "sales") or "sales"

        if role in LEADERSHIP_ROLES:
            return "leadership"

        reports = getattr(user, "direct_reports", None) or []
        if role in MANAGER_ROLES and len(reports) > 0:
            return "manager"

        return "individual"

    @staticmethod
    def compute_health(at_risk: int = 0, stale_leads: int = 0, sla_breach: bool = False) -> str:
        """Compute health indicator for a team member or branch."""
        if sla_breach or at_risk >= 3:
            return "red"
        if at_risk >= 1 or stale_leads >= 3:
            return "yellow"
        return "green"

    # ------------------------------------------------------------------
    # Individual data gathering (Level 1)
    # ------------------------------------------------------------------

    def gather_individual_data(
        self, db: Session, user_id: int, org_id: int, briefing_date: date, user_tz: str,
    ) -> Dict[str, Any]:
        """Run 6 queries for individual-level briefing data."""
        today = briefing_date
        yesterday = today - timedelta(days=1)
        week_ahead = today + timedelta(days=7)
        three_days = today + timedelta(days=3)

        pipeline = self._query_pipeline_snapshot(db, user_id, org_id, week_ahead)
        at_risk = self._query_at_risk_loans(db, user_id, org_id, three_days)
        stale_leads = self._query_stale_leads(db, user_id, org_id, today)
        appointments = self._query_todays_appointments(db, user_id, org_id, today, user_tz)
        conditions = self._query_pending_conditions(db, user_id, org_id, today)
        yesterday_activity = self._query_yesterday_activity(db, user_id, org_id, yesterday)

        return {
            "pipeline": pipeline,
            "at_risk": at_risk,
            "stale_leads": stale_leads,
            "appointments": appointments,
            "conditions": conditions,
            "yesterday": yesterday_activity,
        }

    def _query_pipeline_snapshot(self, db: Session, user_id: int, org_id: int, week_ahead: date) -> Dict:
        """Active loans count, volume, stage breakdown, closing soon."""
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
        try:
            summary = db.execute(sa_text(f"""
                SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(amount), 0) as total_volume,
                    COUNT(CASE WHEN closing_date <= :week_ahead THEN 1 END) as closing_soon
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
            """), {"uid": user_id, "oid": org_id, "week_ahead": week_ahead}).fetchone()

            stages = db.execute(sa_text(f"""
                SELECT UPPER(stage) as stage, COUNT(*) as cnt
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                GROUP BY UPPER(stage)
                ORDER BY cnt DESC
            """), {"uid": user_id, "oid": org_id}).fetchall()

            return {
                "active_count": summary[0] or 0,
                "total_volume": float(summary[1] or 0),
                "closing_soon": summary[2] or 0,
                "by_stage": {row[0]: row[1] for row in stages},
            }
        except Exception as e:
            logger.error("Pipeline snapshot query failed: %s", e)
            return {"active_count": 0, "total_volume": 0, "closing_soon": 0, "by_stage": {}}

    def _query_at_risk_loans(self, db: Session, user_id: int, org_id: int, three_days: date) -> List[Dict]:
        """Loans with SLA breaches, expiring locks, or stagnation."""
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
        try:
            rows = db.execute(sa_text(f"""
                SELECT
                    id, loan_number, borrower_name, UPPER(stage) as stage,
                    stage_changed_at, lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 as days_in_stage
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                  AND (
                    lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days_in_stage DESC
                LIMIT 10
            """), {"uid": user_id, "oid": org_id, "three_days": three_days}).fetchall()

            results = []
            for r in rows:
                stage = r[3] or ""
                days = float(r[6] or 0)
                sla_target = SLA_TARGETS.get(stage, 7)
                reason = []
                if r[5] and r[5] <= three_days:
                    reason.append(f"Lock expires {r[5].strftime('%m/%d') if hasattr(r[5], 'strftime') else r[5]}")
                if days > sla_target:
                    reason.append(f"{days:.0f} days in {stage} (SLA: {sla_target})")
                if days > 10 and not reason:
                    reason.append(f"No movement in {days:.0f} days")

                results.append({
                    "loan_id": r[0],
                    "loan_number": r[1],
                    "borrower": r[2] or "Unknown",
                    "stage": stage,
                    "days_in_stage": round(days, 1),
                    "reason": "; ".join(reason),
                })
            return results
        except Exception as e:
            logger.error("At-risk query failed: %s", e)
            return []

    def _query_stale_leads(self, db: Session, user_id: int, org_id: int, today: date) -> List[Dict]:
        """Leads with no recent contact, prioritizing high-score leads."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    id, first_name, last_name, ai_score, last_contact,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_contact)) / 86400 as days_silent
                FROM leads
                WHERE owner_id = :uid AND organization_id = :oid
                  AND last_contact IS NOT NULL
                  AND (
                    (ai_score >= 70 AND last_contact < CURRENT_DATE - INTERVAL '3 days')
                    OR last_contact < CURRENT_DATE - INTERVAL '7 days'
                  )
                ORDER BY ai_score DESC NULLS LAST, days_silent DESC
                LIMIT 10
            """), {"uid": user_id, "oid": org_id}).fetchall()

            return [
                {
                    "lead_id": r[0],
                    "name": f"{r[1] or ''} {r[2] or ''}".strip() or "Unknown",
                    "score": r[3],
                    "days_silent": round(float(r[5] or 0), 0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Stale leads query failed: %s", e)
            return []

    def _query_todays_appointments(
        self, db: Session, user_id: int, org_id: int, today: date, user_tz: str,
    ) -> List[Dict]:
        """Today's appointments for this user."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    sa.id, sa.attendee_name, sa.title,
                    sa.scheduled_start AT TIME ZONE 'UTC' AT TIME ZONE :tz as local_start
                FROM scheduler_appointments sa
                WHERE sa.assigned_user_id = :uid AND sa.organization_id = :oid
                  AND (sa.scheduled_start AT TIME ZONE 'UTC' AT TIME ZONE :tz)::date = :today
                  AND sa.status NOT IN ('cancelled', 'no_show')
                ORDER BY sa.scheduled_start
            """), {"uid": user_id, "oid": org_id, "tz": user_tz, "today": today}).fetchall()

            return [
                {
                    "id": r[0],
                    "attendee": r[1] or "Unknown",
                    "type": r[2] or "Appointment",
                    "time": r[3].strftime("%-I:%M %p") if r[3] else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Appointments query failed: %s", e)
            return []

    def _query_pending_conditions(self, db: Session, user_id: int, org_id: int, today: date) -> List[Dict]:
        """Open compliance alerts on this user's loans."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    ca.id, ca.title, ca.severity, ca.deadline_date, l.loan_number
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id
                WHERE l.loan_officer_id = :uid AND l.organization_id = :oid
                  AND ca.status = 'open'
                ORDER BY
                    CASE WHEN ca.deadline_date < :today THEN 0 ELSE 1 END,
                    ca.deadline_date ASC NULLS LAST
                LIMIT 10
            """), {"uid": user_id, "oid": org_id, "today": today}).fetchall()

            return [
                {
                    "title": r[1],
                    "severity": r[2],
                    "past_due": bool(r[3] and r[3] < today),
                    "loan_number": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Conditions query failed: %s", e)
            return []

    def _query_yesterday_activity(self, db: Session, user_id: int, org_id: int, yesterday: date) -> Dict:
        """Loans funded, new pipeline, lead conversions from yesterday."""
        try:
            result = db.execute(sa_text("""
                SELECT
                    COUNT(CASE WHEN funded_date = :yesterday THEN 1 END) as funded,
                    COUNT(CASE WHEN created_at::date = :yesterday THEN 1 END) as new_loans
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
            """), {"uid": user_id, "oid": org_id, "yesterday": yesterday}).fetchone()

            lead_conversions = db.execute(sa_text("""
                SELECT COUNT(*) FROM leads
                WHERE owner_id = :uid AND organization_id = :oid
                  AND stage = 'Converted' AND updated_at::date = :yesterday
            """), {"uid": user_id, "oid": org_id, "yesterday": yesterday}).fetchone()

            return {
                "funded": result[0] or 0,
                "new_loans": result[1] or 0,
                "conversions": lead_conversions[0] if lead_conversions else 0,
            }
        except Exception as e:
            logger.error("Yesterday activity query failed: %s", e)
            return {"funded": 0, "new_loans": 0, "conversions": 0}

    # ------------------------------------------------------------------
    # Manager data gathering (Level 2)
    # ------------------------------------------------------------------

    def gather_manager_data(self, db: Session, user_id: int, org_id: int, briefing_date: date) -> Dict:
        """Gather subordinate roll-up data for manager briefing."""
        today = briefing_date
        three_days = today + timedelta(days=3)

        try:
            # Get direct reports
            reports = db.execute(sa_text("""
                SELECT id, first_name, last_name
                FROM users
                WHERE manager_id = :uid AND is_active = TRUE AND organization_id = :oid
            """), {"uid": user_id, "oid": org_id}).fetchall()

            if not reports:
                return {"members": [], "attention_items": []}

            report_ids = [r[0] for r in reports]
            report_names = {r[0]: f"{r[1] or ''} {r[2] or ''}".strip() for r in reports}
            id_list = ", ".join(str(i) for i in report_ids)
            terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)

            # Team pipeline summary per report
            team_loans = db.execute(sa_text(f"""
                SELECT
                    loan_officer_id,
                    COUNT(*) as loan_count,
                    COALESCE(SUM(amount), 0) as volume,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400) as avg_days
                FROM loans
                WHERE loan_officer_id IN ({id_list}) AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                GROUP BY loan_officer_id
            """), {"oid": org_id}).fetchall()

            loan_map = {r[0]: {"count": r[1], "volume": float(r[2] or 0), "avg_days": float(r[3] or 0)} for r in team_loans}

            # At-risk per report
            at_risk_counts = db.execute(sa_text(f"""
                SELECT loan_officer_id, COUNT(*) as cnt,
                    BOOL_OR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 >
                        CASE UPPER(stage)
                            WHEN 'APPLICATION' THEN 3 WHEN 'DISCLOSED' THEN 7
                            WHEN 'SUBMITTED' THEN 2 WHEN 'UW_RECEIVED' THEN 5
                            WHEN 'APPROVED' THEN 3 WHEN 'CLEAR_TO_CLOSE' THEN 3
                            WHEN 'DOCS_OUT' THEN 5 ELSE 7
                        END
                    ) as has_sla_breach
                FROM loans
                WHERE loan_officer_id IN ({id_list}) AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                  AND (
                    lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 > 10
                  )
                GROUP BY loan_officer_id
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            risk_map = {r[0]: {"count": r[1], "sla_breach": bool(r[2])} for r in at_risk_counts}

            # Stale leads per report
            stale_counts = db.execute(sa_text(f"""
                SELECT owner_id, COUNT(*) as cnt
                FROM leads
                WHERE owner_id IN ({id_list}) AND organization_id = :oid
                  AND last_contact IS NOT NULL
                  AND last_contact < CURRENT_DATE - INTERVAL '7 days'
                GROUP BY owner_id
            """), {"oid": org_id}).fetchall()

            stale_map = {r[0]: r[1] for r in stale_counts}

            # Build members list
            members = []
            for uid in report_ids:
                loans_info = loan_map.get(uid, {"count": 0, "volume": 0, "avg_days": 0})
                risk_info = risk_map.get(uid, {"count": 0, "sla_breach": False})
                stale = stale_map.get(uid, 0)

                members.append({
                    "user_id": uid,
                    "name": report_names[uid],
                    "loan_count": loans_info["count"],
                    "volume": loans_info["volume"],
                    "at_risk_count": risk_info["count"],
                    "stale_lead_count": stale,
                    "health": self.compute_health(
                        at_risk=risk_info["count"],
                        stale_leads=stale,
                        sla_breach=risk_info["sla_breach"],
                    ),
                })

            # Top attention items across all reports
            attention = db.execute(sa_text(f"""
                SELECT
                    l.loan_officer_id, l.loan_number, l.borrower_name,
                    UPPER(l.stage) as stage, l.lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 as days
                FROM loans l
                WHERE l.loan_officer_id IN ({id_list}) AND l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                  AND (
                    l.lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN l.lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days DESC
                LIMIT 5
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            attention_items = []
            for r in attention:
                lo_name = report_names.get(r[0], "Unknown")
                issue_parts = []
                if r[4] and r[4] <= three_days:
                    issue_parts.append(f"{r[2] or 'Unknown'} loan lock expires soon")
                elif float(r[5] or 0) > 10:
                    issue_parts.append(f"{r[2] or 'Unknown'} loan stalled {float(r[5]):.0f} days in {r[3]}")

                attention_items.append({
                    "user_name": lo_name,
                    "loan_number": r[1],
                    "issue": "; ".join(issue_parts) if issue_parts else f"{r[2]} loan needs attention",
                    "severity": "high" if r[4] and r[4] <= three_days else "medium",
                })

            return {"members": members, "attention_items": attention_items}

        except Exception as e:
            logger.error("Manager data gathering failed: %s", e)
            return {"members": [], "attention_items": []}

    # ------------------------------------------------------------------
    # Leadership data gathering (Level 3)
    # ------------------------------------------------------------------

    def gather_leadership_data(self, db: Session, org_id: int, briefing_date: date) -> Dict:
        """Gather org-wide roll-up for leadership briefing."""
        today = briefing_date
        three_days = today + timedelta(days=3)
        week_ago = today - timedelta(days=7)
        two_weeks_ago = today - timedelta(days=14)
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)

        try:
            # Org active pipeline snapshot (excludes terminal stages)
            org_snap = db.execute(sa_text(f"""
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(amount), 0) as volume
                FROM loans
                WHERE organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
            """), {"oid": org_id}).fetchone()

            # Funded counts (separate query — funded IS a terminal stage)
            funded_snap = db.execute(sa_text("""
                SELECT
                    COUNT(CASE WHEN funded_date >= :week_ago THEN 1 END) as funded_this_week,
                    COUNT(CASE WHEN funded_date >= :two_weeks_ago AND funded_date < :week_ago THEN 1 END) as funded_last_week
                FROM loans
                WHERE organization_id = :oid AND funded_date >= :two_weeks_ago
            """), {"oid": org_id, "week_ago": week_ago, "two_weeks_ago": two_weeks_ago}).fetchone()

            # Branch comparison
            branches = db.execute(sa_text(f"""
                SELECT
                    COALESCE(b.name, 'Unassigned') as branch_name,
                    COUNT(l.id) as loan_count,
                    COALESCE(SUM(l.amount), 0) as volume,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days,
                    COUNT(CASE WHEN l.lock_expiration_date <= :three_days
                        OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                        THEN 1 END) as at_risk
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                LEFT JOIN branches b ON b.id = u.branch_id
                WHERE l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                GROUP BY b.name
                ORDER BY volume DESC
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            branch_list = []
            for r in branches:
                at_risk = r[4] or 0
                avg_days = float(r[3] or 0)
                branch_list.append({
                    "name": r[0],
                    "loan_count": r[1],
                    "volume": float(r[2] or 0),
                    "avg_days_in_stage": round(avg_days, 1),
                    "at_risk_count": at_risk,
                    "health": self.compute_health(at_risk=at_risk, stale_leads=0, sla_breach=avg_days > 10),
                })

            # Top org risks
            top_risks = db.execute(sa_text(f"""
                SELECT
                    l.loan_number, l.borrower_name, UPPER(l.stage) as stage,
                    l.lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 as days,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                    COALESCE(b.name, 'Unassigned') as branch_name
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                LEFT JOIN branches b ON b.id = u.branch_id
                WHERE l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                  AND (
                    l.lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN l.lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days DESC
                LIMIT 10
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            risks = []
            for r in top_risks:
                issue = ""
                if r[3] and r[3] <= three_days:
                    issue = f"Lock expires {r[3].strftime('%m/%d') if hasattr(r[3], 'strftime') else r[3]}"
                else:
                    issue = f"{float(r[4]):.0f} days in {r[2]}"
                risks.append({
                    "loan_number": r[0],
                    "borrower": r[1] or "Unknown",
                    "lo_name": r[5],
                    "branch": r[6],
                    "issue": issue,
                })

            funded_this_week = funded_snap[0] or 0
            funded_last_week = funded_snap[1] or 0

            return {
                "org_snapshot": {
                    "active_count": org_snap[0] or 0,
                    "total_volume": float(org_snap[1] or 0),
                    "funded_this_week": funded_this_week,
                    "funded_last_week": funded_last_week,
                    "funded_trend": "up" if funded_this_week > funded_last_week else (
                        "down" if funded_this_week < funded_last_week else "flat"
                    ),
                },
                "branches": branch_list,
                "top_risks": risks,
            }

        except Exception as e:
            logger.error("Leadership data gathering failed: %s", e)
            return {"org_snapshot": {}, "branches": [], "top_risks": []}

    # ------------------------------------------------------------------
    # Full briefing context builder
    # ------------------------------------------------------------------

    def build_context(
        self, db: Session, user: Any, briefing_date: date,
    ) -> BriefingContext:
        """Build complete BriefingContext for a user."""
        user_id = user.id
        org_id = user.organization_id
        user_tz = getattr(user, "timezone", None) or "America/New_York"
        user_name = getattr(user, "full_name", None) or f"{user.first_name or ''} {user.last_name or ''}".strip()
        level = self.determine_level(user)

        ctx = BriefingContext(
            user_id=user_id,
            user_name=user_name,
            organization_id=org_id,
            briefing_date=briefing_date,
            level=level,
        )

        # Individual data (all levels get this)
        individual = self.gather_individual_data(db, user_id, org_id, briefing_date, user_tz)
        ctx.pipeline = individual["pipeline"]
        ctx.at_risk = individual["at_risk"]
        ctx.stale_leads = individual["stale_leads"]
        ctx.appointments = individual["appointments"]
        ctx.conditions = individual["conditions"]
        ctx.yesterday = individual["yesterday"]

        # Manager roll-up
        if level == "manager":
            ctx.team = self.gather_manager_data(db, user_id, org_id, briefing_date)

        # Leadership roll-up
        if level == "leadership":
            ctx.team = self.gather_leadership_data(db, org_id, briefing_date)

        return ctx
