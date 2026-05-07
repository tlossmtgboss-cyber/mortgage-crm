"""
Fair Lending Compliance Service

ECOA (Equal Credit Opportunity Act) fair lending bias monitoring.
Calculates denial rates across available demographic proxies and
flags statistical disparities per the disparate impact standard.

Disparate Impact Threshold:
    If any group's denial rate exceeds 2x the lowest group's denial rate,
    the system flags a potential fair lending violation for human review.

Four-Fifths Rule (supplemental):
    EEOC Uniform Guidelines (29 CFR 1607.4(D)) — if the approval rate for
    any group is less than 80% of the highest group's rate, adverse impact
    may be indicated.

Enterprise Readiness: Domain 2, ECOA Fair Lending Monitoring
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Disparate impact: flag if any group's denial rate is >2x the lowest group
DISPARATE_IMPACT_RATIO = 2.0

# Four-fifths rule: flag if approval rate is <80% of the highest group
FOUR_FIFTHS_THRESHOLD = 0.80

# Minimum sample size for statistical relevance
MIN_GROUP_SIZE = 10


def calculate_denial_rates_by_demographic(
    db: Session,
    org_id: int,
    period_days: int = 90,
) -> Dict[str, Any]:
    """Calculate denial rates grouped by available demographic dimensions.

    Since direct demographic data (race, ethnicity, sex) may not be
    collected until the borrower application stage, this uses proxy
    dimensions that are available in the loan pipeline:

    - Loan type (Conventional, FHA, VA, USDA)
    - Property state (geographic proxy)
    - Loan purpose (purchase, refinance, etc.)

    If BorrowerApplication demographics are available, they are included.

    Args:
        db: Database session
        org_id: Organization to analyze
        period_days: Lookback period in days

    Returns:
        Dict with denial rates per dimension, overall rates, and metadata.
    """
    from database.models.lead_loan import Loan

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    # Get all loans in the period with a terminal decision
    terminal_stages = ("FUNDED", "APPROVED", "DENIED", "DOES_NOT_QUALIFY",
                       "WITHDRAWN", "CANCELLED", "DEAD")

    loans = db.query(Loan).filter(
        and_(
            Loan.organization_id == org_id,
            Loan.created_at >= cutoff,
            Loan.stage.isnot(None),
        )
    ).all()

    # Only include loans with a terminal decision for rate calculations
    decided_loans = [
        l for l in loans
        if (getattr(l, "stage", "") or "").upper() in terminal_stages
    ]

    if not decided_loans:
        return {
            "status": "insufficient_data",
            "total_loans": len(loans),
            "decided_loans": 0,
            "period_days": period_days,
            "message": f"No loans with terminal decisions in the past {period_days} days",
        }

    denial_stages = {"DENIED", "DOES_NOT_QUALIFY"}
    approval_stages = {"FUNDED", "APPROVED", "CLEAR_TO_CLOSE"}

    total_decided = len(decided_loans)
    total_denied = sum(1 for l in decided_loans if (l.stage or "").upper() in denial_stages)
    total_approved = sum(1 for l in decided_loans if (l.stage or "").upper() in approval_stages)

    result = {
        "period_days": period_days,
        "total_loans_in_period": len(loans),
        "decided_loans": total_decided,
        "total_denied": total_denied,
        "total_approved": total_approved,
        "overall_denial_rate": round(total_denied / total_decided * 100, 2) if total_decided > 0 else 0,
        "overall_approval_rate": round(total_approved / total_decided * 100, 2) if total_decided > 0 else 0,
        "dimensions": {},
    }

    # --- Denial rates by loan type ---
    result["dimensions"]["loan_type"] = _compute_dimension_rates(
        decided_loans, "loan_type", denial_stages, approval_stages,
    )

    # --- Denial rates by property state ---
    result["dimensions"]["property_state"] = _compute_dimension_rates(
        decided_loans, "property_state", denial_stages, approval_stages,
    )

    # --- Denial rates by loan purpose ---
    result["dimensions"]["loan_purpose"] = _compute_dimension_rates(
        decided_loans, "loan_purpose", denial_stages, approval_stages,
    )

    # --- Denial rates by demographics if available ---
    try:
        from database.models.borrower import BorrowerApplication

        # Get loan IDs for the decided loans
        loan_ids = [l.id for l in decided_loans]
        apps = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id.in_(loan_ids),
        ).all()

        if apps:
            loan_app_map = {a.loan_id: a for a in apps}

            # Build demographic-enriched loan list
            demo_loans = []
            for loan in decided_loans:
                app = loan_app_map.get(loan.id)
                if app:
                    demo_loans.append({
                        "loan": loan,
                        "ethnicity": getattr(app, "applicant_ethnicity", None),
                        "race": getattr(app, "applicant_race", None),
                        "sex": getattr(app, "applicant_sex", None),
                    })

            if demo_loans:
                for demo_field in ("ethnicity", "race", "sex"):
                    dimension_data = {}
                    for entry in demo_loans:
                        group_val = entry.get(demo_field)
                        if not group_val:
                            continue
                        group_key = str(group_val)
                        if group_key not in dimension_data:
                            dimension_data[group_key] = {"total": 0, "denied": 0, "approved": 0}
                        dimension_data[group_key]["total"] += 1
                        stage = (entry["loan"].stage or "").upper()
                        if stage in denial_stages:
                            dimension_data[group_key]["denied"] += 1
                        elif stage in approval_stages:
                            dimension_data[group_key]["approved"] += 1

                    # Convert to rate format
                    groups = {}
                    for group_name, counts in dimension_data.items():
                        if counts["total"] < MIN_GROUP_SIZE:
                            continue
                        groups[group_name] = {
                            "total": counts["total"],
                            "denied": counts["denied"],
                            "approved": counts["approved"],
                            "denial_rate": round(counts["denied"] / counts["total"] * 100, 2) if counts["total"] > 0 else 0,
                            "approval_rate": round(counts["approved"] / counts["total"] * 100, 2) if counts["total"] > 0 else 0,
                        }

                    if groups:
                        result["dimensions"][f"applicant_{demo_field}"] = {
                            "groups": groups,
                            "source": "borrower_application",
                        }
    except Exception as e:
        logger.debug("Could not include demographic data in denial rate analysis: %s", e)

    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def check_statistical_disparity(
    db: Session,
    org_id: int,
    period_days: int = 90,
) -> Dict[str, Any]:
    """Compare denial rates between groups and flag disparate impact.

    Flags a potential disparity if any group has a denial rate exceeding
    2x the lowest group's denial rate within the same dimension.

    Also applies the four-fifths (80%) rule on approval rates.

    Args:
        db: Database session
        org_id: Organization to check
        period_days: Lookback period

    Returns:
        Dict with disparity findings, flags, and recommendations.
    """
    # Get the denial rate data
    rates = calculate_denial_rates_by_demographic(db, org_id, period_days)

    if rates.get("status") == "insufficient_data":
        return {
            "status": "insufficient_data",
            "disparities_found": False,
            "message": rates["message"],
        }

    findings: List[Dict[str, Any]] = []
    dimensions_analyzed = 0

    for dim_name, dim_data in rates.get("dimensions", {}).items():
        groups = dim_data if isinstance(dim_data, dict) and "groups" not in dim_data else dim_data.get("groups", dim_data)

        if not isinstance(groups, dict) or len(groups) < 2:
            continue

        dimensions_analyzed += 1

        # Extract denial rates for groups with sufficient sample size
        denial_rates = {}
        approval_rates = {}
        for group_name, group_data in groups.items():
            if isinstance(group_data, dict) and group_data.get("total", 0) >= MIN_GROUP_SIZE:
                denial_rates[group_name] = group_data.get("denial_rate", 0)
                approval_rates[group_name] = group_data.get("approval_rate", 0)

        if len(denial_rates) < 2:
            continue

        # --- Disparate Impact Check (2x denial rate threshold) ---
        min_denial_rate = min(denial_rates.values())
        max_denial_rate = max(denial_rates.values())

        if min_denial_rate > 0:
            disparity_ratio = max_denial_rate / min_denial_rate
        else:
            disparity_ratio = float("inf") if max_denial_rate > 0 else 1.0

        if disparity_ratio >= DISPARATE_IMPACT_RATIO:
            max_group = max(denial_rates, key=denial_rates.get)
            min_group = min(denial_rates, key=denial_rates.get)
            findings.append({
                "type": "disparate_impact",
                "dimension": dim_name,
                "severity": "critical" if disparity_ratio >= 3.0 else "high",
                "highest_denial_group": max_group,
                "highest_denial_rate": max_denial_rate,
                "lowest_denial_group": min_group,
                "lowest_denial_rate": min_denial_rate,
                "disparity_ratio": round(disparity_ratio, 2),
                "threshold": DISPARATE_IMPACT_RATIO,
                "message": (
                    f"Denial rate for '{max_group}' ({max_denial_rate}%) is "
                    f"{round(disparity_ratio, 1)}x the rate for '{min_group}' "
                    f"({min_denial_rate}%) in dimension '{dim_name}'. "
                    f"Exceeds {DISPARATE_IMPACT_RATIO}x disparate impact threshold."
                ),
            })

        # --- Four-Fifths Rule Check (approval rate) ---
        if approval_rates:
            max_approval = max(approval_rates.values())
            if max_approval > 0:
                for group_name, approval_rate in approval_rates.items():
                    ratio = approval_rate / max_approval
                    if ratio < FOUR_FIFTHS_THRESHOLD:
                        max_group = max(approval_rates, key=approval_rates.get)
                        findings.append({
                            "type": "four_fifths_rule",
                            "dimension": dim_name,
                            "severity": "warning",
                            "group": group_name,
                            "group_approval_rate": approval_rate,
                            "reference_group": max_group,
                            "reference_rate": max_approval,
                            "ratio": round(ratio, 3),
                            "threshold": FOUR_FIFTHS_THRESHOLD,
                            "message": (
                                f"Approval rate for '{group_name}' ({approval_rate}%) "
                                f"is {round(ratio * 100, 1)}% of the highest group rate "
                                f"({max_approval}%) in '{dim_name}'. Below the 80% "
                                f"four-fifths rule threshold."
                            ),
                        })

    has_critical = any(f["severity"] == "critical" for f in findings)
    has_high = any(f["severity"] == "high" for f in findings)

    if has_critical:
        status = "critical_review_required"
    elif has_high:
        status = "review_recommended"
    elif findings:
        status = "warnings_present"
    else:
        status = "pass"

    return {
        "status": status,
        "organization_id": org_id,
        "period_days": period_days,
        "dimensions_analyzed": dimensions_analyzed,
        "disparities_found": len(findings) > 0,
        "findings_count": len(findings),
        "critical_findings": sum(1 for f in findings if f["severity"] == "critical"),
        "findings": findings,
        "denial_rates": rates,
        "thresholds": {
            "disparate_impact_ratio": DISPARATE_IMPACT_RATIO,
            "four_fifths_rule": FOUR_FIFTHS_THRESHOLD,
            "min_group_size": MIN_GROUP_SIZE,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Internal Helpers
# =============================================================================

def _compute_dimension_rates(
    loans: list,
    attr: str,
    denial_stages: set,
    approval_stages: set,
) -> Dict[str, Dict[str, Any]]:
    """Compute denial/approval rates grouped by a loan attribute."""
    groups: Dict[str, Dict[str, int]] = {}

    for loan in loans:
        val = getattr(loan, attr, None)
        if not val:
            continue
        key = str(val)
        if key not in groups:
            groups[key] = {"total": 0, "denied": 0, "approved": 0}
        groups[key]["total"] += 1
        stage = (loan.stage or "").upper()
        if stage in denial_stages:
            groups[key]["denied"] += 1
        elif stage in approval_stages:
            groups[key]["approved"] += 1

    result = {}
    for group_name, counts in groups.items():
        if counts["total"] < MIN_GROUP_SIZE:
            continue
        result[group_name] = {
            "total": counts["total"],
            "denied": counts["denied"],
            "approved": counts["approved"],
            "denial_rate": round(counts["denied"] / counts["total"] * 100, 2) if counts["total"] > 0 else 0,
            "approval_rate": round(counts["approved"] / counts["total"] * 100, 2) if counts["total"] > 0 else 0,
        }

    return result
