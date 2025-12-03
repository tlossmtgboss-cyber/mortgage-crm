"""
Loan Pipeline Agent

Specialized agent for loan pipeline management with 8 tools:
1. get_pipeline_metrics - Overall pipeline health metrics
2. get_loans_by_status - Loans in specific status
3. get_loan_details - Detailed loan information
4. update_loan_status - Move loan through stages
5. get_loan_aging - Aging analysis
6. find_bottlenecks - Pipeline bottleneck detection
7. predict_closing - Closing timeline predictions
8. get_stale_loans - Find stuck/stale loans
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

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

class GetPipelineMetricsInput(BaseModel):
    """Input schema for get_pipeline_metrics tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    branch_id: Optional[str] = Field(None, description="Filter by branch ID")
    date_range: int = Field(default=30, description="Days to include in analysis")


class GetLoansByStatusInput(BaseModel):
    """Input schema for get_loans_by_status tool"""
    status: str = Field(..., description="Loan status: application, processing, underwriting, conditional, clear_to_close, closing")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    limit: int = Field(default=50, description="Maximum loans to return")
    sort_by: str = Field(default="days_in_stage", description="Sort field: days_in_stage, loan_amount, expected_close_date")


class GetLoanDetailsInput(BaseModel):
    """Input schema for get_loan_details tool"""
    loan_id: int = Field(..., description="The loan ID")
    include_conditions: bool = Field(default=True, description="Include conditions list")
    include_timeline: bool = Field(default=True, description="Include status timeline")


class UpdateLoanStatusInput(BaseModel):
    """Input schema for update_loan_status tool"""
    loan_id: int = Field(..., description="The loan ID to update")
    new_status: str = Field(..., description="New status: application, processing, underwriting, conditional, clear_to_close, closing, funded, denied, cancelled")
    reason: Optional[str] = Field(None, description="Reason for status change")


class GetLoanAgingInput(BaseModel):
    """Input schema for get_loan_aging tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    branch_id: Optional[str] = Field(None, description="Filter by branch ID")


class FindBottlenecksInput(BaseModel):
    """Input schema for find_bottlenecks tool"""
    branch_id: Optional[str] = Field(None, description="Filter by branch ID")


class PredictClosingInput(BaseModel):
    """Input schema for predict_closing tool"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID for prediction")
    lo_id: Optional[int] = Field(None, description="Filter predictions by loan officer")


class GetStaleLoansInput(BaseModel):
    """Input schema for get_stale_loans tool"""
    threshold_days: int = Field(default=7, description="Days without activity to consider stale")
    limit: int = Field(default=50, description="Maximum loans to return")


# ============================================================================
# LOAN PIPELINE AGENT
# ============================================================================

