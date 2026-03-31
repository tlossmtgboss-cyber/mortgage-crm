"""
Password Policy — Unified password validation.

Usage:
    from utils.password_policy import validate_password, PASSWORD_REQUIREMENTS
"""

from fastapi import HTTPException


PASSWORD_REQUIREMENTS = {
    "min_length": 8,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
}


def validate_password(password: str) -> None:
    """
    Validate password against the unified policy.
    Raises HTTPException(400) if password doesn't meet requirements.
    """
    if not password or len(password) < PASSWORD_REQUIREMENTS["min_length"]:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {PASSWORD_REQUIREMENTS['min_length']} characters"
        )
    if PASSWORD_REQUIREMENTS["require_uppercase"] and not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter"
        )
    if PASSWORD_REQUIREMENTS["require_lowercase"] and not any(c.islower() for c in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one lowercase letter"
        )
    if PASSWORD_REQUIREMENTS["require_digit"] and not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one digit"
        )
