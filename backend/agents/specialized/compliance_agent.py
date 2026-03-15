"""
Compliance Agent

Specialized agent for regulatory compliance monitoring with 8 tools:
1. check_trid_compliance - Check TRID disclosure requirements
2. check_loan_limits - Verify loan against conforming limits
3. get_audit_checklist - Get compliance audit checklist
4. log_disclosure - Log disclosure delivery
5. check_timeline_compliance - Verify regulatory timelines
6. get_state_requirements - Get state-specific requirements
7. flag_compliance_issue - Flag a compliance concern
8. get_compliance_report - Generate compliance report
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
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CheckTridComplianceInput(BaseModel):
    """Input schema for check_trid_compliance tool"""
    loan_id: int = Field(..., description="Loan ID to check")
    check_type: str = Field(default="all", description="Type: le, cd, all")


class CheckLoanLimitsInput(BaseModel):
    """Input schema for check_loan_limits tool"""
    loan_amount: float = Field(..., description="Loan amount to check")
    county: str = Field(..., description="County name")
    state: str = Field(..., description="State abbreviation")
    property_type: str = Field(default="single_family", description="Property type")
    units: int = Field(default=1, description="Number of units (1-4)")


class GetAuditChecklistInput(BaseModel):
    """Input schema for get_audit_checklist tool"""
    loan_id: int = Field(..., description="Loan ID")
    loan_type: Optional[str] = Field(None, description="Loan type: conventional, fha, va")
    include_completed: bool = Field(default=False, description="Include completed items")


class LogDisclosureInput(BaseModel):
    """Input schema for log_disclosure tool"""
    loan_id: int = Field(..., description="Loan ID")
    disclosure_type: str = Field(..., description="Type: initial_le, revised_le, initial_cd, final_cd, intent_to_proceed")
    delivery_method: str = Field(..., description="Method: email, mail, in_person, esign")
    delivery_date: str = Field(..., description="Delivery date (ISO format)")
    recipient_email: Optional[str] = Field(None, description="Recipient email if applicable")


class CheckTimelineComplianceInput(BaseModel):
    """Input schema for check_timeline_compliance tool"""
    loan_id: int = Field(..., description="Loan ID to check")


class GetStateRequirementsInput(BaseModel):
    """Input schema for get_state_requirements tool"""
    state: str = Field(..., description="State abbreviation (e.g., CA, TX)")
    loan_type: Optional[str] = Field(None, description="Filter by loan type")


class FlagComplianceIssueInput(BaseModel):
    """Input schema for flag_compliance_issue tool"""
    loan_id: int = Field(..., description="Loan ID")
    issue_type: str = Field(..., description="Type: trid, tolerance, timing, documentation, other")
    severity: str = Field(..., description="Severity: low, medium, high, critical")
    description: str = Field(..., description="Description of the issue")
    remediation_required: bool = Field(default=True, description="Whether remediation is required")


class GetComplianceReportInput(BaseModel):
    """Input schema for get_compliance_report tool"""
    start_date: Optional[str] = Field(None, description="Report start date")
    end_date: Optional[str] = Field(None, description="Report end date")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")
    include_details: bool = Field(default=False, description="Include loan-level details")


# ============================================================================
# COMPLIANCE AGENT
# ============================================================================

@AgentRegistry.register
class ComplianceAgent(SpecializedAgent):
    """
    Specialized agent for regulatory compliance.

    Monitors TRID compliance, loan limits, disclosure timelines,
    and state-specific requirements.
    """

    @property
    def name(self) -> str:
        return "ComplianceAgent"

    @property
    def description(self) -> str:
        return "Monitors regulatory compliance including TRID, disclosure timelines, and state requirements"

    def _register_tools(self):
        """Register all compliance tools"""

        # Tool 1: Check TRID Compliance
        self.register_tool(AgentTool(
            name="check_trid_compliance",
            description="Check TRID (TILA-RESPA Integrated Disclosure) compliance for a loan. "
                       "Verifies LE and CD delivery timing and tolerance requirements.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_trid_compliance,
            input_schema=CheckTridComplianceInput
        ))

        # Tool 2: Check Loan Limits
        self.register_tool(AgentTool(
            name="check_loan_limits",
            description="Check if loan amount is within conforming limits for the county. "
                       "Identifies if loan is conforming, high-balance, or jumbo.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_loan_limits,
            input_schema=CheckLoanLimitsInput
        ))

        # Tool 3: Get Audit Checklist
        self.register_tool(AgentTool(
            name="get_audit_checklist",
            description="Get compliance audit checklist for a loan. "
                       "Shows required items and their completion status.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_audit_checklist,
            input_schema=GetAuditChecklistInput
        ))

        # Tool 4: Log Disclosure
        self.register_tool(AgentTool(
            name="log_disclosure",
            description="Log delivery of a disclosure document. "
                       "Records type, delivery method, and date for compliance tracking.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._log_disclosure,
            input_schema=LogDisclosureInput
        ))

        # Tool 5: Check Timeline Compliance
        self.register_tool(AgentTool(
            name="check_timeline_compliance",
            description="Verify regulatory timeline requirements for a loan. "
                       "Checks disclosure delivery dates and waiting periods.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_timeline_compliance,
            input_schema=CheckTimelineComplianceInput
        ))

        # Tool 6: Get State Requirements
        self.register_tool(AgentTool(
            name="get_state_requirements",
            description="Get state-specific mortgage lending requirements. "
                       "Includes licensing, disclosures, and restrictions.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_state_requirements,
            input_schema=GetStateRequirementsInput
        ))

        # Tool 7: Flag Compliance Issue
        self.register_tool(AgentTool(
            name="flag_compliance_issue",
            description="Flag a compliance issue for a loan. "
                       "Creates tracking record and triggers workflow if critical.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._flag_compliance_issue,
            input_schema=FlagComplianceIssueInput
        ))

        # Tool 8: Get Compliance Report
        self.register_tool(AgentTool(
            name="get_compliance_report",
            description="Generate compliance summary report. "
                       "Shows issues, trends, and audit results.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_compliance_report,
            input_schema=GetComplianceReportInput
        ))

    # ========================================================================
    # HELPERS
    # ========================================================================

    @staticmethod
    def _add_business_days(start_date, num_days: int):
        """Add business days (Mon-Fri) to a date. Negative num_days subtracts."""
        if start_date is None:
            return None
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        current = start_date
        step = 1 if num_days >= 0 else -1
        remaining = abs(num_days)
        while remaining > 0:
            current += timedelta(days=step)
            if current.weekday() < 5:  # Mon-Fri
                remaining -= 1
        return current

    @staticmethod
    def _business_days_between(start, end) -> int:
        """Count business days between two dates (exclusive of start, inclusive of end)."""
        if start is None or end is None:
            return 0
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        if end <= start:
            return 0
        count = 0
        current = start
        while current < end:
            current += timedelta(days=1)
            if current.weekday() < 5:
                count += 1
        return count

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _check_trid_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check TRID compliance for a loan"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        check_type = input_data.get("check_type", "all")

        db = SessionLocal()
        try:
            # Get loan info with tenant isolation
            org_id = self.context.get("organization_id")
            org_clause = "AND organization_id = :org_id" if org_id else ""
            loan_params: dict = {"loan_id": loan_id}
            if org_id:
                loan_params["org_id"] = org_id

            loan = db.execute(
                text(f"""
                    SELECT
                        id, loan_number, borrower_name, amount,
                        application_date, lock_date, closing_date,
                        created_at
                    FROM loans WHERE id = :loan_id {org_clause}
                """),
                loan_params
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get disclosure history
            disclosures = db.execute(
                text("""
                    SELECT
                        disclosure_type, delivery_date, delivery_method
                    FROM disclosures
                    WHERE loan_id = :loan_id
                    ORDER BY delivery_date
                """),
                {"loan_id": loan_id}
            ).fetchall()

            disclosure_map = {d.disclosure_type: d for d in disclosures}

            compliance_checks = []
            issues = []
            app_date = loan.application_date or loan.created_at

            # LE Checks
            if check_type in ["le", "all"]:
                initial_le = disclosure_map.get("initial_le")

                # Initial LE must be delivered within 3 BUSINESS days of application
                le_deadline = self._add_business_days(app_date, 3) if app_date else None

                if initial_le:
                    le_delivered = initial_le.delivery_date
                    if le_deadline and le_delivered > le_deadline.date():
                        issues.append({
                            "type": "timing",
                            "severity": "high",
                            "description": f"Initial LE delivered late ({le_delivered} vs deadline {le_deadline.date()})"
                        })
                        compliance_checks.append({
                            "check": "Initial LE timing",
                            "status": "failed",
                            "deadline": le_deadline.date().isoformat() if le_deadline else None,
                            "actual": le_delivered.isoformat() if le_delivered else None
                        })
                    else:
                        compliance_checks.append({
                            "check": "Initial LE timing",
                            "status": "passed",
                            "deadline": le_deadline.date().isoformat() if le_deadline else None,
                            "actual": le_delivered.isoformat() if le_delivered else None
                        })
                else:
                    issues.append({
                        "type": "missing",
                        "severity": "critical",
                        "description": "Initial LE not delivered"
                    })
                    compliance_checks.append({
                        "check": "Initial LE timing",
                        "status": "missing",
                        "deadline": le_deadline.date().isoformat() if le_deadline else None,
                        "actual": None
                    })

            # CD Checks
            if check_type in ["cd", "all"]:
                initial_cd = disclosure_map.get("initial_cd")
                closing = loan.closing_date

                if closing:
                    # Initial CD must be delivered at least 3 BUSINESS days before closing
                    cd_deadline = self._add_business_days(closing, -3)

                    if initial_cd:
                        cd_delivered = initial_cd.delivery_date
                        if cd_delivered > cd_deadline:
                            issues.append({
                                "type": "timing",
                                "severity": "critical",
                                "description": f"Initial CD delivered too late for closing ({cd_delivered} vs required {cd_deadline})"
                            })
                            compliance_checks.append({
                                "check": "Initial CD timing",
                                "status": "failed",
                                "deadline": cd_deadline.isoformat(),
                                "actual": cd_delivered.isoformat() if cd_delivered else None
                            })
                        else:
                            compliance_checks.append({
                                "check": "Initial CD timing",
                                "status": "passed",
                                "deadline": cd_deadline.isoformat(),
                                "actual": cd_delivered.isoformat() if cd_delivered else None
                            })
                    else:
                        issues.append({
                            "type": "missing",
                            "severity": "high",
                            "description": "Initial CD not delivered"
                        })
                        compliance_checks.append({
                            "check": "Initial CD timing",
                            "status": "missing",
                            "deadline": cd_deadline.isoformat(),
                            "actual": None
                        })

            # Fee tolerance check — compare LE to CD amounts from loan_fees table
            try:
                fees = db.execute(
                    text("""
                        SELECT fee_name, tolerance_category, le_amount, cd_amount
                        FROM loan_fees
                        WHERE loan_id = :loan_id
                    """),
                    {"loan_id": loan_id}
                ).fetchall()

                if fees:
                    zero_tolerance_violations = []
                    ten_pct_le_total = 0.0
                    ten_pct_cd_total = 0.0

                    for fee in fees:
                        le_amt = float(fee.le_amount or 0)
                        cd_amt = float(fee.cd_amount or 0)

                        if fee.tolerance_category == "zero" and cd_amt > le_amt:
                            zero_tolerance_violations.append(fee.fee_name)
                        elif fee.tolerance_category == "ten_percent":
                            ten_pct_le_total += le_amt
                            ten_pct_cd_total += cd_amt

                    ten_pct_over = ten_pct_cd_total > ten_pct_le_total * 1.10

                    if zero_tolerance_violations or ten_pct_over:
                        issues.append({
                            "type": "tolerance",
                            "severity": "high",
                            "description": f"Fee tolerance violations: {len(zero_tolerance_violations)} zero-tolerance, "
                                           f"10% category {'OVER' if ten_pct_over else 'OK'}"
                        })
                        compliance_checks.append({
                            "check": "Fee tolerance",
                            "status": "failed",
                            "zero_tolerance_violations": zero_tolerance_violations,
                            "ten_pct_over": ten_pct_over
                        })
                    else:
                        compliance_checks.append({"check": "Fee tolerance", "status": "passed"})
                else:
                    compliance_checks.append({
                        "check": "Fee tolerance",
                        "status": "not_applicable",
                        "note": "No fee data on file yet"
                    })
            except Exception:
                compliance_checks.append({
                    "check": "Fee tolerance",
                    "status": "not_checked",
                    "note": "Fee data not available"
                })

            overall_status = "compliant"
            if any(i["severity"] == "critical" for i in issues):
                overall_status = "non_compliant"
            elif any(i["severity"] == "high" for i in issues):
                overall_status = "at_risk"
            elif issues:
                overall_status = "review_needed"

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "check_type": check_type,
                    "overall_status": overall_status,
                    "checks": compliance_checks,
                    "issues": issues,
                    "disclosures_on_file": list(disclosure_map.keys())
                },
                message=f"TRID check: {overall_status}. {len(issues)} issue(s) found."
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_loan_limits(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check loan against conforming limits"""

        loan_amount = input_data["loan_amount"]
        county = input_data["county"]
        state = input_data["state"].upper()
        units = input_data.get("units", 1)

        # 2026 Conforming loan limits (FHFA announcement Nov 2025)
        # In production, this would come from a database
        base_limits = {
            1: 832750,
            2: 1066050,
            3: 1288650,
            4: 1601550
        }

        # High-cost area limits (150% of base)
        high_cost_limits = {
            1: 1249125,
            2: 1599075,
            3: 1932975,
            4: 2402325
        }

        # High-cost areas (simplified - in production use FHFA data)
        high_cost_areas = {
            "CA": ["los angeles", "san francisco", "san diego", "orange", "santa clara", "alameda"],
            "NY": ["new york", "kings", "queens", "bronx", "nassau", "westchester"],
            "DC": ["district of columbia"],
            "HI": ["honolulu", "maui", "hawaii", "kauai"],
            "AK": ["anchorage", "fairbanks"]
        }

        is_high_cost = False
        if state in high_cost_areas:
            if county.lower() in high_cost_areas[state]:
                is_high_cost = True

        limit = high_cost_limits.get(units, 1249125) if is_high_cost else base_limits.get(units, 832750)

        if loan_amount <= limit:
            classification = "conforming"
            eligible_programs = ["Conventional", "FHA", "VA"]
        elif is_high_cost and loan_amount <= high_cost_limits.get(units, 1249125):
            classification = "high_balance_conforming"
            eligible_programs = ["Conventional High-Balance"]
        else:
            classification = "jumbo"
            eligible_programs = ["Jumbo", "Portfolio"]

        margin = limit - loan_amount
        margin_percent = (margin / limit) * 100

        return ToolResult(
            success=True,
            data={
                "loan_amount": loan_amount,
                "location": f"{county}, {state}",
                "units": units,
                "is_high_cost_area": is_high_cost,
                "conforming_limit": limit,
                "classification": classification,
                "margin_to_limit": margin,
                "margin_percent": round(margin_percent, 1),
                "eligible_programs": eligible_programs
            },
            message=f"Loan is {classification}. Limit: ${limit:,.0f}, Margin: ${margin:,.0f}"
        )

    async def _get_audit_checklist(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get compliance audit checklist"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_completed = input_data.get("include_completed", False)

        db = SessionLocal()
        try:
            # Get loan info
            loan = db.execute(
                text("SELECT * FROM loans WHERE id = :loan_id"),
                {"loan_id": loan_id}
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            loan_type = input_data.get("loan_type") or "conventional"
            if loan.program:
                if "fha" in loan.program.lower():
                    loan_type = "fha"
                elif "va" in loan.program.lower():
                    loan_type = "va"

            # Standard checklist items
            checklist = [
                # Application phase
                {"category": "application", "item": "URLA (1003) complete and signed", "required": True},
                {"category": "application", "item": "Borrower authorization signed", "required": True},
                {"category": "application", "item": "Credit report pulled", "required": True},

                # Disclosures
                {"category": "disclosures", "item": "Initial LE delivered within 3 days", "required": True},
                {"category": "disclosures", "item": "Intent to Proceed received", "required": True},
                {"category": "disclosures", "item": "Initial CD delivered 3+ days before closing", "required": True},
                {"category": "disclosures", "item": "Final CD provided at closing", "required": True},

                # Documentation
                {"category": "documentation", "item": "Income documentation", "required": True},
                {"category": "documentation", "item": "Asset documentation", "required": True},
                {"category": "documentation", "item": "Employment verification", "required": True},
                {"category": "documentation", "item": "Appraisal completed", "required": True},
                {"category": "documentation", "item": "Title commitment received", "required": True},
                {"category": "documentation", "item": "Homeowners insurance", "required": True},

                # Compliance
                {"category": "compliance", "item": "HMDA data collected", "required": True},
                {"category": "compliance", "item": "Fair lending analysis", "required": True},
                {"category": "compliance", "item": "Anti-money laundering check", "required": True},
                {"category": "compliance", "item": "OFAC verification", "required": True}
            ]

            # Add loan-type specific items
            if loan_type == "fha":
                checklist.extend([
                    {"category": "fha_specific", "item": "FHA case number assigned", "required": True},
                    {"category": "fha_specific", "item": "CAIVRS check completed", "required": True},
                    {"category": "fha_specific", "item": "FHA appraisal requirements met", "required": True},
                    {"category": "fha_specific", "item": "MIP disclosure provided", "required": True}
                ])
            elif loan_type == "va":
                checklist.extend([
                    {"category": "va_specific", "item": "COE obtained", "required": True},
                    {"category": "va_specific", "item": "VA appraisal (NOV) received", "required": True},
                    {"category": "va_specific", "item": "VA funding fee calculated", "required": True},
                    {"category": "va_specific", "item": "Pest inspection (if required)", "required": False}
                ])

            # Check completion status from database
            completed_items = db.execute(
                text("""
                    SELECT checklist_item, completed_at, completed_by
                    FROM compliance_checklist
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id}
            ).fetchall()

            completed_map = {c.checklist_item: c for c in completed_items}

            # Update checklist with completion status
            for item in checklist:
                completed = completed_map.get(item["item"])
                item["completed"] = completed is not None
                if completed:
                    item["completed_at"] = completed.completed_at.isoformat() if completed.completed_at else None
                    item["completed_by"] = completed.completed_by

            # Filter if not including completed
            if not include_completed:
                checklist = [i for i in checklist if not i.get("completed")]

            # Summary
            total = len(checklist) + len([c for c in completed_map.values()])
            completed_count = len(completed_map)
            pending = total - completed_count

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_type": loan_type,
                    "checklist": checklist,
                    "summary": {
                        "total_items": total,
                        "completed": completed_count,
                        "pending": pending,
                        "completion_rate": round((completed_count / total * 100), 1) if total > 0 else 0
                    }
                },
                message=f"Audit checklist: {completed_count}/{total} complete ({pending} pending)"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _log_disclosure(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Log disclosure delivery"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            query = text("""
                INSERT INTO disclosures (
                    loan_id, disclosure_type, delivery_method,
                    delivery_date, recipient_email,
                    created_by, created_at
                ) VALUES (
                    :loan_id, :disclosure_type, :delivery_method,
                    :delivery_date, :recipient_email,
                    :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, disclosure_type, delivery_date
            """)

            result = db.execute(query, {
                "loan_id": input_data["loan_id"],
                "disclosure_type": input_data["disclosure_type"],
                "delivery_method": input_data["delivery_method"],
                "delivery_date": input_data["delivery_date"],
                "recipient_email": input_data.get("recipient_email"),
                "created_by": context.get("user_id", 1)
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "disclosure_id": result.id,
                    "type": result.disclosure_type,
                    "delivery_date": result.delivery_date.isoformat() if result.delivery_date else None,
                    "loan_id": input_data["loan_id"]
                },
                message=f"Logged {result.disclosure_type} delivery on {result.delivery_date}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_timeline_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check regulatory timeline compliance"""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()

        try:
            # Get loan details
            loan = db.execute(
                text("""
                    SELECT *,
                        EXTRACT(DAY FROM closing_date - application_date) as days_to_close
                    FROM loans WHERE id = :loan_id
                """),
                {"loan_id": loan_id}
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get disclosures
            disclosures = db.execute(
                text("""
                    SELECT disclosure_type, delivery_date
                    FROM disclosures
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id}
            ).fetchall()

            disclosure_dates = {d.disclosure_type: d.delivery_date for d in disclosures}

            timeline_checks = []
            issues = []

            app_date = loan.application_date or loan.created_at
            if isinstance(app_date, datetime):
                app_date = app_date.date()

            # Check Initial LE timing (3 BUSINESS days from application)
            le_date = disclosure_dates.get("initial_le")
            if le_date and app_date:
                biz_days_to_le = self._business_days_between(app_date, le_date)
                le_deadline = self._add_business_days(app_date, 3)
                le_compliant = biz_days_to_le <= 3

                timeline_checks.append({
                    "requirement": "Initial LE within 3 business days",
                    "deadline": le_deadline.isoformat() if le_deadline else None,
                    "actual": le_date.isoformat() if le_date else None,
                    "compliant": le_compliant,
                    "business_days_used": biz_days_to_le
                })

                if not le_compliant:
                    issues.append({
                        "type": "le_timing",
                        "description": f"Initial LE delivered {days_to_le} days after application (max 3)"
                    })

            # Check CD timing (3 BUSINESS days before closing)
            cd_date = disclosure_dates.get("initial_cd")
            closing_date = loan.closing_date

            if closing_date and cd_date:
                biz_days_before = self._business_days_between(cd_date, closing_date)
                cd_deadline = self._add_business_days(closing_date, -3)
                cd_compliant = biz_days_before >= 3

                timeline_checks.append({
                    "requirement": "Initial CD 3+ business days before closing",
                    "deadline": cd_deadline.isoformat() if cd_deadline else None,
                    "actual": cd_date.isoformat() if cd_date else None,
                    "compliant": cd_compliant,
                    "business_days_before_closing": biz_days_before
                })

                if not cd_compliant:
                    issues.append({
                        "type": "cd_timing",
                        "description": f"Initial CD only {days_before_closing} days before closing (min 3)"
                    })

            # Check Intent to Proceed
            itp_date = disclosure_dates.get("intent_to_proceed")
            if le_date and not itp_date:
                issues.append({
                    "type": "missing_itp",
                    "description": "Intent to Proceed not received after LE"
                })

            timeline_checks.append({
                "requirement": "Intent to Proceed after LE",
                "compliant": itp_date is not None,
                "actual": itp_date.isoformat() if itp_date else None
            })

            # 7-day early disclosure waiting period check
            # (Cannot close within 7 days of certain disclosures)

            overall_compliant = all(c.get("compliant", True) for c in timeline_checks)

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "overall_compliant": overall_compliant,
                    "timeline_checks": timeline_checks,
                    "issues": issues,
                    "key_dates": {
                        "application_date": app_date.isoformat() if app_date else None,
                        "closing_date": closing_date.isoformat() if closing_date else None,
                        "days_to_close": int(loan.days_to_close) if loan.days_to_close else None
                    }
                },
                message=f"Timeline {'compliant' if overall_compliant else 'NON-COMPLIANT'}. {len(issues)} issue(s)."
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_state_requirements(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get state-specific requirements"""

        state = input_data["state"].upper()
        loan_type = input_data.get("loan_type")

        # Comprehensive state requirements database (all 50 states + DC)
        state_requirements = {
            "AL": {"name": "Alabama", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": ["No state-specific restrictions beyond federal"], "waiting_periods": {"rescission": "3 business days for refis"}, "special_requirements": ["Title insurance customary"]},
            "AK": {"name": "Alaska", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": ["No state-specific restrictions"], "waiting_periods": {"rescission": "3 business days"}, "special_requirements": ["FHFA high-cost area limits apply statewide"]},
            "AZ": {"name": "Arizona", "licensing": "NMLS License required", "disclosures": ["Standard federal", "AZ Deed of Trust Disclosure"], "restrictions": ["Anti-deficiency protections on purchase money loans"], "waiting_periods": {}, "special_requirements": ["Deed of trust state (non-judicial foreclosure)"]},
            "AR": {"name": "Arkansas", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": ["Usury limits (17% constitutional cap)"], "waiting_periods": {}, "special_requirements": ["Mortgage tax applies"]},
            "CA": {"name": "California", "licensing": "DFPI (DBO) License required", "disclosures": ["California Mortgage Disclosure Statement (MLDS)", "Fair Lending Notice", "Broker Fee Agreement"], "restrictions": ["Prepayment penalty restrictions", "Balloon payment restrictions", "Higher-priced mortgage loan protections"], "waiting_periods": {"rescission": "3 business days for refis"}, "special_requirements": ["Licensed per DFPI Financial Code", "Unique endorsement per MLO", "Covered loan protections (CFL)"]},
            "CO": {"name": "Colorado", "licensing": "NMLS License required", "disclosures": ["CO Mortgage Broker Disclosure", "Standard federal"], "restrictions": ["Foreclosure mediation program"], "waiting_periods": {}, "special_requirements": ["Public trustee foreclosure process"]},
            "CT": {"name": "Connecticut", "licensing": "NMLS License required", "disclosures": ["CT Fair Lending Notice"], "restrictions": ["CT high-cost loan thresholds"], "waiting_periods": {}, "special_requirements": ["Attorney state — attorney must be present at closing"]},
            "DE": {"name": "Delaware", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Attorney state"]},
            "DC": {"name": "District of Columbia", "licensing": "NMLS License required", "disclosures": ["DC Mortgage Disclosure"], "restrictions": ["High-cost area limits"], "waiting_periods": {}, "special_requirements": ["Recordation tax", "FHFA high-cost limits apply"]},
            "FL": {"name": "Florida", "licensing": "OFR License required", "disclosures": ["Standard federal"], "restrictions": ["Documentary stamp tax", "Intangible tax on new mortgages"], "waiting_periods": {}, "special_requirements": ["Title insurance required", "Survey may be required", "Homestead exemption considerations"]},
            "GA": {"name": "Georgia", "licensing": "NMLS License required", "disclosures": ["GA Fair Lending Notice"], "restrictions": ["GA Fair Lending Act (high-cost thresholds)"], "waiting_periods": {}, "special_requirements": ["Security deed state", "Intangible recording tax"]},
            "HI": {"name": "Hawaii", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["FHFA high-cost area limits", "Leasehold properties common"]},
            "ID": {"name": "Idaho", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Deed of trust state"]},
            "IL": {"name": "Illinois", "licensing": "IDFPR License required", "disclosures": ["IL Mortgage Disclosures", "Standard federal"], "restrictions": ["IL high-risk home loan restrictions"], "waiting_periods": {}, "special_requirements": ["Transfer tax applies", "Survey requirement in some counties"]},
            "IN": {"name": "Indiana", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Mortgage tax applies"]},
            "IA": {"name": "Iowa", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Abstract of title common"]},
            "KS": {"name": "Kansas", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Mortgage registration tax"]},
            "KY": {"name": "Kentucky", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Mortgage recording tax"]},
            "LA": {"name": "Louisiana", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Notarial act required", "Community property state"]},
            "ME": {"name": "Maine", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Attorney state"]},
            "MD": {"name": "Maryland", "licensing": "NMLS License required", "disclosures": ["MD Mortgage Disclosure", "Standard federal"], "restrictions": ["MD Mortgage Assistance Relief Services"], "waiting_periods": {}, "special_requirements": ["Transfer and recordation tax", "Ground rent properties in Baltimore"]},
            "MA": {"name": "Massachusetts", "licensing": "NMLS License required", "disclosures": ["MA Predatory Lending Disclosure"], "restrictions": ["MA predatory lending law (ch. 183C)"], "waiting_periods": {}, "special_requirements": ["Attorney state", "Mortgage excise tax"]},
            "MI": {"name": "Michigan", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Transfer tax applies"]},
            "MN": {"name": "Minnesota", "licensing": "NMLS License required", "disclosures": ["MN Mortgage Disclosure"], "restrictions": ["MN predatory lending restrictions"], "waiting_periods": {}, "special_requirements": ["Mortgage registration tax", "Torrens/registered land system"]},
            "MS": {"name": "Mississippi", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Deed of trust state"]},
            "MO": {"name": "Missouri", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Deed of trust state"]},
            "MT": {"name": "Montana", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": []},
            "NE": {"name": "Nebraska", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Documentary stamp tax"]},
            "NV": {"name": "Nevada", "licensing": "NMLS License required", "disclosures": ["NV Mortgage Disclosure"], "restrictions": ["NV Homeowner Bill of Rights"], "waiting_periods": {}, "special_requirements": ["Community property state", "Deed of trust state"]},
            "NH": {"name": "New Hampshire", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": []},
            "NJ": {"name": "New Jersey", "licensing": "NMLS License required", "disclosures": ["NJ Mortgage Disclosure"], "restrictions": ["NJ Home Ownership Security Act"], "waiting_periods": {}, "special_requirements": ["Attorney state", "Realty transfer fee"]},
            "NM": {"name": "New Mexico", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Community property state"]},
            "NY": {"name": "New York", "licensing": "DFS License required", "disclosures": ["NY Mortgage Disclosure Form", "Subprime Home Loan Notice"], "restrictions": ["Interest rate caps on certain loans", "NY high-cost mortgage regulations", "Banking Dept regulation of non-bank lenders"], "waiting_periods": {"rescission": "3 business days"}, "special_requirements": ["CEMA transactions common", "Mortgage recording tax", "Attorney state for closing", "Mansion tax on loans > $1M"]},
            "NC": {"name": "North Carolina", "licensing": "NMLS License required", "disclosures": ["NC Predatory Lending Disclosure"], "restrictions": ["NC Anti-Predatory Lending Act"], "waiting_periods": {}, "special_requirements": ["Deed of trust state", "Revenue stamps"]},
            "ND": {"name": "North Dakota", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": []},
            "OH": {"name": "Ohio", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Transfer tax applies"]},
            "OK": {"name": "Oklahoma", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Documentary stamp tax"]},
            "OR": {"name": "Oregon", "licensing": "NMLS License required", "disclosures": ["OR Mortgage Lending Disclosure"], "restrictions": ["OR predatory lending restrictions"], "waiting_periods": {}, "special_requirements": ["Trust deed state"]},
            "PA": {"name": "Pennsylvania", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Transfer tax", "Realty transfer tax"]},
            "RI": {"name": "Rhode Island", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Attorney state"]},
            "SC": {"name": "South Carolina", "licensing": "NMLS License required", "disclosures": ["SC Mortgage Disclosure"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Attorney state", "Recording fees"]},
            "SD": {"name": "South Dakota", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": []},
            "TN": {"name": "Tennessee", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Deed of trust state", "Transfer tax"]},
            "TX": {"name": "Texas", "licensing": "NMLS License required", "disclosures": ["Texas Consumer Notice", "Home Equity Acknowledgment (if applicable)", "Texas Section 50(a)(6) requirements"], "restrictions": ["Home equity loans limited to 80% LTV", "No prepayment penalties on home equity", "12-day cooling off for home equity", "Cash-out refi seasoning requirements"], "waiting_periods": {"home_equity": "12 days from application to closing"}, "special_requirements": ["Home equity specific closing requirements (must close at title office)", "Attorney review may be required", "Unique constitutional protections (Art. XVI §50)"]},
            "UT": {"name": "Utah", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Trust deed state"]},
            "VT": {"name": "Vermont", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Attorney state"]},
            "VA": {"name": "Virginia", "licensing": "NMLS License required", "disclosures": ["VA Mortgage Disclosure"], "restrictions": ["VA high-cost mortgage protections"], "waiting_periods": {}, "special_requirements": ["Deed of trust state", "Grantor tax and recordation tax"]},
            "WA": {"name": "Washington", "licensing": "NMLS License required", "disclosures": ["WA Mortgage Broker Disclosure"], "restrictions": ["WA Mortgage Lending Fraud Prosecution Act"], "waiting_periods": {}, "special_requirements": ["Community property state", "Deed of trust state", "Excise tax"]},
            "WV": {"name": "West Virginia", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Deed of trust state"]},
            "WI": {"name": "Wisconsin", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": ["Community property state", "Transfer fee"]},
            "WY": {"name": "Wyoming", "licensing": "NMLS License required", "disclosures": ["Standard federal"], "restrictions": [], "waiting_periods": {}, "special_requirements": []},
        }

        # Default for territories or unrecognized codes
        default_requirements = {
            "name": state,
            "licensing": "NMLS License required",
            "disclosures": ["Standard federal disclosures apply"],
            "restrictions": ["Follow federal regulations"],
            "waiting_periods": {"rescission": "3 business days for refinances"},
            "special_requirements": ["Verify specific jurisdiction requirements with compliance department"]
        }

        requirements = state_requirements.get(state, default_requirements)

        # Add loan-type specific info
        if loan_type:
            if loan_type.lower() == "fha":
                requirements["loan_type_notes"] = [
                    "FHA anti-flipping rules apply",
                    "State may have additional FHA requirements"
                ]
            elif loan_type.lower() == "va":
                requirements["loan_type_notes"] = [
                    "VA funding fee may have state tax implications",
                    "State veteran benefits may apply"
                ]

        return ToolResult(
            success=True,
            data={
                "state": state,
                "requirements": requirements
            },
            message=f"State requirements for {requirements['name']}"
        )

    async def _flag_compliance_issue(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Flag a compliance issue"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            query = text("""
                INSERT INTO compliance_issues (
                    loan_id, issue_type, severity, description,
                    remediation_required, status,
                    created_by, created_at
                ) VALUES (
                    :loan_id, :issue_type, :severity, :description,
                    :remediation_required, 'open',
                    :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, issue_type, severity
            """)

            result = db.execute(query, {
                "loan_id": input_data["loan_id"],
                "issue_type": input_data["issue_type"],
                "severity": input_data["severity"],
                "description": input_data["description"],
                "remediation_required": input_data.get("remediation_required", True),
                "created_by": context.get("user_id", 1)
            }).fetchone()

            # If critical, create a task
            if input_data["severity"] == "critical":
                db.execute(
                    text("""
                        INSERT INTO tasks (
                            title, description, entity_type, entity_id,
                            priority, task_type, status, due_date,
                            created_by, created_at
                        ) VALUES (
                            :title, :description, 'loan', :loan_id,
                            'urgent', 'compliance', 'pending', CURRENT_DATE,
                            :created_by, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "title": f"CRITICAL: {input_data['issue_type']} compliance issue",
                        "description": input_data["description"],
                        "loan_id": input_data["loan_id"],
                        "created_by": context.get("user_id", 1)
                    }
                )

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "issue_id": result.id,
                    "type": result.issue_type,
                    "severity": result.severity,
                    "loan_id": input_data["loan_id"],
                    "task_created": input_data["severity"] == "critical"
                },
                message=f"{result.severity.upper()} compliance issue flagged: {result.issue_type}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_compliance_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate compliance report"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            start_date = input_data.get("start_date", (date.today() - timedelta(days=30)).isoformat())
            end_date = input_data.get("end_date", date.today().isoformat())

            params = {"start_date": start_date, "end_date": end_date}

            lo_filter = ""
            if input_data.get("lo_id"):
                lo_filter = "AND l.assigned_lo = :lo_id"
                params["lo_id"] = input_data["lo_id"]

            # Issues summary
            issues_query = text(f"""
                SELECT
                    ci.issue_type,
                    ci.severity,
                    COUNT(*) as count
                FROM compliance_issues ci
                JOIN loans l ON ci.loan_id = l.id
                WHERE ci.created_at BETWEEN :start_date AND :end_date
                    {lo_filter}
                GROUP BY ci.issue_type, ci.severity
                ORDER BY ci.severity, count DESC
            """)

            issues = db.execute(issues_query, params).fetchall()

            issues_by_type = {}
            issues_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

            for i in issues:
                if i.issue_type not in issues_by_type:
                    issues_by_type[i.issue_type] = 0
                issues_by_type[i.issue_type] += i.count
                issues_by_severity[i.severity] += i.count

            # Disclosure timing analysis
            timing_query = text(f"""
                SELECT
                    d.disclosure_type,
                    COUNT(*) as total,
                    COUNT(CASE WHEN
                        (d.disclosure_type = 'initial_le' AND
                         d.delivery_date <= l.application_date + 3) OR
                        (d.disclosure_type = 'initial_cd' AND
                         d.delivery_date <= l.closing_date - 3)
                    THEN 1 END) as on_time
                FROM disclosures d
                JOIN loans l ON d.loan_id = l.id
                WHERE d.created_at BETWEEN :start_date AND :end_date
                    {lo_filter}
                GROUP BY d.disclosure_type
            """)

            timing = db.execute(timing_query, params).fetchall()

            timing_compliance = [
                {
                    "disclosure": t.disclosure_type,
                    "total": t.total,
                    "on_time": t.on_time or 0,
                    "compliance_rate": round((t.on_time or 0) / t.total * 100, 1) if t.total > 0 else 0
                }
                for t in timing
            ]

            # Overall stats
            total_loans_query = text(f"""
                SELECT COUNT(*) as count
                FROM loans l
                WHERE l.created_at BETWEEN :start_date AND :end_date
                    {lo_filter}
            """)

            total_loans = db.execute(total_loans_query, params).fetchone().count

            total_issues = sum(issues_by_severity.values())

            return ToolResult(
                success=True,
                data={
                    "period": {"start": start_date, "end": end_date},
                    "summary": {
                        "total_loans": total_loans,
                        "total_issues": total_issues,
                        "issues_per_loan": round(total_issues / total_loans, 2) if total_loans > 0 else 0,
                        "critical_issues": issues_by_severity["critical"],
                        "high_issues": issues_by_severity["high"]
                    },
                    "issues_by_type": issues_by_type,
                    "issues_by_severity": issues_by_severity,
                    "timing_compliance": timing_compliance,
                    "risk_score": min(100, issues_by_severity["critical"] * 20 + issues_by_severity["high"] * 10)
                },
                message=f"Compliance report: {total_issues} issues across {total_loans} loans"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
