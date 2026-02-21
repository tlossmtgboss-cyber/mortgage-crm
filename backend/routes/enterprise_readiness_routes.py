"""
Enterprise Readiness Routes
=============================

Consolidates endpoints for enterprise readiness checks across multiple domains:
- Domain 3: Data Quality & Integrity
- Domain 4: Security (file validation, dependency scan)
- Domain 5: Onboarding & Provisioning
- Domain 7: Integration Health (echo prevention)
- Domain 9: Analytics (dashboard performance)
- Domain 10: Migration (import templates)
- Domain 12: White-Label & Theming
"""

import logging
from fastapi import Depends, Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_enterprise_readiness_routes(app, get_db, get_current_user):
    """Register enterprise readiness routes."""

    # =========================================================================
    # DOMAIN 3: DATA QUALITY
    # =========================================================================
    @app.get("/api/v1/data-quality/completeness", tags=["Data Quality"])
    async def check_completeness(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Check record completeness across all entity types."""
        from services.data_quality_service import check_record_completeness
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return check_record_completeness(db, org_id)

    @app.get("/api/v1/data-quality/integrity", tags=["Data Quality"])
    async def check_integrity(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Check referential integrity across tables."""
        from services.data_quality_service import check_referential_integrity
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return check_referential_integrity(db, org_id)

    @app.get("/api/v1/data-quality/duplicates", tags=["Data Quality"])
    async def check_dupes(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Detect duplicate records."""
        from services.data_quality_service import check_duplicates
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return check_duplicates(db, org_id)

    @app.get("/api/v1/data-quality/freshness", tags=["Data Quality"])
    async def check_freshness(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Monitor data freshness."""
        from services.data_quality_service import check_data_freshness
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return check_data_freshness(db, org_id)

    # =========================================================================
    # DOMAIN 4: SECURITY VALIDATORS
    # =========================================================================
    @app.post("/api/v1/security/validate-upload", tags=["Security"])
    async def validate_upload(request: Request, user=Depends(get_current_user)):
        """Validate a file upload for security (MIME type, magic bytes, extension)."""
        from services.security_validators import validate_file_upload

        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")

        content = await file.read()
        result = validate_file_upload(
            filename=file.filename,
            content=content,
            claimed_mime_type=file.content_type,
        )

        if not result["valid"]:
            raise HTTPException(status_code=400, detail={"errors": result["errors"]})

        return result

    @app.get("/api/v1/security/dependency-scan", tags=["Security"])
    async def dependency_scan(user=Depends(get_current_user)):
        """Run dependency vulnerability scan (pip-audit + npm audit)."""
        from services.security_validators import scan_python_dependencies, scan_node_dependencies
        return {
            "python": scan_python_dependencies(),
            "node": scan_node_dependencies(),
            "scanned_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

    # =========================================================================
    # DOMAIN 5: ONBOARDING
    # =========================================================================
    @app.get("/api/v1/onboarding/checklist", tags=["Onboarding"])
    async def get_onboarding_checklist(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Get onboarding completion checklist for the organization."""
        from services.onboarding_checklist_service import compute_onboarding_checklist
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return compute_onboarding_checklist(db, org_id)

    @app.get("/api/v1/onboarding/training-materials", tags=["Onboarding"])
    async def get_training(user=Depends(get_current_user)):
        """Get role-specific training materials."""
        from services.onboarding_checklist_service import get_training_materials
        return get_training_materials()

    # =========================================================================
    # DOMAIN 7: ECHO PREVENTION
    # =========================================================================
    @app.get("/api/v1/integrations/echo-prevention/status", tags=["Integrations"])
    async def echo_prevention_status(user=Depends(get_current_user)):
        """Get echo prevention service status."""
        from services.data_quality_service import EchoPreventionService
        return {
            "active_watermarks": EchoPreventionService.get_active_watermarks(),
            "ttl_seconds": EchoPreventionService._WATERMARK_TTL_SECONDS,
            "description": "Prevents sync loops between CRM and Salesforce by tracking recent outbound pushes",
        }

    # =========================================================================
    # DOMAIN 9: DASHBOARD PERFORMANCE
    # =========================================================================
    @app.get("/api/v1/monitoring/dashboard-performance", tags=["Monitoring"])
    async def dashboard_performance(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Get dashboard performance SLA metrics."""
        from services.data_quality_service import DashboardPerformanceMonitor
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        return {
            "load_times": DashboardPerformanceMonitor.get_load_time_stats(),
            "data_freshness": DashboardPerformanceMonitor.check_data_freshness(db, org_id) if org_id else None,
        }

    # =========================================================================
    # DOMAIN 10: IMPORT TEMPLATES
    # =========================================================================
    @app.get("/api/v1/imports/templates", tags=["Data Import"])
    async def list_templates(user=Depends(get_current_user)):
        """List available import templates for common source systems."""
        from services.data_quality_service import list_import_templates
        return {"templates": list_import_templates()}

    @app.get("/api/v1/imports/templates/{template_id}", tags=["Data Import"])
    async def get_template(template_id: str, user=Depends(get_current_user)):
        """Get a specific import template with field mappings."""
        from services.data_quality_service import get_import_template
        template = get_import_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found. Available: encompass, velocify, generic_crm")
        return template

    @app.post("/api/v1/imports/auto-map", tags=["Data Import"])
    async def auto_map(request: Request, user=Depends(get_current_user)):
        """Auto-map CSV headers to Perennia fields using a template."""
        from services.data_quality_service import auto_map_fields
        body = await request.json()
        headers = body.get("headers", [])
        template_id = body.get("template", "generic_crm")
        if not headers:
            raise HTTPException(status_code=400, detail="'headers' list is required")
        return auto_map_fields(headers, template_id)

    # =========================================================================
    # DOMAIN 12: WHITE-LABEL & BRANDING
    # =========================================================================
    @app.get("/api/v1/branding/config", tags=["White-Label"])
    async def get_branding(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Get full tenant branding configuration."""
        from services.white_label_service import get_tenant_branding
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return get_tenant_branding(db, org_id)

    @app.put("/api/v1/branding/config", tags=["White-Label"])
    async def update_branding(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Update tenant branding configuration."""
        from services.white_label_service import update_tenant_branding
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        body = await request.json()
        return update_tenant_branding(db, org_id, body)

    @app.get("/api/v1/branding/sms-sender", tags=["White-Label"])
    async def sms_sender(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Get SMS sender configuration for tenant."""
        from services.white_label_service import get_sms_sender_config
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return get_sms_sender_config(db, org_id)

    @app.get("/api/v1/branding/leak-scan", tags=["White-Label"])
    async def branding_leak_scan(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Scan for platform branding leaking into white-labeled output."""
        from services.white_label_service import scan_for_branding_leaks
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return scan_for_branding_leaks(db, org_id)

    @app.get("/api/v1/branding/portal-check", tags=["White-Label"])
    async def portal_branding_check(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
        """Check portal branding completeness."""
        from services.white_label_service import check_portal_branding
        org_id = getattr(request.state, "organization_id", None) or getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        return check_portal_branding(db, org_id)

    logger.info(
        "Registered enterprise readiness routes: data quality (4), security (2), "
        "onboarding (2), echo prevention (1), dashboard perf (1), "
        "import templates (3), white-label (5)"
    )
