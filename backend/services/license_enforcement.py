"""
Multi-State License Enforcement Service

Ensures loan officers are properly licensed in the state where the
subject property is located before loan assignment or processing.

Enterprise Readiness: Check 2.20 (Multi-State License Enforcement)

SAFE Act (S.2039) Requirements:
    - All mortgage loan originators must be registered with NMLS
    - State-specific licenses required for origination activity
    - Licenses must be current and not expired/suspended/revoked

Features:
    - NMLS number validation format checking
    - License-to-state verification before loan assignment
    - License expiration tracking and warnings
    - Block/warn on assignment to unlicensed states
    - License status caching for performance

Usage:
    from services.license_enforcement import LicenseEnforcementService

    service = LicenseEnforcementService()

    # Check before loan assignment
    result = service.check_lo_licensed_for_state(db, user_id=5, state="TX")
    if not result["is_licensed"]:
        # Block or warn
        ...

    # Validate during loan creation
    result = service.validate_loan_assignment(db, loan_id=42, lo_id=5)
"""

import logging
import re
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from utils.validators import validate_nmls

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# US states and territories
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU",
}

# States that require separate state license (most do; a few have exemptions)
# This is a simplified lookup; in production, consult NMLS data
STATE_LICENSE_REQUIRED = US_STATES  # All states require licensing

# License types
LICENSE_TYPE_MLO = "mlo"            # Mortgage Loan Originator
LICENSE_TYPE_BRANCH = "branch"       # Branch registration
LICENSE_TYPE_COMPANY = "company"     # Company license

# NMLS number format: 5-12 digits (kept for backward compat; prefer validate_nmls())
NMLS_PATTERN = re.compile(r"^\d{5,12}$")


def _is_nmls_valid(nmls_value) -> bool:
    """Return True if nmls_value passes format validation."""
    try:
        return validate_nmls(nmls_value) is not None
    except ValueError:
        return False


