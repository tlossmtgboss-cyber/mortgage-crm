"""
White-Label & Theming Service
==============================

Enterprise Readiness Domain 12: White-Label & Theming.

Uses the WhiteLabelConfig ORM model (organization_branding table) as
the single source of truth for per-tenant branding.

Provides:
- SMS sender ID per tenant (Check 12.6)
- Favicon customization (Check 12.4)
- Font customization (Check 12.3)
- Report/PDF branding (Check 12.8)
- Branding leak scan (Check 12.12)
- Portal branding completeness check (Check 12.7)
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_COLOR_FIELDS = {"primary_color", "secondary_color", "accent_color"}

# Patterns that must never appear in font_family values (XSS vectors).
_FONT_XSS_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),       # onclick=, onerror=, etc.
    re.compile(r"expression\s*\(", re.IGNORECASE),  # CSS expression()
    re.compile(r"url\s*\(", re.IGNORECASE),         # url() injection
    re.compile(r"<\s*/?\s*\w", re.IGNORECASE),      # any HTML tag
]


def _validate_hex_color(field_name: str, value: str) -> None:
    """Raise ValueError if *value* is not a valid #RRGGBB hex color."""
    if not _HEX_COLOR_RE.match(value):
        raise ValueError(
            f"Invalid color for '{field_name}': '{value}' — "
            "expected 6-digit hex color (e.g. #1a73e8)"
        )


def _validate_font_family(value: str) -> None:
    """Raise ValueError if *value* contains XSS vectors."""
    for pattern in _FONT_XSS_PATTERNS:
        if pattern.search(value):
            raise ValueError(
                f"Invalid font_family: value contains disallowed pattern "
                f"(matched '{pattern.pattern}'). "
                "Only CSS font names are accepted."
            )


# Default platform name (should not appear in white-labeled output)
PLATFORM_NAME = "Perennia"
PLATFORM_VARIANTS = [
    "perennia", "Perennia", "PERENNIA",
    "perennia ai", "Perennia AI", "PERENNIA AI",
    "perenniaai", "PerenniaAI",
]


def _get_config(db, org_id: int):
    """Load the flat-column WhiteLabelConfig row for an org, or None.

    The organization_branding table may also contain JSONB key-value rows
    (setting_type IS NOT NULL) created by BrandingStore in
    company_branding_routes.py. We filter for the canonical flat row
    (setting_type IS NULL) to avoid picking up those rows.
    """
    from database.models.white_label_config import WhiteLabelConfig

    return (
        db.query(WhiteLabelConfig)
        .filter(
            WhiteLabelConfig.organization_id == org_id,
            WhiteLabelConfig.setting_type.is_(None),
        )
        .first()
    )


def _get_org_name(db, org_id: int) -> str:
    """Fallback: get the org name from the organizations table."""
    from sqlalchemy import text

    row = db.execute(
        text("SELECT name FROM organizations WHERE id = :org_id"),
        {"org_id": org_id},
    ).fetchone()
    return row[0] if row else "Company"


# =============================================================================
# TENANT BRANDING CONFIG (Domain 12)
# =============================================================================

def get_tenant_branding(db, org_id: int) -> Dict:
    """
    Get complete branding configuration for a tenant.
    Includes colors, logo, fonts, favicon, SMS sender, and portal settings.
    """
    config = _get_config(db, org_id)

    if not config:
        # Return defaults
        return {
            "org_id": org_id,
            "company_name": _get_org_name(db, org_id),
            "logo_url": None,
            "primary_color": "#1a73e8",
            "secondary_color": "#4285f4",
            "accent_color": "#fbbc04",
            "font_family": "Inter, system-ui, sans-serif",
            "favicon_url": None,
            "sms_sender_id": None,
            "sms_sender_name": None,
            "portal": {"logo_url": None, "title": None, "footer_text": None},
            "custom_domain": None,
            "is_white_labeled": False,
        }

    return {
        "org_id": org_id,
        "company_name": config.company_name,
        "logo_url": config.logo_url,
        "primary_color": config.primary_color or "#1a73e8",
        "secondary_color": config.secondary_color or "#4285f4",
        "accent_color": config.accent_color or "#fbbc04",
        "font_family": config.font_family or "Inter, system-ui, sans-serif",
        "favicon_url": config.favicon_url,
        "sms_sender_id": config.sms_sender_id,
        "sms_sender_name": config.sms_sender_name,
        "portal": {
            "logo_url": config.portal_logo_url,
            "title": config.portal_title,
            "footer_text": config.portal_footer_text,
        },
        "custom_domain": config.custom_domain,
        "custom_css": config.custom_css,
        "email_footer": config.email_footer,
        "email_signature": config.email_signature_template,
        "is_white_labeled": bool(config.logo_url),  # Has logo = white-labeled
    }


