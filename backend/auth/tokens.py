"""
JWT Token Management

Provides secure token creation and validation with:
- RS256 asymmetric key support (recommended for production)
- HS256 symmetric key support (for development/simple deployments)
- Proper JWT claims (iss, aud, jti, sub, exp, iat)
- Token type distinction (access vs refresh)
- Token ID (jti) for revocation support
- Redis-backed token blacklist

Security Best Practices:
- RS256 uses public/private key pairs for signing
- Private key signs tokens, public key verifies
- Public key can be shared with services for verification
- Token blacklist enables immediate revocation on logout/compromise
"""

import uuid
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Literal, Tuple
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from jose import jwt, JWTError
from pydantic import BaseModel

from .config import get_auth_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Key Management for RS256
# =============================================================================

@lru_cache(maxsize=1)
def load_rsa_keys() -> Tuple[Optional[str], Optional[str]]:
    """
    Load RSA private and public keys for RS256 signing.

    Keys can be provided via:
    1. Environment variables: AUTH_PRIVATE_KEY, AUTH_PUBLIC_KEY (base64 or PEM)
    2. File paths: AUTH_PRIVATE_KEY_PATH, AUTH_PUBLIC_KEY_PATH

    Returns:
        Tuple of (private_key, public_key) as PEM strings, or (None, None) if not configured
    """
    settings = get_auth_settings()

    private_key = None
    public_key = None

    # Try environment variables first (for containerized deployments)
    env_private = os.getenv("AUTH_PRIVATE_KEY")
    env_public = os.getenv("AUTH_PUBLIC_KEY")

    if env_private:
        # Handle base64-encoded keys (common in env vars)
        if not env_private.startswith("-----BEGIN"):
            import base64
            try:
                private_key = base64.b64decode(env_private).decode('utf-8')
            except Exception as e:
                logger.exception(f"Failed to base64-decode AUTH_PRIVATE_KEY, using raw value: {e}")
                private_key = env_private
        else:
            private_key = env_private

    if env_public:
        if not env_public.startswith("-----BEGIN"):
            import base64
            try:
                public_key = base64.b64decode(env_public).decode('utf-8')
            except Exception as e:
                logger.exception(f"Failed to base64-decode AUTH_PUBLIC_KEY, using raw value: {e}")
                public_key = env_public
        else:
            public_key = env_public

    # Fall back to file paths
    if not private_key and settings.private_key_path:
        key_path = Path(settings.private_key_path)
        if key_path.exists():
            private_key = key_path.read_text()
            logger.info(f"Loaded RSA private key from {key_path}")

    if not public_key and settings.public_key_path:
        key_path = Path(settings.public_key_path)
        if key_path.exists():
            public_key = key_path.read_text()
            logger.info(f"Loaded RSA public key from {key_path}")

    return private_key, public_key


def get_signing_key() -> str:
    """
    Get the appropriate signing key based on algorithm.

    Returns:
        For HS256: The secret key
        For RS256: The private key (PEM format)

    Raises:
        ValueError: If RS256 is configured but no private key is available
    """
    settings = get_auth_settings()

    if settings.algorithm == "RS256":
        private_key, _ = load_rsa_keys()
        if not private_key:
            raise ValueError(
                "RS256 algorithm requires a private key. "
                "Set AUTH_PRIVATE_KEY environment variable or AUTH_PRIVATE_KEY_PATH in config."
            )
        return private_key

    return settings.secret_key


def get_verification_key() -> str:
    """
    Get the appropriate verification key based on algorithm.

    Returns:
        For HS256: The secret key
        For RS256: The public key (PEM format)

    Raises:
        ValueError: If RS256 is configured but no public key is available
    """
    settings = get_auth_settings()

    if settings.algorithm == "RS256":
        _, public_key = load_rsa_keys()
        if not public_key:
            raise ValueError(
                "RS256 algorithm requires a public key. "
                "Set AUTH_PUBLIC_KEY environment variable or AUTH_PUBLIC_KEY_PATH in config."
            )
        return public_key

    return settings.secret_key


