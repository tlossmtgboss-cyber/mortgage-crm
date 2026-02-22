"""
AI Smart File Analysis Service

Provides intelligent loan file analysis for loan officers:
- Missing document detection
- Red flag identification
- Guideline compliance checking
- Pre-submission recommendations
- Integration with AI Underwriting Engine for comprehensive analysis

This service significantly reduces underwriting kickbacks by catching
issues before submission.
"""

import os
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import anthropic
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Try to import underwriting engine components
_underwriting_engine_available = False
try:
    from services.underwriting_engine import (
        UnderwritingEngine,
        IncomeCalculator,
        AssetAnalyzer,
        CreditAnalyzer,
        EligibilityEngine,
        ConditionGenerator,
    )
    _underwriting_engine_available = True
    logger.info("Underwriting engine components loaded successfully")
except ImportError as e:
    logger.warning(f"Underwriting engine not available: {e}. Using basic analysis only.")

# Document requirement templates by loan type
REQUIRED_DOCUMENTS = {
    "conventional": {
        "income": ["W2 (2 years)", "Paystubs (30 days)", "Tax Returns (if self-employed)"],
        "assets": ["Bank Statements (2 months)", "Investment Statements"],
        "property": ["Purchase Contract", "Appraisal", "Title", "Homeowners Insurance"],
        "identity": ["Driver's License", "Social Security Card"],
        "credit": ["Credit Report"],
    },
    "fha": {
        "income": ["W2 (2 years)", "Paystubs (30 days)", "Tax Returns"],
        "assets": ["Bank Statements (2 months)", "Gift Letter (if applicable)"],
        "property": ["Purchase Contract", "Appraisal", "Title", "Homeowners Insurance", "FHA Case Number"],
        "identity": ["Driver's License", "Social Security Card"],
        "credit": ["Credit Report", "LOE for collections"],
    },
    "va": {
        "income": ["W2 (2 years)", "Paystubs (30 days)"],
        "assets": ["Bank Statements (2 months)"],
        "property": ["Purchase Contract", "Appraisal", "Title", "Homeowners Insurance"],
        "identity": ["Driver's License", "Social Security Card"],
        "credit": ["Credit Report"],
        "va_specific": ["DD-214", "Certificate of Eligibility (COE)", "Statement of Service"],
    },
    "usda": {
        "income": ["W2 (2 years)", "Paystubs (30 days)", "Tax Returns"],
        "assets": ["Bank Statements (2 months)"],
        "property": ["Purchase Contract", "Appraisal", "Title", "Homeowners Insurance"],
        "identity": ["Driver's License", "Social Security Card"],
        "credit": ["Credit Report"],
        "usda_specific": ["USDA Eligibility Verification"],
    },
    "jumbo": {
        "income": ["W2 (2 years)", "Paystubs (30 days)", "Tax Returns (2 years)"],
        "assets": ["Bank Statements (3 months)", "Investment Statements", "Proof of Reserves"],
        "property": ["Purchase Contract", "Appraisal", "Title", "Homeowners Insurance"],
        "identity": ["Driver's License", "Social Security Card"],
        "credit": ["Credit Report"],
    },
}

# Guideline thresholds by loan type
GUIDELINE_THRESHOLDS = {
    "conventional": {
        "min_credit_score": 620,
        "max_dti": 50,
        "max_ltv_primary": 97,
        "max_ltv_investment": 85,
        "min_reserves_investment": 6,  # months
    },
    "fha": {
        "min_credit_score": 580,  # 500 with 10% down
        "max_dti": 56.99,
        "max_ltv": 96.5,
    },
    "va": {
        "min_credit_score": 620,  # No VA minimum, but lenders typically require
        "max_dti": None,  # Residual income based
        "max_ltv": 100,
    },
    "usda": {
        "min_credit_score": 640,
        "max_dti": 44,  # Can go higher with compensating factors
        "max_ltv": 100,
    },
    "jumbo": {
        "min_credit_score": 700,
        "max_dti": 43,
        "max_ltv": 80,
        "min_reserves": 12,  # months
    },
}


