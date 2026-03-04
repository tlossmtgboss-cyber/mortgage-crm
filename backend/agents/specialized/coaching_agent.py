"""
Team Coach Agent

Specialized agent for LO performance coaching with 8 tools:
1. get_lo_performance - Get loan officer performance metrics
2. compare_to_peers - Compare LO performance to peers
3. identify_coaching_opportunities - Find areas for improvement
4. generate_coaching_plan - Create personalized coaching plan
5. track_coaching_progress - Track coaching goal progress
6. get_best_practices - Get best practices from top performers
7. schedule_coaching_session - Schedule 1:1 coaching session
8. generate_performance_report - Generate performance report
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class LOPerformanceInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    period_days: int = Field(default=30, description="Performance period in days")


class PeerComparisonInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID to compare")
    comparison_group: str = Field(default="branch", description="Compare against: branch, company, top_performers")


class CoachingOpportunitiesInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    min_impact: str = Field(default="medium", description="Minimum impact level: low, medium, high")


class CoachingPlanInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    focus_areas: Optional[List[str]] = Field(None, description="Specific areas to focus on")
    duration_weeks: int = Field(default=4, description="Plan duration in weeks")


class CoachingProgressInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    plan_id: Optional[str] = Field(None, description="Specific coaching plan ID")


class BestPracticesInput(BaseModel):
    category: str = Field(..., description="Category: conversion, speed, volume, quality")
    role: str = Field(default="loan_officer", description="Role filter")


class ScheduleSessionInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    coach_id: Optional[int] = Field(None, description="Coach/manager ID")
    topic: str = Field(..., description="Coaching session topic")
    duration_minutes: int = Field(default=30, description="Session duration")


class PerformanceReportInput(BaseModel):
    lo_id: int = Field(..., description="Loan officer ID")
    period_days: int = Field(default=30, description="Report period")
    include_recommendations: bool = Field(default=True, description="Include coaching recommendations")


# ============================================================================
# TEAM COACH AGENT
# ============================================================================

@AgentRegistry.register
class CoachingAgent(SpecializedAgent):
    """
    Team coaching agent for LO performance improvement.

    Provides performance analysis, peer comparison, and personalized
    coaching with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "CoachingAgent"

    @property
    def description(self) -> str:
        return "Provides LO performance coaching, peer comparison, and improvement plans"

    def _register_tools(self):
        """Register all coaching tools"""

        self.register_tool(AgentTool(
            name="get_lo_performance",
            description="Get comprehensive loan officer performance metrics",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_lo_performance,
            input_schema=LOPerformanceInput
        ))

        self.register_tool(AgentTool(
            name="compare_to_peers",
            description="Compare loan officer performance against peers",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_to_peers,
            input_schema=PeerComparisonInput
        ))

        self.register_tool(AgentTool(
            name="identify_coaching_opportunities",
            description="Identify areas where coaching can improve performance",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_coaching_opportunities,
            input_schema=CoachingOpportunitiesInput
        ))

        self.register_tool(AgentTool(
            name="generate_coaching_plan",
            description="Generate personalized coaching plan with goals and milestones",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_coaching_plan,
            input_schema=CoachingPlanInput
        ))

        self.register_tool(AgentTool(
            name="track_coaching_progress",
            description="Track progress against coaching goals",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_coaching_progress,
            input_schema=CoachingProgressInput
        ))

        self.register_tool(AgentTool(
            name="get_best_practices",
            description="Get best practices from top performers",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_best_practices,
            input_schema=BestPracticesInput
        ))

        self.register_tool(AgentTool(
            name="schedule_coaching_session",
            description="Schedule a coaching session with manager",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._schedule_coaching_session,
            input_schema=ScheduleSessionInput
        ))

        self.register_tool(AgentTool(
            name="generate_performance_report",
            description="Generate comprehensive performance report",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_performance_report,
            input_schema=PerformanceReportInput
        ))

    async def _get_lo_performance(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get LO performance metrics"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    COUNT(*) as loan_count,
                    COALESCE(SUM(amount), 0) as total_volume,
                    AVG(amount) as avg_loan_size,
                    COUNT(CASE WHEN stage = 'FUNDED' THEN 1 END) as funded_count
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND created_at >= CURRENT_DATE - :days
                AND organization_id = :org_id
            """)

            result = db.execute(query, {
                "lo_id": input_data["lo_id"],
                "days": input_data.get("period_days", 30),
                "org_id": org_id
            }).fetchone()

            performance = {
                "lo_id": input_data["lo_id"],
                "period_days": input_data.get("period_days", 30),
                "metrics": {
                    "loan_count": result.loan_count or 0,
                    "total_volume": float(result.total_volume or 0),
                    "avg_loan_size": float(result.avg_loan_size or 0),
                    "funded_count": result.funded_count or 0,
                    "pull_through_rate": round((result.funded_count or 0) / (result.loan_count or 1) * 100, 1)
                }
            }

            return ToolResult(
                success=True,
                data=performance,
                message=f"LO {input_data['lo_id']}: {result.loan_count} loans, ${float(result.total_volume or 0):,.0f} volume"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_to_peers(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Compare LO to peers"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            # Get LO's metrics
            lo_query = text("""
                SELECT
                    COUNT(*) as loans,
                    COALESCE(SUM(amount), 0) as volume
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND created_at >= CURRENT_DATE - 30
                AND organization_id = :org_id
            """)
            lo_result = db.execute(lo_query, {"lo_id": input_data["lo_id"], "org_id": org_id}).fetchone()

            # Get peer average
            peer_query = text("""
                SELECT
                    AVG(loan_count) as avg_loans,
                    AVG(volume) as avg_volume
                FROM (
                    SELECT
                        loan_officer_id,
                        COUNT(*) as loan_count,
                        COALESCE(SUM(amount), 0) as volume
                    FROM loans
                    WHERE created_at >= CURRENT_DATE - 30
                    AND organization_id = :org_id
                    GROUP BY loan_officer_id
                ) lo_stats
            """)
            peer_result = db.execute(peer_query, {"org_id": org_id}).fetchone()

            lo_loans = lo_result.loans or 0
            lo_volume = float(lo_result.volume or 0)
            peer_avg_loans = float(peer_result.avg_loans or 1)
            peer_avg_volume = float(peer_result.avg_volume or 1)

            comparison = {
                "lo_id": input_data["lo_id"],
                "comparison_group": input_data.get("comparison_group", "branch"),
                "lo_metrics": {
                    "loans": lo_loans,
                    "volume": lo_volume
                },
                "peer_average": {
                    "loans": peer_avg_loans,
                    "volume": peer_avg_volume
                },
                "percentile": {
                    "loans": min(100, round((lo_loans / peer_avg_loans) * 50, 0)) if peer_avg_loans else 50,
                    "volume": min(100, round((lo_volume / peer_avg_volume) * 50, 0)) if peer_avg_volume else 50
                }
            }

            return ToolResult(
                success=True,
                data=comparison,
                message=f"LO ranks at {comparison['percentile']['volume']:.0f}th percentile for volume"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_coaching_opportunities(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Identify coaching opportunities using DB metrics with static fallback"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        lo_id = input_data["lo_id"]
        min_impact = input_data.get("min_impact", "medium")
        impact_order = ["low", "medium", "high"]

        opportunities = []

        db = SessionLocal()
        try:
            # Get LO's conversion rate (leads with a funded loan vs total leads)
            lo_stats = db.execute(text("""
                SELECT
                    COUNT(DISTINCT ld.id) as total_leads,
                    COUNT(DISTINCT CASE WHEN lo.stage = 'FUNDED' THEN lo.id END) as funded_loans,
                    AVG(CASE WHEN lo.funded_date IS NOT NULL AND lo.application_date IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (lo.funded_date - lo.application_date)) / 86400
                    END) as avg_cycle_days,
                    COUNT(CASE WHEN lo.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY') THEN 1 END) as active_loans,
                    COUNT(CASE WHEN lo.stage IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY') THEN 1 END) as fallout_loans
                FROM leads ld
                LEFT JOIN loans lo ON lo.loan_officer_id = :lo_id AND lo.organization_id = :org_id
                WHERE ld.owner_id = :lo_id AND ld.organization_id = :org_id
                    AND ld.created_at >= CURRENT_DATE - 90
            """), {"lo_id": lo_id, "org_id": org_id}).fetchone()

            # Get peer averages for comparison
            peer_stats = db.execute(text("""
                SELECT
                    AVG(funded_rate) as avg_pull_through,
                    AVG(cycle_days) as avg_cycle_days
                FROM (
                    SELECT
                        loan_officer_id,
                        CASE WHEN COUNT(*) > 0
                            THEN COUNT(CASE WHEN stage = 'FUNDED' THEN 1 END)::float / COUNT(*)
                            ELSE 0 END as funded_rate,
                        AVG(CASE WHEN funded_date IS NOT NULL AND application_date IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400
                        END) as cycle_days
                    FROM loans
                    WHERE organization_id = :org_id AND created_at >= CURRENT_DATE - 90
                    GROUP BY loan_officer_id
                ) peer
            """), {"org_id": org_id}).fetchone()

            total_leads = lo_stats.total_leads or 0
            funded = lo_stats.funded_loans or 0
            lo_cycle = lo_stats.avg_cycle_days
            peer_cycle = peer_stats.avg_cycle_days if peer_stats else None
            peer_pull_through = float(peer_stats.avg_pull_through or 0) if peer_stats else 0
            active = lo_stats.active_loans or 0
            fallout = lo_stats.fallout_loans or 0

            # Determine pull-through rate
            total_decisions = funded + fallout
            lo_pull_through = (funded / total_decisions) if total_decisions > 0 else 0

            # Lead conversion
            if total_leads > 0 and funded < total_leads * 0.2:
                opportunities.append({
                    "area": "lead_conversion",
                    "description": f"Only {funded}/{total_leads} leads converted to funded loans in 90 days",
                    "impact": "high",
                    "recommendation": "Focus on initial contact speed and follow-up cadence"
                })

            # Cycle time
            if lo_cycle is not None and peer_cycle is not None and lo_cycle > peer_cycle * 1.15:
                opportunities.append({
                    "area": "cycle_time",
                    "description": f"Avg cycle time ({lo_cycle:.0f} days) exceeds peer average ({peer_cycle:.0f} days)",
                    "impact": "medium",
                    "recommendation": "Review document collection process and condition clearing"
                })

            # Pull-through
            if lo_pull_through < peer_pull_through * 0.9 and total_decisions > 0:
                opportunities.append({
                    "area": "pull_through",
                    "description": f"Pull-through rate ({lo_pull_through:.0%}) below peer average ({peer_pull_through:.0%})",
                    "impact": "high",
                    "recommendation": "Improve pre-qualification and set proper expectations early"
                })

            # If no data-driven opportunities found, note that
            if not opportunities:
                opportunities.append({
                    "area": "general",
                    "description": "Performance metrics are at or above peer benchmarks",
                    "impact": "low",
                    "recommendation": "Continue current practices and focus on volume growth"
                })

        except Exception as e:
            logger.warning(f"DB query for coaching opportunities failed, using defaults: {e}")
            # Fallback to static opportunities
            opportunities = [
                {
                    "area": "lead_conversion",
                    "description": "Lead to application conversion rate below average",
                    "impact": "high",
                    "recommendation": "Focus on initial contact speed and follow-up cadence"
                },
                {
                    "area": "cycle_time",
                    "description": "Average time from application to close is longer than peers",
                    "impact": "medium",
                    "recommendation": "Review document collection process and condition clearing"
                },
                {
                    "area": "pull_through",
                    "description": "Pull-through rate has opportunity for improvement",
                    "impact": "high",
                    "recommendation": "Improve pre-qualification and set proper expectations early"
                }
            ]
        finally:
            db.close()

        filtered = [o for o in opportunities if impact_order.index(o["impact"]) >= impact_order.index(min_impact)]

        return ToolResult(
            success=True,
            data={"opportunities": filtered, "lo_id": lo_id},
            message=f"Found {len(filtered)} coaching opportunities"
        )

    async def _generate_coaching_plan(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate coaching plan"""
        import uuid

        plan_id = str(uuid.uuid4())[:8].upper()
        duration_weeks = input_data.get("duration_weeks", 4)

        plan = {
            "plan_id": plan_id,
            "lo_id": input_data["lo_id"],
            "created_at": datetime.now().isoformat(),
            "duration_weeks": duration_weeks,
            "focus_areas": input_data.get("focus_areas") or ["conversion", "speed"],
            "goals": [
                {
                    "goal": "Improve lead response time to under 5 minutes",
                    "metric": "avg_response_time",
                    "target": 5,
                    "current": 15,
                    "deadline": (datetime.now() + timedelta(weeks=duration_weeks)).isoformat()
                },
                {
                    "goal": "Increase conversion rate by 10%",
                    "metric": "conversion_rate",
                    "target": 35,
                    "current": 25,
                    "deadline": (datetime.now() + timedelta(weeks=duration_weeks)).isoformat()
                }
            ],
            "weekly_activities": [
                {"week": 1, "activity": "Shadow top performer on lead calls"},
                {"week": 2, "activity": "Practice scripts with manager"},
                {"week": 3, "activity": "Review and optimize follow-up cadence"},
                {"week": 4, "activity": "Measure progress and adjust"}
            ]
        }

        return ToolResult(
            success=True,
            data=plan,
            message=f"Coaching plan {plan_id} created for {duration_weeks} weeks"
        )

    async def _track_coaching_progress(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Track coaching progress"""
        progress = {
            "lo_id": input_data["lo_id"],
            "overall_progress": 45,
            "goals": [
                {
                    "goal": "Improve lead response time",
                    "progress": 60,
                    "status": "on_track",
                    "current_value": 8,
                    "target_value": 5
                },
                {
                    "goal": "Increase conversion rate",
                    "progress": 30,
                    "status": "needs_attention",
                    "current_value": 28,
                    "target_value": 35
                }
            ],
            "completed_activities": 2,
            "total_activities": 4
        }

        return ToolResult(
            success=True,
            data=progress,
            message=f"Coaching progress: {progress['overall_progress']}% complete"
        )

    async def _get_best_practices(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get best practices"""
        practices = {
            "conversion": [
                {"practice": "Call new leads within 5 minutes", "impact": "2x higher conversion"},
                {"practice": "Use video messages for follow-up", "impact": "40% higher response"},
                {"practice": "Pre-qualify thoroughly upfront", "impact": "Better pull-through"}
            ],
            "speed": [
                {"practice": "Collect documents before application", "impact": "3 days faster"},
                {"practice": "Use document checklist with borrower", "impact": "Fewer conditions"},
                {"practice": "Submit complete files", "impact": "Faster underwriting"}
            ],
            "volume": [
                {"practice": "Ask for referrals at key milestones", "impact": "30% more referrals"},
                {"practice": "Maintain database of past clients", "impact": "Repeat business"},
                {"practice": "Partner with top realtors", "impact": "Steady pipeline"}
            ]
        }

        category = input_data["category"]
        if category in practices:
            result = {category: practices[category]}
        else:
            result = practices

        return ToolResult(
            success=True,
            data={"best_practices": result},
            message=f"Best practices for {category}"
        )

    async def _schedule_coaching_session(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Schedule coaching session"""
        return ToolResult(
            success=True,
            data={
                "lo_id": input_data["lo_id"],
                "coach_id": input_data.get("coach_id"),
                "topic": input_data["topic"],
                "duration_minutes": input_data.get("duration_minutes", 30),
                "scheduled_at": (datetime.now() + timedelta(days=2)).isoformat(),
                "meeting_link": "https://meet.perennia.ai/coaching"
            },
            message=f"Coaching session scheduled: {input_data['topic']}"
        )

    async def _generate_performance_report(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate performance report using DB data with static fallback"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        lo_id = input_data["lo_id"]
        period_days = input_data.get("period_days", 30)

        report = {
            "lo_id": lo_id,
            "period_days": period_days,
            "generated_at": datetime.now().isoformat(),
        }

        db = SessionLocal()
        try:
            # Current period metrics
            current = db.execute(text("""
                SELECT
                    COUNT(*) as total_loans,
                    COALESCE(SUM(amount), 0) as total_volume,
                    AVG(amount) as avg_loan_size,
                    COUNT(CASE WHEN stage = 'FUNDED' THEN 1 END) as funded_count,
                    COUNT(CASE WHEN stage IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY') THEN 1 END) as fallout_count,
                    AVG(CASE WHEN funded_date IS NOT NULL AND application_date IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400
                    END) as avg_cycle_time
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND organization_id = :org_id
                AND created_at >= CURRENT_DATE - :days
            """), {"lo_id": lo_id, "org_id": org_id, "days": period_days}).fetchone()

            # Prior period for trend comparison
            prior = db.execute(text("""
                SELECT
                    COALESCE(SUM(amount), 0) as total_volume,
                    COUNT(CASE WHEN stage = 'FUNDED' THEN 1 END) as funded_count,
                    COUNT(*) as total_loans,
                    AVG(CASE WHEN funded_date IS NOT NULL AND application_date IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400
                    END) as avg_cycle_time
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND organization_id = :org_id
                AND created_at >= CURRENT_DATE - :prior_end
                AND created_at < CURRENT_DATE - :days
            """), {"lo_id": lo_id, "org_id": org_id, "days": period_days, "prior_end": period_days * 2}).fetchone()

            total_loans = current.total_loans or 0
            funded = current.funded_count or 0
            fallout = current.fallout_count or 0
            total_decisions = funded + fallout
            pull_through = round((funded / total_decisions) * 100, 1) if total_decisions > 0 else 0

            report["summary"] = {
                "total_loans": total_loans,
                "total_volume": float(current.total_volume or 0),
                "avg_loan_size": round(float(current.avg_loan_size or 0), 0),
                "pull_through": pull_through,
                "avg_cycle_time": round(float(current.avg_cycle_time or 0), 1) if current.avg_cycle_time else None,
                "funded_count": funded,
            }

            # Calculate trends vs prior period
            prior_volume = float(prior.total_volume or 0) if prior else 0
            prior_funded = prior.funded_count or 0 if prior else 0
            prior_total = prior.total_loans or 0 if prior else 0
            prior_decisions = prior_funded + (prior_total - prior_funded)  # approximate
            prior_cycle = float(prior.avg_cycle_time or 0) if prior and prior.avg_cycle_time else None

            def pct_change(curr, prev):
                if prev and prev > 0:
                    return round(((curr - prev) / prev) * 100, 1)
                return 0

            report["trends"] = {
                "volume_change": pct_change(float(current.total_volume or 0), prior_volume),
                "loan_count_change": pct_change(total_loans, prior_total),
                "cycle_time_change": pct_change(
                    float(current.avg_cycle_time or 0),
                    prior_cycle
                ) if current.avg_cycle_time and prior_cycle else None,
            }

            # Data-driven strengths and areas for improvement
            strengths = []
            areas_for_improvement = []

            if pull_through >= 70:
                strengths.append("Strong pull-through rate on pipeline loans")
            elif pull_through > 0:
                areas_for_improvement.append("Pull-through rate below 70% target")

            if current.avg_cycle_time and current.avg_cycle_time <= 35:
                strengths.append("Efficient cycle times from application to funding")
            elif current.avg_cycle_time and current.avg_cycle_time > 45:
                areas_for_improvement.append("Cycle time exceeds 45-day target")

            if report["trends"]["volume_change"] > 0:
                strengths.append(f"Volume trending up {report['trends']['volume_change']}% vs prior period")
            elif report["trends"]["volume_change"] < -10:
                areas_for_improvement.append(f"Volume declined {abs(report['trends']['volume_change'])}% vs prior period")

            if not strengths:
                strengths.append("Consistent pipeline activity")
            if not areas_for_improvement:
                areas_for_improvement.append("Continue focusing on volume growth")

            report["strengths"] = strengths
            report["areas_for_improvement"] = areas_for_improvement

        except Exception as e:
            logger.warning(f"DB query for performance report failed, using defaults: {e}")
            report["summary"] = {
                "total_loans": 0,
                "total_volume": 0,
                "avg_loan_size": 0,
                "pull_through": 0,
                "avg_cycle_time": None
            }
            report["trends"] = {
                "volume_change": 0,
                "loan_count_change": 0,
                "cycle_time_change": None
            }
            report["strengths"] = ["Unable to compute - database unavailable"]
            report["areas_for_improvement"] = ["Unable to compute - database unavailable"]
        finally:
            db.close()

        if input_data.get("include_recommendations", True):
            recommendations = []
            for area in report.get("areas_for_improvement", []):
                if "pull-through" in area.lower():
                    recommendations.append("Improve pre-qualification and set proper expectations early")
                elif "cycle time" in area.lower():
                    recommendations.append("Review document collection process and condition clearing timelines")
                elif "volume" in area.lower():
                    recommendations.append("Increase referral partner outreach and lead follow-up cadence")
            if not recommendations:
                recommendations.append("Schedule weekly pipeline review sessions to maintain momentum")
            report["recommendations"] = recommendations

        return ToolResult(
            success=True,
            data=report,
            message=f"Performance report generated for LO {lo_id}"
        )
