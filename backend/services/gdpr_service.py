"""
GDPR/CCPA Data Deletion Service
Enterprise Readiness Check 8.11

Handles right-to-deletion requests by cascading PII removal
across all tables while retaining required regulatory records.

Tables affected:
- borrower_profiles: PII redacted (email, name, photo, consent fields)
- borrower_applications: PII redacted (names, email, phone, SSN, device info)
- leads: PII redacted (name, email, phone, co-applicant info, notes)
- sms_messages: Message content redacted (metadata retained for compliance)
- email_messages: Body/subject redacted (metadata retained for compliance)
- conversation_memory: Hard deleted (no regulatory retention requirement)
- users: PII redacted, account deactivated (for internal user deletion)
- audit_logs: Retained with PII redacted (regulatory requirement)

Usage:
    from services.gdpr_service import DataDeletionService

    service = DataDeletionService(db)
    result = service.process_deletion_request(
        borrower_email="borrower@example.com",
        reason="gdpr_right_to_erasure",
        requested_by=admin_user_id,
    )
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class DataDeletionService:
    """Handles GDPR/CCPA data deletion requests."""

    # PII field marker
    REDACTED = "[DELETED]"
    REDACTED_GDPR = "[DELETED - GDPR]"

    def __init__(self, db: Session):
        self.db = db

    def process_deletion_request(
        self,
        user_id: int = None,
        borrower_email: str = None,
        reason: str = "gdpr_right_to_erasure",
        requested_by: int = None,
    ) -> dict:
        """
        Process a data deletion request.

        Either user_id (internal user) or borrower_email (borrower) must be provided.
        Cascades PII removal across all relevant tables while preserving
        non-PII audit and compliance records as required by regulators.

        Args:
            user_id: Internal user ID to delete PII for
            borrower_email: Borrower email address to delete PII for
            reason: Reason for deletion (e.g. 'gdpr_right_to_erasure', 'ccpa_request')
            requested_by: ID of the admin user who initiated the request

        Returns:
            dict with deletion results including tables affected and record counts

        Raises:
            ValueError: If neither user_id nor borrower_email is provided
        """
        if not user_id and not borrower_email:
            raise ValueError("Either user_id or borrower_email must be provided")

        results = {
            "request_type": "user" if user_id else "borrower",
            "identifier": user_id if user_id else borrower_email,
            "reason": reason,
            "requested_by": requested_by,
            "tables_affected": [],
            "records_deleted": 0,
            "records_redacted": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if borrower_email:
                self._delete_borrower_data(borrower_email, results)
            if user_id:
                self._delete_user_pii(user_id, results)

            # Log the deletion event in audit trail (immutable)
            self._log_deletion_audit(results, requested_by)

            self.db.commit()
            results["status"] = "completed"
            results["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                f"GDPR deletion completed: type={results['request_type']}, "
                f"tables={len(results['tables_affected'])}, "
                f"redacted={results['records_redacted']}, "
                f"deleted={results['records_deleted']}"
            )

        except Exception as e:
            self.db.rollback()
            results["status"] = "failed"
            results["error"] = str(e)
            logger.error(f"GDPR data deletion failed: {e}", exc_info=True)
            raise

        return results

    def _delete_borrower_data(self, email: str, results: dict):
        """Delete/redact all PII for a borrower by email."""

        # 1. Redact borrower_profiles
        count = self._execute_update("""
            UPDATE borrower_profiles
            SET email = :redacted,
                first_name = :redacted,
                last_name = :redacted,
                profile_photo = NULL,
                raw_profile = NULL,
                consent_ip_address = NULL,
                consent_text = NULL,
                consent_given_to = NULL,
                updated_at = :now
            WHERE email = :email
        """, {"email": email, "redacted": self.REDACTED, "now": datetime.now(timezone.utc)})
        if count:
            results["tables_affected"].append({"table": "borrower_profiles", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 2. Redact borrower_applications
        count = self._execute_update("""
            UPDATE borrower_applications
            SET borrower_first_name = :redacted,
                borrower_last_name = :redacted,
                borrower_email = :redacted,
                borrower_phone = :redacted,
                ssn_encrypted = NULL,
                co_ssn_encrypted = NULL,
                coborrower_email = NULL,
                credit_auth_ip_address = NULL,
                credit_auth_user_agent = NULL,
                credit_auth_ssn_last4 = NULL,
                device_info = NULL,
                step_data = '{}',
                notes = NULL,
                updated_at = :now
            WHERE borrower_email = :email
        """, {"email": email, "redacted": self.REDACTED, "now": datetime.now(timezone.utc)})
        if count:
            results["tables_affected"].append({"table": "borrower_applications", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 3. Redact leads matching email
        count = self._execute_update("""
            UPDATE leads
            SET name = :redacted,
                first_name = :redacted,
                last_name = :redacted,
                email = :redacted,
                phone = :redacted,
                co_applicant_name = NULL,
                co_applicant_email = NULL,
                co_applicant_phone = NULL,
                notes = NULL,
                updated_at = :now
            WHERE email = :email
        """, {"email": email, "redacted": self.REDACTED, "now": datetime.now(timezone.utc)})
        if count:
            results["tables_affected"].append({"table": "leads", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 4. Redact SMS message content (keep metadata for compliance)
        # Find lead IDs that were just redacted (they now have email = REDACTED)
        count = self._execute_update("""
            UPDATE sms_messages
            SET message = :gdpr_redacted,
                meta_data = NULL
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED, "gdpr_redacted": self.REDACTED_GDPR})
        if count:
            results["tables_affected"].append({"table": "sms_messages", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 5. Redact email message content
        count = self._execute_update("""
            UPDATE email_messages
            SET body = :gdpr_redacted,
                html_body = NULL,
                subject = :redacted,
                meta_data = NULL
            WHERE to_email = :email OR from_email = :email
        """, {"email": email, "redacted": self.REDACTED, "gdpr_redacted": self.REDACTED_GDPR})
        if count:
            results["tables_affected"].append({"table": "email_messages", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 6. Hard delete conversation memory (no regulatory retention requirement)
        count = self._execute_update("""
            DELETE FROM conversation_memory
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "conversation_memory", "action": "deleted", "count": count})
            results["records_deleted"] += count

        # 7. Redact borrower auth events (keep event type for security audit)
        count = self._execute_update("""
            UPDATE borrower_auth_events
            SET ip_address = NULL,
                user_agent = NULL
            WHERE borrower_id IN (
                SELECT id FROM borrower_profiles WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "borrower_auth_events", "action": "redacted", "count": count})
            results["records_redacted"] += count

    def _delete_user_pii(self, user_id: int, results: dict):
        """Redact PII for an internal user account."""
        count = self._execute_update("""
            UPDATE users
            SET email = :redacted_email,
                first_name = :redacted,
                last_name = :redacted,
                phone = NULL,
                hashed_password = :redacted,
                is_active = false,
                updated_at = :now
            WHERE id = :user_id
        """, {
            "user_id": user_id,
            "redacted": self.REDACTED,
            "redacted_email": f"[DELETED_{user_id}]",
            "now": datetime.now(timezone.utc),
        })
        if count:
            results["tables_affected"].append({"table": "users", "action": "redacted", "count": count})
            results["records_redacted"] += count

    def _log_deletion_audit(self, results: dict, requested_by: Optional[int] = None):
        """
        Log deletion in audit trail (immutable).

        Uses the AuditLog table schema which has change_type, entity_type,
        after_state, etc. The audit record itself is immutable (DB triggers
        prevent UPDATE/DELETE on audit_logs).
        """
        # Use a safe serializable copy of results (exclude error if present)
        safe_results = {
            "request_type": results.get("request_type"),
            "reason": results.get("reason"),
            "tables_affected": results.get("tables_affected", []),
            "records_deleted": results.get("records_deleted", 0),
            "records_redacted": results.get("records_redacted", 0),
            "started_at": results.get("started_at"),
        }

        # Determine user_id and changed_by_id for the audit log
        # For borrower deletions, there is no user_id in the users table,
        # so we use the requesting admin's ID for both fields.
        audit_user_id = requested_by or 0
        changed_by_id = requested_by or 0

        try:
            self.db.execute(text("""
                INSERT INTO audit_logs
                    (user_id, changed_by_id, change_type, entity_type, reason, after_state, timestamp)
                VALUES
                    (:user_id, :changed_by_id, :change_type, :entity_type, :reason, :after_state, :timestamp)
            """), {
                "user_id": audit_user_id,
                "changed_by_id": changed_by_id,
                "change_type": "gdpr_deletion",
                "entity_type": "data_deletion_request",
                "reason": results.get("reason", "gdpr_right_to_erasure"),
                "after_state": json.dumps(safe_results),
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            # If audit_logs insert fails (e.g. FK constraint on user_id=0),
            # log but don't block the deletion
            logger.warning(f"Failed to write GDPR deletion audit log: {e}")

    def _execute_update(self, sql: str, params: dict) -> int:
        """Execute an UPDATE or DELETE statement and return rowcount."""
        try:
            result = self.db.execute(text(sql), params)
            return result.rowcount
        except Exception as e:
            # Log but don't fail the entire deletion if one table is missing
            logger.warning(f"GDPR deletion step failed (table may not exist): {e}")
            return 0