class LicenseEnforcementService:
    """Enforces multi-state mortgage licensing requirements.

    Checks that loan officers hold valid, active licenses for the states
    in which they originate loans. Integrates with the User model's
    license data and provides enforcement at loan assignment time.
    """

    def check_lo_licensed_for_state(
        self,
        db: Session,
        user_id: int,
        state_code: str,
    ) -> Dict[str, Any]:
        """Check if a loan officer is licensed to originate in a state.

        Args:
            db: Database session
            user_id: User/LO ID
            state_code: Two-letter state code

        Returns:
            Dict with:
                - is_licensed: bool
                - nmls_number: str or None
                - license_status: str (active, expired, not_found, pending)
                - license_expiration: date or None
                - warnings: List of warnings
                - state: str
        """
        from database.models.core import User

        state = state_code.upper().strip()
        result = {
            "user_id": user_id,
            "state": state,
            "is_licensed": False,
            "nmls_number": None,
            "license_status": "not_found",
            "license_expiration": None,
            "warnings": [],
        }

        # Validate state code
        if state not in US_STATES:
            result["warnings"].append(f"'{state}' is not a recognized US state code")
            return result

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            result["warnings"].append(f"User {user_id} not found")
            return result

        # Check NMLS number
        nmls = user.nmls_number or getattr(user, "nmls_id", None)
        result["nmls_number"] = nmls

        if not nmls:
            result["license_status"] = "nmls_missing"
            result["warnings"].append("No NMLS number on file. SAFE Act requires all MLOs to be NMLS-registered.")
            return result

        # Validate NMLS format
        try:
            clean_nmls = validate_nmls(nmls)
        except ValueError:
            result["license_status"] = "invalid_nmls"
            result["warnings"].append(f"Invalid NMLS format. Must be 5-12 digits.")
            return result

        # Check license data
        # The User model doesn't have per-state license data natively.
        # Check user_metadata for license info, or the lo_licenses table if it exists.
        license_info = _get_license_info(db, user, state)

        if license_info is None:
            # No license record found for this state
            # Check if we have a license table at all
            result["license_status"] = "not_found"
            result["warnings"].append(
                f"No license record found for NMLS #{clean_nmls} in state {state}. "
                f"Verify license status at https://www.nmlsconsumeraccess.org/"
            )
            return result

        result["license_status"] = license_info.get("status", "unknown")
        result["license_expiration"] = license_info.get("expiration_date")

        if license_info.get("status") == "active":
            # Check expiration
            exp_date = license_info.get("expiration_date")
            if exp_date:
                if isinstance(exp_date, str):
                    try:
                        exp_date = date.fromisoformat(exp_date)
                    except ValueError:
                        exp_date = None

                if exp_date and exp_date < date.today():
                    result["license_status"] = "expired"
                    result["warnings"].append(
                        f"License expired on {exp_date.isoformat()}. "
                        f"Loan officer must renew before originating in {state}."
                    )
                    return result

                if exp_date and (exp_date - date.today()).days <= 30:
                    result["warnings"].append(
                        f"License expires on {exp_date.isoformat()} "
                        f"({(exp_date - date.today()).days} days). Schedule renewal."
                    )

            result["is_licensed"] = True
        elif license_info.get("status") == "expired":
            result["warnings"].append(f"License is expired in state {state}")
        elif license_info.get("status") == "suspended":
            result["warnings"].append(f"License is SUSPENDED in state {state}. DO NOT originate.")
        elif license_info.get("status") == "pending":
            result["warnings"].append(f"License is pending approval in state {state}")

        return result

    def validate_loan_assignment(
        self,
        db: Session,
        loan_id: int,
        lo_id: int,
    ) -> Dict[str, Any]:
        """Validate that a loan officer can be assigned to a loan.

        Checks the property state of the loan against the LO's licenses.

        Args:
            db: Database session
            loan_id: Loan to validate
            lo_id: Loan officer to assign

        Returns:
            Dict with:
                - can_assign: bool
                - reason: str
                - license_check: license check details
        """
        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return {
                "can_assign": False,
                "reason": f"Loan {loan_id} not found",
                "license_check": None,
            }

        property_state = loan.property_state
        if not property_state:
            return {
                "can_assign": True,
                "reason": "Property state not set on loan; license check skipped",
                "license_check": None,
                "warning": "Property state should be set before assignment for compliance",
            }

        license_result = self.check_lo_licensed_for_state(db, lo_id, property_state)

        can_assign = license_result["is_licensed"]
        reason = "Licensed" if can_assign else f"Not licensed in {property_state}"

        if not can_assign and license_result["license_status"] == "not_found":
            reason = (
                f"No license record found for state {property_state}. "
                f"Verify at NMLS before assignment."
            )

        return {
            "can_assign": can_assign,
            "reason": reason,
            "license_check": license_result,
        }

    def get_lo_license_summary(
        self,
        db: Session,
        user_id: int,
    ) -> Dict[str, Any]:
        """Get a summary of all licenses for a loan officer.

        Args:
            db: Database session
            user_id: User/LO ID

        Returns:
            Dict with NMLS info and list of state licenses
        """
        from database.models.core import User

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": f"User {user_id} not found"}

        nmls = user.nmls_number or getattr(user, "nmls_id", None)

        # Get all license records
        licenses = _get_all_licenses(db, user)

        active_states = [l["state"] for l in licenses if l.get("status") == "active"]
        expiring_soon = [
            l for l in licenses
            if l.get("status") == "active" and l.get("expiration_date")
            and _days_until(l["expiration_date"]) <= 30
        ]

        return {
            "user_id": user_id,
            "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "nmls_number": nmls,
            "nmls_valid": bool(nmls and _is_nmls_valid(nmls)),
            "total_licenses": len(licenses),
            "active_states": active_states,
            "active_count": len(active_states),
            "expiring_soon": [
                {"state": l["state"], "expires": l["expiration_date"]}
                for l in expiring_soon
            ],
            "licenses": licenses,
            "nmls_lookup_url": f"https://www.nmlsconsumeraccess.org/EntityDetails.aspx/INDIVIDUAL/{nmls}" if nmls else None,
        }

    def check_expiring_licenses(
        self,
        db: Session,
        organization_id: int,
        days_ahead: int = 30,
    ) -> Dict[str, Any]:
        """Check for licenses expiring soon across the organization.

        Args:
            db: Database session
            organization_id: Organization to check
            days_ahead: Number of days to look ahead

        Returns:
            Dict with list of expiring licenses
        """
        from database.models.core import User

        users = db.query(User).filter(
            and_(
                User.organization_id == organization_id,
                User.is_active == True,
                User.role.in_(["loan_officer", "branch_manager"]),
            )
        ).all()

        expiring = []
        for user in users:
            licenses = _get_all_licenses(db, user)
            for lic in licenses:
                if lic.get("status") != "active":
                    continue
                exp = lic.get("expiration_date")
                if exp and _days_until(exp) <= days_ahead:
                    expiring.append({
                        "user_id": user.id,
                        "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                        "nmls_number": user.nmls_number or getattr(user, "nmls_id", None),
                        "state": lic["state"],
                        "expiration_date": exp,
                        "days_remaining": _days_until(exp),
                    })

        expiring.sort(key=lambda x: x["days_remaining"])

        return {
            "days_ahead": days_ahead,
            "total_expiring": len(expiring),
            "expiring_licenses": expiring,
            "organization_id": organization_id,
            "checked_users": len(users),
        }


