"""
Intake Field Applier — maps CI-extracted fields to actual loan/lead records.

When the Junior LO agent extracts data like "borrower income = $95,000" or
"credit score = 720" from a call transcript, this service applies those
values to the real database records after LO approval.
"""

import logging
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Mapping from CI field names (as produced by Junior LO agent) to DB columns.
# Format: ci_field_name -> (table, column, value_type, validation_fn_or_None)
FIELD_MAP: Dict[str, Tuple[str, str, str, Any]] = {
    # Loan fields
    "loan_amount": ("loans", "loan_amount", "numeric", None),
    "interest_rate": ("loans", "rate", "numeric", lambda v: 0 < v < 20),
    "rate": ("loans", "rate", "numeric", lambda v: 0 < v < 20),
    "loan_type": ("loans", "loan_type", "string", lambda v: v.lower() in (
        "conventional", "fha", "va", "usda", "jumbo", "non_qm",
    )),
    "loan_term": ("loans", "loan_term", "string", None),
    "property_address": ("loans", "property_address", "string", None),
    "property_type": ("loans", "property_type", "string", None),
    "occupancy_type": ("loans", "occupancy_type", "string", None),
    "credit_score": ("loans", "credit_score", "integer", lambda v: 300 <= v <= 850),
    "borrower_name": ("loans", "borrower_name", "string", None),
    "borrower_email": ("loans", "borrower_email", "string", lambda v: "@" in v),
    "borrower_phone": ("loans", "borrower_phone", "string", None),
    "coborrower_name": ("loans", "coborrower_name", "string", None),
    "estimated_value": ("loans", "estimated_value", "numeric", None),
    "appraised_value": ("loans", "appraised_value", "numeric", None),
    "property_value": ("loans", "estimated_value", "numeric", None),
    "down_payment": ("loans", "down_payment_amount", "numeric", None),
    "down_payment_amount": ("loans", "down_payment_amount", "numeric", None),
    "monthly_income": ("loans", "monthly_income", "numeric", None),
    "annual_income": ("loans", "monthly_income", "numeric_annual_to_monthly", None),
    "employment_type": ("loans", "employment_type", "string", None),
    "employer_name": ("loans", "employer_name", "string", None),
    "employer": ("loans", "employer_name", "string", None),
    "years_at_job": ("loans", "years_at_job", "numeric", lambda v: 0 <= v <= 60),
    "dti_ratio": ("loans", "dti_ratio", "numeric", lambda v: 0 < v < 100),
    "dti": ("loans", "dti_ratio", "numeric", lambda v: 0 < v < 100),
    "ltv": ("loans", "ltv", "numeric", lambda v: 0 < v <= 150),
    "housing_expense": ("loans", "housing_expense", "numeric", None),
    # Lead fields (used when no loan is linked yet)
    "lead_loan_amount": ("leads", "loan_amount", "numeric", None),
    "lead_credit_score": ("leads", "credit_score", "integer", lambda v: 300 <= v <= 850),
    "lead_property_type": ("leads", "property_type", "string", None),
    "loan_purpose": ("leads", "loan_purpose", "string", None),
    "preapproval_amount": ("leads", "preapproval_amount", "numeric", None),
    "lead_annual_income": ("leads", "annual_income", "numeric", None),
}

# Minimum confidence to auto-apply (below this, flag for manual review)
MIN_CONFIDENCE_AUTO = 0.70


def coerce_value(raw_value: Any, value_type: str) -> Any:
    """Coerce a raw extracted value to the correct Python type."""
    if raw_value is None:
        return None

    raw_str = str(raw_value).strip().replace(",", "").replace("$", "").replace("%", "")

    if value_type == "numeric":
        try:
            return float(Decimal(raw_str))
        except (InvalidOperation, ValueError):
            return None
    elif value_type == "numeric_annual_to_monthly":
        try:
            annual = float(Decimal(raw_str))
            return round(annual / 12, 2)
        except (InvalidOperation, ValueError):
            return None
    elif value_type == "integer":
        try:
            return int(float(raw_str))
        except (ValueError, TypeError):
            return None
    elif value_type == "string":
        return str(raw_value).strip()[:500]  # Cap at 500 chars
    return raw_value


