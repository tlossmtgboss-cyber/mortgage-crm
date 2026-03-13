"""
Fraud Data Access Control — BSA/SAR Tipping Prevention

Under the Bank Secrecy Act (31 USC 5318(g)(2)), it is a federal crime to
disclose ("tip off") a borrower or any unauthorized person that:
  - A Suspicious Activity Report (SAR) has been or will be filed
  - They are the subject of a fraud investigation

This module enforces tiered access to fraud detection data so that:
  - Portal/borrower-facing endpoints NEVER see fraud indicators
  - Regular staff see only summary risk scores (no indicator details)
  - Only compliance officers and admins see full fraud data

Every access to fraud data is logged for audit purposes.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# ACCESS LEVELS
# =============================================================================

class FraudAccessLevel(str, Enum):
    """Tiered access to fraud detection data.

    FULL        — Compliance officers and platform admins.
                  Can see all fraud indicators, SAR status, investigation notes.
    SUMMARY     — Internal staff (managers, LOs, processors).
                  Can see risk_score and risk_level only. No indicator details.
    RESTRICTED  — Portal / borrower-facing requests.
                  Sees ONLY neutral document_status. Zero fraud information.
    """
    FULL = "full"
    SUMMARY = "summary"
    RESTRICTED = "restricted"


# =============================================================================
# CONSTANTS
# =============================================================================

# Fields that MUST be stripped from any non-FULL response.
# Presence of these fields in a portal response would constitute SAR tipping.
FRAUD_RESTRICTED_FIELDS = [
    "fraud_indicators",
    "sar_status",
    "investigation_notes",
    "alert_details",
    "suspicious_patterns",
    "suspicious_activities",
    "inconsistencies",
    "tamper_detected",
    "tamper_details",
    "indicators",
    "compliance_notes",
]

# Roles that qualify for FULL fraud data access
_COMPLIANCE_ROLES = {"admin", "site_admin", "compliance"}


# =============================================================================
# ACCESS LEVEL DETERMINATION
# =============================================================================

def get_fraud_access_level(
    current_user,
    is_portal_request: bool = False,
) -> FraudAccessLevel:
    """Determine the fraud data access level for the current user.

    Args:
        current_user: The authenticated user object (has .permission_role, .id).
        is_portal_request: True if the request originates from the borrower portal.

    Returns:
        FraudAccessLevel controlling what fraud data the caller may see.

    Rules:
        1. Portal requests -> always RESTRICTED (no fraud data whatsoever).
        2. Compliance officers + admins -> FULL.
        3. All other internal users -> SUMMARY (risk score only).
    """
    # Portal requests: ALWAYS restricted, regardless of user role.
    if is_portal_request:
        return FraudAccessLevel.RESTRICTED

    # Determine user role
    role = getattr(current_user, "permission_role", "") or ""
    role_lower = role.lower().strip()

    # Compliance officers and admins get full access
    if role_lower in _COMPLIANCE_ROLES:
        return FraudAccessLevel.FULL

    # All other internal staff get summary only
    return FraudAccessLevel.SUMMARY


# =============================================================================
# RESPONSE FILTERING
# =============================================================================

def filter_fraud_response(
    data: Dict[str, Any],
    access_level: FraudAccessLevel,
) -> Dict[str, Any]:
    """Filter fraud analysis response based on access level.

    This is the primary anti-tipping gate. It removes fraud indicator
    details from responses destined for unauthorized viewers.

    Args:
        data: The raw fraud analysis response dict.
        access_level: The caller's FraudAccessLevel.

    Returns:
        A filtered copy of the data dict. The original is not mutated.
    """
    if access_level == FraudAccessLevel.FULL:
        # Compliance staff: return everything unchanged
        return data

    if access_level == FraudAccessLevel.RESTRICTED:
        # Portal / borrower: return ONLY neutral document status.
        # NO risk scores, NO indicators, NO recommendations.
        return _build_restricted_response(data)

    # SUMMARY: internal staff see risk score + risk level + recommendation
    # but NO indicator details, NO SAR data, NO investigation specifics.
    return _build_summary_response(data)


def _build_restricted_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a borrower-safe response with zero fraud information.

    The borrower sees only a neutral document_status string.
    If fraud is detected, the status says "under review" -- never "fraud".
    """
    # Determine a neutral status from the risk level
    risk_level = (data.get("risk_level") or "").upper()
    if risk_level in ("HIGH", "CRITICAL"):
        document_status = "under_review"
    elif risk_level == "MEDIUM":
        document_status = "under_review"
    elif data.get("risk_score", 0) > 0:
        document_status = "pending"
    else:
        document_status = "approved"

    return {
        "loan_id": data.get("loan_id"),
        "document_status": document_status,
        "total_documents": data.get("total_documents") or data.get("documents_analyzed"),
    }


