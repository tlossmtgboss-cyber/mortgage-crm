"""
Webhook Signature Verification Middleware
=========================================
Verifies webhook signatures from external services (Google Calendar,
Microsoft Graph/Outlook, Telnyx, Vapi, and generic HMAC) to prevent
unauthorized POST requests to push notification endpoints.

Usage as FastAPI dependencies:

    from middleware.webhook_verification import (
        require_google_calendar_webhook,
        require_outlook_webhook,
        require_telnyx_webhook,
        require_vapi_webhook,
    )

    @router.post("/webhook/google")
    async def handle_google_webhook(
        request: Request,
        _: bool = Depends(require_google_calendar_webhook),
    ):
        ...

    @router.post("/webhook/outlook")
    async def handle_outlook_webhook(
        request: Request,
        _: bool = Depends(require_outlook_webhook),
    ):
        ...

    @router.post("/webhook/telnyx")
    async def handle_telnyx_webhook(
        request: Request,
        body: bytes = Depends(require_telnyx_webhook),
    ):
        # body is the verified raw body bytes
        ...

    @router.post("/webhook/vapi")
    async def handle_vapi_webhook(
        request: Request,
        body: bytes = Depends(require_vapi_webhook),
    ):
        # body is the verified raw body bytes
        ...

Environment variables:
    GOOGLE_CALENDAR_WEBHOOK_TOKEN  - Token set when creating a Google Calendar watch
    GRAPH_WEBHOOK_SECRET           - clientState set when creating an Outlook/Graph subscription
    WEBHOOK_SECRET                 - Fallback secret for Graph webhooks
    TELNYX_PUBLIC_KEY              - Ed25519 public key for Telnyx webhook verification
    VAPI_WEBHOOK_SECRET            - Shared secret for Vapi webhook verification
"""

import hmac
import hashlib
import logging
import os
import time
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timestamp tolerance for replay protection (seconds)
# ---------------------------------------------------------------------------
WEBHOOK_TIMESTAMP_TOLERANCE = int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE", "300"))  # 5 minutes


