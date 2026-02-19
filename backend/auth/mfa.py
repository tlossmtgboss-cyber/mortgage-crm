"""
Multi-Factor Authentication (MFA) via TOTP
Enterprise Readiness Check 4.6

Implements Time-based One-Time Password (TOTP) authentication using pyotp.
Provides:
- Secret generation and QR code creation for initial setup
- Token verification for login flow
- Backup code generation for recovery
"""
import base64
import hashlib
import io
import logging
import secrets
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# App name shown in authenticator apps
MFA_ISSUER_NAME = "Perennia AI"
BACKUP_CODE_COUNT = 10


def generate_mfa_secret(user_email: str) -> dict:
    """
    Generate a new MFA secret and provisioning URI for QR code.

    Args:
        user_email: The user's email address for the TOTP label.

    Returns:
        dict with 'secret', 'provisioning_uri', and optionally 'qr_code_base64'.
    """
    try:
        import pyotp
    except ImportError:
        logger.error("pyotp not installed. Install with: pip install pyotp")
        raise RuntimeError("MFA dependency 'pyotp' is not installed")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user_email,
        issuer_name=MFA_ISSUER_NAME,
    )

    result = {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
    }

    # Try to generate QR code if qrcode library is available
    qr_base64 = generate_qr_code(provisioning_uri)
    if qr_base64:
        result["qr_code_base64"] = qr_base64

    return result


def verify_mfa_token(secret: str, token: str) -> bool:
    """
    Verify a TOTP token against the given secret.

    Args:
        secret: The TOTP secret (base32 encoded).
        token: The 6-digit token from the authenticator app.

    Returns:
        True if the token is valid, False otherwise.
    """
    try:
        import pyotp
    except ImportError:
        logger.error("pyotp not installed")
        return False

    totp = pyotp.TOTP(secret)
    # valid_window=1 allows the previous and next token to account for clock drift
    return totp.verify(token, valid_window=1)


def generate_qr_code(provisioning_uri: str) -> Optional[str]:
    """
    Generate a QR code image as a base64-encoded PNG string.

    Args:
        provisioning_uri: The otpauth:// URI to encode.

    Returns:
        Base64-encoded PNG string, or None if qrcode library is not available.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage
    except ImportError:
        logger.warning("qrcode or Pillow not installed. QR code generation disabled. "
                       "Install with: pip install qrcode[pil]")
        return None

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        return None


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> Tuple[List[str], List[str]]:
    """
    Generate backup codes for MFA recovery.

    Returns:
        Tuple of (plain_codes, hashed_codes).
        plain_codes: Show to user once for them to save.
        hashed_codes: Store in database for verification.
    """
    plain_codes = []
    hashed_codes = []

    for _ in range(count):
        # Generate 8-character alphanumeric code
        code = secrets.token_hex(4).upper()  # 8 hex chars
        formatted = f"{code[:4]}-{code[4:]}"  # e.g., "A1B2-C3D4"
        plain_codes.append(formatted)
        hashed_codes.append(_hash_backup_code(formatted))

    return plain_codes, hashed_codes


def verify_backup_code(code: str, hashed_codes: List[str]) -> Optional[int]:
    """
    Verify a backup code against the stored hashed codes.

    Args:
        code: The backup code to verify.
        hashed_codes: List of hashed backup codes from the database.

    Returns:
        Index of the matched code (for removal), or None if not found.
    """
    code_hash = _hash_backup_code(code.strip().upper())
    for i, stored_hash in enumerate(hashed_codes):
        if stored_hash == code_hash:
            return i
    return None


def _hash_backup_code(code: str) -> str:
    """Hash a backup code using SHA-256."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
