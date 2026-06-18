"""
Scheduler PII masking — attendee email and phone masking for API responses.

Enterprise compliance (Domains 3 & 4): attendee_email and attendee_phone must
be masked for non-owner API consumers (third-party integrations, read-only API
keys, team members viewing others' appointments).

Who sees unmasked data:
  - The assigned LO (current_user.id == appointment.assigned_user_id)
  - Org admins (permission_role in admin, site_admin, platform_admin)
  - The user who created the appointment (created_by_user_id)

Everyone else gets masked values.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def mask_email(email: Optional[str]) -> Optional[str]:
    """Mask attendee email for non-privileged API consumers.

    Example: john.doe@example.com -> j***@example.com
    """
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask attendee phone for non-privileged API consumers.

    Example: +14155551234 -> ***-***-1234
    """
    if not phone:
        return phone
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return "***-***-****"
    return f"***-***-{digits[-4:]}"


def should_unmask(current_user, appointment) -> bool:
    """Return True if current_user may see unmasked attendee PII for this appointment.

    Privileged viewers:
      - Admin roles (admin, site_admin, platform_admin)
      - The assigned loan officer (assigned_user_id match)
      - The user who created the appointment (created_by_user_id match)
    """
    if not current_user:
        return False

    role = (
        getattr(current_user, 'permission_role', '') or
        getattr(current_user, 'role', '') or
        ''
    ).lower()
    if role in ('admin', 'site_admin', 'platform_admin'):
        return True

    user_id = str(getattr(current_user, 'id', ''))
    if user_id and user_id == str(getattr(appointment, 'assigned_user_id', '')):
        return True
    if user_id and user_id == str(getattr(appointment, 'created_by_user_id', '')):
        return True

    return False


def apply_pii_mask(appt_dict: dict, current_user, appointment) -> dict:
    """Apply PII masking to a serialized appointment dict when not privileged.

    Modifies and returns appt_dict. Logs a debug message when masking is applied.

    Args:
        appt_dict: The serialized appointment response dict (may be mutated).
        current_user: The authenticated user object.
        appointment: The SQLAlchemy Appointment model instance (used for ownership check).

    Returns:
        The (possibly modified) appt_dict.
    """
    if should_unmask(current_user, appointment):
        return appt_dict

    appt_id = appt_dict.get('id', getattr(appointment, 'id', '?'))
    user_id = getattr(current_user, 'id', '?')
    logger.debug("PII masked for appointment %s, viewer %s", appt_id, user_id)

    if 'attendee_email' in appt_dict:
        appt_dict['attendee_email'] = mask_email(appt_dict['attendee_email'])
    if 'attendee_phone' in appt_dict:
        appt_dict['attendee_phone'] = mask_phone(appt_dict['attendee_phone'])

    return appt_dict
