"""
Scheduler input sanitization and validation — text cleaning, URL/phone validation,
public error masking, and Cloudflare Turnstile CAPTCHA verification.
"""

from fastapi import HTTPException
from typing import Optional
import hashlib
import logging
import os
import time
import asyncio

try:
    import nh3
except ImportError:
    raise ImportError(
        "nh3 is required for HTML sanitization. Install with: pip install nh3"
    )

logger = logging.getLogger(__name__)


# ============================================================================
# TEXT SANITIZATION
# ============================================================================

def _sanitize_text(value: Optional[str]) -> Optional[str]:
    """Sanitize user-supplied text input, stripping all HTML."""
    if value is None:
        return None
    return nh3.clean(value, tags=set())


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
    except Exception as e:
        logger.debug(f"URL validation failed for input: {e}")
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
        # NANP area code validation for US numbers (+1NXXNXXXXXX)
        cleaned = phone.strip()
        if cleaned.startswith("+1") and len(cleaned) == 12:
            area_code = cleaned[2:5]
            # NANP: first digit must be 2-9
            if area_code[0] in "01":
                raise HTTPException(
                    status_code=400,
                    detail="Invalid phone number: invalid area code."
                )
            # Reject N11 service codes (211, 311, 411, 511, 611, 711, 811, 911)
            if area_code[1:] == "11":
                raise HTTPException(
                    status_code=400,
                    detail="Invalid phone number: invalid area code."
                )
            # Reject 555 (reserved for fictional use)
            if area_code == "555":
                raise HTTPException(
                    status_code=400,
                    detail="Invalid phone number: invalid area code."
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

# Turnstile token replay prevention
# Tokens are hashed (SHA-256) before storage to avoid holding raw CAPTCHA tokens in memory.
_TURNSTILE_TOKEN_TTL_SECONDS = 300  # Turnstile tokens are valid for ~5 minutes
_TURNSTILE_TOKEN_MAX_CACHE = 10000

# --- Redis-backed replay cache (cross-worker safe) ---
_redis_client = None
_redis_available = False

try:
    import redis as _redis_module
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        _redis_client = _redis_module.from_url(
            _redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Verify connectivity at import time with a lightweight ping
        _redis_client.ping()
        _redis_available = True
        logger.info("Turnstile replay cache: using Redis (cross-worker)")
except Exception as _redis_err:
    _redis_available = False
    _redis_client = None
    logger.info(f"Turnstile replay cache: Redis unavailable ({_redis_err}), using in-memory fallback")


# --- In-memory TTL dict fallback (single-worker only) ---
# LIMITATION: This fallback only prevents replays within the same process.
# In multi-worker deployments without Redis, a token validated by worker A
# can still be replayed against worker B. Use Redis for production.
_used_turnstile_tokens: dict = {}  # {token_hash: expiry_timestamp}
_turnstile_lock = asyncio.Lock()


def _hash_token(token: str) -> str:
    """Hash a Turnstile token so we never store the raw value."""
    return hashlib.sha256(token.encode()).hexdigest()


def _evict_expired_tokens() -> None:
    """Remove expired entries from the in-memory cache. Caller must hold _turnstile_lock."""
    now = time.monotonic()
    expired_keys = [k for k, exp in _used_turnstile_tokens.items() if exp <= now]
    for k in expired_keys:
        del _used_turnstile_tokens[k]


def _evict_lru_if_full() -> None:
    """If cache exceeds max size after expiry eviction, drop oldest entries. Caller must hold _turnstile_lock."""
    if len(_used_turnstile_tokens) >= _TURNSTILE_TOKEN_MAX_CACHE:
        # Sort by expiry (earliest first) and drop the oldest 20%
        sorted_keys = sorted(_used_turnstile_tokens, key=lambda k: _used_turnstile_tokens[k])
        drop_count = max(1, len(sorted_keys) // 5)
        for k in sorted_keys[:drop_count]:
            del _used_turnstile_tokens[k]


async def _check_turnstile_replay(token: str) -> bool:
    """
    Check if a Turnstile token has already been used. Returns False if replay detected.
    Uses Redis with SETNX + TTL when available; falls back to an in-memory TTL dict.
    """
    token_hash = _hash_token(token)

    # --- Redis path ---
    if _redis_available and _redis_client is not None:
        try:
            cache_key = f"turnstile:replay:{token_hash}"
            # SETNX returns True only if the key was newly set (first use)
            was_set = _redis_client.set(
                cache_key, "1", nx=True, ex=_TURNSTILE_TOKEN_TTL_SECONDS
            )
            if not was_set:
                return False  # Key already existed — replay
            return True
        except Exception as e:
            # Redis failure: fall through to in-memory as a safety net
            logger.warning(f"Redis replay check failed, falling back to in-memory: {e}")

    # --- In-memory fallback path ---
    now = time.monotonic()
    async with _turnstile_lock:
        _evict_expired_tokens()

        if token_hash in _used_turnstile_tokens:
            return False  # Replay detected

        _evict_lru_if_full()
        _used_turnstile_tokens[token_hash] = now + _TURNSTILE_TOKEN_TTL_SECONDS
        return True


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
            if not await _check_turnstile_replay(token):
                logger.warning("Turnstile token replay detected — rejecting reused token")
                return False
            return True
        logger.warning(f"Turnstile verification failed: {result.get('error-codes', [])}")
        return False
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return False
