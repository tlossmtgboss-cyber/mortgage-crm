"""
Webhook Signature Verification Utilities
Perennia AI - Centralized webhook security

Provides fail-closed verification for:
- Twilio webhooks (X-Twilio-Signature with RequestValidator)
- Internal webhooks (shared secret via X-Webhook-Secret header)
"""

import os
import hmac
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


async def verify_twilio_webhook(request: Request) -> None:
    """
    Verify Twilio X-Twilio-Signature header. Raises HTTPException(401) on failure.

    FAIL-CLOSED: If TWILIO_AUTH_TOKEN is not set or twilio package is missing,
    the webhook is rejected.
    """
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not auth_token:
        logger.error("TWILIO_AUTH_TOKEN not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook verification not configured")

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        logger.error("twilio package not installed — cannot verify webhook signature")
        raise HTTPException(status_code=500, detail="Webhook verification unavailable")

    try:
        validator = RequestValidator(auth_token)

        # Get form data for signature validation
        form_data = await request.form()
        params = {k: v for k, v in form_data.items()}

        # Reconstruct the URL Twilio used to sign
        url = str(request.url)

        if not validator.validate(url, params, signature):
            logger.warning(f"Invalid Twilio signature for {request.url.path}")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio signature validation error: {e}")
        raise HTTPException(status_code=401, detail="Webhook signature validation failed")


def verify_webhook_secret(request: Request) -> None:
    """
    Verify a shared secret sent via X-Webhook-Secret header.
    Used for internal JSON webhooks that aren't called directly by Twilio.

    FAIL-CLOSED: If WEBHOOK_SECRET is not configured, the webhook is rejected.
    """
    expected_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if not expected_secret:
        logger.error("WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook verification not configured")

    provided_secret = request.headers.get("X-Webhook-Secret", "")
    if not provided_secret:
        logger.warning(f"Missing X-Webhook-Secret header for {request.url.path}")
        raise HTTPException(status_code=401, detail="Missing webhook secret")

    if not hmac.compare_digest(provided_secret, expected_secret):
        logger.warning(f"Invalid webhook secret for {request.url.path}")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
