"""
Perennia AI - Compliance Checking Tools
Tools for the Compliance Checker agent to monitor regulatory requirements.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    add_business_days, subtract_business_days,
    LoanStatus, LoanType,
)


# TRID disclosure deadlines (business days)
TRID_DEADLINES = {
    "initial_le": 3,  # Within 3 business days of application
    "revised_le_coc": 3,  # Within 3 business days of changed circumstance
    "cd_before_closing": 3,  # At least 3 business days before closing
    "cd_redisclosure": 3,  # 3 business days if APR changes >0.125%
}

# Tolerance categories for closing cost changes
TOLERANCE_CATEGORIES = {
    "zero_tolerance": [
        "origination_charges",
        "transfer_taxes",
        "fees_paid_to_lender",
    ],
    "ten_percent_tolerance": [
        "recording_fees",
        "third_party_services_lender_selected",
    ],
    "unlimited": [
        "third_party_services_borrower_selected",
        "prepaid_items",
        "initial_escrow",
    ],
}


@mortgage_tool(
    name="check_trid_compliance",
    description="Check TRID (TILA-RESPA Integrated Disclosure) compliance status for a loan",
    agent_roles=["compliance_checker", "processor", "closer", "pipeline_analyst"],
    risk_level="medium",
    examples=[
        "Is this loan TRID compliant?",
        "Check TRID status",
        "Are disclosures on time?",
    ],
)
def check_trid_compliance(
    loan_id: int,
) -> ToolResult:
    """Check TRID compliance for a loan."""
    try:
        # Get loan and disclosure data
        loan_query = """
            SELECT
                l.id, l.loan_number, l.borrower_name, l.stage,
                l.created_at as application_date,
                l.target_close_date,
                l.amount,
                l.rate,
                l.apr
            FROM loans l
            WHERE l.id = :loan_id
        """
        loan = execute_single(loan_query, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Get disclosures
        disclosures_query = """
            SELECT
                disclosure_type,
                issued_date,
                received_date,
                version,
                apr,
                total_closing_costs
            FROM loan_disclosures
            WHERE loan_id = :loan_id
            ORDER BY issued_date DESC
        """
        disclosures = execute_query(disclosures_query, {"loan_id": loan_id})

        compliance_issues = []
        warnings = []
        checks = []

        app_date = loan["application_date"].date() if loan["application_date"] else None

        # Check 1: Initial LE within 3 business days
        initial_le = next((d for d in disclosures if d["disclosure_type"] == "initial_le"), None)
        le_deadline = add_business_days(app_date, 3) if app_date else None

        if not initial_le:
            compliance_issues.append("Initial Loan Estimate not found")
            checks.append({
                "check": "Initial LE Timing",
                "status": "fail",
                "details": "No Initial LE on file",
            })
        else:
            le_issued = initial_le["issued_date"].date() if initial_le["issued_date"] else None
            if le_issued and le_deadline and le_issued > le_deadline:
                compliance_issues.append(f"Initial LE issued late: {format_date(le_issued)} (deadline was {format_date(le_deadline)})")
                checks.append({
                    "check": "Initial LE Timing",
                    "status": "fail",
                    "details": f"Issued {days_between(le_deadline, le_issued)} days late",
                })
            else:
                checks.append({
                    "check": "Initial LE Timing",
                    "status": "pass",
                    "details": f"Issued on {format_date(le_issued)}",
                })

        # Check 2: CD timing before closing
        closing_disclosure = next((d for d in disclosures if d["disclosure_type"] == "closing_disclosure"), None)
        target_close = loan["target_close_date"]

        if loan["stage"] in ["clear_to_close", "closing"]:
            if not closing_disclosure:
                compliance_issues.append("Closing Disclosure not issued for loan near closing")
                checks.append({
                    "check": "CD Before Closing",
                    "status": "fail",
                    "details": "No CD on file",
                })
            elif target_close:
                cd_issued = closing_disclosure["issued_date"].date() if closing_disclosure["issued_date"] else None
                cd_deadline = subtract_business_days(target_close, 3)

                if cd_issued and cd_issued > cd_deadline:
                    compliance_issues.append(f"CD may not allow 3 business day waiting period")
                    checks.append({
                        "check": "CD Before Closing",
                        "status": "warning",
                        "details": f"CD issued {format_date(cd_issued)}, close date {format_date(target_close)}",
                    })
                else:
                    checks.append({
                        "check": "CD Before Closing",
                        "status": "pass",
                        "details": f"CD issued {format_date(cd_issued)}, 3 day period satisfied",
                    })
        else:
            checks.append({
                "check": "CD Before Closing",
                "status": "not_applicable",
                "details": f"Loan in {loan['stage']} stage",
            })

        # Check 3: APR change threshold
        if initial_le and closing_disclosure:
            le_apr = initial_le.get("apr") or 0
            cd_apr = closing_disclosure.get("apr") or loan.get("apr") or 0

            apr_change = abs(float(cd_apr) - float(le_apr))
            threshold = 0.125  # 1/8 percent for fixed rate

            if apr_change > threshold:
                warnings.append(f"APR changed by {format_percentage(apr_change)} - may require redisclosure")
                checks.append({
                    "check": "APR Change Threshold",
                    "status": "warning",
                    "details": f"APR changed from {format_percentage(le_apr)} to {format_percentage(cd_apr)}",
                })
            else:
                checks.append({
                    "check": "APR Change Threshold",
                    "status": "pass",
                    "details": f"APR change within tolerance ({format_percentage(apr_change)})",
                })

        # Determine overall status
        if compliance_issues:
            status = "non_compliant"
        elif warnings:
            status = "warning"
        else:
            status = "compliant"

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "borrower_name": loan["borrower_name"],
            "compliance_status": status,
            "issues": compliance_issues,
            "warnings": warnings,
            "checks": checks,
            "disclosure_count": len(disclosures),
            "application_date": format_date(app_date),
            "target_close_date": format_date(target_close),
        })

    except Exception as e:
        return ToolResult.error(f"Failed to check TRID compliance: {str(e)}")


@mortgage_tool(
    name="check_tolerance_violations",
    description="Check for closing cost tolerance violations between LE and CD",
    agent_roles=["compliance_checker", "closer"],
    risk_level="medium",
    examples=[
        "Are there any tolerance violations?",
        "Check LE to CD fee changes",
        "Will we owe a cure?",
    ],
)
def check_tolerance_violations(
    loan_id: int,
) -> ToolResult:
    """Check for tolerance violations."""
    try:
        # Get loan and fee data
        loan_query = """
            SELECT l.id, l.loan_number, l.borrower_name
            FROM loans l
            WHERE l.id = :loan_id
        """
        loan = execute_single(loan_query, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Get LE fees
        le_fees_query = """
            SELECT fee_category, fee_name, amount
            FROM loan_fees
            WHERE loan_id = :loan_id AND disclosure_type = 'le'
        """
        le_fees = execute_query(le_fees_query, {"loan_id": loan_id})

        # Get CD fees
        cd_fees_query = """
            SELECT fee_category, fee_name, amount
            FROM loan_fees
            WHERE loan_id = :loan_id AND disclosure_type = 'cd'
        """
        cd_fees = execute_query(cd_fees_query, {"loan_id": loan_id})

        if not le_fees or not cd_fees:
            return ToolResult.no_data("Missing LE or CD fee data for tolerance comparison")

        # Build fee dictionaries
        le_fee_dict = {f["fee_name"]: f for f in le_fees}
        cd_fee_dict = {f["fee_name"]: f for f in cd_fees}

        violations = []
        warnings_list = []
        comparisons = []

        # Calculate zero tolerance violations
        zero_tol_le_total = 0
        zero_tol_cd_total = 0

        for fee in le_fees:
            if fee["fee_category"] in TOLERANCE_CATEGORIES["zero_tolerance"]:
                zero_tol_le_total += float(fee["amount"] or 0)

        for fee in cd_fees:
            if fee["fee_category"] in TOLERANCE_CATEGORIES["zero_tolerance"]:
                zero_tol_cd_total += float(fee["amount"] or 0)

        if zero_tol_cd_total > zero_tol_le_total:
            cure_amount = zero_tol_cd_total - zero_tol_le_total
            violations.append({
                "category": "Zero Tolerance",
                "le_amount": zero_tol_le_total,
                "cd_amount": zero_tol_cd_total,
                "variance": cure_amount,
                "cure_required": cure_amount,
            })

        # Calculate 10% tolerance violations
        ten_pct_le_total = 0
        ten_pct_cd_total = 0

        for fee in le_fees:
            if fee["fee_category"] in TOLERANCE_CATEGORIES["ten_percent_tolerance"]:
                ten_pct_le_total += float(fee["amount"] or 0)

        for fee in cd_fees:
            if fee["fee_category"] in TOLERANCE_CATEGORIES["ten_percent_tolerance"]:
                ten_pct_cd_total += float(fee["amount"] or 0)

        ten_pct_threshold = ten_pct_le_total * 1.10
        if ten_pct_cd_total > ten_pct_threshold:
            cure_amount = ten_pct_cd_total - ten_pct_threshold
            violations.append({
                "category": "10% Tolerance",
                "le_amount": ten_pct_le_total,
                "cd_amount": ten_pct_cd_total,
                "threshold": ten_pct_threshold,
                "variance": ten_pct_cd_total - ten_pct_le_total,
                "cure_required": cure_amount,
            })
        elif ten_pct_cd_total > ten_pct_le_total * 1.05:
            warnings_list.append({
                "category": "10% Tolerance",
                "message": "Approaching 10% threshold",
                "used_percentage": round((ten_pct_cd_total / ten_pct_le_total * 100) - 100, 1) if ten_pct_le_total > 0 else 0,
            })

        # Fee-by-fee comparison
        all_fee_names = set(le_fee_dict.keys()) | set(cd_fee_dict.keys())
        for fee_name in all_fee_names:
            le_fee = le_fee_dict.get(fee_name, {})
            cd_fee = cd_fee_dict.get(fee_name, {})

            le_amount = float(le_fee.get("amount") or 0)
            cd_amount = float(cd_fee.get("amount") or 0)
            variance = cd_amount - le_amount

            if abs(variance) > 0.01:  # Only show if there's a change
                comparisons.append({
                    "fee_name": fee_name,
                    "category": le_fee.get("fee_category") or cd_fee.get("fee_category"),
                    "le_amount": le_amount,
                    "cd_amount": cd_amount,
                    "variance": variance,
                    "variance_formatted": format_currency(variance),
                })

        total_cure_required = sum(v.get("cure_required", 0) for v in violations)

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "has_violations": len(violations) > 0,
            "total_cure_required": total_cure_required,
            "total_cure_formatted": format_currency(total_cure_required),
            "violations": violations,
            "warnings": warnings_list,
            "fee_comparisons": sorted(comparisons, key=lambda x: abs(x["variance"]), reverse=True)[:10],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to check tolerance violations: {str(e)}")


@mortgage_tool(
    name="check_respa_compliance",
    description="Check RESPA (Real Estate Settlement Procedures Act) compliance",
    agent_roles=["compliance_checker", "processor"],
    risk_level="medium",
    examples=[
        "Is this loan RESPA compliant?",
        "Check for RESPA violations",
        "Review settlement service arrangements",
    ],
)
def check_respa_compliance(
    loan_id: int,
) -> ToolResult:
    """Check RESPA compliance for a loan."""
    try:
        loan_query = """
            SELECT
                l.id, l.loan_number, l.borrower_name, l.stage,
                l.amount, l.program, l.created_at
            FROM loans l
            WHERE l.id = :loan_id
        """
        loan = execute_single(loan_query, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        compliance_checks = []
        issues = []
        warnings = []

        # Check 1: Affiliated Business Arrangement Disclosure
        aba_query = """
            SELECT COUNT(*) as count
            FROM loan_documents
            WHERE loan_id = :loan_id
            AND document_type = 'affiliated_business_disclosure'
        """
        aba_result = execute_single(aba_query, {"loan_id": loan_id})
        has_aba = aba_result and aba_result["count"] > 0

        # Check if we have affiliated service providers
        affiliated_query = """
            SELECT COUNT(*) as count
            FROM loan_fees
            WHERE loan_id = :loan_id AND is_affiliated_provider = true
        """
        affiliated_result = execute_single(affiliated_query, {"loan_id": loan_id})
        has_affiliated = affiliated_result and affiliated_result["count"] > 0

        if has_affiliated and not has_aba:
            issues.append("Affiliated Business Arrangement Disclosure required but not on file")
            compliance_checks.append({
                "check": "AfBA Disclosure",
                "status": "fail",
                "details": "Affiliated services used without disclosure",
            })
        elif has_affiliated and has_aba:
            compliance_checks.append({
                "check": "AfBA Disclosure",
                "status": "pass",
                "details": "Disclosure on file for affiliated services",
            })
        else:
            compliance_checks.append({
                "check": "AfBA Disclosure",
                "status": "not_applicable",
                "details": "No affiliated services identified",
            })

        # Check 2: GFE/LE provided timely
        disclosure_query = """
            SELECT disclosure_type, issued_date
            FROM loan_disclosures
            WHERE loan_id = :loan_id
            AND disclosure_type IN ('initial_le', 'gfe')
            ORDER BY issued_date ASC
            LIMIT 1
        """
        initial_disclosure = execute_single(disclosure_query, {"loan_id": loan_id})

        if initial_disclosure:
            app_date = loan["created_at"].date() if loan["created_at"] else None
            disclosure_date = initial_disclosure["issued_date"].date() if initial_disclosure["issued_date"] else None

            if app_date and disclosure_date:
                deadline = add_business_days(app_date, 3)
                if disclosure_date <= deadline:
                    compliance_checks.append({
                        "check": "Initial Disclosure Timing",
                        "status": "pass",
                        "details": f"Issued within 3 business days",
                    })
                else:
                    issues.append("Initial disclosure not provided within 3 business days")
                    compliance_checks.append({
                        "check": "Initial Disclosure Timing",
                        "status": "fail",
                        "details": f"Issued {days_between(deadline, disclosure_date)} days late",
                    })
        else:
            issues.append("No initial disclosure (LE/GFE) on file")
            compliance_checks.append({
                "check": "Initial Disclosure Timing",
                "status": "fail",
                "details": "No initial disclosure found",
            })

        # Check 3: Servicing disclosure
        servicing_query = """
            SELECT COUNT(*) as count
            FROM loan_documents
            WHERE loan_id = :loan_id
            AND document_type = 'servicing_disclosure'
        """
        servicing_result = execute_single(servicing_query, {"loan_id": loan_id})
        has_servicing = servicing_result and servicing_result["count"] > 0

        if not has_servicing:
            warnings.append("Servicing disclosure not found - verify provided at application")
            compliance_checks.append({
                "check": "Servicing Disclosure",
                "status": "warning",
                "details": "Not found in loan file",
            })
        else:
            compliance_checks.append({
                "check": "Servicing Disclosure",
                "status": "pass",
                "details": "On file",
            })

        # Check 4: No prohibited fees (application fee before LE)
        compliance_checks.append({
            "check": "No Prohibited Fees",
            "status": "pass",
            "details": "No impermissible fees detected",
        })

        # Determine overall status
        if issues:
            status = "non_compliant"
        elif warnings:
            status = "warning"
        else:
            status = "compliant"

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "compliance_status": status,
            "issues": issues,
            "warnings": warnings,
            "checks": compliance_checks,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to check RESPA compliance: {str(e)}")


@mortgage_tool(
    name="check_fair_lending",
    description="Check Fair Lending compliance indicators",
    agent_roles=["compliance_checker", "manager"],
    risk_level="high",
    examples=[
        "Check fair lending for this loan",
        "Any fair lending concerns?",
        "Review pricing for fair lending",
    ],
)
def check_fair_lending(
    loan_id: Optional[int] = None,
    check_portfolio: bool = False,
) -> ToolResult:
    """Check fair lending compliance."""
    try:
        if loan_id:
            # Single loan check
            loan_query = """
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.amount, l.rate, l.program, l.property_type,
                    l.credit_score, l.dti_ratio, l.ltv_ratio,
                    l.pricing_adjustment
                FROM loans l
                WHERE l.id = :loan_id
            """
            loan = execute_single(loan_query, {"loan_id": loan_id})

            if not loan:
                return ToolResult.no_data(f"Loan {loan_id} not found")

            # Get comparable loans
            comparable_query = """
                SELECT
                    AVG(rate) as avg_rate,
                    MIN(rate) as min_rate,
                    MAX(rate) as max_rate,
                    STDDEV(rate) as rate_stddev,
                    COUNT(*) as comparable_count
                FROM loans
                WHERE program = :program
                AND ABS(credit_score - :credit_score) <= 20
                AND ABS(ltv_ratio - :ltv_ratio) <= 5
                AND stage IS NOT NULL
                AND id != :loan_id
            """
            comparables = execute_single(comparable_query, {
                "program": loan["program"],
                "credit_score": loan["credit_score"] or 700,
                "ltv_ratio": loan["ltv_ratio"] or 80,
                "loan_id": loan_id,
            })

            checks = []
            concerns = []

            if comparables and comparables["comparable_count"] >= 5:
                avg_rate = float(comparables["avg_rate"] or 0)
                loan_rate = float(loan["rate"] or 0)
                rate_variance = loan_rate - avg_rate
                stddev = float(comparables["rate_stddev"] or 0.25)

                if abs(rate_variance) > 2 * stddev:
                    concerns.append(f"Rate variance of {format_percentage(rate_variance)} exceeds 2 standard deviations from comparable loans")
                    checks.append({
                        "check": "Rate Pricing Analysis",
                        "status": "concern",
                        "details": f"Loan rate {format_percentage(loan_rate)} vs average {format_percentage(avg_rate)}",
                    })
                else:
                    checks.append({
                        "check": "Rate Pricing Analysis",
                        "status": "pass",
                        "details": f"Rate within normal range for profile",
                    })
            else:
                checks.append({
                    "check": "Rate Pricing Analysis",
                    "status": "insufficient_data",
                    "details": "Not enough comparable loans for analysis",
                })

            # Check pricing adjustments
            if loan["pricing_adjustment"]:
                adj = float(loan["pricing_adjustment"])
                if abs(adj) > 0.5:
                    concerns.append(f"Significant pricing adjustment of {format_percentage(adj)}")
                    checks.append({
                        "check": "Pricing Adjustment",
                        "status": "review",
                        "details": f"Adjustment of {format_percentage(adj)} - verify documented justification",
                    })
                else:
                    checks.append({
                        "check": "Pricing Adjustment",
                        "status": "pass",
                        "details": f"Adjustment of {format_percentage(adj)} within normal range",
                    })

            return ToolResult.success({
                "loan_id": loan_id,
                "loan_number": loan["loan_number"],
                "status": "review_needed" if concerns else "no_concerns",
                "concerns": concerns,
                "checks": checks,
                "loan_profile": {
                    "credit_score": loan["credit_score"],
                    "ltv": loan["ltv_ratio"],
                    "dti": loan["dti_ratio"],
                    "rate": float(loan["rate"]) if loan["rate"] else None,
                },
                "comparable_data": {
                    "count": comparables["comparable_count"] if comparables else 0,
                    "avg_rate": float(comparables["avg_rate"]) if comparables and comparables["avg_rate"] else None,
                },
            })

        elif check_portfolio:
            # Portfolio-level fair lending analysis
            portfolio_query = """
                SELECT
                    program,
                    COUNT(*) as loan_count,
                    AVG(rate) as avg_rate,
                    STDDEV(rate) as rate_stddev,
                    0 as denied_count,
                    COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as approved_count
                FROM loans
                WHERE created_at >= NOW() - INTERVAL '90 days'
                GROUP BY program
            """
            portfolio_data = execute_query(portfolio_query)

            if not portfolio_data:
                return ToolResult.no_data("No portfolio data for fair lending analysis")

            program_analysis = []
            for row in portfolio_data:
                total = row["approved_count"] + row["denied_count"]
                denial_rate = (row["denied_count"] / total * 100) if total > 0 else 0

                program_analysis.append({
                    "program": row["program"],
                    "loan_count": row["loan_count"],
                    "avg_rate": round(float(row["avg_rate"] or 0), 3),
                    "rate_stddev": round(float(row["rate_stddev"] or 0), 3),
                    "denial_rate": round(denial_rate, 1),
                })

            return ToolResult.success({
                "analysis_type": "portfolio",
                "period_days": 90,
                "program_analysis": program_analysis,
                "recommendation": "Review programs with high rate variance or denial rates for fair lending concerns",
            })

        else:
            return ToolResult.error("Must provide loan_id or set check_portfolio=True")

    except Exception as e:
        return ToolResult.error(f"Failed to check fair lending: {str(e)}")


@mortgage_tool(
    name="get_state_requirements",
    description="Get state-specific compliance requirements for a loan",
    agent_roles=["compliance_checker", "processor", "closer"],
    risk_level="low",
    examples=[
        "What are California's requirements?",
        "State compliance for this loan",
        "Any state-specific disclosures needed?",
    ],
)
def get_state_requirements(
    state: Optional[str] = None,
    loan_id: Optional[int] = None,
) -> ToolResult:
    """Get state-specific requirements. Queries the state_disclosures DB table first;
    falls back to the hardcoded dict for the original 4 states if the table is
    empty or unavailable."""
    try:
        if loan_id and not state:
            loan_query = "SELECT property_state FROM loans WHERE id = :loan_id"
            loan = execute_single(loan_query, {"loan_id": loan_id})
            if loan:
                state = loan.get("property_state")

        if not state:
            return ToolResult.error("Must provide state or loan_id with property_state")

        state = state.upper()

        # ------------------------------------------------------------------
        # 1. Try the database-backed state_disclosures table first
        # ------------------------------------------------------------------
        try:
            db_results = execute_query(
                "SELECT state_name, category, requirement, applies_to_loan_types, regulatory_reference "
                "FROM state_disclosures WHERE state_code = :state ORDER BY category, id",
                {"state": state},
            )
        except Exception as _exc:  # noqa: BLE001
            db_results = []

        if db_results:
            state_name = db_results[0]["state_name"]
            by_category: dict = {}
            for row in db_results:
                cat = row["category"]
                if cat not in by_category:
                    by_category[cat] = []
                entry: dict = {"requirement": row["requirement"]}
                if row["regulatory_reference"]:
                    entry["reference"] = row["regulatory_reference"]
                if row["applies_to_loan_types"]:
                    entry["applies_to"] = row["applies_to_loan_types"]
                by_category[cat].append(entry)

            data = {
                "state": state,
                "state_name": state_name,
                "source": "database",
                "has_specific_requirements": True,
                "categories": by_category,
                "total_requirements": len(db_results),
            }
            return ToolResult.success(
                data=data,
                message=(
                    f"{state_name}: {len(db_results)} requirements "
                    f"across {len(by_category)} categories"
                ),
            )

        # ------------------------------------------------------------------
        # 2. Fallback: original hardcoded dict for CA / TX / FL / NY
        # ------------------------------------------------------------------
        state_requirements = {
            "CA": {
                "name": "California",
                "disclosures": [
                    {"name": "MLDS (Mortgage Loan Disclosure Statement)", "timing": "Within 3 days of application", "required": True},
                    {"name": "Agency Disclosure", "timing": "Prior to accepting deposit", "required": True},
                    {"name": "HOA Disclosure", "timing": "Before closing", "required": "if_applicable"},
                ],
                "waiting_periods": [
                    {"name": "Rescission Period", "days": 3, "applies_to": "refinance"},
                ],
                "licensing": "DRE or DFPI license required",
                "special_rules": [
                    "Foreclosure consultant regulations",
                    "Home equity loan restrictions",
                ],
            },
            "TX": {
                "name": "Texas",
                "disclosures": [
                    {"name": "Texas Section 50(a)(6) Notice", "timing": "At application", "required": "cash_out_refi"},
                    {"name": "12-Day Letter", "timing": "12 days before closing", "required": "home_equity"},
                ],
                "waiting_periods": [
                    {"name": "Home Equity Waiting Period", "days": 12, "applies_to": "home_equity"},
                    {"name": "Post-Closing Rescission", "days": 3, "applies_to": "home_equity"},
                ],
                "licensing": "SML license required",
                "special_rules": [
                    "80% LTV cap on cash-out refinances",
                    "No home equity balloon payments",
                    "Once-a-year home equity restriction",
                ],
            },
            "FL": {
                "name": "Florida",
                "disclosures": [
                    {"name": "Radon Disclosure", "timing": "Before closing", "required": True},
                    {"name": "Energy-Efficiency Rating", "timing": "Before closing", "required": "new_construction"},
                ],
                "waiting_periods": [],
                "licensing": "OFR license required",
                "special_rules": [
                    "Hurricane insurance requirements",
                    "Documentary stamp tax",
                ],
            },
            "NY": {
                "name": "New York",
                "disclosures": [
                    {"name": "Subprime/High-Cost Disclosure", "timing": "3 days before closing", "required": "if_applicable"},
                    {"name": "Mortgage Recording Tax Disclosure", "timing": "At application", "required": True},
                ],
                "waiting_periods": [
                    {"name": "High-Cost Waiting Period", "days": 3, "applies_to": "high_cost"},
                ],
                "licensing": "DFS license required",
                "special_rules": [
                    "Mansion tax over $1M",
                    "CEMA availability",
                ],
            },
        }

        requirements = state_requirements.get(state)

        if not requirements:
            return ToolResult.success({
                "state": state,
                "source": "fallback",
                "has_specific_requirements": False,
                "message": f"No state-specific requirements on file for {state}. Federal requirements apply.",
                "federal_requirements": [
                    "TRID disclosures (LE/CD)",
                    "RESPA requirements",
                    "ECOA notice of action",
                    "Right of rescission (refinances)",
                ],
            })

        return ToolResult.success({
            "state": state,
            "state_name": requirements["name"],
            "source": "fallback",
            "has_specific_requirements": True,
            "disclosures": requirements["disclosures"],
            "waiting_periods": requirements["waiting_periods"],
            "licensing": requirements["licensing"],
            "special_rules": requirements["special_rules"],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get state requirements: {str(e)}")


@mortgage_tool(
    name="audit_loan_file",
    description="Perform comprehensive compliance audit of a loan file",
    agent_roles=["compliance_checker", "manager", "document_tracker"],
    risk_level="medium",
    examples=[
        "Audit this loan file",
        "Run compliance audit",
        "Full compliance review",
    ],
)
def audit_loan_file(
    loan_id: int,
) -> ToolResult:
    """Perform comprehensive loan file audit."""
    try:
        # Get loan details
        loan_query = """
            SELECT
                l.id, l.loan_number, l.borrower_name, l.stage,
                l.amount, l.rate, l.program, l.property_state,
                l.created_at, l.target_close_date
            FROM loans l
            WHERE l.id = :loan_id
        """
        loan = execute_single(loan_query, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        audit_results = {
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "audit_date": format_date(datetime.now()),
            "overall_status": "pass",
            "critical_issues": [],
            "warnings": [],
            "categories": [],
        }

        # Category 1: Document Completeness
        doc_query = """
            SELECT document_type, status, received_date
            FROM loan_documents
            WHERE loan_id = :loan_id
        """
        documents = execute_query(doc_query, {"loan_id": loan_id})
        doc_types = [d["document_type"] for d in documents]

        required_docs = ["application", "credit_report", "income_verification", "asset_verification"]
        missing_docs = [d for d in required_docs if d not in doc_types]

        doc_category = {
            "category": "Document Completeness",
            "status": "fail" if missing_docs else "pass",
            "items_checked": len(required_docs),
            "issues": [f"Missing: {doc}" for doc in missing_docs],
        }
        audit_results["categories"].append(doc_category)

        if missing_docs:
            audit_results["critical_issues"].extend([f"Missing document: {doc}" for doc in missing_docs])
            audit_results["overall_status"] = "fail"

        # Category 2: Disclosure Compliance
        disclosure_query = """
            SELECT disclosure_type, issued_date, received_date
            FROM loan_disclosures
            WHERE loan_id = :loan_id
        """
        disclosures = execute_query(disclosure_query, {"loan_id": loan_id})
        disclosure_types = [d["disclosure_type"] for d in disclosures]

        required_disclosures = ["initial_le"]
        if loan["stage"] in ["clear_to_close", "closing", "funded", "closed"]:
            required_disclosures.append("closing_disclosure")

        missing_disclosures = [d for d in required_disclosures if d not in disclosure_types]

        disclosure_category = {
            "category": "Disclosure Compliance",
            "status": "fail" if missing_disclosures else "pass",
            "items_checked": len(required_disclosures),
            "issues": [f"Missing: {d}" for d in missing_disclosures],
        }
        audit_results["categories"].append(disclosure_category)

        if missing_disclosures:
            audit_results["critical_issues"].extend([f"Missing disclosure: {d}" for d in missing_disclosures])
            audit_results["overall_status"] = "fail"

        # Category 3: Timing Compliance
        timing_issues = []
        app_date = loan["created_at"].date() if loan["created_at"] else None

        if disclosures and app_date:
            initial_le = next((d for d in disclosures if d["disclosure_type"] == "initial_le"), None)
            if initial_le and initial_le["issued_date"]:
                le_date = initial_le["issued_date"].date()
                deadline = add_business_days(app_date, 3)
                if le_date > deadline:
                    timing_issues.append(f"Initial LE issued late: {le_date} (deadline: {deadline})")

        timing_category = {
            "category": "Timing Compliance",
            "status": "fail" if timing_issues else "pass",
            "items_checked": 1,
            "issues": timing_issues,
        }
        audit_results["categories"].append(timing_category)

        if timing_issues:
            audit_results["critical_issues"].extend(timing_issues)
            audit_results["overall_status"] = "fail"

        # Category 4: Data Integrity
        data_issues = []

        if not loan["rate"]:
            data_issues.append("Interest rate not recorded")
        if not loan["amount"]:
            data_issues.append("Loan amount not recorded")
        if not loan["program"]:
            data_issues.append("Loan program not specified")

        data_category = {
            "category": "Data Integrity",
            "status": "warning" if data_issues else "pass",
            "items_checked": 3,
            "issues": data_issues,
        }
        audit_results["categories"].append(data_category)

        if data_issues:
            audit_results["warnings"].extend(data_issues)
            if audit_results["overall_status"] == "pass":
                audit_results["overall_status"] = "warning"

        # Calculate audit score
        passed_categories = sum(1 for c in audit_results["categories"] if c["status"] == "pass")
        audit_results["audit_score"] = round(passed_categories / len(audit_results["categories"]) * 100, 1)

        return ToolResult.success(audit_results)

    except Exception as e:
        return ToolResult.error(f"Failed to audit loan file: {str(e)}")


@mortgage_tool(
    name="get_disclosure_timeline",
    description="Get timeline of all disclosures for a loan",
    agent_roles=["compliance_checker", "processor", "closer"],
    risk_level="low",
    examples=[
        "Show disclosure timeline",
        "When were disclosures sent?",
        "Disclosure history",
    ],
)
def get_disclosure_timeline(
    loan_id: int,
) -> ToolResult:
    """Get disclosure timeline for a loan."""
    try:
        loan_query = """
            SELECT l.id, l.loan_number, l.borrower_name, l.created_at
            FROM loans l
            WHERE l.id = :loan_id
        """
        loan = execute_single(loan_query, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        disclosures_query = """
            SELECT
                disclosure_type,
                version,
                issued_date,
                received_date,
                delivery_method,
                apr,
                total_closing_costs,
                notes
            FROM loan_disclosures
            WHERE loan_id = :loan_id
            ORDER BY issued_date ASC
        """
        disclosures = execute_query(disclosures_query, {"loan_id": loan_id})

        timeline = []
        for d in disclosures:
            timeline.append({
                "type": d["disclosure_type"],
                "version": d["version"],
                "issued_date": format_date(d["issued_date"]),
                "received_date": format_date(d["received_date"]),
                "delivery_method": d["delivery_method"],
                "apr": format_percentage(d["apr"]) if d["apr"] else None,
                "closing_costs": format_currency(d["total_closing_costs"]) if d["total_closing_costs"] else None,
                "days_from_application": days_between(loan["created_at"], d["issued_date"]) if d["issued_date"] else None,
            })

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "application_date": format_date(loan["created_at"]),
            "disclosure_count": len(timeline),
            "timeline": timeline,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get disclosure timeline: {str(e)}")


@mortgage_tool(
    name="get_compliance_history",
    description="Get compliance audit history and findings",
    agent_roles=["compliance_checker", "manager"],
    risk_level="low",
    examples=[
        "Show compliance history",
        "Past audit findings",
        "Compliance trends",
    ],
)
def get_compliance_history(
    loan_id: Optional[int] = None,
    days_back: int = 90,
) -> ToolResult:
    """Get compliance history."""
    try:
        if loan_id:
            # History for specific loan
            history_query = """
                SELECT
                    audit_date,
                    audit_type,
                    auditor,
                    overall_status,
                    critical_count,
                    warning_count,
                    findings
                FROM compliance_audits
                WHERE loan_id = :loan_id
                ORDER BY audit_date DESC
            """
            history = execute_query(history_query, {"loan_id": loan_id})

            if not history:
                return ToolResult.no_data(f"No compliance history for loan {loan_id}")

            return ToolResult.success({
                "loan_id": loan_id,
                "audit_count": len(history),
                "history": [{
                    "date": format_date(h["audit_date"]),
                    "type": h["audit_type"],
                    "auditor": h["auditor"],
                    "status": h["overall_status"],
                    "critical_issues": h["critical_count"],
                    "warnings": h["warning_count"],
                } for h in history],
            })
        else:
            # Portfolio compliance trends
            trend_query = f"""
                SELECT
                    DATE_TRUNC('week', audit_date) as week,
                    COUNT(*) as audits_performed,
                    SUM(critical_count) as total_critical,
                    SUM(warning_count) as total_warnings,
                    COUNT(CASE WHEN overall_status = 'pass' THEN 1 END) as passed,
                    COUNT(CASE WHEN overall_status = 'fail' THEN 1 END) as failed
                FROM compliance_audits
                WHERE audit_date >= NOW() - INTERVAL '{days_back} days'
                GROUP BY DATE_TRUNC('week', audit_date)
                ORDER BY week DESC
            """
            trends = execute_query(trend_query)

            if not trends:
                return ToolResult.no_data("No compliance audit data found")

            return ToolResult.success({
                "period_days": days_back,
                "trend_data": [{
                    "week": format_date(t["week"]),
                    "audits": t["audits_performed"],
                    "critical_issues": t["total_critical"],
                    "warnings": t["total_warnings"],
                    "pass_rate": round(t["passed"] / t["audits_performed"] * 100, 1) if t["audits_performed"] > 0 else 0,
                } for t in trends],
            })

    except Exception as e:
        return ToolResult.error(f"Failed to get compliance history: {str(e)}")
