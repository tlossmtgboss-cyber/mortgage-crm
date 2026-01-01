"""
GDPR/CCPA Compliance Service

Provides data subject rights implementation:
- Right to Access (data export)
- Right to Erasure (right to be forgotten)
- Right to Rectification
- Right to Data Portability
- Consent management

Enterprise Features:
- Automated DSAR processing
- Data retention enforcement
- Consent tracking
- Audit trail for compliance
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
import asyncio

logger = logging.getLogger(__name__)


class RequestType(str, Enum):
    """Types of data subject requests"""
    ACCESS = "access"  # Right to access
    ERASURE = "erasure"  # Right to be forgotten
    RECTIFICATION = "rectification"  # Right to correction
    PORTABILITY = "portability"  # Right to data portability
    RESTRICTION = "restriction"  # Right to restrict processing
    OBJECTION = "objection"  # Right to object


class RequestStatus(str, Enum):
    """Status of data subject request"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ConsentType(str, Enum):
    """Types of consent"""
    MARKETING_EMAIL = "marketing_email"
    MARKETING_SMS = "marketing_sms"
    MARKETING_PHONE = "marketing_phone"
    DATA_SHARING = "data_sharing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    THIRD_PARTY = "third_party"


@dataclass
class DataSubjectRequest:
    """Data subject request record"""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    request_type: RequestType = RequestType.ACCESS
    status: RequestStatus = RequestStatus.PENDING
    user_id: str = ""
    user_email: str = ""
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    due_date: str = ""
    completed_at: Optional[str] = None
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_type": self.request_type.value,
            "status": self.status.value,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "submitted_at": self.submitted_at,
            "due_date": self.due_date,
            "completed_at": self.completed_at,
            "notes": self.notes,
        }


@dataclass
class UserDataExport:
    """Exported user data package"""
    user_id: str
    export_date: str
    data_categories: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "user_id": self.user_id,
            "export_date": self.export_date,
            "categories": self.data_categories,
            "metadata": self.metadata,
        }, default=str, indent=2)