def _build_summary_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a summary response with risk score but no indicator details.

    Internal staff can see that a loan is flagged and the risk level,
    but they cannot see specific fraud indicators, SAR status, or
    investigation notes.
    """
    filtered = {}

    # Allowlisted keys for SUMMARY level
    summary_allowed = {
        "loan_id",
        "risk_score",
        "risk_level",
        "total_documents",
        "documents_analyzed",
        "analyzed_at",
        "recommendation",
    }

    for key, value in data.items():
        if key in summary_allowed:
            filtered[key] = value

    # Provide a single recommendation string (no details)
    recommendations = data.get("recommendations")
    if recommendations and isinstance(recommendations, list):
        # Only the first, most general recommendation
        filtered["recommendation"] = recommendations[0] if recommendations else None
    elif isinstance(recommendations, str):
        filtered["recommendation"] = recommendations

    return filtered


def strip_fraud_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove all fraud-sensitive fields from a dict (deep copy).

    Utility for sanitizing any response dict that might contain
    fraud data before it reaches a non-authorized viewer.
    """
    if not isinstance(data, dict):
        return data

    cleaned = {}
    for key, value in data.items():
        if key in FRAUD_RESTRICTED_FIELDS:
            continue
        if isinstance(value, dict):
            cleaned[key] = strip_fraud_fields(value)
        elif isinstance(value, list):
            cleaned[key] = [
                strip_fraud_fields(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_fraud_data_access(
    db: Session,
    user_id: Optional[int],
    organization_id: Optional[int],
    loan_id: Optional[int],
    access_level: FraudAccessLevel,
    endpoint: str,
    granted: bool = True,
    denial_reason: Optional[str] = None,
) -> None:
    """Log every access to fraud detection data for BSA audit trail.

    All fraud data accesses -- successful or denied -- are recorded.
    This is a compliance requirement under BSA/AML regulations.

    Args:
        db: SQLAlchemy session.
        user_id: The accessing user's ID.
        organization_id: The user's organization ID.
        loan_id: The loan being accessed.
        access_level: The FraudAccessLevel that was applied.
        endpoint: The API endpoint path.
        granted: Whether access was granted.
        denial_reason: If denied, the reason.
    """
    try:
        db.execute(
            text("""
                INSERT INTO document_access_logs
                    (organization_id, document_id, document_type, user_id,
                     access_type, access_granted, denial_reason, extra_metadata,
                     created_at)
                VALUES
                    (:org_id, :loan_id, 'fraud_data_access', :user_id,
                     'view', :granted, :denial_reason,
                     CAST(:metadata AS json),
                     :now)
            """),
            {
                "org_id": organization_id,
                "loan_id": loan_id or 0,
                "user_id": user_id,
                "granted": granted,
                "denial_reason": denial_reason,
                "metadata": _build_audit_metadata(
                    access_level, endpoint, granted, denial_reason,
                ),
                "now": datetime.now(timezone.utc),
            },
        )
        db.commit()
    except Exception as e:
        logger.exception(
            "Failed to log fraud data access (user=%s, loan=%s, endpoint=%s): %s",
            user_id, loan_id, endpoint, e,
        )
        try:
            db.rollback()
        except Exception:
            pass


def _build_audit_metadata(
    access_level: FraudAccessLevel,
    endpoint: str,
    granted: bool,
    denial_reason: Optional[str],
) -> str:
    """Build JSON metadata for the audit log entry."""
    import json
    return json.dumps({
        "audit_type": "fraud_data_access",
        "access_level": access_level.value,
        "endpoint": endpoint,
        "granted": granted,
        "denial_reason": denial_reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bsa_regulated": True,
    })
