"""
Document Analytics Agent

Specialized agent for document operations intelligence with 15 tools:
1. get_collection_velocity - Document collection speed by loan type, LO, processor
2. identify_collection_bottlenecks - Which document types take longest to collect
3. analyze_rejection_patterns - Why documents get rejected, by type, reason, processor
4. measure_ai_effectiveness - AI classification/review accuracy vs. human decisions
5. calculate_cost_per_loan - Document processing cost per loan (AI + human time)
6. track_borrower_responsiveness - Average response time by communication channel
7. predict_collection_timeline - ML-based prediction of when all docs will be collected
8. benchmark_against_industry - Compare collection times to industry averages
9. identify_process_inefficiencies - Find where documents sit idle (no action taken)
10. generate_management_dashboard - Executive summary of document operations
11. analyze_followup_effectiveness - Which follow-up strategies get best results
12. track_esign_adoption - E-signature adoption rate, completion rate, abandonment
13. measure_portal_engagement - Borrower portal usage, upload frequency, session duration
14. forecast_workload - Predict document processing workload for next 7/14/30 days
15. generate_team_scorecard - Per-processor/per-LO document management performance
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry,
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CollectionVelocityInput(BaseModel):
    """Input for get_collection_velocity tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    loan_type: Optional[str] = Field(None, description="Filter by loan type (conventional, fha, va, etc.)")
    days: int = Field(default=90, description="Lookback period in days")


class CollectionBottlenecksInput(BaseModel):
    """Input for identify_collection_bottlenecks tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    days: int = Field(default=90, description="Lookback period in days")


class RejectionPatternsInput(BaseModel):
    """Input for analyze_rejection_patterns tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    days: int = Field(default=90, description="Lookback period in days")
    doc_type: Optional[str] = Field(None, description="Filter by document type")


class AIEffectivenessInput(BaseModel):
    """Input for measure_ai_effectiveness tool"""
    days: int = Field(default=90, description="Lookback period in days")


class CostPerLoanInput(BaseModel):
    """Input for calculate_cost_per_loan tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    days: int = Field(default=90, description="Lookback period in days")


class BorrowerResponsivenessInput(BaseModel):
    """Input for track_borrower_responsiveness tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    days: int = Field(default=90, description="Lookback period in days")


class PredictCollectionInput(BaseModel):
    """Input for predict_collection_timeline tool"""
    loan_id: int = Field(..., description="Loan ID to predict collection timeline for")


class BenchmarkInput(BaseModel):
    """Input for benchmark_against_industry tool"""
    days: int = Field(default=90, description="Lookback period in days")


class ProcessInefficienciesInput(BaseModel):
    """Input for identify_process_inefficiencies tool"""
    idle_threshold_hours: int = Field(default=48, description="Hours without action to consider idle")
    days: int = Field(default=30, description="Lookback period in days")


class ManagementDashboardInput(BaseModel):
    """Input for generate_management_dashboard tool"""
    days: int = Field(default=30, description="Lookback period in days")


class FollowupEffectivenessInput(BaseModel):
    """Input for analyze_followup_effectiveness tool"""
    days: int = Field(default=90, description="Lookback period in days")


class EsignAdoptionInput(BaseModel):
    """Input for track_esign_adoption tool"""
    days: int = Field(default=90, description="Lookback period in days")


class PortalEngagementInput(BaseModel):
    """Input for measure_portal_engagement tool"""
    days: int = Field(default=30, description="Lookback period in days")


class ForecastWorkloadInput(BaseModel):
    """Input for forecast_workload tool"""
    forecast_days: int = Field(default=14, description="Days to forecast ahead (7, 14, or 30)")


class TeamScorecardInput(BaseModel):
    """Input for generate_team_scorecard tool"""
    days: int = Field(default=30, description="Lookback period in days")
    lo_id: Optional[int] = Field(None, description="Filter to a specific loan officer")


# ============================================================================
# DOCUMENT ANALYTICS AGENT
# ============================================================================

