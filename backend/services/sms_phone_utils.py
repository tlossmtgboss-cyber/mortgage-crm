import re


def normalize_phone(phone: str) -> str:
    """Strip to digits, ensure +1 prefix for US numbers."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    # Non-US or already correct — return with + prefix
    if not phone.startswith("+"):
        return "+" + digits
    return phone
