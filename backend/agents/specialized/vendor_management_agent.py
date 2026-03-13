"""
Vendor Management Agent

Specialized agent for third-party vendor coordination with 15 tools:
1.  check_all_vendor_orders - Status of all third-party orders for a loan
2.  recommend_order_timing - When to place each order based on pipeline stage
3.  track_appraisal_progress - Detailed appraisal status tracking
4.  track_title_progress - Title search status and exception tracking
5.  track_insurance_status - Homeowners insurance and flood determination
6.  identify_delayed_orders - Orders behind expected timeline
7.  escalate_delayed_vendor - Create escalation for vendors missing SLA
8.  validate_appraisal_report - Check appraisal for common issues
9.  validate_title_report - Check title for liens, judgments, exceptions
10. check_flood_determination - Verify flood zone status and insurance requirements
11. coordinate_closing_vendors - Ensure all vendors aligned on closing date
12. calculate_vendor_costs - Track and forecast vendor costs per loan
13. rate_vendor_performance - Score vendors on timeliness, quality, responsiveness
14. generate_vendor_dashboard - Summary of all vendor orders across pipeline
15. recommend_vendor_selection - Recommend best vendor for order type + geography
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
# VENDOR SLA CONSTANTS
# ============================================================================

VENDOR_SLA_TARGETS = {
    "appraisal_order_to_schedule": 3,   # days from order to inspection
    "appraisal_schedule_to_complete": 5, # days from inspection to report
    "appraisal_complete_to_received": 2, # days from report to received in file
    "title_order_to_received": 7,        # days from order to preliminary title
    "insurance_order_to_received": 5,    # days from order to binder
    "flood_determination": 1,            # days for flood cert
    "hoa_cert_order_to_received": 10,    # days for HOA certification
}

ORDER_TIMING_BY_STAGE = {
    "APPLICATION": [],
    "DISCLOSED": ["flood_determination"],
    "PROCESSING": ["appraisal", "title"],
    "SUBMITTED": ["insurance"],
    "UNDERWRITING": [],
    "UW_RECEIVED": [],
    "CONDITIONAL_APPROVAL": ["hoa_cert"],
    "APPROVED": [],
    "CLEAR_TO_CLOSE": [],
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CheckAllVendorOrdersInput(BaseModel):
    """Input for check_all_vendor_orders tool"""
    loan_id: int = Field(..., description="Loan ID to check vendor orders for")


class RecommendOrderTimingInput(BaseModel):
    """Input for recommend_order_timing tool"""
    loan_id: int = Field(..., description="Loan ID to recommend timing for")


class TrackAppraisalProgressInput(BaseModel):
    """Input for track_appraisal_progress tool"""
    loan_id: int = Field(..., description="Loan ID to track appraisal for")


class TrackTitleProgressInput(BaseModel):
    """Input for track_title_progress tool"""
    loan_id: int = Field(..., description="Loan ID to track title for")


class TrackInsuranceStatusInput(BaseModel):
    """Input for track_insurance_status tool"""
    loan_id: int = Field(..., description="Loan ID to track insurance for")


class IdentifyDelayedOrdersInput(BaseModel):
    """Input for identify_delayed_orders tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")
    limit: int = Field(default=50, description="Maximum results to return")


class EscalateDelayedVendorInput(BaseModel):
    """Input for escalate_delayed_vendor tool"""
    loan_id: int = Field(..., description="Loan ID with delayed vendor order")
    vendor_type: str = Field(..., description="Vendor type: appraisal, title, insurance, flood, hoa")
    reason: str = Field(..., description="Reason for escalation")


class ValidateAppraisalReportInput(BaseModel):
    """Input for validate_appraisal_report tool"""
    loan_id: int = Field(..., description="Loan ID to validate appraisal for")


class ValidateTitleReportInput(BaseModel):
    """Input for validate_title_report tool"""
    loan_id: int = Field(..., description="Loan ID to validate title for")


class CheckFloodDeterminationInput(BaseModel):
    """Input for check_flood_determination tool"""
    loan_id: int = Field(..., description="Loan ID to check flood zone for")


class CoordinateClosingVendorsInput(BaseModel):
    """Input for coordinate_closing_vendors tool"""
    loan_id: int = Field(..., description="Loan ID to coordinate closing for")


class CalculateVendorCostsInput(BaseModel):
    """Input for calculate_vendor_costs tool"""
    loan_id: int = Field(..., description="Loan ID to calculate vendor costs for")


class RateVendorPerformanceInput(BaseModel):
    """Input for rate_vendor_performance tool"""
    vendor_type: str = Field(..., description="Vendor type: appraisal, title, insurance")
    days: int = Field(default=90, description="Lookback period in days")