class AIFileAnalysisService:
    """
    AI-powered loan file analysis service.
    Analyzes loan files to identify issues before underwriting submission.
    Integrates with the AI Underwriting Engine when available for comprehensive analysis.
    """

    def __init__(self, db: Session, use_underwriting_engine: bool = True):
        self.db = db
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.use_underwriting_engine = use_underwriting_engine and _underwriting_engine_available

        # Initialize underwriting engine components if available
        if self.use_underwriting_engine:
            try:
                self.underwriting_engine = UnderwritingEngine()
                self.eligibility_engine = EligibilityEngine()
                self.condition_generator = ConditionGenerator()
                logger.info("Underwriting engine initialized for file analysis")
            except Exception as e:
                logger.warning(f"Failed to initialize underwriting engine: {e}")
                self.use_underwriting_engine = False

    def analyze_loan_file(self, loan_id: int) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis of a loan file.

        Returns:
            - summary: Overall file health summary
            - missing_documents: List of missing required documents
            - red_flags: Potential issues that need attention
            - compliance_issues: Guideline compliance concerns
            - recommendations: Actionable recommendations
            - readiness_score: 0-100 score indicating file readiness
            - underwriting_analysis: Detailed underwriting engine results (if available)
        """
        # Gather all loan data
        loan_data = self._get_loan_data(loan_id)
        if not loan_data:
            return {
                "error": "Loan not found",
                "loan_id": loan_id
            }

        documents = self._get_loan_documents(loan_id)
        conditions = self._get_loan_conditions(loan_id)
        borrower_data = self._get_borrower_data(loan_data.get("lead_id"))

        # Perform rule-based analysis
        missing_docs = self._check_missing_documents(
            loan_data.get("loan_type", "conventional"),
            documents
        )

        compliance_issues = self._check_guideline_compliance(
            loan_data,
            borrower_data
        )

        # Run underwriting engine analysis if available
        underwriting_result = None
        engine_conditions = []
        eligibility_result = None

        if self.use_underwriting_engine:
            try:
                underwriting_result = self._run_underwriting_engine_analysis(
                    loan_data, borrower_data, documents
                )
                # Extract additional issues from underwriting engine
                if underwriting_result:
                    # Add eligibility issues to compliance
                    if underwriting_result.get("eligibility_results"):
                        eligibility_result = underwriting_result["eligibility_results"]
                        for program in eligibility_result.get("programs", []):
                            if not program.get("eligible"):
                                for reason in program.get("ineligibility_reasons", []):
                                    compliance_issues.append({
                                        "type": f"{program.get('agency', 'unknown')}_eligibility",
                                        "severity": "high",
                                        "message": reason,
                                    })

                    # Get generated conditions
                    engine_conditions = underwriting_result.get("conditions", [])

                    # Add critical issues as red flags
                    for issue in underwriting_result.get("critical_issues", []):
                        compliance_issues.append({
                            "type": "underwriting_critical",
                            "severity": "critical",
                            "message": issue,
                        })
            except Exception as e:
                logger.warning(f"Underwriting engine analysis failed: {e}")

        # Build context for AI analysis
        context = self._build_analysis_context(
            loan_data,
            documents,
            conditions,
            borrower_data,
            missing_docs,
            compliance_issues
        )

        # Add underwriting engine context if available
        if underwriting_result:
            context["underwriting_engine"] = {
                "decision": underwriting_result.get("decision"),
                "risk_level": underwriting_result.get("risk_level"),
                "confidence_score": underwriting_result.get("confidence_score"),
                "qualifying_income": underwriting_result.get("qualifying_income"),
                "calculated_dti": underwriting_result.get("calculated_dti"),
                "calculated_ltv": underwriting_result.get("calculated_ltv"),
            }

        # Get AI-powered analysis
        ai_analysis = self._get_ai_analysis(context)

        # Calculate readiness score
        readiness_score = self._calculate_readiness_score(
            missing_docs,
            compliance_issues,
            conditions + engine_conditions,  # Include engine-generated conditions
            ai_analysis.get("red_flags", [])
        )

        result = {
            "loan_id": loan_id,
            "loan_number": loan_data.get("loan_number"),
            "loan_type": loan_data.get("loan_type"),
            "analysis_date": datetime.utcnow().isoformat(),
            "summary": ai_analysis.get("summary", ""),
            "readiness_score": readiness_score,
            "readiness_grade": self._score_to_grade(readiness_score),
            "missing_documents": missing_docs,
            "documents_collected": len(documents),
            "red_flags": ai_analysis.get("red_flags", []),
            "compliance_issues": compliance_issues,
            "recommendations": ai_analysis.get("recommendations", []),
            "open_conditions": len([c for c in conditions if c.get("status") == "open"]),
            "next_steps": ai_analysis.get("next_steps", []),
        }

        # Add underwriting engine results if available
        if underwriting_result:
            result["underwriting_analysis"] = {
                "decision": underwriting_result.get("decision"),
                "risk_level": underwriting_result.get("risk_level"),
                "confidence_score": underwriting_result.get("confidence_score"),
                "qualifying_income": underwriting_result.get("qualifying_income"),
                "calculated_dti": underwriting_result.get("calculated_dti"),
                "calculated_ltv": underwriting_result.get("calculated_ltv"),
                "reserves_months": underwriting_result.get("reserves_months"),
                "approved_program": underwriting_result.get("approved_program"),
                "denial_reasons": underwriting_result.get("denial_reasons", []),
                "refer_reasons": underwriting_result.get("refer_reasons", []),
            }
            if eligibility_result:
                result["eligibility"] = eligibility_result

        return result

    def _run_underwriting_engine_analysis(
        self,
        loan_data: Dict,
        borrower_data: Optional[Dict],
        documents: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """
        Run the underwriting engine analysis on the loan file.

        Converts loan data to the format expected by the underwriting engine
        and runs comprehensive analysis including income, assets, credit, and eligibility.
        """
        if not self.use_underwriting_engine:
            return None

        try:
            # Build loan data for underwriting engine
            engine_loan_data = {
                "loan_amount": float(loan_data.get("amount") or 0),
                "property_value": float(loan_data.get("purchase_price") or loan_data.get("amount") or 0),
                "loan_purpose": self._map_loan_purpose(loan_data.get("stage")),
                "property_type": self._map_property_type(loan_data.get("property_type") or borrower_data.get("property_type") if borrower_data else None),
                "occupancy": "primary",  # Default, could be enhanced
                "loan_type": (loan_data.get("loan_type") or "conventional").lower(),
                "property_state": self._extract_state(loan_data.get("property_address")),
                "credit_score": borrower_data.get("credit_score") if borrower_data else None,
                "dti_ratio": float(borrower_data.get("dti") or 0) if borrower_data else None,
                "ltv": float(loan_data.get("ltv") or 0),
            }

            # Build income data if available
            income_data = None
            if borrower_data:
                income_data = {
                    "sources": [{
                        "type": "w2",
                        "annual_amount": float(borrower_data.get("annual_income") or 0) or float(borrower_data.get("loan_amount") or 0) * 0.25,  # Estimate
                    }]
                }

            # Build credit data if available
            credit_data = None
            if borrower_data and borrower_data.get("credit_score"):
                credit_data = {
                    "credit_score": borrower_data.get("credit_score"),
                    "tradelines": [],
                }

            # Run underwriting analysis
            result = self.underwriting_engine.analyze_loan(
                loan_data=engine_loan_data,
                income_data=income_data,
                asset_data=None,  # Could be enhanced with document extraction
                credit_data=credit_data,
            )

            # Convert result to dict format
            return {
                "decision": result.decision.value if hasattr(result.decision, 'value') else str(result.decision),
                "risk_level": result.risk_level.value if hasattr(result.risk_level, 'value') else str(result.risk_level),
                "confidence_score": result.confidence_score,
                "qualifying_income": result.qualifying_income,
                "calculated_dti": result.calculated_dti,
                "calculated_ltv": result.calculated_ltv,
                "reserves_months": result.reserves_months,
                "approved_loan_amount": result.approved_loan_amount,
                "approved_program": result.approved_program,
                "denial_reasons": result.denial_reasons,
                "refer_reasons": result.refer_reasons,
                "critical_issues": result.critical_issues,
                "conditions": result.conditions if hasattr(result, 'conditions') else [],
                "eligibility_results": result.eligibility_result,
            }

        except Exception as e:
            logger.error(f"Underwriting engine analysis failed: {e}")
            return None

    def _map_loan_purpose(self, stage: Optional[str]) -> str:
        """Map loan stage to loan purpose."""
        if not stage:
            return "purchase"
        stage_lower = stage.lower()
        if "refi" in stage_lower or "refinance" in stage_lower:
            if "cash" in stage_lower:
                return "cash_out"
            return "rate_term"
        return "purchase"

    def _map_property_type(self, prop_type: Optional[str]) -> str:
        """Map property type to engine format."""
        if not prop_type:
            return "single_family"
        prop_lower = prop_type.lower()
        mapping = {
            "sfr": "single_family",
            "single": "single_family",
            "condo": "condo",
            "townhouse": "townhouse",
            "town": "townhouse",
            "multi": "multi_family",
            "duplex": "multi_family",
            "triplex": "multi_family",
            "fourplex": "multi_family",
            "manufactured": "manufactured",
            "mobile": "manufactured",
        }
        for key, value in mapping.items():
            if key in prop_lower:
                return value
        return "single_family"

    def _extract_state(self, address: Optional[str]) -> str:
        """Extract state code from address."""
        if not address:
            return "CA"  # Default
        # Simple extraction - look for 2-letter state code
        import re
        state_pattern = r'\b([A-Z]{2})\b'
        matches = re.findall(state_pattern, address.upper())
        us_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
        }
        for match in matches:
            if match in us_states:
                return match
        return "CA"

    def quick_file_check(self, loan_id: int) -> Dict[str, Any]:
        """
        Quick file readiness check without full AI analysis.
        Uses rule-based checking plus optional underwriting engine eligibility check.
        """
        loan_data = self._get_loan_data(loan_id)
        if not loan_data:
            return {"error": "Loan not found", "loan_id": loan_id}

        documents = self._get_loan_documents(loan_id)
        conditions = self._get_loan_conditions(loan_id)
        borrower_data = self._get_borrower_data(loan_data.get("lead_id"))

        missing_docs = self._check_missing_documents(
            loan_data.get("loan_type", "conventional"),
            documents
        )

        compliance_issues = self._check_guideline_compliance(
            loan_data,
            borrower_data
        )

        # Quick eligibility check with underwriting engine
        eligibility_status = None
        if self.use_underwriting_engine:
            try:
                eligibility_status = self._quick_eligibility_check(loan_data, borrower_data)
                # Add eligibility issues to compliance
                if eligibility_status and not eligibility_status.get("is_eligible"):
                    for reason in eligibility_status.get("ineligibility_reasons", []):
                        compliance_issues.append({
                            "type": "eligibility",
                            "severity": "high",
                            "message": reason,
                        })
            except Exception as e:
                logger.debug(f"Quick eligibility check failed: {e}")

        open_conditions = [c for c in conditions if c.get("status") == "open"]

        readiness_score = self._calculate_readiness_score(
            missing_docs,
            compliance_issues,
            conditions,
            []
        )

        result = {
            "loan_id": loan_id,
            "loan_number": loan_data.get("loan_number"),
            "readiness_score": readiness_score,
            "readiness_grade": self._score_to_grade(readiness_score),
            "is_ready_to_submit": readiness_score >= 80 and len(open_conditions) == 0,
            "missing_documents_count": len(missing_docs),
            "compliance_issues_count": len(compliance_issues),
            "open_conditions_count": len(open_conditions),
            "quick_issues": self._get_quick_issues(missing_docs, compliance_issues, open_conditions),
        }

        if eligibility_status:
            result["eligibility_status"] = eligibility_status

        return result

    def _quick_eligibility_check(
        self,
        loan_data: Dict,
        borrower_data: Optional[Dict]
    ) -> Optional[Dict[str, Any]]:
        """Run a quick eligibility check using the underwriting engine."""
        if not self.use_underwriting_engine:
            return None

        try:
            loan_type = (loan_data.get("loan_type") or "conventional").lower()
            credit_score = borrower_data.get("credit_score") if borrower_data else None
            ltv = float(loan_data.get("ltv") or 0)
            dti = float(borrower_data.get("dti") or 0) if borrower_data else None

            # Create loan scenario for eligibility check
            from services.underwriting_engine import LoanScenario, LoanPurpose, PropertyType, OccupancyType, Agency

            scenario = LoanScenario(
                loan_amount=float(loan_data.get("amount") or 0),
                property_value=float(loan_data.get("purchase_price") or loan_data.get("amount") or 0),
                loan_purpose=LoanPurpose.PURCHASE,
                property_type=PropertyType.SINGLE_FAMILY,
                occupancy=OccupancyType.PRIMARY,
                credit_score=credit_score or 720,
                ltv=ltv,
                dti=dti or 43.0,
                property_state=self._extract_state(loan_data.get("property_address")),
            )

            # Check eligibility for the specified loan type
            agency_map = {
                "conventional": Agency.FANNIE_MAE,
                "fha": Agency.FHA,
                "va": Agency.VA,
            }
            agency = agency_map.get(loan_type, Agency.FANNIE_MAE)

            result = self.eligibility_engine.check_eligibility(scenario, [agency])

            # Find the relevant program result
            for program in result.programs:
                if program.agency == agency:
                    return {
                        "is_eligible": program.eligible,
                        "program": program.agency.value if hasattr(program.agency, 'value') else str(program.agency),
                        "max_ltv": program.max_ltv,
                        "max_dti": program.max_dti,
                        "min_credit_score": program.min_credit_score,
                        "ineligibility_reasons": program.ineligibility_reasons,
                    }

            return None

        except Exception as e:
            logger.debug(f"Quick eligibility check error: {e}")
            return None

    def analyze_document(self, document_id: int) -> Dict[str, Any]:
        """
        Analyze a specific document for issues.
        """
        doc = self._get_document(document_id)
        if not doc:
            return {"error": "Document not found", "document_id": document_id}

        # Check for common document issues
        issues = []

        if doc.get("detected_is_screenshot"):
            issues.append({
                "type": "screenshot_detected",
                "severity": "high",
                "message": "Document appears to be a screenshot. Original document required.",
                "confidence": doc.get("screenshot_confidence", 0)
            })

        if doc.get("is_expired"):
            issues.append({
                "type": "expired",
                "severity": "high",
                "message": f"Document has expired. Expires: {doc.get('doc_expires_at')}",
            })
        elif doc.get("days_until_expiration") and doc.get("days_until_expiration") < 14:
            issues.append({
                "type": "expiring_soon",
                "severity": "medium",
                "message": f"Document expires in {doc.get('days_until_expiration')} days.",
            })

        if doc.get("status") == "REJECTED":
            issues.append({
                "type": "rejected",
                "severity": "high",
                "message": doc.get("rejection_reason", "Document was rejected"),
                "category": doc.get("rejection_category"),
                "fix_instructions": doc.get("fix_instructions"),
            })

        return {
            "document_id": document_id,
            "file_name": doc.get("file_name"),
            "doc_type": doc.get("doc_type"),
            "status": doc.get("status"),
            "issues": issues,
            "has_issues": len(issues) > 0,
            "extracted_data": {
                "dates": doc.get("extracted_dates"),
                "names": doc.get("extracted_names"),
                "employer": doc.get("extracted_employer"),
                "amount": float(doc.get("extracted_amount") or 0),
            },
        }

    def _get_loan_data(self, loan_id: int) -> Optional[Dict]:
        """Get loan data from database."""
        try:
            result = self.db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.lead_id, l.loan_officer_id,
                    l.stage, l.program, l.loan_type, l.amount, l.purchase_price,
                    l.ltv, l.rate, l.term, l.property_address,
                    l.lock_date, l.closing_date, l.created_at,
                    le.credit_score, le.loan_amount as lead_loan_amount,
                    le.dti, le.property_type, le.first_name, le.last_name
                FROM loans l
                LEFT JOIN leads le ON le.id = l.lead_id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
        except Exception as e:
            logger.error(f"Error getting loan data: {e}")
            return None

    def _get_loan_documents(self, loan_id: int) -> List[Dict]:
        """Get all documents for a loan."""
        try:
            result = self.db.execute(text("""
                SELECT
                    id, file_name, doc_type, detected_doc_type,
                    status, decision, detected_is_screenshot,
                    is_expired, days_until_expiration,
                    extracted_dates, created_at
                FROM smart_documents
                WHERE loan_id = :loan_id
                ORDER BY created_at DESC
            """), {"loan_id": loan_id})
            return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.exception(f"Failed to get loan documents for loan_id {loan_id}: {e}")
            return []

    def _get_loan_conditions(self, loan_id: int) -> List[Dict]:
        """Get conditions for a loan."""
        try:
            result = self.db.execute(text("""
                SELECT
                    id, condition_type, description, status,
                    priority, due_date, category
                FROM loan_conditions
                WHERE loan_id = :loan_id
                ORDER BY priority DESC, due_date ASC
            """), {"loan_id": loan_id})
            return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.exception(f"Failed to get loan conditions for loan_id {loan_id}: {e}")
            return []

    def _get_borrower_data(self, lead_id: Optional[int]) -> Optional[Dict]:
        """Get borrower data from lead."""
        if not lead_id:
            return None
        try:
            result = self.db.execute(text("""
                SELECT
                    id, first_name, last_name, email, phone,
                    credit_score, loan_amount, dti,
                    property_type, loan_type, source, status
                FROM leads
                WHERE id = :lead_id
            """), {"lead_id": lead_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
        except Exception as e:
            logger.exception(f"Failed to get borrower data for lead_id {lead_id}: {e}")
            return None

    def _get_document(self, document_id: int) -> Optional[Dict]:
        """Get a specific document."""
        try:
            result = self.db.execute(text("""
                SELECT *
                FROM smart_documents
                WHERE id = :document_id
            """), {"document_id": document_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
        except Exception as e:
            logger.exception(f"Failed to get document {document_id}: {e}")
            return None

    def _check_missing_documents(
        self,
        loan_type: str,
        documents: List[Dict]
    ) -> List[Dict]:
        """Check for missing required documents."""
        loan_type = (loan_type or "conventional").lower()
        required = REQUIRED_DOCUMENTS.get(loan_type, REQUIRED_DOCUMENTS["conventional"])

        # Get collected document types
        collected_types = set()
        for doc in documents:
            doc_type = doc.get("doc_type") or doc.get("detected_doc_type")
            if doc_type and doc.get("status") not in ["REJECTED", "EXPIRED"]:
                collected_types.add(doc_type.upper())

        missing = []

        for category, doc_list in required.items():
            for doc_name in doc_list:
                # Check if document is collected (simple matching)
                doc_key = doc_name.upper().split(" (")[0].replace(" ", "_")
                is_collected = any(
                    doc_key in t or t in doc_key
                    for t in collected_types
                )

                if not is_collected:
                    missing.append({
                        "category": category,
                        "document": doc_name,
                        "priority": "critical" if category in ["income", "identity"] else "high",
                    })

        return missing

    def _check_guideline_compliance(
        self,
        loan_data: Dict,
        borrower_data: Optional[Dict]
    ) -> List[Dict]:
        """Check guideline compliance."""
        issues = []
        loan_type = (loan_data.get("loan_type") or "conventional").lower()
        thresholds = GUIDELINE_THRESHOLDS.get(loan_type, GUIDELINE_THRESHOLDS["conventional"])

        # Credit score check
        credit_score = borrower_data.get("credit_score") if borrower_data else None
        if credit_score and thresholds.get("min_credit_score"):
            if credit_score < thresholds["min_credit_score"]:
                issues.append({
                    "type": "credit_score",
                    "severity": "critical",
                    "message": f"Credit score {credit_score} below minimum {thresholds['min_credit_score']} for {loan_type.upper()}",
                    "current_value": credit_score,
                    "threshold": thresholds["min_credit_score"],
                })

        # DTI check
        dti = borrower_data.get("dti") if borrower_data else None
        if dti and thresholds.get("max_dti"):
            if float(dti) > thresholds["max_dti"]:
                issues.append({
                    "type": "dti",
                    "severity": "high",
                    "message": f"DTI {dti}% exceeds maximum {thresholds['max_dti']}% for {loan_type.upper()}",
                    "current_value": dti,
                    "threshold": thresholds["max_dti"],
                })

        # LTV check
        ltv = loan_data.get("ltv")
        if ltv:
            max_ltv = thresholds.get("max_ltv") or thresholds.get("max_ltv_primary")
            if max_ltv and float(ltv) > max_ltv:
                issues.append({
                    "type": "ltv",
                    "severity": "high",
                    "message": f"LTV {ltv}% exceeds maximum {max_ltv}% for {loan_type.upper()}",
                    "current_value": ltv,
                    "threshold": max_ltv,
                })

        return issues

    def _build_analysis_context(
        self,
        loan_data: Dict,
        documents: List[Dict],
        conditions: List[Dict],
        borrower_data: Optional[Dict],
        missing_docs: List[Dict],
        compliance_issues: List[Dict]
    ) -> Dict:
        """Build context for AI analysis."""
        return {
            "loan": {
                "loan_number": loan_data.get("loan_number"),
                "loan_type": loan_data.get("loan_type"),
                "amount": loan_data.get("amount"),
                "purchase_price": loan_data.get("purchase_price"),
                "ltv": loan_data.get("ltv"),
                "rate": loan_data.get("rate"),
                "stage": loan_data.get("stage"),
                "property_address": loan_data.get("property_address"),
            },
            "borrower": {
                "name": f"{borrower_data.get('first_name', '')} {borrower_data.get('last_name', '')}" if borrower_data else "Unknown",
                "credit_score": borrower_data.get("credit_score") if borrower_data else None,
                "dti": borrower_data.get("dti") if borrower_data else None,
            } if borrower_data else None,
            "documents": {
                "collected_count": len(documents),
                "collected": [
                    {"type": d.get("doc_type"), "status": d.get("status")}
                    for d in documents[:20]  # Limit for context
                ],
                "issues": [
                    d for d in documents
                    if d.get("detected_is_screenshot") or d.get("is_expired") or d.get("status") == "REJECTED"
                ][:10],
            },
            "conditions": {
                "total": len(conditions),
                "open": len([c for c in conditions if c.get("status") == "open"]),
                "details": conditions[:10],  # Limit for context
            },
            "missing_documents": missing_docs,
            "compliance_issues": compliance_issues,
        }

    def _get_ai_analysis(self, context: Dict) -> Dict:
        """Get AI-powered analysis of the loan file."""
        system_prompt = """You are an expert mortgage underwriter AI assistant analyzing a loan file for potential issues.

