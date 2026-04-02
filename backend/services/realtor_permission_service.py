"""
Realtor Portal Permission Service - Dynamic permissions based on loan status.

Provides:
- Status-based permission lookups
- Organization-specific permission overrides
- Permission caching for performance
- Role-based access control for realtors
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from functools import lru_cache
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass
class RealtorPermissions:
    """Permissions for a realtor on a specific loan."""
    can_view_status: bool = True
    can_view_timeline: bool = True
    can_view_documents: bool = False
    can_download_documents: bool = False
    can_upload_documents: bool = False
    can_send_messages: bool = True
    can_request_update: bool = True
    can_generate_prequal: bool = False
    can_generate_preapproval: bool = False
    can_view_conditions: bool = False
    can_schedule_meeting: bool = True
    ai_assistant_enabled: bool = True

    visible_document_types: List[str] = field(default_factory=list)
    hidden_fields: List[str] = field(default_factory=list)
    ai_allowed_topics: List[str] = field(default_factory=lambda: ["status", "timeline", "general"])

    @classmethod
    def from_db_row(cls, row: Dict) -> "RealtorPermissions":
        """Create from database row."""
        return cls(
            can_view_status=row.get("can_view_status", True),
            can_view_timeline=row.get("can_view_timeline", True),
            can_view_documents=row.get("can_view_documents", False),
            can_download_documents=row.get("can_download_documents", False),
            can_upload_documents=row.get("can_upload_documents", False),
            can_send_messages=row.get("can_send_messages", True),
            can_request_update=row.get("can_request_update", True),
            can_generate_prequal=row.get("can_generate_prequal", False),
            can_generate_preapproval=row.get("can_generate_preapproval", False),
            can_view_conditions=row.get("can_view_conditions", False),
            can_schedule_meeting=row.get("can_schedule_meeting", True),
            ai_assistant_enabled=row.get("ai_assistant_enabled", True),
            visible_document_types=row.get("visible_document_types") or [],
            hidden_fields=row.get("hidden_fields") or [],
            ai_allowed_topics=row.get("ai_allowed_topics") or ["status", "timeline", "general"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "can_view_status": self.can_view_status,
            "can_view_timeline": self.can_view_timeline,
            "can_view_documents": self.can_view_documents,
            "can_download_documents": self.can_download_documents,
            "can_upload_documents": self.can_upload_documents,
            "can_send_messages": self.can_send_messages,
            "can_request_update": self.can_request_update,
            "can_generate_prequal": self.can_generate_prequal,
            "can_generate_preapproval": self.can_generate_preapproval,
            "can_view_conditions": self.can_view_conditions,
            "can_schedule_meeting": self.can_schedule_meeting,
            "ai_assistant_enabled": self.ai_assistant_enabled,
            "visible_document_types": self.visible_document_types,
            "hidden_fields": self.hidden_fields,
            "ai_allowed_topics": self.ai_allowed_topics,
        }

    def has_permission(self, action: str) -> bool:
        """Check if a specific permission is granted."""
        permission_map = {
            "view_status": self.can_view_status,
            "view_timeline": self.can_view_timeline,
            "view_documents": self.can_view_documents,
            "download_documents": self.can_download_documents,
            "upload_documents": self.can_upload_documents,
            "send_messages": self.can_send_messages,
            "request_update": self.can_request_update,
            "generate_prequal": self.can_generate_prequal,
            "generate_preapproval": self.can_generate_preapproval,
            "view_conditions": self.can_view_conditions,
            "schedule_meeting": self.can_schedule_meeting,
            "ai_assistant": self.ai_assistant_enabled,
        }
        return permission_map.get(action, False)


class RealtorPermissionService:
    """
    Service for managing realtor portal permissions.

    Permission Resolution Order:
    1. Check organization-specific override (portal_status_actions with org_id)
    2. Fall back to system defaults (portal_status_actions with org_id = NULL)
    3. Apply role-based modifiers (buyer_agent vs referring_agent)
    """

    # Permission cache with TTL
    _permission_cache: Dict[str, tuple] = {}
    _cache_ttl = timedelta(minutes=5)

    def __init__(self, db: Session):
        self.db = db

    def get_permissions(
        self,
        realtor_id: int,
        loan_id: int,
        organization_id: Optional[int] = None
    ) -> RealtorPermissions:
        """
        Get permissions for a realtor on a specific loan.

        Args:
            realtor_id: The realtor's ID
            loan_id: The loan ID
            organization_id: Optional org ID (will be looked up if not provided)

        Returns:
            RealtorPermissions object
        """
        # Get loan status and org
        loan_info = self._get_loan_info(loan_id)
        if not loan_info:
            logger.warning(f"Loan {loan_id} not found")
            return self._get_minimal_permissions()

        loan_status = loan_info["status"]
        org_id = organization_id or loan_info["organization_id"]

        # Get realtor's role on this loan
        realtor_role = self._get_realtor_role(realtor_id, loan_id)
        if not realtor_role:
            logger.warning(f"Realtor {realtor_id} has no access to loan {loan_id}")
            return self._get_minimal_permissions()

        # Check cache
        cache_key = f"{org_id}:{loan_status}:{realtor_role}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Look up permissions
        permissions = self._lookup_permissions(org_id, loan_status)

        # Apply role-based modifiers
        permissions = self._apply_role_modifiers(permissions, realtor_role)

        # Cache and return
        self._set_cached(cache_key, permissions)
        return permissions

    def check_permission(
        self,
        realtor_id: int,
        loan_id: int,
        action: str
    ) -> bool:
        """
        Check if a realtor has a specific permission on a loan.

        Args:
            realtor_id: The realtor's ID
            loan_id: The loan ID
            action: The action to check (e.g., "view_documents", "send_messages")

        Returns:
            True if permitted, False otherwise
        """
        permissions = self.get_permissions(realtor_id, loan_id)
        return permissions.has_permission(action)

    def get_available_actions(
        self,
        realtor_id: int,
        loan_id: int
    ) -> List[str]:
        """Get list of available actions for a realtor on a loan."""
        permissions = self.get_permissions(realtor_id, loan_id)
        actions = []

        action_map = {
            "view_status": permissions.can_view_status,
            "view_timeline": permissions.can_view_timeline,
            "view_documents": permissions.can_view_documents,
            "download_documents": permissions.can_download_documents,
            "upload_documents": permissions.can_upload_documents,
            "send_messages": permissions.can_send_messages,
            "request_update": permissions.can_request_update,
            "generate_prequal": permissions.can_generate_prequal,
            "generate_preapproval": permissions.can_generate_preapproval,
            "view_conditions": permissions.can_view_conditions,
            "schedule_meeting": permissions.can_schedule_meeting,
            "ai_assistant": permissions.ai_assistant_enabled,
        }

        return [action for action, allowed in action_map.items() if allowed]

    def can_view_document(
        self,
        realtor_id: int,
        loan_id: int,
        document_type: str
    ) -> bool:
        """Check if realtor can view a specific document type."""
        permissions = self.get_permissions(realtor_id, loan_id)

        if not permissions.can_view_documents:
            return False

        # If visible_document_types is empty, allow all (no filter)
        if not permissions.visible_document_types:
            return True

        return document_type.lower() in [
            dt.lower() for dt in permissions.visible_document_types
        ]

    def filter_loan_data(
        self,
        realtor_id: int,
        loan_id: int,
        loan_data: Dict
    ) -> Dict:
        """Filter loan data to remove hidden fields."""
        permissions = self.get_permissions(realtor_id, loan_id)

        if not permissions.hidden_fields:
            return loan_data

        hidden = set(f.lower() for f in permissions.hidden_fields)

        return {
            k: v for k, v in loan_data.items()
            if k.lower() not in hidden
        }

    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================

    def _get_loan_info(self, loan_id: int) -> Optional[Dict]:
        """Get basic loan info for permission lookup."""
        result = self.db.execute(text("""
            SELECT stage, loan_officer_id
            FROM loans
            WHERE id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if not result:
            return None

        return {
            "status": result[0],
            "organization_id": result[1]  # Using loan_officer_id as org proxy for SQLite
        }

    def _get_realtor_role(self, realtor_id: int, loan_id: int) -> Optional[str]:
        """Get realtor's role on a loan."""
        result = self.db.execute(text("""
            SELECT role
            FROM realtor_loan_associations
            WHERE realtor_id = :realtor_id
                AND loan_id = :loan_id
                AND access_revoked_at IS NULL
        """), {"realtor_id": realtor_id, "loan_id": loan_id}).fetchone()

        return result[0] if result else None

    def _lookup_permissions(
        self,
        organization_id: int,
        loan_status: str
    ) -> RealtorPermissions:
        """Look up permissions from database."""
        # First try organization-specific, then fall back to defaults
        result = self.db.execute(text("""
            SELECT *
            FROM portal_status_actions
            WHERE loan_status = :status
                AND (organization_id = :org_id OR organization_id IS NULL)
            ORDER BY
                CASE WHEN organization_id IS NOT NULL THEN 0 ELSE 1 END,
                priority DESC
            LIMIT 1
        """), {"org_id": organization_id, "status": loan_status}).fetchone()

        if not result:
            # Return restrictive defaults if no config found
            logger.warning(f"No permission config for status '{loan_status}'")
            return self._get_minimal_permissions()

        # Convert to dict for easier access
        columns = result.keys() if hasattr(result, 'keys') else []
        row_dict = dict(zip(columns, result)) if columns else {}

        return RealtorPermissions.from_db_row(row_dict)

    def _apply_role_modifiers(
        self,
        permissions: RealtorPermissions,
        role: str
    ) -> RealtorPermissions:
        """Apply role-based permission modifiers."""
        # Referring agents have reduced permissions
        if role == "referring_agent":
            permissions.can_view_documents = False
            permissions.can_download_documents = False
            permissions.can_upload_documents = False
            permissions.can_view_conditions = False
            permissions.can_generate_preapproval = False

        # Dual agents get full permissions (they represent both sides)
        elif role == "dual_agent":
            # No changes - they get whatever status allows
            pass

        # Seller's agent has very limited access
        elif role == "seller_agent":
            permissions.can_view_documents = False
            permissions.can_download_documents = False
            permissions.can_upload_documents = False
            permissions.can_view_conditions = False
            permissions.can_generate_prequal = False
            permissions.can_generate_preapproval = False
            permissions.ai_allowed_topics = ["status", "timeline"]

        return permissions

    def _get_minimal_permissions(self) -> RealtorPermissions:
        """Get minimal permissions for access-denied scenarios."""
        return RealtorPermissions(
            can_view_status=False,
            can_view_timeline=False,
            can_view_documents=False,
            can_download_documents=False,
            can_upload_documents=False,
            can_send_messages=False,
            can_request_update=False,
            can_generate_prequal=False,
            can_generate_preapproval=False,
            can_view_conditions=False,
            can_schedule_meeting=False,
            ai_assistant_enabled=False,
        )

    def _get_cached(self, key: str) -> Optional[RealtorPermissions]:
        """Get permissions from cache if not expired."""
        if key in self._permission_cache:
            permissions, cached_at = self._permission_cache[key]
            if datetime.now(timezone.utc) - cached_at < self._cache_ttl:
                return permissions
            else:
                del self._permission_cache[key]
        return None

    def _set_cached(self, key: str, permissions: RealtorPermissions):
        """Cache permissions."""
        self._permission_cache[key] = (permissions, datetime.now(timezone.utc))

    def clear_cache(self, organization_id: Optional[int] = None):
        """Clear permission cache, optionally for specific org."""
        if organization_id:
            keys_to_delete = [
                k for k in self._permission_cache.keys()
                if k.startswith(f"{organization_id}:")
            ]
            for key in keys_to_delete:
                del self._permission_cache[key]
        else:
            self._permission_cache.clear()


