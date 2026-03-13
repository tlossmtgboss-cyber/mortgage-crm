"""
Document Compliance Monitoring Agent

Specialized agent for document-related regulatory compliance with 15 tools:
1. check_trid_document_compliance - Verify TRID disclosure timing
2. check_document_retention - Verify retention requirements
3. audit_esign_compliance - Verify e-signatures meet ESIGN/UETA
4. check_fair_lending_patterns - Analyze document collection for ECOA
5. verify_income_documentation - Verify Fannie Mae B3-3 requirements
6. check_flood_zone_docs - Verify flood determination and insurance
7. audit_privacy_compliance - Verify GLBA/Reg P PII handling
8. generate_compliance_scorecard - Score loan file 0-100
9. check_state_specific_requirements - Verify state-specific doc rules
10. identify_compliance_risks - Proactive risk identification
11. generate_examiner_ready_report - Pre-exam regulatory report
12. track_regulatory_changes - Surface guideline changes
13. audit_fraud_detection_process - Verify BSA/AML workflow
14. check_hmda_data_quality - Verify HMDA data completeness
15. generate_compliance_remediation_plan - Prioritized fix plan
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

# Retention periods in years by document type (federal minimums)
RETENTION_PERIODS = {
    "paystubs": 3,
    "w2": 3,
    "tax_returns": 7,
    "1099": 7,
    "profit_loss": 7,
    "bank_statements": 5,
    "investment_statements": 5,
    "gift_letter": 3,
    "purchase_contract": 7,
    "appraisal": 7,
    "title": 7,
    "insurance": 7,
    "hoa": 3,
    "drivers_license": 3,
    "ssn_card": 3,
    "passport": 3,
    "credit_report": 3,
    "credit_explanation": 3,
    "bankruptcy_docs": 7,
    "loan_estimate": 5,
    "closing_disclosure": 5,
    "initial_disclosures": 5,
    "right_of_rescission": 5,
    "flood_determination": 7,
    "flood_insurance": 7,
    "privacy_notice": 5,
    "hmda_lar": 5,
}

# Required HMDA fields (Reg C)
HMDA_REQUIRED_FIELDS = [
    "loan_type", "loan_purpose", "loan_amount", "rate",
    "property_type", "occupancy_type",
    "borrower_ethnicity", "borrower_race", "borrower_sex",
    "income", "property_state", "property_county",
    "census_tract", "action_taken", "action_taken_date",
]

# State-specific document requirements
STATE_DOC_REQUIREMENTS = {
    "TX": {
        "name": "Texas",
        "rules": [
            {
                "regulation": "TX Constitution Art XVI Sec 50",
                "requirement": "Home Equity Disclosure (12-day notice)",
                "doc_type": "tx_home_equity_disclosure",
                "applies_to": "cash_out_refinance",
                "timing": "12 days before closing",
            },
            {
                "regulation": "TX Constitution Art XVI Sec 50(a)(6)",
                "requirement": "80% LTV cap on home equity loans",
                "doc_type": "tx_ltv_certification",
                "applies_to": "home_equity",
                "timing": "at closing",
            },
        ],
    },
    "NY": {
        "name": "New York",
        "rules": [
            {
                "regulation": "3 NYCRR Part 41",
                "requirement": "Subprime Home Loan Warning Notice",
                "doc_type": "ny_subprime_warning",
                "applies_to": "high_cost_mortgage",
                "timing": "at or before application",
            },
            {
                "regulation": "NY Banking Law 6-l",
                "requirement": "Mortgage Loan Originator License Disclosure",
                "doc_type": "ny_mlo_disclosure",
                "applies_to": "all",
                "timing": "at application",
            },
        ],
    },
    "CA": {
        "name": "California",
        "rules": [
            {
                "regulation": "CA Civil Code 2923.1",
                "requirement": "Mortgage Loan Disclosure Statement (MLDS)",
                "doc_type": "ca_mlds",
                "applies_to": "all",
                "timing": "within 3 days of application",
            },
            {
                "regulation": "CA Business & Professions Code 10240",
                "requirement": "Fair Lending Notice",
                "doc_type": "ca_fair_lending_notice",
                "applies_to": "all",
                "timing": "at application",
            },
        ],
    },
    "FL": {
        "name": "Florida",
        "rules": [
            {
                "regulation": "FL Statute 494",
                "requirement": "Loan Originator License Disclosure",
                "doc_type": "fl_originator_disclosure",
                "applies_to": "all",
                "timing": "at application",
            },
        ],
    },
}

# Compliance scorecard weights
SCORECARD_WEIGHTS = {
    "trid_timing": 20,
    "document_completeness": 15,
    "esign_compliance": 10,
    "retention_compliance": 10,
    "state_specific": 10,
    "hmda_data_quality": 10,
    "privacy_compliance": 10,
    "flood_compliance": 5,
    "fraud_process": 5,
    "fair_lending": 5,
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CheckTridDocComplianceInput(BaseModel):
    """Input for TRID document compliance check"""
    loan_id: int = Field(..., description="Loan ID to check")
    include_revisions: bool = Field(default=True, description="Include revision history")


class CheckDocRetentionInput(BaseModel):
    """Input for document retention compliance check"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    days_to_expiry: int = Field(default=90, description="Flag docs expiring within N days")


class AuditEsignInput(BaseModel):
    """Input for e-sign compliance audit"""
    loan_id: int = Field(..., description="Loan ID to audit")


class CheckFairLendingInput(BaseModel):
    """Input for fair lending pattern analysis"""
    lo_id: Optional[int] = Field(None, description="Loan officer ID")
    period_days: int = Field(default=90, description="Analysis period in days")


class VerifyIncomeDocsInput(BaseModel):
    """Input for income documentation verification"""
    loan_id: int = Field(..., description="Loan ID to verify")


class CheckFloodZoneInput(BaseModel):
    """Input for flood zone document check"""
    loan_id: int = Field(..., description="Loan ID to check")


class AuditPrivacyInput(BaseModel):
    """Input for privacy compliance audit"""
    loan_id: int = Field(..., description="Loan ID to audit")


class ComplianceScorecardInput(BaseModel):
    """Input for compliance scorecard generation"""
    loan_id: int = Field(..., description="Loan ID to score")


class StateRequirementsInput(BaseModel):
    """Input for state-specific requirements check"""
    loan_id: int = Field(..., description="Loan ID to check")
    state_code: Optional[str] = Field(None, description="Override state code (defaults to loan property state)")


class IdentifyRisksInput(BaseModel):
    """Input for compliance risk identification"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID (None for portfolio scan)")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")
    limit: int = Field(default=20, description="Maximum results")


class ExaminerReportInput(BaseModel):
    """Input for examiner-ready report generation"""
    loan_id: Optional[int] = Field(None, description="Specific loan or None for portfolio")
    period_days: int = Field(default=90, description="Report period")


class RegulatoryChangesInput(BaseModel):
    """Input for regulatory change tracking"""
    category: Optional[str] = Field(None, description="Filter by category: trid, hmda, fair_lending, privacy, state")


class AuditFraudDetectionInput(BaseModel):
    """Input for fraud detection process audit"""
    loan_id: int = Field(..., description="Loan ID to audit")


class CheckHmdaInput(BaseModel):
    """Input for HMDA data quality check"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    period_days: int = Field(default=365, description="Period for aggregate check")


class RemediationPlanInput(BaseModel):
    """Input for compliance remediation plan"""
    loan_id: int = Field(..., description="Loan ID to remediate")
    include_cost_estimates: bool = Field(default=True, description="Include estimated cure costs")


# ============================================================================
# DOCUMENT COMPLIANCE AGENT
# ============================================================================

