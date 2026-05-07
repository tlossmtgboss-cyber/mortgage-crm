"""
Report Export Routes
====================

Enterprise Readiness Domain 9: Analytics & Reporting

General-Purpose Report Exports (CSV/XLSX):
- GET  /api/v1/reports/pipeline/export?format=csv|xlsx   — Pipeline data (leads + loans)
- GET  /api/v1/reports/production/export?format=csv|xlsx — LO production scorecard
- GET  /api/v1/reports/compliance/export?format=csv|xlsx — Compliance / SLA / risk report

Legacy / Structured Report Exports:
- GET  /api/v1/reports/sla-compliance         — SLA compliance report (Check 9.3)
- POST /api/v1/reports/export/pdf              — Export any report as PDF (Check 9.8)
- POST /api/v1/reports/export/excel            — Export any report as Excel (Check 9.9)
- POST /api/v1/reports/export/csv              — Export any report as CSV (Check 9.10)
- POST /api/v1/reports/schedule                — Schedule recurring report delivery (Check 9.11)
- GET  /api/v1/reports/schedules               — List scheduled reports
- DELETE /api/v1/reports/schedules/{schedule_id} — Cancel scheduled report

Performance Monitoring:
- GET  /api/v1/monitoring/performance          — Performance baseline report (Check 6.1-6.4)
- GET  /api/v1/monitoring/token-usage          — AI token budget stats (Check 6.13)
- GET  /api/v1/monitoring/ai-capacity          — AI concurrent capacity (Check 6.14)
- GET  /api/v1/monitoring/deadlocks            — Database deadlock check (Check 6.8)
- GET  /api/v1/monitoring/webhook-throughput    — Webhook throughput metrics (Check 6.9)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime
import io
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ExportRequest(BaseModel):
    """Request body for report export."""
    report_type: Literal["pipeline", "scorecard", "sla_compliance", "financial"]
    title: Optional[str] = None
    data: Optional[dict] = None
    # Filters for server-side report generation
    period_days: int = 30
    scope_type: str = "organization"
    scope_id: Optional[int] = None


class ScheduleReportRequest(BaseModel):
    """Request body for scheduling a recurring report."""
    report_type: Literal["pipeline", "scorecard", "sla_compliance", "financial"]
    format: Literal["pdf", "excel", "csv"] = "pdf"
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    recipients: List[str]  # Email addresses
    title: Optional[str] = None
    day_of_week: Optional[int] = None  # 0=Monday for weekly
    day_of_month: Optional[int] = None  # For monthly
    hour: int = 8  # Hour to send (UTC)


# =============================================================================
# Report Export Endpoints (Domain 9: Checks 9.3, 9.8, 9.9, 9.10)
# =============================================================================

def register_report_export_routes(app, get_db, get_current_user, **kwargs):
    """Register report export routes."""

    @app.get("/api/v1/reports/sla-compliance")
    async def get_sla_compliance_report(
        request: Request,
        period_days: int = Query(30, ge=1, le=365),
        scope_type: str = Query("organization"),
        scope_id: Optional[int] = Query(None),
        format: Literal["json", "pdf", "excel"] = Query("json"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Generate SLA compliance report.
        Enterprise Readiness Check 9.3: SLA compliance report with all milestones
        tracked and violations flagged.
        """
        from services.report_export_service import report_exporter

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        report_data = report_exporter.generate_sla_compliance_report(
            db=db,
            org_id=org_id,
            period_days=period_days,
            scope_type=scope_type,
            scope_id=scope_id,
        )

        if format == "json":
            return {"success": True, "report": report_data}

        elif format == "pdf":
            pdf_bytes = report_exporter.generate_pdf(report_data, "sla_compliance")
            filename = f"sla_compliance_report_{datetime.now().strftime('%Y%m%d')}.pdf"
            try:
                from utils.export_audit import log_export_event, _get_client_ip
                log_export_event(db=db, user_id=current_user.id, organization_id=org_id, resource_type="sla_compliance_report", export_format="pdf", ip_address=_get_client_ip(request), details={"period_days": period_days})
            except Exception:
                pass
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        elif format == "excel":
            xlsx_bytes = report_exporter.generate_excel(report_data, "sla_compliance")
            filename = f"sla_compliance_report_{datetime.now().strftime('%Y%m%d')}.xlsx"
            try:
                from utils.export_audit import log_export_event, _get_client_ip
                log_export_event(db=db, user_id=current_user.id, organization_id=org_id, resource_type="sla_compliance_report", export_format="xlsx", ip_address=_get_client_ip(request), details={"period_days": period_days})
            except Exception:
                pass
            return StreamingResponse(
                io.BytesIO(xlsx_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    # =========================================================================
    # General-Purpose Pipeline / Production / Compliance Export (GET)
    # =========================================================================

    @app.get("/api/v1/reports/pipeline/export")
    async def export_pipeline_report(
        request: Request,
        format: Literal["csv", "xlsx"] = Query("csv"),
        stage: Optional[str] = Query(None, description="Filter by stage"),
        date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
        date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export pipeline data (leads + loans) as CSV or XLSX.
        Scoped by role via get_report_scope().
        """
        from middleware.report_access import get_report_scope
        from services.report_export_service import (
            format_pipeline_report,
            export_to_csv,
            export_to_excel,
            PIPELINE_COLUMNS,
        )

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        scope = get_report_scope(current_user)

        filters = {}
        if stage:
            filters["stage"] = stage
        if date_from:
            try:
                filters["date_from"] = datetime.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "date_from must be YYYY-MM-DD")
        if date_to:
            try:
                filters["date_to"] = datetime.strptime(date_to, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "date_to must be YYYY-MM-DD")

        data = format_pipeline_report(db=db, org_id=org_id, scope=scope, filters=filters)

        # Audit trail
        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id, organization_id=org_id,
                resource_type="pipeline_report", export_format=format,
                ip_address=_get_client_ip(request),
                details={"record_count": len(data), "filters": filters},
            )
        except Exception:
            pass

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if format == "xlsx":
            return export_to_excel(data, PIPELINE_COLUMNS, sheet_name="Pipeline", filename=f"pipeline_report_{ts}.xlsx")
        return export_to_csv(data, PIPELINE_COLUMNS, filename=f"pipeline_report_{ts}.csv")

    @app.get("/api/v1/reports/production/export")
    async def export_production_report(
        request: Request,
        format: Literal["csv", "xlsx"] = Query("csv"),
        date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
        date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export LO production scorecard as CSV or XLSX.
        Scoped by role via get_report_scope().
        """
        from middleware.report_access import get_report_scope
        from services.report_export_service import (
            format_production_report,
            export_to_csv,
            export_to_excel,
            PRODUCTION_COLUMNS,
        )

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        scope = get_report_scope(current_user)

        parsed_from = None
        parsed_to = None
        if date_from:
            try:
                parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(400, "date_from must be YYYY-MM-DD")
        if date_to:
            try:
                parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(400, "date_to must be YYYY-MM-DD")

        data = format_production_report(
            db=db, org_id=org_id, scope=scope,
            date_from=parsed_from, date_to=parsed_to,
        )

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id, organization_id=org_id,
                resource_type="production_report", export_format=format,
                ip_address=_get_client_ip(request),
                details={"record_count": len(data), "date_from": date_from, "date_to": date_to},
            )
        except Exception:
            pass

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if format == "xlsx":
            return export_to_excel(data, PRODUCTION_COLUMNS, sheet_name="Production", filename=f"production_report_{ts}.xlsx")
        return export_to_csv(data, PRODUCTION_COLUMNS, filename=f"production_report_{ts}.csv")

    @app.get("/api/v1/reports/compliance/export")
    async def export_compliance_report(
        request: Request,
        format: Literal["csv", "xlsx"] = Query("csv"),
        period_days: int = Query(30, ge=1, le=365),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export compliance report (loan SLA/risk data) as CSV or XLSX.
        Scoped by role via get_report_scope().
        """
        from middleware.report_access import get_report_scope
        from services.report_export_service import (
            format_compliance_report,
            export_to_csv,
            export_to_excel,
            COMPLIANCE_COLUMNS,
        )

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        scope = get_report_scope(current_user)

        data = format_compliance_report(
            db=db, org_id=org_id, scope=scope,
            period_days=period_days,
        )

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id, organization_id=org_id,
                resource_type="compliance_report", export_format=format,
                ip_address=_get_client_ip(request),
                details={"record_count": len(data), "period_days": period_days},
            )
        except Exception:
            pass

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if format == "xlsx":
            return export_to_excel(data, COMPLIANCE_COLUMNS, sheet_name="Compliance", filename=f"compliance_report_{ts}.xlsx")
        return export_to_csv(data, COMPLIANCE_COLUMNS, filename=f"compliance_report_{ts}.csv")

    # =========================================================================
    # Legacy POST-based Exports (Enterprise Readiness Domain 9)
    # =========================================================================

    @app.post("/api/v1/reports/export/pdf")
    async def export_report_pdf(
        body: ExportRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export a report as PDF.
        Enterprise Readiness Check 9.8: PDF export renders correctly with timestamp.
        """
        from services.report_export_service import report_exporter

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        # If data not provided, generate it server-side
        report_data = body.data
        if not report_data and body.report_type == "sla_compliance":
            report_data = report_exporter.generate_sla_compliance_report(
                db=db, org_id=org_id,
                period_days=body.period_days,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
            )
        elif not report_data:
            raise HTTPException(400, "report data required for this report type")

        pdf_bytes = report_exporter.generate_pdf(report_data, body.report_type, body.title)
        filename = f"{body.report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(db=db, user_id=current_user.id, organization_id=org_id, resource_type=body.report_type, export_format="pdf", ip_address=_get_client_ip(request), details={"title": body.title})
        except Exception:
            pass

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/v1/reports/export/excel")
    async def export_report_excel(
        body: ExportRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export a report as Excel/XLSX.
        Enterprise Readiness Check 9.9: Excel export with correct columns and formatting.
        """
        from services.report_export_service import report_exporter

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        report_data = body.data
        if not report_data and body.report_type == "sla_compliance":
            report_data = report_exporter.generate_sla_compliance_report(
                db=db, org_id=org_id,
                period_days=body.period_days,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
            )
        elif not report_data:
            raise HTTPException(400, "report data required for this report type")

        xlsx_bytes = report_exporter.generate_excel(report_data, body.report_type, body.title)
        filename = f"{body.report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(db=db, user_id=current_user.id, organization_id=org_id, resource_type=body.report_type, export_format="xlsx", ip_address=_get_client_ip(request), details={"title": body.title})
        except Exception:
            pass

        return StreamingResponse(
            io.BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/v1/reports/export/csv")
    async def export_report_csv(
        body: ExportRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export a report as CSV.
        Enterprise Readiness Check 9.10: Proper escaping and UTF-8 encoding.
        """
        from services.report_export_service import report_exporter

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        report_data = body.data
        if not report_data and body.report_type == "sla_compliance":
            report_data = report_exporter.generate_sla_compliance_report(
                db=db, org_id=org_id,
                period_days=body.period_days,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
            )
        elif not report_data:
            raise HTTPException(400, "report data required for this report type")

        csv_bytes = report_exporter.generate_csv(report_data, body.report_type)
        filename = f"{body.report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(db=db, user_id=current_user.id, organization_id=org_id, resource_type=body.report_type, export_format="csv", ip_address=_get_client_ip(request), details={"title": body.title})
        except Exception:
            pass

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # =========================================================================
    # Scheduled Report Delivery (Check 9.11)
    # =========================================================================

    @app.post("/api/v1/reports/schedule")
    async def schedule_report(
        body: ScheduleReportRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Schedule a recurring report delivery via email.
        Enterprise Readiness Check 9.11: Delivered on schedule.
        """
        from sqlalchemy import text as sa_text

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")
        user_id = current_user.id

        # Store schedule in database
        schedule_id = db.execute(sa_text("""
            INSERT INTO scheduled_reports
            (organization_id, created_by_id, report_type, export_format, frequency,
             recipients, title, day_of_week, day_of_month, hour_utc, is_active, created_at)
            VALUES
            (:org_id, :user_id, :report_type, :format, :frequency,
             :recipients, :title, :day_of_week, :day_of_month, :hour, true, NOW())
            RETURNING id
        """), {
            "org_id": org_id,
            "user_id": user_id,
            "report_type": body.report_type,
            "format": body.format,
            "frequency": body.frequency,
            "recipients": json.dumps(body.recipients),
            "title": body.title or f"{body.report_type.replace('_', ' ').title()} Report",
            "day_of_week": body.day_of_week,
            "day_of_month": body.day_of_month,
            "hour": body.hour,
        }).scalar()
        db.commit()

        return {
            "success": True,
            "schedule_id": schedule_id,
            "message": f"Report scheduled: {body.frequency} {body.format} to {len(body.recipients)} recipients",
        }

    @app.get("/api/v1/reports/schedules")
    async def list_scheduled_reports(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List all scheduled reports for the organization."""
        from sqlalchemy import text as sa_text

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        schedules = db.execute(sa_text("""
            SELECT id, report_type, export_format, frequency, recipients,
                   title, day_of_week, day_of_month, hour_utc, is_active,
                   last_sent_at, created_at
            FROM scheduled_reports
            WHERE organization_id = :org_id AND is_active = true
            ORDER BY created_at DESC
        """), {"org_id": org_id}).fetchall()

        return {
            "success": True,
            "schedules": [
                {
                    "id": row[0],
                    "report_type": row[1],
                    "format": row[2],
                    "frequency": row[3],
                    "recipients": json.loads(row[4]) if row[4] else [],
                    "title": row[5],
                    "day_of_week": row[6],
                    "day_of_month": row[7],
                    "hour_utc": row[8],
                    "is_active": row[9],
                    "last_sent_at": row[10].isoformat() if row[10] else None,
                    "created_at": row[11].isoformat() if row[11] else None,
                }
                for row in schedules
            ],
        }

    @app.delete("/api/v1/reports/schedules/{schedule_id}")
    async def cancel_scheduled_report(
        schedule_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Cancel a scheduled report."""
        from sqlalchemy import text as sa_text

        org_id = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        result = db.execute(sa_text("""
            UPDATE scheduled_reports SET is_active = false
            WHERE id = :id AND organization_id = :org_id
        """), {"id": schedule_id, "org_id": org_id})
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(404, "Schedule not found")

        return {"success": True, "message": "Schedule cancelled"}

    # =========================================================================
    # Performance Monitoring Endpoints (Domain 6)
    # =========================================================================

    @app.get("/api/v1/monitoring/performance")
    async def get_performance_report(
        current_user=Depends(get_current_user),
    ):
        """
        Get comprehensive performance baseline report.
        Enterprise Readiness Checks 6.1-6.4: API performance with documented thresholds.
        """
        from services.performance_monitoring_service import perf_monitor
        return {"success": True, "report": perf_monitor.get_performance_report()}

    @app.get("/api/v1/monitoring/token-usage")
    async def get_token_usage(
        window_seconds: int = Query(3600, ge=60, le=86400),
        org_id: Optional[int] = Query(None),
        current_user=Depends(get_current_user),
    ):
        """
        Get AI token budget usage statistics.
        Enterprise Readiness Check 6.13: Token consumption within budget (12-18K per query).
        """
        from services.performance_monitoring_service import perf_monitor

        stats = perf_monitor.get_token_usage_stats(window_seconds)
        result = {"success": True, "token_usage": stats}

        if org_id:
            result["org_usage"] = perf_monitor.get_org_hourly_usage(org_id)

        return result

    @app.get("/api/v1/monitoring/ai-capacity")
    async def get_ai_capacity(
        current_user=Depends(get_current_user),
    ):
        """
        Get AI concurrent request capacity.
        Enterprise Readiness Check 6.14: 50 simultaneous requests without timeout.
        """
        from services.performance_monitoring_service import perf_monitor
        return {"success": True, "capacity": perf_monitor.get_ai_capacity()}

    @app.get("/api/v1/monitoring/deadlocks")
    async def check_deadlocks(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Check for database deadlocks.
        Enterprise Readiness Check 6.8: Zero deadlocks under concurrent writes.
        """
        from services.performance_monitoring_service import perf_monitor
        return {"success": True, "deadlock_check": await perf_monitor.check_deadlocks(db)}

    @app.get("/api/v1/monitoring/webhook-throughput")
    async def get_webhook_throughput(
        window_seconds: int = Query(60, ge=10, le=3600),
        current_user=Depends(get_current_user),
    ):
        """
        Get webhook processing throughput metrics.
        Enterprise Readiness Check 6.9: 1000 webhooks in 60s all processed within 5 minutes.
        """
        from services.performance_monitoring_service import perf_monitor
        return {"success": True, "throughput": perf_monitor.get_webhook_throughput(window_seconds)}