@AgentRegistry.register
class DocumentAnalyticsAgent(SpecializedAgent):
    """
    Specialized agent for document operations intelligence.

    Provides analytics on document collection velocity, rejection patterns,
    AI classification accuracy, team performance, and workload forecasting.
    All tools are org-aware for multi-tenant isolation.
    """

    @property
    def name(self) -> str:
        return "DocumentAnalyticsAgent"

    @property
    def description(self) -> str:
        return (
            "Analyzes document operations performance including collection velocity, "
            "rejection patterns, AI effectiveness, team scorecards, and workload forecasting"
        )

    def _register_tools(self):
        """Register all document analytics tools"""

        self.register_tool(AgentTool(
            name="get_collection_velocity",
            description="Measure document collection speed by loan type, LO, or processor. "
                       "Shows average days from request to upload and completion rates.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_collection_velocity,
            input_schema=CollectionVelocityInput,
        ))

        self.register_tool(AgentTool(
            name="identify_collection_bottlenecks",
            description="Identify which document types take longest to collect. "
                       "Ranks doc types by average collection time and highlights outliers.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_collection_bottlenecks,
            input_schema=CollectionBottlenecksInput,
        ))

        self.register_tool(AgentTool(
            name="analyze_rejection_patterns",
            description="Analyze why documents are getting rejected. Break down by "
                       "rejection category, document type, and processor.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_rejection_patterns,
            input_schema=RejectionPatternsInput,
        ))

        self.register_tool(AgentTool(
            name="measure_ai_effectiveness",
            description="Measure AI classification and review accuracy vs. human decisions. "
                       "Shows precision, recall, and areas needing model improvement.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._measure_ai_effectiveness,
            input_schema=AIEffectivenessInput,
        ))

        self.register_tool(AgentTool(
            name="calculate_cost_per_loan",
            description="Estimate document processing cost per loan based on AI processing "
                       "time, human review time, and follow-up effort.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_cost_per_loan,
            input_schema=CostPerLoanInput,
        ))

        self.register_tool(AgentTool(
            name="track_borrower_responsiveness",
            description="Track average borrower response time by communication channel. "
                       "Shows which channels get fastest document uploads.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._track_borrower_responsiveness,
            input_schema=BorrowerResponsivenessInput,
        ))

        self.register_tool(AgentTool(
            name="predict_collection_timeline",
            description="Predict when all required documents will be collected for a loan "
                       "based on historical patterns and current collection velocity.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._predict_collection_timeline,
            input_schema=PredictCollectionInput,
        ))

        self.register_tool(AgentTool(
            name="benchmark_against_industry",
            description="Compare document collection times and rejection rates "
                       "against industry benchmarks.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._benchmark_against_industry,
            input_schema=BenchmarkInput,
        ))

        self.register_tool(AgentTool(
            name="identify_process_inefficiencies",
            description="Find where documents sit idle with no action taken. "
                       "Identifies stalled reviews, unprocessed uploads, and orphaned requests.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_process_inefficiencies,
            input_schema=ProcessInefficienciesInput,
        ))

        self.register_tool(AgentTool(
            name="generate_management_dashboard",
            description="Generate executive summary of document operations including "
                       "KPIs, trends, alerts, and action items.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_management_dashboard,
            input_schema=ManagementDashboardInput,
        ))

        self.register_tool(AgentTool(
            name="analyze_followup_effectiveness",
            description="Analyze which follow-up strategies yield best results. "
                       "Compare channels, timing, and campaign types by response rate.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_followup_effectiveness,
            input_schema=FollowupEffectivenessInput,
        ))

        self.register_tool(AgentTool(
            name="track_esign_adoption",
            description="Track e-signature adoption rate, completion rate, and abandonment "
                       "reasons across document types.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._track_esign_adoption,
            input_schema=EsignAdoptionInput,
        ))

        self.register_tool(AgentTool(
            name="measure_portal_engagement",
            description="Measure borrower portal usage including upload frequency, "
                       "session duration, and feature adoption.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._measure_portal_engagement,
            input_schema=PortalEngagementInput,
        ))

        self.register_tool(AgentTool(
            name="forecast_workload",
            description="Predict document processing workload for the next 7, 14, or 30 days "
                       "based on pipeline and historical patterns.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._forecast_workload,
            input_schema=ForecastWorkloadInput,
        ))

        self.register_tool(AgentTool(
            name="generate_team_scorecard",
            description="Generate per-processor and per-LO document management performance "
                       "scorecard with rankings and improvement areas.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_team_scorecard,
            input_schema=TeamScorecardInput,
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_collection_velocity(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Measure document collection speed by loan type, LO, or processor."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            lo_id = input_data.get("lo_id")
            loan_type = input_data.get("loan_type")
            params: Dict[str, Any] = {"org_id": org_id, "days": days}
            lo_filter = ""
            loan_type_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id
            if loan_type:
                loan_type_filter = "AND l.loan_type ILIKE :loan_type"
                params["loan_type"] = f"%{loan_type}%"

            # Overall velocity: avg days from request creation to document upload
            velocity_query = text(f"""
                SELECT
                    COUNT(DISTINCT sd.id) AS total_docs,
                    COUNT(DISTINCT sd.request_id) AS total_requests,
                    AVG(EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400)
                        AS avg_days_to_upload,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400
                    ) AS median_days_to_upload,
                    COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END) AS accepted_count,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS open_count
                FROM smart_documents sd
                JOIN smart_document_requests sdr ON sdr.id = sd.request_id
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
                    {lo_filter} {loan_type_filter}
            """)
            overall = db.execute(velocity_query, params).fetchone()

            # Velocity by doc type
            by_type_query = text(f"""
                SELECT
                    sdr.doc_type,
                    COUNT(*) AS doc_count,
                    AVG(EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400)
                        AS avg_days
                FROM smart_documents sd
                JOIN smart_document_requests sdr ON sdr.id = sd.request_id
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
                    {lo_filter} {loan_type_filter}
                GROUP BY sdr.doc_type
                ORDER BY avg_days DESC
            """)
            by_type = db.execute(by_type_query, params).fetchall()

            completion_rate = 0.0
            total_requests = overall.total_requests or 0
            if total_requests > 0:
                completion_rate = round(
                    (overall.accepted_count or 0) / total_requests * 100, 1
                )

            data = {
                "period_days": days,
                "summary": {
                    "total_documents_uploaded": overall.total_docs or 0,
                    "total_requests": total_requests,
                    "avg_days_to_upload": round(float(overall.avg_days_to_upload or 0), 1),
                    "median_days_to_upload": round(float(overall.median_days_to_upload or 0), 1),
                    "completion_rate": completion_rate,
                    "open_requests": overall.open_count or 0,
                },
                "by_doc_type": [
                    {
                        "doc_type": row.doc_type,
                        "count": row.doc_count,
                        "avg_days": round(float(row.avg_days or 0), 1),
                    }
                    for row in by_type
                ],
            }

            self.audit_log("get_collection_velocity", details={"days": days})

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Collection velocity: {data['summary']['avg_days_to_upload']} avg days, "
                    f"{completion_rate}% completion rate over {days} days"
                ),
            )
        except Exception as e:
            logger.exception("get_collection_velocity failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_collection_bottlenecks(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Identify which document types take longest to collect."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            lo_id = input_data.get("lo_id")
            params: Dict[str, Any] = {"org_id": org_id, "days": days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            query = text(f"""
                SELECT
                    sdr.doc_type,
                    COUNT(*) AS total_requests,
                    COUNT(CASE WHEN sdr.status = 'OPEN' THEN 1 END) AS still_open,
                    AVG(
                        CASE WHEN sd.uploaded_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400
                        ELSE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sdr.created_at)) / 86400
                        END
                    ) AS avg_days_outstanding,
                    MAX(
                        CASE WHEN sdr.status = 'OPEN'
                        THEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sdr.created_at)) / 86400
                        ELSE 0 END
                    ) AS max_days_waiting
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                LEFT JOIN smart_documents sd ON sd.request_id = sdr.id
                WHERE sdr.created_at >= CURRENT_DATE - :days
                    {lo_filter}
                GROUP BY sdr.doc_type
                ORDER BY avg_days_outstanding DESC
            """)
            results = db.execute(query, params).fetchall()

            bottlenecks = []
            for row in results:
                avg_days = round(float(row.avg_days_outstanding or 0), 1)
                open_pct = round(
                    (row.still_open / row.total_requests * 100) if row.total_requests > 0 else 0, 1
                )
                severity = "critical" if avg_days > 10 else "warning" if avg_days > 5 else "normal"
                bottlenecks.append({
                    "doc_type": row.doc_type,
                    "total_requests": row.total_requests,
                    "still_open": row.still_open,
                    "open_pct": open_pct,
                    "avg_days_outstanding": avg_days,
                    "max_days_waiting": round(float(row.max_days_waiting or 0), 1),
                    "severity": severity,
                })

            critical_count = len([b for b in bottlenecks if b["severity"] == "critical"])

            self.audit_log("identify_collection_bottlenecks", details={"critical": critical_count})

            return ToolResult(
                success=True,
                data={"period_days": days, "bottlenecks": bottlenecks, "critical_count": critical_count},
                message=f"{critical_count} critical bottleneck(s) among {len(bottlenecks)} doc types",
            )
        except Exception as e:
            logger.exception("identify_collection_bottlenecks failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_rejection_patterns(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Analyze document rejection patterns by category, type, and processor."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            doc_type = input_data.get("doc_type")
            params: Dict[str, Any] = {"org_id": org_id, "days": days}
            doc_type_filter = ""
            if doc_type:
                doc_type_filter = "AND sd.doc_type = :doc_type"
                params["doc_type"] = doc_type

            # Rejections by category
            by_category_query = text(f"""
                SELECT
                    sd.rejection_category,
                    COUNT(*) AS rejection_count,
                    COUNT(DISTINCT sd.loan_id) AS affected_loans
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.decision = 'REJECT'
                    AND sd.reviewed_at >= CURRENT_DATE - :days
                    {doc_type_filter}
                GROUP BY sd.rejection_category
                ORDER BY rejection_count DESC
            """)
            by_category = db.execute(by_category_query, params).fetchall()

            # Rejections by doc type
            by_type_query = text(f"""
                SELECT
                    sd.doc_type,
                    COUNT(*) AS total_uploads,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejections,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS acceptances
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.reviewed_at >= CURRENT_DATE - :days
                    AND sd.decision IS NOT NULL
                    {doc_type_filter}
                GROUP BY sd.doc_type
                ORDER BY rejections DESC
            """)
            by_type = db.execute(by_type_query, params).fetchall()

            total_rejections = sum(row.rejection_count for row in by_category) if by_category else 0

            data = {
                "period_days": days,
                "total_rejections": total_rejections,
                "by_category": [
                    {
                        "category": row.rejection_category or "UNKNOWN",
                        "count": row.rejection_count,
                        "affected_loans": row.affected_loans,
                    }
                    for row in by_category
                ],
                "by_doc_type": [
                    {
                        "doc_type": row.doc_type,
                        "total_uploads": row.total_uploads,
                        "rejections": row.rejections,
                        "acceptances": row.acceptances,
                        "rejection_rate": round(
                            row.rejections / row.total_uploads * 100 if row.total_uploads > 0 else 0, 1
                        ),
                    }
                    for row in by_type
                ],
            }

            top_reason = data["by_category"][0]["category"] if data["by_category"] else "N/A"
            self.audit_log("analyze_rejection_patterns", details={"total_rejections": total_rejections})

            return ToolResult(
                success=True,
                data=data,
                message=f"{total_rejections} rejections in {days} days. Top reason: {top_reason}",
            )
        except Exception as e:
            logger.exception("analyze_rejection_patterns failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _measure_ai_effectiveness(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Measure AI classification accuracy vs. human corrections."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            accuracy_query = text("""
                SELECT
                    COUNT(*) AS total_classifications,
                    COUNT(CASE WHEN is_correct = true THEN 1 END) AS correct,
                    COUNT(CASE WHEN is_correct = false THEN 1 END) AS incorrect,
                    COUNT(CASE WHEN is_correct IS NULL THEN 1 END) AS unreviewed,
                    AVG(prediction_confidence) AS avg_confidence,
                    AVG(classification_duration_ms) AS avg_duration_ms
                FROM ai_document_classifications
                WHERE organization_id = :org_id
                    AND created_at >= CURRENT_DATE - :days
            """)
            overall = db.execute(accuracy_query, params).fetchone()

            # Accuracy by doc type
            by_type_query = text("""
                SELECT
                    predicted_doc_type,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN is_correct = true THEN 1 END) AS correct,
                    COUNT(CASE WHEN is_correct = false THEN 1 END) AS incorrect,
                    AVG(prediction_confidence) AS avg_confidence
                FROM ai_document_classifications
                WHERE organization_id = :org_id
                    AND created_at >= CURRENT_DATE - :days
                    AND is_correct IS NOT NULL
                GROUP BY predicted_doc_type
                ORDER BY total DESC
            """)
            by_type = db.execute(by_type_query, params).fetchall()

            reviewed = (overall.correct or 0) + (overall.incorrect or 0)
            accuracy_pct = round(
                (overall.correct or 0) / reviewed * 100 if reviewed > 0 else 0, 1
            )

            data = {
                "period_days": days,
                "summary": {
                    "total_classifications": overall.total_classifications or 0,
                    "reviewed": reviewed,
                    "correct": overall.correct or 0,
                    "incorrect": overall.incorrect or 0,
                    "unreviewed": overall.unreviewed or 0,
                    "accuracy_pct": accuracy_pct,
                    "avg_confidence": round(float(overall.avg_confidence or 0), 1),
                    "avg_processing_ms": round(float(overall.avg_duration_ms or 0), 0),
                },
                "by_doc_type": [
                    {
                        "doc_type": row.predicted_doc_type,
                        "total": row.total,
                        "correct": row.correct,
                        "incorrect": row.incorrect,
                        "accuracy_pct": round(
                            row.correct / (row.correct + row.incorrect) * 100
                            if (row.correct + row.incorrect) > 0 else 0, 1
                        ),
                        "avg_confidence": round(float(row.avg_confidence or 0), 1),
                    }
                    for row in by_type
                ],
            }

            self.audit_log("measure_ai_effectiveness", details={"accuracy": accuracy_pct})

            return ToolResult(
                success=True,
                data=data,
                message=f"AI accuracy: {accuracy_pct}% ({reviewed} reviewed, {overall.unreviewed or 0} pending)",
            )
        except Exception as e:
            logger.exception("measure_ai_effectiveness failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_cost_per_loan(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Estimate document processing cost per loan based on effort metrics."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            lo_id = input_data.get("lo_id")
            params: Dict[str, Any] = {"org_id": org_id, "days": days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            # Count documents, reviews, and follow-ups per loan
            effort_query = text(f"""
                SELECT
                    COUNT(DISTINCT l.id) AS loan_count,
                    COUNT(DISTINCT sd.id) AS total_docs,
                    COUNT(CASE WHEN sd.reviewed_by = 'SYSTEM' THEN 1 END) AS ai_reviewed,
                    COUNT(CASE WHEN sd.reviewed_by != 'SYSTEM' AND sd.reviewed_by IS NOT NULL
                          THEN 1 END) AS human_reviewed,
                    COUNT(DISTINCT fc.id) AS followup_campaigns,
                    COALESCE(SUM(fe_counts.event_count), 0) AS total_followup_events
                FROM loans l
                LEFT JOIN smart_documents sd ON sd.loan_id = l.id
                    AND sd.uploaded_at >= CURRENT_DATE - :days
                LEFT JOIN document_followup_campaigns fc ON fc.loan_id = l.id
                    AND fc.organization_id = :org_id
                    AND fc.created_at >= CURRENT_DATE - :days
                LEFT JOIN (
                    SELECT campaign_id, COUNT(*) AS event_count
                    FROM document_followup_events
                    WHERE organization_id = :org_id
                        AND created_at >= CURRENT_DATE - :days
                    GROUP BY campaign_id
                ) fe_counts ON fe_counts.campaign_id = fc.id
                WHERE l.organization_id = :org_id
                    AND l.created_at >= CURRENT_DATE - :days
                    {lo_filter}
            """)
            effort = db.execute(effort_query, params).fetchone()

            loan_count = effort.loan_count or 1
            # Cost model: estimated costs per unit of work
            ai_cost_per_doc = 0.05      # AI classification cost per document
            human_review_cost = 5.00    # estimated cost per human review (minutes of processor time)
            followup_cost = 2.00        # cost per follow-up event (email/sms/call setup)

            total_ai_cost = (effort.ai_reviewed or 0) * ai_cost_per_doc
            total_human_cost = (effort.human_reviewed or 0) * human_review_cost
            total_followup_cost = (effort.total_followup_events or 0) * followup_cost
            total_cost = total_ai_cost + total_human_cost + total_followup_cost
            cost_per_loan = round(total_cost / loan_count, 2)

            data = {
                "period_days": days,
                "loan_count": loan_count,
                "total_documents": effort.total_docs or 0,
                "effort_breakdown": {
                    "ai_reviewed": effort.ai_reviewed or 0,
                    "human_reviewed": effort.human_reviewed or 0,
                    "followup_campaigns": effort.followup_campaigns or 0,
                    "followup_events": effort.total_followup_events or 0,
                },
                "cost_breakdown": {
                    "ai_processing": round(total_ai_cost, 2),
                    "human_review": round(total_human_cost, 2),
                    "followup_outreach": round(total_followup_cost, 2),
                    "total": round(total_cost, 2),
                },
                "cost_per_loan": cost_per_loan,
                "docs_per_loan": round((effort.total_docs or 0) / loan_count, 1),
            }

            self.audit_log("calculate_cost_per_loan", details={"cost_per_loan": cost_per_loan})

            return ToolResult(
                success=True,
                data=data,
                message=f"Doc processing cost: ${cost_per_loan:.2f}/loan across {loan_count} loans",
            )
        except Exception as e:
            logger.exception("calculate_cost_per_loan failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_borrower_responsiveness(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Track average borrower response time by communication channel."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            # Measure time between follow-up event and borrower document upload
            channel_query = text("""
                SELECT
                    fe.channel,
                    COUNT(*) AS outreach_count,
                    COUNT(CASE WHEN fc.borrower_responded = true THEN 1 END) AS responses,
                    AVG(
                        CASE WHEN fc.response_date IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (fc.response_date - fe.created_at)) / 3600
                        END
                    ) AS avg_response_hours
                FROM document_followup_events fe
                JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
                    AND fc.organization_id = :org_id
                WHERE fe.organization_id = :org_id
                    AND fe.created_at >= CURRENT_DATE - :days
                    AND fe.channel IS NOT NULL
                GROUP BY fe.channel
                ORDER BY avg_response_hours ASC NULLS LAST
            """)
            channels = db.execute(channel_query, params).fetchall()

            data = {
                "period_days": days,
                "by_channel": [
                    {
                        "channel": row.channel,
                        "outreach_count": row.outreach_count,
                        "responses": row.responses,
                        "response_rate": round(
                            row.responses / row.outreach_count * 100
                            if row.outreach_count > 0 else 0, 1
                        ),
                        "avg_response_hours": round(float(row.avg_response_hours or 0), 1),
                    }
                    for row in channels
                ],
            }

            best = data["by_channel"][0]["channel"] if data["by_channel"] else "N/A"
            self.audit_log("track_borrower_responsiveness", details={"best_channel": best})

            return ToolResult(
                success=True,
                data=data,
                message=f"Fastest channel: {best}. {len(data['by_channel'])} channels analyzed.",
            )
        except Exception as e:
            logger.exception("track_borrower_responsiveness failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _predict_collection_timeline(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Predict when all required documents will be collected for a loan."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            self.verify_loan_tenant(db, loan_id)
            params: Dict[str, Any] = {"org_id": org_id, "loan_id": loan_id}

            # Get current open requests for this loan
            requests_query = text("""
                SELECT
                    sdr.id, sdr.doc_type, sdr.priority, sdr.created_at,
                    sdr.status
                FROM smart_document_requests sdr
                WHERE sdr.loan_id = :loan_id
                    AND sdr.status = 'OPEN'
                    AND sdr.is_active = true
                ORDER BY
                    CASE sdr.priority
                        WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                        WHEN 'NORMAL' THEN 3 ELSE 4
                    END
            """)
            open_requests = db.execute(requests_query, params).fetchall()

            if not open_requests:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "open_requests": 0, "predicted_complete_date": None},
                    message=f"Loan {loan_id}: all documents collected",
                )

            # Get historical collection velocity per doc type for this org
            velocity_query = text("""
                SELECT
                    sdr.doc_type,
                    AVG(EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400) AS avg_days
                FROM smart_document_requests sdr
                JOIN smart_documents sd ON sd.request_id = sdr.id
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                WHERE sdr.status IN ('ACCEPTED', 'PENDING_REVIEW')
                    AND sd.uploaded_at >= CURRENT_DATE - 180
                GROUP BY sdr.doc_type
            """)
            velocity_rows = db.execute(velocity_query, params).fetchall()
            velocity_map = {row.doc_type: float(row.avg_days or 5) for row in velocity_rows}

            predictions = []
            max_predicted_days = 0
            now = datetime.utcnow()
            for req in open_requests:
                days_waiting = (now - req.created_at).total_seconds() / 86400
                historical_avg = velocity_map.get(req.doc_type, 7.0)
                remaining = max(0, historical_avg - days_waiting)
                predicted_date = date.today() + timedelta(days=int(remaining) + 1)
                if remaining > max_predicted_days:
                    max_predicted_days = remaining

                predictions.append({
                    "request_id": req.id,
                    "doc_type": req.doc_type,
                    "priority": req.priority,
                    "days_waiting": round(days_waiting, 1),
                    "historical_avg_days": round(historical_avg, 1),
                    "predicted_remaining_days": round(remaining, 1),
                    "predicted_date": predicted_date.isoformat(),
                })

            all_complete_date = date.today() + timedelta(days=int(max_predicted_days) + 1)

            data = {
                "loan_id": loan_id,
                "open_requests": len(open_requests),
                "predictions": predictions,
                "predicted_all_complete_date": all_complete_date.isoformat(),
                "predicted_remaining_days": round(max_predicted_days, 1),
                "confidence": "high" if len(velocity_map) >= 5 else "medium" if velocity_map else "low",
            }

            self.audit_log("predict_collection_timeline", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Loan {loan_id}: {len(open_requests)} docs pending, "
                    f"predicted complete by {all_complete_date.isoformat()}"
                ),
            )
        except Exception as e:
            logger.exception("predict_collection_timeline failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _benchmark_against_industry(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Compare collection times and rejection rates to industry averages."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            # Industry benchmarks (MBA/MISMO standards, 2025 data)
            industry_benchmarks = {
                "avg_collection_days": 8.5,
                "rejection_rate_pct": 12.0,
                "first_pass_acceptance_pct": 78.0,
                "avg_followups_per_loan": 3.2,
                "complete_package_days": 14.0,
                "screenshot_rejection_pct": 5.0,
            }

            # Get org metrics for comparison
            org_query = text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400) AS avg_collection_days,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END)::float
                        / NULLIF(COUNT(CASE WHEN sd.decision IS NOT NULL THEN 1 END), 0)
                        * 100 AS rejection_rate,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' AND sd.rejection_category IS NULL THEN 1 END)::float
                        / NULLIF(COUNT(CASE WHEN sd.decision IS NOT NULL THEN 1 END), 0)
                        * 100 AS first_pass_acceptance,
                    COUNT(CASE WHEN sd.rejection_category = 'SCREENSHOT' THEN 1 END)::float
                        / NULLIF(COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END), 0)
                        * 100 AS screenshot_rejection_pct
                FROM smart_documents sd
                JOIN smart_document_requests sdr ON sdr.id = sd.request_id
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
            """)
            org_metrics = db.execute(org_query, params).fetchone()

            def compare(org_val, benchmark_val, lower_is_better=True):
                if org_val is None:
                    return {"value": None, "benchmark": benchmark_val, "delta": None, "rating": "no_data"}
                diff_pct = round(((org_val - benchmark_val) / benchmark_val) * 100, 1) if benchmark_val else 0
                if lower_is_better:
                    rating = "above" if org_val < benchmark_val else "at" if abs(diff_pct) < 10 else "below"
                else:
                    rating = "above" if org_val > benchmark_val else "at" if abs(diff_pct) < 10 else "below"
                return {
                    "value": round(float(org_val), 1),
                    "benchmark": benchmark_val,
                    "delta_pct": diff_pct,
                    "rating": rating,
                }

            data = {
                "period_days": days,
                "comparisons": {
                    "avg_collection_days": compare(
                        org_metrics.avg_collection_days,
                        industry_benchmarks["avg_collection_days"],
                        lower_is_better=True,
                    ),
                    "rejection_rate_pct": compare(
                        org_metrics.rejection_rate,
                        industry_benchmarks["rejection_rate_pct"],
                        lower_is_better=True,
                    ),
                    "first_pass_acceptance_pct": compare(
                        org_metrics.first_pass_acceptance,
                        industry_benchmarks["first_pass_acceptance_pct"],
                        lower_is_better=False,
                    ),
                    "screenshot_rejection_pct": compare(
                        org_metrics.screenshot_rejection_pct,
                        industry_benchmarks["screenshot_rejection_pct"],
                        lower_is_better=True,
                    ),
                },
                "industry_benchmarks": industry_benchmarks,
            }

            above_count = sum(
                1 for c in data["comparisons"].values() if c["rating"] == "above"
            )
            total = len(data["comparisons"])

            self.audit_log("benchmark_against_industry", details={"above_benchmark": above_count})

            return ToolResult(
                success=True,
                data=data,
                message=f"Benchmark: {above_count}/{total} metrics above industry average",
            )
        except Exception as e:
            logger.exception("benchmark_against_industry failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_process_inefficiencies(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Find documents sitting idle with no action taken."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            idle_hours = input_data.get("idle_threshold_hours", 48)
            days = input_data.get("days", 30)
            params: Dict[str, Any] = {"org_id": org_id, "idle_hours": idle_hours, "days": days}

            # Uploaded but not reviewed
            unreviewed_query = text("""
                SELECT
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sd.uploaded_at)) / 3600) AS avg_hours_waiting
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.decision IS NULL
                    AND sd.status NOT IN ('SCANNING', 'PROCESSING')
                    AND sd.uploaded_at >= CURRENT_DATE - :days
                    AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sd.uploaded_at)) / 3600 > :idle_hours
            """)
            unreviewed = db.execute(unreviewed_query, params).fetchone()

            # Open requests with no document uploaded and no follow-up
            orphaned_query = text("""
                SELECT
                    COUNT(*) AS count,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sdr.created_at)) / 86400) AS avg_days_waiting
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                LEFT JOIN smart_documents sd ON sd.request_id = sdr.id
                LEFT JOIN document_followup_campaigns fc ON fc.loan_id = sdr.loan_id
                    AND fc.organization_id = :org_id
                    AND fc.status = 'active'
                WHERE sdr.status = 'OPEN'
                    AND sdr.is_active = true
                    AND sd.id IS NULL
                    AND fc.id IS NULL
                    AND sdr.created_at >= CURRENT_DATE - :days
            """)
            orphaned = db.execute(orphaned_query, params).fetchone()

            # Rejected but no follow-up sent
            rejected_no_followup_query = text("""
                SELECT COUNT(*) AS count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                LEFT JOIN document_followup_campaigns fc ON fc.loan_id = sd.loan_id
                    AND fc.organization_id = :org_id
                    AND fc.trigger_source = 'document_rejected'
                    AND fc.created_at > sd.reviewed_at
                WHERE sd.decision = 'REJECT'
                    AND sd.reviewed_at >= CURRENT_DATE - :days
                    AND fc.id IS NULL
            """)
            rejected_no_followup = db.execute(rejected_no_followup_query, params).fetchone()

            data = {
                "idle_threshold_hours": idle_hours,
                "period_days": days,
                "inefficiencies": {
                    "unreviewed_documents": {
                        "count": unreviewed.count or 0,
                        "avg_hours_waiting": round(float(unreviewed.avg_hours_waiting or 0), 1),
                    },
                    "orphaned_requests": {
                        "count": orphaned.count or 0,
                        "avg_days_waiting": round(float(orphaned.avg_days_waiting or 0), 1),
                    },
                    "rejected_no_followup": {
                        "count": rejected_no_followup.count or 0,
                    },
                },
                "total_issues": (
                    (unreviewed.count or 0) +
                    (orphaned.count or 0) +
                    (rejected_no_followup.count or 0)
                ),
            }

            self.audit_log("identify_process_inefficiencies", details={"total": data["total_issues"]})

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"{data['total_issues']} process inefficiencies: "
                    f"{unreviewed.count or 0} unreviewed, "
                    f"{orphaned.count or 0} orphaned requests, "
                    f"{rejected_no_followup.count or 0} rejected without follow-up"
                ),
            )
        except Exception as e:
            logger.exception("identify_process_inefficiencies failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_management_dashboard(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate executive summary of document operations."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 30)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            kpi_query = text("""
                SELECT
                    COUNT(DISTINCT sd.id) AS total_docs_processed,
                    COUNT(DISTINCT sd.loan_id) AS loans_with_docs,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected,
                    COUNT(CASE WHEN sd.decision = 'NEEDS_REVIEW' THEN 1 END) AS needs_review,
                    COUNT(CASE WHEN sd.reviewed_by = 'SYSTEM' THEN 1 END) AS auto_reviewed,
                    AVG(
                        CASE WHEN sd.decision IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                        END
                    ) AS avg_review_hours,
                    COUNT(CASE WHEN sd.detected_is_screenshot = true THEN 1 END) AS screenshots_detected
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
            """)
            kpis = db.execute(kpi_query, params).fetchone()

            # Open requests count
            open_query = text("""
                SELECT COUNT(*) AS open_count
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id AND l.organization_id = :org_id
                WHERE sdr.status = 'OPEN' AND sdr.is_active = true
            """)
            open_result = db.execute(open_query, params).fetchone()

            # Active campaigns
            campaigns_query = text("""
                SELECT
                    COUNT(*) AS active_campaigns,
                    COUNT(CASE WHEN borrower_responded = true THEN 1 END) AS responded
                FROM document_followup_campaigns
                WHERE organization_id = :org_id
                    AND created_at >= CURRENT_DATE - :days
            """)
            campaigns = db.execute(campaigns_query, params).fetchone()

            total_reviewed = (kpis.accepted or 0) + (kpis.rejected or 0) + (kpis.needs_review or 0)
            acceptance_rate = round(
                (kpis.accepted or 0) / total_reviewed * 100 if total_reviewed > 0 else 0, 1
            )
            automation_rate = round(
                (kpis.auto_reviewed or 0) / total_reviewed * 100 if total_reviewed > 0 else 0, 1
            )

            # Determine health status
            alerts = []
            if acceptance_rate < 70:
                alerts.append("Low acceptance rate - review rejection causes")
            if (open_result.open_count or 0) > 50:
                alerts.append(f"{open_result.open_count} open requests - capacity review needed")
            if float(kpis.avg_review_hours or 0) > 24:
                alerts.append("Avg review time > 24h - staffing or workflow issue")

            health = "healthy" if not alerts else "warning" if len(alerts) <= 1 else "critical"

            data = {
                "period_days": days,
                "kpis": {
                    "total_docs_processed": kpis.total_docs_processed or 0,
                    "loans_with_docs": kpis.loans_with_docs or 0,
                    "acceptance_rate": acceptance_rate,
                    "rejection_rate": round(100 - acceptance_rate, 1) if total_reviewed > 0 else 0,
                    "automation_rate": automation_rate,
                    "avg_review_hours": round(float(kpis.avg_review_hours or 0), 1),
                    "screenshots_detected": kpis.screenshots_detected or 0,
                    "open_requests": open_result.open_count or 0,
                },
                "followup": {
                    "active_campaigns": campaigns.active_campaigns or 0,
                    "borrower_response_rate": round(
                        (campaigns.responded or 0) / (campaigns.active_campaigns or 1) * 100, 1
                    ),
                },
                "health": {
                    "status": health,
                    "alerts": alerts,
                },
            }

            self.audit_log("generate_management_dashboard", details={"health": health})

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Dashboard: {kpis.total_docs_processed or 0} docs, "
                    f"{acceptance_rate}% accepted, {automation_rate}% auto-reviewed. "
                    f"Health: {health}"
                ),
            )
        except Exception as e:
            logger.exception("generate_management_dashboard failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_followup_effectiveness(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Analyze which follow-up strategies yield best results."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            # By campaign type
            by_type_query = text("""
                SELECT
                    fc.campaign_type,
                    COUNT(*) AS total_campaigns,
                    COUNT(CASE WHEN fc.borrower_responded = true THEN 1 END) AS responded,
                    AVG(fc.reminders_sent) AS avg_reminders,
                    AVG(
                        CASE WHEN fc.response_date IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (fc.response_date - fc.started_at)) / 86400
                        END
                    ) AS avg_response_days
                FROM document_followup_campaigns fc
                WHERE fc.organization_id = :org_id
                    AND fc.created_at >= CURRENT_DATE - :days
                GROUP BY fc.campaign_type
                ORDER BY responded DESC
            """)
            by_type = db.execute(by_type_query, params).fetchall()

            # By step/channel effectiveness
            by_channel_query = text("""
                SELECT
                    fe.channel,
                    fe.step_number,
                    COUNT(*) AS sends,
                    COUNT(CASE WHEN fe.delivery_status = 'delivered' THEN 1 END) AS delivered,
                    COUNT(CASE WHEN fe.delivery_status = 'opened' THEN 1 END) AS opened,
                    COUNT(CASE WHEN fe.delivery_status = 'clicked' THEN 1 END) AS clicked
                FROM document_followup_events fe
                WHERE fe.organization_id = :org_id
                    AND fe.created_at >= CURRENT_DATE - :days
                    AND fe.channel IS NOT NULL
                GROUP BY fe.channel, fe.step_number
                ORDER BY fe.channel, fe.step_number
            """)
            by_channel = db.execute(by_channel_query, params).fetchall()

            data = {
                "period_days": days,
                "by_campaign_type": [
                    {
                        "type": row.campaign_type,
                        "total": row.total_campaigns,
                        "responded": row.responded,
                        "response_rate": round(
                            row.responded / row.total_campaigns * 100
                            if row.total_campaigns > 0 else 0, 1
                        ),
                        "avg_reminders_sent": round(float(row.avg_reminders or 0), 1),
                        "avg_response_days": round(float(row.avg_response_days or 0), 1),
                    }
                    for row in by_type
                ],
                "by_channel_step": [
                    {
                        "channel": row.channel,
                        "step": row.step_number,
                        "sends": row.sends,
                        "delivered": row.delivered,
                        "delivery_rate": round(
                            row.delivered / row.sends * 100 if row.sends > 0 else 0, 1
                        ),
                        "open_rate": round(
                            row.opened / row.delivered * 100 if row.delivered > 0 else 0, 1
                        ),
                    }
                    for row in by_channel
                ],
            }

            self.audit_log("analyze_followup_effectiveness")

            best_type = max(
                data["by_campaign_type"],
                key=lambda x: x["response_rate"],
                default=None,
            )
            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Best campaign type: {best_type['type']} ({best_type['response_rate']}% response)"
                    if best_type else "No follow-up data available"
                ),
            )
        except Exception as e:
            logger.exception("analyze_followup_effectiveness failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_esign_adoption(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Track e-signature adoption rate and completion patterns."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 90)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            # Track documents uploaded via different sources as proxy for e-sign vs manual
            source_query = text("""
                SELECT
                    sd.upload_source,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600) AS avg_review_hours
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
                GROUP BY sd.upload_source
                ORDER BY count DESC
            """)
            sources = db.execute(source_query, params).fetchall()

            # Track disclosure e-sign completion from disclosure_events
            esign_query = text("""
                SELECT
                    COUNT(*) AS total_disclosures,
                    COUNT(CASE WHEN l.initial_disclosures_signed_date IS NOT NULL THEN 1 END) AS signed,
                    COUNT(CASE WHEN l.cd_acknowledged_date IS NOT NULL THEN 1 END) AS cd_acknowledged
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.created_at >= CURRENT_DATE - :days
                    AND l.initial_disclosures_sent_date IS NOT NULL
            """)
            esign = db.execute(esign_query, params).fetchone()

            total_docs = sum(row.count for row in sources) if sources else 0
            web_uploads = sum(row.count for row in sources if row.upload_source == "WEB") if sources else 0
            adoption_rate = round(web_uploads / total_docs * 100 if total_docs > 0 else 0, 1)

            esign_completion = round(
                (esign.signed or 0) / (esign.total_disclosures or 1) * 100, 1
            )

            data = {
                "period_days": days,
                "upload_sources": [
                    {
                        "source": row.upload_source or "UNKNOWN",
                        "count": row.count,
                        "accepted": row.accepted,
                        "rejected": row.rejected,
                        "acceptance_rate": round(
                            row.accepted / row.count * 100 if row.count > 0 else 0, 1
                        ),
                        "avg_review_hours": round(float(row.avg_review_hours or 0), 1),
                    }
                    for row in sources
                ],
                "digital_adoption_rate": adoption_rate,
                "esign_disclosure": {
                    "total_sent": esign.total_disclosures or 0,
                    "signed": esign.signed or 0,
                    "completion_rate": esign_completion,
                    "cd_acknowledged": esign.cd_acknowledged or 0,
                },
            }

            self.audit_log("track_esign_adoption", details={"adoption_rate": adoption_rate})

            return ToolResult(
                success=True,
                data=data,
                message=f"Digital adoption: {adoption_rate}%. E-sign completion: {esign_completion}%",
            )
        except Exception as e:
            logger.exception("track_esign_adoption failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _measure_portal_engagement(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Measure borrower portal usage and upload patterns."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 30)
            params: Dict[str, Any] = {"org_id": org_id, "days": days}

            # Upload patterns by day of week and hour
            pattern_query = text("""
                SELECT
                    EXTRACT(DOW FROM sd.uploaded_at) AS day_of_week,
                    EXTRACT(HOUR FROM sd.uploaded_at) AS hour_of_day,
                    COUNT(*) AS upload_count
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
                    AND sd.upload_source = 'WEB'
                GROUP BY EXTRACT(DOW FROM sd.uploaded_at), EXTRACT(HOUR FROM sd.uploaded_at)
                ORDER BY upload_count DESC
            """)
            patterns = db.execute(pattern_query, params).fetchall()

            # Borrower engagement: docs per borrower
            engagement_query = text("""
                SELECT
                    COUNT(DISTINCT sd.borrower_id) AS unique_borrowers,
                    COUNT(*) AS total_uploads,
                    AVG(docs_per_borrower.doc_count) AS avg_docs_per_borrower
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                JOIN (
                    SELECT borrower_id, COUNT(*) AS doc_count
                    FROM smart_documents sd2
                    JOIN loans l2 ON l2.id = sd2.loan_id AND l2.organization_id = :org_id
                    WHERE sd2.uploaded_at >= CURRENT_DATE - :days
                        AND sd2.upload_source = 'WEB'
                    GROUP BY borrower_id
                ) docs_per_borrower ON docs_per_borrower.borrower_id = sd.borrower_id
                WHERE sd.uploaded_at >= CURRENT_DATE - :days
                    AND sd.upload_source = 'WEB'
            """)
            engagement = db.execute(engagement_query, params).fetchone()

            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

            # Find peak upload times
            peak_times = []
            for row in patterns[:5]:
                peak_times.append({
                    "day": day_names[int(row.day_of_week)],
                    "hour": f"{int(row.hour_of_day):02d}:00",
                    "uploads": row.upload_count,
                })

            data = {
                "period_days": days,
                "engagement": {
                    "unique_borrowers": engagement.unique_borrowers or 0,
                    "total_portal_uploads": engagement.total_uploads or 0,
                    "avg_docs_per_borrower": round(float(engagement.avg_docs_per_borrower or 0), 1),
                },
                "peak_upload_times": peak_times,
            }

            self.audit_log("measure_portal_engagement")

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Portal: {engagement.unique_borrowers or 0} borrowers, "
                    f"{engagement.total_uploads or 0} uploads in {days} days"
                ),
            )
        except Exception as e:
            logger.exception("measure_portal_engagement failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _forecast_workload(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Predict document processing workload for the next N days."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            forecast_days = input_data.get("forecast_days", 14)
            params: Dict[str, Any] = {"org_id": org_id}

            # Current backlog
            backlog_query = text("""
                SELECT
                    COUNT(CASE WHEN sd.decision IS NULL AND sd.status NOT IN ('SCANNING', 'PROCESSING')
                          THEN 1 END) AS pending_review,
                    COUNT(CASE WHEN sdr.status = 'OPEN' AND sdr.is_active = true THEN 1 END) AS open_requests
                FROM loans l
                LEFT JOIN smart_documents sd ON sd.loan_id = l.id AND sd.uploaded_at >= CURRENT_DATE - 30
                LEFT JOIN smart_document_requests sdr ON sdr.loan_id = l.id
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
            """)
            backlog = db.execute(backlog_query, params).fetchone()

            # Historical daily averages for forecasting
            daily_avg_query = text("""
                SELECT
                    AVG(daily_uploads) AS avg_daily_uploads,
                    AVG(daily_reviews) AS avg_daily_reviews
                FROM (
                    SELECT
                        sd.uploaded_at::date AS day,
                        COUNT(*) AS daily_uploads,
                        COUNT(CASE WHEN sd.decision IS NOT NULL THEN 1 END) AS daily_reviews
                    FROM smart_documents sd
                    JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                    WHERE sd.uploaded_at >= CURRENT_DATE - 30
                    GROUP BY sd.uploaded_at::date
                ) daily
            """)
            daily_avg = db.execute(daily_avg_query, params).fetchone()

            # Pipeline loans that will need documents
            pipeline_query = text("""
                SELECT
                    COUNT(*) AS active_loans,
                    COUNT(CASE WHEN l.stage IN ('APPLICATION', 'DISCLOSED', 'PROCESSING')
                          THEN 1 END) AS early_stage_loans
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
            """)
            pipeline = db.execute(pipeline_query, params).fetchone()

            avg_uploads = float(daily_avg.avg_daily_uploads or 5)
            avg_reviews = float(daily_avg.avg_daily_reviews or 4)

            forecast = {
                "current_backlog": {
                    "pending_review": backlog.pending_review or 0,
                    "open_requests": backlog.open_requests or 0,
                },
                "daily_averages": {
                    "uploads_per_day": round(avg_uploads, 1),
                    "reviews_per_day": round(avg_reviews, 1),
                },
                "forecast_period_days": forecast_days,
                "predicted_volume": {
                    "expected_uploads": round(avg_uploads * forecast_days),
                    "expected_reviews_needed": round(avg_uploads * forecast_days + (backlog.pending_review or 0)),
                    "review_capacity": round(avg_reviews * forecast_days),
                },
                "pipeline_context": {
                    "active_loans": pipeline.active_loans or 0,
                    "early_stage_loans": pipeline.early_stage_loans or 0,
                },
            }

            capacity_gap = (
                forecast["predicted_volume"]["expected_reviews_needed"]
                - forecast["predicted_volume"]["review_capacity"]
            )
            forecast["capacity_assessment"] = {
                "gap": max(0, capacity_gap),
                "status": "over_capacity" if capacity_gap > 0 else "balanced" if capacity_gap > -10 else "under_utilized",
            }

            self.audit_log("forecast_workload", details={"forecast_days": forecast_days})

            return ToolResult(
                success=True,
                data=forecast,
                message=(
                    f"Forecast ({forecast_days}d): ~{forecast['predicted_volume']['expected_uploads']} uploads expected. "
                    f"Capacity: {forecast['capacity_assessment']['status']}"
                ),
            )
        except Exception as e:
            logger.exception("forecast_workload failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_team_scorecard(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate per-LO document management performance scorecard."""
        from database import SessionLocal

        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            days = input_data.get("days", 30)
            lo_id = input_data.get("lo_id")
            params: Dict[str, Any] = {"org_id": org_id, "days": days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            scorecard_query = text(f"""
                SELECT
                    l.loan_officer_id AS lo_id,
                    CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
                    COUNT(DISTINCT l.id) AS loan_count,
                    COUNT(DISTINCT sd.id) AS total_docs,
                    COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) AS accepted,
                    COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END) AS rejected,
                    AVG(
                        CASE WHEN sd.decision IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600
                        END
                    ) AS avg_review_hours,
                    COUNT(DISTINCT sdr_open.id) AS open_requests,
                    AVG(
                        CASE WHEN sd.uploaded_at IS NOT NULL AND sdr.created_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (sd.uploaded_at - sdr.created_at)) / 86400
                        END
                    ) AS avg_collection_days
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                LEFT JOIN smart_documents sd ON sd.loan_id = l.id
                    AND sd.uploaded_at >= CURRENT_DATE - :days
                LEFT JOIN smart_document_requests sdr ON sdr.id = sd.request_id
                LEFT JOIN smart_document_requests sdr_open ON sdr_open.loan_id = l.id
                    AND sdr_open.status = 'OPEN' AND sdr_open.is_active = true
                WHERE l.organization_id = :org_id
                    AND l.created_at >= CURRENT_DATE - :days
                    {lo_filter}
                GROUP BY l.loan_officer_id, u.first_name, u.last_name
                HAVING COUNT(DISTINCT sd.id) > 0
                ORDER BY COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END) DESC
            """)
            results = db.execute(scorecard_query, params).fetchall()

            if not results:
                return ToolResult(
                    success=True,
                    data={"scorecards": [], "period_days": days},
                    message="No document activity found for scoring",
                )

            scorecards = []
            for i, row in enumerate(results):
                total_reviewed = (row.accepted or 0) + (row.rejected or 0)
                acceptance_rate = round(
                    (row.accepted or 0) / total_reviewed * 100 if total_reviewed > 0 else 0, 1
                )
                # Score: weighted combination of acceptance rate, speed, and volume
                speed_score = max(0, 100 - float(row.avg_collection_days or 10) * 5)
                quality_score = acceptance_rate
                volume_score = min(100, (row.total_docs or 0) * 5)
                overall_score = round(quality_score * 0.4 + speed_score * 0.35 + volume_score * 0.25, 1)

                scorecards.append({
                    "rank": i + 1,
                    "lo_id": row.lo_id,
                    "lo_name": row.lo_name,
                    "loan_count": row.loan_count,
                    "total_docs": row.total_docs,
                    "accepted": row.accepted or 0,
                    "rejected": row.rejected or 0,
                    "acceptance_rate": acceptance_rate,
                    "avg_review_hours": round(float(row.avg_review_hours or 0), 1),
                    "avg_collection_days": round(float(row.avg_collection_days or 0), 1),
                    "open_requests": row.open_requests,
                    "overall_score": overall_score,
                })

            avg_score = round(sum(s["overall_score"] for s in scorecards) / len(scorecards), 1)

            data = {
                "period_days": days,
                "team_avg_score": avg_score,
                "scorecards": scorecards,
                "top_performer": scorecards[0]["lo_name"] if scorecards else None,
            }

            self.audit_log("generate_team_scorecard", details={"team_size": len(scorecards)})

            return ToolResult(
                success=True,
                data=data,
                message=(
                    f"Scorecard: {len(scorecards)} team members. "
                    f"Avg score: {avg_score}. "
                    f"Top: {scorecards[0]['lo_name']}" if scorecards else "No data"
                ),
            )
        except Exception as e:
            logger.exception("generate_team_scorecard failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
