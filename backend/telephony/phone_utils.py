"""Canonical phone number normalization utilities.

All SMS/telephony code should import from here instead of defining local copies.
"""
import re
from typing import Optional


def normalize_phone(phone: str) -> Optional[str]:
    """Normalize any phone format to E.164 (+1XXXXXXXXXX).

    Returns None if the input cannot be normalized to a valid US phone number.
    """
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return None


def digits_only(phone: str) -> str:
    """Strip non-digit characters and leading US country code.

    Returns the 10-digit national number for US phones (11 digits starting
    with '1'), or the raw digits for everything else.  This makes lookups
    consistent regardless of whether the stored value includes the country
    code prefix.
    """
    digits = re.sub(r"[^\d]", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def mask_phone(phone: str) -> str:
    """Mask phone number for logging -- show only last 4 digits."""
    if not phone or len(phone) < 4:
        return "????"
    return f"...{phone[-4:]}"
