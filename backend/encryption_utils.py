"""
Encryption Utilities for Sensitive Data
Provides field-level encryption for borrower financial data
"""
import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String, Integer, Float
import logging

logger = logging.getLogger(__name__)


def _derive_key_pbkdf2(secret_key: str) -> bytes:
    """Derive a Fernet-compatible key from SECRET_KEY using PBKDF2."""
    key_material = hashlib.pbkdf2_hmac(
        "sha256",
        secret_key.encode(),
        b"perennia-encryption-salt-v1",
        iterations=100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(key_material)


def _derive_key_legacy(secret_key: str) -> bytes:
    """Legacy weak key derivation — kept only for decrypting old data."""
    key_material = secret_key.encode()[:32].ljust(32, b"0")
    return base64.urlsafe_b64encode(key_material)


class EncryptionManager:
    """Manages encryption keys and operations"""

    def __init__(self):
        encryption_key = os.getenv("DATA_ENCRYPTION_KEY", "")
        is_production = os.getenv("ENVIRONMENT") == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT"))
        self._legacy_fernet: Optional[Fernet] = None

        initialized = False
        if encryption_key and not encryption_key.startswith("CHANGE_ME"):
            try:
                self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
                initialized = True
            except Exception as e:
                logger.warning(f"DATA_ENCRYPTION_KEY is invalid ({e}), falling back to SECRET_KEY")

        if not initialized:
            secret_key = os.getenv("SECRET_KEY", "")
            if is_production:
                logger.critical(
                    "CRITICAL: DATA_ENCRYPTION_KEY not set in production. "
                    "Deriving encryption key from SECRET_KEY via PBKDF2. "
                    "Set DATA_ENCRYPTION_KEY to a dedicated Fernet key."
                )
            else:
                logger.warning("DATA_ENCRYPTION_KEY not set, deriving from SECRET_KEY (not recommended for production)")

            derived_key = _derive_key_pbkdf2(secret_key)
            try:
                self.fernet = Fernet(derived_key)
                initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
                raise ValueError(f"Invalid encryption key: {e}")

            # Keep legacy derivation as fallback for decrypting old data
            try:
                legacy_key = _derive_key_legacy(secret_key)
                self._legacy_fernet = Fernet(legacy_key)
            except Exception:
                pass

        if initialized:
            logger.info("Encryption manager initialized successfully")

    def encrypt(self, value: str) -> str:
        """Encrypt a string value"""
        if not value:
            return value
        try:
            encrypted = self.fernet.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt an encrypted string. Tries current key, then legacy key,
        then returns plaintext (pre-encryption row)."""
        if not encrypted_value:
            return encrypted_value
        # Try current key
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except InvalidToken:
            pass
        except Exception:
            pass
        # Try legacy-derived key for data encrypted before PBKDF2 migration
        if self._legacy_fernet:
            try:
                return self._legacy_fernet.decrypt(encrypted_value.encode()).decode()
            except Exception:
                pass
        # Not Fernet-encrypted (pre-existing plaintext row) or key mismatch
        logger.warning(f"Decryption returned plaintext — value may not be encrypted (prefix: {encrypted_value[:4]}...)")
        return encrypted_value


# Global encryption manager instance
encryption_manager = EncryptionManager()


class EncryptedString(TypeDecorator):
    """SQLAlchemy type for encrypted string fields"""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt value before storing in database"""
        if value is None:
            return value
        return encryption_manager.encrypt(str(value))

    def process_result_value(self, value, dialect):
        """Decrypt value when retrieving from database"""
        if value is None:
            return value
        return encryption_manager.decrypt(value)


class EncryptedInteger(TypeDecorator):
    """SQLAlchemy type for encrypted integer fields"""

    impl = String  # Store as encrypted string in DB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt integer value before storing"""
        if value is None:
            return value
        return encryption_manager.encrypt(str(value))

    def process_result_value(self, value, dialect):
        """Decrypt and convert back to integer"""
        if value is None:
            return value
        decrypted = encryption_manager.decrypt(value)
        try:
            return int(decrypted) if decrypted else None
        except (ValueError, TypeError):
            return None


class EncryptedFloat(TypeDecorator):
    """SQLAlchemy type for encrypted float fields"""

    impl = String  # Store as encrypted string in DB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt float value before storing"""
        if value is None:
            return value
        return encryption_manager.encrypt(str(value))

    def process_result_value(self, value, dialect):
        """Decrypt and convert back to float"""
        if value is None:
            return value
        decrypted = encryption_manager.decrypt(value)
        try:
            return float(decrypted) if decrypted else None
        except (ValueError, TypeError):
            return None


# Utility functions for manual encryption/decryption
def encrypt_value(value: Optional[str]) -> Optional[str]:
    """Manually encrypt a value"""
    if value is None:
        return None
    return encryption_manager.encrypt(str(value))


def decrypt_value(encrypted_value: Optional[str]) -> Optional[str]:
    """Manually decrypt a value"""
    if encrypted_value is None:
        return None
    return encryption_manager.decrypt(encrypted_value)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key"""
    key = Fernet.generate_key()
    return key.decode()


if __name__ == "__main__":
    # Test encryption/decryption
    print("Testing encryption utilities...")

    # Generate a test key
    test_key = generate_encryption_key()
    print(f"Generated key: {test_key}")

    # Test string encryption
    test_string = "John Doe"
    encrypted = encrypt_value(test_string)
    decrypted = decrypt_value(encrypted)
    print(f"String: {test_string} → {encrypted[:20]}... → {decrypted}")
    assert decrypted == test_string, "String encryption failed!"

    # Test integer encryption
    test_int = 75000
    encrypted_int = encrypt_value(str(test_int))
    decrypted_int = int(decrypt_value(encrypted_int))
    print(f"Integer: {test_int} → {encrypted_int[:20]}... → {decrypted_int}")
    assert decrypted_int == test_int, "Integer encryption failed!"

    # Test float encryption
    test_float = 3.875
    encrypted_float = encrypt_value(str(test_float))
    decrypted_float = float(decrypt_value(encrypted_float))
    print(f"Float: {test_float} → {encrypted_float[:20]}... → {decrypted_float}")
    assert decrypted_float == test_float, "Float encryption failed!"

    print("✅ All encryption tests passed!")
