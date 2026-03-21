"""
Scheduler input sanitization and validation — text cleaning, URL/phone validation,
public error masking, and Cloudflare Turnstile CAPTCHA verification.
"""

from fastapi import HTTPException
from typing import Optional
import html
import logging
import os

try:
    import nh3
except ImportError:
    nh3 = None

logger = logging.getLogger(__name__)


# ============================================================================
# TEXT SANITIZATION
# ============================================================================

def _sanitize_text(value: Optional[str]) -> Optional[str]:
    """Sanitize user-supplied text input, stripping all HTML."""
    if value is None:
        return None
    if nh3:
        return nh3.clean(value, tags=set())
    # Fallback: html.escape
    return html.escape(value)


def _mask_email(email: Optional[str]) -> str:
    """Mask email for logging: j***@example.com"""
    if not email or '@' not in email:
        return '***'
    local, domain = email.split('@', 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _validate_url(value: Optional[str]) -> Optional[str]:
    """Validate URL has safe scheme (http/https only). Returns None for unsafe URLs."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    from urllib.parse import urlparse
    try:
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https'):
            logger.warning(f"Rejected URL with unsafe scheme: {parsed.scheme}")
            return None
        return value
    except Exception:
        return None


def _validate_phone(phone: Optional[str]) -> Optional[str]:
    """
    Validate and normalize phone numbers for public booking.
    Accepts E.164 (+1XXXXXXXXXX) or common US formats (XXX-XXX-XXXX, (XXX) XXX-XXXX, etc.).
    Returns the cleaned phone string, or raises HTTPException for invalid formats.
    """
    import re
    if phone is None or phone.strip() == "":
        return None
    # Strip whitespace and common formatting chars for digit counting
    digits_only = re.sub(r'[^\d]', '', phone.strip())
    # Accept 10-digit US numbers or 11-digit with leading 1, or E.164 with +
    if phone.strip().startswith('+'):
        # E.164: must be + followed by 10-15 digits
        if not re.match(r'^\+\d{10,15}$', phone.strip()):
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Please use a valid phone number."
            )
    elif len(digits_only) == 10:
        pass  # Standard US 10-digit
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        pass  # US with leading country code
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number format. Please use a valid phone number."
        )
    return phone.strip()


def _sanitize_public_error(status_code: int, detail: str) -> str:
    """
    Map internal error details to safe, user-friendly messages for public endpoints.
    Prevents leaking SQL errors, stack traces, model names, or internal state.
    """
    safe_messages = {
        400: "Invalid booking request. Please check your information and try again.",
        403: "This action is not allowed.",
        404: "Booking page not found.",
        409: "This time slot has already been booked. Please select another time.",
        410: "This booking link is no longer available.",
        429: "Too many requests. Please wait a moment and try again.",
    }
    if status_code in safe_messages:
        return safe_messages[status_code]
    # For all 5xx and unknown codes, return a generic message
    return "Something went wrong. Please try again later."


# ============================================================================
# CLOUDFLARE TURNSTILE CAPTCHA
# ============================================================================

_TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
_RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
_IS_PRODUCTION = _RAILWAY_ENVIRONMENT.lower() == "production"

if _IS_PRODUCTION and not _TURNSTILE_SECRET_KEY:
    logger.critical(
        "TURNSTILE_SECRET_KEY is not set in production! "
        "Public booking endpoints will REJECT all requests until this is configured. "
        "Set the TURNSTILE_SECRET_KEY environment variable with your Cloudflare Turnstile secret."
    )


_turnstile_client = None


def _get_turnstile_client():
    global _turnstile_client
    if _turnstile_client is None:
        import httpx
        _turnstile_client = httpx.AsyncClient(timeout=10.0)
    return _turnstile_client


async def _verify_turnstile_token(token: str) -> bool:
    """
    Verify a Cloudflare Turnstile token by POSTing to Cloudflare's siteverify endpoint.
    Returns True if the token is valid, False otherwise.

    Production safety: if TURNSTILE_SECRET_KEY is not set, returns False in production
    (rejecting the request) and True in dev/test (allowing bypass for local development).
    """
    if not _TURNSTILE_SECRET_KEY:
        if _IS_PRODUCTION:
            logger.error("Turnstile verification rejected: TURNSTILE_SECRET_KEY not configured in production")
            return False
        else:
            logger.debug("Turnstile verification skipped: TURNSTILE_SECRET_KEY not set (dev mode)")
            return True

    try:
        client = _get_turnstile_client()
        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": _TURNSTILE_SECRET_KEY,
                "response": token,
            },
        )
        result = response.json()
        if result.get("success"):
            return True
        logger.warning(f"Turnstile verification failed: {result.get('error-codes', [])}")
        return False
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return False
