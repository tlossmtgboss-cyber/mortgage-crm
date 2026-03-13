# backend/integrations/sms_key_vault.py
# Secure storage and retrieval of Telnyx API credentials
# Uses Fernet symmetric encryption; keys stored in DB, master key in env var

import os
import base64
import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encryption helpers (Fernet via cryptography library)
# ---------------------------------------------------------------------------
def _get_fernet():
    """Return a Fernet instance using the master encryption key from env."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "cryptography package not installed. Run: pip install cryptography"
        )
    master_key = os.environ.get("SMS_ENCRYPTION_KEY")
    if not master_key:
        # Auto-generate a key and warn operator to set it permanently
        logger.warning(
            "SMS_ENCRYPTION_KEY not set. Generating ephemeral key - "
            "credentials will not survive restarts. Set SMS_ENCRYPTION_KEY env var."
        )
        master_key = Fernet.generate_key().decode()
        os.environ["SMS_ENCRYPTION_KEY"] = master_key

    key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
    # Key must be 32 url-safe base64 encoded bytes
    if len(key_bytes) != 44:  # 32 bytes b64 = 44 chars
        # Derive a valid key by padding/hashing
        import hashlib
        raw = hashlib.sha256(key_bytes).digest()
        key_bytes = base64.urlsafe_b64encode(raw)
    return Fernet(key_bytes)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously encrypted string."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Credential store (DB-backed)
# ---------------------------------------------------------------------------
def store_telnyx_credential(
    db: Session,
    user_id: int,
    api_key: str,
    public_key: Optional[str] = None,
    phone_number: Optional[str] = None,
    messaging_profile_id: Optional[str] = None,
):
    """
    Encrypt and store Telnyx credentials for a user/org.
    Overwrites existing record for same user_id.
    """
    encrypted_api_key = encrypt_value(api_key)
    encrypted_pub_key = encrypt_value(public_key) if public_key else None

    try:
        db.execute(
            text("""
                INSERT INTO sms_credentials
                  (user_id, encrypted_api_key, encrypted_public_key,
                   phone_number, messaging_profile_id, updated_at)
                VALUES
                  (:user_id, :api_key, :pub_key, :phone, :profile_id, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                  encrypted_api_key     = EXCLUDED.encrypted_api_key,
                  encrypted_public_key  = EXCLUDED.encrypted_public_key,
                  phone_number          = COALESCE(EXCLUDED.phone_number, sms_credentials.phone_number),
                  messaging_profile_id  = COALESCE(EXCLUDED.messaging_profile_id, sms_credentials.messaging_profile_id),
                  updated_at            = NOW()
            """),
            {
                "user_id": user_id,
                "api_key": encrypted_api_key,
                "pub_key": encrypted_pub_key,
                "phone": phone_number,
                "profile_id": messaging_profile_id,
            },
        )
        db.commit()
        logger.info(f"Telnyx credentials stored for user_id={user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store Telnyx credentials: {e}")
        raise


def get_telnyx_credential(db: Session, user_id: int) -> Optional[dict]:
    """
    Retrieve and decrypt Telnyx credentials for a user.
    Returns dict with api_key, public_key, phone_number, messaging_profile_id
    or None if not found.
    """
    try:
        row = db.execute(
            text("""
                SELECT encrypted_api_key, encrypted_public_key,
                       phone_number, messaging_profile_id
                FROM sms_credentials
                WHERE user_id = :user_id
                LIMIT 1
            """),
            {"user_id": user_id},
        ).fetchone()

        if not row:
            return None

        return {
            "api_key": decrypt_value(row[0]) if row[0] else None,
            "public_key": decrypt_value(row[1]) if row[1] else None,
            "phone_number": row[2],
            "messaging_profile_id": row[3],
        }
    except Exception as e:
        logger.error(f"Failed to retrieve Telnyx credentials: {e}")
        return None


def get_active_telnyx_config(db: Session, user_id: Optional[int] = None) -> dict:
    """
    Get Telnyx config, preferring DB-stored credentials over env vars.
    Falls back to TELNYX_API_KEY env var for backward compatibility.
    """
    # Try DB first
    if user_id:
        creds = get_telnyx_credential(db, user_id)
        if creds and creds.get("api_key"):
            return creds

    # Fall back to environment variables
    api_key = os.environ.get("TELNYX_API_KEY", "")
    return {
        "api_key": api_key,
        "public_key": os.environ.get("TELNYX_PUBLIC_KEY"),
        "phone_number": os.environ.get("TELNYX_PHONE_NUMBER"),
        "messaging_profile_id": os.environ.get("TELNYX_MESSAGING_PROFILE_ID"),
    }


def rotate_telnyx_credential(db: Session, user_id: int, new_api_key: str):
    """
    Rotate the API key for a user - re-encrypts with current master key.
    Old key is archived before replacement.
    """
    try:
        # Archive old key
        db.execute(
            text("""
                INSERT INTO sms_credential_audit
                  (user_id, action, rotated_at)
                VALUES (:user_id, 'key_rotated', NOW())
            """),
            {"user_id": user_id},
        )
        # Update with new encrypted key
        encrypted = encrypt_value(new_api_key)
        db.execute(
            text("""
                UPDATE sms_credentials
                SET encrypted_api_key = :key, updated_at = NOW()
                WHERE user_id = :user_id
            """),
            {"key": encrypted, "user_id": user_id},
        )
        db.commit()
        logger.info(f"API key rotated for user_id={user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Key rotation failed for user_id={user_id}: {e}")
        raise


def delete_telnyx_credential(db: Session, user_id: int):
    """Remove stored credentials for a user."""
    try:
        db.execute(
            text("DELETE FROM sms_credentials WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        db.commit()
        logger.info(f"Telnyx credentials deleted for user_id={user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete credentials: {e}")
        raise


# ---------------------------------------------------------------------------
# Key generation utility
# ---------------------------------------------------------------------------
def generate_encryption_key() -> str:
    """
    Generate a new Fernet-compatible encryption key.
    Print this and set as SMS_ENCRYPTION_KEY env var in Railway.
    """
    try:
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()
    except ImportError:
        # Fallback: generate 32 random bytes and base64 encode
        import secrets
        raw = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(raw).decode()


if __name__ == "__main__":
    # Run this script directly to generate a new master key
    key = generate_encryption_key()
    print(f"Generated SMS_ENCRYPTION_KEY: {key}")
    print("Add this to Railway environment variables as SMS_ENCRYPTION_KEY")
