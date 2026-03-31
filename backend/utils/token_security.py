"""
Token Security — Constant-time token comparison and secure generation.

Usage:
    from utils.token_security import safe_token_compare, generate_invite_token
"""

import hmac
import secrets


def safe_token_compare(stored_token: str, provided_token: str) -> bool:
    """
    Constant-time comparison of two tokens to prevent timing attacks.
    Returns True if tokens match, False otherwise.
    Both arguments are coerced to strings; None is treated as empty string.
    """
    return hmac.compare_digest(
        (stored_token or "").encode("utf-8"),
        (provided_token or "").encode("utf-8"),
    )


def generate_invite_token() -> str:
    """Generate a cryptographically secure invitation token (32 bytes, URL-safe base64)."""
    return secrets.token_urlsafe(32)
