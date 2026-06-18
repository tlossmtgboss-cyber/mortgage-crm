"""
Microsoft Graph Email Service

Handles OAuth2 authorization flow and email sending via the Microsoft
Graph API (https://graph.microsoft.com/v1.0).

Configuration (environment variables):
    MICROSOFT_CLIENT_ID        — Azure AD application (client) ID
    MICROSOFT_CLIENT_SECRET    — Azure AD client secret
    MICROSOFT_TENANT_ID        — Azure AD tenant ID (default: "common")
    MICROSOFT_REDIRECT_URI     — OAuth2 redirect URI

Security notes:
    - Tokens are never logged.  Only the email address is logged for
      traceability.
    - Access tokens are refreshed automatically when expired.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
import requests
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
MICROSOFT_REDIRECT_URI = os.getenv(
    "MICROSOFT_REDIRECT_URI",
    "https://api.perenniaai.com/api/v1/email/microsoft/callback",
)

# OAuth2 endpoints (v2.0)
AUTHORIZE_URL = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"

# Graph API
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Scopes required for sending email
SCOPES = "Mail.Send offline_access User.Read"

# Safety margin: refresh token 5 minutes before actual expiry
_TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

# HTTP timeout for all outbound calls (seconds)
_HTTP_TIMEOUT = 30


class MicrosoftGraphEmailService:
    """Microsoft Graph API service for OAuth2 email integration."""

    # ------------------------------------------------------------------
    # OAuth2 Flow
    # ------------------------------------------------------------------

    @staticmethod
    def get_authorization_url(state: str) -> str:
        """Build the Microsoft OAuth2 authorization URL.

        Args:
            state: Opaque state parameter (JWT with user_id/org_id) for CSRF
                   protection and session binding.

        Returns:
            Full authorization URL to redirect the user's browser to.
        """
        params = {
            "client_id": MICROSOFT_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": MICROSOFT_REDIRECT_URI,
            "response_mode": "query",
            "scope": SCOPES,
            "state": state,
            "prompt": "consent",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
        """Exchange an authorization code for access + refresh tokens.

        Args:
            code: The authorization code returned by Microsoft.

        Returns:
            Dict with keys: access_token, refresh_token, expires_in, scope,
            token_type.

        Raises:
            ValueError: When the token exchange fails.
        """
        data = {
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "code": code,
            "redirect_uri": MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        }

        resp = requests.post(TOKEN_URL, data=data, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            error_detail = resp.json().get("error_description", resp.text)
            logger.error("Microsoft token exchange failed: %s", error_detail)
            raise ValueError(f"Token exchange failed: {error_detail}")

        token_data = resp.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_in": token_data.get("expires_in", 3600),
            "scope": token_data.get("scope", ""),
            "token_type": token_data.get("token_type", "Bearer"),
        }

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        """Use a refresh token to obtain a new access token.

        Args:
            refresh_token: The stored refresh token.

        Returns:
            Dict with keys: access_token, refresh_token, expires_in.

        Raises:
            ValueError: When the refresh fails (e.g. token revoked).
        """
        data = {
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": SCOPES,
        }

        resp = requests.post(TOKEN_URL, data=data, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            error_detail = resp.json().get("error_description", resp.text)
            logger.error("Microsoft token refresh failed: %s", error_detail)
            raise ValueError(f"Token refresh failed: {error_detail}")

        token_data = resp.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "expires_in": token_data.get("expires_in", 3600),
        }

    @staticmethod
    async def refresh_access_token_async(refresh_token: str) -> Dict[str, Any]:
        """Async version of refresh_access_token — does not block the event loop.

        Use this in all async FastAPI route handlers and services.

        Raises:
            ValueError: When the refresh fails (e.g. token revoked by user).
        """
        data = {
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": SCOPES,
        }

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(TOKEN_URL, data=data)

        if resp.status_code != 200:
            error_detail = ""
            try:
                error_detail = resp.json().get("error_description", resp.text)
            except Exception:
                error_detail = resp.text[:200]
            logger.error("Microsoft token refresh failed (async): %s", error_detail)
            raise ValueError(f"Token refresh failed: {error_detail}")

        token_data = resp.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "expires_in": token_data.get("expires_in", 3600),
        }

    @classmethod
    async def get_valid_access_token_async(
        cls,
        db: Session,
        org_id: int,
    ) -> Tuple[str, str]:
        """Async version of get_valid_access_token — proactively refreshes if expiring within 5 minutes.

        Proactively refreshes when the token is within _TOKEN_REFRESH_MARGIN (5 min)
        of expiry, rather than waiting for a 401 from the Graph API.

        Returns:
            Tuple of (access_token, from_email).

        Raises:
            ValueError: When no active token exists for the org, the token is
                        revoked, or the user must reconnect Outlook.
        """
        from database.models.microsoft_email import MicrosoftEmailToken

        record = (
            db.query(MicrosoftEmailToken)
            .filter(
                MicrosoftEmailToken.organization_id == org_id,
                MicrosoftEmailToken.is_active.is_(True),
            )
            .first()
        )

        if not record:
            raise ValueError(f"No active Microsoft email token for org {org_id}")

        now = datetime.now(timezone.utc)

        # Proactive refresh: refresh when token is within the 5-minute buffer
        if record.token_expiry and record.token_expiry <= now + _TOKEN_REFRESH_MARGIN:
            logger.info(
                "Proactively refreshing Microsoft token for org %d (%s)",
                org_id, _mask(record.email_address),
            )
            try:
                refreshed = await cls.refresh_access_token_async(record.refresh_token)
            except ValueError:
                # Refresh failed — mark record inactive so we don't keep retrying
                record.is_active = False
                db.commit()
                raise ValueError(
                    f"Microsoft Outlook token for org {org_id} has expired or been revoked. "
                    "Please reconnect Outlook in Settings > Email Integration."
                )

            record.access_token = refreshed["access_token"]
            if refreshed.get("refresh_token"):
                record.refresh_token = refreshed["refresh_token"]
            record.token_expiry = now + timedelta(seconds=refreshed.get("expires_in", 3600))
            record.updated_at = now
            db.commit()
            db.refresh(record)

        return record.access_token, record.email_address

    # ------------------------------------------------------------------
    # Graph API: Send Email
    # ------------------------------------------------------------------

    @staticmethod
    def send_email(
        access_token: str,
        to_email: str,
        subject: str,
        html_content: str,
        from_email: str,
        plain_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send an email via the Microsoft Graph API.

        Args:
            access_token: Valid Graph API access token.
            to_email: Recipient email address.
            subject: Email subject line.
            html_content: HTML body of the email.
            from_email: Sender email (used for logging only; Graph sends as
                        the authenticated user).
            plain_content: Optional plain-text body alternative (not used by
                           Graph sendMail but kept for API parity).
            cc: Optional list of CC email addresses.
            bcc: Optional list of BCC email addresses.
            attachments: Optional list of dicts with keys: name, contentType,
                         contentBytes (base64-encoded).

        Returns:
            {"success": True, "provider": "microsoft_graph"} on success, or
            {"success": False, "error": "<detail>"} on failure.
        """
        # Build recipients
        to_recipients = [{"emailAddress": {"address": to_email}}]
        cc_recipients = (
            [{"emailAddress": {"address": addr}} for addr in cc] if cc else []
        )
        bcc_recipients = (
            [{"emailAddress": {"address": addr}} for addr in bcc] if bcc else []
        )

        # Build message payload
        message: Dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_content,
            },
            "toRecipients": to_recipients,
        }
        if cc_recipients:
            message["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["bccRecipients"] = bcc_recipients

        # Attachments
        if attachments:
            graph_attachments = []
            for att in attachments:
                graph_attachments.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att.get("name", att.get("filename", "attachment")),
                    "contentType": att.get("contentType", att.get("type", "application/octet-stream")),
                    "contentBytes": att.get("contentBytes", att.get("content", "")),
                })
            message["attachments"] = graph_attachments

        payload = {
            "message": message,
            "saveToSentItems": True,
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                f"{GRAPH_BASE}/me/sendMail",
                json=payload,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            # Graph returns 202 Accepted on success (no body)
            if resp.status_code in (200, 202):
                logger.info(
                    "Email sent via Microsoft Graph from %s to %s: %s",
                    _mask(from_email),
                    _mask(to_email),
                    subject,
                )
                return {"success": True, "provider": "microsoft_graph"}

            # Error
            error_body = resp.text
            try:
                error_json = resp.json()
                error_body = error_json.get("error", {}).get("message", resp.text)
            except Exception:
                pass
            logger.error(
                "Microsoft Graph sendMail failed (%d) for %s: %s",
                resp.status_code,
                _mask(from_email),
                error_body,
            )
            return {"success": False, "error": error_body, "status_code": resp.status_code}

        except requests.RequestException as e:
            logger.error("Microsoft Graph sendMail request error: %s", str(e))
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Graph API: User Profile
    # ------------------------------------------------------------------

    @staticmethod
    def get_user_profile(access_token: str) -> Dict[str, Any]:
        """Fetch the authenticated user's profile from Graph API.

        Returns:
            Dict with at least: mail, displayName, userPrincipalName.

        Raises:
            ValueError: When the profile request fails.
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        resp = requests.get(
            f"{GRAPH_BASE}/me",
            headers=headers,
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            error_detail = resp.text
            try:
                error_detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                pass
            logger.error("Microsoft Graph /me failed (%d): %s", resp.status_code, error_detail)
            raise ValueError(f"Failed to fetch user profile: {error_detail}")

        profile = resp.json()
        return {
            "mail": profile.get("mail") or profile.get("userPrincipalName", ""),
            "displayName": profile.get("displayName", ""),
            "userPrincipalName": profile.get("userPrincipalName", ""),
            "id": profile.get("id", ""),
        }

    # ------------------------------------------------------------------
    # Token Management: DB-Aware Helper
    # ------------------------------------------------------------------

    @classmethod
    def get_valid_access_token(
        cls,
        db: Session,
        org_id: int,
    ) -> Tuple[str, str]:
        """Load tokens from DB, refresh if expired, persist updates.

        Args:
            db: Active SQLAlchemy session.
            org_id: Organization ID to look up tokens for.

        Returns:
            Tuple of (access_token, from_email).

        Raises:
            ValueError: When no active token exists for the org, or the
                        refresh fails.
        """
        from database.models.microsoft_email import MicrosoftEmailToken

        record = (
            db.query(MicrosoftEmailToken)
            .filter(
                MicrosoftEmailToken.organization_id == org_id,
                MicrosoftEmailToken.is_active.is_(True),
            )
            .first()
        )

        if not record:
            raise ValueError(f"No active Microsoft email token for org {org_id}")

        now = datetime.now(timezone.utc)

        # Refresh if expired or about to expire
        if record.token_expiry and record.token_expiry <= now + _TOKEN_REFRESH_MARGIN:
            logger.info("Refreshing Microsoft token for org %d (%s)", org_id, _mask(record.email_address))
            try:
                refreshed = cls.refresh_access_token(record.refresh_token)
            except ValueError:
                # Refresh failed — mark record inactive so we don't keep retrying
                record.is_active = False
                db.commit()
                raise

            record.access_token = refreshed["access_token"]
            # Microsoft may rotate the refresh token
            if refreshed.get("refresh_token"):
                record.refresh_token = refreshed["refresh_token"]
            record.token_expiry = now + timedelta(seconds=refreshed.get("expires_in", 3600))
            record.updated_at = now
            db.commit()
            db.refresh(record)

        return record.access_token, record.email_address


# ---------------------------------------------------------------------------
# Utilities (module-private)
# ---------------------------------------------------------------------------

def _mask(email: str) -> str:
    """Mask an email address for safe logging: 'user@example.com' -> 'u***@example.com'."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
