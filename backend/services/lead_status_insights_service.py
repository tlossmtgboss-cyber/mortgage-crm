"""
Lead Status Insights Service

Provides pipeline intelligence and coaching analytics for leads across all stages.
This is the analytics companion to get_leads_by_status - it returns:
- Counts & conversion rates
- Days in status metrics
- Bottlenecks & leaks detection
- Prioritized focus areas
- Recommended actions per status
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_
from collections import defaultdict
import statistics
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# Lead status enum values (matching LeadStage enum in main.py)
LEAD_STATUSES = [
    "New",
    "Attempted Contact",
    "Prospect",
    "Application",
    "Pre-Qualified",
    "Pre-Approved",
    "Nurture",  # Maps to Long-Term Nurture
    "Withdrawn",
    "Does Not Qualify"
]

# Normalized status keys for API
STATUS_KEY_MAP = {
    "new": "New",
    "attempted_contact": "Attempted Contact",
    "prospect": "Prospect",
    "application": "Application",
    "pre_qualified": "Pre-Qualified",
    "pre_approved": "Pre-Approved",
    "nurture": "Long-Term Nurture",
    "withdrawn": "Withdrawn",
    "does_not_qualify": "Does Not Qualify"
}

# Human-readable labels
STATUS_LABELS = {
    "New": "New Lead",
    "Attempted Contact": "Attempted Contact",
    "Prospect": "Qualified Prospect",
    "Application": "Application In Progress",
    "Pre-Qualified": "Pre-Qualified",
    "Pre-Approved": "Pre-Approved",
    "Long-Term Nurture": "Long-Term Nurture",
    "Withdrawn": "Withdrawn",
    "Does Not Qualify": "Does Not Qualify"
}

# Pipeline progression order (for conversion rate calculations)
PIPELINE_ORDER = [
    "New",
    "Attempted Contact",
    "Prospect",
    "Application",
    "Pre-Qualified",
    "Pre-Approved"
]

# SLA target days by status (can be configured per org)
DEFAULT_SLA_TARGETS = {
    "New": 0.5,  # 12 hours to first contact
    "Attempted Contact": 3,  # 3 days to reach/qualify
    "Prospect": 7,  # 7 days to get application
    "Application": 5,  # 5 days to pre-qualify
    "Pre-Qualified": 14,  # 14 days to pre-approve
    "Pre-Approved": 30,  # 30 days to contract
    "Long-Term Nurture": 90,  # 90 days for re-engagement
}

# Terminal statuses (not part of active pipeline)
TERMINAL_STATUSES = ["Withdrawn", "Does Not Qualify"]

# Active statuses (part of active pipeline)
ACTIVE_STATUSES = [s for s in LEAD_STATUSES if s not in TERMINAL_STATUSES and s != "Nurture"]


class LeadStatusInsightsService:
    """
    Service for analyzing lead pipeline health and providing coaching insights.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_insights(
        self,
        assigned_to_user_id: Optional[str] = None,
        include_statuses: Optional[List[str]] = None,
        created_date_from: Optional[str] = None,
        created_date_to: Optional[str] = None,
        time_bucket: str = "week"
    ) -> Dict[str, Any]:
        """
        Get comprehensive lead status insights and coaching recommendations.

        Args:
            assigned_to_user_id: Optional user ID to filter leads
            include_statuses: Optional list of statuses to analyze (defaults to all)
            created_date_from: Optional start date filter (YYYY-MM-DD)
            created_date_to: Optional end date filter (YYYY-MM-DD)
            time_bucket: Time aggregation bucket for trends (day/week/month)

        Returns:
            Dict with context, summary, by_status, bottlenecks, priority_focus_areas, trend_metrics
        """
        # Import Lead model here to avoid circular imports
        from database.enums import LeadStage
        from database.models import Lead

        # Normalize status keys to enum values
        if include_statuses:
            normalized_statuses = []
            for s in include_statuses:
                mapped = STATUS_KEY_MAP.get(s.lower().replace(" ", "_"))
                if mapped:
                    normalized_statuses.append(mapped)
            analyzed_statuses = normalized_statuses if normalized_statuses else list(STATUS_KEY_MAP.values())
        else:
            analyzed_statuses = list(STATUS_KEY_MAP.values())

        # Build base query
        query = self.db.query(Lead)

        # Apply filters
        if assigned_to_user_id:
            try:
                query = query.filter(Lead.owner_id == int(assigned_to_user_id))
            except (ValueError, TypeError):
                pass

        if created_date_from:
            try:
                from_date = datetime.strptime(created_date_from, "%Y-%m-%d")
                query = query.filter(Lead.created_at >= from_date)
            except ValueError:
                pass

        if created_date_to:
            try:
                to_date = datetime.strptime(created_date_to, "%Y-%m-%d")
                to_date = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Lead.created_at <= to_date)
            except ValueError:
                pass

        # Get all leads matching criteria
        leads = query.all()

        # Calculate metrics
        context = self._build_context(
            assigned_to_user_id,
            analyzed_statuses,
            created_date_from,
            created_date_to
        )

        summary = self._calculate_summary(leads, analyzed_statuses)
        by_status = self._calculate_by_status(leads, analyzed_statuses)
        bottlenecks = self._detect_bottlenecks(by_status, leads)
        priority_focus_areas = self._calculate_priorities(by_status, bottlenecks)
        trend_metrics = self._calculate_trends(leads, time_bucket, analyzed_statuses)

        return {
            "context": context,
            "summary": summary,
            "by_status": by_status,
            "bottlenecks": bottlenecks,
            "priority_focus_areas": priority_focus_areas,
            "trend_metrics": trend_metrics
        }

    def _build_context(
        self,
        assigned_to_user_id: Optional[str],
        analyzed_statuses: List[str],
        created_date_from: Optional[str],
        created_date_to: Optional[str]
    ) -> Dict[str, Any]:
        """Build context object for the response."""
        return {
            "assigned_to_user_id": assigned_to_user_id,
            "analyzed_statuses": analyzed_statuses,
            "created_date_from": created_date_from,
            "created_date_to": created_date_to,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    def _calculate_summary(
        self,
        leads: List[Any],
        analyzed_statuses: List[str]
    ) -> Dict[str, Any]:
        """Calculate overall pipeline summary metrics."""
        total_leads = len(leads)

        # Filter to leads in analyzed statuses
        filtered_leads = [
            l for l in leads
            if l.stage and l.stage.value in analyzed_statuses
        ]

        # Active leads (exclude Withdrawn and DNQ)
        active_leads = [
            l for l in filtered_leads
            if l.stage and l.stage.value not in TERMINAL_STATUSES
        ]

        # Calculate rates
        overall_contact_rate = 0.0
        overall_application_rate = 0.0
        overall_preapproval_rate = 0.0
        overall_nurture_rate = 0.0

        if total_leads > 0:
            # Contact rate: leads past "New" status
            contacted = [
                l for l in leads
                if l.stage and l.stage.value not in ["New"]
            ]
            overall_contact_rate = round((len(contacted) / total_leads) * 100, 1)

            # Application rate: leads that reached Application or beyond
            application_stages = ["Application", "Pre-Qualified", "Pre-Approved"]
            in_application = [
                l for l in leads
                if l.stage and l.stage.value in application_stages
            ]
            overall_application_rate = round((len(in_application) / total_leads) * 100, 1)

            # Pre-approval rate
            preapproved = [
                l for l in leads
                if l.stage and l.stage.value == "Pre-Approved"
            ]
            overall_preapproval_rate = round((len(preapproved) / total_leads) * 100, 1)

            # Nurture rate
            in_nurture = [
                l for l in leads
                if l.stage and l.stage.value == "Long-Term Nurture"
            ]
            overall_nurture_rate = round((len(in_nurture) / total_leads) * 100, 1)

        return {
            "total_leads": total_leads,
            "total_active_leads": len(active_leads),
            "overall_contact_rate": overall_contact_rate,
            "overall_application_rate": overall_application_rate,
            "overall_preapproval_rate": overall_preapproval_rate,
            "overall_nurture_rate": overall_nurture_rate
        }

    def _calculate_by_status(
        self,
        leads: List[Any],
        analyzed_statuses: List[str]
    ) -> List[Dict[str, Any]]:
        """Calculate per-status metrics."""
        now = datetime.now(timezone.utc)
        total_leads = len(leads)

        # Group leads by status
        by_status_map = defaultdict(list)
        for lead in leads:
            if lead.stage:
                by_status_map[lead.stage.value].append(lead)

        results = []

        for status in analyzed_statuses:
            status_leads = by_status_map.get(status, [])
            count = len(status_leads)

            # Calculate percentage of total
            percentage_of_total = round((count / total_leads * 100), 1) if total_leads > 0 else 0.0

            # Calculate days in status
            days_in_status = []
            for lead in status_leads:
                if lead.updated_at:
                    # Use updated_at as proxy for when they entered this status
                    try:
                        updated = lead.updated_at
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=timezone.utc)
                        days = (now - updated).days
                        days_in_status.append(max(0, days))
                    except Exception as e:
                        logger.exception(f"Failed to calculate days in status for lead: {e}")

            avg_days = round(statistics.mean(days_in_status), 1) if days_in_status else 0.0
            median_days = round(statistics.median(days_in_status), 1) if days_in_status else 0.0

            # Calculate conversion rate to next status
            conversion_rate = self._calculate_conversion_rate(status, leads)

            # Calculate leak rate (went to Withdrawn or DNQ from this status)
            leak_rate = self._calculate_leak_rate(status, leads)

            # Count overdue leads
            sla_target = DEFAULT_SLA_TARGETS.get(status, 7)
            overdue_count = sum(1 for d in days_in_status if d > sla_target)

            results.append({
                "status": status.lower().replace(" ", "_").replace("-", "_"),
                "label": STATUS_LABELS.get(status, status),
                "count": count,
                "percentage_of_total": percentage_of_total,
                "average_days_in_status": avg_days,
                "median_days_in_status": median_days,
                "conversion_to_next_status_rate": conversion_rate,
                "leak_rate": leak_rate,
                "overdue_count": overdue_count,
                "sla_target_days": sla_target
            })

        return results

    def _calculate_conversion_rate(self, status: str, leads: List[Any]) -> float:
        """Calculate conversion rate from a status to the next logical status."""
        if status not in PIPELINE_ORDER:
            return 0.0

        try:
            current_idx = PIPELINE_ORDER.index(status)
            if current_idx >= len(PIPELINE_ORDER) - 1:
                # Last status in pipeline
                return 0.0

            next_status = PIPELINE_ORDER[current_idx + 1]

            # Count leads that ever reached this status (currently in this or later)
            later_statuses = PIPELINE_ORDER[current_idx:]
            leads_at_or_past = [
                l for l in leads
                if l.stage and l.stage.value in later_statuses
            ]

            # Count leads that advanced past this status
            advanced_statuses = PIPELINE_ORDER[current_idx + 1:]
            leads_advanced = [
                l for l in leads
                if l.stage and l.stage.value in advanced_statuses
            ]

            if len(leads_at_or_past) > 0:
                return round((len(leads_advanced) / len(leads_at_or_past)) * 100, 1)
        except Exception as e:
            logger.exception(f"Failed to calculate conversion rate for status '{status}': {e}")

        return 0.0

    def _calculate_leak_rate(self, status: str, leads: List[Any]) -> float:
        """Calculate rate of leads leaking to terminal statuses from a given status."""
        # This is a simplified calculation - in production you'd want to track
        # status history to know where leads came from before terminal status
        terminal_leads = [
            l for l in leads
            if l.stage and l.stage.value in TERMINAL_STATUSES
        ]

        total_in_funnel = len(leads)
        if total_in_funnel > 0:
            return round((len(terminal_leads) / total_in_funnel) * 100, 1)
        return 0.0

    def _detect_bottlenecks(
        self,
        by_status: List[Dict[str, Any]],
        leads: List[Any]
    ) -> List[Dict[str, Any]]:
        """Detect bottlenecks and issues in the pipeline."""
        bottlenecks = []

        for status_data in by_status:
            status = status_data["status"]
            count = status_data["count"]
            avg_days = status_data["average_days_in_status"]
            overdue = status_data["overdue_count"]
            conversion_rate = status_data["conversion_to_next_status_rate"]
            leak_rate = status_data["leak_rate"]
            sla_target = status_data["sla_target_days"]

            # High overdue count
            if overdue > 5:
                severity = "critical" if overdue > 20 else "high" if overdue > 10 else "medium"
                bottlenecks.append({
                    "status": status,
                    "issue_type": "high_overdue_count",
                    "description": f"{overdue} leads have been in {status_data['label']} longer than the {sla_target}-day SLA target",
                    "severity": severity,
                    "recommended_action": f"Prioritize working the {overdue} overdue {status_data['label']} leads today. Create follow-up tasks or run an outreach sequence."
                })

            # Low conversion rate (only for active pipeline statuses)
            if status not in ["withdrawn", "does_not_qualify", "nurture"]:
                if conversion_rate > 0 and conversion_rate < 25:
                    severity = "high" if conversion_rate < 15 else "medium"
                    bottlenecks.append({
                        "status": status,
                        "issue_type": "low_conversion_rate",
                        "description": f"Only {conversion_rate}% of {status_data['label']} leads advance to the next stage",
                        "severity": severity,
                        "recommended_action": f"Review your {status_data['label']} leads to identify blockers. Consider adjusting your outreach cadence or qualifying criteria."
                    })

            # High leak rate
            if leak_rate > 20:
                severity = "high" if leak_rate > 35 else "medium"
                bottlenecks.append({
                    "status": status,
                    "issue_type": "high_leak_rate",
                    "description": f"{leak_rate}% of leads are dropping out of the pipeline",
                    "severity": severity,
                    "recommended_action": "Analyze why leads are being lost. Consider implementing a win-back campaign or adjusting lead qualification criteria."
                })

            # Stalled nurture
            if status == "nurture" and avg_days > 60 and count > 10:
                bottlenecks.append({
                    "status": status,
                    "issue_type": "stalled_nurture",
                    "description": f"{count} leads have been in nurture for an average of {avg_days} days with no re-engagement",
                    "severity": "medium",
                    "recommended_action": "Run a re-engagement campaign on nurture leads. Segment by last contact date and interests."
                })

            # Missing contact attempts for New leads
            if status == "new" and count > 5:
                # Check if New leads have no last_contact
                new_leads_no_contact = [
                    l for l in leads
                    if l.stage and l.stage.value == "New" and not l.last_contact
                ]
                if len(new_leads_no_contact) > 3:
                    bottlenecks.append({
                        "status": status,
                        "issue_type": "missing_contact_attempts",
                        "description": f"{len(new_leads_no_contact)} new leads have not been contacted yet",
                        "severity": "critical",
                        "recommended_action": "These hot leads need immediate attention. Aim for first contact within 5 minutes of lead arrival."
                    })

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        bottlenecks.sort(key=lambda x: severity_order.get(x["severity"], 4))

        return bottlenecks

    def _calculate_priorities(
        self,
        by_status: List[Dict[str, Any]],
        bottlenecks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Calculate prioritized focus areas based on bottlenecks and metrics."""
        priorities = []
        priority_rank = 1

        # First priority: New leads without contact (speed to lead)
        new_status = next((s for s in by_status if s["status"] == "new"), None)
        if new_status and new_status["count"] > 0:
            priorities.append({
                "rank": priority_rank,
                "status": "new",
                "focus_reason": f"{new_status['count']} new leads require immediate attention for speed-to-lead",
                "suggested_playbook": "Call within 5 minutes, then text + email same day. Schedule consultation."
            })
            priority_rank += 1

        # Second priority: Overdue leads in active pipeline
        for status_data in by_status:
            if status_data["overdue_count"] > 3 and status_data["status"] not in ["withdrawn", "does_not_qualify", "nurture"]:
                priorities.append({
                    "rank": priority_rank,
                    "status": status_data["status"],
                    "focus_reason": f"{status_data['overdue_count']} leads overdue in {status_data['label']} (>{status_data['sla_target_days']} days)",
                    "suggested_playbook": f"Run a 3-day call/text cadence on overdue {status_data['label']} leads to re-engage."
                })
                priority_rank += 1
                if priority_rank > 5:
                    break

        # Third priority: Low conversion bottlenecks
        conversion_bottlenecks = [
            b for b in bottlenecks
            if b["issue_type"] == "low_conversion_rate" and b["severity"] in ["high", "critical"]
        ]
        for bottleneck in conversion_bottlenecks[:2]:
            if priority_rank <= 5:
                priorities.append({
                    "rank": priority_rank,
                    "status": bottleneck["status"],
                    "focus_reason": bottleneck["description"],
                    "suggested_playbook": bottleneck["recommended_action"]
                })
                priority_rank += 1

        # Fourth priority: Nurture re-activation if there are many
        nurture_status = next((s for s in by_status if s["status"] == "nurture"), None)
        if nurture_status and nurture_status["count"] > 20 and priority_rank <= 5:
            priorities.append({
                "rank": priority_rank,
                "status": "nurture",
                "focus_reason": f"{nurture_status['count']} leads in long-term nurture could be reactivated",
                "suggested_playbook": "Segment nurture by interest (refi, purchase, investment) and run targeted drip campaigns."
            })

        return priorities[:5]  # Return top 5 priorities

    def _calculate_trends(
        self,
        leads: List[Any],
        time_bucket: str,
        analyzed_statuses: List[str]
    ) -> List[Dict[str, Any]]:
        """Calculate trend metrics over time buckets."""
        now = datetime.now(timezone.utc)

        # Determine bucket size and count
        if time_bucket == "day":
            delta = timedelta(days=1)
            bucket_count = 14  # Last 14 days
        elif time_bucket == "month":
            delta = timedelta(days=30)
            bucket_count = 6  # Last 6 months
        else:  # week (default)
            delta = timedelta(days=7)
            bucket_count = 8  # Last 8 weeks

        trends = []

        for i in range(bucket_count - 1, -1, -1):
            bucket_end = now - (delta * i)
            bucket_start = bucket_end - delta

            # Filter leads created in this bucket
            bucket_leads = [
                l for l in leads
                if l.created_at and bucket_start <= l.created_at.replace(tzinfo=timezone.utc) < bucket_end
            ]

            # Count by status
            new_count = sum(1 for l in bucket_leads if l.stage and l.stage.value == "New")
            app_count = sum(1 for l in bucket_leads if l.stage and l.stage.value == "Application")
            preapproved_count = sum(1 for l in bucket_leads if l.stage and l.stage.value == "Pre-Approved")
            withdrawn_count = sum(1 for l in bucket_leads if l.stage and l.stage.value == "Withdrawn")
            dnq_count = sum(1 for l in bucket_leads if l.stage and l.stage.value == "Does Not Qualify")

            trends.append({
                "time_bucket_start": bucket_start.strftime("%Y-%m-%d"),
                "time_bucket_end": bucket_end.strftime("%Y-%m-%d"),
                "new_leads_count": len(bucket_leads),  # Total new leads in this period
                "applications_count": app_count,
                "preapprovals_count": preapproved_count,
                "withdrawn_count": withdrawn_count,
                "does_not_qualify_count": dnq_count
            })

        return trends


def get_lead_status_insights(
    db: Session,
    assigned_to_user_id: Optional[str] = None,
    include_statuses: Optional[List[str]] = None,
    created_date_from: Optional[str] = None,
    created_date_to: Optional[str] = None,
    time_bucket: str = "week"
) -> Dict[str, Any]:
    """
    Convenience function to get lead status insights.

    Args:
        db: SQLAlchemy database session
        assigned_to_user_id: Optional user ID to filter leads
        include_statuses: Optional list of statuses to analyze
        created_date_from: Optional start date filter (YYYY-MM-DD)
        created_date_to: Optional end date filter (YYYY-MM-DD)
        time_bucket: Time aggregation bucket (day/week/month)

    Returns:
        Lead status insights dictionary
    """
    service = LeadStatusInsightsService(db)
    return service.get_insights(
        assigned_to_user_id=assigned_to_user_id,
        include_statuses=include_statuses,
        created_date_from=created_date_from,
        created_date_to=created_date_to,
        time_bucket=time_bucket
    )
