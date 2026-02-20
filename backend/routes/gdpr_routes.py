"""
GDPR/CCPA Data Routes
Enterprise Readiness Check 8.11 + CMP-004/CMP-005

Admin-only endpoints for:
- GDPR data export (right to portability) — CMP-004
- GDPR data deletion (right to erasure) — CMP-005
- Viewing deletion history

Endpoints:
    POST /api/v1/admin/gdpr/export           - Export all org data as JSON
    POST /api/v1/admin/gdpr/deletion-request  - Submit a new deletion request
    GET  /api/v1/admin/gdpr/deletion-requests  - List past deletion requests

Registration pattern: function-based (same as scorecard_routes, admin_ops_routes)
"""
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
import json
import io
import zipfile
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

    # ==================================================================
    # CMP-004: GDPR Data Export (Right to Portability)
    # ==================================================================

    @app.post("/api/v1/admin/gdpr/export", tags=["GDPR"])
    async def export_org_data(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export ALL data for the current organization as a ZIP of JSON files.

        GDPR Article 20 — Right to data portability. Returns a structured,
        machine-readable ZIP archive containing all tenant-scoped data.

        Requires admin privileges. The export is scoped to the authenticated
        user's organization via RLS (Row-Level Security).
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with current user",
            )

        try:
            # Tables to export — all tenant-scoped tables with organization_id
            EXPORT_TABLES = [
                ("users", "SELECT id, email, first_name, last_name, phone, role, permission_role, is_active, created_at FROM users WHERE organization_id = :org_id"),
                ("leads", "SELECT id, name, first_name, last_name, email, phone, stage, source, assigned_to, created_at, updated_at FROM leads WHERE organization_id = :org_id"),
                ("loans", "SELECT id, loan_number, loan_amount, loan_type, status, borrower_name, property_address, created_at, updated_at FROM loans WHERE organization_id = :org_id"),
                ("clients", "SELECT id, first_name, last_name, email, phone, status, created_at FROM clients WHERE organization_id = :org_id"),
                ("contacts", "SELECT id, first_name, last_name, email, phone, contact_type, created_at FROM contacts WHERE organization_id = :org_id"),
                ("tasks", "SELECT id, title, description, status, priority, assigned_to, due_date, created_at FROM tasks WHERE organization_id = :org_id"),
                ("notes", "SELECT id, content, entity_type, entity_id, created_by, created_at FROM notes WHERE organization_id = :org_id"),
                ("documents", "SELECT id, filename, document_type, entity_type, entity_id, uploaded_by, created_at FROM documents WHERE organization_id = :org_id"),
                ("email_messages", "SELECT id, from_email, to_email, subject, body, direction, status, sent_at FROM email_messages WHERE organization_id = :org_id"),
                ("sms_messages", "SELECT id, from_number, to_number, message, direction, status, sent_at FROM sms_messages WHERE organization_id = :org_id"),
                ("audit_logs", "SELECT id, user_id, change_type, entity_type, reason, timestamp FROM audit_logs WHERE organization_id = :org_id ORDER BY timestamp DESC LIMIT 10000"),
            ]

            # Build ZIP in memory
            zip_buffer = io.BytesIO()
            export_manifest = {
                "organization_id": org_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "exported_by": current_user.id,
                "format": "GDPR Article 20 portable export",
                "tables": {},
            }

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for table_name, query in EXPORT_TABLES:
                    try:
                        rows = db.execute(text(query), {"org_id": org_id}).fetchall()
                        if rows:
                            columns = rows[0]._fields if hasattr(rows[0], '_fields') else rows[0].keys()
                            data = [dict(zip(columns, row)) for row in rows]

                            # Serialize with date handling
                            json_str = json.dumps(data, default=str, indent=2)
                            zf.writestr(f"{table_name}.json", json_str)
                            export_manifest["tables"][table_name] = len(data)
                        else:
                            zf.writestr(f"{table_name}.json", "[]")
                            export_manifest["tables"][table_name] = 0
                    except Exception as table_err:
                        # Table may not exist — skip gracefully
                        logger.warning(f"GDPR export skipped table {table_name}: {table_err}")
                        export_manifest["tables"][table_name] = f"skipped: {str(table_err)[:100]}"

                # Add manifest
                zf.writestr("_manifest.json", json.dumps(export_manifest, indent=2))

            # Log the export in audit trail
            try:
                db.execute(text("""
                    INSERT INTO audit_logs
                        (user_id, changed_by_id, change_type, entity_type, reason, after_state, timestamp, organization_id)
                    VALUES
                        (:user_id, :user_id, 'gdpr_export', 'data_export', 'gdpr_right_to_portability',
                         :details, :ts, :org_id)
                """), {
                    "user_id": current_user.id,
                    "org_id": org_id,
                    "details": json.dumps({"tables": list(export_manifest["tables"].keys())}),
                    "ts": datetime.now(timezone.utc),
                })
                db.commit()
            except Exception as audit_err:
                logger.warning(f"Failed to log GDPR export audit: {audit_err}")

            zip_buffer.seek(0)
            filename = f"perennia_gdpr_export_org{org_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"

            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"GDPR data export failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Data export failed",
            )

    # ==================================================================
    # CMP-005: GDPR Data Deletion (Right to Erasure)
    # ==================================================================

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
