"""
DocuSign Integration Routes
Handles OAuth and e-signature operations for DocuSign
"""
import os
import logging
from typing import Optional, Callable, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/docusign", tags=["docusign"])

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
# Request models
class SendForSignatureRequest(BaseModel):
    document_name: str
    document_base64: str
    signer_email: str
    signer_name: str
    email_subject: str
    email_body: Optional[str] = None


class CreateEnvelopeFromTemplateRequest(BaseModel):
    template_id: str
    email_subject: str
    template_roles: List[dict]
    status: str = "sent"


class VoidEnvelopeRequest(BaseModel):
    void_reason: str


@router.get("/auth")
async def docusign_auth(
    current_user=Depends(get_current_user)
):
    """Initiate DocuSign OAuth flow"""
    from integrations.docusign_service import docusign_client

    if not docusign_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response("DocuSign integration not configured", code="NOT_CONFIGURED")
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    state = f"{user_id}:{frontend_url}/settings/integrations"

    auth_url = docusign_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def docusign_callback(
    code: str = Query(..., description="Authorization code from DocuSign"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from DocuSign"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from DocuSign.
    Exchanges authorization code for access token.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"DocuSign OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=docusign_auth_failed&message={error_description or error}"
        )

    from integrations.docusign_service import docusign_client

    # Parse state
    user_id = None
    redirect_url = None
    if state:
        parts = state.split(":", 1)
        try:
            user_id = int(parts[0])
        except ValueError:
            pass
        if len(parts) > 1:
            redirect_url = parts[1]

    if not user_id:
        logger.error("Invalid state parameter in DocuSign callback")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state"
        )

    # Exchange code for tokens
    token_data = docusign_client.exchange_code_for_token(code)

    if not token_data:
        logger.error("Failed to exchange DocuSign authorization code")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=docusign_token_exchange_failed"
        )

    # Get user info
    user_info = docusign_client.get_user_info(token_data["access_token"])
    user_email = user_info.get("email") if user_info else None
    docusign_user_id = user_info.get("sub") if user_info else None

    # Get default account
    accounts = user_info.get("accounts", []) if user_info else []
    default_account = next((a for a in accounts if a.get("is_default")), accounts[0] if accounts else None)
    account_id = default_account.get("account_id") if default_account else None
    account_name = default_account.get("account_name") if default_account else None
    base_uri = default_account.get("base_uri") if default_account else None

    # Store tokens in user_integrations table
    try:
        # Check if user_integrations table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'user_integrations'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            db.execute(text("""
                CREATE TABLE user_integrations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    access_token TEXT,
                    refresh_token TEXT,
                    expires_at TIMESTAMP,
                    scopes TEXT,
                    email VARCHAR(255),
                    provider_user_id VARCHAR(255),
                    instance_url TEXT,
                    extra_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            db.commit()

        # Upsert the integration record
        db.execute(text("""
            INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, expires_at, email, provider_user_id, instance_url, scopes, extra_data, updated_at)
            VALUES
                (:user_id, 'docusign', :access_token, :refresh_token, :expires_at, :email, :docusign_user_id, :base_uri, :scopes,
                 jsonb_build_object(
                     'account_id', :account_id,
                     'account_name', :account_name,
                     'environment', :environment
                 ), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                email = EXCLUDED.email,
                provider_user_id = EXCLUDED.provider_user_id,
                instance_url = EXCLUDED.instance_url,
                scopes = EXCLUDED.scopes,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "email": user_email,
            "docusign_user_id": docusign_user_id,
            "base_uri": base_uri,
            "scopes": token_data.get("scope"),
            "account_id": account_id,
            "account_name": account_name,
            "environment": docusign_client.environment,
        })
        db.commit()

        logger.info(f"Successfully stored DocuSign tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing DocuSign tokens: {e}")
        db.rollback()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=docusign_storage_failed"
        )

    # Redirect back to integrations page with success
    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success=docusign_connected"
    )


@router.get("/status")
async def docusign_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check DocuSign connection status"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, provider_user_id, instance_url, scopes, extra_data
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'docusign'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({
                "connected": False,
                "enabled": docusign_client.enabled,
                "environment": docusign_client.environment
            })

        # Check if token is expired
        is_expired = False
        if row.expires_at:
            is_expired = datetime.now(timezone.utc) > row.expires_at

        extra_data = row.extra_data or {}

        return success_response({
            "connected": True,
            "enabled": docusign_client.enabled,
            "email": row.email,
            "account_id": extra_data.get("account_id"),
            "account_name": extra_data.get("account_name"),
            "environment": extra_data.get("environment", docusign_client.environment),
            "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })

    except Exception as e:
        logger.error(f"Error checking DocuSign status: {e}")
        return success_response({
            "connected": False,
            "enabled": docusign_client.enabled,
            "error": "Internal server error"
        })


@router.post("/refresh")
async def refresh_docusign_token(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Refresh DocuSign access token"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        # Get current refresh token
        result = db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = 'docusign'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail="No DocuSign connection found")

        # Refresh the token
        token_data = docusign_client.refresh_access_token(row.refresh_token)

        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        # Update stored tokens
        db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token,
                refresh_token = :refresh_token,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = 'docusign'
        """), {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at")
        })
        db.commit()

        return success_response({
            "refreshed": True,
            "expires_at": token_data.get("expires_at")
        })

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error refreshing DocuSign token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect_docusign(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect DocuSign integration"""
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'docusign'
        """), {"user_id": user_id})
        db.commit()

        return success_response({
            "disconnected": True
        }, "DocuSign integration disconnected")

    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting DocuSign: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# DocuSign API Endpoints