class DataSubjectRightsService:
    """
    Service for handling data subject access requests (DSAR).

    Implements GDPR/CCPA requirements for:
    - Data export (Article 15 GDPR)
    - Data deletion (Article 17 GDPR)
    - Data correction (Article 16 GDPR)
    - Data portability (Article 20 GDPR)
    """

    # Tables containing user data
    USER_DATA_TABLES = [
        ("users", "id"),
        ("leads", "owner_id"),
        ("loans", "loan_officer_id"),
        ("activities", "user_id"),
        ("tasks", "assigned_to"),
        ("email_interactions", "user_id"),
        ("ai_conversations", "user_id"),
    ]

    # Tables with PII that need anonymization (not deletion for regulatory reasons)
    REGULATORY_RETENTION_TABLES = [
        "loans",  # Must retain for 7 years
        "audit_log",  # Must retain for compliance
        "compliance_records",
    ]

    # GDPR deadline: 30 days
    RESPONSE_DEADLINE_DAYS = 30

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._pending_requests: Dict[str, DataSubjectRequest] = {}

    async def submit_request(
        self,
        user_id: str,
        user_email: str,
        request_type: RequestType,
        notes: str = "",
    ) -> DataSubjectRequest:
        """
        Submit a new data subject request.

        Args:
            user_id: The user's ID
            user_email: The user's email
            request_type: Type of request
            notes: Additional notes

        Returns:
            DataSubjectRequest record
        """
        due_date = datetime.now(timezone.utc) + timedelta(days=self.RESPONSE_DEADLINE_DAYS)

        request = DataSubjectRequest(
            request_type=request_type,
            user_id=user_id,
            user_email=user_email,
            due_date=due_date.isoformat(),
            notes=notes,
        )

        # Store request
        self._pending_requests[request.request_id] = request

        # Persist to database
        await self._save_request(request)

        logger.info(f"DSAR submitted: {request.request_id} - {request_type.value} for user {user_id}")

        return request

    async def _save_request(self, request: DataSubjectRequest):
        """Save request to database"""
        from sqlalchemy import text

        with self.db_session_factory() as db:
            db.execute(
                text("""
                    INSERT INTO data_subject_requests (
                        request_id, request_type, status, user_id, user_email,
                        submitted_at, due_date, notes
                    ) VALUES (
                        :request_id, :request_type, :status, :user_id, :user_email,
                        :submitted_at, :due_date, :notes
                    )
                """),
                {
                    "request_id": request.request_id,
                    "request_type": request.request_type.value,
                    "status": request.status.value,
                    "user_id": request.user_id,
                    "user_email": request.user_email,
                    "submitted_at": request.submitted_at,
                    "due_date": request.due_date,
                    "notes": request.notes,
                }
            )
            db.commit()

    async def export_user_data(self, user_id: str) -> UserDataExport:
        """
        Export all user data (Right to Access / Data Portability).

        Collects data from all tables and returns in portable format.
        """
        from sqlalchemy import text

        data_categories = {}

        with self.db_session_factory() as db:
            # User profile
            user_result = db.execute(
                text("SELECT * FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )
            user = user_result.fetchone()
            if user:
                user_dict = dict(user._mapping)
                # Remove sensitive auth data
                user_dict.pop("hashed_password", None)
                user_dict.pop("totp_secret", None)
                data_categories["profile"] = user_dict

            # Leads created/owned by user
            leads_result = db.execute(
                text("SELECT * FROM leads WHERE owner_id = :user_id"),
                {"user_id": user_id}
            )
            data_categories["leads"] = [dict(row._mapping) for row in leads_result.fetchall()]

            # Loans handled by user
            loans_result = db.execute(
                text("SELECT * FROM loans WHERE loan_officer_id = :user_id"),
                {"user_id": user_id}
            )
            data_categories["loans"] = [dict(row._mapping) for row in loans_result.fetchall()]

            # Activities
            activities_result = db.execute(
                text("SELECT * FROM activities WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1000"),
                {"user_id": user_id}
            )
            data_categories["activities"] = [dict(row._mapping) for row in activities_result.fetchall()]

            # Tasks assigned
            tasks_result = db.execute(
                text("SELECT * FROM tasks WHERE assigned_to = :user_id"),
                {"user_id": user_id}
            )
            data_categories["tasks"] = [dict(row._mapping) for row in tasks_result.fetchall()]

            # Email interactions
            try:
                email_result = db.execute(
                    text("SELECT * FROM email_interactions WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1000"),
                    {"user_id": user_id}
                )
                data_categories["emails"] = [dict(row._mapping) for row in email_result.fetchall()]
            except:
                pass

            # AI conversations
            try:
                ai_result = db.execute(
                    text("SELECT * FROM ai_conversations WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 500"),
                    {"user_id": user_id}
                )
                data_categories["ai_conversations"] = [dict(row._mapping) for row in ai_result.fetchall()]
            except:
                pass

            # Consent records
            try:
                consent_result = db.execute(
                    text("SELECT * FROM user_consents WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                data_categories["consents"] = [dict(row._mapping) for row in consent_result.fetchall()]
            except:
                pass

        export = UserDataExport(
            user_id=user_id,
            export_date=datetime.now(timezone.utc).isoformat(),
            data_categories=data_categories,
            metadata={
                "format_version": "1.0",
                "regulation": "GDPR/CCPA",
                "categories_included": list(data_categories.keys()),
            }
        )

        logger.info(f"Data export completed for user {user_id}: {len(data_categories)} categories")

        return export

    async def delete_user_data(
        self,
        user_id: str,
        hard_delete: bool = False,
    ) -> Dict[str, Any]:
        """
        Delete or anonymize user data (Right to Erasure).

        By default, performs soft delete/anonymization to comply with
        regulatory retention requirements. Hard delete only on explicit request.

        Args:
            user_id: User ID to delete
            hard_delete: If True, permanently delete (where legally allowed)

        Returns:
            Summary of deleted/anonymized data
        """
        from sqlalchemy import text

        deletion_summary = {
            "user_id": user_id,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "tables_affected": [],
            "regulatory_retained": [],
            "anonymized": [],
        }

        with self.db_session_factory() as db:
            # 1. Delete non-regulatory data
            non_regulated_tables = [
                "activities",
                "tasks",
                "email_interactions",
                "ai_conversations",
                "user_settings",
                "notifications",
            ]

            for table in non_regulated_tables:
                try:
                    if hard_delete:
                        db.execute(
                            text(f"DELETE FROM {table} WHERE user_id = :user_id"),
                            {"user_id": user_id}
                        )
                    else:
                        # Soft delete
                        db.execute(
                            text(f"UPDATE {table} SET deleted_at = :deleted_at WHERE user_id = :user_id"),
                            {"user_id": user_id, "deleted_at": datetime.now(timezone.utc)}
                        )
                    deletion_summary["tables_affected"].append(table)
                except Exception as e:
                    logger.warning(f"Could not process {table}: {e}")

            # 2. Anonymize regulatory-retained data
            # Loans must be retained for 7 years - anonymize instead
            try:
                db.execute(
                    text("""
                        UPDATE loans SET
                            borrower_name = 'ANONYMIZED',
                            borrower_email = 'anonymized@deleted.local',
                            borrower_phone = NULL,
                            borrower_ssn = NULL,
                            co_borrower_name = CASE WHEN co_borrower_name IS NOT NULL THEN 'ANONYMIZED' END,
                            notes = NULL
                        WHERE loan_officer_id = :user_id
                    """),
                    {"user_id": user_id}
                )
                deletion_summary["anonymized"].append("loans")
            except Exception as e:
                logger.warning(f"Could not anonymize loans: {e}")

            # 3. Anonymize leads
            try:
                db.execute(
                    text("""
                        UPDATE leads SET
                            first_name = 'DELETED',
                            last_name = 'USER',
                            email = CONCAT('deleted_', id, '@anonymized.local'),
                            phone = NULL,
                            notes = NULL
                        WHERE owner_id = :user_id
                    """),
                    {"user_id": user_id}
                )
                deletion_summary["anonymized"].append("leads")
            except Exception as e:
                logger.warning(f"Could not anonymize leads: {e}")

            # 4. Anonymize user account
            anonymized_email = f"deleted_{user_id}@anonymized.local"
            db.execute(
                text("""
                    UPDATE users SET
                        email = :anon_email,
                        full_name = 'Deleted User',
                        phone = NULL,
                        hashed_password = 'DELETED',
                        is_active = FALSE,
                        totp_secret = NULL,
                        backup_codes = NULL,
                        user_metadata = NULL,
                        deleted_at = :deleted_at
                    WHERE id = :user_id
                """),
                {
                    "user_id": user_id,
                    "anon_email": anonymized_email,
                    "deleted_at": datetime.now(timezone.utc),
                }
            )
            deletion_summary["anonymized"].append("users")

            db.commit()

        # Note about regulatory retention
        deletion_summary["regulatory_retained"] = [
            {"table": "loans", "reason": "7-year retention requirement", "data": "anonymized"},
            {"table": "audit_log", "reason": "Compliance requirement", "data": "retained"},
        ]

        logger.info(f"User data deletion completed for {user_id}")

        return deletion_summary

    async def get_request_status(self, request_id: str) -> Optional[DataSubjectRequest]:
        """Get status of a data subject request"""
        return self._pending_requests.get(request_id)

    async def list_pending_requests(self) -> List[DataSubjectRequest]:
        """List all pending requests"""
        return [r for r in self._pending_requests.values() if r.status == RequestStatus.PENDING]


class DataRetentionService:
    """
    Service for enforcing data retention policies.

    Implements:
    - Automatic data expiration
    - Retention policy management
    - Compliance reporting
    """

    # Default retention periods (days)
    RETENTION_POLICIES = {
        "leads": 365 * 3,  # 3 years
        "activities": 365 * 2,  # 2 years
        "email_interactions": 365 * 2,
        "ai_conversations": 365,  # 1 year
        "audit_log": 365 * 7,  # 7 years (regulatory)
        "loans": 365 * 7,  # 7 years (regulatory)
        "notifications": 90,
        "sessions": 30,
    }

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    async def apply_retention_policies(self) -> Dict[str, int]:
        """
        Apply retention policies and delete expired data.

        Returns summary of deleted records by table.
        """
        from sqlalchemy import text

        deletion_summary = {}

        with self.db_session_factory() as db:
            for table, retention_days in self.RETENTION_POLICIES.items():
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

                try:
                    # Check for date column
                    date_column = "created_at"

                    # For regulatory tables, don't delete, just log
                    if table in ["loans", "audit_log"]:
                        result = db.execute(
                            text(f"SELECT COUNT(*) FROM {table} WHERE {date_column} < :cutoff"),
                            {"cutoff": cutoff_date}
                        )
                        count = result.scalar()
                        if count > 0:
                            logger.info(f"Retention: {table} has {count} records past retention but retained for regulatory compliance")
                        continue

                    # Delete expired records
                    result = db.execute(
                        text(f"DELETE FROM {table} WHERE {date_column} < :cutoff"),
                        {"cutoff": cutoff_date}
                    )
                    deleted_count = result.rowcount
                    deletion_summary[table] = deleted_count

                    if deleted_count > 0:
                        logger.info(f"Retention: Deleted {deleted_count} expired records from {table}")

                except Exception as e:
                    logger.warning(f"Retention policy error for {table}: {e}")

            db.commit()

        return deletion_summary

    def get_retention_policy(self, table_name: str) -> int:
        """Get retention period for a table in days"""
        return self.RETENTION_POLICIES.get(table_name, 365)

    def set_retention_policy(self, table_name: str, retention_days: int):
        """Set retention period for a table"""
        self.RETENTION_POLICIES[table_name] = retention_days
        logger.info(f"Retention policy updated: {table_name} = {retention_days} days")


class ConsentManager:
    """
    Service for managing user consents.

    Implements:
    - Consent recording
    - Consent withdrawal
    - Consent history
    - Consent verification
    """

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    async def record_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        granted: bool,
        source: str = "user_action",
        ip_address: Optional[str] = None,
    ) -> str:
        """
        Record a user consent decision.

        Args:
            user_id: User ID
            consent_type: Type of consent
            granted: Whether consent was given
            source: Source of consent (user_action, form, etc.)
            ip_address: IP address when consent was given

        Returns:
            Consent record ID
        """
        from sqlalchemy import text

        consent_id = str(uuid4())

        with self.db_session_factory() as db:
            db.execute(
                text("""
                    INSERT INTO user_consents (
                        id, user_id, consent_type, granted, source,
                        ip_address, recorded_at
                    ) VALUES (
                        :id, :user_id, :consent_type, :granted, :source,
                        :ip_address, :recorded_at
                    )
                """),
                {
                    "id": consent_id,
                    "user_id": user_id,
                    "consent_type": consent_type.value,
                    "granted": granted,
                    "source": source,
                    "ip_address": ip_address,
                    "recorded_at": datetime.now(timezone.utc),
                }
            )
            db.commit()

        logger.info(f"Consent recorded: {consent_type.value} = {granted} for user {user_id}")

        return consent_id

    async def withdraw_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        reason: str = "",
    ) -> bool:
        """Withdraw a previously given consent"""
        return await self.record_consent(
            user_id=user_id,
            consent_type=consent_type,
            granted=False,
            source=f"withdrawal: {reason}",
        ) is not None

    async def check_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> bool:
        """
        Check if user has given consent for a specific type.

        Returns the most recent consent decision.
        """
        from sqlalchemy import text

        with self.db_session_factory() as db:
            result = db.execute(
                text("""
                    SELECT granted FROM user_consents
                    WHERE user_id = :user_id AND consent_type = :consent_type
                    ORDER BY recorded_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id, "consent_type": consent_type.value}
            )
            row = result.fetchone()

            if row:
                return bool(row.granted)

            return False  # No consent = not consented

    async def get_all_consents(self, user_id: str) -> Dict[str, bool]:
        """Get all consent statuses for a user"""
        consents = {}

        for consent_type in ConsentType:
            consents[consent_type.value] = await self.check_consent(user_id, consent_type)

        return consents

    async def get_consent_history(
        self,
        user_id: str,
        consent_type: Optional[ConsentType] = None,
    ) -> List[Dict[str, Any]]:
        """Get consent history for audit purposes"""
        from sqlalchemy import text

        with self.db_session_factory() as db:
            if consent_type:
                result = db.execute(
                    text("""
                        SELECT * FROM user_consents
                        WHERE user_id = :user_id AND consent_type = :consent_type
                        ORDER BY recorded_at DESC
                    """),
                    {"user_id": user_id, "consent_type": consent_type.value}
                )
            else:
                result = db.execute(
                    text("""
                        SELECT * FROM user_consents
                        WHERE user_id = :user_id
                        ORDER BY recorded_at DESC
                    """),
                    {"user_id": user_id}
                )

            return [dict(row._mapping) for row in result.fetchall()]
