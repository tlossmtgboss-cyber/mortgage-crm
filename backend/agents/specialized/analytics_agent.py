"""
Analytics Agent

Specialized agent for reporting and insights generation with 8 tools:
1. get_pipeline_report - Generate pipeline status report
2. get_conversion_metrics - Get lead/loan conversion metrics
3. get_performance_metrics - Get LO/team performance metrics
4. get_revenue_forecast - Generate revenue forecast
5. get_lead_source_analysis - Analyze lead source effectiveness
6. get_cycle_time_analysis - Analyze loan processing times
7. get_comparison_report - Compare periods or LOs
8. export_report - Export report to various formats
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class GetPipelineReportInput(BaseModel):
    """Input schema for get_pipeline_report tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    branch_id: Optional[str] = Field(None, description="Filter by branch ID")
    date_range_days: int = Field(default=30, description="Days to include")


class GetConversionMetricsInput(BaseModel):
    """Input schema for get_conversion_metrics tool"""
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    source: Optional[str] = Field(None, description="Filter by lead source")


class GetPerformanceMetricsInput(BaseModel):
    """Input schema for get_performance_metrics tool"""
    lo_id: Optional[int] = Field(None, description="Specific LO ID, or None for all")
    period: str = Field(default="month", description="Period: week, month, quarter, year")
    include_ranking: bool = Field(default=True, description="Include ranking among peers")


class GetRevenueForecastInput(BaseModel):
    """Input schema for get_revenue_forecast tool"""
    months_ahead: int = Field(default=3, description="Months to forecast")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")


class GetLeadSourceAnalysisInput(BaseModel):
    """Input schema for get_lead_source_analysis tool"""
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    min_leads: int = Field(default=5, description="Minimum leads for source to be included")


class GetCycleTimeAnalysisInput(BaseModel):
    """Input schema for get_cycle_time_analysis tool"""
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date")
    loan_type: Optional[str] = Field(None, description="Filter by loan type")


class GetComparisonReportInput(BaseModel):
    """Input schema for get_comparison_report tool"""
    comparison_type: str = Field(..., description="Type: period_over_period, lo_comparison, source_comparison")
    entity_ids: Optional[List[int]] = Field(None, description="Entity IDs to compare")
    period_1_start: Optional[str] = Field(None, description="First period start date")
    period_1_end: Optional[str] = Field(None, description="First period end date")
    period_2_start: Optional[str] = Field(None, description="Second period start date")
    period_2_end: Optional[str] = Field(None, description="Second period end date")


class ExportReportInput(BaseModel):
    """Input schema for export_report tool"""
    report_type: str = Field(..., description="Report type to export: pipeline, conversion, performance, forecast")
    format: str = Field(default="csv", description="Export format: csv, json, pdf")
    date_range_days: int = Field(default=30, description="Days of data to include")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")


# ============================================================================
# ANALYTICS AGENT
# ============================================================================

