"""
Canonical PII masking functions for safe logging.

All services that need to mask PII in log messages should import from here
rather than defining their own helpers.

Usage:
    from services.pii_masking import mask_email, mask_phone

    logger.info(f"Sent to {mask_email(user.email)}")
    logger.info(f"SMS to {mask_phone(phone)}")
"""


def mask_email(email: str) -> str:
    """Mask email: j***@example.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Mask phone: +1***XXXX (last 4 digits visible)"""
    if not phone or len(phone) < 4:
        return "***"
    return f"+1***{phone[-4:]}"