@AgentRegistry.register
class LoanPipelineAgent(SpecializedAgent):
    """
    Specialized agent for loan pipeline management.

    Monitors active loans, identifies bottlenecks, predicts closings,
    and provides pipeline health insights.
    """

    @property
    def name(self) -> str:
        return "LoanPipelineAgent"

    @property
    def description(self) -> str:
        return "Manages loan pipeline including status tracking, bottleneck detection, and closing predictions"

    def _register_tools(self):
        """Register all loan pipeline tools"""

        # Tool 1: Get Pipeline Metrics
        self.register_tool(AgentTool(
            name="get_pipeline_metrics",
            description="Get comprehensive pipeline metrics including total volume, loan counts by stage, "
                       "and pipeline health indicators. Essential for understanding overall pipeline status.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_pipeline_metrics,
            input_schema=GetPipelineMetricsInput
        ))

        # Tool 2: Get Loans By Status
        self.register_tool(AgentTool(
            name="get_loans_by_status",
            description="Get detailed list of loans in a specific pipeline status. "
                       "Useful for reviewing loans at each stage.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_loans_by_status,
            input_schema=GetLoansByStatusInput
        ))

        # Tool 3: Get Loan Details
        self.register_tool(AgentTool(
            name="get_loan_details",
            description="Get comprehensive details for a specific loan including borrower info, "
                       "loan terms, conditions, and status timeline.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_loan_details,
            input_schema=GetLoanDetailsInput
        ))

        # Tool 4: Update Loan Status
        self.register_tool(AgentTool(
            name="update_loan_status",
            description="Move a loan to a different pipeline status. Records status change history "
                       "for tracking and compliance.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._update_loan_status,
            input_schema=UpdateLoanStatusInput
        ))

        # Tool 5: Get Loan Aging
        self.register_tool(AgentTool(
            name="get_loan_aging",
            description="Get aging analysis showing how long loans have been in each stage. "
                       "Identifies loans exceeding SLA thresholds.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_loan_aging,
            input_schema=GetLoanAgingInput
        ))

        # Tool 6: Find Bottlenecks
        self.register_tool(AgentTool(
            name="find_bottlenecks",
            description="Identify pipeline bottlenecks and their root causes. "
                       "Provides actionable recommendations for improvement.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._find_bottlenecks,
            input_schema=FindBottlenecksInput
        ))

        # Tool 7: Predict Closing
        self.register_tool(AgentTool(
            name="predict_closing",
            description="Predict closing timeline for specific loan or entire pipeline "
                       "based on historical stage durations.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._predict_closing,
            input_schema=PredictClosingInput
        ))

        # Tool 8: Get Stale Loans
        self.register_tool(AgentTool(
            name="get_stale_loans",
            description="Find loans that haven't had activity in a specified number of days. "
                       "Critical for identifying stuck loans that need attention.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_stale_loans,
            input_schema=GetStaleLoansInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_pipeline_metrics(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get comprehensive pipeline metrics"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            date_range = input_data.get("date_range", 30)
            lo_id = input_data.get("lo_id")

            lo_filter = "AND assigned_lo = :lo_id" if lo_id else ""
            params = {"date_range": date_range}
            if lo_id:
                params["lo_id"] = lo_id

            # Main metrics query
            # Note: Stage values must match LoanStage enum in main.py exactly
            query = text(f"""
                SELECT
                    COUNT(*) as total_loans,
                    COALESCE(SUM(amount), 0) as total_volume,
                    COALESCE(AVG(amount), 0) as avg_loan_size,
                    COUNT(CASE WHEN stage = 'Disclosed' THEN 1 END) as applications,
                    COUNT(CASE WHEN stage = 'Processing' THEN 1 END) as processing,
                    COUNT(CASE WHEN stage IN ('Submitted', 'UW Received') THEN 1 END) as underwriting,
                    COUNT(CASE WHEN stage IN ('Approved', 'Suspended') THEN 1 END) as conditional,
                    COUNT(CASE WHEN stage = 'CTC' THEN 1 END) as ctc,
                    COUNT(CASE WHEN stage = 'Docs Out' THEN 1 END) as closing,
                    COUNT(CASE WHEN expected_close_date < CURRENT_DATE THEN 1 END) as past_due,
                    COUNT(CASE WHEN expected_close_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 THEN 1 END) as closing_this_week,
                    COUNT(CASE WHEN expected_close_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30 THEN 1 END) as closing_this_month
                FROM loans
                WHERE stage NOT IN ('Funded')
                    AND created_at >= CURRENT_DATE - :date_range
                    {lo_filter}
            """)

            result = db.execute(query, params).fetchone()

            if not result or result.total_loans == 0:
                return ToolResult(
                    success=True,
                    data={"total_loans": 0, "message": "No active loans in pipeline"},
                    message="Pipeline is empty"
                )

            # Stage distribution with values
            # Note: Stage values must match LoanStage enum in main.py exactly
            stage_query = text(f"""
                SELECT
                    stage,
                    COUNT(*) as loan_count,
                    SUM(amount) as stage_volume,
                    AVG(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as avg_days
                FROM loans
                WHERE stage NOT IN ('Funded')
                    {lo_filter}
                GROUP BY stage
            """)

            stages = db.execute(stage_query, params).fetchall()

            stage_details = []
            for s in stages:
                stage_details.append({
                    "stage": s.stage,
                    "count": s.loan_count,
                    "volume": float(s.stage_volume) if s.stage_volume else 0,
                    "avg_days": round(float(s.avg_days or 0), 1)
                })

            return ToolResult(
                success=True,
                data={
                    "summary": {
                        "total_loans": result.total_loans,
                        "total_volume": float(result.total_volume),
                        "avg_loan_size": float(result.avg_loan_size)
                    },
                    "stage_counts": {
                        "application": result.applications,
                        "processing": result.processing,
                        "underwriting": result.underwriting,
                        "conditional": result.conditional,
                        "clear_to_close": result.ctc,
                        "closing": result.closing
                    },
                    "stage_details": stage_details,
                    "alerts": {
                        "past_due": result.past_due,
                        "closing_this_week": result.closing_this_week,
                        "closing_this_month": result.closing_this_month
                    }
                },
                message=f"Pipeline: {result.total_loans} loans totaling ${result.total_volume:,.0f}"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_loans_by_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get loans in a specific status"""
        from database import SessionLocal

        status = input_data["status"]
        limit = input_data.get("limit", 50)
        lo_id = input_data.get("lo_id")
        sort_by = input_data.get("sort_by", "days_in_stage")

        sort_mapping = {
            "days_in_stage": "days_in_stage DESC",
            "loan_amount": "amount DESC",
            "expected_close_date": "expected_close_date ASC"
        }
        order_by = sort_mapping.get(sort_by, "days_in_stage DESC")

        db = SessionLocal()
        try:
            params = {"status": status, "limit": limit}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND assigned_lo = :lo_id"
                params["lo_id"] = lo_id

            query = text(f"""
                SELECT
                    id, loan_number, borrower_name, amount,
                    program, stage, expected_close_date,
                    EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) as days_in_stage,
                    updated_at
                FROM loans
                WHERE stage = :status
                    {lo_filter}
                ORDER BY {order_by}
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            # SLA thresholds
            sla_thresholds = {
                "application": 3,
                "processing": 5,
                "underwriting": 3,
                "conditional": 7,
                "clear_to_close": 3,
                "closing": 5
            }
            threshold = sla_thresholds.get(status, 5)

            loans = []
            for r in results:
                days = int(r.days_in_stage or 0)
                loans.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower_name": r.borrower_name,
                    "amount": float(r.amount) if r.amount else 0,
                    "program": r.program,
                    "expected_close_date": r.expected_close_date.isoformat() if r.expected_close_date else None,
                    "days_in_stage": days,
                    "is_aging": days > threshold
                })

            aging_count = sum(1 for l in loans if l["is_aging"])

            return ToolResult(
                success=True,
                data={
                    "status": status,
                    "loans": loans,
                    "count": len(loans),
                    "aging_count": aging_count,
                    "sla_threshold_days": threshold
                },
                message=f"{len(loans)} loans in {status}, {aging_count} aging"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_loan_details(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get comprehensive loan details"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()

        try:
            query = text("SELECT * FROM loans WHERE id = :loan_id")
            result = db.execute(query, {"loan_id": loan_id}).fetchone()

            if not result:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            loan_data = dict(result._mapping)

            # Get conditions if requested
            if input_data.get("include_conditions", True):
                cond_query = text("""
                    SELECT condition_type, description, status, due_date, cleared_date
                    FROM loan_conditions
                    WHERE loan_id = :loan_id
                    ORDER BY status, due_date
                """)
                conditions = db.execute(cond_query, {"loan_id": loan_id}).fetchall()
                loan_data["conditions"] = [
                    {
                        "type": c.condition_type,
                        "description": c.description,
                        "status": c.status,
                        "due_date": c.due_date.isoformat() if c.due_date else None,
                        "cleared_date": c.cleared_date.isoformat() if c.cleared_date else None
                    }
                    for c in conditions
                ]
                loan_data["pending_conditions"] = sum(1 for c in conditions if c.status == "pending")

            # Get timeline if requested
            if input_data.get("include_timeline", True):
                timeline_query = text("""
                    SELECT from_stage, to_stage, changed_at, changed_by, reason
                    FROM loan_stage_history
                    WHERE loan_id = :loan_id
                    ORDER BY changed_at DESC
                    LIMIT 20
                """)
                timeline = db.execute(timeline_query, {"loan_id": loan_id}).fetchall()
                loan_data["stage_timeline"] = [
                    {
                        "from_stage": t.from_stage,
                        "to_stage": t.to_stage,
                        "changed_at": t.changed_at.isoformat() if t.changed_at else None,
                        "reason": t.reason
                    }
                    for t in timeline
                ]

            return ToolResult(
                success=True,
                data={"loan": loan_data},
                message=f"Loan {loan_id}: {result.borrower_name} - {result.stage}"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _update_loan_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Update loan status with history tracking"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        new_status = input_data["new_status"]
        reason = input_data.get("reason", "AI agent update")

        valid_statuses = ["application", "processing", "underwriting", "conditional",
                         "clear_to_close", "closing", "funded", "denied", "cancelled"]
        if new_status not in valid_statuses:
            return ToolResult(
                success=False,
                error=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        db = SessionLocal()
        try:
            # Get current status
            current = db.execute(
                text("SELECT stage, borrower_name FROM loans WHERE id = :loan_id"),
                {"loan_id": loan_id}
            ).fetchone()

            if not current:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            old_status = current.stage

            # Update status
            db.execute(
                text("""
                    UPDATE loans
                    SET stage = :new_status, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :loan_id
                """),
                {"loan_id": loan_id, "new_status": new_status}
            )

            # Record history
            db.execute(
                text("""
                    INSERT INTO loan_stage_history
                    (loan_id, from_stage, to_stage, changed_by, reason, changed_at)
                    VALUES (:loan_id, :old_status, :new_status, :changed_by, :reason, CURRENT_TIMESTAMP)
                """),
                {
                    "loan_id": loan_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "changed_by": context.get("user_id", 1),
                    "reason": reason
                }
            )

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "borrower_name": current.borrower_name
                },
                message=f"Loan {loan_id} moved from {old_status} to {new_status}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_loan_aging(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get loan aging analysis"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            lo_id = input_data.get("lo_id")
            params = {}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND assigned_lo = :lo_id"
                params["lo_id"] = lo_id

            query = text(f"""
                SELECT
                    stage,
                    COUNT(*) as total_loans,
                    SUM(amount) as total_volume,
                    AVG(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as avg_days,
                    MAX(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as max_days,
                    COUNT(CASE WHEN EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) <= 3 THEN 1 END) as bucket_0_3,
                    COUNT(CASE WHEN EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) BETWEEN 4 AND 7 THEN 1 END) as bucket_4_7,
                    COUNT(CASE WHEN EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) BETWEEN 8 AND 14 THEN 1 END) as bucket_8_14,
                    COUNT(CASE WHEN EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) > 14 THEN 1 END) as bucket_14_plus
                FROM loans
                WHERE stage NOT IN ('Funded')
                    {lo_filter}
                GROUP BY stage
            """)

            results = db.execute(query, params).fetchall()

            if not results:
                return ToolResult(
                    success=True,
                    data={"stages": [], "total_at_risk": 0},
                    message="No active loans for aging analysis"
                )

            sla_thresholds = {
                "application": 3,
                "processing": 5,
                "underwriting": 3,
                "conditional": 7,
                "clear_to_close": 3,
                "closing": 5
            }

            stages = []
            total_at_risk = 0
            total_critical = 0

            for r in results:
                threshold = sla_thresholds.get(r.stage, 5)
                avg_days = float(r.avg_days or 0)
                at_risk = (r.bucket_8_14 or 0) + (r.bucket_14_plus or 0)
                critical = r.bucket_14_plus or 0
                total_at_risk += at_risk
                total_critical += critical

                stages.append({
                    "stage": r.stage,
                    "total_loans": r.total_loans,
                    "total_volume": float(r.total_volume or 0),
                    "avg_days": round(avg_days, 1),
                    "max_days": int(r.max_days or 0),
                    "sla_threshold": threshold,
                    "sla_status": "on_track" if avg_days <= threshold else "at_risk",
                    "buckets": {
                        "0-3_days": r.bucket_0_3 or 0,
                        "4-7_days": r.bucket_4_7 or 0,
                        "8-14_days": r.bucket_8_14 or 0,
                        "14+_days": r.bucket_14_plus or 0
                    },
                    "at_risk_count": at_risk,
                    "critical_count": critical
                })

            # Find worst bottleneck
            bottleneck = max(stages, key=lambda s: s["avg_days"]) if stages else None

            return ToolResult(
                success=True,
                data={
                    "stages": stages,
                    "summary": {
                        "total_at_risk": total_at_risk,
                        "total_critical": total_critical,
                        "bottleneck_stage": bottleneck["stage"] if bottleneck else None,
                        "bottleneck_avg_days": bottleneck["avg_days"] if bottleneck else None
                    }
                },
                message=f"Aging: {total_at_risk} loans at risk, {total_critical} critical"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _find_bottlenecks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Find pipeline bottlenecks"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            branch_id = input_data.get("branch_id")
            params = {}
            branch_filter = ""
            if branch_id:
                branch_filter = "AND branch_id = :branch_id"
                params["branch_id"] = branch_id

            query = text(f"""
                SELECT
                    stage,
                    COUNT(*) as count,
                    SUM(amount) as volume,
                    AVG(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as avg_days,
                    MAX(EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at)) as max_days
                FROM loans
                WHERE stage NOT IN ('Funded')
                    {branch_filter}
                GROUP BY stage
            """)

            results = db.execute(query, params).fetchall()

            if not results:
                return ToolResult(
                    success=True,
                    data={"bottlenecks": [], "recommendations": []},
                    message="No active loans for bottleneck analysis"
                )

            sla_thresholds = {
                "application": 3,
                "processing": 5,
                "underwriting": 3,
                "conditional": 7,
                "clear_to_close": 3,
                "closing": 5
            }

            bottlenecks = []
            recommendations = []

            for r in results:
                threshold = sla_thresholds.get(r.stage, 5)
                avg_days = float(r.avg_days or 0)

                if avg_days > threshold:
                    severity = "critical" if avg_days > threshold * 2 else "moderate"
                    bottlenecks.append({
                        "stage": r.stage,
                        "loan_count": r.count,
                        "volume": float(r.volume or 0),
                        "avg_days": round(avg_days, 1),
                        "max_days": int(r.max_days or 0),
                        "sla_threshold": threshold,
                        "severity": severity,
                        "over_sla_by": round(avg_days - threshold, 1)
                    })

                    # Generate recommendations
                    if r.stage == "processing":
                        recommendations.append("Add processor capacity or automate doc collection")
                    elif r.stage == "underwriting":
                        recommendations.append("Review underwriter workload distribution")
                    elif r.stage == "conditional":
                        recommendations.append("Assign dedicated resources for condition follow-up")
                    elif r.stage == "closing":
                        recommendations.append("Coordinate earlier with title company")

            # Sort by severity
            bottlenecks.sort(key=lambda x: x["avg_days"], reverse=True)

            primary = bottlenecks[0] if bottlenecks else None

            return ToolResult(
                success=True,
                data={
                    "bottlenecks": bottlenecks,
                    "primary_bottleneck": primary,
                    "recommendations": recommendations[:3],
                    "summary": {
                        "healthy_stages": len(results) - len(bottlenecks),
                        "bottleneck_stages": len(bottlenecks)
                    }
                },
                message=f"Found {len(bottlenecks)} bottleneck(s). Primary: {primary['stage']} ({primary['avg_days']} avg days)" if primary else "No bottlenecks detected"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _predict_closing(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Predict closing timeline"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data.get("loan_id")
            lo_id = input_data.get("lo_id")

            # Historical average days per stage
            historical_durations = {
                "application": 2,
                "processing": 5,
                "underwriting": 3,
                "conditional": 5,
                "clear_to_close": 2,
                "closing": 3
            }

            stage_order = ["application", "processing", "underwriting",
                          "conditional", "clear_to_close", "closing", "funded"]

            if loan_id:
                # Single loan prediction
                loan = db.execute(
                    text("""
                        SELECT id, loan_number, borrower_name, stage,
                               updated_at, expected_close_date, amount
                        FROM loans WHERE id = :loan_id
                    """),
                    {"loan_id": loan_id}
                ).fetchone()

                if not loan:
                    return ToolResult(success=False, error=f"Loan {loan_id} not found")

                current_idx = stage_order.index(loan.stage) if loan.stage in stage_order else 0

                # Calculate remaining days
                days_remaining = 0
                days_in_current = (datetime.now() - loan.updated_at).days if loan.updated_at else 0
                expected_current = historical_durations.get(loan.stage, 3)

                if days_in_current < expected_current:
                    days_remaining += expected_current - days_in_current

                for stage in stage_order[current_idx + 1:-1]:
                    days_remaining += historical_durations.get(stage, 3)

                predicted_close = date.today() + timedelta(days=int(days_remaining))

                on_track = True
                if loan.expected_close_date:
                    on_track = predicted_close <= loan.expected_close_date

                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "current_stage": loan.stage,
                        "days_in_current_stage": days_in_current,
                        "predicted_close_date": predicted_close.isoformat(),
                        "scheduled_close_date": loan.expected_close_date.isoformat() if loan.expected_close_date else None,
                        "days_until_predicted": days_remaining,
                        "on_track": on_track
                    },
                    message=f"Predicted close: {predicted_close.strftime('%m/%d/%Y')} ({'on track' if on_track else 'at risk'})"
                )

            # Pipeline prediction
            params = {}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND assigned_lo = :lo_id"
                params["lo_id"] = lo_id

            loans = db.execute(
                text(f"""
                    SELECT id, loan_number, stage, updated_at,
                           expected_close_date, amount
                    FROM loans
                    WHERE stage NOT IN ('Funded')
                        {lo_filter}
                    ORDER BY expected_close_date ASC NULLS LAST
                    LIMIT 100
                """),
                params
            ).fetchall()

            if not loans:
                return ToolResult(
                    success=True,
                    data={"predictions": []},
                    message="No active loans for prediction"
                )

            predictions = []
            for loan in loans:
                current_idx = stage_order.index(loan.stage) if loan.stage in stage_order else 0

                days_remaining = 0
                days_in_current = (datetime.now() - loan.updated_at).days if loan.updated_at else 0
                expected_current = historical_durations.get(loan.stage, 3)

                if days_in_current < expected_current:
                    days_remaining += expected_current - days_in_current

                for stage in stage_order[current_idx + 1:-1]:
                    days_remaining += historical_durations.get(stage, 3)

                predicted_close = date.today() + timedelta(days=int(days_remaining))

                on_track = True
                if loan.expected_close_date:
                    on_track = predicted_close <= loan.expected_close_date

                predictions.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "current_stage": loan.stage,
                    "predicted_close_date": predicted_close.isoformat(),
                    "days_until_close": days_remaining,
                    "on_track": on_track,
                    "amount": float(loan.amount) if loan.amount else 0
                })

            on_track_count = sum(1 for p in predictions if p["on_track"])
            at_risk_count = len(predictions) - on_track_count

            return ToolResult(
                success=True,
                data={
                    "predictions": predictions[:20],
                    "summary": {
                        "total_loans": len(predictions),
                        "on_track": on_track_count,
                        "at_risk": at_risk_count
                    }
                },
                message=f"Predictions: {on_track_count} on track, {at_risk_count} at risk"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_stale_loans(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Find stale/stuck loans"""
        from database import SessionLocal

        threshold_days = input_data.get("threshold_days", 7)
        limit = input_data.get("limit", 50)

        db = SessionLocal()
        try:
            query = text("""
                SELECT
                    id, loan_number, borrower_name, stage, amount,
                    EXTRACT(DAY FROM CURRENT_TIMESTAMP - updated_at) as days_stale,
                    updated_at
                FROM loans
                WHERE stage NOT IN ('Funded')
                    AND updated_at < CURRENT_TIMESTAMP - INTERVAL ':days days'
                ORDER BY updated_at ASC
                LIMIT :limit
            """)

            results = db.execute(query, {"days": threshold_days, "limit": limit}).fetchall()

            stale_loans = []
            total_volume = 0

            for r in results:
                amount = float(r.amount) if r.amount else 0
                total_volume += amount
                stale_loans.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower_name": r.borrower_name,
                    "stage": r.stage,
                    "amount": amount,
                    "days_stale": round(float(r.days_stale or 0), 1),
                    "last_activity": r.updated_at.isoformat() if r.updated_at else None
                })

            return ToolResult(
                success=True,
                data={
                    "stale_loans": stale_loans,
                    "count": len(stale_loans),
                    "total_volume_at_risk": total_volume,
                    "threshold_days": threshold_days
                },
                message=f"Found {len(stale_loans)} stale loans (>{threshold_days} days), ${total_volume:,.0f} at risk"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