def update_tenant_branding(
    db, org_id: int, updates: Dict, *, user_id: Optional[int] = None
) -> Dict:
    """
    Update branding configuration for a tenant.
    Supports partial updates (only specified fields are changed).

    Validates:
      - Color fields must be valid #RRGGBB hex
      - font_family must not contain XSS vectors

    Logs every change to the server-side audit trail (AuditEvent).
    """
    from database.models.white_label_config import WhiteLabelConfig

    # Fields that can be updated
    allowed_fields = {
        "logo_url", "primary_color", "secondary_color", "accent_color",
        "email_footer", "email_signature_template",
        "company_name", "company_phone", "company_address",
        "favicon_url", "font_family", "sms_sender_id", "sms_sender_name",
        "portal_logo_url", "portal_title", "portal_footer_text",
        "custom_domain", "custom_css",
    }

    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not valid_updates:
        return {"updated": False, "reason": "No valid fields to update"}

    # ----- Input validation ---------------------------------------------------

    # Color hex validation
    for field in _COLOR_FIELDS & valid_updates.keys():
        value = valid_updates[field]
        if value is not None:
            _validate_hex_color(field, str(value))

    # Font family XSS validation
    if "font_family" in valid_updates and valid_updates["font_family"] is not None:
        _validate_font_family(str(valid_updates["font_family"]))

    # ----- Apply updates ------------------------------------------------------

    config = _get_config(db, org_id)
    is_new = config is None

    if is_new:
        config = WhiteLabelConfig(organization_id=org_id)
        db.add(config)

    # Capture old values for audit trail (before mutation)
    old_values = {}
    for key in valid_updates:
        old_values[key] = getattr(config, key, None) if not is_new else None

    for key, value in valid_updates.items():
        setattr(config, key, value)

    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    # ----- Audit trail --------------------------------------------------------
    _log_branding_change(
        db,
        org_id=org_id,
        user_id=user_id,
        fields_changed=list(valid_updates.keys()),
        old_values=old_values,
        new_values=valid_updates,
        is_new_config=is_new,
    )

    return {"updated": True, "fields": list(valid_updates.keys())}


def _log_branding_change(
    db,
    *,
    org_id: int,
    user_id: Optional[int],
    fields_changed: List[str],
    old_values: Dict,
    new_values: Dict,
    is_new_config: bool,
) -> None:
    """
    Write a CONFIG_CHANGED audit event for branding updates.
    Non-blocking — failures are logged but do not roll back the branding change.
    """
    try:
        from services.audit_events import EventType, audit_event

        audit_event(
            db,
            event_type=EventType.CONFIG_CHANGED,
            outcome="success",
            actor_id=user_id,
            org_id=org_id,
            resource_type="white_label_config",
            resource_id=str(org_id),
            metadata={
                "action": "branding_update",
                "is_new_config": is_new_config,
                "fields_changed": fields_changed,
                "old_values": {k: v for k, v in old_values.items() if v != new_values.get(k)},
                "new_values": {k: v for k, v in new_values.items() if v != old_values.get(k)},
            },
        )
        db.commit()
    except Exception as e:
        logger.exception("Failed to log branding audit event for org %s: %s", org_id, e)


# =============================================================================
# SMS SENDER ID (Domain 12, Check 12.6)
# =============================================================================

