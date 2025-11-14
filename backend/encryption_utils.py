"""
Encryption Utilities for Sensitive Data
Provides field-level encryption for borrower financial data
"""
import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy.types import TypeDecorator, String, Integer, Float
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Manages encryption keys and operations"""

    def __init__(self):
        # Use dedicated encryption key (separate from JWT SECRET_KEY)
        encryption_key = os.getenv("DATA_ENCRYPTION_KEY")

        if not encryption_key:
            # Fallback to SECRET_KEY for backward compatibility
            # But log a warning - should use dedicated key
            logger.warning("⚠️ DATA_ENCRYPTION_KEY not set, using SECRET_KEY (not recommended)")
            secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
            key_material = secret_key.encode()[:32].ljust(32, b'0')
            encryption_key = base64.urlsafe_b64encode(key_material).decode()

        try:
            self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            logger.info("✅ Encryption manager initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize encryption: {e}")
            raise ValueError(f"Invalid encryption key: {e}")

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
        """Decrypt an encrypted string"""
        if not encrypted_value:
            return encrypted_value
        try:
            decrypted = self.fernet.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise


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
        return int(decrypted) if decrypted else None


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
        return float(decrypted) if decrypted else None


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