class GenerateVendorDashboardInput(BaseModel):
    """Input for generate_vendor_dashboard tool"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer ID")


class RecommendVendorSelectionInput(BaseModel):
    """Input for recommend_vendor_selection tool"""
    vendor_type: str = Field(..., description="Vendor type: appraisal, title, insurance")
    state: Optional[str] = Field(None, description="State abbreviation for geography filtering")
    county: Optional[str] = Field(None, description="County for geography filtering")


# ============================================================================
# VENDOR MANAGEMENT AGENT
# ============================================================================

@AgentRegistry.register
class VendorManagementAgent(SpecializedAgent):
    """
    Specialized agent for third-party vendor coordination.

    Tracks appraisal, title, insurance, flood, and HOA orders across
    the loan pipeline. Monitors vendor SLAs, identifies delays, escalates
    issues, validates deliverables, and coordinates closing readiness.
    """

    @property
    def name(self) -> str:
        return "VendorManagementAgent"

    @property
    def description(self) -> str:
        return (
            "Coordinates third-party vendor orders (appraisal, title, insurance, "
            "flood, HOA) including SLA tracking, delay escalation, report validation, "
            "and closing coordination"
        )

    def _register_tools(self):
        """Register all vendor management tools"""

        # Tool 1: Check All Vendor Orders
        self.register_tool(AgentTool(
            name="check_all_vendor_orders",
            description=(
                "Get status of all third-party orders (appraisal, title, insurance) "
                "for a loan. Start here for any vendor inquiry."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_all_vendor_orders,
            input_schema=CheckAllVendorOrdersInput,
        ))

        # Tool 2: Recommend Order Timing
        self.register_tool(AgentTool(
            name="recommend_order_timing",
            description=(
                "Recommend when to place each vendor order based on the loan's "
                "current pipeline stage and expected timeline."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_order_timing,
            input_schema=RecommendOrderTimingInput,
        ))

        # Tool 3: Track Appraisal Progress
        self.register_tool(AgentTool(
            name="track_appraisal_progress",
            description=(
                "Detailed appraisal tracking: ordered, scheduled, completed, "
                "received, value, and SLA status."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_appraisal_progress,
            input_schema=TrackAppraisalProgressInput,
        ))

        # Tool 4: Track Title Progress
        self.register_tool(AgentTool(
            name="track_title_progress",
            description=(
                "Track title search status including order date, receipt, "
                "and any exception flags."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_title_progress,
            input_schema=TrackTitleProgressInput,
        ))

        # Tool 5: Track Insurance Status
        self.register_tool(AgentTool(
            name="track_insurance_status",
            description=(
                "Track homeowners insurance status including order, receipt, "
                "and flood determination requirements."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_insurance_status,
            input_schema=TrackInsuranceStatusInput,
        ))

        # Tool 6: Identify Delayed Orders
        self.register_tool(AgentTool(
            name="identify_delayed_orders",
            description=(
                "Find vendor orders across the pipeline that are behind "
                "expected SLA timelines."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_delayed_orders,
            input_schema=IdentifyDelayedOrdersInput,
        ))

        # Tool 7: Escalate Delayed Vendor
        self.register_tool(AgentTool(
            name="escalate_delayed_vendor",
            description=(
                "Create an escalation for a vendor that has missed their SLA "
                "deadline. Notifies the LO and processor."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._escalate_delayed_vendor,
            input_schema=EscalateDelayedVendorInput,
        ))

        # Tool 8: Validate Appraisal Report
        self.register_tool(AgentTool(
            name="validate_appraisal_report",
            description=(
                "Check appraisal for common issues: value support, property "
                "condition, comparable selection, reconciliation."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._validate_appraisal_report,
            input_schema=ValidateAppraisalReportInput,
        ))

        # Tool 9: Validate Title Report
        self.register_tool(AgentTool(
            name="validate_title_report",
            description=(
                "Check title report for issues: liens, judgments, "
                "easements, and exceptions that may affect closing."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._validate_title_report,
            input_schema=ValidateTitleReportInput,
        ))

        # Tool 10: Check Flood Determination
        self.register_tool(AgentTool(
            name="check_flood_determination",
            description=(
                "Verify flood zone status and whether flood insurance "
                "is required for the property."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_flood_determination,
            input_schema=CheckFloodDeterminationInput,
        ))

        # Tool 11: Coordinate Closing Vendors
        self.register_tool(AgentTool(
            name="coordinate_closing_vendors",
            description=(
                "Verify all vendors are aligned on the closing date. "
                "Checks appraisal, title, insurance readiness."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._coordinate_closing_vendors,
            input_schema=CoordinateClosingVendorsInput,
        ))

        # Tool 12: Calculate Vendor Costs
        self.register_tool(AgentTool(
            name="calculate_vendor_costs",
            description=(
                "Track and forecast vendor costs per loan including "
                "appraisal, title, insurance, and recording fees."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_vendor_costs,
            input_schema=CalculateVendorCostsInput,
        ))

        # Tool 13: Rate Vendor Performance
        self.register_tool(AgentTool(
            name="rate_vendor_performance",
            description=(
                "Score vendors on timeliness, quality, and responsiveness "
                "based on historical order data."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._rate_vendor_performance,
            input_schema=RateVendorPerformanceInput,
        ))

        # Tool 14: Generate Vendor Dashboard
        self.register_tool(AgentTool(
            name="generate_vendor_dashboard",
            description=(
                "Summary of all vendor orders across the active pipeline. "
                "Shows pending, delayed, and completed orders."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_vendor_dashboard,
            input_schema=GenerateVendorDashboardInput,
        ))

        # Tool 15: Recommend Vendor Selection
        self.register_tool(AgentTool(
            name="recommend_vendor_selection",
            description=(
                "Recommend the best vendor for a given order type and "
                "geography based on historical performance data."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_vendor_selection,
            input_schema=RecommendVendorSelectionInput,
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _check_all_vendor_orders(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get status of all third-party orders for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.stage, l.borrower_name,
                    l.closing_date, l.title_company,
                    l.appraisal_ordered_date, l.appraisal_scheduled_date,
                    l.appraisal_completed_date, l.appraisal_received_date,
                    l.appraisal_value,
                    l.title_ordered_date, l.title_received_date,
                    l.insurance_ordered_date, l.insurance_received_date,
                    l.flood_zone, l.flood_insurance_required
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()
            orders = []

            # Appraisal
            appraisal_status = "not_ordered"
            appraisal_days = None
            if loan.appraisal_received_date:
                appraisal_status = "received"
            elif loan.appraisal_completed_date:
                appraisal_status = "completed_awaiting_receipt"
                appraisal_days = (today - loan.appraisal_completed_date.date() if isinstance(
                    loan.appraisal_completed_date, datetime) else today - loan.appraisal_completed_date).days
            elif loan.appraisal_scheduled_date:
                appraisal_status = "scheduled"
                appraisal_days = (today - loan.appraisal_ordered_date.date() if isinstance(
                    loan.appraisal_ordered_date, datetime) and loan.appraisal_ordered_date else None)
                if appraisal_days is None and loan.appraisal_ordered_date:
                    appraisal_days = (today - loan.appraisal_ordered_date).days
            elif loan.appraisal_ordered_date:
                appraisal_status = "ordered"
                od = loan.appraisal_ordered_date
                appraisal_days = (today - (od.date() if isinstance(od, datetime) else od)).days

            orders.append({
                "type": "appraisal",
                "status": appraisal_status,
                "ordered": loan.appraisal_ordered_date.isoformat() if loan.appraisal_ordered_date else None,
                "scheduled": loan.appraisal_scheduled_date.isoformat() if loan.appraisal_scheduled_date else None,
                "completed": loan.appraisal_completed_date.isoformat() if loan.appraisal_completed_date else None,
                "received": loan.appraisal_received_date.isoformat() if loan.appraisal_received_date else None,
                "value": float(loan.appraisal_value) if loan.appraisal_value else None,
                "days_since_order": appraisal_days,
                "sla_target_days": 10,
            })

            # Title
            title_status = "not_ordered"
            title_days = None
            if loan.title_received_date:
                title_status = "received"
            elif loan.title_ordered_date:
                title_status = "ordered"
                od = loan.title_ordered_date
                title_days = (today - (od.date() if isinstance(od, datetime) else od)).days

            orders.append({
                "type": "title",
                "status": title_status,
                "ordered": loan.title_ordered_date.isoformat() if loan.title_ordered_date else None,
                "received": loan.title_received_date.isoformat() if loan.title_received_date else None,
                "company": loan.title_company,
                "days_since_order": title_days,
                "sla_target_days": VENDOR_SLA_TARGETS["title_order_to_received"],
            })

            # Insurance
            insurance_status = "not_ordered"
            insurance_days = None
            if loan.insurance_received_date:
                insurance_status = "received"
            elif loan.insurance_ordered_date:
                insurance_status = "ordered"
                od = loan.insurance_ordered_date
                insurance_days = (today - (od.date() if isinstance(od, datetime) else od)).days

            orders.append({
                "type": "insurance",
                "status": insurance_status,
                "ordered": loan.insurance_ordered_date.isoformat() if loan.insurance_ordered_date else None,
                "received": loan.insurance_received_date.isoformat() if loan.insurance_received_date else None,
                "flood_zone": loan.flood_zone,
                "flood_insurance_required": loan.flood_insurance_required,
                "days_since_order": insurance_days,
                "sla_target_days": VENDOR_SLA_TARGETS["insurance_order_to_received"],
            })

            pending = [o for o in orders if o["status"] not in ("received", "not_ordered")]
            completed = [o for o in orders if o["status"] == "received"]
            not_started = [o for o in orders if o["status"] == "not_ordered"]

            self.audit_log("check_all_vendor_orders", "loan", entity_id=loan_id, details={
                "pending": len(pending),
                "completed": len(completed),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "orders": orders,
                    "summary": {
                        "total": len(orders),
                        "completed": len(completed),
                        "pending": len(pending),
                        "not_started": len(not_started),
                    },
                },
                message=f"Vendor orders: {len(completed)} received, {len(pending)} pending, {len(not_started)} not ordered",
            )

        except Exception as e:
            logger.exception(f"check_all_vendor_orders failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_order_timing(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Recommend when to place each vendor order based on pipeline stage."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.stage, l.closing_date,
                    l.appraisal_ordered_date, l.title_ordered_date,
                    l.insurance_ordered_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            current_stage = loan.stage or "APPLICATION"
            recommendations = []

            stage_order = list(ORDER_TIMING_BY_STAGE.keys())
            try:
                current_idx = stage_order.index(current_stage)
            except ValueError:
                current_idx = 0

            # Check what has already been ordered
            already_ordered = set()
            if loan.appraisal_ordered_date:
                already_ordered.add("appraisal")
            if loan.title_ordered_date:
                already_ordered.add("title")
            if loan.insurance_ordered_date:
                already_ordered.add("insurance")

            for stage_name, order_types in ORDER_TIMING_BY_STAGE.items():
                stage_idx = stage_order.index(stage_name)
                for order_type in order_types:
                    if order_type in already_ordered:
                        continue

                    if stage_idx <= current_idx:
                        urgency = "order_now"
                        reason = f"Should have been ordered at {stage_name} stage"
                    elif stage_idx == current_idx + 1:
                        urgency = "order_soon"
                        reason = f"Order when loan reaches {stage_name}"
                    else:
                        urgency = "upcoming"
                        reason = f"Order at {stage_name} stage"

                    sla_key_map = {
                        "appraisal": "appraisal_order_to_schedule",
                        "title": "title_order_to_received",
                        "insurance": "insurance_order_to_received",
                        "flood_determination": "flood_determination",
                        "hoa_cert": "hoa_cert_order_to_received",
                    }
                    sla_days = VENDOR_SLA_TARGETS.get(sla_key_map.get(order_type, ""), 7)

                    recommendations.append({
                        "order_type": order_type,
                        "recommended_stage": stage_name,
                        "urgency": urgency,
                        "reason": reason,
                        "expected_turnaround_days": sla_days,
                    })

            # Sort: order_now first, then order_soon, then upcoming
            urgency_order = {"order_now": 0, "order_soon": 1, "upcoming": 2}
            recommendations.sort(key=lambda r: urgency_order.get(r["urgency"], 3))

            self.audit_log("recommend_order_timing", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "current_stage": current_stage,
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "already_ordered": list(already_ordered),
                    "recommendations": recommendations,
                },
                message=f"{len([r for r in recommendations if r['urgency'] == 'order_now'])} orders needed now",
            )

        except Exception as e:
            logger.exception(f"recommend_order_timing failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_appraisal_progress(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Detailed appraisal status tracking."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.amount,
                    l.property_address, l.property_type, l.loan_type,
                    l.appraisal_ordered_date, l.appraisal_scheduled_date,
                    l.appraisal_completed_date, l.appraisal_received_date,
                    l.appraisal_value, l.appraisal_docs_expire_date,
                    l.closing_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()

            # Build timeline
            timeline = []
            if loan.appraisal_ordered_date:
                timeline.append({"event": "ordered", "date": loan.appraisal_ordered_date.isoformat()})
            if loan.appraisal_scheduled_date:
                timeline.append({"event": "scheduled", "date": loan.appraisal_scheduled_date.isoformat()})
            if loan.appraisal_completed_date:
                timeline.append({"event": "completed", "date": loan.appraisal_completed_date.isoformat()})
            if loan.appraisal_received_date:
                timeline.append({"event": "received", "date": loan.appraisal_received_date.isoformat()})

            # Determine current status
            status = "not_ordered"
            if loan.appraisal_received_date:
                status = "received"
            elif loan.appraisal_completed_date:
                status = "completed_awaiting_receipt"
            elif loan.appraisal_scheduled_date:
                status = "scheduled"
            elif loan.appraisal_ordered_date:
                status = "ordered"

            # SLA check
            sla_status = "on_track"
            days_elapsed = 0
            total_sla = (
                VENDOR_SLA_TARGETS["appraisal_order_to_schedule"]
                + VENDOR_SLA_TARGETS["appraisal_schedule_to_complete"]
                + VENDOR_SLA_TARGETS["appraisal_complete_to_received"]
            )
            if loan.appraisal_ordered_date and not loan.appraisal_received_date:
                od = loan.appraisal_ordered_date
                days_elapsed = (today - (od.date() if isinstance(od, datetime) else od)).days
                if days_elapsed > total_sla:
                    sla_status = "breached"
                elif days_elapsed > total_sla * 0.75:
                    sla_status = "at_risk"

            # Expiration check
            expiring_soon = False
            if loan.appraisal_docs_expire_date:
                exp = loan.appraisal_docs_expire_date
                exp_date = exp.date() if isinstance(exp, datetime) else exp
                if exp_date < today:
                    expiring_soon = True
                elif (exp_date - today).days <= 30:
                    expiring_soon = True

            # LTV check
            ltv = None
            if loan.appraisal_value and loan.amount:
                ltv = round(float(loan.amount) / float(loan.appraisal_value) * 100, 2)

            self.audit_log("track_appraisal_progress", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "property_address": loan.property_address,
                    "property_type": loan.property_type,
                    "status": status,
                    "sla_status": sla_status,
                    "days_elapsed": days_elapsed,
                    "sla_target_days": total_sla,
                    "timeline": timeline,
                    "value": float(loan.appraisal_value) if loan.appraisal_value else None,
                    "loan_amount": float(loan.amount) if loan.amount else None,
                    "ltv": ltv,
                    "expiration_date": loan.appraisal_docs_expire_date.isoformat() if loan.appraisal_docs_expire_date else None,
                    "expiring_soon": expiring_soon,
                },
                message=f"Appraisal: {status} | SLA: {sla_status} ({days_elapsed}/{total_sla} days)",
            )

        except Exception as e:
            logger.exception(f"track_appraisal_progress failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_title_progress(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Track title search status and exception tracking."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.property_address, l.title_company,
                    l.title_ordered_date, l.title_received_date,
                    l.closing_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()

            status = "not_ordered"
            days_elapsed = None
            sla_status = "n/a"

            if loan.title_received_date:
                status = "received"
                sla_status = "completed"
            elif loan.title_ordered_date:
                status = "ordered"
                od = loan.title_ordered_date
                days_elapsed = (today - (od.date() if isinstance(od, datetime) else od)).days
                target = VENDOR_SLA_TARGETS["title_order_to_received"]
                if days_elapsed > target:
                    sla_status = "breached"
                elif days_elapsed > target * 0.75:
                    sla_status = "at_risk"
                else:
                    sla_status = "on_track"

            # Check for title-related compliance alerts
            title_alerts = db.execute(text("""
                SELECT id, title, severity, status, description
                FROM compliance_alerts
                WHERE loan_id = :loan_id
                AND alert_type IN ('title_exception', 'title_issue', 'lien', 'judgment')
                AND status = 'open'
                ORDER BY severity DESC
            """), {"loan_id": loan_id}).fetchall()

            exceptions = [
                {
                    "id": a.id,
                    "title": a.title,
                    "severity": a.severity,
                    "description": a.description,
                }
                for a in title_alerts
            ]

            self.audit_log("track_title_progress", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "property_address": loan.property_address,
                    "title_company": loan.title_company,
                    "status": status,
                    "sla_status": sla_status,
                    "days_elapsed": days_elapsed,
                    "sla_target_days": VENDOR_SLA_TARGETS["title_order_to_received"],
                    "ordered_date": loan.title_ordered_date.isoformat() if loan.title_ordered_date else None,
                    "received_date": loan.title_received_date.isoformat() if loan.title_received_date else None,
                    "exceptions": exceptions,
                    "exception_count": len(exceptions),
                },
                message=f"Title: {status} | SLA: {sla_status} | {len(exceptions)} exceptions",
            )

        except Exception as e:
            logger.exception(f"track_title_progress failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_insurance_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Track homeowners insurance status and flood determination."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.property_address,
                    l.insurance_ordered_date, l.insurance_received_date,
                    l.flood_zone, l.flood_insurance_required,
                    l.closing_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()

            # Homeowners insurance
            hi_status = "not_ordered"
            hi_days = None
            hi_sla = "n/a"

            if loan.insurance_received_date:
                hi_status = "received"
                hi_sla = "completed"
            elif loan.insurance_ordered_date:
                hi_status = "ordered"
                od = loan.insurance_ordered_date
                hi_days = (today - (od.date() if isinstance(od, datetime) else od)).days
                target = VENDOR_SLA_TARGETS["insurance_order_to_received"]
                if hi_days > target:
                    hi_sla = "breached"
                elif hi_days > target * 0.75:
                    hi_sla = "at_risk"
                else:
                    hi_sla = "on_track"

            # Flood status
            flood_zone = loan.flood_zone
            flood_required = loan.flood_insurance_required
            flood_high_risk = flood_zone in ("A", "AE", "AH", "AO", "AR", "V", "VE") if flood_zone else False

            self.audit_log("track_insurance_status", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "homeowners_insurance": {
                        "status": hi_status,
                        "sla_status": hi_sla,
                        "days_elapsed": hi_days,
                        "sla_target_days": VENDOR_SLA_TARGETS["insurance_order_to_received"],
                        "ordered": loan.insurance_ordered_date.isoformat() if loan.insurance_ordered_date else None,
                        "received": loan.insurance_received_date.isoformat() if loan.insurance_received_date else None,
                    },
                    "flood": {
                        "zone": flood_zone,
                        "insurance_required": flood_required,
                        "high_risk_zone": flood_high_risk,
                    },
                },
                message=f"Insurance: {hi_status} | Flood zone: {flood_zone or 'unknown'}",
            )

        except Exception as e:
            logger.exception(f"track_insurance_status failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_delayed_orders(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Find vendor orders behind expected SLA timelines across pipeline."""
        from database import SessionLocal

        org_id = self.require_org_id()
        lo_id = input_data.get("lo_id")
        limit = input_data.get("limit", 50)
        db = SessionLocal()

        try:
            params = {"org_id": org_id, "limit": limit}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            # Find loans with open vendor orders exceeding SLA
            appraisal_sla = (
                VENDOR_SLA_TARGETS["appraisal_order_to_schedule"]
                + VENDOR_SLA_TARGETS["appraisal_schedule_to_complete"]
                + VENDOR_SLA_TARGETS["appraisal_complete_to_received"]
            )
            title_sla = VENDOR_SLA_TARGETS["title_order_to_received"]
            insurance_sla = VENDOR_SLA_TARGETS["insurance_order_to_received"]

            params["appraisal_sla"] = appraisal_sla
            params["title_sla"] = title_sla
            params["insurance_sla"] = insurance_sla

            query = text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.closing_date,
                    l.appraisal_ordered_date, l.appraisal_received_date,
                    l.title_ordered_date, l.title_received_date,
                    l.insurance_ordered_date, l.insurance_received_date,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.organization_id = :org_id
                AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                {lo_filter}
                AND (
                    (l.appraisal_ordered_date IS NOT NULL
                     AND l.appraisal_received_date IS NULL
                     AND l.appraisal_ordered_date < CURRENT_DATE - :appraisal_sla)
                    OR
                    (l.title_ordered_date IS NOT NULL
                     AND l.title_received_date IS NULL
                     AND l.title_ordered_date < CURRENT_DATE - :title_sla)
                    OR
                    (l.insurance_ordered_date IS NOT NULL
                     AND l.insurance_received_date IS NULL
                     AND l.insurance_ordered_date < CURRENT_DATE - :insurance_sla)
                )
                ORDER BY l.closing_date ASC NULLS LAST
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            delayed_orders = []
            today = date.today()

            for r in results:
                loan_delays = []

                if r.appraisal_ordered_date and not r.appraisal_received_date:
                    od = r.appraisal_ordered_date
                    days = (today - (od.date() if isinstance(od, datetime) else od)).days
                    if days > appraisal_sla:
                        loan_delays.append({
                            "type": "appraisal",
                            "days_elapsed": days,
                            "sla_target": appraisal_sla,
                            "days_over": days - appraisal_sla,
                        })

                if r.title_ordered_date and not r.title_received_date:
                    od = r.title_ordered_date
                    days = (today - (od.date() if isinstance(od, datetime) else od)).days
                    if days > title_sla:
                        loan_delays.append({
                            "type": "title",
                            "days_elapsed": days,
                            "sla_target": title_sla,
                            "days_over": days - title_sla,
                        })

                if r.insurance_ordered_date and not r.insurance_received_date:
                    od = r.insurance_ordered_date
                    days = (today - (od.date() if isinstance(od, datetime) else od)).days
                    if days > insurance_sla:
                        loan_delays.append({
                            "type": "insurance",
                            "days_elapsed": days,
                            "sla_target": insurance_sla,
                            "days_over": days - insurance_sla,
                        })

                if loan_delays:
                    delayed_orders.append({
                        "loan_id": r.id,
                        "loan_number": r.loan_number,
                        "borrower": r.borrower_name,
                        "stage": r.stage,
                        "lo_name": r.lo_name,
                        "closing_date": r.closing_date.isoformat() if r.closing_date else None,
                        "delayed_orders": loan_delays,
                    })

            self.audit_log("identify_delayed_orders", details={
                "delayed_count": len(delayed_orders),
            })

            return ToolResult(
                success=True,
                data={
                    "delayed_loans": delayed_orders,
                    "total_delayed_loans": len(delayed_orders),
                    "total_delayed_orders": sum(len(d["delayed_orders"]) for d in delayed_orders),
                },
                message=f"{len(delayed_orders)} loans with delayed vendor orders",
            )

        except Exception as e:
            logger.exception("identify_delayed_orders failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _escalate_delayed_vendor(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create escalation for a vendor missing SLA."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        vendor_type = input_data["vendor_type"]
        reason = input_data["reason"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.loan_officer_id,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Insert compliance alert as escalation record
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, alert_type, severity, title, description, status, created_at)
                VALUES
                    (:loan_id, :alert_type, 'high',
                     :title, :description, 'open', CURRENT_TIMESTAMP)
            """), {
                "loan_id": loan_id,
                "alert_type": f"vendor_delay_{vendor_type}",
                "title": f"Vendor SLA breach: {vendor_type}",
                "description": f"Vendor delay escalation for {vendor_type} on loan {loan.loan_number}. Reason: {reason}",
            })
            db.commit()

            self.audit_log("escalate_delayed_vendor", "loan", entity_id=loan_id, details={
                "vendor_type": vendor_type,
                "reason": reason,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "vendor_type": vendor_type,
                    "escalated_to": loan.lo_name,
                    "reason": reason,
                    "status": "open",
                    "created_at": datetime.now().isoformat(),
                },
                message=f"Escalation created for {vendor_type} delay on loan {loan.loan_number}",
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"escalate_delayed_vendor failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _validate_appraisal_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check appraisal for common issues."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.amount, l.loan_type,
                    l.property_type, l.occupancy_type,
                    l.appraisal_value, l.appraisal_received_date,
                    l.purchase_price
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            if not loan.appraisal_received_date:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "status": "not_received"},
                    message="Appraisal has not been received yet",
                )

            issues = []
            warnings = []

            appraisal_value = float(loan.appraisal_value) if loan.appraisal_value else 0
            loan_amount = float(loan.amount) if loan.amount else 0
            purchase_price = float(loan.purchase_price) if loan.purchase_price else 0

            # LTV check
            if appraisal_value > 0 and loan_amount > 0:
                ltv = loan_amount / appraisal_value * 100
                if ltv > 97:
                    issues.append({
                        "type": "HIGH_LTV",
                        "severity": "high",
                        "message": f"LTV is {ltv:.1f}% — exceeds 97% maximum for most programs",
                    })
                elif ltv > 95:
                    warnings.append({
                        "type": "ELEVATED_LTV",
                        "message": f"LTV is {ltv:.1f}% — MI required, limited program eligibility",
                    })

            # Value vs purchase price (appraisal gap)
            if appraisal_value > 0 and purchase_price > 0:
                if appraisal_value < purchase_price:
                    gap = purchase_price - appraisal_value
                    issues.append({
                        "type": "APPRAISAL_GAP",
                        "severity": "high",
                        "message": f"Appraisal value ${appraisal_value:,.0f} is below purchase price ${purchase_price:,.0f} (gap: ${gap:,.0f})",
                    })
                elif appraisal_value > purchase_price * 1.15:
                    warnings.append({
                        "type": "VALUE_OVERSHOOT",
                        "message": f"Appraisal value ${appraisal_value:,.0f} is >15% above purchase price ${purchase_price:,.0f} — verify comparable support",
                    })

            # Condo/manufactured property flags
            if loan.property_type in ("condo", "CONDO"):
                warnings.append({
                    "type": "CONDO_REVIEW",
                    "message": "Condo appraisal — verify HOA questionnaire and project approval",
                })
            if loan.property_type in ("manufactured", "MANUFACTURED"):
                issues.append({
                    "type": "MANUFACTURED_HOME",
                    "severity": "medium",
                    "message": "Manufactured home — verify foundation certification and HUD compliance",
                })

            # Investment property
            if loan.occupancy_type in ("investment", "INVESTMENT"):
                warnings.append({
                    "type": "INVESTMENT_PROPERTY",
                    "message": "Investment property — verify rental income analysis and market rent comparables",
                })

            is_clean = len(issues) == 0

            self.audit_log("validate_appraisal_report", "loan", entity_id=loan_id, details={
                "issues": len(issues),
                "warnings": len(warnings),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "appraisal_value": appraisal_value,
                    "purchase_price": purchase_price,
                    "loan_amount": loan_amount,
                    "ltv": round(loan_amount / appraisal_value * 100, 2) if appraisal_value > 0 else None,
                    "is_clean": is_clean,
                    "issues": issues,
                    "warnings": warnings,
                },
                message=f"Appraisal: {'Clean' if is_clean else f'{len(issues)} issues found'}, {len(warnings)} warnings",
            )

        except Exception as e:
            logger.exception(f"validate_appraisal_report failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _validate_title_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check title report for liens, judgments, and exceptions."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.property_address, l.title_company,
                    l.title_ordered_date, l.title_received_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            if not loan.title_received_date:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "status": "not_received"},
                    message="Title report has not been received yet",
                )

            # Check for title-related compliance alerts
            alerts = db.execute(text("""
                SELECT id, alert_type, severity, title, description, status
                FROM compliance_alerts
                WHERE loan_id = :loan_id
                AND (
                    alert_type LIKE '%title%'
                    OR alert_type LIKE '%lien%'
                    OR alert_type LIKE '%judgment%'
                    OR alert_type LIKE '%easement%'
                )
                ORDER BY
                    CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3 ELSE 4 END
            """), {"loan_id": loan_id}).fetchall()

            issues = []
            for a in alerts:
                if a.status == "open":
                    issues.append({
                        "alert_id": a.id,
                        "type": a.alert_type,
                        "severity": a.severity,
                        "title": a.title,
                        "description": a.description,
                    })

            is_clear = len(issues) == 0

            self.audit_log("validate_title_report", "loan", entity_id=loan_id, details={
                "issues": len(issues),
                "is_clear": is_clear,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "property_address": loan.property_address,
                    "title_company": loan.title_company,
                    "title_received": loan.title_received_date.isoformat(),
                    "is_clear": is_clear,
                    "issues": issues,
                    "issue_count": len(issues),
                },
                message=f"Title: {'Clear' if is_clear else f'{len(issues)} open issues'}",
            )

        except Exception as e:
            logger.exception(f"validate_title_report failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_flood_determination(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Verify flood zone status and insurance requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.property_address,
                    l.flood_zone, l.flood_insurance_required,
                    l.insurance_ordered_date, l.insurance_received_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            high_risk_zones = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
            moderate_risk_zones = {"B", "X500", "X (shaded)"}
            low_risk_zones = {"C", "X", "X (unshaded)"}

            flood_zone = loan.flood_zone
            is_high_risk = flood_zone in high_risk_zones if flood_zone else False
            is_moderate_risk = flood_zone in moderate_risk_zones if flood_zone else False
            is_low_risk = flood_zone in low_risk_zones if flood_zone else False

            risk_category = "unknown"
            if is_high_risk:
                risk_category = "high"
            elif is_moderate_risk:
                risk_category = "moderate"
            elif is_low_risk:
                risk_category = "low"

            issues = []
            if flood_zone is None:
                issues.append({
                    "type": "NO_FLOOD_CERT",
                    "severity": "high",
                    "message": "No flood determination on file — required for all loans",
                })
            elif is_high_risk and not loan.flood_insurance_required:
                issues.append({
                    "type": "FLOOD_INSURANCE_MISSING",
                    "severity": "critical",
                    "message": f"Property in high-risk flood zone {flood_zone} but flood insurance not flagged as required",
                })
            elif is_high_risk and not loan.insurance_received_date:
                issues.append({
                    "type": "FLOOD_POLICY_PENDING",
                    "severity": "high",
                    "message": f"Property in flood zone {flood_zone} — flood insurance policy not yet received",
                })

            self.audit_log("check_flood_determination", "loan", entity_id=loan_id, details={
                "flood_zone": flood_zone,
                "risk_category": risk_category,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "property_address": loan.property_address,
                    "flood_zone": flood_zone,
                    "risk_category": risk_category,
                    "flood_insurance_required": loan.flood_insurance_required or is_high_risk,
                    "insurance_received": loan.insurance_received_date is not None,
                    "issues": issues,
                },
                message=f"Flood zone: {flood_zone or 'UNKNOWN'} ({risk_category} risk) | {len(issues)} issues",
            )

        except Exception as e:
            logger.exception(f"check_flood_determination failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _coordinate_closing_vendors(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Ensure all vendors are aligned on closing date."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.closing_date, l.title_company,
                    l.appraisal_received_date, l.appraisal_docs_expire_date,
                    l.title_received_date,
                    l.insurance_received_date,
                    l.cd_sent_to_borrower_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()
            closing_date = loan.closing_date
            readiness_items = []
            blockers = []

            # Appraisal readiness
            if loan.appraisal_received_date:
                appraisal_ready = True
                # Check expiration
                if loan.appraisal_docs_expire_date:
                    exp = loan.appraisal_docs_expire_date
                    exp_date = exp.date() if isinstance(exp, datetime) else exp
                    if closing_date and exp_date < (closing_date.date() if isinstance(closing_date, datetime) else closing_date):
                        appraisal_ready = False
                        blockers.append("Appraisal expires before closing date — reorder required")
                readiness_items.append({"vendor": "appraisal", "ready": appraisal_ready, "status": "received"})
            else:
                readiness_items.append({"vendor": "appraisal", "ready": False, "status": "not_received"})
                blockers.append("Appraisal not received")

            # Title readiness
            if loan.title_received_date:
                readiness_items.append({"vendor": "title", "ready": True, "status": "received"})
            else:
                readiness_items.append({"vendor": "title", "ready": False, "status": "not_received"})
                blockers.append("Title not received")

            # Insurance readiness
            if loan.insurance_received_date:
                readiness_items.append({"vendor": "insurance", "ready": True, "status": "received"})
            else:
                readiness_items.append({"vendor": "insurance", "ready": False, "status": "not_received"})
                blockers.append("Insurance binder not received")

            # CD timing
            if loan.cd_sent_to_borrower_date:
                cd_date = loan.cd_sent_to_borrower_date
                cd_d = cd_date.date() if isinstance(cd_date, datetime) else cd_date
                if closing_date:
                    cl_d = closing_date.date() if isinstance(closing_date, datetime) else closing_date
                    cd_gap = (cl_d - cd_d).days
                    if cd_gap < 3:
                        blockers.append(f"CD sent only {cd_gap} days before closing (3 required)")
                readiness_items.append({"vendor": "cd_delivery", "ready": True, "status": "sent"})
            else:
                readiness_items.append({"vendor": "cd_delivery", "ready": False, "status": "not_sent"})
                blockers.append("Closing Disclosure not yet sent to borrower")

            all_ready = len(blockers) == 0
            days_to_close = None
            if closing_date:
                cl_d = closing_date.date() if isinstance(closing_date, datetime) else closing_date
                days_to_close = (cl_d - today).days

            self.audit_log("coordinate_closing_vendors", "loan", entity_id=loan_id, details={
                "all_ready": all_ready,
                "blocker_count": len(blockers),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "closing_date": closing_date.isoformat() if closing_date else None,
                    "days_to_close": days_to_close,
                    "all_ready": all_ready,
                    "readiness": readiness_items,
                    "blockers": blockers,
                },
                message=f"Closing readiness: {'READY' if all_ready else f'{len(blockers)} blockers'} | {days_to_close} days to close" if days_to_close is not None else f"Closing readiness: {'READY' if all_ready else f'{len(blockers)} blockers'}",
            )

        except Exception as e:
            logger.exception(f"coordinate_closing_vendors failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_vendor_costs(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Track and forecast vendor costs per loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.amount, l.loan_type,
                    l.property_type
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Pull from loan_fees table if available
            fees = db.execute(text("""
                SELECT fee_name, fee_category, cd_amount
                FROM loan_fees
                WHERE loan_id = :loan_id
                AND fee_category IN ('appraisal', 'title', 'insurance', 'recording', 'vendor', 'third_party')
            """), {"loan_id": loan_id}).fetchall()

            vendor_costs = []
            total = 0.0

            if fees:
                for f in fees:
                    amt = float(f.cd_amount) if f.cd_amount else 0
                    total += amt
                    vendor_costs.append({
                        "fee_name": f.fee_name,
                        "category": f.fee_category,
                        "amount": amt,
                    })
            else:
                # Estimate typical costs if no fee data available
                loan_amount = float(loan.amount) if loan.amount else 350000
                estimates = [
                    {"fee_name": "Appraisal Fee", "category": "appraisal", "amount": 550.0},
                    {"fee_name": "Title Search", "category": "title", "amount": 350.0},
                    {"fee_name": "Title Insurance (Lender)", "category": "title", "amount": round(loan_amount * 0.002, 2)},
                    {"fee_name": "Homeowners Insurance (Annual)", "category": "insurance", "amount": round(loan_amount * 0.004, 2)},
                    {"fee_name": "Flood Certification", "category": "vendor", "amount": 20.0},
                    {"fee_name": "Recording Fees", "category": "recording", "amount": 125.0},
                ]
                for est in estimates:
                    total += est["amount"]
                    vendor_costs.append(est)
                vendor_costs = [dict(c, estimated=True) for c in vendor_costs]

            self.audit_log("calculate_vendor_costs", "loan", entity_id=loan_id)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "vendor_costs": vendor_costs,
                    "total_vendor_costs": round(total, 2),
                    "is_estimated": len(fees) == 0,
                },
                message=f"Vendor costs: ${total:,.2f} ({'estimated' if not fees else 'from fee schedule'})",
            )

        except Exception as e:
            logger.exception(f"calculate_vendor_costs failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _rate_vendor_performance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Score vendors on timeliness, quality, and responsiveness."""
        from database import SessionLocal

        vendor_type = input_data["vendor_type"]
        days = input_data.get("days", 90)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            date_columns = {
                "appraisal": {
                    "ordered": "appraisal_ordered_date",
                    "received": "appraisal_received_date",
                    "vendor_col": None,
                    "sla_target": (
                        VENDOR_SLA_TARGETS["appraisal_order_to_schedule"]
                        + VENDOR_SLA_TARGETS["appraisal_schedule_to_complete"]
                        + VENDOR_SLA_TARGETS["appraisal_complete_to_received"]
                    ),
                },
                "title": {
                    "ordered": "title_ordered_date",
                    "received": "title_received_date",
                    "vendor_col": "title_company",
                    "sla_target": VENDOR_SLA_TARGETS["title_order_to_received"],
                },
                "insurance": {
                    "ordered": "insurance_ordered_date",
                    "received": "insurance_received_date",
                    "vendor_col": None,
                    "sla_target": VENDOR_SLA_TARGETS["insurance_order_to_received"],
                },
            }

            if vendor_type not in date_columns:
                return ToolResult(
                    success=False,
                    error=f"Invalid vendor_type: {vendor_type}. Must be: appraisal, title, insurance",
                )

            cfg = date_columns[vendor_type]
            ordered_col = cfg["ordered"]
            received_col = cfg["received"]
            vendor_col = cfg["vendor_col"]
            sla_target = cfg["sla_target"]

            # Build vendor grouping
            if vendor_col:
                group_select = f"l.{vendor_col} as vendor_name,"
                group_by = f"GROUP BY l.{vendor_col}"
            else:
                group_select = "'all' as vendor_name,"
                group_by = ""

            query = text(f"""
                SELECT
                    {group_select}
                    COUNT(*) as total_orders,
                    COUNT(CASE WHEN l.{received_col} IS NOT NULL THEN 1 END) as completed_orders,
                    AVG(
                        CASE WHEN l.{received_col} IS NOT NULL THEN
                            EXTRACT(EPOCH FROM (l.{received_col} - l.{ordered_col})) / 86400
                        END
                    ) as avg_turnaround_days,
                    COUNT(
                        CASE WHEN l.{received_col} IS NOT NULL
                             AND EXTRACT(EPOCH FROM (l.{received_col} - l.{ordered_col})) / 86400 <= :sla_target
                        THEN 1 END
                    ) as on_time_count
                FROM loans l
                WHERE l.organization_id = :org_id
                AND l.{ordered_col} IS NOT NULL
                AND l.{ordered_col} >= CURRENT_DATE - :days
                {group_by}
                ORDER BY total_orders DESC
            """)

            results = db.execute(query, {
                "org_id": org_id,
                "days": days,
                "sla_target": sla_target,
            }).fetchall()

            vendor_scores = []
            for r in results:
                completed = r.completed_orders or 0
                total = r.total_orders or 0
                on_time = r.on_time_count or 0
                avg_days = float(r.avg_turnaround_days) if r.avg_turnaround_days else None

                on_time_pct = round(on_time / completed * 100, 1) if completed > 0 else 0
                completion_pct = round(completed / total * 100, 1) if total > 0 else 0

                # Composite score: 60% on-time rate + 40% completion rate
                score = round(on_time_pct * 0.6 + completion_pct * 0.4, 1)

                vendor_scores.append({
                    "vendor_name": r.vendor_name,
                    "total_orders": total,
                    "completed_orders": completed,
                    "on_time_count": on_time,
                    "on_time_rate": on_time_pct,
                    "completion_rate": completion_pct,
                    "avg_turnaround_days": round(avg_days, 1) if avg_days else None,
                    "sla_target_days": sla_target,
                    "performance_score": score,
                })

            vendor_scores.sort(key=lambda v: v["performance_score"], reverse=True)

            self.audit_log("rate_vendor_performance", details={
                "vendor_type": vendor_type,
                "vendor_count": len(vendor_scores),
            })

            return ToolResult(
                success=True,
                data={
                    "vendor_type": vendor_type,
                    "period_days": days,
                    "sla_target_days": sla_target,
                    "vendors": vendor_scores,
                },
                message=f"{len(vendor_scores)} {vendor_type} vendors scored over {days} days",
            )

        except Exception as e:
            logger.exception(f"rate_vendor_performance failed for {vendor_type}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_vendor_dashboard(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Summary of all vendor orders across active pipeline."""
        from database import SessionLocal

        org_id = self.require_org_id()
        lo_id = input_data.get("lo_id")
        db = SessionLocal()

        try:
            params = {"org_id": org_id}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            query = text(f"""
                SELECT
                    COUNT(*) as total_active,
                    COUNT(CASE WHEN l.appraisal_ordered_date IS NOT NULL
                               AND l.appraisal_received_date IS NULL THEN 1 END) as appraisal_pending,
                    COUNT(CASE WHEN l.appraisal_received_date IS NOT NULL THEN 1 END) as appraisal_complete,
                    COUNT(CASE WHEN l.appraisal_ordered_date IS NULL
                               AND l.stage NOT IN ('APPLICATION', 'DISCLOSED') THEN 1 END) as appraisal_not_ordered,
                    COUNT(CASE WHEN l.title_ordered_date IS NOT NULL
                               AND l.title_received_date IS NULL THEN 1 END) as title_pending,
                    COUNT(CASE WHEN l.title_received_date IS NOT NULL THEN 1 END) as title_complete,
                    COUNT(CASE WHEN l.title_ordered_date IS NULL
                               AND l.stage NOT IN ('APPLICATION', 'DISCLOSED') THEN 1 END) as title_not_ordered,
                    COUNT(CASE WHEN l.insurance_ordered_date IS NOT NULL
                               AND l.insurance_received_date IS NULL THEN 1 END) as insurance_pending,
                    COUNT(CASE WHEN l.insurance_received_date IS NOT NULL THEN 1 END) as insurance_complete,
                    COUNT(CASE WHEN l.insurance_ordered_date IS NULL
                               AND l.stage NOT IN ('APPLICATION', 'DISCLOSED', 'PROCESSING') THEN 1 END) as insurance_not_ordered
                FROM loans l
                WHERE l.organization_id = :org_id
                AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                {lo_filter}
            """)

            result = db.execute(query, params).fetchone()

            if not result or result.total_active == 0:
                return ToolResult(
                    success=True,
                    data={"total_active": 0, "message": "No active loans in pipeline"},
                    message="No active loans for vendor dashboard",
                )

            dashboard = {
                "total_active_loans": result.total_active,
                "appraisal": {
                    "pending": result.appraisal_pending,
                    "complete": result.appraisal_complete,
                    "not_ordered": result.appraisal_not_ordered,
                },
                "title": {
                    "pending": result.title_pending,
                    "complete": result.title_complete,
                    "not_ordered": result.title_not_ordered,
                },
                "insurance": {
                    "pending": result.insurance_pending,
                    "complete": result.insurance_complete,
                    "not_ordered": result.insurance_not_ordered,
                },
                "total_pending": (
                    result.appraisal_pending + result.title_pending + result.insurance_pending
                ),
                "total_complete": (
                    result.appraisal_complete + result.title_complete + result.insurance_complete
                ),
            }

            self.audit_log("generate_vendor_dashboard", details={
                "total_active": result.total_active,
                "total_pending": dashboard["total_pending"],
            })

            return ToolResult(
                success=True,
                data=dashboard,
                message=(
                    f"Vendor Dashboard: {dashboard['total_pending']} pending, "
                    f"{dashboard['total_complete']} complete across {result.total_active} loans"
                ),
            )

        except Exception as e:
            logger.exception("generate_vendor_dashboard failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_vendor_selection(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Recommend best vendor based on performance data and geography."""
        from database import SessionLocal

        vendor_type = input_data["vendor_type"]
        state = input_data.get("state")
        county = input_data.get("county")
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            # Only title has a vendor_col we can group by
            if vendor_type != "title":
                return ToolResult(
                    success=True,
                    data={
                        "vendor_type": vendor_type,
                        "recommendation": (
                            f"Vendor selection for {vendor_type} requires AMC/panel management. "
                            "Use rate_vendor_performance to evaluate current {vendor_type} turnaround times."
                        ),
                    },
                    message=f"Vendor selection for {vendor_type} managed through AMC/panel",
                )

            params = {"org_id": org_id}
            geo_filter = ""
            if state:
                geo_filter += " AND l.property_state = :state"
                params["state"] = state
            if county:
                geo_filter += " AND l.property_county = :county"
                params["county"] = county

            sla_target = VENDOR_SLA_TARGETS["title_order_to_received"]
            params["sla_target"] = sla_target

            query = text(f"""
                SELECT
                    l.title_company as vendor_name,
                    COUNT(*) as total_orders,
                    COUNT(CASE WHEN l.title_received_date IS NOT NULL THEN 1 END) as completed,
                    AVG(
                        CASE WHEN l.title_received_date IS NOT NULL THEN
                            EXTRACT(EPOCH FROM (l.title_received_date - l.title_ordered_date)) / 86400
                        END
                    ) as avg_days,
                    COUNT(
                        CASE WHEN l.title_received_date IS NOT NULL
                             AND EXTRACT(EPOCH FROM (l.title_received_date - l.title_ordered_date)) / 86400 <= :sla_target
                        THEN 1 END
                    ) as on_time
                FROM loans l
                WHERE l.organization_id = :org_id
                AND l.title_company IS NOT NULL
                AND l.title_ordered_date IS NOT NULL
                AND l.title_ordered_date >= CURRENT_DATE - 180
                {geo_filter}
                GROUP BY l.title_company
                HAVING COUNT(*) >= 3
                ORDER BY
                    COUNT(CASE WHEN l.title_received_date IS NOT NULL
                               AND EXTRACT(EPOCH FROM (l.title_received_date - l.title_ordered_date)) / 86400 <= :sla_target
                          THEN 1 END)::float / NULLIF(COUNT(CASE WHEN l.title_received_date IS NOT NULL THEN 1 END), 0) DESC NULLS LAST
                LIMIT 5
            """)

            results = db.execute(query, params).fetchall()

            recommendations = []
            for r in results:
                completed = r.completed or 0
                on_time = r.on_time or 0
                on_time_pct = round(on_time / completed * 100, 1) if completed > 0 else 0
                avg_days = round(float(r.avg_days), 1) if r.avg_days else None

                recommendations.append({
                    "vendor_name": r.vendor_name,
                    "total_orders": r.total_orders,
                    "completed_orders": completed,
                    "on_time_rate": on_time_pct,
                    "avg_turnaround_days": avg_days,
                    "recommendation": "recommended" if on_time_pct >= 80 else "acceptable" if on_time_pct >= 60 else "review",
                })

            self.audit_log("recommend_vendor_selection", details={
                "vendor_type": vendor_type,
                "state": state,
                "results": len(recommendations),
            })

            return ToolResult(
                success=True,
                data={
                    "vendor_type": vendor_type,
                    "geography": {"state": state, "county": county},
                    "recommendations": recommendations,
                    "top_pick": recommendations[0] if recommendations else None,
                },
                message=f"{len(recommendations)} {vendor_type} vendors ranked" if recommendations else "No vendor data available for this geography",
            )

        except Exception as e:
            logger.exception(f"recommend_vendor_selection failed for {vendor_type}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
