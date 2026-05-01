"""
Privacy Compliance Service — CCPA/CPRA/GLBA

Implements Data Subject Access Request (DSAR) automation:
- Right to know (data export)
- Right to delete (soft-delete with retention overrides)
- Right to opt-out (marketing preferences)
- GLBA privacy notice tracking
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging
import uuid

from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DSARType(str, Enum):
    ACCESS = "access"
    DELETE = "delete"
    OPT_OUT = "opt_out"
    CORRECTION = "correction"
    PORTABILITY = "portability"


class DSARStatus(str, Enum):
    RECEIVED = "received"
    IDENTITY_VERIFIED = "identity_verified"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    DENIED = "denied"


CCPA_RESPONSE_DEADLINE_DAYS = 45
CCPA_EXTENSION_DAYS = 45


@dataclass
class DSARRequest:
    id: str
    org_id: str
    request_type: DSARType
    requestor_email: str
    requestor_name: str
    requestor_phone: Optional[str]
    identity_verified: bool
    status: DSARStatus
    submitted_at: datetime
    deadline: datetime
    completed_at: Optional[datetime]
    response_data: Optional[Dict[str, Any]]
    denial_reason: Optional[str]
    processed_by: Optional[str]
    notes: str


class PrivacyComplianceService:
    """
    Manages DSAR requests and privacy compliance workflows.
    """

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id

    def create_dsar(
        self,
        request_type: str,
        requestor_email: str,
        requestor_name: str,
        requestor_phone: Optional[str] = None,
    ) -> DSARRequest:
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(days=CCPA_RESPONSE_DEADLINE_DAYS)

        dsar = DSARRequest(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            request_type=DSARType(request_type),
            requestor_email=requestor_email,
            requestor_name=requestor_name,
            requestor_phone=requestor_phone,
            identity_verified=False,
            status=DSARStatus.RECEIVED,
            submitted_at=now,
            deadline=deadline,
            completed_at=None,
            response_data=None,
            denial_reason=None,
            processed_by=None,
            notes="",
        )

        self._persist_dsar(dsar)
        logger.info(f"DSAR {dsar.id} created: type={request_type}, email={requestor_email}")
        return dsar

    def verify_identity(self, dsar_id: str, verified_by: str) -> DSARRequest:
        dsar = self._load_dsar(dsar_id)
        if not dsar:
            raise ValueError(f"DSAR {dsar_id} not found")

        dsar.identity_verified = True
        dsar.status = DSARStatus.IDENTITY_VERIFIED
        dsar.processed_by = verified_by
        self._persist_dsar(dsar)
        logger.info(f"DSAR {dsar_id} identity verified by {verified_by}")
        return dsar

    def process_access_request(self, dsar_id: str, processed_by: str) -> DSARRequest:
        dsar = self._load_dsar(dsar_id)
        if not dsar:
            raise ValueError(f"DSAR {dsar_id} not found")
        if not dsar.identity_verified:
            raise ValueError("Identity must be verified before processing")

        dsar.status = DSARStatus.IN_PROGRESS

        data = self._collect_personal_data(dsar.requestor_email)
        dsar.response_data = data
        dsar.status = DSARStatus.REVIEW
        dsar.processed_by = processed_by
        self._persist_dsar(dsar)

        logger.info(f"DSAR {dsar_id} access data collected: {len(data)} categories")
        return dsar

    def process_deletion_request(self, dsar_id: str, processed_by: str) -> DSARRequest:
        dsar = self._load_dsar(dsar_id)
        if not dsar:
            raise ValueError(f"DSAR {dsar_id} not found")
        if not dsar.identity_verified:
            raise ValueError("Identity must be verified before processing")

        dsar.status = DSARStatus.IN_PROGRESS

        retention_overrides = self._check_retention_requirements(dsar.requestor_email)
        deletion_results = self._soft_delete_personal_data(
            dsar.requestor_email, processed_by, retention_overrides
        )

        dsar.response_data = {
            "deleted": deletion_results["deleted"],
            "retained": deletion_results["retained"],
            "retention_reasons": deletion_results["retention_reasons"],
        }
        dsar.status = DSARStatus.REVIEW
        dsar.processed_by = processed_by
        self._persist_dsar(dsar)

        logger.info(
            f"DSAR {dsar_id} deletion processed: "
            f"{len(deletion_results['deleted'])} deleted, "
            f"{len(deletion_results['retained'])} retained for compliance"
        )
        return dsar

    def process_opt_out(self, dsar_id: str, processed_by: str) -> DSARRequest:
        dsar = self._load_dsar(dsar_id)
        if not dsar:
            raise ValueError(f"DSAR {dsar_id} not found")

        dsar.status = DSARStatus.IN_PROGRESS
        opt_out_results = self._apply_opt_out(dsar.requestor_email)
        dsar.response_data = opt_out_results
        dsar.status = DSARStatus.COMPLETED
        dsar.completed_at = datetime.now(timezone.utc)
        dsar.processed_by = processed_by
        self._persist_dsar(dsar)

        logger.info(f"DSAR {dsar_id} opt-out completed for {dsar.requestor_email}")
        return dsar

    def complete_dsar(self, dsar_id: str, processed_by: str) -> DSARRequest:
        dsar = self._load_dsar(dsar_id)
        if not dsar:
            raise ValueError(f"DSAR {dsar_id} not found")

        dsar.status = DSARStatus.COMPLETED
        dsar.completed_at = datetime.now(timezone.utc)
        dsar.processed_by = processed_by
        self._persist_dsar(dsar)

        logger.info(f"DSAR {dsar_id} completed by {processed_by}")
        return dsar

    def get_overdue_dsars(self) -> List[DSARRequest]:
        from sqlalchemy import text
        now = datetime.now(timezone.utc)
        try:
            result = self.db.execute(
                text("""
                    SELECT id, request_type, requestor_email, status, deadline
                    FROM dsar_requests
                    WHERE org_id = :org_id
                    AND status NOT IN ('completed', 'denied')
                    AND deadline < :now
                    ORDER BY deadline ASC
                """),
                {"org_id": self.org_id, "now": now},
            )
            return [self._load_dsar(row.id) for row in result.fetchall()]
        except Exception as e:
            logger.warning(f"Could not query overdue DSARs: {e}")
            return []

    # -----------------------------------------------------------------------
    # GLBA Privacy Notice
    # -----------------------------------------------------------------------

    def record_privacy_notice_delivery(
        self, borrower_email: str, notice_version: str, delivery_method: str
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        try:
            self.db.execute(
                text("""
                    INSERT INTO privacy_notice_deliveries
                    (id, org_id, borrower_email, notice_version, delivery_method, delivered_at)
                    VALUES (:id, :org_id, :email, :version, :method, :delivered_at)
                """),
                {
                    "id": record_id, "org_id": self.org_id,
                    "email": borrower_email, "version": notice_version,
                    "method": delivery_method, "delivered_at": now,
                },
            )
            self.db.commit()
            return {"id": record_id, "delivered_at": now.isoformat()}
        except Exception as e:
            logger.warning(f"Could not record privacy notice delivery: {e}")
            self.db.rollback()
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _collect_personal_data(self, email: str) -> Dict[str, Any]:
        from sqlalchemy import text
        data = {}

        tables_and_fields = {
            "leads": ["first_name", "last_name", "email", "phone", "address", "created_at"],
            "loans": ["loan_number", "loan_amount", "property_address", "stage", "created_at"],
            "borrower_applications": ["first_name", "last_name", "email", "phone", "created_at"],
            "activities": ["activity_type", "description", "created_at"],
        }

        for table, fields in tables_and_fields.items():
            try:
                cols = ", ".join(fields)
                result = self.db.execute(
                    text(f"SELECT {cols} FROM {table} WHERE email = :email AND org_id = :org_id"),
                    {"email": email, "org_id": self.org_id},
                )
                rows = result.fetchall()
                if rows:
                    data[table] = [
                        {f: self._serialize_value(getattr(row, f, None)) for f in fields}
                        for row in rows
                    ]
            except Exception as e:
                logger.debug(f"Could not collect from {table}: {e}")

        data["collected_at"] = datetime.now(timezone.utc).isoformat()
        data["requestor_email"] = email
        return data

    def _check_retention_requirements(self, email: str) -> Dict[str, str]:
        overrides = {}
        from sqlalchemy import text

        try:
            result = self.db.execute(
                text("""
                    SELECT COUNT(*) as count FROM loans
                    WHERE email = :email AND org_id = :org_id
                    AND stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN')
                """),
                {"email": email, "org_id": self.org_id},
            )
            if result.scalar() > 0:
                overrides["loans"] = "Active loan in pipeline — GLBA retention required"
        except Exception:
            pass

        try:
            result = self.db.execute(
                text("""
                    SELECT COUNT(*) as count FROM loans
                    WHERE email = :email AND org_id = :org_id
                    AND stage = 'FUNDED'
                    AND funded_date > :cutoff
                """),
                {
                    "email": email, "org_id": self.org_id,
                    "cutoff": datetime.now(timezone.utc) - timedelta(days=365 * 7),
                },
            )
            if result.scalar() > 0:
                overrides["loans"] = "Funded loan within 7-year RESPA retention window"
        except Exception:
            pass

        overrides["voice_consents"] = "TCPA consent records retained per 5-year regulatory requirement"
        overrides["activities"] = "Audit trail retained for compliance (NMLS requirement)"
        return overrides

    def _soft_delete_personal_data(
        self, email: str, deleted_by: str, retention_overrides: Dict[str, str]
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        now = datetime.now(timezone.utc)
        deleted = []
        retained = []
        retention_reasons = {}

        deletable_tables = ["leads", "borrower_applications"]
        for table in deletable_tables:
            if table in retention_overrides:
                retained.append(table)
                retention_reasons[table] = retention_overrides[table]
                continue
            try:
                result = self.db.execute(
                    text(f"""
                        UPDATE {table}
                        SET deleted_at = :now
                        WHERE email = :email AND org_id = :org_id AND deleted_at IS NULL
                    """),
                    {"now": now, "email": email, "org_id": self.org_id},
                )
                if result.rowcount > 0:
                    deleted.append(f"{table} ({result.rowcount} records)")
            except Exception as e:
                logger.warning(f"Could not soft-delete from {table}: {e}")

        for table, reason in retention_overrides.items():
            if table not in [t.split(" (")[0] for t in deleted]:
                retained.append(table)
                retention_reasons[table] = reason

        self.db.commit()
        return {
            "deleted": deleted,
            "retained": retained,
            "retention_reasons": retention_reasons,
        }

    def _apply_opt_out(self, email: str) -> Dict[str, Any]:
        from sqlalchemy import text
        results = {}
        now = datetime.now(timezone.utc)

        try:
            self.db.execute(
                text("""
                    UPDATE leads
                    SET do_not_contact = TRUE, do_not_contact_updated_at = :now
                    WHERE email = :email AND org_id = :org_id
                """),
                {"email": email, "org_id": self.org_id, "now": now},
            )
            results["do_not_contact"] = True
        except Exception as e:
            logger.debug(f"Could not update do_not_contact: {e}")

        try:
            self.db.execute(
                text("""
                    UPDATE channel_preferences
                    SET email_opted_in = FALSE, sms_opted_in = FALSE,
                        call_opted_in = FALSE, updated_at = :now
                    WHERE contact_email = :email AND org_id = :org_id
                """),
                {"email": email, "org_id": self.org_id, "now": now},
            )
            results["channel_preferences_cleared"] = True
        except Exception as e:
            logger.debug(f"Could not update channel preferences: {e}")

        self.db.commit()
        results["opted_out_at"] = now.isoformat()
        return results

    def _persist_dsar(self, dsar: DSARRequest):
        from sqlalchemy import text
        try:
            self.db.execute(
                text("""
                    INSERT INTO dsar_requests
                    (id, org_id, request_type, requestor_email, requestor_name,
                     requestor_phone, identity_verified, status, submitted_at,
                     deadline, completed_at, response_data, denial_reason,
                     processed_by, notes)
                    VALUES
                    (:id, :org_id, :type, :email, :name, :phone, :verified,
                     :status, :submitted, :deadline, :completed, :response,
                     :denial, :processed_by, :notes)
                    ON CONFLICT (id) DO UPDATE SET
                        identity_verified = EXCLUDED.identity_verified,
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at,
                        response_data = EXCLUDED.response_data,
                        denial_reason = EXCLUDED.denial_reason,
                        processed_by = EXCLUDED.processed_by,
                        notes = EXCLUDED.notes
                """),
                {
                    "id": dsar.id, "org_id": dsar.org_id,
                    "type": dsar.request_type.value,
                    "email": dsar.requestor_email, "name": dsar.requestor_name,
                    "phone": dsar.requestor_phone,
                    "verified": dsar.identity_verified,
                    "status": dsar.status.value,
                    "submitted": dsar.submitted_at, "deadline": dsar.deadline,
                    "completed": dsar.completed_at,
                    "response": json.dumps(dsar.response_data) if dsar.response_data else None,
                    "denial": dsar.denial_reason,
                    "processed_by": dsar.processed_by,
                    "notes": dsar.notes,
                },
            )
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to persist DSAR {dsar.id}: {e}")
            self.db.rollback()
            raise

    def _load_dsar(self, dsar_id: str) -> Optional[DSARRequest]:
        from sqlalchemy import text
        try:
            result = self.db.execute(
                text("SELECT * FROM dsar_requests WHERE id = :id AND org_id = :org_id"),
                {"id": dsar_id, "org_id": self.org_id},
            )
            row = result.fetchone()
            if not row:
                return None
            return DSARRequest(
                id=row.id, org_id=row.org_id,
                request_type=DSARType(row.request_type),
                requestor_email=row.requestor_email,
                requestor_name=row.requestor_name,
                requestor_phone=row.requestor_phone,
                identity_verified=row.identity_verified,
                status=DSARStatus(row.status),
                submitted_at=row.submitted_at,
                deadline=row.deadline,
                completed_at=row.completed_at,
                response_data=json.loads(row.response_data) if row.response_data else None,
                denial_reason=row.denial_reason,
                processed_by=row.processed_by,
                notes=row.notes or "",
            )
        except Exception as e:
            logger.error(f"Failed to load DSAR {dsar_id}: {e}")
            return None

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return "[binary data]"
        return value
