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
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Literal, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

from .config import get_auth_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Key Management for RS256
# =============================================================================

_rsa_keys_cache: Optional[Tuple[Optional[str], Optional[str]]] = None


def load_rsa_keys() -> Tuple[Optional[str], Optional[str]]:
    """
    Load RSA private and public keys for RS256 signing.

    Keys can be provided via:
    1. Environment variables: AUTH_PRIVATE_KEY, AUTH_PUBLIC_KEY (base64 or PEM)
    2. File paths: AUTH_PRIVATE_KEY_PATH, AUTH_PUBLIC_KEY_PATH

    Results are cached in a module-level variable that can be invalidated
    via invalidate_rsa_keys() to support key rotation at runtime.

    Returns:
        Tuple of (private_key, public_key) as PEM strings, or (None, None) if not configured
    """
    global _rsa_keys_cache
    if _rsa_keys_cache is not None:
        return _rsa_keys_cache

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

    _rsa_keys_cache = (private_key, public_key)
    return _rsa_keys_cache


def invalidate_rsa_keys():
    """Invalidate the cached RSA keys, forcing reload on next token operation.

    Call this after rotating RSA keys in the environment or on disk.
    Existing tokens signed with the old key will fail verification once
    the new public key is loaded.
    """
    global _rsa_keys_cache
    _rsa_keys_cache = None
    logger.info("RSA key cache invalidated — keys will reload on next use")


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

    SECURITY: Only the single configured algorithm is accepted. This prevents
    algorithm confusion attacks where an attacker crafts a token with alg=none
    or switches RS256 -> HS256 (using the public key as HMAC secret).

    Args:
        token: The JWT token string
        verify_exp: Whether to verify expiration (set False for inspection)

    Returns:
        Decoded token payload or None if invalid
    """
    settings = get_auth_settings()

    # SECURITY: Reject "none" algorithm and enforce single-algorithm verification.
    # This is defense-in-depth — PyJWT >= 2.4 rejects "none" by default, but we
    # make the intent explicit to survive library upgrades or misconfigurations.
    allowed_algorithm = settings.algorithm
    if allowed_algorithm.lower() == "none":
        logger.error("JWT algorithm configured as 'none' — rejecting all tokens")
        return None

    try:
        options = {}
        if not verify_exp:
            options["verify_exp"] = False

        verification_key = get_verification_key()
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[allowed_algorithm],
            audience=settings.audience,
            issuer=settings.issuer,
            options=options,
        )

        # Defense-in-depth: verify the token's header algorithm matches what we expect.
        # PyJWT should enforce this via the algorithms parameter, but we double-check.
        header = jwt.get_unverified_header(token)
        if header.get("alg") != allowed_algorithm:
            logger.warning(
                "JWT header alg=%s does not match configured algorithm=%s — rejecting",
                header.get("alg"), allowed_algorithm,
            )
            return None

        return payload
    except InvalidTokenError as e:
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


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a JWT access token and return the raw payload dict.

    This is a convenience wrapper around verify_token() for route files
    that previously called jwt.decode() directly. It ensures the token
    is not blacklisted and is a valid access token.

    Returns:
        Decoded payload dict if valid, None if invalid/expired/blacklisted.
    """
    token_data = verify_token(token, expected_type=TokenType.ACCESS)
    if token_data is None:
        return None
    # Reconstruct a payload dict compatible with what jwt.decode() returns
    payload = {
        "sub": token_data.sub,
        "user_id": token_data.user_id,
        "tenant_id": token_data.tenant_id,
        "jti": token_data.jti,
        "type": token_data.token_type.value if token_data.token_type else None,
        "roles": token_data.roles,
    }
    if token_data.extra:
        payload.update(token_data.extra)
    return payload


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
# Token Blacklist (Redis-backed, no in-memory fallback in production)
# =============================================================================

# Redis key prefix for deny-listed JTIs
_DENY_KEY_PREFIX = "token:deny:"
_USER_REVOKED_PREFIX = "token:user_revoked:"


def _is_production() -> bool:
    """Detect production environment (Railway or explicit ENV)."""
    env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
    return env.lower() in ("production", "prod")