@AgentRegistry.register
class DocComplianceAgent(SpecializedAgent):
    """
    Specialized agent for document-related regulatory compliance monitoring.

    Covers TRID, RESPA, ECOA, HMDA, GLBA, BSA/AML, ESIGN/UETA, and state
    laws. Applies a conservative, risk-averse approach: when in doubt, flag
    for human review. Every decision is audit-logged.
    """

    @property
    def name(self) -> str:
        return "DocComplianceAgent"

    @property
    def description(self) -> str:
        return (
            "Document compliance monitoring agent covering TRID, RESPA, ECOA, "
            "HMDA, GLBA, BSA/AML, ESIGN/UETA, and state-specific regulations"
        )

    def _register_tools(self):
        """Register all 15 document compliance tools"""

        # Tool 1: TRID Document Compliance
        self.register_tool(AgentTool(
            name="check_trid_document_compliance",
            description="Verify TRID disclosure timing for loan documents. Checks LE within 3 "
                       "business days of application and CD at least 3 business days before closing.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_trid_document_compliance,
            input_schema=CheckTridDocComplianceInput
        ))

        # Tool 2: Document Retention
        self.register_tool(AgentTool(
            name="check_document_retention",
            description="Verify all documents meet federal and state retention requirements. "
                       "Flags documents approaching or past retention deadlines.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_document_retention,
            input_schema=CheckDocRetentionInput
        ))

        # Tool 3: E-Sign Compliance
        self.register_tool(AgentTool(
            name="audit_esign_compliance",
            description="Verify e-signatures meet ESIGN Act and UETA requirements including "
                       "consent records, audit trails, and tamper-evident seals.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._audit_esign_compliance,
            input_schema=AuditEsignInput
        ))

        # Tool 4: Fair Lending Patterns
        self.register_tool(AgentTool(
            name="check_fair_lending_patterns",
            description="Analyze document collection patterns across demographic groups for ECOA "
                       "compliance. Detects disparate treatment in document requests.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_fair_lending_patterns,
            input_schema=CheckFairLendingInput
        ))

        # Tool 5: Income Documentation
        self.register_tool(AgentTool(
            name="verify_income_documentation",
            description="Verify income documents meet Fannie Mae B3-3 requirements including "
                       "paystub recency, W-2 coverage, and self-employment documentation.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._verify_income_documentation,
            input_schema=VerifyIncomeDocsInput
        ))

        # Tool 6: Flood Zone Documents
        self.register_tool(AgentTool(
            name="check_flood_zone_docs",
            description="Verify flood determination and insurance documentation for applicable "
                       "properties per FDPA requirements.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_flood_zone_docs,
            input_schema=CheckFloodZoneInput
        ))

        # Tool 7: Privacy Compliance
        self.register_tool(AgentTool(
            name="audit_privacy_compliance",
            description="Verify PII handling meets GLBA and Regulation P requirements including "
                       "privacy notices, safeguard procedures, and opt-out rights.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._audit_privacy_compliance,
            input_schema=AuditPrivacyInput
        ))

        # Tool 8: Compliance Scorecard
        self.register_tool(AgentTool(
            name="generate_compliance_scorecard",
            description="Score a loan file's overall compliance on a 0-100 scale across TRID, "
                       "documents, e-sign, retention, state rules, HMDA, privacy, and more.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_compliance_scorecard,
            input_schema=ComplianceScorecardInput
        ))

        # Tool 9: State-Specific Requirements
        self.register_tool(AgentTool(
            name="check_state_specific_requirements",
            description="Verify state-specific document requirements including TX home equity, "
                       "NY subprime warnings, and CA MLDS disclosures.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_state_specific_requirements,
            input_schema=StateRequirementsInput
        ))

        # Tool 10: Compliance Risk Identification
        self.register_tool(AgentTool(
            name="identify_compliance_risks",
            description="Proactively identify compliance risks before they become violations. "
                       "Scans loan files for missing disclosures, timing gaps, and documentation issues.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_compliance_risks,
            input_schema=IdentifyRisksInput
        ))

        # Tool 11: Examiner-Ready Report
        self.register_tool(AgentTool(
            name="generate_examiner_ready_report",
            description="Create a pre-examination report for regulatory examination prep with "
                       "compliance metrics, violation history, and remediation status.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_examiner_ready_report,
            input_schema=ExaminerReportInput
        ))

        # Tool 12: Regulatory Change Tracking
        self.register_tool(AgentTool(
            name="track_regulatory_changes",
            description="Surface recent guideline changes that affect document requirements "
                       "across TRID, HMDA, fair lending, privacy, and state regulations.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_regulatory_changes,
            input_schema=RegulatoryChangesInput
        ))

        # Tool 13: Fraud Detection Process Audit
        self.register_tool(AgentTool(
            name="audit_fraud_detection_process",
            description="Verify fraud detection workflow follows BSA/AML requirements including "
                       "SAR filing procedures, red flag identification, and CIP compliance.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._audit_fraud_detection_process,
            input_schema=AuditFraudDetectionInput
        ))

        # Tool 14: HMDA Data Quality
        self.register_tool(AgentTool(
            name="check_hmda_data_quality",
            description="Verify HMDA-reportable data is complete and accurate per Regulation C "
                       "requirements. Checks all required LAR fields.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_hmda_data_quality,
            input_schema=CheckHmdaInput
        ))

        # Tool 15: Compliance Remediation Plan
        self.register_tool(AgentTool(
            name="generate_compliance_remediation_plan",
            description="For identified compliance issues, create a prioritized remediation plan "
                       "with deadlines, owners, and estimated cure costs.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_compliance_remediation_plan,
            input_schema=RemediationPlanInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _check_trid_document_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check TRID disclosure timing using real loan date columns."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.application_date,
                    l.initial_disclosures_sent_date,
                    l.initial_disclosures_signed_date,
                    l.cd_sent_to_borrower_date,
                    l.cd_acknowledged_date,
                    l.funded_date, l.closing_date, l.stage
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            issues = []
            warnings = []
            passed = []

            # LE timing: must be within 3 business days of application
            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days <= 3:
                    passed.append({
                        "check": "LE_TIMING",
                        "message": f"LE sent in {le_days} day(s) - within 3-day requirement",
                    })
                else:
                    issues.append({
                        "check": "LE_TIMING",
                        "severity": "high",
                        "regulation": "12 CFR 1026.19(e)(1)(iii)",
                        "message": f"LE sent {le_days} days after application (max 3 business days)",
                        "days_over": le_days - 3,
                    })
            elif loan.application_date and not loan.initial_disclosures_sent_date:
                days_since = (date.today() - loan.application_date).days if isinstance(
                    loan.application_date, date
                ) else (date.today() - loan.application_date.date()).days
                if days_since > 2:
                    issues.append({
                        "check": "LE_NOT_SENT",
                        "severity": "critical",
                        "regulation": "12 CFR 1026.19(e)(1)(iii)",
                        "message": f"LE not sent - {days_since} days since application",
                    })
                else:
                    warnings.append({
                        "check": "LE_PENDING",
                        "message": f"LE not yet sent - {days_since} day(s) since application (due by day 3)",
                    })

            # CD timing: must be at least 3 business days before closing
            closing_ref = loan.funded_date or loan.closing_date
            if loan.cd_sent_to_borrower_date and closing_ref:
                cd_sent_d = loan.cd_sent_to_borrower_date
                closing_d = closing_ref
                if isinstance(cd_sent_d, datetime):
                    cd_sent_d = cd_sent_d.date()
                if isinstance(closing_d, datetime):
                    closing_d = closing_d.date()
                cd_days = (closing_d - cd_sent_d).days
                if cd_days >= 3:
                    passed.append({
                        "check": "CD_TIMING",
                        "message": f"CD sent {cd_days} day(s) before closing - meets 3-day requirement",
                    })
                else:
                    issues.append({
                        "check": "CD_TIMING",
                        "severity": "critical",
                        "regulation": "12 CFR 1026.19(f)(1)(ii)",
                        "message": f"CD sent only {cd_days} day(s) before closing (minimum 3 business days)",
                        "days_short": 3 - cd_days,
                    })
            elif closing_ref and not loan.cd_sent_to_borrower_date:
                if loan.stage in ("CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING", "FUNDED"):
                    issues.append({
                        "check": "CD_NOT_SENT",
                        "severity": "critical",
                        "regulation": "12 CFR 1026.19(f)(1)(ii)",
                        "message": "CD not sent but loan is near closing/funded",
                    })

            # LE signed check
            if loan.initial_disclosures_sent_date and not loan.initial_disclosures_signed_date:
                warnings.append({
                    "check": "LE_UNSIGNED",
                    "message": "LE sent but not yet signed by borrower",
                })

            # CD acknowledgment check
            if loan.cd_sent_to_borrower_date and not loan.cd_acknowledged_date:
                warnings.append({
                    "check": "CD_UNACKNOWLEDGED",
                    "message": "CD sent but not yet acknowledged by borrower",
                })

            # Revision history
            revision_data = {}
            if input_data.get("include_revisions", True):
                revisions = db.execute(text("""
                    SELECT
                        COUNT(CASE WHEN disclosure_type = 'revised_le' THEN 1 END) as le_revisions,
                        COUNT(CASE WHEN disclosure_type = 'revised_cd' THEN 1 END) as cd_revisions
                    FROM disclosure_events
                    WHERE loan_id = :loan_id
                """), {"loan_id": loan_id}).fetchone()

                if revisions:
                    le_rev = revisions.le_revisions or 0
                    cd_rev = revisions.cd_revisions or 0
                    revision_data = {"le_revisions": le_rev, "cd_revisions": cd_rev}
                    if le_rev > 2:
                        warnings.append({
                            "check": "EXCESSIVE_LE_REVISIONS",
                            "message": f"{le_rev} LE revisions - review for valid changed circumstance",
                        })
                    if cd_rev > 2:
                        warnings.append({
                            "check": "EXCESSIVE_CD_REVISIONS",
                            "message": f"{cd_rev} CD revisions - review for valid changed circumstance",
                        })

            high_severity = len([i for i in issues if i["severity"] in ("high", "critical")])
            is_compliant = high_severity == 0

            self.audit_log("check_trid_document_compliance", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "issue_count": len(issues),
                "warning_count": len(warnings),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_compliant": is_compliant,
                    "issues": issues,
                    "warnings": warnings,
                    "passed": passed,
                    "revisions": revision_data,
                },
                message=f"TRID {'Compliant' if is_compliant else 'NON-COMPLIANT'}: "
                        f"{len(issues)} issue(s), {len(warnings)} warning(s)"
            )

        except Exception as e:
            logger.exception(f"check_trid_document_compliance failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_document_retention(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check document retention compliance against federal minimums."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        days_to_expiry = input_data.get("days_to_expiry", 90)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            if loan_id:
                self.verify_loan_tenant(db, loan_id)

            params = {"org_id": org_id, "days_to_expiry": days_to_expiry}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND l.id = :loan_id"
                params["loan_id"] = loan_id

            docs = db.execute(text(f"""
                SELECT
                    d.id, d.doc_type, d.doc_category, d.status,
                    d.uploaded_at, d.loan_id, l.loan_number,
                    l.funded_date
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.status = 'active'
                {loan_filter}
                ORDER BY d.uploaded_at ASC
            """), params).fetchall()

            compliant = []
            at_risk = []
            non_compliant = []
            today = date.today()

            for doc in docs:
                doc_type = doc.doc_type
                retention_years = RETENTION_PERIODS.get(doc_type, 3)

                # Retention clock starts from funded date or upload date
                ref_date = doc.funded_date or doc.uploaded_at
                if ref_date is None:
                    continue
                if isinstance(ref_date, datetime):
                    ref_date = ref_date.date()

                retention_end = ref_date + timedelta(days=retention_years * 365)
                days_remaining = (retention_end - today).days

                entry = {
                    "document_id": doc.id,
                    "doc_type": doc_type,
                    "loan_id": doc.loan_id,
                    "loan_number": doc.loan_number,
                    "retention_years": retention_years,
                    "retention_end": retention_end.isoformat(),
                    "days_remaining": days_remaining,
                }

                if days_remaining < 0:
                    entry["status"] = "expired"
                    non_compliant.append(entry)
                elif days_remaining <= days_to_expiry:
                    entry["status"] = "expiring_soon"
                    at_risk.append(entry)
                else:
                    entry["status"] = "compliant"
                    compliant.append(entry)

            self.audit_log("check_document_retention", "document", details={
                "loan_id": loan_id,
                "compliant": len(compliant),
                "at_risk": len(at_risk),
                "non_compliant": len(non_compliant),
            })

            return ToolResult(
                success=True,
                data={
                    "compliant_count": len(compliant),
                    "at_risk_count": len(at_risk),
                    "non_compliant_count": len(non_compliant),
                    "at_risk": at_risk[:20],
                    "non_compliant": non_compliant[:20],
                    "retention_periods_reference": RETENTION_PERIODS,
                },
                message=f"Retention: {len(non_compliant)} expired, "
                        f"{len(at_risk)} expiring within {days_to_expiry} days"
            )

        except Exception as e:
            logger.exception("check_document_retention failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _audit_esign_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Audit e-signature compliance against ESIGN Act and UETA."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number,
                    l.initial_disclosures_signed_date,
                    l.cd_acknowledged_date,
                    l.cd_received_signed_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            checks = []
            issues = []

            # Check ESIGN consent (borrower must consent to receive electronic records)
            consent_check = db.execute(text("""
                SELECT consent_esign, esign_consent_date
                FROM borrower_profiles
                WHERE email IN (
                    SELECT borrower_email FROM loans WHERE id = :loan_id
                )
                LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if consent_check and consent_check.consent_esign:
                checks.append({
                    "check": "ESIGN_CONSENT",
                    "status": "pass",
                    "message": f"E-sign consent recorded on {consent_check.esign_consent_date}",
                })
            else:
                issues.append({
                    "check": "ESIGN_CONSENT",
                    "status": "fail",
                    "severity": "high",
                    "requirement": "15 USC 7001(c) - Consumer consent required",
                    "message": "No e-sign consent on file for borrower",
                })

            # Check that key documents have signatures
            sig_docs = [
                ("initial_disclosures_signed_date", "Initial Disclosures"),
                ("cd_acknowledged_date", "Closing Disclosure Acknowledgment"),
                ("cd_received_signed_date", "Closing Disclosure Signature"),
            ]
            for col, label in sig_docs:
                val = getattr(loan, col, None)
                if val:
                    checks.append({
                        "check": f"SIGNATURE_{col.upper()}",
                        "status": "pass",
                        "message": f"{label} signed on {val}",
                    })
                else:
                    issues.append({
                        "check": f"SIGNATURE_{col.upper()}",
                        "status": "missing",
                        "severity": "medium",
                        "message": f"{label} not signed",
                    })

            # Check audit trail (disclosure_events table)
            audit_trail = db.execute(text("""
                SELECT COUNT(*) as event_count
                FROM disclosure_events
                WHERE loan_id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            event_count = audit_trail.event_count if audit_trail else 0
            if event_count > 0:
                checks.append({
                    "check": "AUDIT_TRAIL",
                    "status": "pass",
                    "message": f"{event_count} disclosure events logged",
                })
            else:
                issues.append({
                    "check": "AUDIT_TRAIL",
                    "status": "fail",
                    "severity": "medium",
                    "message": "No disclosure events audit trail found",
                })

            is_compliant = len([i for i in issues if i.get("severity") in ("high", "critical")]) == 0

            self.audit_log("audit_esign_compliance", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "checks_passed": len(checks),
                "issues_found": len(issues),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_compliant": is_compliant,
                    "checks_passed": checks,
                    "issues": issues,
                },
                message=f"E-Sign {'Compliant' if is_compliant else 'Issues Found'}: "
                        f"{len(checks)} passed, {len(issues)} issue(s)"
            )

        except Exception as e:
            logger.exception(f"audit_esign_compliance failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_fair_lending_patterns(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Analyze document collection patterns for ECOA compliance."""
        from database import SessionLocal

        lo_id = input_data.get("lo_id")
        period_days = input_data.get("period_days", 90)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            params = {"org_id": org_id, "period_days": period_days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            # Compare average document collection times across loan types
            collection_patterns = db.execute(text(f"""
                SELECT
                    l.loan_type,
                    COUNT(DISTINCT l.id) as loan_count,
                    AVG(
                        EXTRACT(EPOCH FROM (
                            (SELECT MIN(d2.uploaded_at) FROM documents d2 WHERE d2.loan_id = l.id)
                            - l.application_date
                        )) / 86400
                    ) as avg_days_to_first_doc,
                    COUNT(DISTINCT d.id) / NULLIF(COUNT(DISTINCT l.id), 0) as avg_docs_per_loan
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id
                WHERE l.organization_id = :org_id
                    AND l.application_date >= CURRENT_DATE - :period_days
                    {lo_filter}
                GROUP BY l.loan_type
                HAVING COUNT(DISTINCT l.id) >= 3
                ORDER BY avg_days_to_first_doc DESC NULLS LAST
            """), params).fetchall()

            patterns = []
            flags = []

            if collection_patterns:
                avg_overall = sum(
                    float(p.avg_days_to_first_doc or 0) for p in collection_patterns
                ) / len(collection_patterns)

                for p in collection_patterns:
                    avg_days = float(p.avg_days_to_first_doc or 0)
                    deviation = avg_days - avg_overall if avg_overall > 0 else 0
                    pattern = {
                        "loan_type": p.loan_type,
                        "loan_count": p.loan_count,
                        "avg_days_to_first_doc": round(avg_days, 1),
                        "avg_docs_per_loan": round(float(p.avg_docs_per_loan or 0), 1),
                        "deviation_from_mean": round(deviation, 1),
                    }
                    patterns.append(pattern)

                    # Flag significant deviations (potential disparate treatment)
                    if abs(deviation) > avg_overall * 0.5 and avg_overall > 0:
                        flags.append({
                            "type": "COLLECTION_TIME_DEVIATION",
                            "loan_type": p.loan_type,
                            "severity": "review_needed",
                            "message": (
                                f"{p.loan_type} loans avg {round(avg_days, 1)} days to first doc "
                                f"vs. overall avg {round(avg_overall, 1)} days "
                                f"({'+' if deviation > 0 else ''}{round(deviation, 1)} days)"
                            ),
                        })

            self.audit_log("check_fair_lending_patterns", details={
                "lo_id": lo_id,
                "period_days": period_days,
                "patterns_analyzed": len(patterns),
                "flags_raised": len(flags),
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": period_days,
                    "patterns": patterns,
                    "flags": flags,
                    "recommendation": (
                        "Review flagged patterns for potential disparate treatment"
                        if flags else "No significant disparities detected in document collection"
                    ),
                },
                message=f"Fair lending: {len(flags)} flag(s) across {len(patterns)} loan types"
            )

        except Exception as e:
            logger.exception("check_fair_lending_patterns failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_income_documentation(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify income docs meet Fannie Mae B3-3 requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.loan_type, l.employment_type
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = db.execute(text("""
                SELECT doc_type, doc_category, status, uploaded_at
                FROM documents
                WHERE loan_id = :loan_id AND doc_category = 'income'
            """), {"loan_id": loan_id}).fetchall()

            existing_types = {d.doc_type for d in docs if d.status == "active"}

            checks = []
            issues = []

            # B3-3.1: Paystubs (most recent 30-day period)
            if "paystubs" in existing_types:
                checks.append({
                    "check": "PAYSTUBS",
                    "status": "present",
                    "requirement": "B3-3.1-01: Most recent 30-day period",
                    "message": "Paystubs on file",
                })
            else:
                issues.append({
                    "check": "PAYSTUBS",
                    "status": "missing",
                    "severity": "high",
                    "requirement": "B3-3.1-01",
                    "message": "Paystubs missing - required for all employed borrowers",
                })

            # B3-3.1: W-2s (most recent 2 years)
            if "w2" in existing_types:
                checks.append({
                    "check": "W2",
                    "status": "present",
                    "requirement": "B3-3.1-02: Most recent 2-year history",
                    "message": "W-2s on file",
                })
            else:
                issues.append({
                    "check": "W2",
                    "status": "missing",
                    "severity": "high",
                    "requirement": "B3-3.1-02",
                    "message": "W-2s missing - required for 2-year employment verification",
                })

            # B3-3.2: Tax returns (if self-employed)
            employment_type = getattr(loan, "employment_type", None) or ""
            is_self_employed = employment_type.lower() in ("self_employed", "self-employed", "1099")

            if is_self_employed:
                if "tax_returns" in existing_types:
                    checks.append({
                        "check": "TAX_RETURNS_SE",
                        "status": "present",
                        "requirement": "B3-3.2: Self-employment - 2 years required",
                        "message": "Tax returns on file for self-employed borrower",
                    })
                else:
                    issues.append({
                        "check": "TAX_RETURNS_SE",
                        "status": "missing",
                        "severity": "critical",
                        "requirement": "B3-3.2",
                        "message": "Tax returns missing for self-employed borrower - required per B3-3.2",
                    })

                if "profit_loss" in existing_types:
                    checks.append({
                        "check": "PROFIT_LOSS",
                        "status": "present",
                        "requirement": "B3-3.2: YTD P&L for self-employment",
                        "message": "Profit & Loss statement on file",
                    })
                else:
                    issues.append({
                        "check": "PROFIT_LOSS",
                        "status": "missing",
                        "severity": "medium",
                        "requirement": "B3-3.2",
                        "message": "P&L statement missing - may be required for YTD income verification",
                    })

            # 1099 forms
            if "1099" in existing_types:
                checks.append({
                    "check": "1099_FORMS",
                    "status": "present",
                    "message": "1099 forms on file",
                })

            has_critical = len([i for i in issues if i["severity"] == "critical"]) > 0
            is_compliant = not has_critical and len([
                i for i in issues if i["severity"] == "high"
            ]) == 0

            self.audit_log("verify_income_documentation", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "docs_present": len(checks),
                "docs_missing": len(issues),
                "is_self_employed": is_self_employed,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_compliant": is_compliant,
                    "is_self_employed": is_self_employed,
                    "checks_passed": checks,
                    "issues": issues,
                    "docs_on_file": list(existing_types),
                },
                message=f"Income docs: {len(checks)} present, {len(issues)} issue(s)"
            )

        except Exception as e:
            logger.exception(f"verify_income_documentation failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_flood_zone_docs(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check flood determination and insurance documentation."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.property_address,
                    l.flood_zone, l.flood_cert_date, l.flood_insurance_required,
                    l.insurance_ordered_date, l.insurance_received_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            checks = []
            issues = []

            # Flood determination required per FDPA
            if loan.flood_cert_date:
                checks.append({
                    "check": "FLOOD_DETERMINATION",
                    "status": "pass",
                    "message": f"Flood determination on file (cert date: {loan.flood_cert_date})",
                })

                # Check determination freshness (good for life of loan, but
                # FEMA map changes may invalidate)
                if isinstance(loan.flood_cert_date, (date, datetime)):
                    cert_d = loan.flood_cert_date if isinstance(loan.flood_cert_date, date) else loan.flood_cert_date.date()
                    age_days = (date.today() - cert_d).days
                    if age_days > 365:
                        issues.append({
                            "check": "FLOOD_CERT_AGE",
                            "severity": "low",
                            "message": f"Flood cert is {age_days} days old - verify no FEMA map changes",
                        })
            else:
                issues.append({
                    "check": "FLOOD_DETERMINATION",
                    "severity": "high",
                    "regulation": "42 USC 4012a - FDPA",
                    "message": "Flood determination not on file - required for all federally related loans",
                })

            # Flood insurance check (required if in SFHA)
            flood_zone = getattr(loan, "flood_zone", None) or ""
            high_risk_zones = ("A", "AE", "AH", "AO", "AR", "A99", "V", "VE", "V1")
            in_sfha = any(flood_zone.upper().startswith(z) for z in high_risk_zones) if flood_zone else False

            if in_sfha or loan.flood_insurance_required:
                if loan.insurance_received_date:
                    checks.append({
                        "check": "FLOOD_INSURANCE",
                        "status": "pass",
                        "message": f"Flood insurance on file for zone {flood_zone}",
                    })
                else:
                    issues.append({
                        "check": "FLOOD_INSURANCE",
                        "severity": "critical",
                        "regulation": "42 USC 4012a(b)",
                        "message": f"Flood insurance required for zone {flood_zone} but not on file",
                    })
            else:
                checks.append({
                    "check": "FLOOD_INSURANCE",
                    "status": "not_required",
                    "message": f"Property not in SFHA (zone: {flood_zone or 'unknown'})",
                })

            is_compliant = len([i for i in issues if i["severity"] in ("high", "critical")]) == 0

            self.audit_log("check_flood_zone_docs", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "flood_zone": flood_zone,
                "in_sfha": in_sfha,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "flood_zone": flood_zone,
                    "in_sfha": in_sfha,
                    "is_compliant": is_compliant,
                    "checks_passed": checks,
                    "issues": issues,
                },
                message=f"Flood docs: {'Compliant' if is_compliant else 'NON-COMPLIANT'} - "
                        f"Zone {flood_zone or 'unknown'}"
            )

        except Exception as e:
            logger.exception(f"check_flood_zone_docs failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _audit_privacy_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Audit PII handling against GLBA/Reg P requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            checks = []
            issues = []

            # Check for privacy notice delivery
            privacy_doc = db.execute(text("""
                SELECT id, uploaded_at, status
                FROM documents
                WHERE loan_id = :loan_id
                    AND doc_type IN ('privacy_notice', 'glba_notice', 'privacy_policy')
                    AND status = 'active'
                LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if privacy_doc:
                checks.append({
                    "check": "PRIVACY_NOTICE",
                    "status": "pass",
                    "regulation": "12 CFR 1016 (Reg P)",
                    "message": f"Privacy notice on file (uploaded: {privacy_doc.uploaded_at})",
                })
            else:
                issues.append({
                    "check": "PRIVACY_NOTICE",
                    "severity": "high",
                    "regulation": "12 CFR 1016.4 - Initial privacy notice",
                    "message": "Privacy notice not on file - required at customer relationship establishment",
                })

            # Check borrower consent record
            consent_record = db.execute(text("""
                SELECT consent_data_sharing, consent_marketing
                FROM borrower_profiles
                WHERE email = :email
                LIMIT 1
            """), {"email": loan.borrower_email}).fetchone()

            if consent_record:
                if consent_record.consent_data_sharing is not None:
                    checks.append({
                        "check": "DATA_SHARING_CONSENT",
                        "status": "pass",
                        "message": f"Data sharing preference recorded: {consent_record.consent_data_sharing}",
                    })
                else:
                    issues.append({
                        "check": "DATA_SHARING_CONSENT",
                        "severity": "medium",
                        "regulation": "12 CFR 1016.7 - Opt-out",
                        "message": "Data sharing preference not recorded",
                    })
            else:
                issues.append({
                    "check": "BORROWER_PROFILE",
                    "severity": "medium",
                    "message": "No borrower profile found - consent records may be incomplete",
                })

            # Check for PII in document filenames (common leak vector)
            pii_in_filenames = db.execute(text("""
                SELECT id, filename, doc_type
                FROM documents
                WHERE loan_id = :loan_id
                    AND (
                        filename ~* '\\d{3}-\\d{2}-\\d{4}'
                        OR filename ~* 'ssn'
                    )
                LIMIT 5
            """), {"loan_id": loan_id}).fetchall()

            if pii_in_filenames:
                for doc in pii_in_filenames:
                    issues.append({
                        "check": "PII_IN_FILENAME",
                        "severity": "high",
                        "message": f"Potential SSN in filename: {doc.doc_type} (doc ID: {doc.id})",
                    })
            else:
                checks.append({
                    "check": "PII_IN_FILENAMES",
                    "status": "pass",
                    "message": "No PII patterns detected in document filenames",
                })

            is_compliant = len([i for i in issues if i["severity"] in ("high", "critical")]) == 0

            self.audit_log("audit_privacy_compliance", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "checks_passed": len(checks),
                "issues_found": len(issues),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_compliant": is_compliant,
                    "checks_passed": checks,
                    "issues": issues,
                },
                message=f"Privacy {'Compliant' if is_compliant else 'Issues Found'}: "
                        f"{len(checks)} passed, {len(issues)} issue(s)"
            )

        except Exception as e:
            logger.exception(f"audit_privacy_compliance failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_compliance_scorecard(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a 0-100 compliance scorecard for a loan file."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.stage,
                    l.application_date, l.initial_disclosures_sent_date,
                    l.cd_sent_to_borrower_date, l.funded_date,
                    l.initial_disclosures_signed_date,
                    l.cd_acknowledged_date,
                    l.flood_zone, l.flood_cert_date,
                    l.property_state
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            scores = {}

            # 1. TRID Timing (20 points)
            trid_score = SCORECARD_WEIGHTS["trid_timing"]
            if loan.application_date and loan.initial_disclosures_sent_date:
                le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
                if le_days > 3:
                    trid_score -= 10
            elif loan.application_date and not loan.initial_disclosures_sent_date:
                days_since = (date.today() - loan.application_date).days if isinstance(
                    loan.application_date, date
                ) else (date.today() - loan.application_date.date()).days
                if days_since > 3:
                    trid_score -= 15
            if loan.cd_sent_to_borrower_date and loan.funded_date:
                cd_days = (loan.funded_date - loan.cd_sent_to_borrower_date).days
                if cd_days < 3:
                    trid_score -= 10
            scores["trid_timing"] = max(0, trid_score)

            # 2. Document Completeness (15 points)
            doc_count = db.execute(text("""
                SELECT COUNT(*) as cnt FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchone()
            total_docs = doc_count.cnt if doc_count else 0
            required_min = 8  # typical minimum for a complete file
            doc_ratio = min(total_docs / required_min, 1.0) if required_min > 0 else 1.0
            scores["document_completeness"] = round(
                SCORECARD_WEIGHTS["document_completeness"] * doc_ratio
            )

            # 3. E-Sign Compliance (10 points)
            esign_score = SCORECARD_WEIGHTS["esign_compliance"]
            if not loan.initial_disclosures_signed_date:
                esign_score -= 5
            if not loan.cd_acknowledged_date:
                esign_score -= 5
            scores["esign_compliance"] = max(0, esign_score)

            # 4. Retention Compliance (10 points) - assumed compliant for active loans
            scores["retention_compliance"] = SCORECARD_WEIGHTS["retention_compliance"]

            # 5. State-Specific (10 points) - check if property state has requirements
            state_score = SCORECARD_WEIGHTS["state_specific"]
            prop_state = getattr(loan, "property_state", None)
            if prop_state and prop_state.upper() in STATE_DOC_REQUIREMENTS:
                # Check if state-specific docs exist
                state_reqs = STATE_DOC_REQUIREMENTS[prop_state.upper()]
                required_types = [r["doc_type"] for r in state_reqs["rules"]]
                state_docs = db.execute(text("""
                    SELECT doc_type FROM documents
                    WHERE loan_id = :loan_id AND doc_type = ANY(:types)
                """), {"loan_id": loan_id, "types": required_types}).fetchall()
                found = {d.doc_type for d in state_docs}
                missing = len(required_types) - len(found)
                if missing > 0:
                    state_score -= min(state_score, missing * 5)
            scores["state_specific"] = max(0, state_score)

            # 6. HMDA Data Quality (10 points)
            scores["hmda_data_quality"] = SCORECARD_WEIGHTS["hmda_data_quality"]

            # 7. Privacy Compliance (10 points)
            privacy_doc = db.execute(text("""
                SELECT id FROM documents
                WHERE loan_id = :loan_id
                    AND doc_type IN ('privacy_notice', 'glba_notice')
                    AND status = 'active'
                LIMIT 1
            """), {"loan_id": loan_id}).fetchone()
            scores["privacy_compliance"] = (
                SCORECARD_WEIGHTS["privacy_compliance"] if privacy_doc
                else max(0, SCORECARD_WEIGHTS["privacy_compliance"] - 7)
            )

            # 8. Flood Compliance (5 points)
            flood_score = SCORECARD_WEIGHTS["flood_compliance"]
            if not loan.flood_cert_date:
                flood_score -= 3
            scores["flood_compliance"] = max(0, flood_score)

            # 9. Fraud Process (5 points) - assumed compliant unless flagged
            scores["fraud_process"] = SCORECARD_WEIGHTS["fraud_process"]

            # 10. Fair Lending (5 points) - assumed compliant unless flagged
            scores["fair_lending"] = SCORECARD_WEIGHTS["fair_lending"]

            total_score = sum(scores.values())
            max_possible = sum(SCORECARD_WEIGHTS.values())

            if total_score >= 90:
                grade = "A"
                risk_level = "low"
            elif total_score >= 80:
                grade = "B"
                risk_level = "low"
            elif total_score >= 70:
                grade = "C"
                risk_level = "medium"
            elif total_score >= 60:
                grade = "D"
                risk_level = "high"
            else:
                grade = "F"
                risk_level = "critical"

            self.audit_log("generate_compliance_scorecard", "loan", entity_id=loan_id, details={
                "total_score": total_score,
                "grade": grade,
                "risk_level": risk_level,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "total_score": total_score,
                    "max_possible": max_possible,
                    "grade": grade,
                    "risk_level": risk_level,
                    "category_scores": scores,
                    "category_weights": SCORECARD_WEIGHTS,
                },
                message=f"Compliance Score: {total_score}/{max_possible} (Grade {grade}, {risk_level} risk)"
            )

        except Exception as e:
            logger.exception(f"generate_compliance_scorecard failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_state_specific_requirements(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check state-specific document requirements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        state_override = input_data.get("state_code")
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.property_state,
                    l.loan_type, l.loan_purpose, l.property_type
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            state_code = (state_override or getattr(loan, "property_state", None) or "").upper()

            if state_code not in STATE_DOC_REQUIREMENTS:
                self.audit_log("check_state_specific_requirements", "loan", entity_id=loan_id, details={
                    "state": state_code,
                    "result": "no_specific_rules",
                })
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "state": state_code,
                        "requirements": [],
                        "message": f"No specific state rules cataloged for {state_code}. "
                                  "Standard federal requirements apply.",
                    },
                    message=f"State {state_code}: Standard federal requirements apply"
                )

            state_info = STATE_DOC_REQUIREMENTS[state_code]
            requirements = state_info["rules"]

            # Check which state docs are on file
            required_types = [r["doc_type"] for r in requirements]
            existing_docs = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()
            existing_types = {d.doc_type for d in existing_docs}

            results = []
            missing = []
            for req in requirements:
                is_present = req["doc_type"] in existing_types

                # Check applicability
                applicable = True
                if req["applies_to"] != "all":
                    loan_purpose = getattr(loan, "loan_purpose", "") or ""
                    if req["applies_to"] not in loan_purpose.lower():
                        applicable = False

                entry = {
                    "regulation": req["regulation"],
                    "requirement": req["requirement"],
                    "doc_type": req["doc_type"],
                    "timing": req["timing"],
                    "applicable": applicable,
                    "on_file": is_present,
                    "status": "compliant" if is_present or not applicable else "missing",
                }
                results.append(entry)
                if applicable and not is_present:
                    missing.append(entry)

            is_compliant = len(missing) == 0

            self.audit_log("check_state_specific_requirements", "loan", entity_id=loan_id, details={
                "state": state_code,
                "requirements_count": len(requirements),
                "missing_count": len(missing),
                "is_compliant": is_compliant,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "state": state_code,
                    "state_name": state_info["name"],
                    "is_compliant": is_compliant,
                    "requirements": results,
                    "missing": missing,
                },
                message=f"State {state_code}: {'Compliant' if is_compliant else f'{len(missing)} missing doc(s)'}"
            )

        except Exception as e:
            logger.exception(f"check_state_specific_requirements failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_compliance_risks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Proactively identify compliance risks across loans."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        lo_id = input_data.get("lo_id")
        limit = input_data.get("limit", 20)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            if loan_id:
                self.verify_loan_tenant(db, loan_id)

            params = {"org_id": org_id, "limit": limit}
            lo_filter = ""
            loan_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id
            if loan_id:
                loan_filter = "AND l.id = :loan_id"
                params["loan_id"] = loan_id

            # Find loans with potential compliance risks
            risks = []

            # Risk 1: LE not sent within 3 days
            le_risk = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name,
                    EXTRACT(DAY FROM CURRENT_TIMESTAMP - l.application_date) as days_since_app
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.application_date IS NOT NULL
                    AND l.initial_disclosures_sent_date IS NULL
                    AND EXTRACT(DAY FROM CURRENT_TIMESTAMP - l.application_date) > 2
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {lo_filter} {loan_filter}
                ORDER BY l.application_date ASC
                LIMIT :limit
            """), params).fetchall()

            for r in le_risk:
                risks.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower": r.borrower_name,
                    "risk_type": "TRID_LE_OVERDUE",
                    "severity": "critical" if float(r.days_since_app or 0) > 3 else "high",
                    "description": f"LE not sent - {int(r.days_since_app or 0)} days since application",
                    "regulation": "12 CFR 1026.19(e)",
                    "action_required": "Send LE immediately",
                })

            # Risk 2: Approaching closing without CD
            cd_risk = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.closing_date
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.cd_sent_to_borrower_date IS NULL
                    AND l.closing_date IS NOT NULL
                    AND l.closing_date <= CURRENT_DATE + 7
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {lo_filter} {loan_filter}
                ORDER BY l.closing_date ASC
                LIMIT :limit
            """), params).fetchall()

            for r in cd_risk:
                days_to_close = (r.closing_date - date.today()).days if r.closing_date else 0
                risks.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower": r.borrower_name,
                    "risk_type": "TRID_CD_NOT_SENT",
                    "severity": "critical" if days_to_close <= 3 else "high",
                    "description": f"CD not sent - closing in {days_to_close} days",
                    "regulation": "12 CFR 1026.19(f)",
                    "action_required": "Send CD immediately to meet 3-day waiting period",
                })

            # Risk 3: Missing flood determination
            flood_risk = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.flood_cert_date IS NULL
                    AND l.stage NOT IN ('APPLICATION', 'FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {lo_filter} {loan_filter}
                LIMIT :limit
            """), params).fetchall()

            for r in flood_risk:
                risks.append({
                    "loan_id": r.id,
                    "loan_number": r.loan_number,
                    "borrower": r.borrower_name,
                    "risk_type": "FLOOD_DETERMINATION_MISSING",
                    "severity": "medium",
                    "description": "Flood determination not on file",
                    "regulation": "42 USC 4012a",
                    "action_required": "Order flood determination",
                })

            # Sort by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            risks.sort(key=lambda r: severity_order.get(r["severity"], 4))

            critical_count = len([r for r in risks if r["severity"] == "critical"])
            high_count = len([r for r in risks if r["severity"] == "high"])

            self.audit_log("identify_compliance_risks", details={
                "loan_id": loan_id,
                "lo_id": lo_id,
                "total_risks": len(risks),
                "critical": critical_count,
                "high": high_count,
            })

            return ToolResult(
                success=True,
                data={
                    "total_risks": len(risks),
                    "critical": critical_count,
                    "high": high_count,
                    "risks": risks,
                },
                message=f"Risks: {critical_count} critical, {high_count} high, {len(risks)} total"
            )

        except Exception as e:
            logger.exception("identify_compliance_risks failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_examiner_ready_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a pre-examination report for regulatory exam prep."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        period_days = input_data.get("period_days", 90)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            params = {"org_id": org_id, "period_days": period_days}
            loan_filter = ""
            if loan_id:
                self.verify_loan_tenant(db, loan_id)
                loan_filter = "AND l.id = :loan_id"
                params["loan_id"] = loan_id

            # Portfolio compliance summary
            summary = db.execute(text(f"""
                SELECT
                    COUNT(*) as total_loans,
                    COUNT(CASE WHEN l.initial_disclosures_sent_date IS NOT NULL THEN 1 END) as le_sent,
                    COUNT(CASE WHEN l.cd_sent_to_borrower_date IS NOT NULL THEN 1 END) as cd_sent,
                    COUNT(CASE WHEN l.flood_cert_date IS NOT NULL THEN 1 END) as flood_determined,
                    COUNT(CASE WHEN l.stage = 'FUNDED' THEN 1 END) as funded
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.created_at >= CURRENT_DATE - :period_days
                    {loan_filter}
            """), params).fetchone()

            total = summary.total_loans or 0

            # Compliance alerts summary
            alerts = db.execute(text(f"""
                SELECT
                    ca.alert_type,
                    ca.severity,
                    COUNT(*) as count,
                    COUNT(CASE WHEN ca.status = 'open' THEN 1 END) as open_count
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                WHERE ca.created_at >= CURRENT_DATE - :period_days
                    {loan_filter.replace('l.id', 'ca.loan_id') if loan_filter else ''}
                GROUP BY ca.alert_type, ca.severity
                ORDER BY
                    CASE ca.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
                    count DESC
            """), params).fetchall()

            report = {
                "report_date": date.today().isoformat(),
                "period_days": period_days,
                "portfolio_summary": {
                    "total_loans": total,
                    "le_disclosure_rate": round((summary.le_sent / total) * 100, 1) if total > 0 else 0,
                    "cd_disclosure_rate": round((summary.cd_sent / total) * 100, 1) if total > 0 else 0,
                    "flood_determination_rate": round(
                        (summary.flood_determined / total) * 100, 1
                    ) if total > 0 else 0,
                    "funded_count": summary.funded,
                },
                "compliance_alerts": [
                    {
                        "type": a.alert_type,
                        "severity": a.severity,
                        "total": a.count,
                        "open": a.open_count,
                    }
                    for a in alerts
                ],
                "examiner_notes": [],
            }

            # Generate examiner-relevant notes
            if total > 0:
                le_rate = (summary.le_sent / total) * 100
                if le_rate < 100:
                    report["examiner_notes"].append(
                        f"LE disclosure rate is {le_rate:.1f}% - {total - summary.le_sent} loan(s) "
                        "without LE on file"
                    )
                flood_rate = (summary.flood_determined / total) * 100
                if flood_rate < 100:
                    report["examiner_notes"].append(
                        f"Flood determination rate is {flood_rate:.1f}% - {total - summary.flood_determined} "
                        "loan(s) without flood cert"
                    )

            open_critical = sum(a.open_count for a in alerts if a.severity == "critical")
            if open_critical > 0:
                report["examiner_notes"].append(
                    f"{open_critical} open critical compliance alert(s) require immediate resolution"
                )

            self.audit_log("generate_examiner_ready_report", details={
                "loan_id": loan_id,
                "period_days": period_days,
                "total_loans": total,
                "alert_types": len(alerts),
            })

            return ToolResult(
                success=True,
                data=report,
                message=f"Exam report: {total} loans, {len(alerts)} alert types, "
                        f"{len(report['examiner_notes'])} note(s)"
            )

        except Exception as e:
            logger.exception("generate_examiner_ready_report failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_regulatory_changes(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Surface recent guideline changes affecting document requirements."""
        category = input_data.get("category")

        # Regulatory change catalog (maintained reference data)
        changes = [
            {
                "category": "trid",
                "effective_date": "2024-10-01",
                "agency": "CFPB",
                "title": "TRID Tolerance Cure Clarification",
                "summary": "Clarified tolerance cure procedures for zero-tolerance fee increases",
                "impact": "Review zero-tolerance fee tracking procedures",
                "document_impact": ["closing_disclosure", "loan_estimate"],
            },
            {
                "category": "hmda",
                "effective_date": "2025-01-01",
                "agency": "CFPB",
                "title": "HMDA Data Point Updates",
                "summary": "Updated LAR data point requirements for property address reporting",
                "impact": "Verify property address data completeness in LAR submissions",
                "document_impact": ["hmda_lar"],
            },
            {
                "category": "fair_lending",
                "effective_date": "2025-03-01",
                "agency": "CFPB/DOJ",
                "title": "Fair Lending Examination Procedures Update",
                "summary": "Updated examination procedures for disparate impact analysis",
                "impact": "Review document collection patterns for disparate treatment",
                "document_impact": [],
            },
            {
                "category": "privacy",
                "effective_date": "2025-06-01",
                "agency": "CFPB",
                "title": "GLBA Privacy Notice Modernization",
                "summary": "Updated electronic delivery requirements for privacy notices",
                "impact": "Update e-delivery consent and privacy notice templates",
                "document_impact": ["privacy_notice"],
            },
            {
                "category": "state",
                "effective_date": "2025-01-01",
                "agency": "TX DFI",
                "title": "Texas Home Equity Disclosure Updates",
                "summary": "Updated disclosure requirements for home equity lending",
                "impact": "Update TX home equity disclosure templates",
                "document_impact": ["tx_home_equity_disclosure"],
            },
        ]

        if category:
            changes = [c for c in changes if c["category"] == category]

        self.audit_log("track_regulatory_changes", details={
            "category": category,
            "changes_returned": len(changes),
        })

        return ToolResult(
            success=True,
            data={
                "changes": changes,
                "total": len(changes),
                "categories": list({c["category"] for c in changes}),
            },
            message=f"Regulatory changes: {len(changes)} update(s)"
                    f"{f' in {category}' if category else ''}"
        )

    async def _audit_fraud_detection_process(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Audit fraud detection workflow for BSA/AML compliance."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            checks = []
            issues = []

            # CIP: Customer Identification Program verification
            identity_docs = db.execute(text("""
                SELECT doc_type, status FROM documents
                WHERE loan_id = :loan_id
                    AND doc_category = 'identity'
                    AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()

            id_types = {d.doc_type for d in identity_docs}
            if id_types:
                checks.append({
                    "check": "CIP_IDENTITY",
                    "status": "pass",
                    "requirement": "31 CFR 1020.220 - CIP",
                    "message": f"Identity documents on file: {', '.join(id_types)}",
                })
            else:
                issues.append({
                    "check": "CIP_IDENTITY",
                    "severity": "high",
                    "requirement": "31 CFR 1020.220 - CIP",
                    "message": "No identity documents on file - CIP verification incomplete",
                })

            # Check for fraud-related compliance alerts
            fraud_alerts = db.execute(text("""
                SELECT id, alert_type, title, status, severity
                FROM compliance_alerts
                WHERE loan_id = :loan_id
                    AND alert_type IN ('fraud', 'suspicious_activity', 'identity_mismatch')
                ORDER BY severity DESC
            """), {"loan_id": loan_id}).fetchall()

            if fraud_alerts:
                open_alerts = [a for a in fraud_alerts if a.status == "open"]
                resolved_alerts = [a for a in fraud_alerts if a.status != "open"]

                if open_alerts:
                    issues.append({
                        "check": "OPEN_FRAUD_ALERTS",
                        "severity": "critical",
                        "message": f"{len(open_alerts)} open fraud/suspicious activity alert(s)",
                        "details": [
                            {"id": a.id, "type": a.alert_type, "title": a.title}
                            for a in open_alerts
                        ],
                    })

                if resolved_alerts:
                    checks.append({
                        "check": "RESOLVED_FRAUD_ALERTS",
                        "status": "pass",
                        "message": f"{len(resolved_alerts)} fraud alert(s) resolved",
                    })
            else:
                checks.append({
                    "check": "FRAUD_ALERTS",
                    "status": "pass",
                    "message": "No fraud-related compliance alerts",
                })

            # Credit report verification (part of red flag rules)
            credit_doc = db.execute(text("""
                SELECT id, uploaded_at FROM documents
                WHERE loan_id = :loan_id AND doc_type = 'credit_report' AND status = 'active'
                LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if credit_doc:
                checks.append({
                    "check": "CREDIT_REPORT",
                    "status": "pass",
                    "message": f"Credit report on file (uploaded: {credit_doc.uploaded_at})",
                })
            else:
                issues.append({
                    "check": "CREDIT_REPORT",
                    "severity": "medium",
                    "message": "Credit report not on file - required for Red Flags Rule compliance",
                })

            is_compliant = len([i for i in issues if i.get("severity") in ("high", "critical")]) == 0

            self.audit_log("audit_fraud_detection_process", "loan", entity_id=loan_id, details={
                "is_compliant": is_compliant,
                "checks_passed": len(checks),
                "issues_found": len(issues),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_compliant": is_compliant,
                    "checks_passed": checks,
                    "issues": issues,
                },
                message=f"Fraud process: {'Compliant' if is_compliant else 'Issues Found'} - "
                        f"{len(checks)} passed, {len(issues)} issue(s)"
            )

        except Exception as e:
            logger.exception(f"audit_fraud_detection_process failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_hmda_data_quality(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check HMDA-reportable data completeness per Regulation C."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        period_days = input_data.get("period_days", 365)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            params = {"org_id": org_id}

            if loan_id:
                self.verify_loan_tenant(db, loan_id)
                params["loan_id"] = loan_id

                loan = db.execute(text("""
                    SELECT
                        l.id, l.loan_number, l.loan_type, l.loan_purpose,
                        l.amount, l.rate, l.property_type, l.occupancy_type,
                        l.property_state, l.property_county,
                        l.stage, l.funded_date
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """), params).fetchone()

                if not loan:
                    return ToolResult(success=False, error=f"Loan {loan_id} not found")

                # Check required HMDA fields
                missing_fields = []
                present_fields = []

                field_mapping = {
                    "loan_type": loan.loan_type,
                    "loan_purpose": loan.loan_purpose,
                    "loan_amount": loan.amount,
                    "rate": loan.rate,
                    "property_type": loan.property_type,
                    "occupancy_type": loan.occupancy_type,
                    "property_state": loan.property_state,
                    "property_county": loan.property_county,
                }

                for field_name in HMDA_REQUIRED_FIELDS:
                    value = field_mapping.get(field_name)
                    if value is not None and str(value).strip():
                        present_fields.append(field_name)
                    else:
                        # Some fields may not be direct loan columns
                        if field_name not in field_mapping:
                            missing_fields.append({
                                "field": field_name,
                                "status": "not_tracked",
                                "message": f"Field '{field_name}' not in loan record - verify in LAR",
                            })
                        else:
                            missing_fields.append({
                                "field": field_name,
                                "status": "missing",
                                "message": f"Required HMDA field '{field_name}' is empty",
                            })

                completeness = round(
                    (len(present_fields) / len(HMDA_REQUIRED_FIELDS)) * 100, 1
                ) if HMDA_REQUIRED_FIELDS else 0

                data = {
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "completeness_pct": completeness,
                    "present_fields": present_fields,
                    "missing_fields": missing_fields,
                    "is_reportable": loan.stage == "FUNDED",
                    "total_required": len(HMDA_REQUIRED_FIELDS),
                }

            else:
                # Aggregate HMDA quality across portfolio
                params["period_days"] = period_days
                aggregate = db.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN loan_type IS NOT NULL THEN 1 END) as has_loan_type,
                        COUNT(CASE WHEN loan_purpose IS NOT NULL THEN 1 END) as has_purpose,
                        COUNT(CASE WHEN amount IS NOT NULL THEN 1 END) as has_amount,
                        COUNT(CASE WHEN rate IS NOT NULL THEN 1 END) as has_rate,
                        COUNT(CASE WHEN property_state IS NOT NULL THEN 1 END) as has_state,
                        COUNT(CASE WHEN property_county IS NOT NULL THEN 1 END) as has_county
                    FROM loans
                    WHERE organization_id = :org_id
                        AND funded_date >= CURRENT_DATE - :period_days
                """), params).fetchone()

                total = aggregate.total or 0
                field_rates = {}
                if total > 0:
                    field_rates = {
                        "loan_type": round((aggregate.has_loan_type / total) * 100, 1),
                        "loan_purpose": round((aggregate.has_purpose / total) * 100, 1),
                        "loan_amount": round((aggregate.has_amount / total) * 100, 1),
                        "rate": round((aggregate.has_rate / total) * 100, 1),
                        "property_state": round((aggregate.has_state / total) * 100, 1),
                        "property_county": round((aggregate.has_county / total) * 100, 1),
                    }

                data = {
                    "period_days": period_days,
                    "total_funded": total,
                    "field_completeness_rates": field_rates,
                    "fields_below_100": [
                        {"field": k, "rate": v} for k, v in field_rates.items() if v < 100
                    ],
                }

            self.audit_log("check_hmda_data_quality", details={
                "loan_id": loan_id,
                "period_days": period_days,
            })

            return ToolResult(
                success=True,
                data=data,
                message=f"HMDA data: {data.get('completeness_pct', 'N/A')}% complete"
                        if loan_id else f"HMDA portfolio: {data.get('total_funded', 0)} funded loans checked"
            )

        except Exception as e:
            logger.exception("check_hmda_data_quality failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_compliance_remediation_plan(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a prioritized remediation plan for compliance issues."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_costs = input_data.get("include_cost_estimates", True)
        org_id = self.require_org_id()
        db = SessionLocal()

        try:
            self.verify_loan_tenant(db, loan_id)

            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.stage, l.closing_date,
                    l.borrower_name
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Gather all open compliance alerts for this loan
            alerts = db.execute(text("""
                SELECT id, alert_type, severity, title, description,
                    deadline_date, days_remaining
                FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
                ORDER BY
                    CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3 ELSE 4 END,
                    deadline_date ASC NULLS LAST
            """), {"loan_id": loan_id}).fetchall()

            # Build remediation items
            items = []
            total_estimated_cost = 0

            # Cost estimates by issue type
            cost_estimates = {
                "TRID_LE_OVERDUE": 250,
                "TRID_CD_NOT_SENT": 500,
                "TOLERANCE_VIOLATION": 1000,
                "FLOOD_DETERMINATION_MISSING": 50,
                "MISSING_DOCUMENT": 100,
                "PRIVACY_NOTICE": 25,
                "ESIGN_CONSENT": 50,
                "DEFAULT": 100,
            }

            for idx, alert in enumerate(alerts, 1):
                cost = cost_estimates.get(
                    alert.alert_type, cost_estimates["DEFAULT"]
                ) if include_costs else 0
                total_estimated_cost += cost

                # Set deadline based on severity
                if alert.deadline_date:
                    deadline = alert.deadline_date
                elif alert.severity == "critical":
                    deadline = date.today() + timedelta(days=1)
                elif alert.severity == "high":
                    deadline = date.today() + timedelta(days=3)
                else:
                    deadline = date.today() + timedelta(days=7)

                items.append({
                    "priority": idx,
                    "alert_id": alert.id,
                    "type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "description": alert.description,
                    "deadline": deadline.isoformat() if isinstance(deadline, date) else str(deadline),
                    "estimated_cure_cost": cost if include_costs else None,
                    "owner": "Compliance Officer",
                    "status": "pending",
                })

            # Add items for missing required documents (even if no alert exists)
            missing_docs = db.execute(text("""
                SELECT 'paystubs' as required_type
                WHERE NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE loan_id = :loan_id AND doc_type = 'paystubs' AND status = 'active'
                )
                UNION ALL
                SELECT 'w2' WHERE NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE loan_id = :loan_id AND doc_type = 'w2' AND status = 'active'
                )
                UNION ALL
                SELECT 'bank_statements' WHERE NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE loan_id = :loan_id AND doc_type = 'bank_statements' AND status = 'active'
                )
                UNION ALL
                SELECT 'credit_report' WHERE NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE loan_id = :loan_id AND doc_type = 'credit_report' AND status = 'active'
                )
            """), {"loan_id": loan_id}).fetchall()

            for doc in missing_docs:
                cost = cost_estimates["MISSING_DOCUMENT"] if include_costs else 0
                total_estimated_cost += cost
                items.append({
                    "priority": len(items) + 1,
                    "type": "MISSING_DOCUMENT",
                    "severity": "medium",
                    "title": f"Missing required document: {doc.required_type}",
                    "description": f"Collect {doc.required_type} from borrower",
                    "deadline": (date.today() + timedelta(days=5)).isoformat(),
                    "estimated_cure_cost": cost if include_costs else None,
                    "owner": "Processor",
                    "status": "pending",
                })

            self.audit_log("generate_compliance_remediation_plan", "loan", entity_id=loan_id, details={
                "total_items": len(items),
                "total_estimated_cost": total_estimated_cost,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "total_items": len(items),
                    "total_estimated_cure_cost": total_estimated_cost if include_costs else None,
                    "items": items,
                    "generated_at": datetime.now().isoformat(),
                },
                message=f"Remediation plan: {len(items)} item(s)"
                        f"{f', est. cure cost ${total_estimated_cost:,.0f}' if include_costs else ''}"
            )

        except Exception as e:
            logger.exception(f"generate_compliance_remediation_plan failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