def get_docusign_credentials(user_id: int, db: Session):
    """Helper to get DocuSign credentials for a user"""
    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at, extra_data
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'docusign'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="DocuSign not connected")

    extra_data = row.extra_data or {}
    return row.access_token, extra_data.get("account_id")


@router.get("/envelopes")
async def list_envelopes(
    days: int = Query(30, description="Number of days to fetch envelopes for"),
    envelope_status: Optional[str] = Query(None, description="Filter by status: sent, delivered, completed, voided"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List envelopes (documents)"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    if not account_id:
        raise HTTPException(status_code=400, detail="DocuSign account not configured")

    from_date = datetime.now(timezone.utc) - timedelta(days=days)

    envelopes = docusign_client.list_envelopes(
        access_token,
        account_id,
        from_date=from_date,
        status=envelope_status
    )

    if envelopes is None:
        raise HTTPException(status_code=500, detail="Failed to fetch envelopes from DocuSign")

    return success_response(envelopes)


@router.get("/envelopes/{envelope_id}")
async def get_envelope(
    envelope_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get envelope details"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    envelope = docusign_client.get_envelope(access_token, account_id, envelope_id)

    if envelope is None:
        raise HTTPException(status_code=404, detail="Envelope not found")

    return success_response(envelope)


@router.post("/envelopes/send")
async def send_for_signature(
    request: SendForSignatureRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a document for signature"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    envelope = docusign_client.send_envelope_for_signature(
        access_token,
        account_id,
        document_name=request.document_name,
        document_base64=request.document_base64,
        signer_email=request.signer_email,
        signer_name=request.signer_name,
        email_subject=request.email_subject,
        email_body=request.email_body
    )

    if envelope is None:
        raise HTTPException(status_code=500, detail="Failed to send document for signature")

    return success_response(envelope, "Document sent for signature")


@router.post("/envelopes/{envelope_id}/void")
async def void_envelope(
    envelope_id: str,
    request: VoidEnvelopeRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Void an envelope"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    result = docusign_client.void_envelope(
        access_token,
        account_id,
        envelope_id,
        request.void_reason
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to void envelope")

    return success_response(result, "Envelope voided")


@router.get("/envelopes/{envelope_id}/documents")
async def get_envelope_documents(
    envelope_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of documents in an envelope"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    documents = docusign_client.get_envelope_documents(access_token, account_id, envelope_id)

    if documents is None:
        raise HTTPException(status_code=500, detail="Failed to fetch documents")

    return success_response(documents)


@router.get("/templates")
async def list_templates(
    count: int = Query(100, le=1000),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available templates"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    templates = docusign_client.list_templates(access_token, account_id, count=count)

    if templates is None:
        raise HTTPException(status_code=500, detail="Failed to fetch templates from DocuSign")

    return success_response(templates)


@router.post("/templates/{template_id}/send")
async def send_from_template(
    template_id: str,
    request: CreateEnvelopeFromTemplateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create and send an envelope from a template"""
    from integrations.docusign_service import docusign_client

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    access_token, account_id = get_docusign_credentials(user_id, db)

    envelope = docusign_client.create_envelope_from_template(
        access_token,
        account_id,
        template_id=template_id,
        email_subject=request.email_subject,
        template_roles=request.template_roles,
        status=request.status
    )

    if envelope is None:
        raise HTTPException(status_code=500, detail="Failed to create envelope from template")

    return success_response(envelope, "Envelope created from template")