class RealtorAccessValidator:
    """
    Validates realtor access to loans.

    Checks:
    - Association exists and is active
    - Access hasn't been revoked
    - Realtor account is active
    """

    def __init__(self, db: Session):
        self.db = db

    def validate_access(self, realtor_id: int, loan_id: int) -> Dict[str, Any]:
        """
        Validate a realtor's access to a loan.

        Returns:
            Dict with 'valid' boolean and 'reason' if invalid
        """
        # Check realtor is active
        realtor = self.db.execute(text("""
            SELECT is_active FROM realtor_portal_users WHERE id = :id
        """), {"id": realtor_id}).fetchone()

        if not realtor:
            return {"valid": False, "reason": "Realtor not found"}

        if not realtor[0]:
            return {"valid": False, "reason": "Realtor account is inactive"}

        # Check loan association
        association = self.db.execute(text("""
            SELECT
                role,
                access_granted_at,
                access_revoked_at
            FROM realtor_loan_associations
            WHERE realtor_id = :realtor_id AND loan_id = :loan_id
        """), {"realtor_id": realtor_id, "loan_id": loan_id}).fetchone()

        if not association:
            return {"valid": False, "reason": "No access to this loan"}

        if association[2]:  # access_revoked_at
            return {"valid": False, "reason": "Access has been revoked"}

        def format_date(val):
            if val is None:
                return None
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        return {
            "valid": True,
            "role": association[0],
            "granted_at": format_date(association[1])
        }

    def get_accessible_loans(self, realtor_id: int) -> List[Dict]:
        """Get all loans a realtor has access to."""
        results = self.db.execute(text("""
            SELECT
                rla.loan_id,
                rla.role,
                rla.access_granted_at,
                l.stage,
                l.amount as loan_amount,
                l.borrower_name
            FROM realtor_loan_associations rla
            JOIN loans l ON l.id = rla.loan_id
            WHERE rla.realtor_id = :realtor_id
                AND rla.access_revoked_at IS NULL
            ORDER BY rla.access_granted_at DESC
        """), {"realtor_id": realtor_id}).fetchall()

        def format_date(val):
            if val is None:
                return None
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        return [
            {
                "loan_id": row[0],
                "role": row[1],
                "granted_at": format_date(row[2]),
                "status": row[3],
                "loan_amount": float(row[4]) if row[4] else None,
                "borrower_name": row[5],
            }
            for row in results
        ]

    def grant_access(
        self,
        realtor_id: int,
        loan_id: int,
        role: str,
        granted_by: int
    ) -> Dict[str, Any]:
        """Grant a realtor access to a loan."""
        try:
            self.db.execute(text("""
                INSERT INTO realtor_loan_associations (
                    realtor_id, loan_id, role, access_granted_by
                ) VALUES (
                    :realtor_id, :loan_id, :role, :granted_by
                )
                ON CONFLICT (realtor_id, loan_id) DO UPDATE SET
                    role = :role,
                    access_revoked_at = NULL,
                    access_granted_by = :granted_by,
                    access_granted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "realtor_id": realtor_id,
                "loan_id": loan_id,
                "role": role,
                "granted_by": granted_by
            })
            self.db.commit()

            return {"success": True, "loan_id": loan_id, "role": role}
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error granting access: {e}")
            return {"success": False, "error": "Internal server error"}

    def revoke_access(
        self,
        realtor_id: int,
        loan_id: int,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Revoke a realtor's access to a loan."""
        try:
            self.db.execute(text("""
                UPDATE realtor_loan_associations
                SET access_revoked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE realtor_id = :realtor_id AND loan_id = :loan_id
            """), {"realtor_id": realtor_id, "loan_id": loan_id})
            self.db.commit()

            return {"success": True, "loan_id": loan_id, "revoked": True}
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error revoking access: {e}")
            return {"success": False, "error": "Internal server error"}

    def record_view(self, realtor_id: int, loan_id: int):
        """Record that a realtor viewed a loan."""
        try:
            self.db.execute(text("""
                UPDATE realtor_loan_associations
                SET last_viewed_at = CURRENT_TIMESTAMP,
                    view_count = view_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE realtor_id = :realtor_id AND loan_id = :loan_id
            """), {"realtor_id": realtor_id, "loan_id": loan_id})
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error recording view: {e}")
            self.db.rollback()
