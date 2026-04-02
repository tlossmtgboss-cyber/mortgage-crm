"""
GDPR/CCPA Data Routes
Enterprise Readiness Check 8.11 + CMP-004/CMP-005

Endpoints:
    POST /api/v1/admin/gdpr/export              - Export all org data as JSON
    POST /api/v1/admin/gdpr/deletion-request     - Submit a new deletion request
    GET  /api/v1/admin/gdpr/deletion-requests    - List past deletion requests
    POST /api/v1/gdpr/data-subject-request       - Public: submit a DSAR (no auth)
    GET  /api/v1/gdpr/data-subject-request/{id}  - Public: check DSAR status by email
    GET  /api/v1/admin/gdpr/data-subject-requests - Admin: list/manage DSARs for org

Registration pattern: function-based (same as scorecard_routes, admin_ops_routes)
"""
from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
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


class DSARSubmitBody(BaseModel):
    """Public DSAR submission body."""
    request_type: str = Field("access", description="Type: access, rectification, erasure, restriction")
    requestor_email: str = Field(..., description="Email of the data subject")
    requestor_name: Optional[str] = Field(None, description="Name of the data subject")
    notes: Optional[str] = Field(None, max_length=2000, description="Additional details")


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
            # Includes all PII-bearing tables for GDPR Article 20 compliance.
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
                ("sms_messages", "SELECT id, from_number, to_number, message, direction, status, created_at FROM sms_messages WHERE organization_id = :org_id"),
                ("borrower_profiles", "SELECT id, email, first_name, last_name, provider, communication_consent, marketing_consent, consent_captured_at, created_at FROM borrower_profiles WHERE organization_id = :org_id"),
                ("borrower_applications", "SELECT id, borrower_first_name, borrower_last_name, borrower_email, borrower_phone, status, current_step, progress_percentage, submitted_at, created_at FROM borrower_applications WHERE organization_id = :org_id"),
                ("application_documents", "SELECT ad.id, ad.application_id, ad.filename, ad.original_filename, ad.category, ad.is_verified, ad.created_at FROM application_documents ad JOIN borrower_applications ba ON ba.id = ad.application_id WHERE ba.organization_id = :org_id"),
                ("call_logs", "SELECT id, contact_phone, contact_name, call_sid, start_time, end_time, duration_seconds, outcome, disposition, created_at FROM call_logs WHERE organization_id = :org_id"),
                ("activities", "SELECT id, type, content, lead_id, loan_id, user_id, duration, sentiment, created_at FROM activities WHERE organization_id = :org_id"),
                ("conversations", "SELECT id, user_id, lead_id, loan_id, message, response, role, created_at FROM conversations WHERE organization_id = :org_id"),
                ("voicemail_drops", "SELECT id, contact_name, phone_number, contact_email, message_text, delivery_method, status, delivered_at, created_at FROM voicemail_drops WHERE organization_id = :org_id"),
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

    # ==================================================================
    # CMP-004: GDPR Data Subject Request — Public Submission
    # ==================================================================

    @app.post("/api/v1/gdpr/data-subject-request", tags=["GDPR"])
    async def submit_data_subject_request(
        body: DSARSubmitBody,
        db: Session = Depends(get_db),
    ):
        """
        Submit a GDPR Data Subject Access Request (public, no auth required).

        GDPR Articles 15-18: Data subjects can request access, rectification,
        erasure, or restriction of their personal data. The organization has
        30 days to respond.
        """
        valid_types = ("access", "rectification", "erasure", "restriction")
        if body.request_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request_type. Must be one of: {', '.join(valid_types)}",
            )

        try:
            now = datetime.now(timezone.utc)
            due = now + timedelta(days=30)

            # Try to determine org from email domain (best-effort)
            org_id = None
            try:
                email_domain = body.requestor_email.split("@")[1] if "@" in body.requestor_email else None
                if email_domain:
                    org_row = db.execute(text("""
                        SELECT DISTINCT o.id FROM organizations o
                        JOIN users u ON u.organization_id = o.id
                        WHERE u.email LIKE :domain_pattern
                        LIMIT 1
                    """), {"domain_pattern": f"%@{email_domain}"}).fetchone()
                    if org_row:
                        org_id = org_row[0]
            except Exception as e:
                logger.error(f"Error determining org_id from email domain: {e}")
                pass  # Best effort — org_id can be NULL

            result = db.execute(text("""
                INSERT INTO data_subject_requests
                    (organization_id, request_type, requestor_email, requestor_name,
                     status, submitted_at, due_date, notes)
                VALUES
                    (:org_id, :req_type, :email, :name, 'pending', :now, :due, :notes)
                RETURNING id
            """), {
                "org_id": org_id,
                "req_type": body.request_type,
                "email": body.requestor_email,
                "name": body.requestor_name,
                "now": now,
                "due": due,
                "notes": body.notes,
            })
            db.commit()
            dsr_id = result.fetchone()[0]

            logger.info(f"DSAR submitted: id={dsr_id}, type={body.request_type}, email={body.requestor_email}")

            return {
                "success": True,
                "request_id": dsr_id,
                "status": "pending",
                "due_date": due.isoformat(),
                "message": f"Your {body.request_type} request has been received. We will respond within 30 days.",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DSAR submission failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit data subject request",
            )

    # ==================================================================
    # CMP-004: GDPR Data Subject Request — Public Status Check
    # ==================================================================

    @app.get("/api/v1/gdpr/data-subject-request/{request_id}", tags=["GDPR"])
    async def check_dsar_status(
        request_id: int,
        email: str = Query(..., description="Requestor email for verification"),
        db: Session = Depends(get_db),
    ):
        """
        Check the status of a GDPR Data Subject Access Request (public).

        The requestor must provide their email to verify identity.
        """
        try:
            row = db.execute(text("""
                SELECT id, request_type, requestor_email, requestor_name,
                       status, submitted_at, due_date, result_summary,
                       identity_verified
                FROM data_subject_requests
                WHERE id = :id AND requestor_email = :email
            """), {"id": request_id, "email": email}).fetchone()

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Request not found or email does not match",
                )

            return {
                "request_id": row[0],
                "request_type": row[1],
                "requestor_email": row[2],
                "requestor_name": row[3],
                "status": row[4],
                "submitted_at": row[5].isoformat() if row[5] else None,
                "due_date": row[6].isoformat() if row[6] else None,
                "result_summary": row[7],
                "identity_verified": row[8],
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DSAR status check failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to check request status",
            )

    # ==================================================================
    # CMP-004: Admin DSAR Management
    # ==================================================================

    @app.get("/api/v1/admin/gdpr/data-subject-requests", tags=["GDPR"])
    async def list_data_subject_requests(
        status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        List and manage GDPR Data Subject Requests for the organization (admin only).
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)

        try:
            params = {"limit": limit}
            where_clauses = []

            if org_id:
                where_clauses.append("(organization_id = :org_id OR organization_id IS NULL)")
                params["org_id"] = org_id

            if status_filter:
                where_clauses.append("status = :status")
                params["status"] = status_filter

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            sql = (
                "SELECT id, organization_id, request_type, requestor_email,"
                " requestor_name, status, submitted_at, due_date,"
                " handled_by_id, handled_at, notes, result_summary,"
                " identity_verified"
                " FROM data_subject_requests"
                " " + where_sql +
                " ORDER BY submitted_at DESC"
                " LIMIT :limit"
            )
            rows = db.execute(text(sql), params).fetchall()

            requests = []
            for row in rows:
                requests.append({
                    "id": row[0],
                    "organization_id": row[1],
                    "request_type": row[2],
                    "requestor_email": row[3],
                    "requestor_name": row[4],
                    "status": row[5],
                    "submitted_at": row[6].isoformat() if row[6] else None,
                    "due_date": row[7].isoformat() if row[7] else None,
                    "handled_by_id": row[8],
                    "handled_at": row[9].isoformat() if row[9] else None,
                    "notes": row[10],
                    "result_summary": row[11],
                    "identity_verified": row[12],
                    "is_overdue": row[7] < datetime.now(timezone.utc) if row[7] and row[5] in ("pending", "in_progress") else False,
                })

            overdue_count = sum(1 for r in requests if r.get("is_overdue"))

            return {
                "total": len(requests),
                "overdue_count": overdue_count,
                "requests": requests,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DSAR list failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to list data subject requests",
            )

    logger.info("GDPR/CCPA data deletion routes loaded")
