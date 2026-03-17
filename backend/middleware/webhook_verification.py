"""
Webhook Signature Verification Middleware
=========================================
Verifies webhook signatures from external services (Google Calendar,
Microsoft Graph/Outlook, and generic HMAC) to prevent unauthorized
POST requests to push notification endpoints.

Usage as FastAPI dependencies:

    from middleware.webhook_verification import (
        require_google_calendar_webhook,
        require_outlook_webhook,
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

Environment variables:
    GOOGLE_CALENDAR_WEBHOOK_TOKEN  - Token set when creating a Google Calendar watch
    GRAPH_WEBHOOK_SECRET           - clientState set when creating an Outlook/Graph subscription
    WEBHOOK_SECRET                 - Fallback secret for Graph webhooks
"""

import hmac
import hashlib
import logging
import os
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)


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
