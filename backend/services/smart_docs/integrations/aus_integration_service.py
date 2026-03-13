"""
AUS (Automated Underwriting System) Integration Service

Abstraction layer for submitting loans to Desktop Underwriter (DU) and
Loan Product Advisor (LPA). Maps loan data to MISMO 3.4 format, submits
to the appropriate AUS API, and imports findings back into the CRM.

In development mode (no DU_API_URL / LPA_API_URL configured), returns
realistic mock responses so the full workflow can be exercised end-to-end
without live API credentials.

Usage:
    from services.smart_docs.integrations.aus_integration_service import (
        AUSIntegrationService,
        AUSSubmissionResult,
    )

    service = AUSIntegrationService(db)
    result = service.submit_to_du(loan_id=42, org_id=1)
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AUSCondition:
    """A condition returned by the AUS that must be satisfied."""
    condition_id: str
    category: str  # "prior_to_closing", "prior_to_funding", "prior_to_docs"
    description: str
    status: str = "open"  # open, cleared, waived

    def to_dict(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "category": self.category,
            "description": self.description,
            "status": self.status,
        }


@dataclass
class AUSFinding:
    """A finding/message returned by the AUS."""
    finding_id: str
    code: str  # AUS-specific code (e.g., "DU001", "LPA-F42")
    message: str
    severity: str = "info"  # info, warning, error

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class AUSSubmissionResult:
    """Result of submitting a loan to DU or LPA."""
    case_id: str
    aus_type: str  # "DU" or "LPA"
    recommendation: str  # "Approve/Eligible", "Refer", "Caution", "Out of Scope"
    risk_class: str  # "Accept", "Refer with Caution", etc.
    conditions: List[AUSCondition] = field(default_factory=list)
    findings: List[AUSFinding] = field(default_factory=list)
    income_used: Dict[str, Any] = field(default_factory=dict)
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "aus_type": self.aus_type,
            "recommendation": self.recommendation,
            "risk_class": self.risk_class,
            "conditions": [c.to_dict() for c in self.conditions],
            "findings": [f.to_dict() for f in self.findings],
            "income_used": self.income_used,
            "submitted_at": self.submitted_at.isoformat(),
        }


# =============================================================================
# AUS INTEGRATION SERVICE
# =============================================================================

class AUSIntegrationService:
    """Service for submitting loans to DU and LPA automated underwriting systems.

    Reads API credentials from environment variables:
        DU_API_URL, DU_API_KEY   -- Fannie Mae Desktop Underwriter
        LPA_API_URL, LPA_API_KEY -- Freddie Mac Loan Product Advisor

    When URLs are not configured, mock responses are returned for development.
    """

    def __init__(self, db: Session):
        self.db = db
        self.du_api_url = os.getenv("DU_API_URL", "")
        self.du_api_key = os.getenv("DU_API_KEY", "")
        self.lpa_api_url = os.getenv("LPA_API_URL", "")
        self.lpa_api_key = os.getenv("LPA_API_KEY", "")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def submit_to_du(
        self,
        loan_id: int,
        org_id: int,
        income_data: Optional[dict] = None,
    ) -> AUSSubmissionResult:
        """Submit a loan to Fannie Mae Desktop Underwriter.

        Args:
            loan_id: The CRM loan ID.
            org_id: The organization ID (tenant isolation).
            income_data: Optional income calculation data to include. If not
                         provided, the service will attempt to load the latest
                         approved income calculation for this loan.

        Returns:
            AUSSubmissionResult with findings, conditions, and recommendation.
        """
        mismo_data = self.map_loan_to_mismo(loan_id, org_id)
        if income_data:
            mismo_data["income_override"] = income_data

        if self.du_api_url:
            return self._submit_live_du(mismo_data, loan_id, org_id)
        else:
            logger.info(f"DU_API_URL not configured — returning mock DU response for loan {loan_id}")
            return self._mock_du_response(mismo_data, loan_id)

    def submit_to_lpa(
        self,
        loan_id: int,
        org_id: int,
        income_data: Optional[dict] = None,
    ) -> AUSSubmissionResult:
        """Submit a loan to Freddie Mac Loan Product Advisor.

        Args:
            loan_id: The CRM loan ID.
            org_id: The organization ID (tenant isolation).
            income_data: Optional income calculation data to include.

        Returns:
            AUSSubmissionResult with findings, conditions, and recommendation.
        """
        mismo_data = self.map_loan_to_mismo(loan_id, org_id)
        if income_data:
            mismo_data["income_override"] = income_data

        if self.lpa_api_url:
            return self._submit_live_lpa(mismo_data, loan_id, org_id)
        else:
            logger.info(f"LPA_API_URL not configured — returning mock LPA response for loan {loan_id}")
            return self._mock_lpa_response(mismo_data, loan_id)

    def get_du_findings(self, case_id: str) -> dict:
        """Retrieve DU findings for a previous submission by case ID.

        In production, this calls the DU API to fetch updated findings.
        In dev mode, returns mock data.
        """
        if self.du_api_url:
            return self._fetch_live_du_findings(case_id)
        return self._mock_findings("DU", case_id)

    def get_lpa_findings(self, case_id: str) -> dict:
        """Retrieve LPA findings for a previous submission by case ID.

        In production, this calls the LPA API to fetch updated findings.
        In dev mode, returns mock data.
        """
        if self.lpa_api_url:
            return self._fetch_live_lpa_findings(case_id)
        return self._mock_findings("LPA", case_id)

    def map_loan_to_mismo(self, loan_id: int, org_id: int) -> dict:
        """Convert CRM loan data to MISMO 3.4 format for AUS submission.

        Pulls borrower info, income, assets, liabilities, property info,
        and loan terms from the database and maps them to the MISMO XML
        data points that DU and LPA expect.

        Returns a dict representation of the MISMO data (would be serialized
        to XML for the actual API call).
        """
        from database.models.lead_loan import Loan

        loan = (
            self.db.query(Loan)
            .filter(Loan.id == loan_id, Loan.organization_id == org_id)
            .first()
        )
        if not loan:
            raise ValueError(f"Loan {loan_id} not found for organization {org_id}")

        # Load income calculation data if available
        income_data = self._load_income_data(loan_id)

        # Build MISMO 3.4 structure
        mismo = {
            "DEAL": {
                "LOANS": {
                    "LOAN": {
                        "LoanIdentifier": loan.loan_number,
                        "LoanPurposeType": self._map_loan_purpose(loan.loan_purpose),
                        "MortgageType": self._map_loan_type(loan.loan_type),
                        "LoanAmountNote": float(loan.amount or 0),
                        "NoteRatePercent": float(loan.rate or 0),
                        "LoanTermMonths": loan.term or 360,
                        "LoanMaturityDate": None,
                        "BaseLoanAmount": float(loan.amount or 0),
                    },
                },
                "PARTIES": {
                    "PARTY": [
                        self._build_borrower_party(loan),
                    ],
                },
                "COLLATERALS": {
                    "COLLATERAL": {
                        "SUBJECT_PROPERTY": {
                            "StreetAddress": loan.property_address or "",
                            "City": loan.property_city or "",
                            "State": loan.property_state or "",
                            "PostalCode": loan.property_zip or "",
                            "PropertyType": self._map_property_type(loan.property_type),
                            "OccupancyType": self._map_occupancy_type(loan.occupancy_type),
                            "PropertyUnits": loan.property_units or 1,
                            "PropertyEstimatedValueAmount": float(loan.purchase_price or loan.appraisal_value or 0),
                        },
                    },
                },
                "LIABILITIES": self._build_liabilities(loan),
                "ASSETS": self._build_assets(loan_id),
                "INCOME": income_data or {},
                "LOAN_PRODUCT": {
                    "RateType": loan.rate_type or "Fixed",
                    "IndexType": None,
                    "IndexRate": float(loan.index_rate or 0) if loan.index_rate else None,
                    "Margin": float(loan.margin or 0) if loan.margin else None,
                },
                "RATIOS": {
                    "FrontEndDTI": float(loan.ltv or 0),
                    "LTV": float(loan.ltv or 0),
                    "CLTV": float(loan.cltv or 0),
                },
            },
        }

        return mismo

    def import_findings(
        self,
        loan_id: int,
        findings: dict,
        source: str,
    ) -> dict:
        """Import AUS findings back to loan as compliance alerts.

        Creates ComplianceAlert records from AUS conditions so they appear
        in the loan's condition tracker.

        Args:
            loan_id: The CRM loan ID.
            findings: Dict containing 'conditions' and 'findings' lists.
            source: "DU" or "LPA".

        Returns:
            Summary of imported items.
        """
        from database.models.compliance import ComplianceAlert

        conditions = findings.get("conditions", [])
        imported_count = 0

        for cond in conditions:
            alert = ComplianceAlert(
                loan_id=loan_id,
                alert_type=f"AUS_{source}_CONDITION",
                severity="medium",
                title=f"[{source}] {cond.get('category', 'General')}",
                description=cond.get("description", ""),
                status="open",
            )
            self.db.add(alert)
            imported_count += 1

        aus_findings = findings.get("findings", [])
        for finding in aus_findings:
            if finding.get("severity") in ("warning", "error"):
                alert = ComplianceAlert(
                    loan_id=loan_id,
                    alert_type=f"AUS_{source}_FINDING",
                    severity="low" if finding["severity"] == "warning" else "medium",
                    title=f"[{source}] {finding.get('code', 'N/A')}",
                    description=finding.get("message", ""),
                    status="open",
                )
                self.db.add(alert)
                imported_count += 1

        self.db.flush()

        return {
            "source": source,
            "loan_id": loan_id,
            "conditions_imported": len(conditions),
            "findings_imported": imported_count - len(conditions),
            "total_alerts_created": imported_count,
        }

    def compare_income_to_findings(
        self,
        loan_id: int,
        our_income: dict,
        findings: dict,
    ) -> dict:
        """Compare our income calculation to what the AUS calculated.

        Produces a variance report highlighting discrepancies between
        the CRM's income calculation and the AUS's income determination.

        Args:
            loan_id: The CRM loan ID.
            our_income: Dict with our income calculation (total_monthly, sources).
            findings: Dict with AUS income data (income_used from AUSSubmissionResult).

        Returns:
            Variance report dict.
        """
        aus_income = findings.get("income_used", {})

        our_total = float(our_income.get("total_monthly_income", 0))
        aus_total = float(aus_income.get("total_monthly_income", 0))

        variance_amount = our_total - aus_total
        variance_pct = (
            round((variance_amount / aus_total) * 100, 2)
            if aus_total > 0
            else 0.0
        )

        # Compare individual income sources if available
        source_variances = []
        our_sources = our_income.get("sources", [])
        aus_sources = aus_income.get("sources", [])

        for our_src in our_sources:
            src_type = our_src.get("source_type", "")
            our_amount = float(our_src.get("monthly_amount", 0))

            # Find matching AUS source by type
            matching_aus = next(
                (s for s in aus_sources if s.get("source_type") == src_type),
                None,
            )

            if matching_aus:
                aus_amount = float(matching_aus.get("monthly_amount", 0))
                src_variance = our_amount - aus_amount
                source_variances.append({
                    "source_type": src_type,
                    "our_amount": our_amount,
                    "aus_amount": aus_amount,
                    "variance": round(src_variance, 2),
                    "variance_pct": round((src_variance / aus_amount) * 100, 2) if aus_amount else 0,
                    "status": "match" if abs(src_variance) < 50 else "discrepancy",
                })
            else:
                source_variances.append({
                    "source_type": src_type,
                    "our_amount": our_amount,
                    "aus_amount": 0,
                    "variance": our_amount,
                    "variance_pct": 100.0,
                    "status": "not_in_aus",
                })

        # Determine overall status
        has_discrepancy = abs(variance_pct) > 5.0  # > 5% total variance is notable
        has_source_issues = any(sv["status"] == "discrepancy" for sv in source_variances)

        return {
            "loan_id": loan_id,
            "summary": {
                "our_total_monthly": our_total,
                "aus_total_monthly": aus_total,
                "variance_amount": round(variance_amount, 2),
                "variance_pct": variance_pct,
                "status": "discrepancy" if has_discrepancy else "aligned",
            },
            "source_variances": source_variances,
            "flags": self._build_variance_flags(
                variance_pct, has_source_issues, source_variances
            ),
            "recommendation": (
                "Review income discrepancies before proceeding"
                if has_discrepancy
                else "Income calculations are aligned with AUS"
            ),
        }

    def get_submission_history(self, loan_id: int, org_id: int) -> List[dict]:
        """Get all AUS submissions for a loan.

        Returns:
            List of submission dicts ordered by submitted_at descending.
        """
        from database.models.aus_submission import AUSSubmission

        submissions = (
            self.db.query(AUSSubmission)
            .filter(
                AUSSubmission.loan_id == loan_id,
                AUSSubmission.organization_id == org_id,
            )
            .order_by(AUSSubmission.submitted_at.desc())
            .all()
        )

        return [
            {
                "id": s.id,
                "aus_type": s.aus_type,
                "case_id": s.case_id,
                "recommendation": s.recommendation,
                "risk_class": s.risk_class,
                "submission_status": s.submission_status,
                "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "submitted_by_user_id": s.submitted_by_user_id,
                "conditions_count": len(s.conditions or []),
                "findings_count": len(s.findings or []),
                "has_income_variance": s.income_variance is not None,
            }
            for s in submissions
        ]

    # -------------------------------------------------------------------------
    # MISMO Mapping Helpers
    # -------------------------------------------------------------------------

    def _build_borrower_party(self, loan) -> dict:
        """Build the MISMO PARTY element for the borrower."""
        name_parts = (loan.borrower_name or "").split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        party = {
            "INDIVIDUAL": {
                "NAME": {
                    "FirstName": first_name,
                    "LastName": last_name,
                },
                "CONTACT_POINTS": {
                    "Email": loan.borrower_email or "",
                    "Phone": loan.borrower_phone or "",
                },
            },
            "ROLES": {
                "ROLE": {
                    "RoleType": "Borrower",
                },
            },
        }

        # Add coborrower if present
        if loan.coborrower_name:
            co_parts = loan.coborrower_name.split(" ", 1)
            party["COBORROWER"] = {
                "NAME": {
                    "FirstName": co_parts[0] if co_parts else "",
                    "LastName": co_parts[1] if len(co_parts) > 1 else "",
                },
                "CONTACT_POINTS": {
                    "Email": loan.co_borrower_email or "",
                },
            }

        return party

    def _build_liabilities(self, loan) -> dict:
        """Build MISMO liabilities section from loan data."""
        liabilities = []

        if loan.monthly_payment:
            liabilities.append({
                "LiabilityType": "MortgageExpense",
                "MonthlyPaymentAmount": float(loan.monthly_payment),
            })

        if loan.second_loan_amount:
            liabilities.append({
                "LiabilityType": "SecondMortgage",
                "UnpaidBalanceAmount": float(loan.second_loan_amount),
                "MonthlyPaymentAmount": float(loan.second_loan_payment or 0),
            })

        return {"LIABILITY": liabilities}

    def _build_assets(self, loan_id: int) -> dict:
        """Build MISMO assets section from document data."""
        # In the real implementation, this would query bank statements
        # and asset documents. For now, return an empty structure.
        return {"ASSET": []}

    def _load_income_data(self, loan_id: int) -> Optional[dict]:
        """Load the latest approved income calculation for a loan."""
        try:
            from database.models.income_calculation import (
                IncomeCalculation,
                IncomeSource,
                CalculationStatus,
            )

            calc = (
                self.db.query(IncomeCalculation)
                .filter(
                    IncomeCalculation.loan_id == loan_id,
                    IncomeCalculation.status.in_([
                        CalculationStatus.APPROVED,
                        CalculationStatus.REVIEWED,
                        CalculationStatus.COMPLETED,
                    ]),
                )
                .order_by(IncomeCalculation.created_at.desc())
                .first()
            )

            if not calc:
                return None

            sources = (
                self.db.query(IncomeSource)
                .filter(IncomeSource.calculation_id == calc.id)
                .all()
            )

            return {
                "calculation_id": calc.id,
                "total_monthly_income": float(calc.total_qualifying_monthly_income or 0),
                "total_annual_income": float(calc.total_qualifying_annual_income or 0),
                "dti_front_end": float(calc.dti_front_end or 0),
                "dti_back_end": float(calc.dti_back_end or 0),
                "calculation_status": calc.status.value if hasattr(calc.status, "value") else str(calc.status),
                "sources": [
                    {
                        "source_type": (
                            src.source_type.value
                            if hasattr(src.source_type, "value")
                            else str(src.source_type)
                        ),
                        "employer_name": src.employer_name,
                        "monthly_amount": float(src.total_monthly_income or 0),
                        "annual_amount": float(src.total_annual_income or 0),
                        "base_monthly": float(src.base_monthly_income or 0),
                        "overtime_monthly": float(src.overtime_monthly or 0),
                        "bonus_monthly": float(src.bonus_monthly or 0),
                        "commission_monthly": float(src.commission_monthly or 0),
                    }
                    for src in sources
                ],
            }
        except Exception as e:
            logger.warning(f"Could not load income data for loan {loan_id}: {e}")
            return None

    @staticmethod
    def _map_loan_purpose(purpose: Optional[str]) -> str:
        """Map CRM loan purpose to MISMO LoanPurposeType."""
        mapping = {
            "purchase": "Purchase",
            "refinance": "Refinance",
            "cashout_refinance": "CashOutRefinance",
            "cash_out": "CashOutRefinance",
            "construction": "Construction",
            "heloc": "HELOC",
        }
        return mapping.get((purpose or "").lower(), "Purchase")

    @staticmethod
    def _map_loan_type(loan_type: Optional[str]) -> str:
        """Map CRM loan type to MISMO MortgageType."""
        mapping = {
            "conventional": "Conventional",
            "fha": "FHA",
            "va": "VA",
            "usda": "USDA",
            "jumbo": "Jumbo",
            "non_qm": "Other",
        }
        return mapping.get((loan_type or "").lower(), "Conventional")

    @staticmethod
    def _map_property_type(prop_type: Optional[str]) -> str:
        """Map CRM property type to MISMO PropertyType."""
        mapping = {
            "single_family": "SingleFamily",
            "condo": "Condominium",
            "townhouse": "Townhouse",
            "multi_family": "TwoToFourFamily",
            "manufactured": "ManufacturedHousing",
        }
        return mapping.get((prop_type or "").lower(), "SingleFamily")

    @staticmethod
    def _map_occupancy_type(occ_type: Optional[str]) -> str:
        """Map CRM occupancy type to MISMO OccupancyType."""
        mapping = {
            "primary": "PrimaryResidence",
            "second_home": "SecondHome",
            "investment": "InvestmentProperty",
        }
        return mapping.get((occ_type or "").lower(), "PrimaryResidence")

    # -------------------------------------------------------------------------
    # Live API Calls (stubs for real integration)
    # -------------------------------------------------------------------------

    def _submit_live_du(
        self, mismo_data: dict, loan_id: int, org_id: int
    ) -> AUSSubmissionResult:
        """Submit to real DU API.

        TODO: Implement actual MISMO XML serialization and HTTPS POST to
        Fannie Mae DU endpoint. For now, raises NotImplementedError.
        """
        raise NotImplementedError(
            "Live DU API integration not yet implemented. "
            "Set DU_API_URL='' to use mock mode."
        )

    def _submit_live_lpa(
        self, mismo_data: dict, loan_id: int, org_id: int
    ) -> AUSSubmissionResult:
        """Submit to real LPA API.

        TODO: Implement actual MISMO XML serialization and HTTPS POST to
        Freddie Mac LPA endpoint. For now, raises NotImplementedError.
        """
        raise NotImplementedError(
            "Live LPA API integration not yet implemented. "
            "Set LPA_API_URL='' to use mock mode."
        )

    def _fetch_live_du_findings(self, case_id: str) -> dict:
        """Fetch findings from live DU API."""
        raise NotImplementedError("Live DU findings retrieval not yet implemented.")

    def _fetch_live_lpa_findings(self, case_id: str) -> dict:
        """Fetch findings from live LPA API."""
        raise NotImplementedError("Live LPA findings retrieval not yet implemented.")

    # -------------------------------------------------------------------------
    # Mock Responses (dev mode)
    # -------------------------------------------------------------------------

    def _mock_du_response(
        self, mismo_data: dict, loan_id: int
    ) -> AUSSubmissionResult:
        """Generate a realistic mock DU response."""
        case_id = f"DU-{uuid.uuid4().hex[:8].upper()}"
        loan_data = mismo_data.get("DEAL", {}).get("LOANS", {}).get("LOAN", {})
        loan_amount = loan_data.get("BaseLoanAmount", 0)
        income = mismo_data.get("DEAL", {}).get("INCOME", {})
        monthly_income = income.get("total_monthly_income", 8500.0) if income else 8500.0

        # Determine recommendation based on LTV and income
        property_data = (
            mismo_data.get("DEAL", {})
            .get("COLLATERALS", {})
            .get("COLLATERAL", {})
            .get("SUBJECT_PROPERTY", {})
        )
        property_value = property_data.get("PropertyEstimatedValueAmount", 0)
        ltv = (loan_amount / property_value * 100) if property_value > 0 else 80

        if ltv <= 80 and monthly_income > 5000:
            recommendation = "Approve/Eligible"
            risk_class = "Accept"
        elif ltv <= 95:
            recommendation = "Approve/Eligible"
            risk_class = "Accept"
        else:
            recommendation = "Refer"
            risk_class = "Refer with Caution"

        conditions = [
            AUSCondition(
                condition_id=f"DU-C-{i+1:03d}",
                category=cat,
                description=desc,
            )
            for i, (cat, desc) in enumerate([
                ("prior_to_closing", "Verify employment within 10 business days of closing"),
                ("prior_to_closing", "Provide final paycheck stub covering 30-day period"),
                ("prior_to_docs", "Title commitment showing no outstanding liens"),
                ("prior_to_docs", "Hazard insurance binder with mortgagee clause"),
                ("prior_to_funding", "Signed closing disclosure"),
            ])
        ]

        findings = [
            AUSFinding(
                finding_id=f"DU-F-{i+1:03d}",
                code=code,
                message=msg,
                severity=sev,
            )
            for i, (code, msg, sev) in enumerate([
                ("DU001", "Loan meets eligibility requirements for delivery to Fannie Mae", "info"),
                ("DU002", f"Qualifying income: ${monthly_income:,.2f}/month", "info"),
                ("DU003", "Credit risk assessment: Acceptable", "info"),
                ("DU004", "Property eligibility confirmed", "info"),
                ("DU005", "MI required for LTV > 80%" if ltv > 80 else "No MI required", "warning" if ltv > 80 else "info"),
            ])
        ]

        income_used = {
            "total_monthly_income": monthly_income,
            "total_annual_income": monthly_income * 12,
            "sources": [
                {
                    "source_type": "w2_employment",
                    "monthly_amount": monthly_income * 0.85,
                    "description": "Primary employment income",
                },
                {
                    "source_type": "bonus",
                    "monthly_amount": monthly_income * 0.15,
                    "description": "Bonus/overtime income (2-year average)",
                },
            ],
        }

        return AUSSubmissionResult(
            case_id=case_id,
            aus_type="DU",
            recommendation=recommendation,
            risk_class=risk_class,
            conditions=conditions,
            findings=findings,
            income_used=income_used,
            raw_response={
                "mock": True,
                "engine": "Desktop Underwriter",
                "version": "11.0",
                "case_id": case_id,
                "recommendation": recommendation,
                "risk_class": risk_class,
            },
        )

    def _mock_lpa_response(
        self, mismo_data: dict, loan_id: int
    ) -> AUSSubmissionResult:
        """Generate a realistic mock LPA response."""
        case_id = f"LPA-{uuid.uuid4().hex[:8].upper()}"
        loan_data = mismo_data.get("DEAL", {}).get("LOANS", {}).get("LOAN", {})
        loan_amount = loan_data.get("BaseLoanAmount", 0)
        income = mismo_data.get("DEAL", {}).get("INCOME", {})
        monthly_income = income.get("total_monthly_income", 8500.0) if income else 8500.0

        property_data = (
            mismo_data.get("DEAL", {})
            .get("COLLATERALS", {})
            .get("COLLATERAL", {})
            .get("SUBJECT_PROPERTY", {})
        )
        property_value = property_data.get("PropertyEstimatedValueAmount", 0)
        ltv = (loan_amount / property_value * 100) if property_value > 0 else 80

        if ltv <= 80 and monthly_income > 5000:
            recommendation = "Accept"
            risk_class = "Accept"
        elif ltv <= 95:
            recommendation = "Accept"
            risk_class = "Accept"
        else:
            recommendation = "Caution"
            risk_class = "Caution"

        conditions = [
            AUSCondition(
                condition_id=f"LPA-C-{i+1:03d}",
                category=cat,
                description=desc,
            )
            for i, (cat, desc) in enumerate([
                ("prior_to_closing", "Verification of employment dated within 120 days of note date"),
                ("prior_to_closing", "Evidence of sufficient funds for closing"),
                ("prior_to_docs", "Preliminary title report with no exceptions"),
                ("prior_to_docs", "Flood zone determination"),
                ("prior_to_funding", "All conditions cleared and signed CD received"),
            ])
        ]

        findings = [
            AUSFinding(
                finding_id=f"LPA-F-{i+1:03d}",
                code=code,
                message=msg,
                severity=sev,
            )
            for i, (code, msg, sev) in enumerate([
                ("LPA001", "Loan eligible for purchase by Freddie Mac", "info"),
                ("LPA002", f"Total qualifying income: ${monthly_income:,.2f}/month", "info"),
                ("LPA003", "Credit evaluation: Acceptable risk", "info"),
                ("LPA004", "Collateral assessment: Acceptable", "info"),
                ("LPA005", "Mortgage insurance required" if ltv > 80 else "No mortgage insurance required", "warning" if ltv > 80 else "info"),
            ])
        ]

        income_used = {
            "total_monthly_income": monthly_income,
            "total_annual_income": monthly_income * 12,
            "sources": [
                {
                    "source_type": "w2_employment",
                    "monthly_amount": monthly_income * 0.80,
                    "description": "Base employment income",
                },
                {
                    "source_type": "commission",
                    "monthly_amount": monthly_income * 0.20,
                    "description": "Commission income (24-month average)",
                },
            ],
        }

        return AUSSubmissionResult(
            case_id=case_id,
            aus_type="LPA",
            recommendation=recommendation,
            risk_class=risk_class,
            conditions=conditions,
            findings=findings,
            income_used=income_used,
            raw_response={
                "mock": True,
                "engine": "Loan Product Advisor",
                "version": "5.0",
                "case_id": case_id,
                "recommendation": recommendation,
                "risk_class": risk_class,
            },
        )

    def _mock_findings(self, aus_type: str, case_id: str) -> dict:
        """Return mock findings for a previous submission."""
        prefix = "DU" if aus_type == "DU" else "LPA"
        return {
            "case_id": case_id,
            "aus_type": aus_type,
            "status": "complete",
            "findings": [
                {
                    "finding_id": f"{prefix}-F-001",
                    "code": f"{prefix}001",
                    "message": f"Loan meets {aus_type} eligibility requirements",
                    "severity": "info",
                },
            ],
            "conditions": [
                {
                    "condition_id": f"{prefix}-C-001",
                    "category": "prior_to_closing",
                    "description": "Verify employment within 10 business days of closing",
                    "status": "open",
                },
            ],
        }

    @staticmethod
    def _build_variance_flags(
        variance_pct: float,
        has_source_issues: bool,
        source_variances: list,
    ) -> List[str]:
        """Build human-readable flags from variance analysis."""
        flags = []

        if abs(variance_pct) > 10:
            flags.append(
                f"Total income variance of {variance_pct:+.1f}% exceeds 10% threshold — "
                "manual review required"
            )
        elif abs(variance_pct) > 5:
            flags.append(
                f"Total income variance of {variance_pct:+.1f}% exceeds 5% — "
                "recommend verification"
            )

        not_in_aus = [sv for sv in source_variances if sv["status"] == "not_in_aus"]
        if not_in_aus:
            types = ", ".join(sv["source_type"] for sv in not_in_aus)
            flags.append(
                f"Income sources not recognized by AUS: {types}"
            )

        discrepancies = [
            sv for sv in source_variances
            if sv["status"] == "discrepancy"
        ]
        for d in discrepancies:
            flags.append(
                f"{d['source_type']}: our ${d['our_amount']:,.2f}/mo vs "
                f"AUS ${d['aus_amount']:,.2f}/mo ({d['variance_pct']:+.1f}%)"
            )

        return flags
