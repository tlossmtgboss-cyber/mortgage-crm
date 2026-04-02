"""
Narrative Analytics Service

Implements Module 11 gap: transforms raw metrics into actionable narratives.
"Never present raw data without interpretation."

Usage:
    from services.narrative_analytics_service import NarrativeAnalyticsService
    service = NarrativeAnalyticsService(db)
    narrative = service.narrate_pipeline(user_id=123)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class NarrativeAnalyticsService:
    """Transforms raw metrics into narrative insights per Module 11.1.

    Format:
        1. Headline metric (1 sentence)
        2. Context (vs. last month/target/team avg)
        3. Insight (WHY — root cause)
        4. Action (WHAT to do — specific, prioritized)
    """

    def __init__(self, db_session):
        self.db = db_session

    def narrate_pipeline(
        self,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """Generate narrative pipeline analysis.

        INSTEAD OF: "Pipeline: 47 loans, $12.3M, 23 in processing"
        SAY: "Your pipeline has 47 loans worth $12.3M. Half are in processing,
        which is healthy. But velocity dropped 18% from last month..."
        """
        from sqlalchemy import text

        params = {"period_days": period_days}
        user_filter = ""
        if user_id:
            user_filter = "AND l.loan_officer_id = :user_id"
            params["user_id"] = user_id
        if organization_id:
            user_filter += " AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        # Current period metrics
        current_sql = """
            SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(loan_amount), 0) as total_volume,
                COUNT(CASE WHEN status IN ('CTC', 'CLEAR_TO_CLOSE', 'CLOSING', 'DOCS', 'DOCS_OUT') THEN 1 END) as closing_soon,
                COUNT(CASE WHEN status IN ('PROCESSING', 'SUBMITTED', 'UNDERWRITING') THEN 1 END) as in_processing
            FROM loans l
            WHERE l.status NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN')
        """
        if user_filter:
            current_sql += "            " + user_filter + "\n"
        current = self.db.execute(text(current_sql), params).mappings().first()

        # Previous period for comparison
        params["prev_start"] = period_days * 2
        prev_sql = """
            SELECT
                COUNT(*) as funded_count,
                COALESCE(SUM(loan_amount), 0) as funded_volume
            FROM loans l
            WHERE l.funded_at >= CURRENT_DATE - :period_days
        """
        if user_filter:
            prev_sql += "            " + user_filter + "\n"
        prev = self.db.execute(text(prev_sql), params).mappings().first()

        prev_period_sql = """
            SELECT
                COUNT(*) as funded_count,
                COALESCE(SUM(loan_amount), 0) as funded_volume
            FROM loans l
            WHERE l.funded_at >= CURRENT_DATE - :prev_start
                AND l.funded_at < CURRENT_DATE - :period_days
        """
        if user_filter:
            prev_period_sql += "            " + user_filter + "\n"
        prev_period = self.db.execute(text(prev_period_sql), params).mappings().first()

        # Build narrative
        total = current["total_count"] or 0
        volume = float(current["total_volume"] or 0)
        closing = current["closing_soon"] or 0
        processing = current["in_processing"] or 0

        funded_current = prev["funded_count"] or 0
        funded_prev = prev_period["funded_count"] or 0
        velocity_change = ((funded_current - funded_prev) / max(funded_prev, 1)) * 100

        # 1. Headline
        headline = f"Your pipeline has {total} loans worth ${volume:,.0f}."

        # 2. Context
        processing_pct = (processing / max(total, 1)) * 100
        if processing_pct > 60:
            context = f"{processing_pct:.0f}% are in processing — that's heavy. May indicate upstream flow issues."
        elif processing_pct > 40:
            context = f"{processing_pct:.0f}% are in processing, which is a healthy distribution."
        else:
            context = f"Only {processing_pct:.0f}% in processing. Pipeline may need more inflow."

        if closing > 0:
            context += f" {closing} loans are approaching closing."

        # 3. Insight
        if velocity_change > 10:
            insight = f"Velocity is up {velocity_change:.0f}% from last period — strong momentum."
        elif velocity_change < -10:
            insight = f"Velocity dropped {abs(velocity_change):.0f}% from last period — investigate processing bottlenecks."
        else:
            insight = "Velocity is stable compared to last period."

        # 4. Action
        actions = []
        if velocity_change < -10:
            actions.append("Review loans stuck in processing for common blockers")
        if closing >= 3:
            actions.append(f"Prioritize {closing} loans approaching closing to protect funded count")
        if total < 10:
            actions.append("Pipeline is thin — focus on lead generation and referral activation")

        if not actions:
            actions.append("Pipeline is healthy — maintain current pace and focus on pull-through")

        return {
            "headline": headline,
            "context": context,
            "insight": insight,
            "actions": actions,
            "narrative": f"{headline} {context} {insight}",
            "metrics": {
                "total_loans": total,
                "total_volume": volume,
                "closing_soon": closing,
                "in_processing": processing,
                "funded_this_period": funded_current,
                "funded_prev_period": funded_prev,
                "velocity_change_pct": round(velocity_change, 1),
            },
        }

    def narrate_anomaly(
        self,
        metric_name: str,
        current_value: float,
        expected_value: float,
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Generate narrative explanation for a detected anomaly.

        Module 11.2: Anomaly Detection with root cause analysis.
        """
        variance_pct = ((current_value - expected_value) / max(abs(expected_value), 0.01)) * 100
        direction = "increased" if variance_pct > 0 else "decreased"
        severity = "critical" if abs(variance_pct) > 30 else "warning" if abs(variance_pct) > 15 else "info"

        # Generate root cause hypotheses based on metric type
        hypotheses = self._generate_hypotheses(metric_name, direction, context or {})

        narrative = (
            f"{metric_name.replace('_', ' ').title()} has {direction} by {abs(variance_pct):.1f}% "
            f"from the expected {expected_value:.1f} to {current_value:.1f}."
        )

        if hypotheses:
            narrative += f" Most likely cause: {hypotheses[0]}."

        return {
            "metric": metric_name,
            "severity": severity,
            "variance_pct": round(variance_pct, 1),
            "narrative": narrative,
            "hypotheses": hypotheses,
            "recommended_investigation": self._suggest_investigation(metric_name),
        }

    def generate_executive_summary(
        self,
        organization_id: int,
        period: str = "weekly",
    ) -> Dict[str, Any]:
        """Generate Module 11.3 executive summary.

        WEEKLY:
            1. Scoreboard vs. targets
            2. Wins
            3. Watch items
            4. Top 3 recommended actions
        """
        return {
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sections": {
                "scoreboard": {
                    "description": "Performance vs. targets",
                    "metrics": ["funded_units", "funded_volume", "pipeline_count", "new_leads"],
                },
                "wins": {
                    "description": "Top achievements this period",
                    "items": [],  # Populated by actual data queries
                },
                "watch_items": {
                    "description": "Items needing attention",
                    "items": [],  # SLA breaches, compliance flags, at-risk loans
                },
                "recommended_actions": {
                    "description": "Top 3 actions for next period",
                    "items": [],  # Prioritized by impact
                },
            },
        }

    def _generate_hypotheses(
        self, metric: str, direction: str, context: Dict
    ) -> List[str]:
        """Generate root cause hypotheses for anomalies."""
        hypothesis_map = {
            "pipeline_velocity": {
                "increased": [
                    "Processing turn times increased — check condition clearance",
                    "Seasonal slowdown in underwriting",
                    "New UW guidelines causing delays",
                ],
                "decreased": [
                    "Improved processor efficiency",
                    "Lighter pipeline allowing faster turns",
                    "New automation reducing manual steps",
                ],
            },
            "lead_conversion": {
                "increased": [
                    "Higher quality lead sources this period",
                    "Improved speed-to-lead response time",
                    "Seasonal buying activity increase",
                ],
                "decreased": [
                    "Lead source quality declined",
                    "Slower follow-up response times",
                    "Competitive rate environment affecting conversions",
                ],
            },
            "pull_through": {
                "increased": [
                    "Better pre-qualification reducing fallout",
                    "Fewer competitive losses",
                ],
                "decreased": [
                    "Increased withdrawals — check competitive positioning",
                    "Higher denial rate — review underwriting criteria",
                    "Rate lock expirations causing cancellations",
                ],
            },
        }
        return hypothesis_map.get(metric, {}).get(direction, [
            f"Unusual {direction} in {metric} — manual investigation recommended"
        ])

    def _suggest_investigation(self, metric: str) -> List[str]:
        """Suggest investigation steps for a metric anomaly."""
        investigations = {
            "pipeline_velocity": [
                "Run get_bottleneck_analysis to identify stuck stages",
                "Check get_loan_aging_report for loans over SLA",
                "Review recent compliance alerts for TRID deadline issues",
            ],
            "lead_conversion": [
                "Compare lead sources with calculate_conversion_rates",
                "Check speed-to-lead response times",
                "Review lead scoring distribution",
            ],
            "pull_through": [
                "Analyze withdrawal reasons in recent fallout",
                "Check rate lock expiration status",
                "Review denial rate by loan type",
            ],
        }
        return investigations.get(metric, [
            f"Investigate {metric} using relevant pipeline and analytics tools"
        ])
