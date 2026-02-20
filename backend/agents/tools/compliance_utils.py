"""
Perennia AI - Compliance Gate Tools
====================================
Tools providing compliance gate functions for outbound contact tools.
4 tools for DNC checking, TCPA consent verification, calling window
validation, and composite outbound contact validation.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
)


# =============================================================================
# Timezone offset map for calling window validation
# =============================================================================

# UTC offsets in hours for common US timezones (standard / daylight)
# We use a simple lookup rather than requiring pytz
_TIMEZONE_OFFSETS: Dict[str, float] = {
    "America/New_York": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Los_Angeles": -8,
    "America/Phoenix": -7,
    "America/Anchorage": -9,
    "Pacific/Honolulu": -10,
    "US/Eastern": -5,
    "US/Central": -6,
    "US/Mountain": -7,
    "US/Pacific": -8,
    "EST": -5,
    "CST": -6,
    "MST": -7,
    "PST": -8,
    "EDT": -4,
    "CDT": -5,
    "MDT": -6,
    "PDT": -7,
}

# TCPA-compliant calling window (local time)
CALLING_WINDOW_START = 8   # 8:00 AM
CALLING_WINDOW_END = 21    # 9:00 PM


# =============================================================================
# Compliance Gate Tools (4 tools)
# =============================================================================

@mortgage_tool(
    name="check_dnc_status",
    description="Check whether a phone number is on the Do-Not-Call list",
    agent_roles=["voice_os", "notification_center", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "phone": "Phone number to check against DNC registry",
    },
)
def check_dnc_status(
    phone: str,
) -> ToolResult:
    """Check DNC status for a phone number."""
    if not phone or not phone.strip():
        return ToolResult.error("Phone number is required")

    # Normalize phone: strip whitespace, dashes, parens, spaces
    normalized = phone.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "")

    record = execute_single("""
        SELECT
            id, phone_number, reason, added_by_id, created_at
        FROM contact_dnc_status
        WHERE phone_number = :phone
    """, {"phone": normalized})

    if record:
        return ToolResult.success(
            data={
                "phone": normalized,
                "on_dnc": True,
                "reason": record.get("reason"),
                "added_at": record.get("created_at").isoformat() if record.get("created_at") else None,
                "added_by_id": record.get("added_by_id"),
            },
            message=f"BLOCKED: {normalized} is on the Do-Not-Call list",
        )

    return ToolResult.success(
        data={
            "phone": normalized,
            "on_dnc": False,
            "reason": None,
        },
        message=f"CLEAR: {normalized} is not on the Do-Not-Call list",
    )


@mortgage_tool(
    name="check_tcpa_consent",
    description="Check TCPA consent status for a contact by email and channel. "
                "BorrowerProfile has no phone column; matches on email only. "
                "For SMS channel, both communication_consent AND marketing_consent must be True.",
    agent_roles=["voice_os", "notification_center", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "contact_email": "Contact email to look up consent in borrower_profiles",
        "channel": "Outbound channel: call, sms, email",
    },
)
def check_tcpa_consent(
    contact_email: str,
    channel: str = "call",
) -> ToolResult:
    """Check TCPA consent for a contact email and channel."""
    if not contact_email or not contact_email.strip():
        return ToolResult.error("Contact email is required")

    profile = execute_single("""
        SELECT
            id, email,
            communication_consent,
            marketing_consent,
            consent_captured_at,
            consent_method
        FROM borrower_profiles
        WHERE email = :email
    """, {"email": contact_email.strip().lower()})

    if not profile:
        return ToolResult.error(
            error=f"No borrower profile found for {contact_email}",
            message=f"BLOCKED: No consent record found for {contact_email}. Cannot proceed without consent on file.",
        )

    communication_consent = bool(profile.get("communication_consent"))
    marketing_consent = bool(profile.get("marketing_consent"))

    # Determine consent based on channel
    channel_lower = channel.strip().lower()
    has_consent = False
    reason = ""

    if channel_lower == "sms":
        # SMS requires BOTH communication AND marketing consent
        has_consent = communication_consent and marketing_consent
        if not has_consent:
            missing = []
            if not communication_consent:
                missing.append("communication_consent")
            if not marketing_consent:
                missing.append("marketing_consent")
            reason = f"SMS requires both communication_consent and marketing_consent. Missing: {', '.join(missing)}"
    elif channel_lower in ("call", "phone"):
        # Calls require communication consent
        has_consent = communication_consent
        if not has_consent:
            reason = "Call requires communication_consent, which is False"
    elif channel_lower == "email":
        # Email requires communication consent
        has_consent = communication_consent
        if not has_consent:
            reason = "Email requires communication_consent, which is False"
    else:
        # Unknown channel -- require communication consent as baseline
        has_consent = communication_consent
        if not has_consent:
            reason = f"Channel '{channel}' requires communication_consent, which is False"

    consent_data = {
        "contact_email": contact_email,
        "channel": channel,
        "has_consent": has_consent,
        "communication_consent": communication_consent,
        "marketing_consent": marketing_consent,
        "consent_captured_at": profile.get("consent_captured_at").isoformat() if profile.get("consent_captured_at") else None,
        "consent_method": profile.get("consent_method"),
    }

    if has_consent:
        return ToolResult.success(
            data=consent_data,
            message=f"CLEAR: Consent verified for {channel} to {contact_email}",
        )
    else:
        consent_data["block_reason"] = reason
        return ToolResult.error(
            error=f"BLOCKED: No {channel} consent for {contact_email}. {reason}",
            message=f"BLOCKED: No {channel} consent for {contact_email}. {reason}",
        )


@mortgage_tool(
    name="check_calling_window",
    description="Validate that current time is within TCPA-compliant calling hours (8 AM - 9 PM) "
                "in the contact's local timezone. Returns error if outside the window.",
    agent_roles=["voice_os", "notification_center", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "phone": "Phone number (used for logging/context)",
        "timezone": "IANA timezone string (default: America/New_York)",
    },
)
def check_calling_window(
    phone: str,
    timezone: Optional[str] = None,
) -> ToolResult:
    """Validate calling window for a phone number in the given timezone."""
    if not phone or not phone.strip():
        return ToolResult.error("Phone number is required")

    tz_name = timezone or "America/New_York"
    utc_offset = _TIMEZONE_OFFSETS.get(tz_name)

    if utc_offset is None:
        # Attempt to parse as a numeric offset like "-5" or "+5.5"
        try:
            utc_offset = float(tz_name)
        except (ValueError, TypeError):
            return ToolResult.error(
                f"Unrecognized timezone '{tz_name}'. Use an IANA name like 'America/New_York' "
                f"or a numeric UTC offset like '-5'."
            )

    # Calculate local time from UTC
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(hours=utc_offset)
    local_hour = local_now.hour
    local_minute = local_now.minute

    within_window = CALLING_WINDOW_START <= local_hour < CALLING_WINDOW_END

    window_data = {
        "phone": phone.strip(),
        "timezone": tz_name,
        "utc_offset_hours": utc_offset,
        "local_time": local_now.strftime("%I:%M %p"),
        "local_hour": local_hour,
        "local_minute": local_minute,
        "window_start": f"{CALLING_WINDOW_START}:00 AM",
        "window_end": f"{CALLING_WINDOW_END - 12}:00 PM",
        "within_window": within_window,
    }

    if within_window:
        return ToolResult.success(
            data=window_data,
            message=f"CLEAR: Local time is {local_now.strftime('%I:%M %p')} {tz_name} -- within calling window",
        )
    else:
        return ToolResult.error(
            error=(
                f"BLOCKED: Local time is {local_now.strftime('%I:%M %p')} {tz_name}. "
                f"Outside TCPA calling window ({CALLING_WINDOW_START}:00 AM - {CALLING_WINDOW_END - 12}:00 PM)."
            ),
            message=(
                f"BLOCKED: Local time is {local_now.strftime('%I:%M %p')} {tz_name}. "
                f"Outside TCPA calling window ({CALLING_WINDOW_START}:00 AM - {CALLING_WINDOW_END - 12}:00 PM)."
            ),
        )


@mortgage_tool(
    name="validate_outbound_contact",
    description="Composite compliance gate that runs DNC check, TCPA consent check, and calling "
                "window validation. Returns error on any failure, success with clearance data on pass.",
    agent_roles=["voice_os", "notification_center", "lead_nurturer", "ai_receptionist", "smart_scheduler"],
    risk_level="LOW",
    parameters={
        "phone": "Phone number for outbound contact",
        "channel": "Contact channel: call, sms, email",
        "contact_email": "Contact email for consent lookup (required for sms/call)",
        "timezone": "IANA timezone of the contact (default: America/New_York)",
    },
)
def validate_outbound_contact(
    phone: str,
    channel: str = "call",
    contact_email: Optional[str] = None,
    timezone: Optional[str] = None,
) -> ToolResult:
    """Composite compliance gate for outbound contact.

    Runs all three checks in sequence:
      1. DNC status check
      2. TCPA consent check (if contact_email provided)
      3. Calling window check (for call/sms channels)

    Returns ToolResult.error on the first failure, or ToolResult.success
    with full clearance data if all checks pass.
    """
    if not phone or not phone.strip():
        return ToolResult.error("Phone number is required")

    clearance = {
        "phone": phone.strip(),
        "channel": channel,
        "contact_email": contact_email,
        "timezone": timezone or "America/New_York",
        "checks": {},
    }

    # -----------------------------------------------------------------------
    # 1. DNC check
    # -----------------------------------------------------------------------
    dnc_result = check_dnc_status(phone)
    if dnc_result.status.value == "error":
        return ToolResult.error(
            error=f"DNC check failed: {dnc_result.error}",
            message=f"DNC check failed: {dnc_result.error}",
        )

    dnc_data = dnc_result.data or {}
    if dnc_data.get("on_dnc"):
        clearance["checks"]["dnc"] = {"passed": False, "reason": dnc_data.get("reason")}
        return ToolResult.error(
            error=f"BLOCKED: Phone {phone} is on the Do-Not-Call list. Reason: {dnc_data.get('reason')}",
            message=f"BLOCKED: Phone {phone} is on the Do-Not-Call list. Reason: {dnc_data.get('reason')}",
        )

    clearance["checks"]["dnc"] = {"passed": True}

    # -----------------------------------------------------------------------
    # 2. TCPA consent check
    # -----------------------------------------------------------------------
    if contact_email:
        consent_result = check_tcpa_consent(contact_email, channel)
        if consent_result.status.value == "error":
            clearance["checks"]["tcpa_consent"] = {
                "passed": False,
                "reason": consent_result.error,
            }
            return ToolResult.error(
                error=f"TCPA consent check failed: {consent_result.error}",
                message=f"TCPA consent check failed: {consent_result.error}",
            )

        consent_data = consent_result.data or {}
        clearance["checks"]["tcpa_consent"] = {
            "passed": True,
            "communication_consent": consent_data.get("communication_consent"),
            "marketing_consent": consent_data.get("marketing_consent"),
        }
    else:
        clearance["checks"]["tcpa_consent"] = {
            "passed": None,
            "reason": "No contact_email provided -- consent not verified",
        }

    # -----------------------------------------------------------------------
    # 3. Calling window check (for call and sms channels)
    # -----------------------------------------------------------------------
    channel_lower = channel.strip().lower()
    if channel_lower in ("call", "phone", "sms"):
        window_result = check_calling_window(phone, timezone)
        if window_result.status.value == "error":
            clearance["checks"]["calling_window"] = {
                "passed": False,
                "reason": window_result.error,
            }
            return ToolResult.error(
                error=f"Calling window check failed: {window_result.error}",
                message=f"Calling window check failed: {window_result.error}",
            )

        window_data = window_result.data or {}
        clearance["checks"]["calling_window"] = {
            "passed": True,
            "local_time": window_data.get("local_time"),
            "timezone": window_data.get("timezone"),
        }
    else:
        # Email and other channels don't have time-of-day restrictions
        clearance["checks"]["calling_window"] = {
            "passed": True,
            "reason": f"No calling window restriction for channel '{channel}'",
        }

    # -----------------------------------------------------------------------
    # All checks passed
    # -----------------------------------------------------------------------
    clearance["cleared"] = True
    clearance["cleared_at"] = datetime.now().isoformat()

    return ToolResult.success(
        data=clearance,
        message=f"CLEARED: All compliance checks passed for {channel} to {phone}",
    )
