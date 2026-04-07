"""
Encryption Key Rotation Support

Provides a RotatingFernet class that supports seamless key rotation:
- Encrypts with the current key (DATA_ENCRYPTION_KEY)
- Decrypts by trying the current key first, then falling back to the previous
  key (DATA_ENCRYPTION_KEY_PREVIOUS)
- Logs when a value is decrypted with the old key (indicates re-encryption needed)

The EncryptionManager in encryption_utils.py is patched to use RotatingFernet
when both keys are present, ensuring transparent rotation for all EncryptedString
columns across the codebase.
"""

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class RotatingFernet:
    """Fernet wrapper that supports decryption with a previous key.

    Encrypt always uses the current (primary) key. Decrypt tries the
    primary key first; on InvalidToken, falls back to the previous key.
    If the previous key succeeds, a warning is logged so operators know
    the value should be re-encrypted via rotate_encryption_key.py.

    Thread-safe: Fernet instances are safe for concurrent use.
    """

    def __init__(self, current_key: bytes, previous_key: Optional[bytes] = None):
        """
        Args:
            current_key: The active Fernet key (used for encryption + primary decryption).
            previous_key: The old Fernet key (used only for decryption fallback).
                          Can be None if no rotation is in progress.
        """
        self._current = Fernet(current_key)
        self._previous = Fernet(previous_key) if previous_key else None
        self._old_key_decrypt_count = 0

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt with the current key."""
        return self._current.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        """Decrypt, trying current key first, then previous key.

        Raises InvalidToken if neither key can decrypt the token.
        """
        try:
            return self._current.decrypt(token)
        except InvalidToken:
            if self._previous is None:
                raise
            # Try the previous key
            try:
                result = self._previous.decrypt(token)
                self._old_key_decrypt_count += 1
                if self._old_key_decrypt_count <= 10:
                    logger.warning(
                        "Value decrypted with PREVIOUS encryption key — "
                        "run rotate_encryption_key.py to re-encrypt with current key "
                        "(suppressing after 10 warnings)"
                    )
                elif self._old_key_decrypt_count == 11:
                    logger.warning(
                        "Suppressing further old-key decryption warnings. "
                        "Run rotate_encryption_key.py to complete key rotation."
                    )
                return result
            except InvalidToken:
                raise InvalidToken(
                    "Token could not be decrypted with either current or previous key"
                )

    @property
    def old_key_decrypt_count(self) -> int:
        """Number of values decrypted with the previous key since startup."""
        return self._old_key_decrypt_count


def build_rotating_fernet() -> Optional[RotatingFernet]:
    """Build a RotatingFernet from environment variables.

    Reads:
    - DATA_ENCRYPTION_KEY: current (primary) Fernet key
    - DATA_ENCRYPTION_KEY_PREVIOUS: previous Fernet key (optional)

    Returns:
        RotatingFernet if DATA_ENCRYPTION_KEY is a valid Fernet key, else None.
        If only the current key is present (no previous), the RotatingFernet
        is created without a fallback key.
    """
    current_raw = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    previous_raw = os.getenv("DATA_ENCRYPTION_KEY_PREVIOUS", "").strip()

    if not current_raw or current_raw.startswith("CHANGE_ME"):
        return None

    try:
        current_key = current_raw.encode() if isinstance(current_raw, str) else current_raw
        # Validate it is a proper Fernet key
        Fernet(current_key)
    except Exception as e:
        logger.warning(f"DATA_ENCRYPTION_KEY is not a valid Fernet key: {e}")
        return None

    previous_key = None
    if previous_raw and not previous_raw.startswith("CHANGE_ME"):
        try:
            previous_key = previous_raw.encode() if isinstance(previous_raw, str) else previous_raw
            Fernet(previous_key)
            logger.info(
                "Encryption key rotation active: DATA_ENCRYPTION_KEY_PREVIOUS is set. "
                "Decryption will fall back to previous key. Run rotate_encryption_key.py "
                "to re-encrypt all values with the new key."
            )
        except Exception as e:
            logger.warning(f"DATA_ENCRYPTION_KEY_PREVIOUS is not a valid Fernet key: {e} — ignoring")
            previous_key = None

    return RotatingFernet(current_key, previous_key)


def install_rotating_fernet():
    """Patch the global EncryptionManager to use RotatingFernet.

    Called during app startup (main.py). If both DATA_ENCRYPTION_KEY and
    DATA_ENCRYPTION_KEY_PREVIOUS are set, replaces encryption_manager.fernet
    with a RotatingFernet instance that can decrypt values encrypted with
    either key.

    This is safe because RotatingFernet exposes the same encrypt()/decrypt()
    interface as cryptography.fernet.Fernet.
    """
    rotating = build_rotating_fernet()
    if rotating is None:
        return False

    try:
        from encryption_utils import encryption_manager
        # Only patch if there is a previous key — otherwise the existing
        # Fernet is equivalent
        previous_raw = os.getenv("DATA_ENCRYPTION_KEY_PREVIOUS", "").strip()
        if previous_raw and not previous_raw.startswith("CHANGE_ME"):
            encryption_manager.fernet = rotating
            logger.info("EncryptionManager patched with RotatingFernet (key rotation active)")
            return True
        else:
            logger.debug("No previous encryption key — EncryptionManager unchanged")
            return False
    except ImportError:
        logger.warning("encryption_utils not available — cannot install RotatingFernet")
        return False
    except Exception as e:
        logger.error(f"Failed to install RotatingFernet: {e}")
        return False