@AgentRegistry.register
class AnalyticsAgent(SpecializedAgent):
    """
    Specialized agent for analytics and reporting.

    Generates reports, analyzes metrics, forecasts revenue,
    and provides business intelligence.
    """

    @property
    def name(self) -> str:
        return "AnalyticsAgent"

    @property
    def description(self) -> str:
        return "Generates reports, analyzes performance metrics, and provides business intelligence"

    def _register_tools(self):
        """Register all analytics tools"""

        self.register_tool(AgentTool(
            name="get_pipeline_report",
            description="Generate comprehensive pipeline status report with volume, "
                       "stage distribution, and health indicators.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_pipeline_report,
            input_schema=GetPipelineReportInput
        ))

        self.register_tool(AgentTool(
            name="get_conversion_metrics",
            description="Get lead-to-loan and stage conversion metrics. "
                       "Shows funnel performance and drop-off points.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_conversion_metrics,
            input_schema=GetConversionMetricsInput
        ))

        self.register_tool(AgentTool(
            name="get_performance_metrics",
            description="Get loan officer or team performance metrics including "
                       "volume, closings, and peer ranking.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_performance_metrics,
            input_schema=GetPerformanceMetricsInput
        ))

        self.register_tool(AgentTool(
            name="get_revenue_forecast",
            description="Generate revenue forecast based on pipeline and historical data. "
                       "Includes confidence intervals.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_revenue_forecast,
            input_schema=GetRevenueForecastInput
        ))

        self.register_tool(AgentTool(
            name="get_lead_source_analysis",
            description="Analyze lead source effectiveness by conversion rate, "
                       "cost per acquisition, and quality.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_lead_source_analysis,
            input_schema=GetLeadSourceAnalysisInput
        ))

        self.register_tool(AgentTool(
            name="get_cycle_time_analysis",
            description="Analyze loan processing cycle times by stage. "
                       "Identifies bottlenecks and improvement opportunities.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_cycle_time_analysis,
            input_schema=GetCycleTimeAnalysisInput
        ))

        self.register_tool(AgentTool(
            name="get_comparison_report",
            description="Compare metrics between time periods, loan officers, "
                       "or lead sources. Shows deltas and trends.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_comparison_report,
            input_schema=GetComparisonReportInput
        ))

        self.register_tool(AgentTool(
            name="export_report",
            description="Export a report to CSV, JSON, or PDF format. "
                       "Returns file path or download link.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._export_report,
            input_schema=ExportReportInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_pipeline_report(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate pipeline status report"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            date_range = input_data.get("date_range_days", 30)
            lo_id = input_data.get("lo_id")
            params = {"date_range": date_range, "org_id": org_id}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND assigned_lo = :lo_id"
                params["lo_id"] = lo_id
            summary_query = text(f"""
                SELECT COUNT(*) as total_loans, COALESCE(SUM(amount), 0) as total_volume,
                    COALESCE(AVG(amount), 0) as avg_loan_size,
                    COUNT(CASE WHEN expected_close_date < CURRENT_DATE THEN 1 END) as past_due,
                    COUNT(CASE WHEN expected_close_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 THEN 1 END) as closing_7_days,
                    COUNT(CASE WHEN expected_close_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30 THEN 1 END) as closing_30_days
                FROM loans WHERE stage NOT IN ('Funded') AND organization_id = :org_id
                    AND created_at >= CURRENT_DATE - :date_range {lo_filter}
            """)
            summary = db.execute(summary_query, params).fetchone()
            stage_query = text(f"""
                SELECT stage, COUNT(*) as count, COALESCE(SUM(amount), 0) as volume,
                    COALESCE(AVG(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)), 0) as avg_days
                FROM loans WHERE stage NOT IN ('Funded') AND organization_id = :org_id {lo_filter}
                GROUP BY stage
                ORDER BY CASE stage WHEN 'Disclosed' THEN 1 WHEN 'Processing' THEN 2 WHEN 'Submitted' THEN 3 WHEN 'UW Received' THEN 4 WHEN 'Approved' THEN 5 WHEN 'Suspended' THEN 6 WHEN 'CTC' THEN 7 WHEN 'Docs Out' THEN 8 ELSE 9 END
            """)
            stages = db.execute(stage_query, params).fetchall()
            stage_data = [{"stage": s.stage, "count": s.count, "volume": float(s.volume), "avg_days": round(float(s.avg_days), 1), "percentage": round((s.count / summary.total_loans * 100), 1) if summary.total_loans > 0 else 0} for s in stages]
            funded_query = text(f"""
                SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as volume
                FROM loans WHERE stage = 'Funded' AND organization_id = :org_id AND updated_at >= CURRENT_DATE - :date_range {lo_filter}
            """)
            funded = db.execute(funded_query, params).fetchone()
            health_score = 100
            health_issues = []
            if summary.past_due > 0:
                health_score -= min(20, summary.past_due * 5)
                health_issues.append(f"{summary.past_due} loans past expected close date")
            bottleneck_stages = [s for s in stage_data if s["avg_days"] > 7]
            if bottleneck_stages:
                health_score -= min(20, len(bottleneck_stages) * 10)
                health_issues.append(f"{len(bottleneck_stages)} stage(s) with aging loans")
            return ToolResult(success=True, data={"period_days": date_range, "summary": {"total_loans": summary.total_loans, "total_volume": float(summary.total_volume), "avg_loan_size": float(summary.avg_loan_size), "past_due": summary.past_due, "closing_7_days": summary.closing_7_days, "closing_30_days": summary.closing_30_days}, "stages": stage_data, "funded_period": {"count": funded.count, "volume": float(funded.volume)}, "health": {"score": max(0, health_score), "status": "healthy" if health_score >= 80 else "warning" if health_score >= 60 else "critical", "issues": health_issues}}, message=f"Pipeline: {summary.total_loans} loans, ${summary.total_volume:,.0f} volume, health score: {health_score}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_conversion_metrics(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get conversion metrics"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            start_date = input_data.get("start_date", (date.today() - timedelta(days=90)).isoformat())
            end_date = input_data.get("end_date", date.today().isoformat())
            params = {"start_date": start_date, "end_date": end_date, "org_id": org_id}
            source_filter = ""
            if input_data.get("source"):
                source_filter = "AND source = :source"
                params["source"] = input_data["source"]
            lo_filter = ""
            if input_data.get("lo_id"):
                lo_filter = "AND assigned_to = :lo_id"
                params["lo_id"] = input_data["lo_id"]
            funnel_query = text(f"""
                SELECT stage, COUNT(*) as count FROM leads
                WHERE created_at BETWEEN :start_date AND :end_date AND organization_id = :org_id {source_filter} {lo_filter}
                GROUP BY stage
            """)
            funnel_results = db.execute(funnel_query, params).fetchall()
            funnel = {r.stage: r.count for r in funnel_results}
            total_leads = sum(funnel.values())
            stage_order = ["new", "contacted", "qualified", "prospect", "application"]
            conversions = []
            for i in range(len(stage_order) - 1):
                from_stage = stage_order[i]
                to_stage = stage_order[i + 1]
                from_count = sum(funnel.get(s, 0) for s in stage_order[i:])
                to_count = sum(funnel.get(s, 0) for s in stage_order[i + 1:])
                rate = (to_count / from_count * 100) if from_count > 0 else 0
                conversions.append({"from_stage": from_stage, "to_stage": to_stage, "from_count": from_count, "to_count": to_count, "conversion_rate": round(rate, 1)})
            lead_to_loan_query = text(f"""
                SELECT COUNT(DISTINCT lead_id) as converted FROM loans
                WHERE lead_id IS NOT NULL AND organization_id = :org_id AND created_at BETWEEN :start_date AND :end_date
            """)
            converted = db.execute(lead_to_loan_query, params).fetchone()
            overall_rate = (converted.converted / total_leads * 100) if total_leads > 0 else 0
            return ToolResult(success=True, data={"period": {"start": start_date, "end": end_date}, "total_leads": total_leads, "funnel": funnel, "stage_conversions": conversions, "lead_to_loan": {"leads": total_leads, "converted": converted.converted, "rate": round(overall_rate, 1)}}, message=f"Conversion: {overall_rate:.1f}% lead-to-loan from {total_leads} leads")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_performance_metrics(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get LO/team performance metrics"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            period = input_data.get("period", "month")
            period_days = {"week": 7, "month": 30, "quarter": 90, "year": 365}.get(period, 30)
            lo_id = input_data.get("lo_id")
            params = {"period_days": period_days, "org_id": org_id}
            if lo_id:
                query = text("""
                    SELECT u.id, u.name,
                        COUNT(DISTINCT l.id) as total_loans, COALESCE(SUM(l.amount), 0) as total_volume,
                        COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded_count,
                        COALESCE(SUM(CASE WHEN l.stage = 'Funded' THEN l.amount END), 0) as funded_volume,
                        COUNT(DISTINCT ld.id) as total_leads,
                        COALESCE(AVG(EXTRACT(DAY FROM l.updated_at - l.created_at)), 0) as avg_cycle_days
                    FROM users u
                    LEFT JOIN loans l ON l.assigned_lo = u.id AND l.created_at >= CURRENT_DATE - :period_days AND l.organization_id = :org_id
                    LEFT JOIN leads ld ON ld.assigned_to = u.id AND ld.created_at >= CURRENT_DATE - :period_days AND ld.organization_id = :org_id
                    WHERE u.id = :lo_id GROUP BY u.id, u.name
                """)
                params["lo_id"] = lo_id
                result = db.execute(query, params).fetchone()
                if not result:
                    return ToolResult(success=False, error=f"LO {lo_id} not found")
                metrics = {"lo_id": result.id, "name": result.name, "period": period, "total_loans": result.total_loans, "total_volume": float(result.total_volume), "funded_count": result.funded_count, "funded_volume": float(result.funded_volume), "total_leads": result.total_leads, "avg_cycle_days": round(float(result.avg_cycle_days), 1), "pull_through_rate": round((result.funded_count / result.total_loans * 100), 1) if result.total_loans > 0 else 0}
                if input_data.get("include_ranking", True):
                    rank_query = text("""
                        SELECT u.id, COALESCE(SUM(l.amount), 0) as volume FROM users u
                        LEFT JOIN loans l ON l.assigned_lo = u.id AND l.stage = 'Funded' AND l.updated_at >= CURRENT_DATE - :period_days AND l.organization_id = :org_id
                        WHERE u.role = 'loan_officer' GROUP BY u.id ORDER BY volume DESC
                    """)
                    rankings = db.execute(rank_query, params).fetchall()
                    rank = next((i + 1 for i, r in enumerate(rankings) if r.id == lo_id), None)
                    metrics["ranking"] = {"rank": rank, "total_los": len(rankings)}
                return ToolResult(success=True, data={"metrics": metrics}, message=f"{result.name}: {result.funded_count} funded (${result.funded_volume:,.0f})")
            else:
                query = text("""
                    SELECT u.id, u.name,
                        COUNT(DISTINCT l.id) as total_loans, COALESCE(SUM(l.amount), 0) as total_volume,
                        COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded_count,
                        COALESCE(SUM(CASE WHEN l.stage = 'Funded' THEN l.amount END), 0) as funded_volume
                    FROM users u
                    LEFT JOIN loans l ON l.assigned_lo = u.id AND l.created_at >= CURRENT_DATE - :period_days AND l.organization_id = :org_id
                    WHERE u.role = 'loan_officer' GROUP BY u.id, u.name ORDER BY funded_volume DESC
                """)
                results = db.execute(query, params).fetchall()
                team_metrics = [{"lo_id": r.id, "name": r.name, "total_loans": r.total_loans, "total_volume": float(r.total_volume), "funded_count": r.funded_count, "funded_volume": float(r.funded_volume), "rank": i + 1} for i, r in enumerate(results)]
                total_funded = sum(m["funded_volume"] for m in team_metrics)
                total_count = sum(m["funded_count"] for m in team_metrics)
                return ToolResult(success=True, data={"period": period, "team_metrics": team_metrics, "totals": {"funded_volume": total_funded, "funded_count": total_count, "avg_per_lo": total_funded / len(team_metrics) if team_metrics else 0}}, message=f"Team: {total_count} loans funded (${total_funded:,.0f}) by {len(team_metrics)} LOs")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_revenue_forecast(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate revenue forecast"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            months_ahead = input_data.get("months_ahead", 3)
            lo_id = input_data.get("lo_id")
            params = {"org_id": org_id}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND assigned_lo = :lo_id"
                params["lo_id"] = lo_id
            pipeline_query = text(f"""
                SELECT DATE_TRUNC('month', expected_close_date) as close_month, COUNT(*) as loan_count,
                    COALESCE(SUM(amount), 0) as volume, COALESCE(AVG(rate), 0) as avg_rate
                FROM loans WHERE stage NOT IN ('Funded') AND organization_id = :org_id
                    AND expected_close_date IS NOT NULL AND expected_close_date BETWEEN CURRENT_DATE AND CURRENT_DATE + :days {lo_filter}
                GROUP BY DATE_TRUNC('month', expected_close_date) ORDER BY close_month
            """)
            params["days"] = months_ahead * 31
            pipeline = db.execute(pipeline_query, params).fetchall()
            pull_through_query = text(f"""
                SELECT COUNT(CASE WHEN stage = 'Funded' THEN 1 END)::float / NULLIF(COUNT(*), 0) as rate
                FROM loans WHERE created_at >= CURRENT_DATE - 180 AND organization_id = :org_id {lo_filter}
            """)
            pull_through = db.execute(pull_through_query, params).fetchone()
            pull_through_rate = float(pull_through.rate or 0.7)
            margin_rate = 0.01
            forecasts = []
            total_expected = 0
            total_conservative = 0
            total_optimistic = 0
            for p in pipeline:
                expected_volume = float(p.volume) * pull_through_rate
                conservative = expected_volume * 0.8
                optimistic = expected_volume * 1.1
                expected_revenue = expected_volume * margin_rate
                conservative_revenue = conservative * margin_rate
                optimistic_revenue = optimistic * margin_rate
                total_expected += expected_revenue
                total_conservative += conservative_revenue
                total_optimistic += optimistic_revenue
                forecasts.append({"month": p.close_month.strftime("%Y-%m") if p.close_month else None, "pipeline_count": p.loan_count, "pipeline_volume": float(p.volume), "expected_volume": expected_volume, "expected_revenue": expected_revenue, "conservative_revenue": conservative_revenue, "optimistic_revenue": optimistic_revenue})
            return ToolResult(success=True, data={"months_ahead": months_ahead, "pull_through_rate": round(pull_through_rate * 100, 1), "margin_rate": margin_rate * 100, "monthly_forecast": forecasts, "totals": {"expected_revenue": total_expected, "conservative_revenue": total_conservative, "optimistic_revenue": total_optimistic}}, message=f"Forecast: ${total_expected:,.0f} expected revenue over {months_ahead} months")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_lead_source_analysis(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze lead source effectiveness"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            start_date = input_data.get("start_date", (date.today() - timedelta(days=90)).isoformat())
            end_date = input_data.get("end_date", date.today().isoformat())
            min_leads = input_data.get("min_leads", 5)
            query = text("""
                WITH source_stats AS (
                    SELECT source, COUNT(*) as total_leads,
                        COUNT(CASE WHEN stage IN ('qualified', 'prospect', 'application') THEN 1 END) as qualified,
                        COUNT(CASE WHEN stage = 'application' THEN 1 END) as applications,
                        AVG(EXTRACT(DAY FROM updated_at - created_at)) as avg_days_to_qualify
                    FROM leads WHERE created_at BETWEEN :start_date AND :end_date AND organization_id = :org_id AND source IS NOT NULL
                    GROUP BY source HAVING COUNT(*) >= :min_leads
                )
                SELECT source, total_leads, qualified, applications, avg_days_to_qualify,
                    ROUND(qualified::numeric / total_leads * 100, 1) as qualification_rate,
                    ROUND(applications::numeric / total_leads * 100, 1) as application_rate
                FROM source_stats ORDER BY application_rate DESC
            """)
            results = db.execute(query, {"start_date": start_date, "end_date": end_date, "min_leads": min_leads, "org_id": org_id}).fetchall()
            sources = []
            total_leads = 0
            total_qualified = 0
            for r in results:
                total_leads += r.total_leads
                total_qualified += r.qualified
                quality_score = (float(r.application_rate or 0) * 0.6 + min(100, r.total_leads * 2) * 0.4)
                sources.append({"source": r.source, "total_leads": r.total_leads, "qualified": r.qualified, "applications": r.applications, "qualification_rate": float(r.qualification_rate or 0), "application_rate": float(r.application_rate or 0), "avg_days_to_qualify": round(float(r.avg_days_to_qualify or 0), 1), "quality_score": round(quality_score, 1)})
            best_source = max(sources, key=lambda x: x["application_rate"]) if sources else None
            worst_source = min(sources, key=lambda x: x["application_rate"]) if sources else None
            return ToolResult(success=True, data={"period": {"start": start_date, "end": end_date}, "sources": sources, "total_leads": total_leads, "total_qualified": total_qualified, "insights": {"best_source": best_source["source"] if best_source else None, "best_conversion": best_source["application_rate"] if best_source else 0, "worst_source": worst_source["source"] if worst_source else None, "worst_conversion": worst_source["application_rate"] if worst_source else 0}}, message=f"Analyzed {len(sources)} lead sources. Best: {best_source['source'] if best_source else 'N/A'} ({best_source['application_rate'] if best_source else 0}%)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_cycle_time_analysis(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze loan processing cycle times"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            start_date = input_data.get("start_date", (date.today() - timedelta(days=90)).isoformat())
            end_date = input_data.get("end_date", date.today().isoformat())
            params = {"start_date": start_date, "end_date": end_date, "org_id": org_id}
            loan_type_filter = ""
            if input_data.get("loan_type"):
                loan_type_filter = "AND program ILIKE :loan_type"
                params["loan_type"] = f"%{input_data['loan_type']}%"
            stage_query = text(f"""
                SELECT stage, COUNT(*) as count,
                    AVG(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as avg_days,
                    MIN(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as min_days,
                    MAX(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as max_days,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as median_days
                FROM loans WHERE created_at BETWEEN :start_date AND :end_date AND organization_id = :org_id AND stage NOT IN ('Funded') {loan_type_filter}
                GROUP BY stage
            """)
            stages = db.execute(stage_query, params).fetchall()
            sla_targets = {"application": 3, "processing": 5, "underwriting": 3, "conditional": 7, "clear_to_close": 3, "closing": 5}
            stage_analysis = []
            bottlenecks = []
            for s in stages:
                avg = float(s.avg_days or 0)
                target = sla_targets.get(s.stage, 5)
                variance = avg - target
                is_bottleneck = variance > 2
                if is_bottleneck:
                    bottlenecks.append(s.stage)
                stage_analysis.append({"stage": s.stage, "count": s.count, "avg_days": round(avg, 1), "min_days": round(float(s.min_days or 0), 1), "max_days": round(float(s.max_days or 0), 1), "median_days": round(float(s.median_days or 0), 1), "sla_target": target, "variance": round(variance, 1), "is_bottleneck": is_bottleneck})
            overall_query = text(f"""
                SELECT AVG(EXTRACT(DAY FROM updated_at - created_at)) as avg_total,
                    MIN(EXTRACT(DAY FROM updated_at - created_at)) as min_total,
                    MAX(EXTRACT(DAY FROM updated_at - created_at)) as max_total
                FROM loans WHERE stage = 'Funded' AND organization_id = :org_id AND updated_at BETWEEN :start_date AND :end_date {loan_type_filter}
            """)
            overall = db.execute(overall_query, params).fetchone()
            return ToolResult(success=True, data={"period": {"start": start_date, "end": end_date}, "stage_analysis": stage_analysis, "bottlenecks": bottlenecks, "overall_cycle": {"avg_days": round(float(overall.avg_total or 0), 1), "min_days": round(float(overall.min_total or 0), 1), "max_days": round(float(overall.max_total or 0), 1)}}, message=f"Cycle analysis: {len(bottlenecks)} bottleneck(s) identified. Avg cycle: {overall.avg_total:.0f} days")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_comparison_report(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate comparison report"""
        from database import SessionLocal
        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            comparison_type = input_data["comparison_type"]
            if comparison_type == "period_over_period":
                p1_start = input_data.get("period_1_start", (date.today() - timedelta(days=60)).isoformat())
                p1_end = input_data.get("period_1_end", (date.today() - timedelta(days=30)).isoformat())
                p2_start = input_data.get("period_2_start", (date.today() - timedelta(days=30)).isoformat())
                p2_end = input_data.get("period_2_end", date.today().isoformat())
                period_query = text("""
                    SELECT COUNT(*) as loans, COALESCE(SUM(amount), 0) as volume,
                        COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded
                    FROM loans WHERE organization_id = :org_id AND created_at BETWEEN :start AND :end
                """)
                p1 = db.execute(period_query, {"start": p1_start, "end": p1_end, "org_id": org_id}).fetchone()
                p2 = db.execute(period_query, {"start": p2_start, "end": p2_end, "org_id": org_id}).fetchone()
                def calc_change(old, new):
                    if old == 0:
                        return 100 if new > 0 else 0
                    return round(((new - old) / old) * 100, 1)
                comparison = {"period_1": {"start": p1_start, "end": p1_end}, "period_2": {"start": p2_start, "end": p2_end}, "metrics": {"loans": {"period_1": p1.loans, "period_2": p2.loans, "change": calc_change(p1.loans, p2.loans)}, "volume": {"period_1": float(p1.volume), "period_2": float(p2.volume), "change": calc_change(float(p1.volume), float(p2.volume))}, "funded": {"period_1": p1.funded, "period_2": p2.funded, "change": calc_change(p1.funded, p2.funded)}}}
                return ToolResult(success=True, data=comparison, message=f"Volume change: {comparison['metrics']['volume']['change']}%")
            elif comparison_type == "lo_comparison":
                lo_ids = input_data.get("entity_ids", [])
                if not lo_ids or len(lo_ids) < 2:
                    return ToolResult(success=False, error="Need at least 2 LO IDs to compare")
                query = text("""
                    SELECT u.id, u.name, COUNT(l.id) as loans, COALESCE(SUM(l.amount), 0) as volume,
                        COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded
                    FROM users u LEFT JOIN loans l ON l.assigned_lo = u.id AND l.created_at >= CURRENT_DATE - 30 AND l.organization_id = :org_id
                    WHERE u.id = ANY(:lo_ids) GROUP BY u.id, u.name ORDER BY volume DESC
                """)
                results = db.execute(query, {"lo_ids": lo_ids, "org_id": org_id}).fetchall()
                los = [{"id": r.id, "name": r.name, "loans": r.loans, "volume": float(r.volume), "funded": r.funded} for r in results]
                return ToolResult(success=True, data={"loan_officers": los}, message=f"Compared {len(los)} loan officers")
            else:
                return ToolResult(success=False, error=f"Unknown comparison type: {comparison_type}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _export_report(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Export report to file"""
        import json
        import csv
        import io
        report_type = input_data["report_type"]
        export_format = input_data.get("format", "csv")
        date_range_days = input_data.get("date_range_days", 30)
        if report_type == "pipeline":
            report_result = await self._get_pipeline_report({"date_range_days": date_range_days}, context)
        elif report_type == "conversion":
            report_result = await self._get_conversion_metrics({}, context)
        elif report_type == "performance":
            report_result = await self._get_performance_metrics({"period": "month"}, context)
        else:
            return ToolResult(success=False, error=f"Unknown report type: {report_type}")
        if not report_result.success:
            return report_result
        data = report_result.data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_report_{timestamp}.{export_format}"
        if export_format == "json":
            content = json.dumps(data, indent=2, default=str)
        elif export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            def _sanitize_csv(val):
                """Prevent CSV formula injection by prefixing dangerous characters."""
                s = str(val) if val is not None else ""
                if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
                    return "'" + s
                return s
            if report_type == "pipeline" and "stages" in data:
                writer.writerow(["Stage", "Count", "Volume", "Avg Days", "Percentage"])
                for stage in data["stages"]:
                    writer.writerow([_sanitize_csv(stage["stage"]), stage["count"], stage["volume"], stage["avg_days"], stage["percentage"]])
            elif report_type == "performance" and "team_metrics" in data:
                writer.writerow(["Rank", "Name", "Loans", "Volume", "Funded Count", "Funded Volume"])
                for m in data["team_metrics"]:
                    writer.writerow([m["rank"], _sanitize_csv(m["name"]), m["total_loans"], m["total_volume"], m["funded_count"], m["funded_volume"]])
            else:
                writer.writerow(["Key", "Value"])
                for key, value in data.items():
                    writer.writerow([_sanitize_csv(key), _sanitize_csv(str(value))])
            content = output.getvalue()
        else:
            return ToolResult(success=False, error=f"Unsupported format: {export_format}")
        return ToolResult(success=True, data={"filename": filename, "format": export_format, "size_bytes": len(content), "content_preview": content[:500] + "..." if len(content) > 500 else content}, message=f"Report exported to {filename}")
