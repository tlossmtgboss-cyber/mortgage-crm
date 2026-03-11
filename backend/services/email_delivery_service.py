"""
Native Email Delivery Service
==============================
Provides email sending without requiring enterprise email OAuth setup.

Provider waterfall (per attempt):
  1. SendGrid  — SENDGRID_API_KEY env var or org-level key
  2. Microsoft Graph API — if org has Microsoft OAuth tokens stored in
                           user_integrations (provider='microsoft')
  3. Gmail API           — if org has Google OAuth tokens stored in
                           user_integrations (provider='google')

When no provider is configured the message is logged in dry-run mode so
development and staging environments work without credentials.

Usage::

    from services.email_delivery_service import EmailDeliveryService
    from services.email_delivery_models import EmailMessage

    service = EmailDeliveryService(db)
    result = await service.send_email(
        to="borrower@example.com",
        subject="Your Loan Update",
        html_body="<p>Loan update details...</p>",
        from_email="lo@company.com",
        organization_id="42",
    )
    if not result.success:
        logger.error("Email failed: %s", result.error)

Features
--------
- SendGrid primary → Microsoft Graph fallback → Gmail fallback
- Per-org rate limiting (default 100 emails/minute, token-bucket)
- HTML + plain-text multipart bodies
- File attachments (path-based or raw bytes)
- CAN-SPAM List-Unsubscribe header injection
- Structured delivery logging (provider, status, message_id, latency)
- Full type hints; no circular imports with main.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from services.email_delivery_models import (
    EmailAttachment,
    EmailDeliveryConfig,
    EmailDeliveryResult,
    EmailMessage,
    EmailProvider,
    EmailStatus,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_SENDGRID_API_BASE = "https://api.sendgrid.com/v3"
_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"

# HTTP timeout for provider calls (seconds)
_HTTP_TIMEOUT = 30.0

# Number of seconds a delivery attempt is retried before failing
_MAX_PROVIDER_ATTEMPTS = 2


# =============================================================================
# IN-PROCESS TOKEN-BUCKET RATE LIMITER
# =============================================================================

class _OrgRateLimiter:
    """
    Simple in-process token-bucket rate limiter keyed by organization_id.

    Thread-safe via asyncio.Lock.  One instance is shared across all
    EmailDeliveryService instances through the module-level
    ``_rate_limiters`` registry below.
    """

    def __init__(self, max_per_minute: int = 100) -> None:
        self._max = max_per_minute
        self._tokens: float = float(max_per_minute)
        self._last_refill: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Consume one token.  Returns True if allowed, False if rate-limited.
        Never blocks; callers should handle False by returning immediately.
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            # Refill at a rate of max_per_minute tokens per 60 seconds
            self._tokens = min(
                float(self._max),
                self._tokens + elapsed * (self._max / 60.0),
            )
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# Module-level registry: org_id (str) → _OrgRateLimiter
_rate_limiters: Dict[str, _OrgRateLimiter] = {}
_rate_limiter_registry_lock = asyncio.Lock()


async def _get_rate_limiter(org_id: str, max_per_minute: int) -> _OrgRateLimiter:
    async with _rate_limiter_registry_lock:
        if org_id not in _rate_limiters:
            _rate_limiters[org_id] = _OrgRateLimiter(max_per_minute)
        limiter = _rate_limiters[org_id]
        # Update cap if org config changed
        limiter._max = max_per_minute
        return limiter


# =============================================================================
# HELPER: ATTACHMENT ENCODING
# =============================================================================

def _encode_attachment(att: EmailAttachment) -> bytes:
    """
    Return raw bytes for an attachment.

    Reads from att.file_path if raw_content is not set.
    Raises ValueError when neither is available.
    """
    if att.raw_content is not None:
        return att.raw_content
    if att.file_path:
        with open(att.file_path, "rb") as fh:
            return fh.read()
    raise ValueError(
        f"Attachment '{att.filename}' has neither file_path nor raw_content"
    )


# =============================================================================
# HELPER: UNSUBSCRIBE HEADER / FOOTER
# =============================================================================

def _make_unsubscribe_token(email: str, secret: str = "") -> str:
    """Deterministic HMAC-SHA256 token for an unsubscribe link."""
    key = (secret or os.getenv("SECRET_KEY", "perennia-email-unsub")).encode()
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()[:32]


def _inject_unsubscribe(
    message: EmailMessage,
    unsubscribe_url: str,
) -> EmailMessage:
    """
    Return a copy of *message* with List-Unsubscribe header and footer link.
    The unsubscribe URL gets a ``token`` query parameter appended so the
    backend can validate opt-outs without exposing raw emails.
    """
    to_addr = message.to[0] if message.to else ""
    token = _make_unsubscribe_token(to_addr)
    sep = "&" if "?" in unsubscribe_url else "?"
    full_url = f"{unsubscribe_url}{sep}token={token}"

    # Build updated headers dict
    headers = dict(message.headers or {})
    headers["List-Unsubscribe"] = f"<{full_url}>"
    headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Append footer to HTML body
    html_body = message.html_body
    if html_body:
        footer = (
            f'<p style="font-size:11px;color:#9ca3af;text-align:center;'
            f'margin-top:32px;">'
            f'<a href="{full_url}" style="color:#9ca3af;">Unsubscribe</a>'
            f" from this email list.</p>"
        )
        html_body = html_body + footer

    return message.model_copy(
        update={"headers": headers, "html_body": html_body}
    )


# =============================================================================
# MAIN SERVICE
# =============================================================================

class EmailDeliveryService:
    """
    Native multi-provider email delivery service.

    Instantiate per-request (passes in a SQLAlchemy session for OAuth token
    lookup).  The service itself is stateless beyond the session reference;
    rate limiter state lives at module level so it persists across requests.

    Parameters
    ----------
    db : Session
        SQLAlchemy session used to look up org settings and OAuth tokens.
    default_config : EmailDeliveryConfig | None
        Override the default global config (primarily for unit testing).
    """

    def __init__(
        self,
        db: Session,
        default_config: Optional[EmailDeliveryConfig] = None,
    ) -> None:
        self._db = db
        self._default_config = default_config or EmailDeliveryConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_email(
        self,
        *,
        to: str | List[str],
        subject: str,
        html_body: Optional[str] = None,
        text_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[EmailAttachment]] = None,
        headers: Optional[Dict[str, str]] = None,
        unsubscribe_url: Optional[str] = None,
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> EmailDeliveryResult:
        """
        Send an email using the configured provider waterfall.

        Parameters
        ----------
        to : str | list[str]
            One or more recipient addresses.
        subject : str
            Email subject line.
        html_body : str | None
            HTML body.  At least one of html_body / text_body is required.
        text_body : str | None
            Plain-text fallback body.
        from_email : str | None
            Sender address.  Falls back to org config then env var.
        from_name : str | None
            Sender display name.
        cc : list[str] | None
            CC recipients.
        bcc : list[str] | None
            BCC recipients.
        reply_to : str | None
            Reply-To address.
        attachments : list[EmailAttachment] | None
            File attachments.
        headers : dict | None
            Extra headers (merged with auto-generated ones).
        unsubscribe_url : str | None
            If set, injects List-Unsubscribe header + footer link.
        organization_id : str | None
            Used for rate limiting and audit logging.
        user_id : str | None
            Sender user ID stored in delivery logs.

        Returns
        -------
        EmailDeliveryResult
        """
        to_list = [to] if isinstance(to, str) else list(to)

        message = EmailMessage(
            to=to_list,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_email=from_email,
            from_name=from_name,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            headers=headers,
            unsubscribe_url=unsubscribe_url,
            organization_id=organization_id,
            user_id=user_id,
        )

        return await self._deliver(message)

    async def send_message(self, message: EmailMessage) -> EmailDeliveryResult:
        """
        Lower-level send method that accepts a fully-constructed EmailMessage.
        """
        return await self._deliver(message)

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    async def _deliver(self, message: EmailMessage) -> EmailDeliveryResult:
        """
        Core delivery orchestrator.

        1. Load org config.
        2. Apply unsubscribe decoration.
        3. Check rate limit.
        4. Try providers in order; return first success.
        5. Log the outcome.
        """
        org_id = message.organization_id or "__global__"
        config = await self._load_org_config(org_id)

        # Inject unsubscribe links/headers
        effective_url = message.unsubscribe_url or config.unsubscribe_base_url
        if effective_url:
            message = _inject_unsubscribe(message, effective_url)

        # Rate limit check
        limiter = await _get_rate_limiter(org_id, config.max_emails_per_minute)
        if not await limiter.acquire():
            result = EmailDeliveryResult(
                status=EmailStatus.RATE_LIMITED,
                provider=EmailProvider.NONE,
                error=(
                    f"Rate limit exceeded for org {org_id} "
                    f"({config.max_emails_per_minute}/min)"
                ),
                to=message.to,
            )
            logger.warning(
                "email.rate_limited org=%s to=%s subject=%r",
                org_id,
                message.to,
                message.subject,
            )
            return result

        # Resolve effective sender
        effective_from_email = (
            message.from_email
            or config.from_email
            or os.getenv("SENDGRID_FROM_EMAIL", "noreply@perenniaai.com")
        )
        effective_from_name = (
            message.from_name
            or config.from_name
            or os.getenv("SENDGRID_FROM_NAME", "Perennia AI")
        )
        message = message.model_copy(
            update={
                "from_email": effective_from_email,
                "from_name": effective_from_name,
            }
        )

        # Build ordered provider list
        providers_to_try = self._build_provider_order(config)

        providers_tried: List[str] = []
        last_error: Optional[str] = None

        for provider in providers_to_try:
            providers_tried.append(provider.value)
            try:
                result = await self._try_provider(
                    provider=provider,
                    message=message,
                    config=config,
                    org_id=org_id,
                )
                if result.success:
                    result = result.model_copy(
                        update={"providers_tried": providers_tried}
                    )
                    self._log_delivery(result, message)
                    return result
                last_error = result.error
            except Exception as exc:
                last_error = str(exc)
                logger.exception(
                    "email.provider_exception provider=%s org=%s",
                    provider.value,
                    org_id,
                )

        # All providers failed
        result = EmailDeliveryResult(
            status=EmailStatus.FAILED,
            provider=EmailProvider.NONE,
            error=last_error or "All providers failed",
            providers_tried=providers_tried,
            to=message.to,
        )
        self._log_delivery(result, message)
        return result

    def _build_provider_order(
        self, config: EmailDeliveryConfig
    ) -> List[EmailProvider]:
        """
        Return the ordered list of providers to try.

        Preferred provider goes first; remaining available providers follow.
        """
        all_providers = [
            EmailProvider.SENDGRID,
            EmailProvider.MICROSOFT,
            EmailProvider.GMAIL,
        ]
        # Put preferred first, keep others in default order after
        ordered: List[EmailProvider] = [config.preferred_provider]
        for p in all_providers:
            if p not in ordered:
                ordered.append(p)
        return ordered

    async def _try_provider(
        self,
        *,
        provider: EmailProvider,
        message: EmailMessage,
        config: EmailDeliveryConfig,
        org_id: str,
    ) -> EmailDeliveryResult:
        """Dispatch to the correct provider method."""
        if provider == EmailProvider.SENDGRID:
            return await self._send_via_sendgrid(message, config)
        if provider == EmailProvider.MICROSOFT:
            return await self._send_via_microsoft(message, org_id)
        if provider == EmailProvider.GMAIL:
            return await self._send_via_gmail(message, org_id)
        # Fallthrough — dry-run
        return self._dry_run_result(message)

    # ------------------------------------------------------------------
    # Provider: SendGrid
    # ------------------------------------------------------------------

    async def _send_via_sendgrid(
        self, message: EmailMessage, config: EmailDeliveryConfig
    ) -> EmailDeliveryResult:
        """Send via SendGrid Mail Send v3 API."""
        api_key = (
            config.sendgrid_api_key
            or os.getenv("SENDGRID_API_KEY", "")
        )
        if not api_key:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.SENDGRID,
                error="SendGrid API key not configured",
                to=message.to,
            )

        payload = self._build_sendgrid_payload(message)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{_SENDGRID_API_BASE}/mail/send",
                    json=payload,
                    headers=headers,
                )

            if response.status_code in (200, 202):
                message_id = response.headers.get("X-Message-Id") or str(uuid.uuid4())
                logger.info(
                    "email.sendgrid.sent message_id=%s to=%s subject=%r",
                    message_id,
                    message.to,
                    message.subject,
                )
                return EmailDeliveryResult(
                    message_id=message_id,
                    status=EmailStatus.SENT,
                    provider=EmailProvider.SENDGRID,
                    to=message.to,
                )

            # Parse SendGrid error body
            try:
                err_body = response.json()
                errors = err_body.get("errors", [])
                err_msg = "; ".join(e.get("message", "") for e in errors) or response.text
            except Exception:
                err_msg = response.text or f"HTTP {response.status_code}"

            logger.warning(
                "email.sendgrid.failed status=%s error=%r to=%s",
                response.status_code,
                err_msg,
                message.to,
            )
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.SENDGRID,
                error=f"SendGrid {response.status_code}: {err_msg}",
                to=message.to,
            )

        except httpx.TimeoutException:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.SENDGRID,
                error="SendGrid request timed out",
                to=message.to,
            )
        except Exception as exc:
            logger.error("email.sendgrid.exception: %s", exc)
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.SENDGRID,
                error=str(exc),
                to=message.to,
            )

    def _build_sendgrid_payload(self, message: EmailMessage) -> Dict[str, Any]:
        """Construct the SendGrid /mail/send JSON body."""
        from_obj: Dict[str, str] = {"email": message.from_email or ""}
        if message.from_name:
            from_obj["name"] = message.from_name

        personalizations: Dict[str, Any] = {
            "to": [{"email": addr} for addr in message.to],
        }
        if message.cc:
            personalizations["cc"] = [{"email": addr} for addr in message.cc]
        if message.bcc:
            personalizations["bcc"] = [{"email": addr} for addr in message.bcc]

        # Subject can also live in personalizations for per-recipient overrides
        # but we keep it at the top level here.
        payload: Dict[str, Any] = {
            "from": from_obj,
            "subject": message.subject,
            "personalizations": [personalizations],
            "content": [],
        }

        # Plain text first (RFC 2822 ordering)
        if message.text_body:
            payload["content"].append(
                {"type": "text/plain", "value": message.text_body}
            )
        elif message.html_body:
            # Auto-generate a plain-text alternative by stripping HTML
            payload["content"].append(
                {"type": "text/plain", "value": message.effective_text_body}
            )

        if message.html_body:
            payload["content"].append(
                {"type": "text/html", "value": message.html_body}
            )

        if message.reply_to:
            payload["reply_to"] = {"email": message.reply_to}

        # Custom headers (already includes List-Unsubscribe if injected)
        if message.headers:
            payload["headers"] = message.headers

        # Attachments
        if message.attachments:
            sg_attachments = []
            for att in message.attachments:
                try:
                    raw = _encode_attachment(att)
                    sg_attachments.append(
                        {
                            "content": base64.b64encode(raw).decode("utf-8"),
                            "type": att.content_type,
                            "filename": att.filename,
                            "disposition": "attachment",
                        }
                    )
                except Exception as exc:
                    logger.error(
                        "email.sendgrid.attachment_error filename=%s error=%s",
                        att.filename,
                        exc,
                    )
            if sg_attachments:
                payload["attachments"] = sg_attachments

        return payload

    # ------------------------------------------------------------------
    # Provider: Microsoft Graph API
    # ------------------------------------------------------------------

    async def _send_via_microsoft(
        self, message: EmailMessage, org_id: str
    ) -> EmailDeliveryResult:
        """
        Send via Microsoft Graph /me/sendMail using a stored user OAuth token.

        Looks up an active Microsoft token for any user in the organization
        from the user_integrations table.
        """
        token_info = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_microsoft_token, org_id
        )
        if not token_info:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.MICROSOFT,
                error="No Microsoft OAuth token configured for this organization",
                to=message.to,
            )

        access_token, user_id = token_info

        # Refresh if token is stale (best-effort; proceed even if refresh fails)
        access_token = await self._refresh_microsoft_token_if_needed(
            access_token, user_id
        )

        graph_payload = self._build_graph_payload(message)

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{_GRAPH_API_BASE}/me/sendMail",
                    json=graph_payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )

            if response.status_code == 202:
                message_id = str(uuid.uuid4())
                logger.info(
                    "email.microsoft.sent message_id=%s to=%s subject=%r",
                    message_id,
                    message.to,
                    message.subject,
                )
                return EmailDeliveryResult(
                    message_id=message_id,
                    status=EmailStatus.SENT,
                    provider=EmailProvider.MICROSOFT,
                    to=message.to,
                )

            try:
                err_data = response.json()
                err_msg = (
                    err_data.get("error", {}).get("message")
                    or f"HTTP {response.status_code}"
                )
            except Exception:
                err_msg = f"HTTP {response.status_code}"

            logger.warning(
                "email.microsoft.failed status=%s error=%r to=%s",
                response.status_code,
                err_msg,
                message.to,
            )
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.MICROSOFT,
                error=f"Microsoft Graph {response.status_code}: {err_msg}",
                to=message.to,
            )

        except httpx.TimeoutException:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.MICROSOFT,
                error="Microsoft Graph request timed out",
                to=message.to,
            )
        except Exception as exc:
            logger.error("email.microsoft.exception: %s", exc)
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.MICROSOFT,
                error=str(exc),
                to=message.to,
            )

    def _fetch_microsoft_token(
        self, org_id: str
    ) -> Optional[tuple[str, int]]:
        """
        Blocking DB call — run in executor.

        Returns (access_token, user_integration_id) for the first active
        Microsoft integration belonging to any user in this organization,
        or None if none exist.
        """
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("""
                    SELECT ui.id, ui.access_token, ui.refresh_token, ui.expires_at
                    FROM user_integrations ui
                    JOIN users u ON u.id = ui.user_id
                    WHERE ui.provider = 'microsoft'
                      AND ui.access_token IS NOT NULL
                      AND CAST(u.organization_id AS TEXT) = :org_id
                    ORDER BY ui.updated_at DESC
                    LIMIT 1
                """),
                {"org_id": org_id},
            ).fetchone()

            if not row or not row.access_token:
                return None
            return row.access_token, row.id

        except Exception as exc:
            logger.error("email.microsoft.token_lookup_error: %s", exc)
            return None

    async def _refresh_microsoft_token_if_needed(
        self, access_token: str, integration_id: int
    ) -> str:
        """
        Attempt a token refresh if the stored token looks stale.
        Returns a valid access token (refreshed or original).
        """
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("""
                    SELECT access_token, refresh_token, expires_at
                    FROM user_integrations
                    WHERE id = :id
                """),
                {"id": integration_id},
            ).fetchone()

            if not row:
                return access_token

            now = datetime.now(timezone.utc)
            expires_at = row.expires_at
            if expires_at:
                # Make expires_at tz-aware if it isn't
                if expires_at.tzinfo is None:
                    from datetime import timezone as tz_module
                    import datetime as dt_module
                    expires_at = expires_at.replace(tzinfo=tz_module.utc)
                # Add a 5-minute buffer before expiry
                from datetime import timedelta
                if expires_at > now + timedelta(minutes=5):
                    return row.access_token  # Still valid

            if not row.refresh_token:
                return access_token

            client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

            if not client_id or not client_secret:
                return access_token

            token_url = _GRAPH_TOKEN_URL.format(tenant=tenant_id)

            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    token_url,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": row.refresh_token,
                        "grant_type": "refresh_token",
                        "scope": (
                            "Mail.Send Mail.ReadWrite Calendars.ReadWrite "
                            "User.Read offline_access"
                        ),
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if resp.status_code != 200:
                logger.warning(
                    "email.microsoft.token_refresh_failed status=%s",
                    resp.status_code,
                )
                return access_token

            tokens = resp.json()
            new_access = tokens["access_token"]
            new_refresh = tokens.get("refresh_token", row.refresh_token)
            from datetime import timedelta as _td

            new_expires = datetime.now(timezone.utc) + _td(
                seconds=tokens.get("expires_in", 3600)
            )

            self._db.execute(
                text("""
                    UPDATE user_integrations
                    SET access_token = :access_token,
                        refresh_token = :refresh_token,
                        expires_at = :expires_at,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": integration_id,
                    "access_token": new_access,
                    "refresh_token": new_refresh,
                    "expires_at": new_expires,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            self._db.commit()
            return new_access

        except Exception as exc:
            logger.error("email.microsoft.refresh_exception: %s", exc)
            return access_token

    def _build_graph_payload(self, message: EmailMessage) -> Dict[str, Any]:
        """Build Microsoft Graph /me/sendMail request body."""
        mail_msg: Dict[str, Any] = {
            "subject": message.subject,
            "body": {
                "contentType": "HTML" if message.html_body else "Text",
                "content": message.html_body or message.effective_text_body,
            },
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in message.to
            ],
        }

        if message.cc:
            mail_msg["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in message.cc
            ]
        if message.bcc:
            mail_msg["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in message.bcc
            ]
        if message.reply_to:
            mail_msg["replyTo"] = [
                {"emailAddress": {"address": message.reply_to}}
            ]

        # Custom headers (Graph does not surface arbitrary SMTP headers but
        # we include them in internetMessageHeaders if non-empty)
        if message.headers:
            mail_msg["internetMessageHeaders"] = [
                {"name": k, "value": v}
                for k, v in message.headers.items()
            ]

        # Attachments
        if message.attachments:
            graph_atts = []
            for att in message.attachments:
                try:
                    raw = _encode_attachment(att)
                    graph_atts.append(
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": att.filename,
                            "contentType": att.content_type,
                            "contentBytes": base64.b64encode(raw).decode("utf-8"),
                        }
                    )
                except Exception as exc:
                    logger.error(
                        "email.microsoft.attachment_error filename=%s error=%s",
                        att.filename,
                        exc,
                    )
            if graph_atts:
                mail_msg["attachments"] = graph_atts

        return {"message": mail_msg, "saveToSentItems": True}

    # ------------------------------------------------------------------
    # Provider: Gmail API
    # ------------------------------------------------------------------

    async def _send_via_gmail(
        self, message: EmailMessage, org_id: str
    ) -> EmailDeliveryResult:
        """
        Send via Gmail using a stored Google OAuth token.

        Uses the Gmail REST API directly (no google-api-python-client
        dependency in the hot path) to keep the service lightweight.
        """
        token_info = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_google_token, org_id
        )
        if not token_info:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.GMAIL,
                error="No Google OAuth token configured for this organization",
                to=message.to,
            )

        access_token, integration_id = token_info
        access_token = await self._refresh_google_token_if_needed(
            access_token, integration_id
        )

        raw_mime = self._build_mime_message(message)
        encoded = base64.urlsafe_b64encode(raw_mime).decode("utf-8")

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{_GOOGLE_GMAIL_BASE}/users/me/messages/send",
                    json={"raw": encoded},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )

            if response.status_code == 200:
                data = response.json()
                message_id = data.get("id") or str(uuid.uuid4())
                logger.info(
                    "email.gmail.sent message_id=%s to=%s subject=%r",
                    message_id,
                    message.to,
                    message.subject,
                )
                return EmailDeliveryResult(
                    message_id=message_id,
                    status=EmailStatus.SENT,
                    provider=EmailProvider.GMAIL,
                    to=message.to,
                )

            try:
                err_data = response.json()
                err_msg = (
                    err_data.get("error", {}).get("message")
                    or f"HTTP {response.status_code}"
                )
            except Exception:
                err_msg = f"HTTP {response.status_code}"

            logger.warning(
                "email.gmail.failed status=%s error=%r to=%s",
                response.status_code,
                err_msg,
                message.to,
            )
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.GMAIL,
                error=f"Gmail {response.status_code}: {err_msg}",
                to=message.to,
            )

        except httpx.TimeoutException:
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.GMAIL,
                error="Gmail request timed out",
                to=message.to,
            )
        except Exception as exc:
            logger.error("email.gmail.exception: %s", exc)
            return EmailDeliveryResult(
                status=EmailStatus.FAILED,
                provider=EmailProvider.GMAIL,
                error=str(exc),
                to=message.to,
            )

    def _fetch_google_token(
        self, org_id: str
    ) -> Optional[tuple[str, int]]:
        """
        Blocking DB call — run in executor.

        Returns (access_token, user_integration_id) for the first active
        Google integration belonging to any user in this organization.
        """
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("""
                    SELECT ui.id, ui.access_token, ui.refresh_token, ui.expires_at
                    FROM user_integrations ui
                    JOIN users u ON u.id = ui.user_id
                    WHERE ui.provider = 'google'
                      AND ui.access_token IS NOT NULL
                      AND CAST(u.organization_id AS TEXT) = :org_id
                    ORDER BY ui.updated_at DESC
                    LIMIT 1
                """),
                {"org_id": org_id},
            ).fetchone()

            if not row or not row.access_token:
                return None
            return row.access_token, row.id

        except Exception as exc:
            logger.error("email.gmail.token_lookup_error: %s", exc)
            return None

    async def _refresh_google_token_if_needed(
        self, access_token: str, integration_id: int
    ) -> str:
        """Refresh a Google OAuth token if it is within 5 minutes of expiry."""
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("""
                    SELECT access_token, refresh_token, expires_at
                    FROM user_integrations
                    WHERE id = :id
                """),
                {"id": integration_id},
            ).fetchone()

            if not row:
                return access_token

            now = datetime.now(timezone.utc)
            expires_at = row.expires_at
            if expires_at:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                from datetime import timedelta
                if expires_at > now + timedelta(minutes=5):
                    return row.access_token

            if not row.refresh_token:
                return access_token

            client_id = os.getenv("GOOGLE_CLIENT_ID", "")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

            if not client_id or not client_secret:
                return access_token

            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    _GOOGLE_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": row.refresh_token,
                        "grant_type": "refresh_token",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if resp.status_code != 200:
                logger.warning(
                    "email.gmail.token_refresh_failed status=%s",
                    resp.status_code,
                )
                return access_token

            tokens = resp.json()
            new_access = tokens["access_token"]
            from datetime import timedelta as _td

            new_expires = datetime.now(timezone.utc) + _td(
                seconds=tokens.get("expires_in", 3600)
            )

            self._db.execute(
                text("""
                    UPDATE user_integrations
                    SET access_token = :access_token,
                        expires_at = :expires_at,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": integration_id,
                    "access_token": new_access,
                    "expires_at": new_expires,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            self._db.commit()
            return new_access

        except Exception as exc:
            logger.error("email.gmail.refresh_exception: %s", exc)
            return access_token

    def _build_mime_message(self, message: EmailMessage) -> bytes:
        """
        Build a raw RFC 2822 / MIME message suitable for Gmail's
        messages.send endpoint (base64url encoded after this call).
        """
        has_attachments = bool(message.attachments)

        if has_attachments:
            outer = MIMEMultipart("mixed")
            if message.html_body:
                alt = MIMEMultipart("alternative")
                if message.text_body:
                    alt.attach(MIMEText(message.text_body, "plain", "utf-8"))
                alt.attach(MIMEText(message.html_body, "html", "utf-8"))
                outer.attach(alt)
            else:
                outer.attach(MIMEText(message.effective_text_body, "plain", "utf-8"))

            for att in (message.attachments or []):
                try:
                    raw = _encode_attachment(att)
                    part = MIMEApplication(raw, Name=att.filename)
                    part["Content-Disposition"] = (
                        f'attachment; filename="{att.filename}"'
                    )
                    part["Content-Type"] = att.content_type
                    outer.attach(part)
                except Exception as exc:
                    logger.error(
                        "email.gmail.attachment_error filename=%s error=%s",
                        att.filename,
                        exc,
                    )
        elif message.html_body:
            outer = MIMEMultipart("alternative")  # type: ignore[assignment]
            if message.text_body:
                outer.attach(MIMEText(message.text_body, "plain", "utf-8"))
            outer.attach(MIMEText(message.html_body, "html", "utf-8"))
        else:
            outer = MIMEText(message.effective_text_body, "plain", "utf-8")  # type: ignore[assignment]

        # Addressing
        outer["To"] = ", ".join(message.to)
        outer["Subject"] = message.subject
        if message.from_email:
            from_header = (
                f"{message.from_name} <{message.from_email}>"
                if message.from_name
                else message.from_email
            )
            outer["From"] = from_header
        if message.cc:
            outer["Cc"] = ", ".join(message.cc)
        if message.reply_to:
            outer["Reply-To"] = message.reply_to

        # Extra headers
        for k, v in (message.headers or {}).items():
            outer[k] = v

        return outer.as_bytes()

    # ------------------------------------------------------------------
    # Dry-run fallback
    # ------------------------------------------------------------------

    def _dry_run_result(self, message: EmailMessage) -> EmailDeliveryResult:
        """Return a DRY_RUN result when no provider is available."""
        logger.info(
            "email.dry_run to=%s subject=%r (no provider configured)",
            message.to,
            message.subject,
        )
        return EmailDeliveryResult(
            message_id=f"dry-run-{uuid.uuid4()}",
            status=EmailStatus.DRY_RUN,
            provider=EmailProvider.NONE,
            to=message.to,
        )

    # ------------------------------------------------------------------
    # Org config loader
    # ------------------------------------------------------------------

    async def _load_org_config(self, org_id: str) -> EmailDeliveryConfig:
        """
        Load per-org email delivery config from the organizations.settings
        JSON column (key ``"email_delivery"``).

        Falls back to self._default_config when:
        - org_id is "__global__"
        - the org is not found
        - the settings column has no "email_delivery" key
        """
        if org_id == "__global__":
            return self._default_config

        try:
            config_data = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_org_config_sync, org_id
            )
            if config_data:
                return EmailDeliveryConfig(**config_data)
        except Exception as exc:
            logger.warning("email.config_load_error org=%s: %s", org_id, exc)

        return self._default_config

    def _fetch_org_config_sync(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Blocking DB read — run in executor."""
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("""
                    SELECT settings
                    FROM organizations
                    WHERE id = :org_id
                    LIMIT 1
                """),
                {"org_id": org_id},
            ).fetchone()

            if not row or not row.settings:
                return None

            settings: Dict[str, Any] = row.settings
            return settings.get("email_delivery")

        except Exception as exc:
            logger.error("email.org_settings_fetch_error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Structured delivery logging
    # ------------------------------------------------------------------

    def _log_delivery(
        self, result: EmailDeliveryResult, message: EmailMessage
    ) -> None:
        """Emit a structured log entry for observability / audit trail."""
        level = logging.INFO if result.success else logging.ERROR
        logger.log(
            level,
            "email.delivery "
            "status=%s provider=%s message_id=%s "
            "to=%s subject=%r org=%s user=%s "
            "providers_tried=%s error=%s",
            result.status.value,
            result.provider.value,
            result.message_id,
            result.to,
            message.subject,
            message.organization_id,
            message.user_id,
            result.providers_tried,
            result.error,
        )