Your role is to:
1. Identify red flags that could cause underwriting kickbacks
2. Spot inconsistencies in the documentation
3. Highlight compliance concerns
4. Provide actionable recommendations to fix issues before submission

Be specific, practical, and prioritize issues by severity.
Return your analysis as JSON with these keys:
- summary: A 2-3 sentence executive summary of file health
- red_flags: Array of {severity: "critical"|"high"|"medium", issue: string, recommendation: string}
- recommendations: Array of specific actionable recommendations (strings)
- next_steps: Array of the top 3 immediate actions needed"""

        user_prompt = f"""Analyze this loan file for potential issues:

LOAN DETAILS:
{json.dumps(context['loan'], indent=2)}

BORROWER:
{json.dumps(context['borrower'], indent=2) if context['borrower'] else 'No borrower data'}

DOCUMENTS COLLECTED: {context['documents']['collected_count']}
{json.dumps(context['documents']['collected'][:10], indent=2)}

DOCUMENT ISSUES:
{json.dumps(context['documents']['issues'], indent=2) if context['documents']['issues'] else 'None detected'}

CONDITIONS:
Open: {context['conditions']['open']} of {context['conditions']['total']}
{json.dumps(context['conditions']['details'][:5], indent=2) if context['conditions']['details'] else 'None'}

