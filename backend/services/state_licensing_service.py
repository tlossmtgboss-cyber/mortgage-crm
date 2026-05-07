"""
State Licensing Service

Verifies that loan officers hold active NMLS licenses for the states
in which they originate loans. Provides the four core functions
required by Domain 2 (Compliance) Check 2.20: Multi-State License
Enforcement.

SAFE Act (S.2039) Requirements:
    - All mortgage loan originators must be registered with NMLS
    - State-specific licenses required for origination activity
    - Licenses must be current and not expired/suspended/revoked

This service uses the LoanOfficerLicense ORM model (lo_licenses table)
as the primary data source, with fallback to user_metadata JSON for
organizations that have not migrated license data yet.

Usage:
    from services.state_licensing_service import (
        check_lo_state_license,
        validate_loan_state_assignment,
        get_lo_license_summary,
        find_unlicensed_assignments,
    )

    result = check_lo_state_license(db, user_id=5, state="TX")
    if not result["licensed"]:
        raise ComplianceError(result)
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# US states and territories requiring MLO licensing
US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU",
})

# Days threshold for "expiring soon" warnings
EXPIRING_SOON_DAYS = 30


# =============================================================================
# Public API
# =============================================================================

def check_lo_state_license(
    db: Session,
    user_id: int,
    state: str,
) -> Dict[str, Any]:
    """Verify an LO has an active license for the given state.

    Args:
        db: Database session (RLS-aware).
        user_id: The LO's user ID.
        state: Two-letter US state code.

    Returns:
        Dict with keys:
            - licensed: bool -- whether the LO may originate in this state
            - nmls_id: str or None -- the LO's NMLS number
            - state: str -- the normalized state code
            - expiry: date or None -- license expiration date
            - status: str -- active, expired, suspended, revoked, pending,
              nmls_missing, not_found
            - warnings: list[str]
    """
    from database.models.core import User
    from database.models.lo_license import LoanOfficerLicense

    state = state.upper().strip()
    result: Dict[str, Any] = {
        "licensed": False,
        "nmls_id": None,
        "state": state,
        "expiry": None,
        "status": "not_found",
        "warnings": [],
    }

    # Validate state code
    if state not in US_STATES:
        result["warnings"].append(f"'{state}' is not a recognized US state/territory code")
        return result

    # Look up user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        result["warnings"].append(f"User {user_id} not found")
        return result

    nmls = user.nmls_number or getattr(user, "nmls_id", None)
    result["nmls_id"] = nmls

    if not nmls:
        result["status"] = "nmls_missing"
        result["warnings"].append(
            "No NMLS number on file. SAFE Act requires all MLOs to be NMLS-registered."
        )
        return result

    # Query the lo_licenses table via ORM
    license_record = db.query(LoanOfficerLicense).filter(
        LoanOfficerLicense.user_id == user_id,
        LoanOfficerLicense.state == state,
    ).first()

    # Fallback: check user_metadata JSON
    if license_record is None:
        license_record = _check_user_metadata_for_license(user, state)
        if license_record is not None:
            # user_metadata returned a dict; normalize into the result
            result["status"] = license_record.get("status", "unknown")
            result["expiry"] = _parse_date(license_record.get("expiration_date"))
            if result["status"] == "active":
                if result["expiry"] and result["expiry"] < date.today():
                    result["status"] = "expired"
                    result["warnings"].append(
                        f"License expired on {result['expiry'].isoformat()}. "
                        f"Renewal required before originating in {state}."
                    )
                else:
                    result["licensed"] = True
                    if result["expiry"] and (result["expiry"] - date.today()).days <= EXPIRING_SOON_DAYS:
                        days_left = (result["expiry"] - date.today()).days
                        result["warnings"].append(
                            f"License expires on {result['expiry'].isoformat()} "
                            f"({days_left} days). Schedule renewal."
                        )
            return result

    if license_record is None:
        result["status"] = "not_found"
        result["warnings"].append(
            f"No license record found for NMLS #{nmls} in state {state}. "
            f"Verify at https://www.nmlsconsumeraccess.org/"
        )
        return result

    # ORM record path
    status = license_record.status or "unknown"
    result["status"] = status
    exp_date = license_record.expiration_date
    result["expiry"] = exp_date

    if status == "active":
        if exp_date and exp_date < date.today():
            result["status"] = "expired"
            result["warnings"].append(
                f"License expired on {exp_date.isoformat()}. "
                f"Renewal required before originating in {state}."
            )
        else:
            result["licensed"] = True
            if exp_date:
                days_left = (exp_date - date.today()).days
                if days_left <= EXPIRING_SOON_DAYS:
                    result["warnings"].append(
                        f"License expires on {exp_date.isoformat()} "
                        f"({days_left} days). Schedule renewal."
                    )
    elif status == "expired":
        result["warnings"].append(f"License is expired in state {state}.")
    elif status == "suspended":
        result["warnings"].append(
            f"License is SUSPENDED in state {state}. DO NOT originate."
        )
    elif status == "revoked":
        result["warnings"].append(
            f"License is REVOKED in state {state}. DO NOT originate."
        )
    elif status == "pending":
        result["warnings"].append(
            f"License is pending approval in state {state}. Cannot originate until active."
        )

    return result


def validate_loan_state_assignment(
    db: Session,
    loan_id: int,
    lo_user_id: int,
) -> Dict[str, Any]:
    """Check if the assigned LO is licensed in the loan's property state.

    Should be called during loan creation or LO re-assignment.

    Args:
        db: Database session.
        loan_id: Loan ID.
        lo_user_id: The LO's user ID to validate.

    Returns:
        Dict with keys:
            - valid: bool -- whether the assignment is compliant
            - loan_id: int
            - lo_user_id: int
            - property_state: str or None
            - warnings: list[str]
            - license_check: dict or None -- full license check result
    """
    from database.models.lead_loan import Loan

    result: Dict[str, Any] = {
        "valid": False,
        "loan_id": loan_id,
        "lo_user_id": lo_user_id,
        "property_state": None,
        "warnings": [],
        "license_check": None,
    }

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        result["warnings"].append(f"Loan {loan_id} not found")
        return result

    property_state = loan.property_state
    if not property_state:
        # No state set -- cannot enforce, pass with warning
        result["valid"] = True
        result["warnings"].append(
            "Property state not set on loan. License check skipped. "
            "Set property_state before closing for compliance."
        )
        return result

    property_state = property_state.upper().strip()
    result["property_state"] = property_state

    license_result = check_lo_state_license(db, lo_user_id, property_state)
    result["license_check"] = license_result
    result["valid"] = license_result["licensed"]

    if not license_result["licensed"]:
        status = license_result["status"]
        if status == "not_found":
            result["warnings"].append(
                f"No license record for state {property_state}. "
                f"Verify NMLS before assignment."
            )
        elif status == "expired":
            result["warnings"].append(
                f"LO license expired in {property_state}. Assignment blocked."
            )
        elif status == "suspended":
            result["warnings"].append(
                f"LO license SUSPENDED in {property_state}. Assignment blocked."
            )
        elif status == "revoked":
            result["warnings"].append(
                f"LO license REVOKED in {property_state}. Assignment blocked."
            )
        elif status == "nmls_missing":
            result["warnings"].append("LO has no NMLS number on file.")
        else:
            result["warnings"].append(
                f"LO not licensed in {property_state} (status: {status})."
            )

    # Propagate license-level warnings
    result["warnings"].extend(license_result.get("warnings", []))

    return result


def get_lo_license_summary(
    db: Session,
    user_id: int,
) -> Dict[str, Any]:
    """List all states the LO is licensed in.

    Args:
        db: Database session.
        user_id: The LO's user ID.

    Returns:
        Dict with keys:
            - user_id: int
            - user_name: str
            - nmls_id: str or None
            - total_licenses: int
            - active_states: list[str]
            - licenses: list[dict] -- full license details per state
            - expiring_soon: list[dict] -- licenses expiring within 30 days
            - nmls_lookup_url: str or None
    """
    from database.models.core import User
    from database.models.lo_license import LoanOfficerLicense

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": f"User {user_id} not found"}

    nmls = user.nmls_number or getattr(user, "nmls_id", None)

    # Query all ORM license records
    orm_licenses = db.query(LoanOfficerLicense).filter(
        LoanOfficerLicense.user_id == user_id,
    ).all()

    seen_states: set = set()
    licenses: List[Dict[str, Any]] = []

    for lic in orm_licenses:
        seen_states.add(lic.state)
        exp = lic.expiration_date
        effective_status = lic.status
        # Mark as expired if date has passed even if status says active
        if effective_status == "active" and exp and exp < date.today():
            effective_status = "expired"
        licenses.append({
            "state": lic.state,
            "status": effective_status,
            "license_number": lic.license_number,
            "nmls_number": lic.nmls_number,
            "license_type": lic.license_type,
            "expiration_date": exp.isoformat() if exp else None,
            "issue_date": lic.issue_date.isoformat() if lic.issue_date else None,
            "renewal_date": lic.renewal_date.isoformat() if lic.renewal_date else None,
            "verified_at": lic.verified_at.isoformat() if lic.verified_at else None,
        })

    # Merge in user_metadata licenses not already covered
    meta_licenses = _get_metadata_licenses(user)
    for ml in meta_licenses:
        state = ml.get("state", "").upper()
        if state and state not in seen_states:
            seen_states.add(state)
            licenses.append({
                "state": state,
                "status": ml.get("status", "active"),
                "license_number": ml.get("license_number"),
                "nmls_number": ml.get("nmls_number"),
                "license_type": ml.get("license_type", "mlo"),
                "expiration_date": ml.get("expiration_date"),
                "issue_date": ml.get("issue_date"),
                "renewal_date": None,
                "verified_at": None,
            })

    active_states = [
        l["state"] for l in licenses if l["status"] == "active"
    ]
    expiring_soon = []
    for l in licenses:
        if l["status"] == "active" and l["expiration_date"]:
            exp = _parse_date(l["expiration_date"])
            if exp and (exp - date.today()).days <= EXPIRING_SOON_DAYS:
                expiring_soon.append({
                    "state": l["state"],
                    "expiration_date": exp.isoformat(),
                    "days_remaining": (exp - date.today()).days,
                })

    return {
        "user_id": user_id,
        "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "nmls_id": nmls,
        "total_licenses": len(licenses),
        "active_states": sorted(active_states),
        "active_count": len(active_states),
        "licenses": licenses,
        "expiring_soon": expiring_soon,
        "nmls_lookup_url": (
            f"https://www.nmlsconsumeraccess.org/EntityDetails.aspx/INDIVIDUAL/{nmls}"
            if nmls else None
        ),
    }


def find_unlicensed_assignments(
    db: Session,
    org_id: int,
) -> List[Dict[str, Any]]:
    """Find all loans where the assigned LO may not be licensed for the property state.

    Scans all active (non-terminal) loans in the organization where
    property_state is set and an LO is assigned. For each, checks
    whether the LO holds an active license in that state.

    Args:
        db: Database session.
        org_id: Organization ID to scan.

    Returns:
        List of dicts, each with:
            - loan_id: int
            - loan_number: str
            - borrower_name: str
            - property_state: str
            - loan_officer_id: int
            - loan_officer_name: str
            - nmls_id: str or None
            - license_status: str
            - violation_reason: str
    """
    from database.models.lead_loan import Loan
    from database.models.core import User
    from database.models.lo_license import LoanOfficerLicense

    TERMINAL_STAGES = frozenset({
        "FUNDED", "CANCELLED", "DENIED", "DEAD",
        "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
    })

    # Get all active loans with an LO and property_state set
    loans = db.query(Loan).filter(
        Loan.organization_id == org_id,
        Loan.loan_officer_id.isnot(None),
        Loan.property_state.isnot(None),
        Loan.property_state != "",
        ~Loan.stage.in_(TERMINAL_STAGES),
    ).all()

    if not loans:
        return []

    # Build lookup of user_id -> User
    lo_ids = list({loan.loan_officer_id for loan in loans})
    users = db.query(User).filter(User.id.in_(lo_ids)).all()
    user_map = {u.id: u for u in users}

    # Bulk-load all licenses for these LOs
    all_licenses = db.query(LoanOfficerLicense).filter(
        LoanOfficerLicense.user_id.in_(lo_ids),
    ).all()
    # Map: (user_id, state) -> LoanOfficerLicense
    license_map: Dict = {}
    for lic in all_licenses:
        license_map[(lic.user_id, lic.state.upper())] = lic

    violations: List[Dict[str, Any]] = []

    for loan in loans:
        prop_state = (loan.property_state or "").upper().strip()
        if not prop_state or prop_state not in US_STATES:
            continue

        lo_id = loan.loan_officer_id
        user = user_map.get(lo_id)
        if not user:
            continue

        nmls = user.nmls_number or getattr(user, "nmls_id", None)
        lo_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

        # Check ORM license
        lic = license_map.get((lo_id, prop_state))

        if lic is not None:
            if lic.status == "active":
                # Check if actually expired by date
                if lic.expiration_date and lic.expiration_date < date.today():
                    violations.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "property_state": prop_state,
                        "loan_officer_id": lo_id,
                        "loan_officer_name": lo_name,
                        "nmls_id": nmls,
                        "license_status": "expired",
                        "violation_reason": (
                            f"License expired on {lic.expiration_date.isoformat()}"
                        ),
                    })
                # else: licensed and active -- no violation
                continue
            else:
                violations.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "property_state": prop_state,
                    "loan_officer_id": lo_id,
                    "loan_officer_name": lo_name,
                    "nmls_id": nmls,
                    "license_status": lic.status,
                    "violation_reason": (
                        f"License status is '{lic.status}' in {prop_state}"
                    ),
                })
                continue

        # No ORM record -- check user_metadata fallback
        meta_lic = _check_user_metadata_for_license(user, prop_state) if user else None
        if meta_lic and meta_lic.get("status") == "active":
            exp = _parse_date(meta_lic.get("expiration_date"))
            if exp and exp < date.today():
                violations.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "property_state": prop_state,
                    "loan_officer_id": lo_id,
                    "loan_officer_name": lo_name,
                    "nmls_id": nmls,
                    "license_status": "expired",
                    "violation_reason": (
                        f"License expired on {exp.isoformat()} (from user metadata)"
                    ),
                })
            # else: active in metadata -- no violation
            continue

        # No license found at all
        if not nmls:
            reason = "No NMLS number on file"
        else:
            reason = f"No license record for state {prop_state}"

        violations.append({
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "property_state": prop_state,
            "loan_officer_id": lo_id,
            "loan_officer_name": lo_name,
            "nmls_id": nmls,
            "license_status": "not_found",
            "violation_reason": reason,
        })

    return violations


# =============================================================================
# Internal Helpers
# =============================================================================

def _check_user_metadata_for_license(
    user, state: str
) -> Optional[Dict[str, Any]]:
    """Check user_metadata JSON field for license data.

    Supports two formats:
        1. {"licenses": [{"state": "TX", "status": "active", ...}, ...]}
        2. {"licensed_states": ["TX", "CA", ...]}
    """
    meta = getattr(user, "user_metadata", None)
    if not meta or not isinstance(meta, dict):
        return None

    # Format 1: structured license list
    licenses = meta.get("licenses", [])
    if isinstance(licenses, list):
        for lic in licenses:
            if isinstance(lic, dict) and lic.get("state", "").upper() == state.upper():
                return lic

    # Format 2: simple state list
    licensed_states = meta.get("licensed_states", [])
    if isinstance(licensed_states, list):
        for s in licensed_states:
            if isinstance(s, str) and s.upper() == state.upper():
                return {"state": state, "status": "active", "expiration_date": None}

    return None


def _get_metadata_licenses(user) -> List[Dict[str, Any]]:
    """Get all license entries from user_metadata."""
    meta = getattr(user, "user_metadata", None)
    if not meta or not isinstance(meta, dict):
        return []

    result = []

    # Structured format
    licenses = meta.get("licenses", [])
    if isinstance(licenses, list):
        for lic in licenses:
            if isinstance(lic, dict) and lic.get("state"):
                result.append(lic)

    # Simple format
    seen = {l.get("state", "").upper() for l in result}
    licensed_states = meta.get("licensed_states", [])
    if isinstance(licensed_states, list):
        for s in licensed_states:
            if isinstance(s, str) and s.upper() not in seen:
                result.append({
                    "state": s.upper(),
                    "status": "active",
                    "expiration_date": None,
                })

    return result


def _parse_date(val) -> Optional[date]:
    """Parse a date from string, datetime, or date."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None
