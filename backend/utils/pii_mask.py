"""
PII masking utilities for safe logging.

Usage:
    from utils.pii_mask import mask_email, mask_phone, mask_name

    logger.info(f"User logged in: {mask_email(user.email)}")
    logger.info(f"SMS sent to {mask_phone(phone_number)}")
"""


def mask_email(email: str) -> str:
    """Mask email: 'user@example.com' -> 'u***@e***.com'"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    parts = domain.rsplit(".", 1)
    masked_local = local[0] + "***" if local else "***"
    masked_domain = parts[0][0] + "***" if parts[0] else "***"
    suffix = "." + parts[1] if len(parts) > 1 else ""
    return f"{masked_local}@{masked_domain}{suffix}"


def mask_phone(phone: str) -> str:
    """Mask phone: '+18005551234' -> '***1234'"""
    if not phone:
        return "***"
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"


def mask_name(name: str) -> str:
    """Mask name: 'John Doe' -> 'J*** D***'"""
    if not name:
        return "***"
    parts = name.split()
    return " ".join(p[0] + "***" if p else "***" for p in parts)
