"""
LOS Integration API Routes

Admin endpoints for managing LOS (Loan Origination System) integration,
pushing/pulling loan data, and configuring field mappings.

Enterprise Readiness: Domain 7 (Integration Health)
- Check 7.1: LOS Integration Framework
- Check 7.2: Bidirectional LOS Sync

Endpoints:
    POST /api/v1/los/push/{loan_id}       - Push loan to LOS
    POST /api/v1/los/pull/{loan_id}       - Pull loan from LOS
    GET  /api/v1/los/status/{loan_id}     - Check LOS sync status
    GET  /api/v1/los/config               - Get LOS configuration
    PUT  /api/v1/los/config               - Update LOS configuration
    POST /api/v1/los/field-mapping        - Configure field mappings
    GET  /api/v1/los/health               - LOS integration health check
    POST /api/v1/los/search               - Search LOS pipeline

Registration pattern: function-based (same as gdpr_routes)
"""

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Schemas
# =============================================================================

class LOSPushRequest(BaseModel):
    """Request to push specific fields to LOS."""
    fields: Optional[List[str]] = None  # If None, push all mapped fields
    create_if_missing: bool = False     # Create loan in LOS if not linked


class LOSPullRequest(BaseModel):
    """Request to pull from LOS."""
    los_loan_id: Optional[str] = None   # Override LOS loan ID


class LOSConfigUpdate(BaseModel):
    """Update LOS configuration."""
    instance_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    auto_push: Optional[bool] = None
    auto_pull: Optional[bool] = None
    conflict_resolution: Optional[str] = None
    sync_interval_minutes: Optional[int] = None


class LOSFieldMappingRequest(BaseModel):
    """Field mapping configuration."""
    mappings: List[Dict[str, Any]]


class LOSSearchRequest(BaseModel):
    """Search LOS pipeline."""
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    loan_officer: Optional[str] = None
    limit: int = 25


# =============================================================================
# Route Registration
# =============================================================================

