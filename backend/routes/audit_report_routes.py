"""
Audit Report Share Routes
=========================

Public HTML report pages for CRM workflow audit results.

Endpoints:
- POST   /api/v1/audit-reports                          — Create share link (auth required)
- GET    /api/v1/audit-reports/shared/{token}            — View HTML report (public)
- GET    /api/v1/audit-reports/shared/{token}/json       — Raw JSON data (public)
- DELETE /api/v1/audit-reports/shared/{token}            — Deactivate link (auth required)
- GET    /api/v1/audit-reports/my-shares                 — List user's shares (auth required)
"""

import json
import logging
import os

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

logger = logging.getLogger(__name__)


class CreateAuditReportRequest(BaseModel):
    """Request body for creating a shared audit report."""
    report_data: dict
    title: Optional[str] = None
    expires_in_days: int = 30


def register_audit_report_routes(app, get_db, get_current_user, **kwargs):
    """Register audit report share routes."""

    # -------------------------------------------------------------------------
    # Table creation (production pattern — checkfirst doesn't add missing cols)
    # -------------------------------------------------------------------------
    try:
        from db import engine as _engine
        from sqlalchemy import inspect

        inspector = inspect(_engine)
        if not inspector.has_table("audit_report_shares"):
            from migrations.add_audit_report_shares_table import run_migration
            run_migration()
            logger.info("Created audit_report_shares table via migration")
    except Exception as e:
        logger.warning(f"audit_report_shares table check/create skipped: {e}")

    # -------------------------------------------------------------------------
    # POST /api/v1/audit-reports — Create share link
    # Accepts JWT auth OR X-Audit-Publish-Key header for CLI publishing
    # -------------------------------------------------------------------------
    @app.post("/api/v1/audit-reports")
    async def create_audit_report_share(
        body: CreateAuditReportRequest,
        request: Request,
        db: Session = Depends(get_db),
    ):
        from services.audit_report_share_service import AuditReportShareService

        # Auth: try JWT first, fall back to publish key
        user_id = None
        try:
            current_user = await get_current_user(request=request, db=db)
            user_id = current_user.id
        except Exception as e:
            logger.warning(f"Error during JWT auth, falling back to publish key: {e}")
            # Check for publish key header
            publish_key = request.headers.get("X-Audit-Publish-Key", "")
            expected_key = os.getenv("AUDIT_PUBLISH_KEY", "")
            if not expected_key or not publish_key or publish_key != expected_key:
                raise HTTPException(status_code=401, detail="Authentication required. Use JWT or X-Audit-Publish-Key header.")

        service = AuditReportShareService(db)

        result = service.create_share_link(
            report_data=body.report_data,
            user_id=user_id,
            expires_in_days=body.expires_in_days,
            title=body.title,
        )

        # Build full URL
        api_base = os.getenv("API_BASE_URL", "").rstrip("/")
        if not api_base:
            api_base = str(request.base_url).rstrip("/")
        full_url = f"{api_base}{result['share_url']}"

        return {
            "status": "success",
            "share_token": result["share_token"],
            "share_url": result["share_url"],
            "full_url": full_url,
            "expires_at": result["expires_at"],
        }

    # -------------------------------------------------------------------------
    # GET /api/v1/audit-reports/shared/{token} — Public HTML page
    # -------------------------------------------------------------------------
    @app.get("/api/v1/audit-reports/shared/{share_token}", response_class=HTMLResponse)
    async def view_shared_audit_report(
        share_token: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        from services.audit_report_share_service import (
            AuditReportShareService,
            generate_audit_html,
            generate_not_found_html,
        )

        viewer_ip = request.client.host if request.client else None
        viewer_ua = request.headers.get("user-agent")

        service = AuditReportShareService(db)
        result = service.get_shared_report(
            share_token=share_token,
            viewer_ip=viewer_ip,
            viewer_ua=viewer_ua,
        )

        if not result:
            # Check whether it exists but is expired/deactivated
            row = db.execute(
                text("SELECT is_active, expires_at FROM audit_report_shares WHERE share_token = :t"),
                {"t": share_token},
            ).fetchone()

            if row and not row.is_active:
                return HTMLResponse(generate_not_found_html("been deactivated"), status_code=410)
            elif row:
                return HTMLResponse(generate_not_found_html("expired"), status_code=410)
            return HTMLResponse(generate_not_found_html("not been found"), status_code=404)

        html = generate_audit_html(
            report_data=result["report_data"],
            expires_at=result.get("expires_at"),
        )
        return HTMLResponse(html)

    # -------------------------------------------------------------------------
    # GET /api/v1/audit-reports/shared/{token}/json — Public JSON
    # -------------------------------------------------------------------------
    @app.get("/api/v1/audit-reports/shared/{share_token}/json")
    async def view_shared_audit_report_json(
        share_token: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        from services.audit_report_share_service import AuditReportShareService

        viewer_ip = request.client.host if request.client else None
        viewer_ua = request.headers.get("user-agent")

        service = AuditReportShareService(db)
        result = service.get_shared_report(
            share_token=share_token,
            viewer_ip=viewer_ip,
            viewer_ua=viewer_ua,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Report not found or expired")

        return JSONResponse({
            "status": "success",
            "report_title": result["report_title"],
            "environment": result["environment"],
            "view_count": result["view_count"],
            "report_data": result["report_data"],
        })

    # -------------------------------------------------------------------------
    # DELETE /api/v1/audit-reports/shared/{token} — Deactivate (auth required)
    # -------------------------------------------------------------------------
    @app.delete("/api/v1/audit-reports/shared/{share_token}")
    async def deactivate_audit_report_share(
        share_token: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        from services.audit_report_share_service import AuditReportShareService

        service = AuditReportShareService(db)
        success = service.deactivate_share(share_token, current_user.id)

        if not success:
            raise HTTPException(status_code=404, detail="Share not found or unauthorized")

        return {"status": "success", "message": "Share link deactivated"}

    # -------------------------------------------------------------------------
    # GET /api/v1/audit-reports/my-shares — List user's shares (auth required)
    # -------------------------------------------------------------------------
    @app.get("/api/v1/audit-reports/my-shares")
    async def list_my_audit_report_shares(
        include_expired: bool = False,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        from services.audit_report_share_service import AuditReportShareService

        service = AuditReportShareService(db)
        shares = service.get_user_shares(current_user.id, include_expired=include_expired)

        return {
            "status": "success",
            "shares": shares,
            "count": len(shares),
        }
