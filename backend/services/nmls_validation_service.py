"""
NMLS License Validation Service

Validates NMLS license data for mortgage recruiting compliance.
Performs format validation + opportunistic live lookup against NMLS Consumer Access.
"""

import logging
import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.validators import validate_nmls

logger = logging.getLogger(__name__)

_NMLS_LOOKUP_URL = (
    "https://www.nmlsconsumeraccess.org/api/SearchResults"
    "?searchValue={nmls_id}&searchType=IndividualNMLSID"
)


@dataclass
class NMLSValidationResult:
    is_valid: bool
    nmls_id: Optional[str] = None
    issues: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    license_summary: Dict[str, Any] = field(default_factory=dict)
    verification_status: str = "unverified_format_only"
    last_verified_at: Optional[str] = None


class NMLSValidationService:
    """Validates NMLS license data for recruiting compliance."""

    def __init__(self, db: Session):
        self.db = db

    def validate_nmls_format(self, nmls_id: Optional[str]) -> Optional[str]:
        """Validate NMLS ID format (5-12 digits). Returns error message or None."""
        if not nmls_id:
            return "NMLS ID is missing"
        try:
            validate_nmls(nmls_id)
            return None
        except ValueError:
            return f"NMLS ID '{nmls_id}' invalid format — must be 5-12 digits"

    async def lookup_nmls_public(self, nmls_id: str) -> str:
        """
        Attempt a live NMLS Consumer Access lookup.
        Returns "verified_public", "not_found", or "unverified_format_only".
        """
        try:
            url = _NMLS_LOOKUP_URL.format(nmls_id=nmls_id)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                # Response is a list of result objects; empty list means not found
                if isinstance(data, list) and len(data) > 0:
                    return "verified_public"
                elif isinstance(data, dict) and data.get("Results"):
                    return "verified_public"
                return "not_found"
            elif resp.status_code == 404:
                return "not_found"
            else:
                logger.warning("NMLS lookup non-200 status %s for %s", resp.status_code, nmls_id)
                return "unverified_format_only"
        except Exception as exc:
            logger.warning("NMLS public lookup failed for %s: %s", nmls_id, exc)
            return "unverified_format_only"

    async def check_license_status(
        self, candidate_id: int, organization_id: int
    ) -> NMLSValidationResult:
        """Full license validation for a candidate."""
        row = self.db.execute(text("""
            SELECT nmls_id, license_states, license_expiration_dates,
                   ce_credits_completed, sponsorship_transfer_status,
                   first_name, last_name
            FROM mm_candidates
            WHERE id = :cid AND organization_id = :org_id AND is_active = true
        """), {"cid": candidate_id, "org_id": organization_id}).fetchone()

        if not row:
            return NMLSValidationResult(
                is_valid=False,
                issues=[{"type": "NOT_FOUND", "message": "Candidate not found"}]
            )

        result = NMLSValidationResult(is_valid=True, nmls_id=row.nmls_id)

        # 1. Validate NMLS ID format
        format_error = self.validate_nmls_format(row.nmls_id)
        if format_error:
            result.issues.append({"type": "NMLS_FORMAT", "message": format_error})

        # 2. Check license states
        license_states = row.license_states or []
        if not license_states:
            result.issues.append({"type": "NO_LICENSE_STATES", "message": "No license states on file"})

        # 3. Check license expirations
        expiration_dates = row.license_expiration_dates or {}
        today = date.today()
        expired_states = []
        expiring_soon = []

        for state, exp_str in expiration_dates.items():
            try:
                if isinstance(exp_str, str):
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                elif isinstance(exp_str, date):
                    exp_date = exp_str
                else:
                    result.warnings.append({"type": "BAD_DATE", "message": f"Invalid expiration date for {state}"})
                    continue

                if exp_date < today:
                    expired_states.append(state)
                elif (exp_date - today).days <= 60:
                    expiring_soon.append({"state": state, "expires": str(exp_date)})
            except (ValueError, TypeError):
                result.warnings.append({"type": "BAD_DATE", "message": f"Invalid expiration date for {state}"})

        if expired_states:
            result.issues.append({
                "type": "EXPIRED_LICENSE",
                "message": f"Expired licenses in: {', '.join(expired_states)}"
            })

        if expiring_soon:
            result.warnings.append({
                "type": "EXPIRING_SOON",
                "message": f"Licenses expiring within 60 days: {', '.join(e['state'] for e in expiring_soon)}"
            })

        # 4. Check CE credits
        if row.ce_credits_completed is False:
            result.issues.append({
                "type": "CE_INCOMPLETE",
                "message": "Continuing education credits not completed"
            })
        elif row.ce_credits_completed is None:
            result.warnings.append({
                "type": "CE_UNKNOWN",
                "message": "CE credits status not recorded"
            })

        # 5. Sponsorship transfer
        if row.sponsorship_transfer_status == "pending":
            result.warnings.append({
                "type": "SPONSORSHIP_PENDING",
                "message": "NMLS sponsorship transfer is pending"
            })

        result.is_valid = len(result.issues) == 0
        result.license_summary = {
            "nmls_id": row.nmls_id,
            "license_states": license_states,
            "expired_states": expired_states,
            "expiring_soon": expiring_soon,
            "ce_completed": row.ce_credits_completed,
            "sponsorship_status": row.sponsorship_transfer_status,
        }

        # Live NMLS public lookup (best-effort; never blocks validation)
        if row.nmls_id and not format_error:
            verification_status = await self.lookup_nmls_public(row.nmls_id)
            result.verification_status = verification_status
            result.last_verified_at = datetime.now(timezone.utc).isoformat()
            if verification_status == "not_found":
                result.warnings.append({
                    "type": "NMLS_NOT_FOUND",
                    "message": f"NMLS ID {row.nmls_id} not found in NMLS Consumer Access public database",
                })
        else:
            result.verification_status = "unverified_format_only"

        return result
