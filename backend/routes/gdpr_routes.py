"""
GDPR/CCPA Data Deletion Routes
Enterprise Readiness Check 8.11

Admin-only endpoints for processing GDPR/CCPA right-to-deletion requests
and viewing deletion history.

Endpoints:
    POST /api/v1/admin/gdpr/deletion-request  - Submit a new deletion request
    GET  /api/v1/admin/gdpr/deletion-requests  - List past deletion requests

Registration pattern: function-based (same as scorecard_routes, admin_ops_routes)
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response schemas
# ============================================================================

class DeletionRequestBody(BaseModel):
    """Request body for GDPR deletion request."""
    user_id: Optional[int] = None
    borrower_email: Optional[str] = None
    reason: str = "gdpr_right_to_erasure"


class DeletionRequestResponse(BaseModel):
    """Response for GDPR deletion request."""
    status: str
    request_type: str
    identifier: Optional[str] = None
    reason: str
    tables_affected: list
    records_deleted: int
    records_redacted: int
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Route registration
# ============================================================================

def register_gdpr_routes(app, get_db, get_current_user, **kwargs):
    """Register GDPR/CCPA data deletion routes.

    Endpoints:
        POST /api/v1/admin/gdpr/deletion-request
        GET  /api/v1/admin/gdpr/deletion-requests
    """

    @app.post("/api/v1/admin/gdpr/deletion-request", tags=["GDPR"])
    async def submit_deletion_request(
        body: DeletionRequestBody,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Submit a GDPR/CCPA data deletion request.

        Requires admin privileges. Cascades PII removal across all tables
        while retaining required regulatory/audit records.

        Either user_id or borrower_email must be provided:
        - user_id: Deletes PII for an internal user account
        - borrower_email: Deletes PII for a borrower across all related tables
        """
        # Admin-only access check
        from utils.auth import require_admin
        require_admin(current_user)

        if not body.user_id and not body.borrower_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either user_id or borrower_email must be provided",
            )

        try:
            from services.gdpr_service import DataDeletionService

            service = DataDeletionService(db)
            result = service.process_deletion_request(
                user_id=body.user_id,
                borrower_email=body.borrower_email,
                reason=body.reason,
                requested_by=current_user.id,
            )

            logger.info(
                f"GDPR deletion request processed by user {current_user.id}: "
                f"type={result['request_type']}, "
                f"tables={len(result.get('tables_affected', []))}"
            )

            return result

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            logger.error(f"GDPR deletion request failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Data deletion request failed",
            )

    @app.get("/api/v1/admin/gdpr/deletion-requests", tags=["GDPR"])
    async def list_deletion_requests(
        limit: int = 50,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        List past GDPR/CCPA deletion requests from audit logs.

        Requires admin privileges. Returns deletion events recorded in the
        audit trail, ordered by most recent first.
        """
        # Admin-only access check
        from utils.auth import require_admin
        require_admin(current_user)

        try:
            rows = db.execute(text("""
                SELECT
                    al.id,
                    al.user_id,
                    al.changed_by_id,
                    al.reason,
                    al.after_state,
                    al.timestamp,
                    u.email as requested_by_email,
                    u.first_name as requested_by_name
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.changed_by_id
                WHERE al.change_type = 'gdpr_deletion'
                ORDER BY al.timestamp DESC
                LIMIT :limit
            """), {"limit": limit}).fetchall()

            requests = []
            for row in rows:
                entry = {
                    "id": row.id,
                    "requested_by_user_id": row.changed_by_id,
                    "requested_by_email": row.requested_by_email,
                    "requested_by_name": row.requested_by_name,
                    "reason": row.reason,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                }

                # Parse the after_state JSON for details
                if row.after_state:
                    import json
                    try:
                        details = json.loads(row.after_state) if isinstance(row.after_state, str) else row.after_state
                        entry["request_type"] = details.get("request_type")
                        entry["tables_affected"] = details.get("tables_affected", [])
                        entry["records_deleted"] = details.get("records_deleted", 0)
                        entry["records_redacted"] = details.get("records_redacted", 0)
                    except (json.JSONDecodeError, TypeError):
                        entry["details_raw"] = str(row.after_state)

                requests.append(entry)

            return {
                "total": len(requests),
                "requests": requests,
            }

        except Exception as e:
            logger.error(f"Failed to list GDPR deletion requests: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve deletion history",
            )

    logger.info("GDPR/CCPA data deletion routes loaded")