def get_sms_sender_config(db, org_id: int) -> Dict:
    """
    Get SMS sender configuration for a tenant.
    Supports custom sender ID/name per organization.
    """
    config = _get_config(db, org_id)

    default_sender = os.getenv("TELNYX_FROM_NUMBER", "")

    if config and config.sms_sender_id:
        return {
            "sender_id": config.sms_sender_id,
            "sender_name": config.sms_sender_name or config.company_name,
            "is_custom": True,
        }

    return {
        "sender_id": default_sender,
        "sender_name": None,
        "is_custom": False,
    }


# =============================================================================
# BRANDING LEAK SCAN (Domain 12, Check 12.12)
# =============================================================================

def scan_for_branding_leaks(db, org_id: int) -> Dict:
    """
    Scan for platform branding leaking into white-labeled tenant output.

    Checks:
    1. Email templates for platform name references
    2. Organization settings for unbranded defaults
    3. SMS templates for platform references
    4. Report headers/footers
    """
    leaks = []

    config = _get_config(db, org_id)

    if config:
        fields = [
            ("email_footer", config.email_footer),
            ("email_signature_template", config.email_signature_template),
            ("portal_footer_text", config.portal_footer_text),
        ]
        for field_name, value in fields:
            if value:
                for variant in PLATFORM_VARIANTS:
                    if variant in value:
                        leaks.append({
                            "location": field_name,
                            "found": variant,
                            "severity": "medium",
                            "fix": f"Replace '{variant}' with tenant company name in {field_name}",
                        })

    # Check if org still uses default branding
    branding = get_tenant_branding(db, org_id)
    if not branding.get("logo_url"):
        leaks.append({
            "location": "logo",
            "found": "No custom logo set",
            "severity": "high",
            "fix": "Upload tenant logo to replace default",
        })
    if not branding.get("favicon_url"):
        leaks.append({
            "location": "favicon",
            "found": "No custom favicon set",
            "severity": "low",
            "fix": "Upload custom favicon",
        })

    return {
        "org_id": org_id,
        "leaks_found": len(leaks),
        "leaks": leaks,
        "is_clean": len(leaks) == 0,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# PORTAL BRANDING COMPLETENESS (Domain 12, Check 12.7)
# =============================================================================

def check_portal_branding(db, org_id: int) -> Dict:
    """
    Check borrower portal branding completeness.
    """
    branding = get_tenant_branding(db, org_id)

    checks = {
        "logo": bool(branding.get("logo_url")),
        "primary_color": bool(branding.get("primary_color")),
        "secondary_color": bool(branding.get("secondary_color")),
        "portal_logo": bool(branding.get("portal", {}).get("logo_url")),
        "portal_title": bool(branding.get("portal", {}).get("title")),
        "portal_footer": bool(branding.get("portal", {}).get("footer_text")),
        "favicon": bool(branding.get("favicon_url")),
        "font_family": bool(branding.get("font_family")),
        "company_name": bool(branding.get("company_name")),
    }

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    return {
        "org_id": org_id,
        "checks": checks,
        "passed": passed,
        "total": total,
        "completion_pct": round((passed / total) * 100, 1) if total > 0 else 0,
        "is_complete": passed >= 7,  # At least 7/9 items configured
    }


# =============================================================================
# PDF/REPORT BRANDING (Domain 12, Check 12.8)
# =============================================================================

def get_report_branding(db, org_id: int) -> Dict:
    """
    Get branding configuration for PDF/Excel report generation.

    Returns colors, logo URL, company name, and font for report headers/footers.
    """
    branding = get_tenant_branding(db, org_id)

    return {
        "company_name": branding.get("company_name", ""),
        "logo_url": branding.get("logo_url"),
        "primary_color": branding.get("primary_color", "#1a73e8"),
        "secondary_color": branding.get("secondary_color", "#4285f4"),
        "accent_color": branding.get("accent_color", "#fbbc04"),
        "font_family": branding.get("font_family", "Helvetica"),
    }