class TokenType(str, Enum):
    """Token types for different authentication purposes."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    BORROWER = "borrower"


@dataclass
class TokenData:
    """Decoded token data."""
    sub: str  # Subject (user email or ID)
    token_type: TokenType
    jti: str  # Token ID for revocation
    exp: datetime
    iat: datetime
    iss: str
    aud: str
    user_id: Optional[int] = None
    tenant_id: Optional[str] = None
    roles: Optional[list] = None
    extra: Optional[Dict[str, Any]] = None


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    token_id: Optional[str] = None,
) -> str:
    """
    Create a JWT access token with proper claims.

    Args:
        data: Token payload (must include 'sub' for subject)
        expires_delta: Custom expiration time
        token_id: Custom token ID (jti), auto-generated if not provided

    Returns:
        Encoded JWT string
    """
    settings = get_auth_settings()

    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    # Set expiration
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": settings.issuer,
        "aud": settings.audience,
        "jti": token_id or str(uuid.uuid4()),
        "type": TokenType.ACCESS.value,
    })

    signing_key = get_signing_key()
    return jwt.encode(to_encode, signing_key, algorithm=settings.algorithm)


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    token_id: Optional[str] = None,
) -> str:
    """
    Create a JWT refresh token with proper claims.

    Refresh tokens are used to obtain new access tokens without
    requiring re-authentication. They have longer expiry times
    and should be stored securely (HttpOnly cookies).

    Args:
        data: Token payload (must include 'sub' for subject)
        expires_delta: Custom expiration time
        token_id: Custom token ID (jti), auto-generated if not provided

    Returns:
        Encoded JWT string
    """
    settings = get_auth_settings()

    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    # Refresh tokens have longer expiry
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.refresh_token_expire_days)

    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": settings.issuer,
        "aud": settings.audience,
        "jti": token_id or str(uuid.uuid4()),
        "type": TokenType.REFRESH.value,
    })

    signing_key = get_signing_key()
    return jwt.encode(to_encode, signing_key, algorithm=settings.algorithm)


def decode_token(token: str, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
    """
    Decode a JWT token and return the payload.

    Args:
        token: The JWT token string
        verify_exp: Whether to verify expiration (set False for inspection)

    Returns:
        Decoded token payload or None if invalid
    """
    settings = get_auth_settings()

    try:
        options = {}
        if not verify_exp:
            options["verify_exp"] = False

        verification_key = get_verification_key()
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[settings.algorithm],
            audience=settings.audience,
            issuer=settings.issuer,
            options=options,
        )
        return payload
    except JWTError as e:
        logger.debug(f"Token decode failed: {e}")
        return None


def verify_token(
    token: str,
    expected_type: Optional[TokenType] = None,
    check_blacklist: bool = True,
) -> Optional[TokenData]:
    """
    Verify a JWT token and return structured token data.

    Args:
        token: The JWT token string
        expected_type: If provided, verify token type matches
        check_blacklist: Whether to check if token is blacklisted (default: True)

    Returns:
        TokenData if valid, None if invalid, expired, or blacklisted
    """
    payload = decode_token(token)
    if not payload:
        return None

    # SECURITY FIX: Check if token is blacklisted (logout, password change, etc.)
    if check_blacklist and token_blacklist.is_blacklisted(token):
        logger.warning(f"Rejected blacklisted token: {payload.get('jti', 'unknown')[:8]}...")
        return None

    # Also check if user's tokens have been globally revoked
    user_id = payload.get("user_id")
    if check_blacklist and user_id and token_blacklist.is_user_revoked(user_id, payload.get("iat")):
        logger.warning(f"Rejected token for revoked user: {user_id}")
        return None

    # Verify token type if expected
    token_type_str = payload.get("type", TokenType.ACCESS.value)
    try:
        token_type = TokenType(token_type_str)
    except ValueError:
        logger.warning(f"Unknown token type: {token_type_str}")
        return None

    if expected_type and token_type != expected_type:
        logger.warning(f"Token type mismatch: expected {expected_type}, got {token_type}")
        return None

    # Extract expiration as datetime
    exp_timestamp = payload.get("exp")
    iat_timestamp = payload.get("iat")

    try:
        exp = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else None
        iat = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc) if iat_timestamp else None
    except (TypeError, ValueError):
        return None

    return TokenData(
        sub=payload.get("sub", ""),
        token_type=token_type,
        jti=payload.get("jti", ""),
        exp=exp,
        iat=iat,
        iss=payload.get("iss", ""),
        aud=payload.get("aud", ""),
        user_id=payload.get("user_id"),
        tenant_id=payload.get("tenant_id"),
        roles=payload.get("roles"),
        extra={k: v for k, v in payload.items()
               if k not in ("sub", "exp", "iat", "iss", "aud", "jti", "type", "user_id", "tenant_id", "roles")},
    )


def get_token_jti(token: str) -> Optional[str]:
    """
    Extract the JTI (token ID) from a token without full validation.

    Useful for token revocation where you need the ID even if expired.

    Args:
        token: The JWT token string

    Returns:
        Token ID or None if cannot be extracted
    """
    payload = decode_token(token, verify_exp=False)
    return payload.get("jti") if payload else None


# =============================================================================
# Token Blacklist (Phase 4 - Redis-backed)
# =============================================================================

class TokenBlacklist:
    """
    Token blacklist for immediate revocation.

    Tokens can be blacklisted when:
    - User logs out
    - Password is changed
    - Account is compromised
    - Admin force-logout

    Implementation uses Redis with TTL matching token expiration.
    """

    def __init__(self):
        self._redis = None
        self._enabled = False

    def initialize(self, redis_url: str):
        """Initialize Redis connection for blacklist."""
        try:
            import redis
            self._redis = redis.from_url(redis_url)
            self._enabled = True
            logger.info("Token blacklist initialized with Redis")
        except Exception as e:
            logger.warning(f"Token blacklist disabled: {e}")
            self._enabled = False

    def add(self, token: str, reason: str = "logout") -> bool:
        """
        Add a token to the blacklist.

        Args:
            token: The JWT token to blacklist
            reason: Reason for blacklisting

        Returns:
            True if successfully blacklisted
        """
        if not self._enabled:
            return False

        jti = get_token_jti(token)
        if not jti:
            return False

        # Get token expiration to set Redis TTL
        payload = decode_token(token, verify_exp=False)
        if not payload:
            return False

        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            # TTL = time until token expires
            ttl = max(0, exp_timestamp - datetime.now(timezone.utc).timestamp())
            self._redis.setex(f"blacklist:{jti}", int(ttl), reason)
        else:
            # No expiration, use default 24 hours
            self._redis.setex(f"blacklist:{jti}", 86400, reason)

        logger.info(f"Token {jti[:8]}... blacklisted: {reason}")
        return True

    def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted."""
        if not self._enabled:
            return False

        jti = get_token_jti(token)
        if not jti:
            return False

        return self._redis.exists(f"blacklist:{jti}") > 0

    def revoke_all_for_user(self, user_id: int) -> int:
        """
        Revoke all tokens for a user.

        This marks the user's token family as revoked, requiring re-authentication.
        """
        if not self._enabled:
            return 0

        # Store user revocation timestamp
        key = f"user_revoked:{user_id}"
        self._redis.set(key, datetime.now(timezone.utc).isoformat())
        logger.info(f"All tokens revoked for user {user_id}")
        return 1

    def is_user_revoked(self, user_id: int, token_iat: Optional[int] = None) -> bool:
        """
        Check if a user's tokens have been globally revoked.

        Args:
            user_id: The user ID to check
            token_iat: The token's issued-at timestamp (if available)

        Returns:
            True if user's tokens are revoked and token was issued before revocation
        """
        if not self._enabled:
            return False

        key = f"user_revoked:{user_id}"
        revoked_at = self._redis.get(key)

        if not revoked_at:
            return False

        # If we have token issue time, only reject if token was issued before revocation
        if token_iat:
            try:
                revoked_timestamp = datetime.fromisoformat(revoked_at.decode() if isinstance(revoked_at, bytes) else revoked_at)
                token_issued = datetime.fromtimestamp(token_iat, tz=timezone.utc)
                return token_issued < revoked_timestamp
            except (ValueError, TypeError):
                # If we can't parse, assume revoked for safety
                return True

        return True

    def clear_user_revocation(self, user_id: int) -> bool:
        """
        Clear the revocation flag for a user (after successful re-authentication).
        """
        if not self._enabled:
            return False

        key = f"user_revoked:{user_id}"
        self._redis.delete(key)
        logger.info(f"Revocation cleared for user {user_id}")
        return True


# Global blacklist instance
token_blacklist = TokenBlacklist()
