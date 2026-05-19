"""
Smart Docs Plaid Integration Routes

API endpoints for Plaid bank account verification, asset reports,
and transaction analysis. Provides the server-side endpoints that
pair with the Plaid Link frontend component.

Endpoints:
    POST /plaid/link-token              Create Link token for borrower
    POST /plaid/exchange-token          Exchange public token after Link
    GET  /plaid/connections/{loan_id}   List connected accounts for loan
    POST /plaid/asset-report/{loan_id}  Request GSE-certified asset report
    GET  /plaid/asset-report/{report_id} Get completed asset report
    POST /plaid/analyze/{loan_id}       Run bank analysis on Plaid data
    DELETE /plaid/connections/{id}      Disconnect account
    POST /plaid/webhooks                Plaid webhook handler (no auth)

All endpoints except /plaid/webhooks require authentication and enforce
tenant isolation via organization_id.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Plaid Integration"])


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class LinkTokenRequest(BaseModel):
    borrower_id: int = Field(..., description="Lead ID of the borrower")
    loan_id: int = Field(..., description="Loan ID to associate the connection with")


class LinkTokenResponse(BaseModel):
    link_token: str
    expiration: str
    request_id: Optional[str] = None


class ExchangeTokenRequest(BaseModel):
    public_token: str = Field(..., description="Public token from Plaid Link")
    borrower_id: int = Field(..., description="Lead ID of the borrower")
    loan_id: Optional[int] = Field(None, description="Loan ID to associate")


class ExchangeTokenResponse(BaseModel):
    connection_id: int
    item_id: str
    institution: Optional[str] = None


class PlaidConnectionSummary(BaseModel):
    connection_id: int
    institution_name: Optional[str] = None
    institution_id: Optional[str] = None
    item_id: str
    account_count: int = 0
    connection_status: str
    last_synced_at: Optional[str] = None
    asset_report_id: Optional[str] = None
    asset_report_status: Optional[str] = None
    created_at: str


class AssetReportRequest(BaseModel):
    connection_id: int = Field(..., description="PlaidConnection ID to generate report for")
    days_requested: int = Field(60, description="Number of days of history", ge=1, le=730)


class AssetReportResponse(BaseModel):
    asset_report_token: str


class BankAnalysisResponse(BaseModel):
    loan_id: int
    analysis_date: str
    connections_analyzed: int
    total_transactions: int
    large_deposits: List[dict] = []
    nsf_events: List[dict] = []
    irs_payments: dict = {}
    risk_score: int = 0
    risk_level: str = "low"
    risk_factors: List[dict] = []
    recommendations: List[str] = []


class WebhookPayload(BaseModel):
    webhook_type: str
    webhook_code: str
    item_id: Optional[str] = None
    asset_report_id: Optional[str] = None
    error: Optional[dict] = None


# =============================================================================
# Helpers
# =============================================================================

def _get_plaid_service(db: Session):
    """Get PlaidIntegrationService instance."""
    from services.smart_docs.integrations.plaid_service import (
        get_plaid_service,
    )
    return get_plaid_service(db)


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/plaid/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    request: LinkTokenRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a Plaid Link token for a borrower to connect their bank.

    The Link token is used by the Plaid Link frontend component to
    launch the bank account connection flow.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        result = service.create_link_token(
            borrower_id=request.borrower_id,
            org_id=org_id,
            loan_id=request.loan_id,
        )
        return LinkTokenResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create Plaid link token")
        raise HTTPException(status_code=500, detail=f"Failed to create link token: {e}")


@router.post("/plaid/exchange-token", response_model=ExchangeTokenResponse)
async def exchange_public_token(
    request: ExchangeTokenRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Exchange a public token from Plaid Link for an access token.

    The access token is encrypted before storage. The raw token is
    never persisted or returned to the client.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        result = service.exchange_public_token(
            public_token=request.public_token,
            borrower_id=request.borrower_id,
            org_id=org_id,
            loan_id=request.loan_id,
        )
        return ExchangeTokenResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to exchange Plaid public token")
        raise HTTPException(status_code=500, detail=f"Failed to exchange token: {e}")


@router.get(
    "/plaid/connections/{loan_id}",
    response_model=List[PlaidConnectionSummary],
)
async def get_connections(
    loan_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List all Plaid connections for a loan.

    Returns connection summaries including institution name, status,
    and asset report availability.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        connections = service.get_connections_for_loan(
            loan_id=loan_id,
            org_id=org_id,
        )
        return [PlaidConnectionSummary(**c) for c in connections]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list Plaid connections")
        raise HTTPException(status_code=500, detail=f"Failed to list connections: {e}")


@router.post("/plaid/asset-report/{loan_id}", response_model=AssetReportResponse)
async def create_asset_report(
    loan_id: int,
    request: AssetReportRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Request a GSE-certified Plaid Asset Report.

    Asset Reports are generated asynchronously. Poll the
    GET /plaid/asset-report/{report_id} endpoint or wait for
    the ASSET_REPORT webhook to know when it is ready.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        token = service.create_asset_report(
            access_token_id=request.connection_id,
            days_requested=request.days_requested,
            org_id=org_id,
        )
        return AssetReportResponse(asset_report_token=token)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create asset report")
        raise HTTPException(status_code=500, detail=f"Failed to create asset report: {e}")


@router.get("/plaid/asset-report/{report_id}")
async def get_asset_report(
    report_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve a completed Plaid Asset Report.

    Returns account balances, transaction history, and report metadata.
    Returns 404 if the report is not ready yet.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        report = service.get_asset_report(
            asset_report_id=report_id,
            org_id=org_id,
        )
        return report

    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)
        if "not found" in error_str.lower():
            raise HTTPException(status_code=404, detail="Asset report not found")
        logger.exception("Failed to get asset report")
        raise HTTPException(status_code=500, detail=f"Failed to get asset report: {e}")


@router.post("/plaid/analyze/{loan_id}", response_model=BankAnalysisResponse)
async def analyze_bank_data(
    loan_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Run full bank analysis on Plaid data for a loan.

    Analyzes transactions from all connected accounts, detecting
    large deposits, NSF events, IRS payments, and computing a
    risk score.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        analysis = service.generate_bank_analysis_from_plaid(
            loan_id=loan_id,
            org_id=org_id,
        )
        return BankAnalysisResponse(**analysis)

    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)
        if "no active" in error_str.lower() or "no connections" in error_str.lower():
            raise HTTPException(
                status_code=404,
                detail="No active Plaid connections for this loan",
            )
        logger.exception("Failed to run bank analysis")
        raise HTTPException(status_code=500, detail=f"Bank analysis failed: {e}")


@router.delete("/plaid/connections/{connection_id}")
async def disconnect_account(
    connection_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Disconnect a Plaid account and revoke the access token.

    This permanently revokes Plaid access for the specified connection.
    The connection record is preserved with status "revoked" for
    audit purposes.
    """
    try:
        service = _get_plaid_service(db)
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        result = service.disconnect_account(
            access_token_id=connection_id,
            org_id=org_id,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)
        if "not found" in error_str.lower():
            raise HTTPException(status_code=404, detail="Connection not found")
        logger.exception("Failed to disconnect Plaid account")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {e}")


@router.post("/plaid/webhooks")
async def handle_plaid_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Handle Plaid webhook notifications (no auth required).

    Plaid sends webhooks for async events like asset report completion,
    transaction updates, and connection status changes.

    The webhook signature is verified using the Plaid-Verification
    header when a verification key is configured.
    """
    try:
        body = await request.body()
        webhook_data = await request.json()

        # Verify webhook signature
        from services.smart_docs.integrations.plaid_service import (
            PlaidIntegrationService,
        )
        import os

        verification_header = request.headers.get("Plaid-Verification", "")
        verification_key = os.environ.get("PLAID_WEBHOOK_VERIFICATION_KEY", "")

        if not PlaidIntegrationService.verify_webhook_signature(
            body=body,
            signed_jwt=verification_header,
            plaid_webhook_verification_key=verification_key or None,
        ):
            logger.warning("Plaid webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        service = _get_plaid_service(db)
        result = service.webhook_handler(webhook_data)

        logger.info(
            "Plaid webhook processed | type=%s | code=%s | result=%s",
            webhook_data.get("webhook_type"),
            webhook_data.get("webhook_code"),
            result,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to handle Plaid webhook")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {e}")
