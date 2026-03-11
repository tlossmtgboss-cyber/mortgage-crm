"""
Encompass LOS Integration Routes

Provides API endpoints for connecting to, managing, and syncing data with
the Encompass (ICE Mortgage Technology) Loan Origination System.

Endpoints (all under /api/v1/encompass):
    POST /connect            - Connect org to Encompass
    POST /disconnect         - Disconnect org from Encompass
    GET  /status             - Get connection status
    POST /test-connection    - Test credentials
    POST /sync/pull          - Pull loans from Encompass
    POST /sync/push/{loan_id} - Push loan to Encompass
    GET  /search             - Search Encompass pipeline
    POST /import             - Import loans from Encompass
    GET  /field-mappings     - Get field mappings
    PUT  /field-mappings     - Update field mappings

Registration pattern: function-based (same as other route modules in this codebase)
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class EncompassConnectRequest(BaseModel):
    """Request to connect an organization to Encompass."""
    instance_id: str = Field(..., description="Encompass instance ID (e.g., BE11200822)")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    api_user: Optional[str] = Field(None, description="Service account username")
    webhook_secret: Optional[str] = Field(None, description="HMAC secret for webhook verification")


class EncompassSyncPullRequest(BaseModel):
    """Request to pull specific loans from Encompass."""
    loan_ids: Optional[List[int]] = Field(None, description="CRM loan IDs to pull (None = all linked)")
    los_loan_ids: Optional[List[str]] = Field(None, description="Encompass GUIDs to pull")


class EncompassSyncPushRequest(BaseModel):
    """Request to push a loan to Encompass."""
    fields: Optional[List[str]] = Field(
        default=None,
        description="Specific CRM fields to push (None = all mapped push/bidirectional fields)",
    )


class EncompassSearchRequest(BaseModel):
    """Search filters for Encompass pipeline."""
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    loan_officer: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(25, ge=1, le=200)


class EncompassImportRequest(BaseModel):
    """Request to import loans from Encompass into CRM."""
    los_loan_ids: List[str] = Field(..., description="Encompass GUIDs to import")
    assign_to_lo_id: Optional[int] = Field(None, description="Loan officer to assign imported loans to")


_VALID_DIRECTIONS = frozenset({"push", "pull", "bidirectional"})


class FieldMappingItem(BaseModel):
    """A single field mapping entry."""
    crm_field: str = Field(..., min_length=1)
    los_field: str = Field(..., min_length=1)
    direction: str = Field("bidirectional", description="push | pull | bidirectional")
    required: bool = False
    transform: Optional[str] = None

    class Config:
        # Enforce direction is one of the allowed values at validation time
        pass

    def __init__(self, **data):
        super().__init__(**data)
        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {sorted(_VALID_DIRECTIONS)}, got '{self.direction}'"
            )


class FieldMappingUpdateRequest(BaseModel):
    """Request to update field mappings."""
    mappings: List[FieldMappingItem]


# =============================================================================
# Route Registration
# =============================================================================

def register_encompass_integration_routes(app, get_db, get_current_user, **kwargs):
    """Register Encompass LOS integration routes.

    Args:
        app: FastAPI application instance
        get_db: Database session dependency
        get_current_user: Authentication dependency
        **kwargs: Additional config (ENVIRONMENT, etc.)
    """

    from services.los_integration.encompass_oauth_service import EncompassOAuthService
    from services.los_integration.sync_service import LOSSyncService

    oauth_service = EncompassOAuthService()

    # -----------------------------------------------------------------
    # Helper: Get org_id from current user
    # -----------------------------------------------------------------

    def _get_org_id(user) -> int:
        """Extract organization_id from user object."""
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not associated with an organization",
            )
        return org_id

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/connect
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/connect",
        tags=["Encompass Integration"],
        summary="Connect organization to Encompass",
    )
    async def encompass_connect(
        request: EncompassConnectRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Connect the current user's organization to Encompass.

        Tests the provided credentials and stores them if valid.
        Requires admin or platform admin role.
        """
        org_id = _get_org_id(user)

        try:
            result = await oauth_service.connect(
                db=db,
                org_id=org_id,
                instance_id=request.instance_id,
                client_id=request.client_id,
                client_secret=request.client_secret,
                api_user=request.api_user,
                webhook_secret=request.webhook_secret,
            )
            return result
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            logger.error(f"Encompass connect failed for org {org_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to connect to Encompass. Please try again.",
            )

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/disconnect
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/disconnect",
        tags=["Encompass Integration"],
        summary="Disconnect organization from Encompass",
    )
    async def encompass_disconnect(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Disconnect the current user's organization from Encompass.

        Deactivates the stored configuration but does not delete it.
        """
        org_id = _get_org_id(user)

        try:
            result = await oauth_service.disconnect(db=db, org_id=org_id)
            return result
        except Exception as e:
            logger.error(f"Encompass disconnect failed for org {org_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to disconnect from Encompass.",
            )

    # -----------------------------------------------------------------
    # GET /api/v1/encompass/status
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/encompass/status",
        tags=["Encompass Integration"],
        summary="Get Encompass connection status",
    )
    async def encompass_status(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Get the current Encompass connection status for the organization.

        Returns configuration details (with secrets masked) and active status.
        """
        org_id = _get_org_id(user)

        config = await oauth_service.get_config(db=db, org_id=org_id)
        if not config:
            return {
                "connected": False,
                "message": "No Encompass integration configured",
            }

        return {
            "connected": config["is_active"],
            "config": config,
        }

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/test-connection
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/test-connection",
        tags=["Encompass Integration"],
        summary="Test Encompass connection",
    )
    async def encompass_test_connection(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Test the Encompass connection using stored credentials.

        Returns authentication status and latency.
        """
        org_id = _get_org_id(user)

        result = await oauth_service.test_connection(db=db, org_id=org_id)
        return result

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/sync/pull
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/sync/pull",
        tags=["Encompass Integration"],
        summary="Pull loans from Encompass",
    )
    async def encompass_sync_pull(
        request: EncompassSyncPullRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Pull loan data from Encompass into the CRM.

        Can pull specific loans by CRM ID or Encompass GUID, or pull all
        linked loans if no IDs are specified.
        """
        org_id = _get_org_id(user)

        try:
            client = await oauth_service.get_authenticated_client(db=db, org_id=org_id)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        sync_service = LOSSyncService(client=client)
        results = []

        async def _pull_one(loan_id_val: int, los_loan_id_val: Optional[str] = None):
            """Pull a single loan and record the result, isolating per-loan errors."""
            try:
                res = await sync_service.pull_from_los(
                    db=db, loan_id=loan_id_val, los_loan_id=los_loan_id_val,
                )
                # Update encompass_sync_status on the CRM loan record
                from database.models.lead_loan import Loan as _Loan
                _loan = db.query(_Loan).filter(_Loan.id == loan_id_val).first()
                if _loan:
                    _loan.encompass_sync_status = (
                        "synced" if res.status.value in ("success", "partial") else "error"
                    )
                    from datetime import datetime, timezone as _tz
                    _loan.encompass_last_synced_at = datetime.now(_tz.utc)
                    try:
                        db.flush()
                    except Exception as _e:
                        logger.warning(f"Failed to update sync status for loan {loan_id_val}: {_e}")
                results.append(res.to_dict())
            except Exception as pull_exc:
                logger.error(
                    f"Unexpected error during pull for CRM loan {loan_id_val} "
                    f"(los_loan_id={los_loan_id_val}): {pull_exc}",
                    exc_info=True,
                )
                results.append({
                    "status": "error",
                    "loan_id": loan_id_val,
                    "los_loan_id": los_loan_id_val,
                    "error": str(pull_exc),
                })

        if request.loan_ids:
            # Pull by CRM loan IDs
            for loan_id in request.loan_ids:
                await _pull_one(loan_id)
        elif request.los_loan_ids:
            # Pull by Encompass GUIDs — find matching CRM loans first
            from database.models.lead_loan import Loan

            for los_id in request.los_loan_ids:
                loan = db.query(Loan).filter(
                    Loan.encompass_loan_id == los_id,
                    Loan.organization_id == org_id,
                ).first()
                if loan:
                    await _pull_one(loan.id, los_loan_id_val=los_id)
                else:
                    logger.info(
                        f"Encompass pull: no CRM loan linked to GUID {los_id} "
                        f"for org {org_id}; skipping"
                    )
                    results.append({
                        "status": "skipped",
                        "los_loan_id": los_id,
                        "message": "No CRM loan linked to this Encompass ID",
                    })
        else:
            # Pull all linked loans for this org
            from database.models.lead_loan import Loan

            linked_loans = db.query(Loan).filter(
                Loan.organization_id == org_id,
                Loan.encompass_loan_id.isnot(None),
            ).all()

            logger.info(
                f"Encompass bulk pull for org {org_id}: "
                f"{len(linked_loans)} linked loans found"
            )
            for loan in linked_loans:
                await _pull_one(loan.id, los_loan_id_val=loan.encompass_loan_id)

        # Update last sync timestamp on the org's config
        _update_last_sync(db, org_id)

        success_count = sum(1 for r in results if r.get("status") in ("success", "partial"))
        error_count = sum(1 for r in results if r.get("status") == "error")
        logger.info(
            f"Encompass sync/pull for org {org_id}: "
            f"total={len(results)}, success={success_count}, errors={error_count}"
        )

        return {
            "total": len(results),
            "success": success_count,
            "errors": error_count,
            "results": results,
        }

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/sync/push/{loan_id}
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/sync/push/{loan_id}",
        tags=["Encompass Integration"],
        summary="Push loan to Encompass",
    )
    async def encompass_sync_push(
        loan_id: int,
        request: EncompassSyncPushRequest = None,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Push a CRM loan to Encompass.

        If the loan is already linked to an Encompass loan, updates it.
        If not, creates a new loan in Encompass and stores the returned GUID.
        """
        org_id = _get_org_id(user)

        # Verify the loan belongs to this org
        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.organization_id == org_id,
        ).first()
        if not loan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan {loan_id} not found in your organization",
            )

        try:
            client = await oauth_service.get_authenticated_client(db=db, org_id=org_id)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        sync_service = LOSSyncService(client=client)
        fields = request.fields if request else None
        result = await sync_service.push_to_los(db=db, loan_id=loan_id, fields=fields)

        # Update encompass columns on the loan after push
        if result.los_loan_id and not loan.encompass_loan_id:
            loan.encompass_loan_id = result.los_loan_id
        loan.encompass_last_synced_at = datetime.now(timezone.utc)
        loan.encompass_sync_status = "synced" if result.status.value == "success" else "error"
        db.flush()

        _update_last_sync(db, org_id)

        return result.to_dict()

    # -----------------------------------------------------------------
    # GET /api/v1/encompass/search
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/encompass/search",
        tags=["Encompass Integration"],
        summary="Search Encompass pipeline",
    )
    async def encompass_search(
        loan_number: Optional[str] = Query(None),
        borrower_name: Optional[str] = Query(None),
        loan_officer: Optional[str] = Query(None),
        limit: int = Query(25, ge=1, le=200),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Search the Encompass loan pipeline.

        Returns matching loans from Encompass with basic details.
        Useful for finding loans to import or link.
        """
        org_id = _get_org_id(user)

        try:
            client = await oauth_service.get_authenticated_client(db=db, org_id=org_id)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        filters = {}
        if loan_number:
            filters["loan_number"] = loan_number
        if borrower_name:
            filters["borrower_name"] = borrower_name
        if loan_officer:
            filters["loan_officer"] = loan_officer

        try:
            results = await client.search_loans(filters=filters, limit=limit)
            return {
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            logger.error(f"Encompass search failed for org {org_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Encompass search failed: {str(e)}",
            )

    # -----------------------------------------------------------------
    # POST /api/v1/encompass/import
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/encompass/import",
        tags=["Encompass Integration"],
        summary="Import loans from Encompass",
    )
    async def encompass_import(
        request: EncompassImportRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Import loans from Encompass into the CRM.

        Creates new CRM loan records from Encompass data and links them
        via the encompass_loan_id column.
        """
        org_id = _get_org_id(user)

        try:
            client = await oauth_service.get_authenticated_client(db=db, org_id=org_id)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        sync_service = LOSSyncService(client=client)

        try:
            result = await sync_service.import_from_los(
                db=db,
                los_loan_ids=request.los_loan_ids,
                organization_id=org_id,
                assign_to_lo_id=request.assign_to_lo_id,
            )
            return result
        except Exception as e:
            logger.error(f"Encompass import failed for org {org_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Import failed: {str(e)}",
            )

    # -----------------------------------------------------------------
    # GET /api/v1/encompass/field-mappings
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/encompass/field-mappings",
        tags=["Encompass Integration"],
        summary="Get field mappings",
    )
    async def encompass_get_field_mappings(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Get the current CRM-to-Encompass field mapping configuration.

        Returns the list of field mappings showing which CRM fields
        correspond to which Encompass field IDs and their sync direction.
        """
        # Use default sync service to get mappings
        from services.los_integration.sync_service import LOSSyncService, DEFAULT_FIELD_MAPPINGS
        from services.los_integration.encompass_client import EncompassClient

        # Create a temporary service just for getting mappings (no auth needed)
        # The field mappings are statically defined
        mappings = [
            {
                "crm_field": m.crm_field,
                "los_field": m.los_field,
                "direction": m.direction,
                "required": m.required,
                "transform": m.transform,
            }
            for m in DEFAULT_FIELD_MAPPINGS
        ]

        return {
            "count": len(mappings),
            "mappings": mappings,
        }

    # -----------------------------------------------------------------
    # GET /api/v1/encompass/health
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/encompass/health",
        tags=["Encompass Integration"],
        summary="Health check for Encompass integration",
    )
    async def encompass_health(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Check Encompass OAuth token validity and API connectivity.

        Attempts to obtain (or reuse) a valid access token for the
        organization's Encompass configuration, then performs a lightweight
        API call to verify end-to-end connectivity.

        Returns:
            status: "healthy" | "auth_failed" | "api_error" | "not_configured" | "error"
            authenticated: bool
            latency_ms: round-trip latency in milliseconds
            token_expires_at: ISO timestamp when the current token expires (if healthy)
            instance_id: Encompass instance ID
        """
        org_id = _get_org_id(user)

        # First make sure a config exists
        config_info = await oauth_service.get_config(db=db, org_id=org_id)
        if not config_info or not config_info.get("is_active"):
            return {
                "status": "not_configured",
                "authenticated": False,
                "message": (
                    "No active Encompass integration configured. "
                    "Connect via POST /api/v1/encompass/connect."
                ),
            }

        # Delegate to the OAuth service's test_connection which does both
        # token acquisition and a lightweight API ping
        result = await oauth_service.test_connection(db=db, org_id=org_id)
        logger.info(
            f"Encompass health check for org {org_id}: "
            f"status={result.get('status')}, latency={result.get('latency_ms')}ms"
        )
        return result

    # -----------------------------------------------------------------
    # PUT /api/v1/encompass/field-mappings
    # -----------------------------------------------------------------

    @app.put(
        "/api/v1/encompass/field-mappings",
        tags=["Encompass Integration"],
        summary="Update field mappings",
    )
    async def encompass_update_field_mappings(
        request: FieldMappingUpdateRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """Update the CRM-to-Encompass field mapping configuration.

        Replaces the current field mappings with the provided list.
        Changes take effect on the next sync operation.
        """
        org_id = _get_org_id(user)

        if not request.mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mappings list must not be empty",
            )

        # Validate all mappings before writing any to the database
        invalid = []
        for idx, item in enumerate(request.mappings):
            if item.direction not in _VALID_DIRECTIONS:
                invalid.append(
                    f"mappings[{idx}].direction '{item.direction}' is not valid "
                    f"(must be one of {sorted(_VALID_DIRECTIONS)})"
                )
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"errors": invalid},
            )

        # Store custom mappings in the database via LosFieldMapping model
        from database.models.los_sync import LosFieldMapping as DbFieldMapping

        # Deactivate existing mappings for this org
        existing = db.query(DbFieldMapping).filter(
            DbFieldMapping.organization_id == org_id,
            DbFieldMapping.los_system == "encompass",
        ).all()
        deactivated = len(existing)
        for mapping in existing:
            mapping.is_active = False

        # Create new mappings
        created = 0
        for item in request.mappings:
            db_mapping = DbFieldMapping(
                organization_id=org_id,
                los_system="encompass",
                entity_type="loan",
                crm_field_name=item.crm_field,
                los_field_name=item.los_field,
                sync_direction=item.direction,
                is_required=item.required,
                transform_function=item.transform,
                is_active=True,
            )
            db.add(db_mapping)
            created += 1

        db.flush()

        logger.info(
            f"Encompass field mappings updated for org {org_id}: "
            f"deactivated={deactivated}, created={created}"
        )

        return {
            "status": "updated",
            "mappings_count": created,
            "deactivated": deactivated,
            "message": f"Updated {created} field mappings for Encompass",
        }

    # -----------------------------------------------------------------
    # Helper Functions
    # -----------------------------------------------------------------

    def _update_last_sync(db: Session, org_id: int):
        """Update last_sync_at on the org's EncompassConfig."""
        try:
            from database.models.encompass_config import EncompassConfig

            config = db.query(EncompassConfig).filter(
                EncompassConfig.organization_id == org_id,
                EncompassConfig.is_active == True,  # noqa: E712
            ).first()
            if config:
                config.last_sync_at = datetime.now(timezone.utc)
                db.flush()
        except Exception as e:
            logger.warning(f"Failed to update last_sync_at for org {org_id}: {e}")

    logger.info("Encompass integration routes registered (11 endpoints)")
