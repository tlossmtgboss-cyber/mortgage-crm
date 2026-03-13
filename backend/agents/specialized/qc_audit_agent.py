"""
QC Audit Agent

Specialized agent for quality control auditing with 15 tools:
1. run_prefunding_audit - Pre-funding QC check on all loan documents
2. run_postclosing_audit - Post-closing QC review per investor requirements
3. check_data_integrity - Verify data consistency across all documents
4. verify_regulatory_compliance - Check all regulatory requirements met
5. identify_repurchase_risks - Find defects that could lead to repurchase demands
6. generate_qc_scorecard - Score loan file quality 0-100 with defect breakdown
7. compare_to_investor_overlay - Check docs against investor overlay requirements
8. check_signature_completeness - Verify all required signatures are present
9. verify_disclosures_timing - Verify disclosure send/receive timeframes
10. check_appraisal_independence - Verify appraiser independence requirements
11. generate_deficiency_report - Comprehensive deficiency report with cure recommendations
12. track_defect_trends - Analyze QC defect trends across loans/LOs/processors
13. calculate_defect_rate - Organization-level defect rate for management reporting
14. recommend_process_improvements - Suggest process changes based on defect patterns
15. generate_audit_trail_report - Complete audit trail for examiner review
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
# CONSTANTS
# ============================================================================

# Defect severity classification
DEFECT_SEVERITY = {
    "critical": {
        "description": "Defect would cause loan rejection or repurchase demand",
        "weight": 25,
        "examples": [
            "Missing borrower signature on Note",
            "TRID timing violation",
            "Undisclosed liabilities",
            "Appraisal independence violation",
            "Misrepresentation of occupancy",
        ],
    },
    "major": {
        "description": "Defect requires cure before investor delivery",
        "weight": 10,
        "examples": [
            "Tolerance violation without cure",
            "Stale credit report",
            "Incomplete conditions clearance",
            "Missing hazard insurance binder",
        ],
    },
    "minor": {
        "description": "Documentation gap that should be corrected",
        "weight": 3,
        "examples": [
            "Missing initials on one disclosure page",
            "Name variance without explanation letter",
            "Outdated bank statement (within 30-day grace)",
        ],
    },
    "observation": {
        "description": "Best practice deviation, not a compliance failure",
        "weight": 1,
        "examples": [
            "File organization not per company standard",
            "Communication log incomplete",
            "Processor notes missing timestamps",
        ],
    },
}

# Investor overlay reference data
INVESTOR_OVERLAYS = {
    "fannie_mae": {
        "name": "Fannie Mae / DU",
        "max_dti": 50,
        "min_credit": 620,
        "max_ltv_conventional": 97,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
        ],
        "specific_rules": [
            "DU Approve/Eligible required",
            "Age of documents: 4 months from note date",
            "Appraisal within 12 months (new within 4 months preferred)",
        ],
    },
    "freddie_mac": {
        "name": "Freddie Mac / LP",
        "max_dti": 50,
        "min_credit": 620,
        "max_ltv_conventional": 97,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
        ],
        "specific_rules": [
            "LP Accept required",
            "Age of documents: 4 months from note date",
            "Appraisal within 12 months",
        ],
    },
    "ginnie_mae": {
        "name": "Ginnie Mae (FHA/VA)",
        "max_dti": 57,
        "min_credit": 580,
        "max_ltv_fha": 96.5,
        "required_docs": [
            "uniform_residential_loan_application",
            "credit_report",
            "appraisal",
            "title_commitment",
            "hazard_insurance",
            "flood_certification",
            "income_verification",
            "asset_verification",
            "fha_case_number_assignment",
            "mortgage_insurance_certificate",
        ],
        "specific_rules": [
            "FHA case number required before appraisal",
            "CAIVRS check required",
            "Manual underwriting rules apply below 620 FICO",
        ],
    },
}

# QC scorecard weights by category
QC_CATEGORY_WEIGHTS = {
    "disclosure_compliance": 25,
    "data_integrity": 20,
    "document_completeness": 20,
    "regulatory_compliance": 15,
    "signature_completeness": 10,
    "appraisal_review": 10,
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class RunPrefundingAuditInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for pre-funding QC audit")
    audit_scope: str = Field(
        default="full",
        description="Audit scope: full, targeted, disclosure_only"
    )


class RunPostclosingAuditInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for post-closing review")
    investor: str = Field(
        default="fannie_mae",
        description="Investor: fannie_mae, freddie_mac, ginnie_mae"
    )


class CheckDataIntegrityInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for data consistency check")


class VerifyRegulatoryComplianceInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to verify regulatory compliance")
    regulations: Optional[List[str]] = Field(
        None,
        description="Specific regulations to check: trid, respa, ecoa, hmda, state"
    )


class IdentifyRepurchaseRisksInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for repurchase risk assessment")


class GenerateQCScorecardInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for QC scorecard")


class CompareToInvestorOverlayInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")
    investor: str = Field(
        default="fannie_mae",
        description="Investor: fannie_mae, freddie_mac, ginnie_mae"
    )


class CheckSignatureCompletenessInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")


class VerifyDisclosuresTimingInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")


class CheckAppraisalIndependenceInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")


class GenerateDeficiencyReportInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID")
    include_cure_plan: bool = Field(
        default=True, description="Include cure recommendations"
    )


class TrackDefectTrendsInput(BaseModel):
    period_days: int = Field(default=90, description="Analysis period in days")
    group_by: str = Field(
        default="defect_type",
        description="Group by: defect_type, lo, processor, branch"
    )
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")


class CalculateDefectRateInput(BaseModel):
    period_days: int = Field(default=90, description="Analysis period in days")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")


class RecommendProcessImprovementsInput(BaseModel):
    period_days: int = Field(default=90, description="Analysis period in days")


class GenerateAuditTrailReportInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for audit trail")


# ============================================================================
# QC AUDIT AGENT
# ============================================================================

@AgentRegistry.register
class QCAuditAgent(SpecializedAgent):
    """
    Specialized agent for quality control auditing of mortgage loan files.

    Performs pre-funding and post-closing QC reviews, data integrity checks,
    regulatory compliance verification, and defect trend analysis. All queries
    are tenant-isolated via organization_id.
    """

    @property
    def name(self) -> str:
        return "QCAuditAgent"

    @property
    def description(self) -> str:
        return (
            "Quality control audit agent for pre-funding and post-closing "
            "document review, defect detection, repurchase risk assessment, "
            "and investor overlay compliance"
        )

    def _register_tools(self):
        """Register all 15 QC audit tools"""

        self.register_tool(AgentTool(
            name="run_prefunding_audit",
            description="Run a pre-funding QC audit on a loan file. Checks disclosure timing, "
                       "document completeness, data integrity, and regulatory compliance before funding.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._run_prefunding_audit,
            input_schema=RunPrefundingAuditInput
        ))

        self.register_tool(AgentTool(
            name="run_postclosing_audit",
            description="Run a post-closing QC review per investor requirements. Verifies loan meets "
                       "delivery requirements for Fannie Mae, Freddie Mac, or Ginnie Mae.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._run_postclosing_audit,
            input_schema=RunPostclosingAuditInput
        ))

        self.register_tool(AgentTool(
            name="check_data_integrity",
            description="Verify data consistency across all loan documents. Checks that borrower names, "
                       "dates, loan amounts, and property addresses match across all documents.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_data_integrity,
            input_schema=CheckDataIntegrityInput
        ))

        self.register_tool(AgentTool(
            name="verify_regulatory_compliance",
            description="Comprehensive regulatory compliance verification including TRID, RESPA, "
                       "ECOA, HMDA, and state-specific requirements.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._verify_regulatory_compliance,
            input_schema=VerifyRegulatoryComplianceInput
        ))

        self.register_tool(AgentTool(
            name="identify_repurchase_risks",
            description="Identify defects that could trigger investor repurchase demands. "
                       "Assesses risk level and estimated financial exposure.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_repurchase_risks,
            input_schema=IdentifyRepurchaseRisksInput
        ))

        self.register_tool(AgentTool(
            name="generate_qc_scorecard",
            description="Generate a 0-100 quality scorecard for a loan file with weighted "
                       "category scores and detailed defect breakdown.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_qc_scorecard,
            input_schema=GenerateQCScorecardInput
        ))

        self.register_tool(AgentTool(
            name="compare_to_investor_overlay",
            description="Compare loan documentation against specific investor overlay requirements "
                       "for Fannie Mae, Freddie Mac, or Ginnie Mae.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_to_investor_overlay,
            input_schema=CompareToInvestorOverlayInput
        ))

        self.register_tool(AgentTool(
            name="check_signature_completeness",
            description="Verify all required signatures are present on all loan documents "
                       "including Note, Deed of Trust, disclosures, and closing documents.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_signature_completeness,
            input_schema=CheckSignatureCompletenessInput
        ))

        self.register_tool(AgentTool(
            name="verify_disclosures_timing",
            description="Verify all disclosures were sent and received within required "
                       "regulatory timeframes (TRID LE/CD timing).",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._verify_disclosures_timing,
            input_schema=VerifyDisclosuresTimingInput
        ))

        self.register_tool(AgentTool(
            name="check_appraisal_independence",
            description="Verify appraiser independence requirements are met including "
                       "no prohibited relationships and proper engagement procedures.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_appraisal_independence,
            input_schema=CheckAppraisalIndependenceInput
        ))

        self.register_tool(AgentTool(
            name="generate_deficiency_report",
            description="Generate a comprehensive deficiency report listing all defects "
                       "found with severity classification and cure recommendations.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_deficiency_report,
            input_schema=GenerateDeficiencyReportInput
        ))

        self.register_tool(AgentTool(
            name="track_defect_trends",
            description="Analyze QC defect trends across loans, loan officers, and processors "
                       "to identify systemic issues.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._track_defect_trends,
            input_schema=TrackDefectTrendsInput
        ))

        self.register_tool(AgentTool(
            name="calculate_defect_rate",
            description="Calculate organization-level defect rate for management reporting. "
                       "Shows percentage of loans with critical/major defects.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_defect_rate,
            input_schema=CalculateDefectRateInput
        ))

        self.register_tool(AgentTool(
            name="recommend_process_improvements",
            description="Based on defect patterns, suggest process changes to reduce "
                       "defect rates and improve loan quality.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_process_improvements,
            input_schema=RecommendProcessImprovementsInput
        ))

        self.register_tool(AgentTool(
            name="generate_audit_trail_report",
            description="Generate a complete audit trail for a loan file suitable "
                       "for regulatory examiner review.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._generate_audit_trail_report,
            input_schema=GenerateAuditTrailReportInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _run_prefunding_audit(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Pre-funding QC audit on a loan file."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        audit_scope = input_data.get("audit_scope", "full")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)
            params = {"loan_id": loan_id, "org_id": org_id}

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.rate,
                       l.loan_type, l.stage, l.property_address,
                       l.application_date, l.initial_disclosures_sent_date,
                       l.initial_disclosures_signed_date,
                       l.cd_sent_to_borrower_date, l.cd_acknowledged_date,
                       l.funded_date, l.closing_date,
                       l.appraisal_ordered_date, l.appraisal_received_date,
                       l.appraisal_value, l.credit_docs_expire_date,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                       u.nmls_number as lo_nmls
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), params).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            defects = []
            warnings = []
            passed = []

            # --- Disclosure timing checks ---
            if audit_scope in ("full", "disclosure_only"):
                if loan.application_date and loan.initial_disclosures_sent_date:
                    le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                    if le_days > 3:
                        defects.append({
                            "category": "disclosure_compliance",
                            "severity": "critical",
                            "finding": f"LE sent {le_days} days after application (max 3 business days)",
                            "regulation": "TRID 12 CFR 1026.19(e)(1)(iii)",
                        })
                    else:
                        passed.append("LE timing compliant")
                elif loan.application_date and not loan.initial_disclosures_sent_date:
                    defects.append({
                        "category": "disclosure_compliance",
                        "severity": "critical",
                        "finding": "Initial LE has not been sent",
                        "regulation": "TRID 12 CFR 1026.19(e)(1)(iii)",
                    })

                if loan.cd_sent_to_borrower_date and loan.closing_date:
                    cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                    if cd_days < 3:
                        defects.append({
                            "category": "disclosure_compliance",
                            "severity": "critical",
                            "finding": f"CD sent only {cd_days} days before closing (min 3 business days)",
                            "regulation": "TRID 12 CFR 1026.19(f)(1)(ii)",
                        })
                    else:
                        passed.append("CD timing compliant")

            # --- Document completeness ---
            if audit_scope == "full":
                docs = db.execute(text("""
                    SELECT doc_type, doc_category, status
                    FROM documents
                    WHERE loan_id = :loan_id
                """), {"loan_id": loan_id}).fetchall()

                existing_types = {d.doc_type for d in docs if d.status == "active"}
                required_prefund = [
                    "paystubs", "w2", "bank_statements", "credit_report",
                    "appraisal", "title", "insurance"
                ]
                for req_doc in required_prefund:
                    if req_doc not in existing_types:
                        defects.append({
                            "category": "document_completeness",
                            "severity": "major",
                            "finding": f"Missing required document: {req_doc}",
                            "regulation": "Investor delivery requirement",
                        })
                    else:
                        passed.append(f"Document on file: {req_doc}")

                # Credit docs expiration
                if loan.credit_docs_expire_date:
                    today = date.today()
                    expire_dt = loan.credit_docs_expire_date
                    if hasattr(expire_dt, 'date'):
                        expire_dt = expire_dt.date()
                    if expire_dt < today:
                        defects.append({
                            "category": "document_completeness",
                            "severity": "major",
                            "finding": f"Credit documents expired on {expire_dt.isoformat()}",
                            "regulation": "Investor age-of-document requirement",
                        })

            # --- LO NMLS verification ---
            if loan.lo_nmls:
                passed.append(f"LO NMLS #{loan.lo_nmls} on file")
            else:
                defects.append({
                    "category": "regulatory_compliance",
                    "severity": "major",
                    "finding": "Loan officer NMLS ID not on file",
                    "regulation": "SAFE Act",
                })

            # --- Appraisal presence ---
            if loan.appraisal_received_date:
                passed.append("Appraisal received")
                if loan.appraisal_value and loan.amount:
                    ltv = (float(loan.amount) / float(loan.appraisal_value)) * 100
                    if ltv > 97:
                        warnings.append({
                            "category": "appraisal_review",
                            "severity": "minor",
                            "finding": f"LTV is {ltv:.1f}% - verify program eligibility",
                        })
            elif loan.stage not in ("APPLICATION", "DISCLOSED", "PROCESSING"):
                defects.append({
                    "category": "appraisal_review",
                    "severity": "major",
                    "finding": "Appraisal not received for loan past processing stage",
                    "regulation": "USPAP / Dodd-Frank appraisal requirements",
                })

            # --- Compliance alerts check ---
            open_alerts = db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
            """), {"loan_id": loan_id}).fetchone()

            if open_alerts and open_alerts.cnt > 0:
                warnings.append({
                    "category": "regulatory_compliance",
                    "severity": "minor",
                    "finding": f"{open_alerts.cnt} open compliance alert(s) on file",
                })

            # Score
            critical_count = len([d for d in defects if d["severity"] == "critical"])
            major_count = len([d for d in defects if d["severity"] == "major"])
            pass_fail = "FAIL" if critical_count > 0 else ("CONDITIONAL" if major_count > 0 else "PASS")

            self.audit_log("run_prefunding_audit", "loan", entity_id=loan_id, details={
                "result": pass_fail,
                "defects": len(defects),
                "warnings": len(warnings),
                "scope": audit_scope,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "audit_type": "pre-funding",
                    "audit_scope": audit_scope,
                    "result": pass_fail,
                    "defects": defects,
                    "warnings": warnings,
                    "passed_checks": passed,
                    "summary": {
                        "critical": critical_count,
                        "major": major_count,
                        "warnings": len(warnings),
                        "passed": len(passed),
                    },
                    "audited_at": datetime.utcnow().isoformat(),
                },
                message=f"Pre-funding audit: {pass_fail} - {critical_count} critical, {major_count} major defects"
            )

        except Exception as e:
            logger.exception(f"run_prefunding_audit failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _run_postclosing_audit(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Post-closing QC review per investor requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        investor = input_data.get("investor", "fannie_mae")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)
            params = {"loan_id": loan_id, "org_id": org_id}

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.rate,
                       l.loan_type, l.stage, l.funded_date, l.closing_date,
                       l.application_date, l.cd_sent_to_borrower_date,
                       l.initial_disclosures_sent_date,
                       l.appraisal_value, l.appraisal_received_date,
                       l.credit_docs_expire_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), params).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            overlay = INVESTOR_OVERLAYS.get(investor)
            if not overlay:
                return ToolResult(
                    success=False,
                    error=f"Unknown investor: {investor}. Use: fannie_mae, freddie_mac, ginnie_mae"
                )

            defects = []
            passed = []

            # Check loan was actually funded/closed
            if not loan.funded_date and loan.stage != "FUNDED":
                defects.append({
                    "category": "post_closing",
                    "severity": "critical",
                    "finding": "Loan has not been funded - post-closing audit requires funded loan",
                })

            # Document completeness against investor requirements
            docs = db.execute(text("""
                SELECT doc_type, status FROM documents WHERE loan_id = :loan_id
            """), {"loan_id": loan_id}).fetchall()
            existing_types = {d.doc_type for d in docs if d.status == "active"}

            for req_doc in overlay["required_docs"]:
                if req_doc not in existing_types:
                    defects.append({
                        "category": "document_completeness",
                        "severity": "major",
                        "finding": f"Missing {overlay['name']} required document: {req_doc}",
                    })
                else:
                    passed.append(f"{req_doc} on file")

            # Document age check (4 months from note date for most investors)
            if loan.closing_date and loan.credit_docs_expire_date:
                expire_dt = loan.credit_docs_expire_date
                if hasattr(expire_dt, 'date'):
                    expire_dt = expire_dt.date()
                closing_dt = loan.closing_date
                if hasattr(closing_dt, 'date'):
                    closing_dt = closing_dt.date()
                if expire_dt < closing_dt:
                    defects.append({
                        "category": "document_completeness",
                        "severity": "major",
                        "finding": "Credit documents expired before closing date",
                    })

            # Check for tolerance violations
            fee_violations = db.execute(text("""
                SELECT fee_name, le_amount, cd_amount, tolerance_category
                FROM loan_fees
                WHERE loan_id = :loan_id
                    AND tolerance_category = 'zero'
                    AND cd_amount > le_amount
            """), {"loan_id": loan_id}).fetchall()

            for violation in fee_violations:
                diff = float(violation.cd_amount or 0) - float(violation.le_amount or 0)
                if diff > 0:
                    defects.append({
                        "category": "disclosure_compliance",
                        "severity": "critical",
                        "finding": f"Zero-tolerance fee increase: {violation.fee_name} "
                                   f"(LE: ${float(violation.le_amount or 0):,.2f}, "
                                   f"CD: ${float(violation.cd_amount or 0):,.2f})",
                    })

            # Disclosure timing
            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days > 3:
                    defects.append({
                        "category": "disclosure_compliance",
                        "severity": "critical",
                        "finding": f"LE sent {le_days} days after application",
                    })
                else:
                    passed.append("LE timing compliant")

            if loan.cd_sent_to_borrower_date and loan.closing_date:
                cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                if cd_days < 3:
                    defects.append({
                        "category": "disclosure_compliance",
                        "severity": "critical",
                        "finding": f"CD delivered only {cd_days} day(s) before closing",
                    })
                else:
                    passed.append("CD timing compliant")

            critical_count = len([d for d in defects if d["severity"] == "critical"])
            major_count = len([d for d in defects if d["severity"] == "major"])
            result = "FAIL" if critical_count > 0 else ("CONDITIONAL" if major_count > 0 else "PASS")

            self.audit_log("run_postclosing_audit", "loan", entity_id=loan_id, details={
                "investor": investor,
                "result": result,
                "defects": len(defects),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "investor": overlay["name"],
                    "audit_type": "post-closing",
                    "result": result,
                    "defects": defects,
                    "passed_checks": passed,
                    "summary": {
                        "critical": critical_count,
                        "major": major_count,
                        "passed": len(passed),
                    },
                    "delivery_ready": result == "PASS",
                    "audited_at": datetime.utcnow().isoformat(),
                },
                message=f"Post-closing audit ({overlay['name']}): {result} - "
                        f"{critical_count} critical, {major_count} major"
            )

        except Exception as e:
            logger.exception(f"run_postclosing_audit failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_data_integrity(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify data consistency across all documents."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
                       l.amount, l.rate, l.property_address, l.loan_type,
                       l.application_date, l.closing_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            discrepancies = []
            verified = []

            # Check lead-to-loan data consistency
            lead_data = db.execute(text("""
                SELECT ld.first_name, ld.last_name, ld.email, ld.loan_amount
                FROM leads ld
                WHERE ld.loan_number = :loan_number
                LIMIT 1
            """), {"loan_number": loan.loan_number}).fetchone()

            if lead_data:
                lead_name = f"{lead_data.first_name or ''} {lead_data.last_name or ''}".strip()
                if lead_name and loan.borrower_name and lead_name.lower() != loan.borrower_name.lower():
                    discrepancies.append({
                        "field": "borrower_name",
                        "severity": "major",
                        "lead_value": lead_name,
                        "loan_value": loan.borrower_name,
                        "finding": "Borrower name mismatch between lead and loan records",
                    })
                else:
                    verified.append("Borrower name consistent between lead and loan")

                if lead_data.email and loan.borrower_email:
                    if lead_data.email.lower() != loan.borrower_email.lower():
                        discrepancies.append({
                            "field": "borrower_email",
                            "severity": "minor",
                            "lead_value": lead_data.email,
                            "loan_value": loan.borrower_email,
                            "finding": "Borrower email mismatch between lead and loan records",
                        })
                    else:
                        verified.append("Borrower email consistent")

                if lead_data.loan_amount and loan.amount:
                    if abs(float(lead_data.loan_amount) - float(loan.amount)) > 1.0:
                        discrepancies.append({
                            "field": "loan_amount",
                            "severity": "minor",
                            "lead_value": float(lead_data.loan_amount),
                            "loan_value": float(loan.amount),
                            "finding": "Loan amount changed from lead to loan (may be legitimate)",
                        })

            # Check fee data consistency (LE vs CD)
            fee_mismatches = db.execute(text("""
                SELECT fee_name, le_amount, cd_amount, tolerance_category
                FROM loan_fees
                WHERE loan_id = :loan_id
                    AND le_amount IS NOT NULL AND cd_amount IS NOT NULL
                    AND ABS(cd_amount - le_amount) > 0.01
            """), {"loan_id": loan_id}).fetchall()

            for fee in fee_mismatches:
                diff = abs(float(fee.cd_amount or 0) - float(fee.le_amount or 0))
                severity = "critical" if fee.tolerance_category == "zero" and diff > 0.01 else "minor"
                discrepancies.append({
                    "field": f"fee_{fee.fee_name}",
                    "severity": severity,
                    "le_value": float(fee.le_amount or 0),
                    "cd_value": float(fee.cd_amount or 0),
                    "finding": f"Fee variance on {fee.fee_name}: "
                               f"LE ${float(fee.le_amount or 0):,.2f} vs CD ${float(fee.cd_amount or 0):,.2f}",
                })

            # Check stage history for backdating
            stage_history = db.execute(text("""
                SELECT from_stage, to_stage, changed_at
                FROM loan_stage_history
                WHERE loan_id = :loan_id
                ORDER BY changed_at ASC
            """), {"loan_id": loan_id}).fetchall()

            prev_date = None
            for sh in stage_history:
                if prev_date and sh.changed_at and sh.changed_at < prev_date:
                    discrepancies.append({
                        "field": "stage_history",
                        "severity": "critical",
                        "finding": f"Stage transition date out of sequence: "
                                   f"{sh.from_stage} -> {sh.to_stage} at {sh.changed_at.isoformat()}",
                    })
                prev_date = sh.changed_at

            if not discrepancies:
                verified.append("All stage transitions in chronological order")

            has_critical = any(d["severity"] == "critical" for d in discrepancies)

            self.audit_log("check_data_integrity", "loan", entity_id=loan_id, details={
                "discrepancies": len(discrepancies),
                "verified": len(verified),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "integrity_status": "FAIL" if has_critical else ("WARNING" if discrepancies else "PASS"),
                    "discrepancies": discrepancies,
                    "verified_fields": verified,
                    "summary": {
                        "total_discrepancies": len(discrepancies),
                        "critical": len([d for d in discrepancies if d["severity"] == "critical"]),
                        "major": len([d for d in discrepancies if d["severity"] == "major"]),
                        "minor": len([d for d in discrepancies if d["severity"] == "minor"]),
                        "verified": len(verified),
                    },
                },
                message=f"Data integrity: {len(discrepancies)} discrepancies found, {len(verified)} fields verified"
            )

        except Exception as e:
            logger.exception(f"check_data_integrity failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_regulatory_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Comprehensive regulatory compliance verification."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        regulations = input_data.get("regulations") or ["trid", "respa", "ecoa"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.rate,
                       l.loan_type, l.stage, l.property_address,
                       l.application_date, l.initial_disclosures_sent_date,
                       l.initial_disclosures_signed_date,
                       l.cd_sent_to_borrower_date, l.cd_acknowledged_date,
                       l.funded_date, l.closing_date,
                       l.title_company, l.lender, l.realtor_agent
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            findings = []

            # TRID checks
            if "trid" in regulations:
                if loan.application_date and loan.initial_disclosures_sent_date:
                    le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                    if le_days > 3:
                        findings.append({
                            "regulation": "TRID",
                            "rule": "12 CFR 1026.19(e)(1)(iii)",
                            "severity": "critical",
                            "finding": f"LE delivered {le_days} days after application (max 3 business days)",
                            "status": "violation",
                        })
                    else:
                        findings.append({
                            "regulation": "TRID",
                            "rule": "LE timing",
                            "severity": "none",
                            "finding": "LE delivered within 3-day window",
                            "status": "compliant",
                        })
                elif loan.application_date and not loan.initial_disclosures_sent_date:
                    findings.append({
                        "regulation": "TRID",
                        "rule": "12 CFR 1026.19(e)(1)(iii)",
                        "severity": "critical",
                        "finding": "LE has not been delivered",
                        "status": "violation",
                    })

                if loan.cd_sent_to_borrower_date and loan.closing_date:
                    cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                    if cd_days < 3:
                        findings.append({
                            "regulation": "TRID",
                            "rule": "12 CFR 1026.19(f)(1)(ii)",
                            "severity": "critical",
                            "finding": f"CD delivered {cd_days} day(s) before closing (min 3)",
                            "status": "violation",
                        })
                    else:
                        findings.append({
                            "regulation": "TRID",
                            "rule": "CD timing",
                            "severity": "none",
                            "finding": "CD delivered within required window",
                            "status": "compliant",
                        })

                # Check for LE revisions
                revision_counts = db.execute(text("""
                    SELECT
                        COUNT(CASE WHEN disclosure_type = 'revised_le' THEN 1 END) as le_revisions,
                        COUNT(CASE WHEN disclosure_type = 'revised_cd' THEN 1 END) as cd_revisions
                    FROM disclosure_events
                    WHERE loan_id = :loan_id
                """), {"loan_id": loan_id}).fetchone()

                if revision_counts and revision_counts.le_revisions > 2:
                    findings.append({
                        "regulation": "TRID",
                        "rule": "LE revision frequency",
                        "severity": "minor",
                        "finding": f"{revision_counts.le_revisions} LE revisions - "
                                   f"verify valid changed circumstances for each",
                        "status": "review_required",
                    })

            # RESPA checks
            if "respa" in regulations:
                # Check for referral partner relationship
                referral = db.execute(text("""
                    SELECT ld.referral_partner_id, rp.name as partner_name
                    FROM leads ld
                    JOIN loans l ON l.loan_number = ld.loan_number
                    LEFT JOIN referral_partners rp ON rp.id = ld.referral_partner_id
                    WHERE l.id = :loan_id AND ld.referral_partner_id IS NOT NULL
                    LIMIT 1
                """), {"loan_id": loan_id}).fetchone()

                if referral and referral.partner_name:
                    findings.append({
                        "regulation": "RESPA",
                        "rule": "Section 8 - Referral fees",
                        "severity": "minor",
                        "finding": f"Referral partner ({referral.partner_name}) present - "
                                   f"verify no prohibited referral fees",
                        "status": "review_required",
                    })

                if loan.title_company:
                    findings.append({
                        "regulation": "RESPA",
                        "rule": "Section 8 - AfBA disclosure",
                        "severity": "minor",
                        "finding": f"Title company ({loan.title_company}) - "
                                   f"verify AfBA disclosure if affiliated",
                        "status": "review_required",
                    })

            # ECOA checks
            if "ecoa" in regulations:
                # Check for adverse action if denied
                if loan.stage in ("DENIED", "DOES_NOT_QUALIFY"):
                    findings.append({
                        "regulation": "ECOA",
                        "rule": "Adverse action notice",
                        "severity": "major",
                        "finding": "Loan denied - verify adverse action notice sent within 30 days",
                        "status": "review_required",
                    })

            violations = [f for f in findings if f["status"] == "violation"]
            reviews = [f for f in findings if f["status"] == "review_required"]
            compliant = [f for f in findings if f["status"] == "compliant"]

            overall = "NON-COMPLIANT" if violations else ("REVIEW_REQUIRED" if reviews else "COMPLIANT")

            self.audit_log("verify_regulatory_compliance", "loan", entity_id=loan_id, details={
                "result": overall,
                "violations": len(violations),
                "regulations_checked": regulations,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "overall_status": overall,
                    "regulations_checked": regulations,
                    "findings": findings,
                    "summary": {
                        "violations": len(violations),
                        "review_required": len(reviews),
                        "compliant": len(compliant),
                    },
                },
                message=f"Regulatory compliance: {overall} - "
                        f"{len(violations)} violations, {len(reviews)} items for review"
            )

        except Exception as e:
            logger.exception(f"verify_regulatory_compliance failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_repurchase_risks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify defects that could lead to repurchase demands."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.rate,
                       l.loan_type, l.stage, l.funded_date,
                       l.application_date, l.initial_disclosures_sent_date,
                       l.cd_sent_to_borrower_date, l.closing_date,
                       l.appraisal_value, l.appraisal_received_date,
                       l.credit_docs_expire_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            risks = []
            loan_amount = float(loan.amount or 0)

            # Risk 1: TRID timing violations - high repurchase risk
            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days > 3:
                    risks.append({
                        "risk_type": "trid_violation",
                        "severity": "critical",
                        "description": f"LE timing violation ({le_days} days)",
                        "repurchase_likelihood": "high",
                        "estimated_exposure": loan_amount,
                        "cure": "Cannot be cured post-closing - material breach",
                    })

            if loan.cd_sent_to_borrower_date and loan.closing_date:
                cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                if cd_days < 3:
                    risks.append({
                        "risk_type": "cd_timing_violation",
                        "severity": "critical",
                        "description": f"CD timing violation ({cd_days} day waiting period)",
                        "repurchase_likelihood": "high",
                        "estimated_exposure": loan_amount,
                        "cure": "Cannot be cured post-closing - material breach",
                    })

            # Risk 2: Stale documentation
            if loan.credit_docs_expire_date and loan.closing_date:
                expire_dt = loan.credit_docs_expire_date
                if hasattr(expire_dt, 'date'):
                    expire_dt = expire_dt.date()
                closing_dt = loan.closing_date
                if hasattr(closing_dt, 'date'):
                    closing_dt = closing_dt.date()
                if expire_dt < closing_dt:
                    risks.append({
                        "risk_type": "stale_documentation",
                        "severity": "major",
                        "description": "Credit documents expired before closing",
                        "repurchase_likelihood": "medium",
                        "estimated_exposure": loan_amount,
                        "cure": "Obtain updated credit report and re-verify qualifications",
                    })

            # Risk 3: Tolerance violations
            tolerance_violations = db.execute(text("""
                SELECT COUNT(*) as cnt,
                       SUM(CASE WHEN cd_amount > le_amount THEN cd_amount - le_amount ELSE 0 END) as total_cure
                FROM loan_fees
                WHERE loan_id = :loan_id
                    AND tolerance_category = 'zero'
                    AND cd_amount > le_amount
            """), {"loan_id": loan_id}).fetchone()

            if tolerance_violations and tolerance_violations.cnt > 0:
                cure_amount = float(tolerance_violations.total_cure or 0)
                risks.append({
                    "risk_type": "tolerance_violation",
                    "severity": "critical" if cure_amount > 500 else "major",
                    "description": f"{tolerance_violations.cnt} zero-tolerance fee violation(s), "
                                   f"cure amount: ${cure_amount:,.2f}",
                    "repurchase_likelihood": "high" if cure_amount > 500 else "medium",
                    "estimated_exposure": loan_amount,
                    "cure": f"Issue borrower refund of ${cure_amount:,.2f}",
                })

            # Risk 4: Missing critical documents
            docs = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing = {d.doc_type for d in docs}

            critical_docs = ["appraisal", "credit_report", "title"]
            for doc in critical_docs:
                if doc not in existing:
                    risks.append({
                        "risk_type": "missing_critical_document",
                        "severity": "major",
                        "description": f"Missing {doc} in loan file",
                        "repurchase_likelihood": "medium",
                        "estimated_exposure": loan_amount,
                        "cure": f"Obtain and add {doc} to file before investor delivery",
                    })

            # Risk 5: Open compliance alerts
            open_critical = db.execute(text("""
                SELECT COUNT(*) as cnt FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
                    AND severity IN ('critical', 'high')
            """), {"loan_id": loan_id}).fetchone()

            if open_critical and open_critical.cnt > 0:
                risks.append({
                    "risk_type": "unresolved_compliance",
                    "severity": "major",
                    "description": f"{open_critical.cnt} unresolved critical/high compliance alert(s)",
                    "repurchase_likelihood": "medium",
                    "estimated_exposure": loan_amount,
                    "cure": "Resolve all open compliance alerts before investor delivery",
                })

            total_exposure = loan_amount if any(r["repurchase_likelihood"] == "high" for r in risks) else 0
            risk_level = "HIGH" if any(r["severity"] == "critical" for r in risks) else (
                "MEDIUM" if risks else "LOW"
            )

            self.audit_log("identify_repurchase_risks", "loan", entity_id=loan_id, details={
                "risk_level": risk_level,
                "risk_count": len(risks),
                "exposure": total_exposure,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "loan_amount": loan_amount,
                    "risk_level": risk_level,
                    "risks": risks,
                    "total_exposure": total_exposure,
                    "summary": {
                        "critical_risks": len([r for r in risks if r["severity"] == "critical"]),
                        "major_risks": len([r for r in risks if r["severity"] == "major"]),
                        "high_likelihood": len([r for r in risks if r["repurchase_likelihood"] == "high"]),
                    },
                },
                message=f"Repurchase risk: {risk_level} - {len(risks)} risk factor(s), "
                        f"exposure: ${total_exposure:,.0f}"
            )

        except Exception as e:
            logger.exception(f"identify_repurchase_risks failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_qc_scorecard(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a 0-100 QC scorecard for a loan file."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount,
                       l.loan_type, l.stage,
                       l.application_date, l.initial_disclosures_sent_date,
                       l.initial_disclosures_signed_date,
                       l.cd_sent_to_borrower_date, l.cd_acknowledged_date,
                       l.closing_date, l.funded_date,
                       l.appraisal_received_date, l.appraisal_value,
                       l.credit_docs_expire_date,
                       u.nmls_number as lo_nmls
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            category_scores = {}
            defects_by_category = {}

            # --- Disclosure compliance (25 points) ---
            disc_score = 25
            disc_defects = []

            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days > 3:
                    disc_score -= 15
                    disc_defects.append(f"LE timing violation ({le_days} days)")
            elif loan.application_date and not loan.initial_disclosures_sent_date:
                disc_score -= 20
                disc_defects.append("LE not sent")

            if loan.cd_sent_to_borrower_date and loan.closing_date:
                cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                if cd_days < 3:
                    disc_score -= 15
                    disc_defects.append(f"CD timing violation ({cd_days} day wait)")

            if not loan.initial_disclosures_signed_date:
                disc_score -= 5
                disc_defects.append("LE not signed by borrower")

            category_scores["disclosure_compliance"] = max(0, disc_score)
            defects_by_category["disclosure_compliance"] = disc_defects

            # --- Data integrity (20 points) ---
            data_score = 20
            data_defects = []

            fee_issues = db.execute(text("""
                SELECT COUNT(*) as cnt FROM loan_fees
                WHERE loan_id = :loan_id
                    AND tolerance_category = 'zero'
                    AND cd_amount > le_amount
            """), {"loan_id": loan_id}).fetchone()

            if fee_issues and fee_issues.cnt > 0:
                data_score -= min(15, fee_issues.cnt * 5)
                data_defects.append(f"{fee_issues.cnt} tolerance violation(s)")

            category_scores["data_integrity"] = max(0, data_score)
            defects_by_category["data_integrity"] = data_defects

            # --- Document completeness (20 points) ---
            doc_score = 20
            doc_defects = []

            docs = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing = {d.doc_type for d in docs}

            required = ["paystubs", "w2", "bank_statements", "credit_report",
                        "appraisal", "title", "insurance"]
            missing = [r for r in required if r not in existing]
            if missing:
                doc_score -= min(20, len(missing) * 4)
                doc_defects.extend([f"Missing: {m}" for m in missing])

            if loan.credit_docs_expire_date:
                expire_dt = loan.credit_docs_expire_date
                if hasattr(expire_dt, 'date'):
                    expire_dt = expire_dt.date()
                if expire_dt < date.today():
                    doc_score -= 5
                    doc_defects.append("Credit documents expired")

            category_scores["document_completeness"] = max(0, doc_score)
            defects_by_category["document_completeness"] = doc_defects

            # --- Regulatory compliance (15 points) ---
            reg_score = 15
            reg_defects = []

            if not loan.lo_nmls:
                reg_score -= 5
                reg_defects.append("LO NMLS ID missing")

            open_alerts = db.execute(text("""
                SELECT COUNT(*) as cnt FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
            """), {"loan_id": loan_id}).fetchone()
            if open_alerts and open_alerts.cnt > 0:
                reg_score -= min(10, open_alerts.cnt * 3)
                reg_defects.append(f"{open_alerts.cnt} open compliance alert(s)")

            category_scores["regulatory_compliance"] = max(0, reg_score)
            defects_by_category["regulatory_compliance"] = reg_defects

            # --- Signature completeness (10 points) ---
            sig_score = 10
            sig_defects = []
            if not loan.initial_disclosures_signed_date:
                sig_score -= 5
                sig_defects.append("Initial disclosures unsigned")
            if not loan.cd_acknowledged_date and loan.cd_sent_to_borrower_date:
                sig_score -= 5
                sig_defects.append("CD not acknowledged")

            category_scores["signature_completeness"] = max(0, sig_score)
            defects_by_category["signature_completeness"] = sig_defects

            # --- Appraisal review (10 points) ---
            appr_score = 10
            appr_defects = []
            if not loan.appraisal_received_date and loan.stage not in (
                "APPLICATION", "DISCLOSED", "PROCESSING"
            ):
                appr_score -= 10
                appr_defects.append("Appraisal not received")
            elif loan.appraisal_received_date and not loan.appraisal_value:
                appr_score -= 5
                appr_defects.append("Appraisal value not recorded")

            category_scores["appraisal_review"] = max(0, appr_score)
            defects_by_category["appraisal_review"] = appr_defects

            # Total score
            total_score = sum(category_scores.values())
            all_defects = []
            for cat, defs in defects_by_category.items():
                for d in defs:
                    all_defects.append({"category": cat, "defect": d})

            if total_score >= 90:
                grade = "A"
            elif total_score >= 80:
                grade = "B"
            elif total_score >= 70:
                grade = "C"
            elif total_score >= 60:
                grade = "D"
            else:
                grade = "F"

            self.audit_log("generate_qc_scorecard", "loan", entity_id=loan_id, details={
                "score": total_score,
                "grade": grade,
                "defect_count": len(all_defects),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "total_score": total_score,
                    "grade": grade,
                    "category_scores": category_scores,
                    "category_weights": QC_CATEGORY_WEIGHTS,
                    "defects": all_defects,
                    "defect_count": len(all_defects),
                },
                message=f"QC Scorecard: {total_score}/100 (Grade {grade}) - {len(all_defects)} defect(s)"
            )

        except Exception as e:
            logger.exception(f"generate_qc_scorecard failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_to_investor_overlay(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Compare loan docs against specific investor overlay requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        investor = input_data.get("investor", "fannie_mae")
        org_id = self.require_org_id()

        overlay = INVESTOR_OVERLAYS.get(investor)
        if not overlay:
            return ToolResult(
                success=False,
                error=f"Unknown investor: {investor}. Use: fannie_mae, freddie_mac, ginnie_mae"
            )

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.amount, l.rate, l.loan_type,
                       l.appraisal_value, l.closing_date, l.credit_docs_expire_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            violations = []
            met = []

            # Document completeness check
            docs = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing = {d.doc_type for d in docs}

            for req_doc in overlay["required_docs"]:
                if req_doc in existing:
                    met.append(f"Document present: {req_doc}")
                else:
                    violations.append({
                        "requirement": f"{overlay['name']} required document: {req_doc}",
                        "status": "missing",
                        "severity": "major",
                    })

            # LTV check
            if loan.appraisal_value and loan.amount:
                ltv = (float(loan.amount) / float(loan.appraisal_value)) * 100
                max_ltv = overlay.get("max_ltv_conventional", 97)
                if ltv > max_ltv:
                    violations.append({
                        "requirement": f"Max LTV: {max_ltv}%",
                        "status": f"LTV is {ltv:.1f}%",
                        "severity": "critical",
                    })
                else:
                    met.append(f"LTV {ltv:.1f}% within {max_ltv}% limit")

            # Age of documents check
            if loan.closing_date and loan.credit_docs_expire_date:
                expire_dt = loan.credit_docs_expire_date
                if hasattr(expire_dt, 'date'):
                    expire_dt = expire_dt.date()
                closing_dt = loan.closing_date
                if hasattr(closing_dt, 'date'):
                    closing_dt = closing_dt.date()
                if expire_dt < closing_dt:
                    violations.append({
                        "requirement": "Documents must be within age limits at closing",
                        "status": "Credit documents expired before closing",
                        "severity": "major",
                    })

            eligible = len(violations) == 0

            self.audit_log("compare_to_investor_overlay", "loan", entity_id=loan_id, details={
                "investor": investor,
                "eligible": eligible,
                "violations": len(violations),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "investor": overlay["name"],
                    "eligible": eligible,
                    "violations": violations,
                    "requirements_met": met,
                    "specific_rules": overlay["specific_rules"],
                    "summary": {
                        "violations": len(violations),
                        "met": len(met),
                    },
                },
                message=f"Investor overlay ({overlay['name']}): "
                        f"{'Eligible' if eligible else 'NOT Eligible'} - "
                        f"{len(violations)} violation(s)"
            )

        except Exception as e:
            logger.exception(f"compare_to_investor_overlay failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_signature_completeness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify all required signatures are present."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                       l.initial_disclosures_signed_date,
                       l.cd_acknowledged_date,
                       l.cd_received_signed_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            sig_checks = []

            # Initial disclosures signature
            if loan.initial_disclosures_signed_date:
                sig_checks.append({
                    "document": "Initial Disclosures (LE)",
                    "status": "signed",
                    "signed_date": loan.initial_disclosures_signed_date.isoformat()
                        if loan.initial_disclosures_signed_date else None,
                })
            else:
                sig_checks.append({
                    "document": "Initial Disclosures (LE)",
                    "status": "unsigned",
                    "severity": "major",
                })

            # CD acknowledgment
            if loan.cd_acknowledged_date:
                sig_checks.append({
                    "document": "Closing Disclosure (CD)",
                    "status": "acknowledged",
                    "signed_date": loan.cd_acknowledged_date.isoformat()
                        if loan.cd_acknowledged_date else None,
                })
            else:
                # Only flag if CD has been sent
                sig_checks.append({
                    "document": "Closing Disclosure (CD)",
                    "status": "not_acknowledged",
                    "severity": "major" if loan.stage in (
                        "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED"
                    ) else "observation",
                })

            # CD signed copy received
            if loan.cd_received_signed_date:
                sig_checks.append({
                    "document": "Closing Disclosure - Signed Copy",
                    "status": "received",
                    "signed_date": loan.cd_received_signed_date.isoformat()
                        if loan.cd_received_signed_date else None,
                })
            elif loan.stage in ("FUNDED", "DOCS_OUT", "CLOSING"):
                sig_checks.append({
                    "document": "Closing Disclosure - Signed Copy",
                    "status": "not_received",
                    "severity": "major",
                })

            unsigned = [s for s in sig_checks if s["status"] in ("unsigned", "not_acknowledged", "not_received")]
            signed = [s for s in sig_checks if s["status"] in ("signed", "acknowledged", "received")]
            complete = len(unsigned) == 0

            self.audit_log("check_signature_completeness", "loan", entity_id=loan_id, details={
                "complete": complete,
                "unsigned": len(unsigned),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "signature_complete": complete,
                    "checks": sig_checks,
                    "summary": {
                        "signed": len(signed),
                        "unsigned": len(unsigned),
                        "total": len(sig_checks),
                    },
                },
                message=f"Signatures: {len(signed)}/{len(sig_checks)} complete"
                        f"{' - INCOMPLETE' if not complete else ''}"
            )

        except Exception as e:
            logger.exception(f"check_signature_completeness failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_disclosures_timing(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify all disclosures were sent/received within required timeframes."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number,
                       l.application_date,
                       l.initial_disclosures_sent_date,
                       l.initial_disclosures_signed_date,
                       l.loan_estimate_sent_date,
                       l.cd_sent_to_borrower_date,
                       l.cd_acknowledged_date,
                       l.cd_received_signed_date,
                       l.closing_date, l.funded_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            timing_checks = []

            # LE timing: 3 business days from application
            if loan.application_date:
                if loan.initial_disclosures_sent_date:
                    le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                    timing_checks.append({
                        "disclosure": "Loan Estimate (LE)",
                        "requirement": "Within 3 business days of application",
                        "application_date": loan.application_date.isoformat(),
                        "sent_date": loan.initial_disclosures_sent_date.isoformat(),
                        "calendar_days": le_days,
                        "status": "compliant" if le_days <= 3 else "violation",
                        "severity": "critical" if le_days > 3 else "none",
                    })
                else:
                    days_since_app = (date.today() - (
                        loan.application_date.date() if hasattr(loan.application_date, 'date')
                        else loan.application_date
                    )).days
                    timing_checks.append({
                        "disclosure": "Loan Estimate (LE)",
                        "requirement": "Within 3 business days of application",
                        "application_date": loan.application_date.isoformat(),
                        "sent_date": None,
                        "calendar_days": days_since_app,
                        "status": "violation" if days_since_app > 3 else "pending",
                        "severity": "critical" if days_since_app > 3 else "minor",
                    })

            # CD timing: 3 business days before closing
            if loan.cd_sent_to_borrower_date and loan.closing_date:
                cd_days = (loan.closing_date - loan.cd_sent_to_borrower_date).days
                timing_checks.append({
                    "disclosure": "Closing Disclosure (CD)",
                    "requirement": "3 business days before consummation",
                    "sent_date": loan.cd_sent_to_borrower_date.isoformat(),
                    "closing_date": loan.closing_date.isoformat(),
                    "calendar_days_before_closing": cd_days,
                    "status": "compliant" if cd_days >= 3 else "violation",
                    "severity": "critical" if cd_days < 3 else "none",
                })
            elif loan.closing_date and not loan.cd_sent_to_borrower_date:
                timing_checks.append({
                    "disclosure": "Closing Disclosure (CD)",
                    "requirement": "3 business days before consummation",
                    "sent_date": None,
                    "closing_date": loan.closing_date.isoformat(),
                    "status": "not_sent",
                    "severity": "critical",
                })

            # LE revision tracking
            revisions = db.execute(text("""
                SELECT disclosure_type, event_date, reason
                FROM disclosure_events
                WHERE loan_id = :loan_id
                ORDER BY event_date ASC
            """), {"loan_id": loan_id}).fetchall()

            revision_timeline = []
            for rev in revisions:
                revision_timeline.append({
                    "type": rev.disclosure_type,
                    "date": rev.event_date.isoformat() if rev.event_date else None,
                    "reason": rev.reason,
                })

            violations = [t for t in timing_checks if t["status"] == "violation"]
            compliant = [t for t in timing_checks if t["status"] == "compliant"]

            self.audit_log("verify_disclosures_timing", "loan", entity_id=loan_id, details={
                "violations": len(violations),
                "compliant": len(compliant),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "timing_checks": timing_checks,
                    "revision_timeline": revision_timeline,
                    "overall_status": "NON-COMPLIANT" if violations else "COMPLIANT",
                    "summary": {
                        "violations": len(violations),
                        "compliant": len(compliant),
                        "pending": len([t for t in timing_checks if t["status"] == "pending"]),
                        "revisions": len(revision_timeline),
                    },
                },
                message=f"Disclosure timing: "
                        f"{'NON-COMPLIANT' if violations else 'COMPLIANT'} - "
                        f"{len(violations)} violation(s)"
            )

        except Exception as e:
            logger.exception(f"verify_disclosures_timing failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_appraisal_independence(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify appraiser independence requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name,
                       l.appraisal_ordered_date, l.appraisal_scheduled_date,
                       l.appraisal_completed_date, l.appraisal_received_date,
                       l.appraisal_value, l.amount, l.property_address,
                       l.loan_officer_id,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            independence_checks = []

            # Check 1: Appraisal was ordered (should be through AMC or independent channel)
            if loan.appraisal_ordered_date:
                independence_checks.append({
                    "check": "Appraisal ordered through proper channel",
                    "status": "review_required",
                    "detail": f"Ordered on {loan.appraisal_ordered_date.isoformat()} - "
                              f"verify ordered through AMC or independent panel",
                    "regulation": "Dodd-Frank Section 1472 / AIR",
                })
            else:
                independence_checks.append({
                    "check": "Appraisal order documentation",
                    "status": "missing",
                    "detail": "No appraisal order date on file",
                    "severity": "major",
                })

            # Check 2: LO did not select or communicate with appraiser
            independence_checks.append({
                "check": "LO independence from appraiser selection",
                "status": "review_required",
                "detail": f"Verify LO ({loan.lo_name}) did not select or communicate "
                          f"with appraiser regarding value",
                "regulation": "Appraiser Independence Requirements (AIR)",
            })

            # Check 3: No pressure or coercion on value
            if loan.appraisal_value and loan.amount:
                # Flag if appraisal came in exactly at purchase/loan amount
                # (may indicate pressure, though not conclusive)
                if abs(float(loan.appraisal_value) - float(loan.amount)) < 1.0:
                    independence_checks.append({
                        "check": "Appraisal value vs loan amount",
                        "status": "review_required",
                        "detail": "Appraisal value matches loan amount exactly - "
                                  "verify no value pressure was applied",
                        "severity": "minor",
                    })

            # Check 4: Proper turnaround time
            if loan.appraisal_ordered_date and loan.appraisal_completed_date:
                turnaround = (loan.appraisal_completed_date - loan.appraisal_ordered_date).days
                if turnaround < 2:
                    independence_checks.append({
                        "check": "Appraisal turnaround time",
                        "status": "review_required",
                        "detail": f"Appraisal completed in {turnaround} day(s) - "
                                  f"unusually fast, verify thoroughness",
                        "severity": "minor",
                    })
                else:
                    independence_checks.append({
                        "check": "Appraisal turnaround time",
                        "status": "acceptable",
                        "detail": f"Completed in {turnaround} days",
                    })

            # Check 5: Appraisal delivered to borrower
            if loan.appraisal_received_date:
                independence_checks.append({
                    "check": "Appraisal copy provided to borrower",
                    "status": "review_required",
                    "detail": "Verify borrower received copy at least 3 business days before closing "
                              "(ECOA requirement)",
                    "regulation": "ECOA / Regulation B 12 CFR 1002.14",
                })

            issues = [c for c in independence_checks
                      if c["status"] in ("missing", "violation")]
            reviews = [c for c in independence_checks
                       if c["status"] == "review_required"]

            self.audit_log("check_appraisal_independence", "loan", entity_id=loan_id, details={
                "issues": len(issues),
                "reviews": len(reviews),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "independence_status": "VIOLATION" if issues else "REVIEW_REQUIRED",
                    "checks": independence_checks,
                    "summary": {
                        "issues": len(issues),
                        "review_required": len(reviews),
                        "acceptable": len([c for c in independence_checks
                                           if c["status"] == "acceptable"]),
                    },
                },
                message=f"Appraisal independence: {len(issues)} issue(s), "
                        f"{len(reviews)} item(s) for review"
            )

        except Exception as e:
            logger.exception(f"check_appraisal_independence failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_deficiency_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate comprehensive deficiency report with cure recommendations."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_cure = input_data.get("include_cure_plan", True)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount,
                       l.loan_type, l.stage, l.funded_date,
                       l.application_date, l.initial_disclosures_sent_date,
                       l.cd_sent_to_borrower_date, l.closing_date,
                       l.appraisal_received_date, l.credit_docs_expire_date,
                       l.initial_disclosures_signed_date, l.cd_acknowledged_date,
                       u.nmls_number as lo_nmls,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            deficiencies = []

            # Collect all deficiencies with cure plans

            # Disclosure deficiencies
            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days > 3:
                    deficiencies.append({
                        "id": len(deficiencies) + 1,
                        "category": "Disclosure Timing",
                        "severity": "critical",
                        "finding": f"LE delivered {le_days} days after application",
                        "regulation": "TRID 12 CFR 1026.19(e)(1)(iii)",
                        "cure": "Cannot be cured post-closing. Document exception with compliance officer." if include_cure else None,
                        "cure_deadline": None,
                        "responsible_party": "Compliance Officer",
                    })
            elif loan.application_date and not loan.initial_disclosures_sent_date:
                deficiencies.append({
                    "id": len(deficiencies) + 1,
                    "category": "Disclosure Timing",
                    "severity": "critical",
                    "finding": "Initial LE not sent",
                    "regulation": "TRID 12 CFR 1026.19(e)(1)(iii)",
                    "cure": "Send LE immediately. Document late delivery reason." if include_cure else None,
                    "cure_deadline": "Immediate",
                    "responsible_party": loan.lo_name or "Loan Officer",
                })

            # Signature deficiencies
            if not loan.initial_disclosures_signed_date:
                deficiencies.append({
                    "id": len(deficiencies) + 1,
                    "category": "Signatures",
                    "severity": "major",
                    "finding": "Initial disclosures not signed by borrower",
                    "regulation": "TRID disclosure receipt requirement",
                    "cure": "Obtain borrower signature on initial disclosures." if include_cure else None,
                    "cure_deadline": "Before submission to underwriting",
                    "responsible_party": "Processor",
                })

            if not loan.cd_acknowledged_date and loan.cd_sent_to_borrower_date:
                deficiencies.append({
                    "id": len(deficiencies) + 1,
                    "category": "Signatures",
                    "severity": "major",
                    "finding": "CD not acknowledged by borrower",
                    "regulation": "TRID CD acknowledgment",
                    "cure": "Obtain CD acknowledgment from borrower." if include_cure else None,
                    "cure_deadline": "Before closing",
                    "responsible_party": "Closer",
                })

            # Document deficiencies
            docs = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing = {d.doc_type for d in docs}

            required = ["paystubs", "w2", "bank_statements", "credit_report",
                        "appraisal", "title", "insurance"]
            for req_doc in required:
                if req_doc not in existing:
                    deficiencies.append({
                        "id": len(deficiencies) + 1,
                        "category": "Document Completeness",
                        "severity": "major",
                        "finding": f"Missing required document: {req_doc}",
                        "regulation": "Investor delivery requirement",
                        "cure": f"Obtain {req_doc} and upload to file." if include_cure else None,
                        "cure_deadline": "Before investor delivery",
                        "responsible_party": "Processor",
                    })

            # Credit expiration
            if loan.credit_docs_expire_date:
                expire_dt = loan.credit_docs_expire_date
                if hasattr(expire_dt, 'date'):
                    expire_dt = expire_dt.date()
                if expire_dt < date.today():
                    deficiencies.append({
                        "id": len(deficiencies) + 1,
                        "category": "Document Freshness",
                        "severity": "major",
                        "finding": f"Credit documents expired on {expire_dt.isoformat()}",
                        "regulation": "Age-of-document investor requirement",
                        "cure": "Order new credit report and re-verify qualifying ratios." if include_cure else None,
                        "cure_deadline": "Before investor delivery",
                        "responsible_party": "Processor",
                    })

            # NMLS
            if not loan.lo_nmls:
                deficiencies.append({
                    "id": len(deficiencies) + 1,
                    "category": "Regulatory",
                    "severity": "major",
                    "finding": "LO NMLS ID not on file",
                    "regulation": "SAFE Act",
                    "cure": "Add LO NMLS ID to loan file and all disclosures." if include_cure else None,
                    "cure_deadline": "Before investor delivery",
                    "responsible_party": "Compliance",
                })

            # Tolerance violations
            tolerance_issues = db.execute(text("""
                SELECT fee_name, le_amount, cd_amount, tolerance_category
                FROM loan_fees
                WHERE loan_id = :loan_id
                    AND tolerance_category = 'zero'
                    AND cd_amount > le_amount
            """), {"loan_id": loan_id}).fetchall()

            for tv in tolerance_issues:
                cure_amt = float(tv.cd_amount or 0) - float(tv.le_amount or 0)
                deficiencies.append({
                    "id": len(deficiencies) + 1,
                    "category": "Fee Tolerance",
                    "severity": "critical",
                    "finding": f"Zero-tolerance violation on {tv.fee_name}: "
                               f"${cure_amt:,.2f} overcharge",
                    "regulation": "TRID tolerance requirements",
                    "cure": f"Issue borrower refund of ${cure_amt:,.2f}." if include_cure else None,
                    "cure_deadline": "Before investor delivery or within 60 days of closing",
                    "responsible_party": "Accounting / Compliance",
                })

            critical = len([d for d in deficiencies if d["severity"] == "critical"])
            major = len([d for d in deficiencies if d["severity"] == "major"])

            self.audit_log("generate_deficiency_report", "loan", entity_id=loan_id, details={
                "deficiency_count": len(deficiencies),
                "critical": critical,
                "major": major,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "report_date": datetime.utcnow().isoformat(),
                    "deficiencies": deficiencies,
                    "summary": {
                        "total": len(deficiencies),
                        "critical": critical,
                        "major": major,
                        "minor": len([d for d in deficiencies if d["severity"] == "minor"]),
                    },
                    "file_status": "DEFICIENT" if deficiencies else "CLEAN",
                },
                message=f"Deficiency report: {len(deficiencies)} deficiency(ies) - "
                        f"{critical} critical, {major} major"
            )

        except Exception as e:
            logger.exception(f"generate_deficiency_report failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_defect_trends(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Analyze QC defect trends across loans/LOs/processors."""
        from database import SessionLocal

        period_days = input_data.get("period_days", 90)
        group_by = input_data.get("group_by", "defect_type")
        lo_id = input_data.get("lo_id")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            params = {"org_id": org_id, "period_days": period_days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            # Analyze compliance alerts as proxy for QC defects
            if group_by == "lo":
                trends = db.execute(text(f"""
                    SELECT
                        CONCAT(u.first_name, ' ', u.last_name) as group_name,
                        COUNT(*) as defect_count,
                        COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END) as critical_count,
                        COUNT(CASE WHEN ca.severity = 'high' THEN 1 END) as major_count,
                        COUNT(DISTINCT ca.loan_id) as affected_loans
                    FROM compliance_alerts ca
                    JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE ca.created_at >= CURRENT_DATE - :period_days
                        {lo_filter}
                    GROUP BY u.first_name, u.last_name
                    ORDER BY defect_count DESC
                """), params).fetchall()
            else:
                trends = db.execute(text(f"""
                    SELECT
                        ca.alert_type as group_name,
                        COUNT(*) as defect_count,
                        COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END) as critical_count,
                        COUNT(CASE WHEN ca.severity = 'high' THEN 1 END) as major_count,
                        COUNT(DISTINCT ca.loan_id) as affected_loans
                    FROM compliance_alerts ca
                    JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                    WHERE ca.created_at >= CURRENT_DATE - :period_days
                        {lo_filter}
                    GROUP BY ca.alert_type
                    ORDER BY defect_count DESC
                """), params).fetchall()

            if not trends:
                return ToolResult(
                    success=True,
                    data={"trends": [], "period_days": period_days},
                    message=f"No defects found in the last {period_days} days"
                )

            total_defects = sum(t.defect_count for t in trends)

            trend_data = [
                {
                    "group": t.group_name,
                    "total_defects": t.defect_count,
                    "critical": t.critical_count,
                    "major": t.major_count,
                    "affected_loans": t.affected_loans,
                    "pct_of_total": round((t.defect_count / total_defects) * 100, 1) if total_defects > 0 else 0,
                }
                for t in trends
            ]

            self.audit_log("track_defect_trends", details={
                "period_days": period_days,
                "group_by": group_by,
                "total_defects": total_defects,
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": period_days,
                    "group_by": group_by,
                    "total_defects": total_defects,
                    "trends": trend_data,
                    "top_defect": trend_data[0] if trend_data else None,
                },
                message=f"Defect trends ({period_days}d): {total_defects} total defects, "
                        f"top: {trend_data[0]['group'] if trend_data else 'none'}"
            )

        except Exception as e:
            logger.exception("track_defect_trends failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_defect_rate(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Calculate organization-level defect rate."""
        from database import SessionLocal

        period_days = input_data.get("period_days", 90)
        lo_id = input_data.get("lo_id")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            params = {"org_id": org_id, "period_days": period_days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            # Total loans in period
            total_loans = db.execute(text(f"""
                SELECT COUNT(DISTINCT l.id) as cnt
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.created_at >= CURRENT_DATE - :period_days
                    {lo_filter}
            """), params).fetchone()

            # Loans with critical/high defects
            defective_loans = db.execute(text(f"""
                SELECT COUNT(DISTINCT ca.loan_id) as cnt
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                WHERE ca.created_at >= CURRENT_DATE - :period_days
                    AND ca.severity IN ('critical', 'high')
                    {lo_filter}
            """), params).fetchone()

            total = total_loans.cnt if total_loans else 0
            defective = defective_loans.cnt if defective_loans else 0
            defect_rate = round((defective / total) * 100, 1) if total > 0 else 0

            # Industry benchmark: 5% or less is excellent
            if defect_rate <= 5:
                rating = "EXCELLENT"
            elif defect_rate <= 10:
                rating = "ACCEPTABLE"
            elif defect_rate <= 15:
                rating = "NEEDS_IMPROVEMENT"
            else:
                rating = "CRITICAL"

            # Severity breakdown
            severity_breakdown = db.execute(text(f"""
                SELECT
                    ca.severity,
                    COUNT(*) as cnt
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                WHERE ca.created_at >= CURRENT_DATE - :period_days
                    {lo_filter}
                GROUP BY ca.severity
                ORDER BY cnt DESC
            """), params).fetchall()

            self.audit_log("calculate_defect_rate", details={
                "defect_rate": defect_rate,
                "rating": rating,
                "total_loans": total,
                "defective_loans": defective,
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": period_days,
                    "total_loans_audited": total,
                    "loans_with_defects": defective,
                    "defect_rate_pct": defect_rate,
                    "rating": rating,
                    "benchmark": {
                        "excellent": "0-5%",
                        "acceptable": "5-10%",
                        "needs_improvement": "10-15%",
                        "critical": ">15%",
                    },
                    "severity_breakdown": [
                        {"severity": s.severity, "count": s.cnt}
                        for s in severity_breakdown
                    ],
                },
                message=f"Defect rate: {defect_rate}% ({rating}) - "
                        f"{defective}/{total} loans with critical/high defects"
            )

        except Exception as e:
            logger.exception("calculate_defect_rate failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_process_improvements(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Based on defect patterns, suggest process changes."""
        from database import SessionLocal

        period_days = input_data.get("period_days", 90)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            params = {"org_id": org_id, "period_days": period_days}

            # Get top defect types
            top_defects = db.execute(text("""
                SELECT
                    ca.alert_type,
                    COUNT(*) as cnt,
                    COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END) as critical_cnt
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                WHERE ca.created_at >= CURRENT_DATE - :period_days
                GROUP BY ca.alert_type
                ORDER BY cnt DESC
                LIMIT 10
            """), params).fetchall()

            # Get repeat-offender LOs
            repeat_los = db.execute(text("""
                SELECT
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                    COUNT(*) as defect_count,
                    COUNT(DISTINCT ca.loan_id) as affected_loans
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                JOIN users u ON u.id = l.loan_officer_id
                WHERE ca.created_at >= CURRENT_DATE - :period_days
                    AND ca.severity IN ('critical', 'high')
                GROUP BY u.first_name, u.last_name
                HAVING COUNT(*) >= 3
                ORDER BY defect_count DESC
            """), params).fetchall()

            recommendations = []

            # Recommendation mapping based on defect type patterns
            defect_recommendations = {
                "trid_timing": {
                    "issue": "TRID disclosure timing violations",
                    "recommendation": "Implement automated LE delivery within 24 hours of application receipt. "
                                     "Add real-time alerts at 48 hours post-application.",
                    "impact": "HIGH - regulatory risk reduction",
                    "effort": "MEDIUM - requires workflow automation",
                },
                "missing_document": {
                    "issue": "Missing required documents at closing",
                    "recommendation": "Implement mandatory document checklist gate at processing "
                                     "stage. Automate borrower document reminders at 3-day intervals.",
                    "impact": "HIGH - reduces post-closing deficiency rate",
                    "effort": "LOW - process change with existing tools",
                },
                "tolerance_violation": {
                    "issue": "Fee tolerance violations",
                    "recommendation": "Implement automated fee comparison between LE and CD before "
                                     "closing package generation. Require compliance sign-off on any fee change.",
                    "impact": "HIGH - prevents borrower refund obligations",
                    "effort": "MEDIUM - requires fee tracking enhancement",
                },
                "stale_documentation": {
                    "issue": "Expired/stale documentation at closing",
                    "recommendation": "Add document expiration tracking with 30-day, 15-day, and 7-day "
                                     "automated alerts. Block closing package generation with expired docs.",
                    "impact": "MEDIUM - prevents investor rejection",
                    "effort": "LOW - alerting enhancement",
                },
            }

            for defect in top_defects:
                alert_type = defect.alert_type or ""
                for key, rec in defect_recommendations.items():
                    if key in alert_type.lower():
                        recommendations.append({
                            "defect_type": defect.alert_type,
                            "occurrences": defect.cnt,
                            "critical_count": defect.critical_cnt,
                            **rec,
                        })
                        break
                else:
                    # Generic recommendation for unmapped defect types
                    recommendations.append({
                        "defect_type": defect.alert_type,
                        "occurrences": defect.cnt,
                        "critical_count": defect.critical_cnt,
                        "issue": f"Recurring {defect.alert_type} defects ({defect.cnt} in {period_days} days)",
                        "recommendation": f"Conduct root cause analysis on {defect.alert_type} defects. "
                                         f"Implement targeted training for affected staff.",
                        "impact": "MEDIUM",
                        "effort": "LOW - training initiative",
                    })

            # Add training recommendations for repeat offenders
            training_recs = []
            for lo in repeat_los:
                training_recs.append({
                    "lo_name": lo.lo_name,
                    "defect_count": lo.defect_count,
                    "affected_loans": lo.affected_loans,
                    "recommendation": f"Schedule QC remediation training for {lo.lo_name} - "
                                     f"{lo.defect_count} defects across {lo.affected_loans} loans",
                })

            self.audit_log("recommend_process_improvements", details={
                "recommendations": len(recommendations),
                "training_recs": len(training_recs),
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": period_days,
                    "process_recommendations": recommendations,
                    "training_recommendations": training_recs,
                    "summary": {
                        "process_changes": len(recommendations),
                        "training_needed": len(training_recs),
                        "top_defect": top_defects[0].alert_type if top_defects else None,
                    },
                },
                message=f"Process improvements: {len(recommendations)} recommendation(s), "
                        f"{len(training_recs)} training need(s)"
            )

        except Exception as e:
            logger.exception("recommend_process_improvements failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_audit_trail_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate complete audit trail for examiner review."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.amount,
                       l.loan_type, l.stage, l.created_at,
                       l.application_date, l.funded_date, l.closing_date,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                       u.nmls_number as lo_nmls
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Stage history
            stage_history = db.execute(text("""
                SELECT from_stage, to_stage, changed_at, changed_by, reason
                FROM loan_stage_history
                WHERE loan_id = :loan_id
                ORDER BY changed_at ASC
            """), {"loan_id": loan_id}).fetchall()

            # Disclosure events
            disclosure_events = db.execute(text("""
                SELECT disclosure_type, event_date, reason
                FROM disclosure_events
                WHERE loan_id = :loan_id
                ORDER BY event_date ASC
            """), {"loan_id": loan_id}).fetchall()

            # Compliance alerts
            compliance_alerts = db.execute(text("""
                SELECT alert_type, severity, title, status,
                       created_at, resolved_at, resolution_notes
                FROM compliance_alerts
                WHERE loan_id = :loan_id
                ORDER BY created_at ASC
            """), {"loan_id": loan_id}).fetchall()

            # Documents
            documents = db.execute(text("""
                SELECT doc_type, doc_category, status, uploaded_at, source
                FROM documents
                WHERE loan_id = :loan_id
                ORDER BY uploaded_at ASC
            """), {"loan_id": loan_id}).fetchall()

            # Activities
            activities = db.execute(text("""
                SELECT a.type, a.content, a.created_at,
                       CONCAT(u.first_name, ' ', u.last_name) as user_name
                FROM activities a
                LEFT JOIN users u ON u.id = a.user_id
                WHERE a.loan_id = :loan_id
                ORDER BY a.created_at ASC
                LIMIT 100
            """), {"loan_id": loan_id}).fetchall()

            audit_trail = {
                "stage_transitions": [
                    {
                        "from": sh.from_stage,
                        "to": sh.to_stage,
                        "date": sh.changed_at.isoformat() if sh.changed_at else None,
                        "changed_by": sh.changed_by,
                        "reason": sh.reason,
                    }
                    for sh in stage_history
                ],
                "disclosure_events": [
                    {
                        "type": de.disclosure_type,
                        "date": de.event_date.isoformat() if de.event_date else None,
                        "reason": de.reason,
                    }
                    for de in disclosure_events
                ],
                "compliance_alerts": [
                    {
                        "type": ca.alert_type,
                        "severity": ca.severity,
                        "title": ca.title,
                        "status": ca.status,
                        "created": ca.created_at.isoformat() if ca.created_at else None,
                        "resolved": ca.resolved_at.isoformat() if ca.resolved_at else None,
                        "resolution": ca.resolution_notes,
                    }
                    for ca in compliance_alerts
                ],
                "documents": [
                    {
                        "type": d.doc_type,
                        "category": d.doc_category,
                        "status": d.status,
                        "uploaded": d.uploaded_at.isoformat() if d.uploaded_at else None,
                        "source": d.source,
                    }
                    for d in documents
                ],
                "activities": [
                    {
                        "type": a.type,
                        "content": (a.content or "")[:200],
                        "date": a.created_at.isoformat() if a.created_at else None,
                        "user": a.user_name,
                    }
                    for a in activities
                ],
            }

            self.audit_log("generate_audit_trail_report", "loan", entity_id=loan_id, details={
                "stage_transitions": len(audit_trail["stage_transitions"]),
                "disclosures": len(audit_trail["disclosure_events"]),
                "alerts": len(audit_trail["compliance_alerts"]),
                "documents": len(audit_trail["documents"]),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "lo_nmls": loan.lo_nmls,
                    "loan_amount": float(loan.amount) if loan.amount else 0,
                    "loan_type": loan.loan_type,
                    "current_stage": loan.stage,
                    "application_date": loan.application_date.isoformat() if loan.application_date else None,
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
                    "report_generated": datetime.utcnow().isoformat(),
                    "audit_trail": audit_trail,
                    "summary": {
                        "stage_transitions": len(audit_trail["stage_transitions"]),
                        "disclosure_events": len(audit_trail["disclosure_events"]),
                        "compliance_alerts": len(audit_trail["compliance_alerts"]),
                        "documents_on_file": len(audit_trail["documents"]),
                        "activities_logged": len(audit_trail["activities"]),
                    },
                },
                message=f"Audit trail for loan {loan.loan_number}: "
                        f"{len(audit_trail['stage_transitions'])} transitions, "
                        f"{len(audit_trail['documents'])} documents, "
                        f"{len(audit_trail['compliance_alerts'])} alerts"
            )

        except Exception as e:
            logger.exception(f"generate_audit_trail_report failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