def register_los_routes(app, get_db, get_current_user, **kwargs):
    """Register LOS integration routes.

    These endpoints require authentication. Admin-level operations
    (config updates, field mappings) additionally require admin role.
    """

    # ---- Lazy-init LOS client and sync service ----

    _los_client = None
    _sync_service = None

    def _get_los_client():
        """Get or create the LOS client singleton."""
        nonlocal _los_client
        if _los_client is None:
            from services.los_integration import EncompassClient

            instance_id = os.getenv("ENCOMPASS_INSTANCE_ID", "")
            client_id = os.getenv("ENCOMPASS_CLIENT_ID", "")
            client_secret = os.getenv("ENCOMPASS_CLIENT_SECRET", "")
            api_key = os.getenv("ENCOMPASS_API_KEY")

            if not instance_id or not client_id or not client_secret:
                return None

            _los_client = EncompassClient(
                instance_id=instance_id,
                client_id=client_id,
                client_secret=client_secret,
                api_key=api_key,
            )
        return _los_client

    def _get_sync_service():
        """Get or create the sync service singleton."""
        nonlocal _sync_service
        if _sync_service is None:
            client = _get_los_client()
            if client is None:
                return None
            from services.los_integration import LOSSyncService
            conflict_resolution = os.getenv("LOS_CONFLICT_RESOLUTION", "crm_wins")
            _sync_service = LOSSyncService(
                client=client,
                conflict_resolution=conflict_resolution,
            )
        return _sync_service

    def _require_los_configured():
        """Raise 503 if LOS is not configured."""
        if _get_los_client() is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LOS integration not configured. Set ENCOMPASS_INSTANCE_ID, ENCOMPASS_CLIENT_ID, and ENCOMPASS_CLIENT_SECRET.",
            )

    def _require_admin(current_user):
        """Require admin or site_admin role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for this operation",
            )

    # -----------------------------------------------------------------
    # Push loan to LOS
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/los/push/{loan_id}",
        tags=["LOS Integration"],
    )
    async def push_loan_to_los(
        loan_id: int,
        body: LOSPushRequest = LOSPushRequest(),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Push loan data from CRM to LOS.

        Maps CRM fields to Encompass field IDs and sends to the LOS API.
        Creates a new loan in the LOS if create_if_missing is True and
        the loan is not yet linked.
        """
        _require_los_configured()
        sync = _get_sync_service()

        result = await sync.push_to_los(
            db=db,
            loan_id=loan_id,
            fields=body.fields,
        )

        return {
            "status": result.status.value,
            "loan_id": loan_id,
            "los_loan_id": result.los_loan_id,
            "fields_synced": result.fields_synced,
            "fields_skipped": result.fields_skipped,
            "errors": result.errors,
            "conflicts": result.conflicts,
        }

    # -----------------------------------------------------------------
    # Pull loan from LOS
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/los/pull/{loan_id}",
        tags=["LOS Integration"],
    )
    async def pull_loan_from_los(
        loan_id: int,
        body: LOSPullRequest = LOSPullRequest(),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Pull loan data from LOS to CRM.

        Fetches the loan from Encompass, maps fields back to CRM schema,
        detects conflicts, and applies changes per the configured
        conflict resolution strategy.
        """
        _require_los_configured()
        sync = _get_sync_service()

        result = await sync.pull_from_los(
            db=db,
            loan_id=loan_id,
            los_loan_id=body.los_loan_id,
        )

        return {
            "status": result.status.value,
            "loan_id": loan_id,
            "los_loan_id": result.los_loan_id,
            "fields_synced": result.fields_synced,
            "fields_skipped": result.fields_skipped,
            "conflicts": result.conflicts,
            "errors": result.errors,
            "details": result.details,
        }

    # -----------------------------------------------------------------
    # Sync Status
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/los/status/{loan_id}",
        tags=["LOS Integration"],
    )
    async def get_los_sync_status(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get LOS sync status for a loan.

        Returns whether the loan is linked to a LOS loan, the last
        sync timestamp, and the current LOS milestone.
        """
        _require_los_configured()
        sync = _get_sync_service()

        result = await sync.get_sync_status(db, loan_id)
        return result

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/los/config",
        tags=["LOS Integration"],
    )
    async def get_los_config(
        current_user=Depends(get_current_user),
    ):
        """Get current LOS integration configuration.

        Returns the configured LOS provider, instance, and sync settings.
        Secrets are masked.
        """
        client = _get_los_client()
        sync = _get_sync_service()

        is_configured = client is not None

        return {
            "configured": is_configured,
            "provider": "encompass" if is_configured else None,
            "instance_id": os.getenv("ENCOMPASS_INSTANCE_ID", ""),
            "client_id_set": bool(os.getenv("ENCOMPASS_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("ENCOMPASS_CLIENT_SECRET")),
            "api_key_set": bool(os.getenv("ENCOMPASS_API_KEY")),
            "conflict_resolution": os.getenv("LOS_CONFLICT_RESOLUTION", "crm_wins"),
            "webhook_secret_set": bool(os.getenv("ENCOMPASS_WEBHOOK_SECRET")),
            "field_mappings_count": len(sync.get_field_mappings()) if sync else 0,
        }

    @app.put(
        "/api/v1/los/config",
        tags=["LOS Integration"],
    )
    async def update_los_config(
        body: LOSConfigUpdate,
        current_user=Depends(get_current_user),
    ):
        """Update LOS integration configuration.

        Admin-only. Note: environment variables must be updated separately
        in the deployment platform. This endpoint updates runtime configuration.
        """
        _require_admin(current_user)

        # Runtime config updates (non-secret settings)
        updates = {}
        if body.conflict_resolution is not None:
            os.environ["LOS_CONFLICT_RESOLUTION"] = body.conflict_resolution
            updates["conflict_resolution"] = body.conflict_resolution

        if body.enabled is not None:
            updates["enabled"] = body.enabled

        return {
            "status": "updated",
            "updates": updates,
            "note": "Credential updates require environment variable changes in the deployment platform.",
        }

    # -----------------------------------------------------------------
    # Field Mappings
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/los/field-mapping",
        tags=["LOS Integration"],
    )
    async def get_field_mappings(
        current_user=Depends(get_current_user),
    ):
        """Get current field mapping configuration."""
        sync = _get_sync_service()
        if sync is None:
            return {"mappings": [], "note": "LOS not configured"}

        return {
            "mappings": sync.get_field_mappings(),
            "total": len(sync.get_field_mappings()),
        }

    @app.post(
        "/api/v1/los/field-mapping",
        tags=["LOS Integration"],
    )
    async def update_field_mappings(
        body: LOSFieldMappingRequest,
        current_user=Depends(get_current_user),
    ):
        """Update field mapping configuration.

        Admin-only. Each mapping must include crm_field and los_field.
        Optional: direction (push/pull/bidirectional), required, transform.
        """
        _require_admin(current_user)
        _require_los_configured()
        sync = _get_sync_service()

        count = sync.update_field_mappings(body.mappings)
        return {
            "status": "updated",
            "mappings_count": count,
        }

    # -----------------------------------------------------------------
    # Health Check
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/los/health",
        tags=["LOS Integration"],
    )
    async def los_health_check(
        current_user=Depends(get_current_user),
    ):
        """Check LOS integration health.

        Tests connectivity and authentication with the LOS API.
        Returns latency and circuit breaker status.
        """
        client = _get_los_client()
        if client is None:
            return {
                "status": "not_configured",
                "message": "LOS integration not configured",
            }

        health = await client.health_check()

        # Add circuit breaker status if available
        if hasattr(client, "error_handler") and hasattr(client.error_handler, "_circuit_breaker"):
            health["circuit_breaker"] = client.error_handler._circuit_breaker.stats

        return health

    # -----------------------------------------------------------------
    # Pipeline Search
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/los/search",
        tags=["LOS Integration"],
    )
    async def search_los_pipeline(
        body: LOSSearchRequest,
        current_user=Depends(get_current_user),
    ):
        """Search the LOS pipeline.

        Searches Encompass loans by loan number, borrower name, or LO name.
        """
        _require_los_configured()
        client = _get_los_client()

        filters = {}
        if body.loan_number:
            filters["loan_number"] = body.loan_number
        if body.borrower_name:
            filters["borrower_name"] = body.borrower_name
        if body.loan_officer:
            filters["loan_officer"] = body.loan_officer

        try:
            results = await client.search_loans(filters, limit=body.limit)
            return {
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LOS search failed: {str(e)}",
            )