class WebhookVerifier:
    """Verifies webhook signatures from external services."""

    # ------------------------------------------------------------------
    # Google Calendar push notifications
    # ------------------------------------------------------------------
    @staticmethod
    async def verify_google_calendar(request: Request) -> bool:
        """
        Google Calendar push notifications include:
        - X-Goog-Channel-ID: channel identifier we created
        - X-Goog-Channel-Token: token we set when creating the watch
        - X-Goog-Resource-State: sync | exists | not_exists

        Verification strategy:
        1. Require both Channel-ID and Channel-Token headers.
        2. Compare Channel-Token against our stored secret using
           constant-time comparison to prevent timing attacks.
        3. On initial sync notifications (resource_state == "sync"),
           still verify but allow gracefully.

        The expected token is read from the GOOGLE_CALENDAR_WEBHOOK_TOKEN
        environment variable. When using per-user watch channels, the
        token can encode the user_id for lookup (e.g. "user_42:<secret>").
        """
        channel_id = request.headers.get("X-Goog-Channel-ID")
        channel_token = request.headers.get("X-Goog-Channel-Token")
        resource_state = request.headers.get("X-Goog-Resource-State", "")

        if not channel_id:
            logger.warning(
                "Google Calendar webhook missing X-Goog-Channel-ID from %s",
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=403, detail="Missing Google webhook channel ID")

        if not channel_token:
            logger.warning(
                "Google Calendar webhook missing X-Goog-Channel-Token from %s",
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=403, detail="Missing Google webhook channel token")

        expected_token = os.getenv("GOOGLE_CALENDAR_WEBHOOK_TOKEN")
        if not expected_token:
            logger.error(
                "GOOGLE_CALENDAR_WEBHOOK_TOKEN not configured - rejecting webhook"
            )
            raise HTTPException(
                status_code=503,
                detail="Google Calendar webhook not configured",
            )

        # The channel_token may be a compound value like "user_42:<secret>".
        # Extract the secret portion for comparison. If the expected token
        # contains no colon, compare the full value.
        token_to_verify = channel_token
        if ":" in channel_token and ":" not in expected_token:
            # Per-user token format: strip the user prefix
            token_to_verify = channel_token.rsplit(":", 1)[-1]

        if not hmac.compare_digest(token_to_verify, expected_token):
            logger.warning(
                "Invalid Google Calendar webhook token for channel %s from %s",
                channel_id,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=403, detail="Invalid Google webhook token")

        logger.info(
            "Google Calendar webhook verified: channel=%s state=%s",
            channel_id, resource_state,
        )
        return True

    # ------------------------------------------------------------------
    # Microsoft Graph / Outlook push notifications
    # ------------------------------------------------------------------
    @staticmethod
    async def verify_outlook(
        request: Request,
        validation_token: Optional[str] = None,
    ) -> bool:
        """
        Microsoft Graph webhook subscriptions:
        1. On subscription creation, Graph sends a validation request with
           ?validationToken=<token>. The endpoint MUST echo that token back
           as plain text with 200 OK. This is handled by the route itself
           before this verifier runs (see require_outlook_webhook).
        2. On actual notifications, the JSON payload includes a clientState
           field that must match the secret we set during subscription
           creation.

        The expected secret comes from GRAPH_WEBHOOK_SECRET (fallback:
        WEBHOOK_SECRET).
        """
        expected_secret = os.getenv(
            "GRAPH_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET")
        )

        if not expected_secret:
            logger.error(
                "GRAPH_WEBHOOK_SECRET not configured - rejecting webhook"
            )
            raise HTTPException(
                status_code=503,
                detail="Outlook webhook not configured",
            )

        # For notification payloads, verify clientState in the body.
        # We read the body and validate each notification's clientState.
        try:
            body = await request.json()
        except Exception as e:
            logger.error("Failed to parse Outlook webhook body: %s", e)
            raise HTTPException(status_code=400, detail="Invalid webhook payload")

        notifications = body.get("value", [])
        if not notifications:
            logger.warning(
                "Outlook webhook received empty notification list from %s",
                request.client.host if request.client else "unknown",
            )
            # Empty payloads are suspicious but not necessarily malicious.
            # Return True to let the route handler decide.
            return True

        # Verify clientState on ALL notifications. If any fail, reject.
        for notification in notifications:
            client_state = notification.get("clientState")
            if not client_state:
                logger.warning(
                    "Outlook webhook notification missing clientState for "
                    "subscription %s",
                    notification.get("subscriptionId", "unknown"),
                )
                raise HTTPException(
                    status_code=403,
                    detail="Missing clientState in notification",
                )

            if not hmac.compare_digest(client_state, expected_secret):
                logger.warning(
                    "Invalid Outlook clientState for subscription %s from %s",
                    notification.get("subscriptionId", "unknown"),
                    request.client.host if request.client else "unknown",
                )
                raise HTTPException(
                    status_code=403,
                    detail="Invalid webhook clientState",
                )

        logger.info(
            "Outlook webhook verified: %d notifications", len(notifications)
        )
        return True

    # ------------------------------------------------------------------
    # Generic HMAC-SHA256 verification
    # ------------------------------------------------------------------
    @staticmethod
    async def verify_generic_hmac(
        request: Request,
        secret: str,
        header: str = "X-Webhook-Signature",
        algorithm: str = "sha256",
    ) -> bool:
        """
        Generic HMAC verification for any webhook provider.

        Expects the signature in the specified header as either:
          - "sha256=<hex_digest>"
          - "<hex_digest>" (bare)

        Uses constant-time comparison to prevent timing attacks.
        """
        signature = request.headers.get(header)
        if not signature:
            logger.warning(
                "Webhook missing %s header from %s",
                header,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(
                status_code=403,
                detail=f"Missing {header}",
            )

        body = await request.body()

        if algorithm == "sha256":
            digest = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
        elif algorithm == "sha1":
            digest = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha1
            ).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Handle "sha256=<hex>" prefix format
        expected_prefixed = f"{algorithm}={digest}"
        # Compare against both prefixed and bare forms
        if not (
            hmac.compare_digest(signature, expected_prefixed)
            or hmac.compare_digest(signature, digest)
        ):
            logger.warning(
                "Invalid webhook signature in %s from %s",
                header,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(
                status_code=403,
                detail="Invalid webhook signature",
            )

        return True

    # ------------------------------------------------------------------
    # Telnyx webhook verification (Ed25519)
    # ------------------------------------------------------------------
    @staticmethod
    async def verify_telnyx(request: Request) -> bytes:
        """
        Verify a Telnyx webhook using Ed25519 signature verification.

        Telnyx signs webhooks with Ed25519.  The signed payload is
        ``timestamp + "." + raw_body``.  Headers:

        - ``telnyx-signature-ed25519``: base64-encoded Ed25519 signature
        - ``telnyx-timestamp``: UNIX epoch seconds when Telnyx signed

        Verification is **fail-closed** in production/staging when
        ``TELNYX_PUBLIC_KEY`` is not set — webhooks are rejected.
        In development, webhooks are allowed through with a warning.
        When the key IS set, verification is always fail-closed.

        Replay protection rejects payloads whose timestamp is older than
        ``WEBHOOK_TIMESTAMP_TOLERANCE`` seconds (default 300 = 5 min).

        Returns the raw request body bytes so the caller can parse JSON
        without reading the body a second time.
        """
        public_key = os.getenv("TELNYX_PUBLIC_KEY")
        body = await request.body()

        if not public_key:
            env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENVIRONMENT", "")).lower()
            if env in ("production", "staging"):
                logger.error(
                    "TELNYX_PUBLIC_KEY not configured in %s — rejecting webhook "
                    "(set the key to enable Ed25519 verification)", env,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Telnyx webhook verification not configured",
                )
            # Development/local: warn but allow through for testing
            logger.warning(
                "TELNYX_PUBLIC_KEY not configured — allowing webhook without "
                "signature verification (development mode)"
            )
            return body

        signature = request.headers.get("telnyx-signature-ed25519", "")
        timestamp = request.headers.get("telnyx-timestamp", "")
        source_ip = request.client.host if request.client else "unknown"

        if not signature or not timestamp:
            logger.warning(
                "Telnyx webhook missing signature headers from %s", source_ip,
            )
            raise HTTPException(status_code=401, detail="Missing Telnyx signature headers")

        # -- Replay protection ------------------------------------------------
        try:
            ts = int(timestamp)
            now = int(time.time())
            if abs(now - ts) > WEBHOOK_TIMESTAMP_TOLERANCE:
                logger.warning(
                    "Telnyx webhook timestamp too old/future: ts=%d now=%d diff=%ds from %s",
                    ts, now, abs(now - ts), source_ip,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Telnyx webhook timestamp out of tolerance",
                )
        except (ValueError, TypeError):
            logger.warning(
                "Telnyx webhook invalid timestamp value: %r from %s",
                timestamp, source_ip,
            )
            raise HTTPException(status_code=401, detail="Invalid Telnyx timestamp")

        # -- Ed25519 signature verification -----------------------------------
        # Fail closed: signature must validate. IP-based trust is unreliable
        # behind Railway's reverse proxy and has been removed.
        try:
            from telephony.providers.telnyx.webhooks import validate_telnyx_webhook
            if not validate_telnyx_webhook(body, signature, timestamp, public_key):
                logger.warning(
                    "Invalid Telnyx Ed25519 signature from %s", source_ip,
                )
                raise HTTPException(status_code=401, detail="Invalid Telnyx webhook signature")
        except ImportError:
            logger.error(
                "Telnyx webhook validation module not available — "
                "rejecting webhook (install PyNaCl)"
            )
            raise HTTPException(
                status_code=503,
                detail="Telnyx webhook verification unavailable",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Telnyx webhook signature validation error: %s", e)
            raise HTTPException(
                status_code=401,
                detail="Telnyx webhook signature validation failed",
            )

        return body

    # ------------------------------------------------------------------
    # Vapi webhook verification (shared secret / HMAC-SHA256)
    # ------------------------------------------------------------------
    @staticmethod
    async def verify_vapi(request: Request) -> bytes:
        """
        Verify a Vapi webhook using the shared secret.

        Vapi supports two authentication modes for server URLs:

        1. **Shared secret** (``X-Vapi-Secret`` header) — the secret is set
           when configuring the assistant's ``serverUrlSecret``.  The header
           value is compared directly against ``VAPI_WEBHOOK_SECRET``.

        2. **HMAC-SHA256** (``x-vapi-signature`` header) — the header
           contains the hex-encoded HMAC-SHA256 of the raw request body
           using ``VAPI_WEBHOOK_SECRET`` as the key.

        This method checks both header formats for maximum compatibility.

        Verification is **fail-closed** in production/staging when
        ``VAPI_WEBHOOK_SECRET`` is not set — webhooks are rejected.
        In development, webhooks are allowed through without verification.

        Returns the raw request body bytes so the caller can parse JSON
        without reading the body a second time.
        """
        secret = os.getenv("VAPI_WEBHOOK_SECRET", "")
        body = await request.body()
        source_ip = request.client.host if request.client else "unknown"

        if not secret:
            env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENVIRONMENT", "")).lower()
            if env in ("production", "staging"):
                logger.error(
                    "VAPI_WEBHOOK_SECRET not configured in %s — rejecting Vapi "
                    "webhook (set secret to enable verification)", env,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Vapi webhook verification not configured",
                )
            # Development/local: warn but allow through for testing
            logger.warning(
                "VAPI_WEBHOOK_SECRET not configured — allowing Vapi "
                "webhook without verification (development mode)"
            )
            return body

        # --- Mode 1: X-Vapi-Secret header (direct secret comparison) --------
        vapi_secret_header = request.headers.get("X-Vapi-Secret", "")
        if vapi_secret_header:
            if hmac.compare_digest(vapi_secret_header, secret):
                return body
            logger.warning(
                "Invalid Vapi X-Vapi-Secret from %s", source_ip,
            )
            raise HTTPException(status_code=401, detail="Invalid Vapi webhook authentication")

        # --- Mode 2: x-vapi-signature header (HMAC-SHA256) -------------------
        vapi_signature = request.headers.get("x-vapi-signature", "")
        if vapi_signature:
            expected = hmac.new(
                secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(vapi_signature, expected):
                return body
            logger.warning(
                "Invalid Vapi HMAC signature from %s", source_ip,
            )
            raise HTTPException(status_code=401, detail="Invalid Vapi webhook signature")

        # --- No recognized auth header present -------------------------------
        logger.warning(
            "Vapi webhook missing authentication header (X-Vapi-Secret or "
            "x-vapi-signature) from %s", source_ip,
        )
        raise HTTPException(status_code=401, detail="Missing Vapi webhook authentication")


# ======================================================================
# FastAPI Dependencies
# ======================================================================

async def require_google_calendar_webhook(request: Request) -> bool:
    """
    FastAPI dependency that verifies incoming Google Calendar push
    notification webhooks.

    Usage:
        @router.post("/webhook/google-calendar")
        async def handler(
            request: Request,
            _: bool = Depends(require_google_calendar_webhook),
        ):
            ...
    """
    return await WebhookVerifier.verify_google_calendar(request)


async def require_outlook_webhook(
    request: Request,
    validationToken: Optional[str] = Query(None),
) -> Optional[PlainTextResponse]:
    """
    FastAPI dependency that verifies incoming Microsoft Graph / Outlook
    push notification webhooks.

    Handles the special validation handshake: if validationToken is present
    in the query string, this is a subscription validation request and the
    route should echo the token back. The dependency returns a
    PlainTextResponse in that case, which the route handler should check.

    For normal notifications, verifies clientState and returns True.

    Usage:
        @router.post("/webhook/outlook-calendar")
        async def handler(
            request: Request,
            verification = Depends(require_outlook_webhook),
        ):
            # Handle validation handshake
            if isinstance(verification, PlainTextResponse):
                return verification
            # ... process notification
    """
    if validationToken:
        # This is a subscription validation request from Microsoft Graph.
        # We must echo the token back as plain text within 10 seconds.
        logger.info("Outlook webhook subscription validation request received")
        return PlainTextResponse(
            content=validationToken, media_type="text/plain"
        )

    await WebhookVerifier.verify_outlook(request)
    return True


async def require_generic_hmac_webhook(request: Request) -> bool:
    """
    FastAPI dependency for generic HMAC-SHA256 webhook verification.
    Uses WEBHOOK_HMAC_SECRET environment variable.

    Usage:
        @router.post("/webhook/external")
        async def handler(
            request: Request,
            _: bool = Depends(require_generic_hmac_webhook),
        ):
            ...
    """
    secret = os.getenv("WEBHOOK_HMAC_SECRET")
    if not secret:
        logger.error("WEBHOOK_HMAC_SECRET not configured")
        raise HTTPException(
            status_code=503, detail="Webhook not configured"
        )
    return await WebhookVerifier.verify_generic_hmac(request, secret)


async def require_telnyx_webhook(request: Request) -> bytes:
    """
    FastAPI dependency that verifies incoming Telnyx webhook signatures
    using Ed25519.

    Returns the raw request body bytes.  The caller should parse JSON
    from these bytes instead of calling ``request.json()`` again (the
    body stream is already consumed).

    Verification is **skipped** (with a debug log) when the
    ``TELNYX_PUBLIC_KEY`` env var is not set, so local development works
    without the key.  In ``production`` / ``staging`` it is fail-closed.

    Usage:
        @router.post("/webhook/telnyx")
        async def handler(
            request: Request,
            raw_body: bytes = Depends(require_telnyx_webhook),
        ):
            payload = json.loads(raw_body)
            ...
    """
    return await WebhookVerifier.verify_telnyx(request)


async def require_vapi_webhook(request: Request) -> bytes:
    """
    FastAPI dependency that verifies incoming Vapi webhook requests.

    Supports two authentication modes:
    - ``X-Vapi-Secret`` header (shared secret comparison)
    - ``x-vapi-signature`` header (HMAC-SHA256 of the body)

    Returns the raw request body bytes.  The caller should parse JSON
    from these bytes instead of calling ``request.json()`` again.

    Verification is **fail-closed** in production/staging when
    ``VAPI_WEBHOOK_SECRET`` is not set — webhooks are rejected.
    In development, webhooks are allowed through with a warning.
    When the secret IS set, verification is always fail-closed.

    Usage:
        @router.post("/webhook/vapi")
        async def handler(
            request: Request,
            raw_body: bytes = Depends(require_vapi_webhook),
        ):
            payload = json.loads(raw_body)
            ...
    """
    return await WebhookVerifier.verify_vapi(request)
