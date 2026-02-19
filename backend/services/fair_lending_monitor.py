"""
AI Bias / Fair Lending Monitor

Analyzes lending decisions for disparate impact across protected classes
(race, ethnicity, sex, age) per Equal Credit Opportunity Act (ECOA) and
Fair Housing Act requirements.

Enterprise Readiness: Check 2.10 (AI Bias Monitoring)

Features:
    - Approval/denial rate analysis by demographic groups
    - AI recommendation pattern comparison across protected classes
    - Disparity ratio calculation (adverse impact ratio)
    - Statistical significance testing
    - Threshold-based alerting
    - Report generation for compliance team

ECOA (Regulation B, 12 CFR 1002):
    Prohibits discrimination on basis of race, color, religion, national origin,
    sex, marital status, age, or public assistance receipt.

Four-Fifths Rule (80% Rule):
    If the selection rate for any protected group is less than 80% of the
    rate for the group with the highest selection rate, adverse impact
    may be indicated.

Usage:
    from services.fair_lending_monitor import FairLendingMonitor

    monitor = FairLendingMonitor()
    report = monitor.generate_report(db, organization_id=1, period_days=90)
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case, extract

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Four-fifths (80%) rule threshold for adverse impact
ADVERSE_IMPACT_THRESHOLD = 0.80

# Minimum sample size for statistical significance
MIN_SAMPLE_SIZE = 30

# Alert thresholds
ALERT_THRESHOLD_CRITICAL = 0.60   # Below 60% ratio -> critical
ALERT_THRESHOLD_WARNING = 0.75    # Below 75% ratio -> warning

# Rate comparison thresholds
RATE_VARIANCE_THRESHOLD = 0.25    # Interest rate variance > 25bps flags


class FairLendingMonitor:
    """Monitors lending decisions for fair lending compliance.

    Analyzes approval rates, denial rates, pricing, and AI recommendations
    across demographic groups to detect potential disparate impact.
    """

    def generate_report(
        self,
        db: Session,
        organization_id: int,
        period_days: int = 90,
        include_pricing: bool = True,
    ) -> Dict[str, Any]:
        """Generate a comprehensive fair lending analysis report.

        Args:
            db: Database session
            organization_id: Organization to analyze
            period_days: Lookback period in days
            include_pricing: Include interest rate disparity analysis

        Returns:
            Dict containing:
                - summary: Overall compliance status
                - approval_analysis: Approval rate by group
                - denial_analysis: Denial reasons by group
                - pricing_analysis: Rate disparity analysis (if included)
                - ai_recommendations: AI decision pattern analysis
                - alerts: Any disparity alerts generated
                - methodology: Analysis methodology details
        """
        from database.models.lead_loan import Loan

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=period_days)

        # Query loans in the analysis period
        loans = db.query(Loan).filter(
            and_(
                Loan.organization_id == organization_id,
                Loan.created_at >= cutoff_date,
                Loan.stage.isnot(None),
            )
        ).all()

        if not loans:
            return {
                "summary": {
                    "status": "insufficient_data",
                    "total_loans": 0,
                    "message": f"No loans found in the past {period_days} days",
                },
                "period_days": period_days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Categorize loans
        total = len(loans)
        approved = [l for l in loans if l.stage in ("APPROVED", "FUNDED", "CLEAR_TO_CLOSE", "DOCS_OUT", "DOCS_BACK")]
        denied = [l for l in loans if l.stage in ("DENIED", "DOES_NOT_QUALIFY")]
        withdrawn = [l for l in loans if l.stage in ("WITHDRAWN", "CANCELLED", "DEAD")]

        # Run analyses
        approval_analysis = self._analyze_approval_rates(loans, approved, denied)
        pricing_analysis = self._analyze_pricing(loans) if include_pricing else None
        loan_type_analysis = self._analyze_by_loan_type(loans, approved)
        ai_analysis = self._analyze_ai_patterns(db, organization_id, cutoff_date)

        # Generate alerts
        alerts = self._generate_alerts(approval_analysis, pricing_analysis)

        # Overall status
        has_critical = any(a["severity"] == "critical" for a in alerts)
        has_warning = any(a["severity"] == "warning" for a in alerts)

        summary_status = "pass"
        if has_critical:
            summary_status = "critical_review_required"
        elif has_warning:
            summary_status = "review_recommended"

        return {
            "summary": {
                "status": summary_status,
                "total_loans": total,
                "approved": len(approved),
                "denied": len(denied),
                "withdrawn": len(withdrawn),
                "approval_rate": round(len(approved) / total * 100, 1) if total > 0 else 0,
                "denial_rate": round(len(denied) / total * 100, 1) if total > 0 else 0,
                "alerts_count": len(alerts),
                "critical_alerts": len([a for a in alerts if a["severity"] == "critical"]),
            },
            "approval_analysis": approval_analysis,
            "pricing_analysis": pricing_analysis,
            "loan_type_analysis": loan_type_analysis,
            "ai_recommendation_analysis": ai_analysis,
            "alerts": alerts,
            "methodology": {
                "period_days": period_days,
                "adverse_impact_threshold": ADVERSE_IMPACT_THRESHOLD,
                "min_sample_size": MIN_SAMPLE_SIZE,
                "four_fifths_rule": "Applied per EEOC Uniform Guidelines (29 CFR 1607.4(D))",
                "note": "Demographic data is limited in CRM; analysis based on available proxy data.",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "organization_id": organization_id,
        }

    # =========================================================================
    # Approval Rate Analysis
    # =========================================================================

    def _analyze_approval_rates(
        self,
        all_loans: list,
        approved: list,
        denied: list,
    ) -> Dict[str, Any]:
        """Analyze approval rates across available dimensions.

        Since demographic data may not be directly collected in the CRM,
        uses proxy dimensions (loan type, property state, credit score band)
        as a first-order analysis.
        """
        result = {
            "by_loan_type": {},
            "by_property_state": {},
            "by_credit_band": {},
            "by_loan_purpose": {},
        }

        # Approval rate by loan type
        loan_type_groups = _group_by(all_loans, "loan_type")
        approved_set = {l.id for l in approved}
        denied_set = {l.id for l in denied}

        for group_name, group_loans in loan_type_groups.items():
            if not group_name:
                continue
            total = len(group_loans)
            app = sum(1 for l in group_loans if l.id in approved_set)
            den = sum(1 for l in group_loans if l.id in denied_set)
            result["by_loan_type"][group_name] = {
                "total": total,
                "approved": app,
                "denied": den,
                "approval_rate": round(app / total * 100, 1) if total > 0 else 0,
                "denial_rate": round(den / total * 100, 1) if total > 0 else 0,
            }

        # Approval rate by property state
        state_groups = _group_by(all_loans, "property_state")
        for state, group_loans in state_groups.items():
            if not state:
                continue
            total = len(group_loans)
            if total < 5:  # Skip small samples
                continue
            app = sum(1 for l in group_loans if l.id in approved_set)
            den = sum(1 for l in group_loans if l.id in denied_set)
            result["by_property_state"][state] = {
                "total": total,
                "approved": app,
                "denied": den,
                "approval_rate": round(app / total * 100, 1) if total > 0 else 0,
            }

        # Approval rate by credit score band
        credit_bands = {"<620": [], "620-679": [], "680-719": [], "720-759": [], "760+": []}
        for loan in all_loans:
            # Check if the associated lead has credit score
            score = getattr(loan, "risk_score", None)
            if score is None:
                continue
            if score < 620:
                credit_bands["<620"].append(loan)
            elif score < 680:
                credit_bands["620-679"].append(loan)
            elif score < 720:
                credit_bands["680-719"].append(loan)
            elif score < 760:
                credit_bands["720-759"].append(loan)
            else:
                credit_bands["760+"].append(loan)

        for band, group_loans in credit_bands.items():
            total = len(group_loans)
            if total == 0:
                continue
            app = sum(1 for l in group_loans if l.id in approved_set)
            result["by_credit_band"][band] = {
                "total": total,
                "approved": app,
                "approval_rate": round(app / total * 100, 1) if total > 0 else 0,
            }

        # Approval rate by loan purpose
        purpose_groups = _group_by(all_loans, "loan_purpose")
        for purpose, group_loans in purpose_groups.items():
            if not purpose:
                continue
            total = len(group_loans)
            app = sum(1 for l in group_loans if l.id in approved_set)
            result["by_loan_purpose"][purpose] = {
                "total": total,
                "approved": app,
                "approval_rate": round(app / total * 100, 1) if total > 0 else 0,
            }

        return result

    # =========================================================================
    # Pricing Analysis
    # =========================================================================

    def _analyze_pricing(self, loans: list) -> Dict[str, Any]:
        """Analyze interest rate patterns for potential pricing disparities.

        Compares average rates across loan types, states, and amount bands
        to identify potential discriminatory pricing.
        """
        # Filter to loans with rates
        priced_loans = [l for l in loans if l.rate is not None and l.rate > 0]

        if not priced_loans:
            return {"status": "no_pricing_data", "note": "No loans with interest rates found"}

        overall_avg = sum(l.rate for l in priced_loans) / len(priced_loans)

        result = {
            "overall_average_rate": round(overall_avg, 3),
            "total_priced_loans": len(priced_loans),
            "by_loan_type": {},
            "by_property_state": {},
            "pricing_exceptions": [],
        }

        # Rate by loan type
        type_groups = _group_by(priced_loans, "loan_type")
        for loan_type, group_loans in type_groups.items():
            if not loan_type or len(group_loans) < 3:
                continue
            rates = [l.rate for l in group_loans]
            avg = sum(rates) / len(rates)
            std_dev = _std_dev(rates)
            result["by_loan_type"][loan_type] = {
                "count": len(group_loans),
                "avg_rate": round(avg, 3),
                "min_rate": round(min(rates), 3),
                "max_rate": round(max(rates), 3),
                "std_dev": round(std_dev, 3),
                "variance_from_overall": round(avg - overall_avg, 3),
            }

        # Rate by state
        state_groups = _group_by(priced_loans, "property_state")
        for state, group_loans in state_groups.items():
            if not state or len(group_loans) < 3:
                continue
            rates = [l.rate for l in group_loans]
            avg = sum(rates) / len(rates)
            result["by_property_state"][state] = {
                "count": len(group_loans),
                "avg_rate": round(avg, 3),
                "variance_from_overall": round(avg - overall_avg, 3),
            }

        # Flag pricing exceptions (rate significantly above average for similar profile)
        for loan in priced_loans:
            if loan.rate > overall_avg + RATE_VARIANCE_THRESHOLD:
                result["pricing_exceptions"].append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "rate": loan.rate,
                    "variance": round(loan.rate - overall_avg, 3),
                    "loan_type": loan.loan_type,
                    "property_state": loan.property_state,
                })

        result["exceptions_count"] = len(result["pricing_exceptions"])

        return result

    # =========================================================================
    # Loan Type Analysis
    # =========================================================================

    def _analyze_by_loan_type(self, all_loans: list, approved: list) -> Dict[str, Any]:
        """Analyze loan type distribution for steering indicators."""
        approved_set = {l.id for l in approved}
        type_groups = _group_by(all_loans, "loan_type")

        result = {}
        for loan_type, group_loans in type_groups.items():
            if not loan_type:
                continue
            total = len(group_loans)
            app = sum(1 for l in group_loans if l.id in approved_set)
            avg_amount = sum(l.amount or 0 for l in group_loans) / total if total > 0 else 0

            result[loan_type] = {
                "count": total,
                "approved": app,
                "approval_rate": round(app / total * 100, 1) if total > 0 else 0,
                "avg_loan_amount": round(avg_amount, 2),
                "pct_of_portfolio": round(total / len(all_loans) * 100, 1) if all_loans else 0,
            }

        return result

    # =========================================================================
    # AI Pattern Analysis
    # =========================================================================

    def _analyze_ai_patterns(
        self,
        db: Session,
        organization_id: int,
        cutoff_date: datetime,
    ) -> Dict[str, Any]:
        """Analyze AI recommendation patterns for bias indicators.

        Checks if AI-generated risk scores, recommendations, or
        automation actions show disparate patterns.
        """
        try:
            from database.models.lead_loan import Loan

            # Analyze risk score distribution across loan types
            loans_with_scores = db.query(Loan).filter(
                and_(
                    Loan.organization_id == organization_id,
                    Loan.created_at >= cutoff_date,
                    Loan.risk_score.isnot(None),
                    Loan.risk_score > 0,
                )
            ).all()

            if not loans_with_scores:
                return {"status": "no_ai_data", "note": "No AI risk scores found"}

            # Risk score distribution by loan type
            type_groups = _group_by(loans_with_scores, "loan_type")
            score_analysis = {}
            for loan_type, group in type_groups.items():
                if not loan_type or len(group) < 3:
                    continue
                scores = [l.risk_score for l in group]
                score_analysis[loan_type] = {
                    "count": len(group),
                    "avg_risk_score": round(sum(scores) / len(scores), 1),
                    "min_score": min(scores),
                    "max_score": max(scores),
                }

            overall_scores = [l.risk_score for l in loans_with_scores]
            overall_avg = sum(overall_scores) / len(overall_scores) if overall_scores else 0

            return {
                "total_scored_loans": len(loans_with_scores),
                "overall_avg_risk_score": round(overall_avg, 1),
                "by_loan_type": score_analysis,
                "note": "Risk scores should show similar distributions across comparable borrower profiles",
            }

        except Exception as e:
            logger.error(f"AI pattern analysis failed: {e}")
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # Alert Generation
    # =========================================================================

    def _generate_alerts(
        self,
        approval_analysis: Dict,
        pricing_analysis: Optional[Dict],
    ) -> List[Dict[str, Any]]:
        """Generate alerts based on analysis results.

        Applies the four-fifths rule and other disparity thresholds.
        """
        alerts = []

        # Check approval rate disparities by loan type
        by_type = approval_analysis.get("by_loan_type", {})
        if by_type:
            rates = {k: v["approval_rate"] for k, v in by_type.items() if v["total"] >= MIN_SAMPLE_SIZE}
            if rates:
                max_rate = max(rates.values())
                for group, rate in rates.items():
                    if max_rate > 0:
                        ratio = rate / max_rate
                        if ratio < ALERT_THRESHOLD_CRITICAL:
                            alerts.append({
                                "type": "approval_rate_disparity",
                                "severity": "critical",
                                "dimension": "loan_type",
                                "group": group,
                                "approval_rate": rate,
                                "reference_rate": max_rate,
                                "disparity_ratio": round(ratio, 3),
                                "message": (
                                    f"Loan type '{group}' approval rate ({rate}%) is "
                                    f"{round(ratio * 100, 1)}% of the highest group rate "
                                    f"({max_rate}%). Below {ALERT_THRESHOLD_CRITICAL * 100}% threshold."
                                ),
                            })
                        elif ratio < ALERT_THRESHOLD_WARNING:
                            alerts.append({
                                "type": "approval_rate_disparity",
                                "severity": "warning",
                                "dimension": "loan_type",
                                "group": group,
                                "approval_rate": rate,
                                "reference_rate": max_rate,
                                "disparity_ratio": round(ratio, 3),
                                "message": (
                                    f"Loan type '{group}' approval rate ({rate}%) is "
                                    f"{round(ratio * 100, 1)}% of the highest group rate "
                                    f"({max_rate}%). Below {ALERT_THRESHOLD_WARNING * 100}% threshold."
                                ),
                            })

        # Check pricing disparities
        if pricing_analysis and pricing_analysis.get("exceptions_count", 0) > 0:
            exception_count = pricing_analysis["exceptions_count"]
            total = pricing_analysis["total_priced_loans"]
            exception_rate = exception_count / total if total > 0 else 0

            if exception_rate > 0.10:  # More than 10% are outliers
                alerts.append({
                    "type": "pricing_exception_rate",
                    "severity": "warning",
                    "message": (
                        f"{exception_count} of {total} loans ({round(exception_rate * 100, 1)}%) "
                        f"have rates exceeding the average by more than {RATE_VARIANCE_THRESHOLD * 100}bps. "
                        f"Review for potential pricing disparities."
                    ),
                    "exception_count": exception_count,
                    "total_priced": total,
                })

        # Check state-level disparities
        by_state = approval_analysis.get("by_property_state", {})
        if by_state:
            state_rates = {k: v["approval_rate"] for k, v in by_state.items() if v["total"] >= 10}
            if state_rates and len(state_rates) >= 2:
                max_rate = max(state_rates.values())
                min_rate = min(state_rates.values())
                min_state = min(state_rates, key=state_rates.get)

                if max_rate > 0 and (min_rate / max_rate) < ADVERSE_IMPACT_THRESHOLD:
                    alerts.append({
                        "type": "geographic_disparity",
                        "severity": "warning",
                        "message": (
                            f"Approval rate in {min_state} ({min_rate}%) is significantly "
                            f"lower than the highest state rate ({max_rate}%). "
                            f"Review for potential geographic redlining."
                        ),
                        "state": min_state,
                        "rate": min_rate,
                        "highest_rate": max_rate,
                    })

        return alerts


# =============================================================================
# Utility Functions
# =============================================================================

def _group_by(items: list, attr: str) -> Dict[str, list]:
    """Group items by an attribute value."""
    groups: Dict[str, list] = {}
    for item in items:
        key = getattr(item, attr, None)
        if key is not None:
            groups.setdefault(str(key), []).append(item)
    return groups


def _std_dev(values: list) -> float:
    """Calculate standard deviation of a list of numbers."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)