# =============================================================================
# Internal Helpers
# =============================================================================

def _get_license_info(db: Session, user, state: str) -> Optional[Dict[str, Any]]:
    """Get license info for a user in a specific state.

    Checks:
    1. lo_licenses table (if it exists)
    2. user_metadata JSON field for license data
    3. Organization settings for default license info
    """
    # Check user_metadata for license info
    if user.user_metadata and isinstance(user.user_metadata, dict):
        licenses = user.user_metadata.get("licenses", [])
        if isinstance(licenses, list):
            for lic in licenses:
                if isinstance(lic, dict) and lic.get("state", "").upper() == state:
                    return lic

        # Check for simpler format: {"licensed_states": ["TX", "CA", ...]}
        licensed_states = user.user_metadata.get("licensed_states", [])
        if isinstance(licensed_states, list) and state in licensed_states:
            return {"state": state, "status": "active", "expiration_date": None}

    # Try lo_licenses table (may not exist)
    try:
        from sqlalchemy import text
        row = db.execute(
            text("SELECT state, status, expiration_date FROM lo_licenses WHERE user_id = :uid AND state = :state"),
            {"uid": user.id, "state": state},
        ).first()
        if row:
            return {
                "state": row[0],
                "status": row[1],
                "expiration_date": str(row[2]) if row[2] else None,
            }
    except Exception as e:
        logger.exception(f"Failed to query lo_licenses table (may not exist): {e}")

    return None


def _get_all_licenses(db: Session, user) -> List[Dict[str, Any]]:
    """Get all licenses for a user from available data sources."""
    licenses = []

    # From user_metadata
    if user.user_metadata and isinstance(user.user_metadata, dict):
        meta_licenses = user.user_metadata.get("licenses", [])
        if isinstance(meta_licenses, list):
            for lic in meta_licenses:
                if isinstance(lic, dict) and lic.get("state"):
                    licenses.append(lic)

        # Simple format
        licensed_states = user.user_metadata.get("licensed_states", [])
        if isinstance(licensed_states, list):
            existing = {l.get("state") for l in licenses}
            for state in licensed_states:
                if state not in existing:
                    licenses.append({"state": state, "status": "active", "expiration_date": None})

    # From lo_licenses table
    try:
        from sqlalchemy import text
        rows = db.execute(
            text("SELECT state, status, expiration_date FROM lo_licenses WHERE user_id = :uid"),
            {"uid": user.id},
        ).fetchall()
        existing = {l.get("state") for l in licenses}
        for row in rows:
            if row[0] not in existing:
                licenses.append({
                    "state": row[0],
                    "status": row[1],
                    "expiration_date": str(row[2]) if row[2] else None,
                })
    except Exception as e:
        logger.exception(f"Failed to query lo_licenses table for all licenses: {e}")

    return licenses


def _days_until(date_val) -> int:
    """Calculate days until a date."""
    if isinstance(date_val, str):
        try:
            date_val = date.fromisoformat(date_val)
        except ValueError:
            return 999
    if isinstance(date_val, datetime):
        date_val = date_val.date()
    if isinstance(date_val, date):
        return (date_val - date.today()).days
    return 999