class IntakeFieldApplier:
    """Applies CI-extracted intake fields to loan/lead records."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    async def apply_intake_fields(
        self,
        session_id: str,
        loan_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Apply all approved intake_field artifacts for a session to the linked
        loan or lead record.

        Returns summary of applied/skipped/failed fields.
        """
        # Get approved, unexecuted intake_field artifacts
        artifacts = self.db.execute(text("""
            SELECT id, title, content, structured_data, confidence, priority
            FROM call_artifacts
            WHERE session_id = :session_id
                AND organization_id = :org_id
                AND artifact_type = 'intake_field'
                AND approval_status = 'approved'
                AND execution_status = 'pending'
            ORDER BY confidence DESC NULLS LAST
        """), {
            "session_id": session_id,
            "org_id": self.organization_id,
        }).fetchall()

        if not artifacts:
            return {"success": True, "applied": 0, "skipped": 0, "message": "No intake fields to apply"}

        # Resolve target record IDs from session if not provided
        if not loan_id or not lead_id:
            session = self.db.execute(text("""
                SELECT loan_id, lead_id FROM call_sessions
                WHERE id = :session_id AND organization_id = :org_id
            """), {"session_id": session_id, "org_id": self.organization_id}).fetchone()
            if session:
                loan_id = loan_id or (str(session.loan_id) if session.loan_id else None)
                lead_id = lead_id or (str(session.lead_id) if session.lead_id else None)

        applied = []
        skipped = []
        failed = []

        for artifact in artifacts:
            result = self._apply_single_field(artifact, loan_id, lead_id, user_id)

            if result["status"] == "applied":
                applied.append(result)
                # Mark artifact as executed
                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'executed',
                        execution_result = :result::jsonb
                    WHERE id = :artifact_id AND organization_id = :org_id
                """), {
                    "artifact_id": str(artifact.id),
                    "org_id": self.organization_id,
                    "result": json.dumps(result),
                })
            elif result["status"] == "skipped":
                skipped.append(result)
            else:
                failed.append(result)
                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'failed',
                        execution_result = :result::jsonb
                    WHERE id = :artifact_id AND organization_id = :org_id
                """), {
                    "artifact_id": str(artifact.id),
                    "org_id": self.organization_id,
                    "result": json.dumps(result),
                })

        self.db.flush()

        logger.info(
            f"Intake fields applied: {len(applied)} applied, {len(skipped)} skipped, {len(failed)} failed",
            extra={"session_id": session_id},
        )

        return {
            "success": True,
            "applied": len(applied),
            "skipped": len(skipped),
            "failed": len(failed),
            "details": {
                "applied": applied,
                "skipped": skipped,
                "failed": failed,
            },
        }

    def _apply_single_field(
        self,
        artifact,
        loan_id: Optional[str],
        lead_id: Optional[str],
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        """Apply a single intake_field artifact."""
        structured = artifact.structured_data
        if isinstance(structured, str):
            try:
                structured = json.loads(structured)
            except (json.JSONDecodeError, TypeError):
                structured = {}

        if not isinstance(structured, dict):
            structured = {}

        field_name = structured.get("field_name", "").lower().strip()
        proposed_value = structured.get("proposed_value")
        confidence = float(artifact.confidence) if artifact.confidence else 0.0

        if not field_name or proposed_value is None:
            return {
                "status": "skipped",
                "field": field_name,
                "reason": "Missing field_name or proposed_value",
            }

        # Look up field mapping
        mapping = FIELD_MAP.get(field_name)
        if not mapping:
            return {
                "status": "skipped",
                "field": field_name,
                "reason": f"Unknown field: {field_name}",
            }

        table, column, value_type, validator = mapping

        # Determine target record
        if table == "loans" and not loan_id:
            # Try to fall back to leads if we have a lead
            lead_mapping = FIELD_MAP.get(f"lead_{field_name}")
            if lead_mapping and lead_id:
                table, column, value_type, validator = lead_mapping
            else:
                return {
                    "status": "skipped",
                    "field": field_name,
                    "reason": "No linked loan record",
                }

        if table == "leads" and not lead_id:
            return {
                "status": "skipped",
                "field": field_name,
                "reason": "No linked lead record",
            }

        # Coerce value
        coerced = coerce_value(proposed_value, value_type)
        if coerced is None:
            return {
                "status": "failed",
                "field": field_name,
                "reason": f"Could not coerce '{proposed_value}' to {value_type}",
            }

        # Validate
        if validator and not validator(coerced):
            return {
                "status": "failed",
                "field": field_name,
                "reason": f"Validation failed for value: {coerced}",
            }

        # Get current value for audit trail
        record_id = loan_id if table == "loans" else lead_id
        current = self.db.execute(text(f"""
            SELECT {column} FROM {table}
            WHERE id = :record_id AND organization_id = :org_id
        """), {"record_id": record_id, "org_id": self.organization_id}).fetchone()

        old_value = getattr(current, column, None) if current else None

        # Apply update
        try:
            self.db.execute(text(f"""
                UPDATE {table}
                SET {column} = :new_value, updated_at = NOW()
                WHERE id = :record_id AND organization_id = :org_id
            """), {
                "new_value": coerced,
                "record_id": record_id,
                "org_id": self.organization_id,
            })

            logger.info(
                f"Intake field applied: {table}.{column} = {coerced}",
                extra={
                    "record_id": record_id,
                    "old_value": str(old_value),
                    "confidence": confidence,
                },
            )

            return {
                "status": "applied",
                "field": field_name,
                "table": table,
                "column": column,
                "old_value": str(old_value) if old_value is not None else None,
                "new_value": str(coerced),
                "confidence": confidence,
            }

        except Exception as e:
            logger.error(f"Failed to apply {table}.{column}: {e}")
            return {
                "status": "failed",
                "field": field_name,
                "reason": str(e),
            }