class _InMemoryBlacklist:
    """
    Process-local fallback blacklist used ONLY in development/test.

    In production, Redis is mandatory for the token denylist. This class
    exists solely for local development and test suites where Redis may
    not be available.

    Entries are stored with TTL-based expiry and lazily evicted on read.
    """

    def __init__(self):
        self._store: Dict[str, Tuple[str, float]] = {}  # key -> (value, expire_timestamp)
        self._lock = threading.Lock()

    def _evict_expired(self):
        """Remove expired entries. Must be called with _lock held."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired_keys:
            del self._store[k]

    def setex(self, key: str, ttl_seconds: int, value: str):
        """Set a key with TTL (seconds)."""
        with self._lock:
            self._evict_expired()
            self._store[key] = (value, time.time() + ttl_seconds)

    def set(self, key: str, value: str):
        """Set a key with no expiry (defaults to 24h to avoid leaks)."""
        self.setex(key, 86400, value)

    def get(self, key: str) -> Optional[bytes]:
        """Get a value by key, returning None if missing or expired. Returns bytes for Redis compat."""
        with self._lock:
            self._evict_expired()
            entry = self._store.get(key)
            if entry is None:
                return None
            value, exp = entry
            if time.time() >= exp:
                del self._store[key]
                return None
            return value.encode("utf-8")

    def exists(self, key: str) -> int:
        """Check if key exists (returns 1 or 0 for Redis compat)."""
        return 1 if self.get(key) is not None else 0

    def delete(self, key: str):
        """Delete a key."""
        with self._lock:
            self._store.pop(key, None)


class TokenBlacklist:
    """
    Token denylist for immediate revocation.

    Tokens can be denied when:
    - User logs out
    - Password is changed
    - Account is compromised
    - Admin force-logout

    Implementation:
    - Redis keys: ``token:deny:{jti}`` with TTL = remaining token lifetime
    - User-level revocation: ``token:user_revoked:{user_id}``
    - Production: Redis is MANDATORY. In-memory fallback is disabled.
    - Development/test: In-memory fallback is allowed.
    """

    def __init__(self):
        self._redis = None
        self._enabled = True
        self._fallback = _InMemoryBlacklist()
        self._using_fallback = True  # Start in fallback until Redis is configured
        self._is_production = _is_production()

    def _handle_redis_failure(self, operation: str, error: Exception):
        """Handle Redis failures based on environment.

        Production: Log CRITICAL and do NOT fall back to in-memory.
        Development: Log warning and fall back to in-memory.
        """
        if self._is_production:
            logger.critical(
                "SECURITY: Redis unavailable during %s: %s. "
                "Token denylist is NOT operational — revoked tokens may be accepted. "
                "Redis is MANDATORY in production for token revocation. "
                "Restore Redis connectivity immediately.",
                operation, error,
            )
            # Do NOT set self._using_fallback = True in production.
            # The denylist will report "not denied" for all checks when Redis
            # is down, which is safer than silently accepting an in-memory
            # fallback that is not shared across replicas.
        else:
            if not self._using_fallback:
                logger.warning(
                    "Redis unavailable during %s: %s. "
                    "Falling back to in-memory token denylist (dev/test mode).",
                    operation, error,
                )
                self._using_fallback = True

    def initialize(self, redis_url: str):
        """Initialize Redis connection for the denylist."""
        try:
            import redis
            self._redis = redis.from_url(redis_url)
            # Verify connectivity
            self._redis.ping()
            self._enabled = True
            self._using_fallback = False
            logger.info("Token denylist initialized with Redis")
        except Exception as e:
            if self._is_production:
                logger.critical(
                    "SECURITY: Redis connection failed during denylist init: %s. "
                    "Token revocation will NOT work until Redis is restored. "
                    "In-memory fallback is DISABLED in production.",
                    e,
                )
                self._enabled = True
                self._using_fallback = False  # No fallback in production
            else:
                logger.warning(
                    "Redis connection failed: %s. Using in-memory token denylist (dev/test).",
                    e,
                )
                self._enabled = True
                self._using_fallback = True

    def _redis_available(self) -> bool:
        """Check if Redis is available for denylist operations."""
        return self._redis is not None and not self._using_fallback

    def add(self, token: str, reason: str = "logout") -> bool:
        """
        Add a token to the denylist.

        Args:
            token: The JWT token to deny
            reason: Reason for denial

        Returns:
            True if successfully denied
        """
        if not self._enabled:
            return False

        jti = get_token_jti(token)
        if not jti:
            return False

        # Get token expiration to set TTL
        payload = decode_token(token, verify_exp=False)
        if not payload:
            return False

        exp_timestamp = payload.get("exp")
        ttl = int(max(0, exp_timestamp - datetime.now(timezone.utc).timestamp())) if exp_timestamp else 86400

        return self.revoke_token(jti, ttl, reason)

    def revoke_token(self, jti: str, remaining_ttl: int, reason: str = "revoked") -> bool:
        """
        Revoke a token by its JTI with the remaining TTL.

        This is the primary revocation method. The TTL ensures the Redis
        key auto-expires when the token would have expired naturally,
        preventing unbounded key growth.

        Args:
            jti: The JWT token ID (jti claim)
            remaining_ttl: Seconds until the token expires (Redis TTL)
            reason: Human-readable revocation reason

        Returns:
            True if successfully written to Redis
        """
        if not self._enabled or not jti:
            return False

        # Ensure TTL is at least 1 second (Redis rejects 0 or negative)
        ttl = max(1, remaining_ttl)
        key = f"{_DENY_KEY_PREFIX}{jti}"

        if self._redis_available():
            try:
                self._redis.setex(key, ttl, reason)
                logger.info("Token %s... denied (ttl=%ds): %s", jti[:8], ttl, reason)
                return True
            except Exception as e:
                self._handle_redis_failure("revoke_token", e)

        # Fallback: in-memory (dev/test only — production never reaches here)
        if self._using_fallback:
            self._fallback.setex(key, ttl, reason)
            logger.info("Token %s... denied (in-memory, ttl=%ds): %s", jti[:8], ttl, reason)
            return True

        # Production with Redis down — log but return False
        logger.error("Token %s... revocation FAILED — Redis unavailable in production", jti[:8])
        return False

    def is_blacklisted(self, token: str) -> bool:
        """Check if a token is denied (by full JWT token string)."""
        if not self._enabled:
            return False

        jti = get_token_jti(token)
        if not jti:
            return False

        return self.is_blacklisted_by_jti(jti)

    def is_blacklisted_by_jti(self, jti: str) -> bool:
        """Check if a token is denied by its JTI (token ID) directly.

        This avoids re-decoding the JWT when the caller already has the JTI
        extracted from the payload.
        """
        if not self._enabled:
            return False

        if not jti:
            return False

        key = f"{_DENY_KEY_PREFIX}{jti}"

        if self._redis_available():
            try:
                return self._redis.exists(key) > 0
            except Exception as e:
                self._handle_redis_failure("is_blacklisted_by_jti", e)

        # Fallback for dev/test
        if self._using_fallback:
            return self._fallback.exists(key) > 0

        # Production with Redis down — cannot confirm denial
        # Log and return False (fail-open for availability, fail is logged)
        logger.error(
            "SECURITY: Cannot check denylist for jti=%s... — Redis unavailable in production",
            jti[:8],
        )
        return False

    def revoke_all_for_user(self, user_id: int) -> int:
        """
        Revoke all tokens for a user.

        This marks the user's token family as revoked, requiring re-authentication.
        """
        if not self._enabled:
            return 0

        key = f"{_USER_REVOKED_PREFIX}{user_id}"
        value = datetime.now(timezone.utc).isoformat()

        if self._redis_available():
            try:
                self._redis.set(key, value)
                logger.info("All tokens revoked for user %s", user_id)
                return 1
            except Exception as e:
                self._handle_redis_failure("revoke_all_for_user", e)

        if self._using_fallback:
            self._fallback.set(key, value)
            logger.info("All tokens revoked for user %s (in-memory)", user_id)
            return 1

        logger.error("User %s token revocation FAILED — Redis unavailable in production", user_id)
        return 0

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

        key = f"{_USER_REVOKED_PREFIX}{user_id}"
        revoked_at = None

        if self._redis_available():
            try:
                revoked_at = self._redis.get(key)
            except Exception as e:
                self._handle_redis_failure("is_user_revoked", e)
                if self._using_fallback:
                    revoked_at = self._fallback.get(key)
        elif self._using_fallback:
            revoked_at = self._fallback.get(key)

        if not revoked_at:
            return False

        # If we have token issue time, only reject if token was issued before revocation
        if token_iat:
            try:
                revoked_timestamp = datetime.fromisoformat(revoked_at.decode() if isinstance(revoked_at, bytes) else revoked_at)
                if revoked_timestamp.tzinfo is None:
                    revoked_timestamp = revoked_timestamp.replace(tzinfo=timezone.utc)
                token_issued = datetime.fromtimestamp(token_iat, tz=timezone.utc)
                return token_issued < revoked_timestamp
            except (ValueError, TypeError):
                # If we can't parse, assume revoked for safety
                return True

        return True

    def revoke_on_privilege_change(self, user_id: int, reason: str = "privilege_change"):
        """Revoke all tokens when user's role/permissions change."""
        self.revoke_all_for_user(user_id)
        logger.info("Revoked all tokens for user %s due to: %s", user_id, reason)

    def clear_user_revocation(self, user_id: int) -> bool:
        """
        Clear the revocation flag for a user (after successful re-authentication).
        """
        if not self._enabled:
            return False

        key = f"{_USER_REVOKED_PREFIX}{user_id}"

        if self._redis_available():
            try:
                self._redis.delete(key)
                logger.info("Revocation cleared for user %s", user_id)
                return True
            except Exception as e:
                self._handle_redis_failure("clear_user_revocation", e)

        if self._using_fallback:
            self._fallback.delete(key)
            logger.info("Revocation cleared for user %s (in-memory)", user_id)
            return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Return the current status of the token denylist for health checks.

        Reports which backend is active (redis vs in-memory), the number of
        denied tokens currently tracked, and whether the denylist is
        operating in degraded mode.

        Returns:
            Dict with: mode, status, denied_count, and cross_replica_safe.
        """
        if not self._enabled:
            return {
                "status": "disabled",
                "mode": "none",
                "blacklisted_count": 0,
                "cross_replica_safe": False,
            }

        if self._redis_available():
            # Redis mode — shared across replicas
            try:
                blacklisted_count = 0
                try:
                    cursor = 0
                    while True:
                        cursor, keys = self._redis.scan(cursor, match=f"{_DENY_KEY_PREFIX}*", count=100)
                        blacklisted_count += len(keys)
                        if cursor == 0:
                            break
                except Exception:
                    blacklisted_count = -1  # Unknown

                return {
                    "status": "healthy",
                    "mode": "redis",
                    "blacklisted_count": blacklisted_count,
                    "cross_replica_safe": True,
                }
            except Exception as e:
                self._handle_redis_failure("get_status", e)

        if self._using_fallback:
            # In-memory fallback mode (dev/test only)
            with self._fallback._lock:
                self._fallback._evict_expired()
                blacklisted_count = sum(
                    1 for k in self._fallback._store if k.startswith(_DENY_KEY_PREFIX)
                )

            return {
                "status": "degraded",
                "mode": "in_memory",
                "blacklisted_count": blacklisted_count,
                "cross_replica_safe": False,
                "warning": (
                    "Token denylist is using in-memory fallback (dev/test mode). "
                    "This is NOT acceptable in production."
                ),
            }

        # Production with Redis down
        return {
            "status": "critical",
            "mode": "unavailable",
            "blacklisted_count": -1,
            "cross_replica_safe": False,
            "warning": (
                "SECURITY CRITICAL: Token denylist Redis is unavailable in production. "
                "Revoked tokens may be accepted. Restore Redis immediately."
            ),
        }


# Global blacklist instance
token_blacklist = TokenBlacklist()


def is_token_blacklisted(jti: str) -> bool:
    """
    Check if a token JTI has been blacklisted.

    This is the convenience function that callers (middleware, route files) import
    when they already have the JTI extracted from a decoded JWT payload.  It
    delegates to the global TokenBlacklist singleton.

    Args:
        jti: The JWT token ID (jti claim) to check.

    Returns:
        True if the token has been blacklisted, False otherwise.
    """
    if not jti:
        return False
    return token_blacklist.is_blacklisted_by_jti(jti)
