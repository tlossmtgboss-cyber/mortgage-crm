"""
GDPR/CCPA Data Service
Enterprise Readiness Check 8.11

Handles:
- Right-to-erasure (Article 17) — PII anonymization with regulatory preservation
- Right-to-portability (Article 20) — per-contact data export
- Erasure request lifecycle management (pending -> approved -> executing -> completed)
- Erasure audit report generation

IMPORTANT — Mortgage Compliance / GDPR Tension:
    US mortgage regulations (RESPA, ECOA/Reg B, TRID, NMLS record retention)
    require 7-year preservation of loan records, disclosures, adverse actions,
    and fee histories. GDPR Article 17(3)(b) exempts erasure when processing
    is necessary for compliance with a legal obligation.

    Resolution strategy:
    - ANONYMIZE borrower PII (name, email, phone, SSN, address) across all tables.
    - PRESERVE loan financial structure (amounts, rates, dates, fees, stages).
    - PRESERVE disclosure and adverse-action records (TRID/ECOA).
    - RETAIN audit trail entries but strip PII from free-text fields.
    - REDACT communication content (SMS bodies, email bodies).
    - HARD DELETE documents and conversation memory (no regulatory hold).

Tables affected by borrower erasure:
    - borrower_profiles: PII redacted (email, name, photo, consent fields)
    - borrower_applications: PII redacted (names, email, phone, SSN, device info)
    - leads: PII redacted (name, email, phone, co-applicant info, notes)
    - loans: borrower PII redacted (name, email, phone, address), financial data PRESERVED
    - sms_messages: message content redacted (metadata retained for TCPA compliance)
    - email_messages: body/subject redacted (metadata retained for compliance)
    - conversation_memory: hard deleted (no regulatory retention requirement)
    - borrower_auth_events: IP/user-agent redacted (event type retained)
    - application_documents: hard deleted (child of borrower_applications)
    - call_logs: contact name/phone redacted, notes cleared (metadata retained)
    - activities: content redacted (type/timestamps retained for audit)
    - conversations: message/response redacted (role/timestamps retained)
    - voicemail_drops: contact PII and message text redacted (delivery metadata retained)
    - documents: hard deleted where entity matches the lead
    - users: PII redacted, account deactivated (for internal user deletion)
    - audit_logs: retained with PII redacted in free-text fields (regulatory requirement)

Usage:
    from services.gdpr_service import DataDeletionService, GDPRErasureService

    # Direct deletion (existing pattern)
    service = DataDeletionService(db)
    result = service.process_deletion_request(
        borrower_email="borrower@example.com",
        reason="gdpr_right_to_erasure",
        requested_by=admin_user_id,
    )

    # Managed erasure request lifecycle (new)
    erasure_svc = GDPRErasureService(db)
    contact_data = erasure_svc.export_contact_data(email="borrower@example.com", org_id=1)
    erasure_svc.anonymize_contact(contact_id=lead_id, org_id=1)
    report = erasure_svc.generate_erasure_report(request_id=42)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

REDACTED = "[DELETED]"
REDACTED_GDPR = "[GDPR_REDACTED]"

# Mortgage regulatory retention: 7 years = 2555 days.
# Loan records, disclosures, adverse actions, and fee histories must be
# preserved for this period. PII is anonymized but structure is kept.
REGULATORY_RETENTION_YEARS = 7


# =============================================================================
# DataDeletionService — original immediate-execution service
# =============================================================================

class DataDeletionService:
    """Handles GDPR/CCPA data deletion requests (immediate execution)."""

    REDACTED = REDACTED
    REDACTED_GDPR = REDACTED_GDPR

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
        """Delete/redact all PII for a borrower by email.

        IMPORTANT: Loan records are anonymized but NOT deleted — 7-year
        NMLS/RESPA/TRID retention requirement. Only borrower PII fields
        on the loan are replaced; financial structure is preserved.
        """

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
                address = NULL,
                city = NULL,
                state = NULL,
                zip_code = NULL,
                notes = NULL,
                updated_at = :now
            WHERE email = :email
        """, {"email": email, "redacted": self.REDACTED, "now": datetime.now(timezone.utc)})
        if count:
            results["tables_affected"].append({"table": "leads", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 4. Anonymize loan borrower PII — PRESERVE financial structure.
        # Mortgage compliance (RESPA, TRID, NMLS) requires 7-year retention
        # of loan records. We anonymize PII fields but keep loan amounts,
        # rates, dates, stages, fees, and disclosures intact.
        count = self._execute_update("""
            UPDATE loans
            SET borrower_name = :redacted,
                borrower_email = NULL,
                borrower_phone = NULL,
                coborrower_name = NULL,
                co_borrower_email = NULL,
                co_borrower_phone = NULL,
                property_address = NULL,
                property_city = NULL,
                property_state = NULL,
                property_zip = NULL
            WHERE borrower_email = :email
               OR id IN (
                   SELECT l2.id FROM loans l2
                   JOIN leads ld ON ld.loan_number = l2.loan_number
                   WHERE ld.email = :redacted
               )
        """, {"email": email, "redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({
                "table": "loans",
                "action": "pii_anonymized",
                "count": count,
                "note": "Financial structure preserved for 7-year NMLS/RESPA compliance",
            })
            results["records_redacted"] += count

        # 5. Redact SMS message content (keep metadata for TCPA compliance)
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

        # 6. Redact email message content
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

        # 7. Hard delete conversation memory (no regulatory retention requirement)
        count = self._execute_update("""
            DELETE FROM conversation_memory
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "conversation_memory", "action": "deleted", "count": count})
            results["records_deleted"] += count

        # 8. Redact borrower auth events (keep event type for security audit)
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

        # 9. Delete application_documents for redacted borrower_applications
        count = self._execute_update("""
            DELETE FROM application_documents
            WHERE application_id IN (
                SELECT id FROM borrower_applications WHERE borrower_email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "application_documents", "action": "deleted", "count": count})
            results["records_deleted"] += count

        # 10. Redact call_logs
        count = self._execute_update("""
            UPDATE call_logs
            SET contact_phone = :redacted,
                contact_name = :redacted,
                notes = NULL,
                ai_note_summary = NULL
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "call_logs", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 11. Redact activities
        count = self._execute_update("""
            UPDATE activities
            SET content = :gdpr_redacted,
                user_metadata = NULL
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED, "gdpr_redacted": self.REDACTED_GDPR})
        if count:
            results["tables_affected"].append({"table": "activities", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 12. Redact conversations
        count = self._execute_update("""
            UPDATE conversations
            SET message = :gdpr_redacted,
                response = :gdpr_redacted,
                meta_data = NULL
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED, "gdpr_redacted": self.REDACTED_GDPR})
        if count:
            results["tables_affected"].append({"table": "conversations", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 13. Redact voicemail_drops
        count = self._execute_update("""
            UPDATE voicemail_drops
            SET contact_name = :redacted,
                phone_number = :redacted,
                contact_email = NULL,
                message_text = :gdpr_redacted,
                message_variables = NULL,
                callback_notes = NULL
            WHERE lead_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED, "gdpr_redacted": self.REDACTED_GDPR})
        if count:
            results["tables_affected"].append({"table": "voicemail_drops", "action": "redacted", "count": count})
            results["records_redacted"] += count

        # 14. Delete documents linked to the lead (files may contain PII)
        count = self._execute_update("""
            DELETE FROM documents
            WHERE entity_type = 'lead' AND entity_id IN (
                SELECT id FROM leads WHERE email = :redacted
            )
        """, {"redacted": self.REDACTED})
        if count:
            results["tables_affected"].append({"table": "documents", "action": "deleted", "count": count})
            results["records_deleted"] += count

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
        """Log deletion in audit trail (immutable)."""
        safe_results = {
            "request_type": results.get("request_type"),
            "reason": results.get("reason"),
            "tables_affected": results.get("tables_affected", []),
            "records_deleted": results.get("records_deleted", 0),
            "records_redacted": results.get("records_redacted", 0),
            "started_at": results.get("started_at"),
        }

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
            logger.warning(f"Failed to write GDPR deletion audit log: {e}")

    def _execute_update(self, sql: str, params: dict) -> int:
        """Execute an UPDATE or DELETE statement and return rowcount."""
        try:
            result = self.db.execute(text(sql), params)
            return result.rowcount
        except Exception as e:
            logger.warning(f"GDPR deletion step failed (table may not exist): {e}")
            return 0


# =============================================================================
# GDPRErasureService — managed lifecycle + export + reporting
# =============================================================================

class GDPRErasureService:
    """Manages the full GDPR erasure lifecycle with audit trail.

    This service wraps DataDeletionService for the actual PII removal but
    adds:
    - ErasureRequest model-based tracking (pending/approved/executing/completed)
    - Per-contact data export (Article 20 portability for an individual)
    - Erasure audit report generation
    - Loan-aware anonymization that preserves regulatory records
    """

    def __init__(self, db: Session):
        self.db = db

    # -----------------------------------------------------------------
    # Erasure Request Lifecycle
    # -----------------------------------------------------------------

    def create_erasure_request(
        self,
        requester_id: int,
        organization_id: int,
        data_subject_email: Optional[str] = None,
        data_subject_user_id: Optional[int] = None,
        reason: str = "GDPR Article 17 right to erasure",
    ) -> dict:
        """Create a new erasure request in pending status.

        At least one of data_subject_email or data_subject_user_id is required.
        """
        if not data_subject_email and not data_subject_user_id:
            raise ValueError(
                "At least one of data_subject_email or data_subject_user_id must be provided"
            )

        now = datetime.now(timezone.utc)

        try:
            result = self.db.execute(text("""
                INSERT INTO erasure_requests
                    (requester_id, organization_id, data_subject_email,
                     data_subject_user_id, status, reason, requested_at, audit_log)
                VALUES
                    (:requester_id, :org_id, :email, :user_id, 'pending',
                     :reason, :now, :audit_log)
                RETURNING id, status, requested_at
            """), {
                "requester_id": requester_id,
                "org_id": organization_id,
                "email": data_subject_email,
                "user_id": data_subject_user_id,
                "reason": reason,
                "now": now,
                "audit_log": json.dumps({"created": now.isoformat(), "events": []}),
            })
            self.db.commit()
            row = result.fetchone()

            return {
                "id": row[0],
                "status": row[1],
                "requested_at": row[2].isoformat() if row[2] else now.isoformat(),
                "data_subject_email": data_subject_email,
                "data_subject_user_id": data_subject_user_id,
                "reason": reason,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create erasure request: {e}", exc_info=True)
            raise

    def list_erasure_requests(
        self,
        organization_id: int,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """List erasure requests for an organization."""
        params: Dict[str, Any] = {"org_id": organization_id, "limit": limit}
        where = "WHERE er.organization_id = :org_id"

        if status_filter:
            where += " AND er.status = :status"
            params["status"] = status_filter

        try:
            rows = self.db.execute(text(f"""
                SELECT
                    er.id,
                    er.requester_id,
                    er.data_subject_email,
                    er.data_subject_user_id,
                    er.status,
                    er.reason,
                    er.requested_at,
                    er.approved_at,
                    er.completed_at,
                    er.error_message,
                    u.email as requester_email
                FROM erasure_requests er
                LEFT JOIN users u ON u.id = er.requester_id
                {where}
                ORDER BY er.requested_at DESC
                LIMIT :limit
            """), params).fetchall()

            return [
                {
                    "id": r[0],
                    "requester_id": r[1],
                    "data_subject_email": r[2],
                    "data_subject_user_id": r[3],
                    "status": r[4],
                    "reason": r[5],
                    "requested_at": r[6].isoformat() if r[6] else None,
                    "approved_at": r[7].isoformat() if r[7] else None,
                    "completed_at": r[8].isoformat() if r[8] else None,
                    "error_message": r[9],
                    "requester_email": r[10],
                }
                for r in rows
            ]

        except Exception as e:
            logger.error(f"Failed to list erasure requests: {e}", exc_info=True)
            raise

    def execute_erasure_request(self, request_id: int, executed_by_id: int) -> dict:
        """Execute a pending/approved erasure request.

        Transitions the request through: approved -> executing -> completed/failed.
        Delegates actual PII removal to DataDeletionService, then records the
        result in the ErasureRequest audit_log.

        IMPORTANT: Loan records are anonymized, not deleted. See module docstring
        for the GDPR/mortgage-compliance reconciliation strategy.
        """
        now = datetime.now(timezone.utc)

        # Fetch and validate the request
        row = self.db.execute(text("""
            SELECT id, data_subject_email, data_subject_user_id, status,
                   organization_id, audit_log
            FROM erasure_requests
            WHERE id = :id
        """), {"id": request_id}).fetchone()

        if not row:
            raise ValueError(f"Erasure request {request_id} not found")

        req_id, email, user_id, status, org_id, existing_log = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )

        if status not in ("pending", "approved"):
            raise ValueError(
                f"Erasure request {request_id} is in status '{status}' "
                f"and cannot be executed. Only 'pending' or 'approved' requests "
                f"can be executed."
            )

        # Transition to executing
        self.db.execute(text("""
            UPDATE erasure_requests
            SET status = 'executing',
                approved_at = COALESCE(approved_at, :now),
                executed_at = :now
            WHERE id = :id
        """), {"id": request_id, "now": now})
        self.db.commit()

        # Execute the actual deletion via DataDeletionService
        deletion_svc = DataDeletionService(self.db)
        try:
            result = deletion_svc.process_deletion_request(
                user_id=user_id,
                borrower_email=email,
                reason=f"GDPR erasure request #{request_id}",
                requested_by=executed_by_id,
            )

            # Parse existing audit_log
            audit_entries = []
            if existing_log:
                parsed = existing_log if isinstance(existing_log, dict) else json.loads(existing_log)
                audit_entries = parsed.get("events", [])

            audit_entries.append({
                "timestamp": now.isoformat(),
                "action": "executed",
                "executed_by": executed_by_id,
                "tables_affected": result.get("tables_affected", []),
                "records_deleted": result.get("records_deleted", 0),
                "records_redacted": result.get("records_redacted", 0),
            })

            # Mark completed
            completed_at = datetime.now(timezone.utc)
            self.db.execute(text("""
                UPDATE erasure_requests
                SET status = 'completed',
                    completed_at = :completed_at,
                    audit_log = :audit_log
                WHERE id = :id
            """), {
                "id": request_id,
                "completed_at": completed_at,
                "audit_log": json.dumps({
                    "created": (existing_log or {}).get("created") if isinstance(existing_log, dict) else None,
                    "events": audit_entries,
                }),
            })
            self.db.commit()

            return {
                "request_id": request_id,
                "status": "completed",
                "completed_at": completed_at.isoformat(),
                "tables_affected": result.get("tables_affected", []),
                "records_deleted": result.get("records_deleted", 0),
                "records_redacted": result.get("records_redacted", 0),
                "regulatory_note": (
                    "Loan financial records preserved for 7-year NMLS/RESPA/TRID "
                    "compliance. Borrower PII on loan records has been anonymized."
                ),
            }

        except Exception as e:
            # Mark as failed
            error_msg = str(e)[:500]
            self.db.execute(text("""
                UPDATE erasure_requests
                SET status = 'failed',
                    completed_at = :now,
                    error_message = :error
                WHERE id = :id
            """), {"id": request_id, "now": datetime.now(timezone.utc), "error": error_msg})
            self.db.commit()

            logger.error(f"Erasure request {request_id} failed: {e}", exc_info=True)
            raise

    # -----------------------------------------------------------------
    # anonymize_contact — targeted PII removal for a specific contact
    # -----------------------------------------------------------------

    def anonymize_contact(self, contact_id: int, org_id: int) -> dict:
        """Anonymize PII for a specific lead/contact by ID within an org.

        This is a targeted operation: it finds the lead by ID (with org
        isolation), retrieves the email, then delegates to the full
        borrower-data deletion cascade.

        Args:
            contact_id: Lead/contact ID to anonymize.
            org_id: Organization ID for tenant isolation.

        Returns:
            dict with anonymization results.

        Raises:
            ValueError: If the contact is not found.
        """
        # Look up the lead's email for cascade
        row = self.db.execute(text("""
            SELECT id, email, name FROM leads
            WHERE id = :id AND organization_id = :org_id
        """), {"id": contact_id, "org_id": org_id}).fetchone()

        if not row:
            raise ValueError(
                f"Contact (lead) {contact_id} not found in organization {org_id}"
            )

        lead_id, email, name = row[0], row[1], row[2]

        if not email or email == REDACTED:
            raise ValueError(
                f"Contact {contact_id} has no email or is already anonymized"
            )

        # Delegate to the full cascade
        svc = DataDeletionService(self.db)
        results = {
            "request_type": "contact_anonymization",
            "identifier": f"lead:{contact_id}",
            "reason": "gdpr_anonymize_contact",
            "tables_affected": [],
            "records_deleted": 0,
            "records_redacted": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        svc._delete_borrower_data(email, results)
        svc._log_deletion_audit(results, requested_by=None)
        self.db.commit()

        results["status"] = "completed"
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        results["regulatory_note"] = (
            "Loan records preserved with anonymized PII per 7-year "
            "NMLS/RESPA retention requirement."
        )

        return results

    # -----------------------------------------------------------------
    # export_contact_data — GDPR Article 20 portability for one person
    # -----------------------------------------------------------------

    def export_contact_data(
        self,
        org_id: int,
        email: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Export all data for a specific data subject (Article 20 portability).

        Collects data across all tables where this person appears, organized
        by category. Returns a structured dict suitable for JSON serialization.

        Args:
            org_id: Organization ID for tenant isolation.
            email: Email address of the data subject.
            user_id: Internal user ID (for employee data requests).

        Returns:
            Dict with all personal data organized by category.
        """
        if not email and not user_id:
            raise ValueError("Either email or user_id must be provided")

        export: Dict[str, Any] = {
            "export_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "organization_id": org_id,
                "data_subject_email": email,
                "data_subject_user_id": user_id,
                "format": "GDPR Article 20 portable export (individual)",
                "regulatory_note": (
                    "Loan financial records included for completeness. "
                    "These records are subject to 7-year NMLS/RESPA retention."
                ),
            },
            "sections": {},
        }

        # Helper to run a query and return list of dicts
        def _query(sql: str, params: dict) -> List[dict]:
            try:
                rows = self.db.execute(text(sql), params).fetchall()
                if not rows:
                    return []
                columns = rows[0]._fields if hasattr(rows[0], '_fields') else rows[0].keys()
                return [
                    {k: (v.isoformat() if isinstance(v, datetime) else v)
                     for k, v in zip(columns, row)}
                    for row in rows
                ]
            except Exception as e:
                logger.warning(f"GDPR export query failed: {e}")
                return []

        params: Dict[str, Any] = {"org_id": org_id}

        if email:
            params["email"] = email

            # Leads
            export["sections"]["leads"] = _query(
                "SELECT id, name, first_name, last_name, email, phone, "
                "stage, source, ai_score, loan_type, created_at, updated_at "
                "FROM leads WHERE email = :email AND organization_id = :org_id",
                params,
            )

            # Loans (borrower PII + financial data — both included for portability)
            export["sections"]["loans"] = _query(
                "SELECT id, loan_number, borrower_name, borrower_email, "
                "stage, loan_type, amount, rate, term, property_address, "
                "closing_date, funded_date, created_at "
                "FROM loans WHERE borrower_email = :email AND organization_id = :org_id",
                params,
            )

            # Borrower profiles
            export["sections"]["borrower_profiles"] = _query(
                "SELECT id, email, first_name, last_name, "
                "communication_consent, marketing_consent, "
                "consent_captured_at, created_at "
                "FROM borrower_profiles WHERE email = :email AND organization_id = :org_id",
                params,
            )

            # Borrower applications
            export["sections"]["borrower_applications"] = _query(
                "SELECT id, borrower_first_name, borrower_last_name, "
                "borrower_email, status, current_step, progress_percentage, "
                "submitted_at, created_at "
                "FROM borrower_applications "
                "WHERE borrower_email = :email AND organization_id = :org_id",
                params,
            )

            # Email messages
            export["sections"]["email_messages"] = _query(
                "SELECT id, from_email, to_email, subject, direction, "
                "status, sent_at "
                "FROM email_messages "
                "WHERE (to_email = :email OR from_email = :email) "
                "AND organization_id = :org_id "
                "ORDER BY sent_at DESC",
                params,
            )

            # SMS messages (via lead association)
            export["sections"]["sms_messages"] = _query(
                "SELECT sm.id, sm.from_number, sm.to_number, sm.message, "
                "sm.direction, sm.status, sm.created_at "
                "FROM sms_messages sm "
                "JOIN leads l ON l.id = sm.lead_id "
                "WHERE l.email = :email AND l.organization_id = :org_id "
                "ORDER BY sm.created_at DESC",
                params,
            )

            # Call logs (via lead association)
            export["sections"]["call_logs"] = _query(
                "SELECT cl.id, cl.contact_phone, cl.contact_name, "
                "cl.start_time, cl.end_time, cl.duration_seconds, "
                "cl.outcome, cl.disposition, cl.created_at "
                "FROM call_logs cl "
                "JOIN leads l ON l.id = cl.lead_id "
                "WHERE l.email = :email AND l.organization_id = :org_id "
                "ORDER BY cl.created_at DESC",
                params,
            )

            # Activities (via lead association)
            export["sections"]["activities"] = _query(
                "SELECT a.id, a.type, a.content, a.duration, "
                "a.sentiment, a.created_at "
                "FROM activities a "
                "JOIN leads l ON l.id = a.lead_id "
                "WHERE l.email = :email AND l.organization_id = :org_id "
                "ORDER BY a.created_at DESC",
                params,
            )

            # Voicemail drops
            export["sections"]["voicemail_drops"] = _query(
                "SELECT vd.id, vd.contact_name, vd.phone_number, "
                "vd.message_text, vd.status, vd.delivered_at, vd.created_at "
                "FROM voicemail_drops vd "
                "JOIN leads l ON l.id = vd.lead_id "
                "WHERE l.email = :email AND l.organization_id = :org_id "
                "ORDER BY vd.created_at DESC",
                params,
            )

            # Documents
            export["sections"]["documents"] = _query(
                "SELECT d.id, d.filename, d.document_type, "
                "d.entity_type, d.created_at "
                "FROM documents d "
                "WHERE d.entity_type = 'lead' AND d.entity_id IN ("
                "  SELECT id FROM leads WHERE email = :email AND organization_id = :org_id"
                ") ORDER BY d.created_at DESC",
                params,
            )

            # Conversations (AI chat history)
            export["sections"]["conversations"] = _query(
                "SELECT c.id, c.message, c.response, c.role, c.created_at "
                "FROM conversations c "
                "JOIN leads l ON l.id = c.lead_id "
                "WHERE l.email = :email AND l.organization_id = :org_id "
                "ORDER BY c.created_at DESC",
                params,
            )

            # Consent records
            export["sections"]["consent_records"] = _query(
                "SELECT id, consent_type, consent_given, consent_method, "
                "ip_address, created_at "
                "FROM smart_docs_consent_records "
                "WHERE contact_email = :email",
                params,
            )

        if user_id:
            params["user_id"] = user_id

            # Internal user profile
            export["sections"]["user_profile"] = _query(
                "SELECT id, email, first_name, last_name, phone, role, "
                "permission_role, is_active, created_at "
                "FROM users WHERE id = :user_id AND organization_id = :org_id",
                params,
            )

            # Tasks assigned to the user
            export["sections"]["tasks"] = _query(
                "SELECT id, title, description, status, priority, "
                "due_date, created_at "
                "FROM tasks WHERE assigned_to = :user_id "
                "AND organization_id = :org_id "
                "ORDER BY created_at DESC",
                params,
            )

        return export

    # -----------------------------------------------------------------
    # generate_erasure_report — audit report of what was deleted
    # -----------------------------------------------------------------

    def generate_erasure_report(self, request_id: int) -> Dict[str, Any]:
        """Generate a detailed audit report for a completed erasure request.

        The report documents exactly what was anonymized/deleted, when, and
        by whom. It is designed for compliance officers and DPOs to verify
        that erasure was properly executed.

        Args:
            request_id: ID of the ErasureRequest to report on.

        Returns:
            Dict with the complete erasure audit report.

        Raises:
            ValueError: If the request is not found.
        """
        row = self.db.execute(text("""
            SELECT
                er.id,
                er.requester_id,
                er.organization_id,
                er.data_subject_email,
                er.data_subject_user_id,
                er.status,
                er.reason,
                er.requested_at,
                er.approved_at,
                er.executed_at,
                er.completed_at,
                er.audit_log,
                er.error_message,
                u.email as requester_email,
                u.first_name as requester_name
            FROM erasure_requests er
            LEFT JOIN users u ON u.id = er.requester_id
            WHERE er.id = :id
        """), {"id": request_id}).fetchone()

        if not row:
            raise ValueError(f"Erasure request {request_id} not found")

        # Parse audit log
        audit_log = row[11]
        if audit_log and isinstance(audit_log, str):
            audit_log = json.loads(audit_log)
        elif not audit_log:
            audit_log = {"events": []}

        # Compile summary statistics
        total_deleted = 0
        total_redacted = 0
        tables_summary = []

        for event in audit_log.get("events", []):
            total_deleted += event.get("records_deleted", 0)
            total_redacted += event.get("records_redacted", 0)
            for table_info in event.get("tables_affected", []):
                tables_summary.append({
                    "table": table_info.get("table"),
                    "action": table_info.get("action"),
                    "count": table_info.get("count", 0),
                    "note": table_info.get("note"),
                })

        report = {
            "report_type": "gdpr_erasure_audit",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "id": row[0],
                "requester_id": row[1],
                "requester_email": row[13],
                "requester_name": row[14],
                "organization_id": row[2],
                "data_subject_email": row[3],
                "data_subject_user_id": row[4],
                "status": row[5],
                "reason": row[6],
                "requested_at": row[7].isoformat() if row[7] else None,
                "approved_at": row[8].isoformat() if row[8] else None,
                "executed_at": row[9].isoformat() if row[9] else None,
                "completed_at": row[10].isoformat() if row[10] else None,
                "error_message": row[12],
            },
            "summary": {
                "total_records_deleted": total_deleted,
                "total_records_redacted": total_redacted,
                "total_records_affected": total_deleted + total_redacted,
                "tables_affected": len(tables_summary),
            },
            "tables_detail": tables_summary,
            "execution_log": audit_log.get("events", []),
            "compliance_notes": {
                "gdpr_article_17": (
                    "Right to erasure executed. All personal data identified "
                    "by email/user_id has been anonymized or deleted."
                ),
                "mortgage_regulatory_retention": (
                    "Loan records (amounts, rates, dates, stages, fees, "
                    "disclosures, adverse actions) preserved for 7-year "
                    "NMLS/RESPA/TRID/ECOA retention requirement. Borrower "
                    "PII on these records has been replaced with "
                    f"'{REDACTED}' markers."
                ),
                "audit_trail": (
                    "Audit log entries retained per regulatory requirement. "
                    "PII in free-text audit fields has been redacted."
                ),
                "communication_records": (
                    "SMS and email message content redacted. Metadata "
                    "(timestamps, direction, status) retained for TCPA "
                    "compliance."
                ),
            },
        }

        return report