MISSING DOCUMENTS:
{json.dumps(context['missing_documents'], indent=2) if context['missing_documents'] else 'None identified'}

COMPLIANCE ISSUES:
{json.dumps(context['compliance_issues'], indent=2) if context['compliance_issues'] else 'None identified'}

Provide your analysis as JSON."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            response_text = response.content[0].text

            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text)
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return {
                "summary": "Unable to complete AI analysis. Review file manually.",
                "red_flags": [],
                "recommendations": ["Complete AI analysis unavailable - manual review recommended"],
                "next_steps": ["Review missing documents", "Check compliance issues", "Clear open conditions"],
            }

    def _calculate_readiness_score(
        self,
        missing_docs: List[Dict],
        compliance_issues: List[Dict],
        conditions: List[Dict],
        red_flags: List[Dict]
    ) -> int:
        """Calculate file readiness score (0-100)."""
        score = 100

        # Deduct for missing documents
        for doc in missing_docs:
            if doc.get("priority") == "critical":
                score -= 10
            elif doc.get("priority") == "high":
                score -= 5
            else:
                score -= 2

        # Deduct for compliance issues
        for issue in compliance_issues:
            if issue.get("severity") == "critical":
                score -= 20
            elif issue.get("severity") == "high":
                score -= 10
            else:
                score -= 5

        # Deduct for open conditions
        open_conditions = [c for c in conditions if c.get("status") == "open"]
        score -= len(open_conditions) * 5

        # Deduct for red flags
        for flag in red_flags:
            if flag.get("severity") == "critical":
                score -= 15
            elif flag.get("severity") == "high":
                score -= 8
            else:
                score -= 3

        return max(0, min(100, score))

    def _score_to_grade(self, score: int) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _get_quick_issues(
        self,
        missing_docs: List[Dict],
        compliance_issues: List[Dict],
        open_conditions: List[Dict]
    ) -> List[str]:
        """Get quick issue summary."""
        issues = []

        critical_missing = [d for d in missing_docs if d.get("priority") == "critical"]
        if critical_missing:
            issues.append(f"{len(critical_missing)} critical documents missing")

        critical_compliance = [i for i in compliance_issues if i.get("severity") == "critical"]
        if critical_compliance:
            issues.append(f"{len(critical_compliance)} critical compliance issues")

        if open_conditions:
            issues.append(f"{len(open_conditions)} conditions need to be cleared")

        return issues
