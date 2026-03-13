"""
E-Signature Key Manager

Centralized key management for e-signature cryptographic operations.

All keys are derived from a single master secret (ESIGN_SIGNING_SECRET) using
HKDF-based key derivation with domain-separated info strings.  This ensures:

- No ephemeral keys: the service REFUSES to start without the env var.
- Domain separation: signing, token, and audit keys are cryptographically
  independent even though they share a master secret.
- Key rotation: new keys can be deployed while still verifying signatures
  made with the previous key.
- Health checks: a self-test can confirm the keys are loaded and functional
  before the service accepts traffic.

Environment variables:
    ESIGN_SIGNING_SECRET  - Master secret (required, min 32 chars).
    ESIGN_TOKEN_SECRET    - Token secret (required, min 32 chars).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import struct
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_SECRET_LENGTH = 32  # bytes / chars

# HKDF info strings for domain-separated key derivation.
_INFO_SIGNING = b"esign-signing-key-v1"
_INFO_TOKEN = b"esign-token-key-v1"
_INFO_AUDIT = b"esign-audit-key-v1"

# Key length for derived keys (256-bit).
_DERIVED_KEY_LENGTH = 32


# ---------------------------------------------------------------------------
# HKDF helpers (stdlib-only, no third-party dependency)
# ---------------------------------------------------------------------------

def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract: PRK = HMAC-Hash(salt, IKM)."""
    if not salt:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand: derive *length* bytes of output keying material."""
    hash_len = 32  # SHA-256
    n = (length + hash_len - 1) // hash_len
    okm = b""
    t = b""
    for i in range(1, n + 1):
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def _hkdf_derive(master: bytes, info: bytes, length: int = _DERIVED_KEY_LENGTH) -> bytes:
    """Derive a key from *master* using HKDF-SHA256 with the given *info*."""
    prk = _hkdf_extract(salt=b"perennia-esign-v1", ikm=master)
    return _hkdf_expand(prk, info, length)


# ---------------------------------------------------------------------------
# Length-prefixed encoding
# ---------------------------------------------------------------------------

def length_prefix_encode(*fields: str) -> bytes:
    """
    Encode variable-length string fields using length-prefixed framing.

    Each field is encoded as a 4-byte big-endian length prefix followed by
    its UTF-8 bytes.  This prevents field-boundary confusion attacks that
    are possible with simple delimiter-based (e.g. ``|``) concatenation.

    Example attack with pipe separator:
        field1="a|b", field2="c"  vs  field1="a", field2="b|c"
        Both produce the same pipe-joined string "a|b|c".

    With length-prefixed encoding these produce different byte strings.
    """
    parts: list[bytes] = []
    for field in fields:
        raw = field.encode("utf-8")
        parts.append(struct.pack(">I", len(raw)))
        parts.append(raw)
    return b"".join(parts)


# ---------------------------------------------------------------------------
# ESignatureKeyManager
# ---------------------------------------------------------------------------

class ESignatureKeyManager:
    """
    Centralized key management for e-signature operations.

    Initialisation validates that the required environment variables are set
    and derives purpose-specific keys using HKDF.  If the env vars are
    missing the constructor raises ``RuntimeError`` so the application fails
    fast rather than silently generating unverifiable signatures.
    """

    def __init__(
        self,
        signing_secret: Optional[str] = None,
        token_secret: Optional[str] = None,
        *,
        _previous_signing_secret: Optional[str] = None,
    ):
        # ----- resolve master secrets -----
        signing_secret = signing_secret or os.getenv("ESIGN_SIGNING_SECRET", "")
        token_secret = token_secret or os.getenv("ESIGN_TOKEN_SECRET", "")

        if not signing_secret:
            raise RuntimeError(
                "ESIGN_SIGNING_SECRET environment variable is not set. "
                "E-signature cryptographic operations require a persistent "
                "signing secret. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
                "and set it in your environment / Railway variables."
            )

        if not token_secret:
            raise RuntimeError(
                "ESIGN_TOKEN_SECRET environment variable is not set. "
                "E-signature token operations require a persistent token "
                "secret. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
                "and set it in your environment / Railway variables."
            )

        if len(signing_secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"ESIGN_SIGNING_SECRET is too short ({len(signing_secret)} chars). "
                f"Minimum length is {_MIN_SECRET_LENGTH} characters."
            )

        if len(token_secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"ESIGN_TOKEN_SECRET is too short ({len(token_secret)} chars). "
                f"Minimum length is {_MIN_SECRET_LENGTH} characters."
            )

        master_signing = signing_secret.encode("utf-8")
        master_token = token_secret.encode("utf-8")

        # ----- derive purpose-specific keys -----
        self._signing_key = _hkdf_derive(master_signing, _INFO_SIGNING)
        self._token_key = _hkdf_derive(master_token, _INFO_TOKEN)
        self._audit_key = _hkdf_derive(master_signing, _INFO_AUDIT)

        # ----- optional previous key for rotation -----
        self._previous_signing_key: Optional[bytes] = None
        if _previous_signing_secret:
            prev_master = _previous_signing_secret.encode("utf-8")
            self._previous_signing_key = _hkdf_derive(prev_master, _INFO_SIGNING)

        # ----- self-test stamp (for health_check) -----
        self._init_timestamp = datetime.now(timezone.utc).isoformat()
        self._test_signature = hmac.new(
            self._signing_key,
            b"esign-key-manager-self-test",
            hashlib.sha256,
        ).hexdigest()

        logger.info(
            "ESignatureKeyManager initialised at %s (rotation key present: %s)",
            self._init_timestamp,
            self._previous_signing_key is not None,
        )

    # ------------------------------------------------------------------
    # Key accessors
    # ------------------------------------------------------------------

    def get_signing_key(self) -> bytes:
        """Return the current signing key. Raises if not configured."""
        if not self._signing_key:
            raise RuntimeError("Signing key is not configured")
        return self._signing_key

    def get_token_key(self) -> bytes:
        """Return the token encryption key. Raises if not configured."""
        if not self._token_key:
            raise RuntimeError("Token key is not configured")
        return self._token_key

    def get_audit_key(self) -> bytes:
        """Return the audit hash key. Raises if not configured."""
        if not self._audit_key:
            raise RuntimeError("Audit key is not configured")
        return self._audit_key

    def get_previous_signing_key(self) -> Optional[bytes]:
        """Return the previous signing key (for rotation), or None."""
        return self._previous_signing_key

    # ------------------------------------------------------------------
    # Key rotation helpers
    # ------------------------------------------------------------------

    def rotate_keys(self, new_signing_secret: str) -> "ESignatureKeyManager":
        """
        Create a new key manager with *new_signing_secret* as the current key
        and the current signing key demoted to the previous-key slot.

        The returned manager will:
        - Sign new signatures with the new key.
        - Verify signatures made with either the new or old key.

        The caller should replace the singleton with the returned instance and
        update the environment variable for the next deploy.
        """
        if len(new_signing_secret) < _MIN_SECRET_LENGTH:
            raise ValueError(
                f"New signing secret is too short ({len(new_signing_secret)} chars). "
                f"Minimum length is {_MIN_SECRET_LENGTH} characters."
            )

        # Recover the current master from env (we don't store it raw).
        current_master = os.getenv("ESIGN_SIGNING_SECRET", "")
        token_secret = os.getenv("ESIGN_TOKEN_SECRET", "")

        return ESignatureKeyManager(
            signing_secret=new_signing_secret,
            token_secret=token_secret,
            _previous_signing_secret=current_master or None,
        )

    def verify_with_rotation(
        self,
        message: bytes,
        expected_mac_hex: str,
    ) -> bool:
        """
        Verify an HMAC using the current signing key, falling back to the
        previous key if rotation is in progress.

        Returns True if the mac matches either key.
        """
        # Try current key first
        current_mac = hmac.new(
            self._signing_key, message, hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(current_mac, expected_mac_hex):
            return True

        # Fall back to previous key if available
        if self._previous_signing_key:
            prev_mac = hmac.new(
                self._previous_signing_key, message, hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(prev_mac, expected_mac_hex):
                logger.info(
                    "Signature verified with PREVIOUS key — "
                    "re-sign with current key at next opportunity"
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """
        Verify that keys are loaded and functional.

        Returns a dict with ``healthy`` (bool), ``initialized_at``, and
        optionally ``error``.
        """
        try:
            # Re-compute the self-test signature and compare
            check = hmac.new(
                self._signing_key,
                b"esign-key-manager-self-test",
                hashlib.sha256,
            ).hexdigest()

            keys_valid = hmac.compare_digest(check, self._test_signature)

            if not keys_valid:
                return {
                    "healthy": False,
                    "initialized_at": self._init_timestamp,
                    "error": "Self-test signature mismatch — signing key may have been corrupted in memory",
                }

            return {
                "healthy": True,
                "initialized_at": self._init_timestamp,
                "has_rotation_key": self._previous_signing_key is not None,
            }

        except Exception as e:
            logger.exception("Key manager health check failed")
            return {
                "healthy": False,
                "initialized_at": self._init_timestamp,
                "error": str(e),
            }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[ESignatureKeyManager] = None


def get_esignature_key_manager() -> ESignatureKeyManager:
    """
    Get or create the singleton ``ESignatureKeyManager``.

    Raises ``RuntimeError`` if the required env vars are not set.
    """
    global _manager
    if _manager is None:
        _manager = ESignatureKeyManager()
    return _manager


def reset_key_manager() -> None:
    """Reset the singleton (used in tests and key rotation)."""
    global _manager
    _manager = None
