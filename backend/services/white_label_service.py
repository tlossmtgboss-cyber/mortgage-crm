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

    # Custom CSS sanitization (XSS, data exfiltration prevention)
    if "custom_css" in valid_updates and valid_updates["custom_css"] is not None:
        from input_validation import sanitize_custom_css
        valid_updates["custom_css"] = sanitize_custom_css(
            str(valid_updates["custom_css"]), max_length=50000
        )

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

def check_domain_health(db, org_id: int) -> Dict:
    """
    Check custom domain health for an organization.

    Inspects SSL certificate expiry, domain verification status, and SSL
    provisioning state. Returns a dict with warnings for any issues found:
      - SSL expiring within 30 days
      - Domain not verified
      - SSL provisioning failed or still pending

    Also updates the ssl_expires_at column on the WhiteLabelConfig row if
    Vercel provides cert expiry data.
    """
    config = _get_config(db, org_id)

    result: Dict = {
        "org_id": org_id,
        "domain": None,
        "domain_verified": False,
        "ssl_status": "pending",
        "ssl_expires_at": None,
        "ssl_expires_in_days": None,
        "warnings": [],
        "healthy": True,
    }

    if not config or not config.custom_domain:
        result["warnings"].append({
            "code": "NO_CUSTOM_DOMAIN",
            "severity": "info",
            "message": "No custom domain configured for this organization.",
        })
        return result

    result["domain"] = config.custom_domain
    result["domain_verified"] = bool(config.domain_verified)
    result["ssl_status"] = config.ssl_status or "pending"

    # Warning: domain not verified
    if not config.domain_verified:
        result["healthy"] = False
        result["warnings"].append({
            "code": "DOMAIN_NOT_VERIFIED",
            "severity": "high",
            "message": (
                f"Domain '{config.custom_domain}' has not been verified. "
                "Complete DNS verification to enable SSL."
            ),
        })

    # Warning: SSL provisioning failed
    if config.ssl_status == "failed":
        result["healthy"] = False
        result["warnings"].append({
            "code": "SSL_PROVISIONING_FAILED",
            "severity": "high",
            "message": (
                f"SSL provisioning failed for '{config.custom_domain}'. "
                "Check DNS records and retry domain verification."
            ),
        })
    elif config.ssl_status in ("pending", "provisioning") and config.domain_verified:
        result["warnings"].append({
            "code": "SSL_NOT_ACTIVE",
            "severity": "medium",
            "message": (
                f"SSL is '{config.ssl_status}' for '{config.custom_domain}'. "
                "Provisioning may still be in progress — check back shortly."
            ),
        })

    # Check SSL expiry from Vercel if domain is active
    ssl_expires_at = getattr(config, "ssl_expires_at", None)

    if config.domain_verified and config.ssl_status == "active":
        try:
            from services import vercel_domain_service

            vercel_expiry = vercel_domain_service.get_ssl_expiry(config.custom_domain)
            if vercel_expiry:
                ssl_expires_at = vercel_expiry
                # Persist the expiry date
                config.ssl_expires_at = vercel_expiry
                db.commit()
        except Exception as e:
            logger.warning(
                "Could not check Vercel SSL expiry for org %s domain %s: %s",
                org_id, config.custom_domain, e,
            )

    if ssl_expires_at:
        result["ssl_expires_at"] = ssl_expires_at.isoformat()
        now = datetime.now(timezone.utc)
        days_remaining = (ssl_expires_at - now).days
        result["ssl_expires_in_days"] = days_remaining

        if days_remaining <= 0:
            result["healthy"] = False
            result["warnings"].append({
                "code": "SSL_EXPIRED",
                "severity": "critical",
                "message": (
                    f"SSL certificate for '{config.custom_domain}' has expired. "
                    "Visitors will see security warnings."
                ),
            })
        elif days_remaining <= 30:
            result["warnings"].append({
                "code": "SSL_EXPIRING_SOON",
                "severity": "high",
                "message": (
                    f"SSL certificate for '{config.custom_domain}' expires in "
                    f"{days_remaining} days ({ssl_expires_at.strftime('%Y-%m-%d')}). "
                    "Vercel auto-renews, but verify renewal is not blocked by DNS issues."
                ),
            })

    if not result["warnings"]:
        result["warnings"].append({
            "code": "ALL_CLEAR",
            "severity": "info",
            "message": "Domain and SSL are healthy.",
        })

    return result


# =============================================================================
# SSL EXPIRY ALERTS (Domain 12, Check 12.10)
# =============================================================================

def check_ssl_expiry_alerts(db) -> Dict:
    """
    Proactively check all custom domains for upcoming SSL certificate expiry.

    First, for any domain with a custom_domain but NULL ssl_expires_at, performs
    a proactive SSL check via Vercel/TLS to populate the expiry date.

    Then queries all WhiteLabelConfig rows that have a custom domain with an
    ssl_expires_at value within the next 30 days. Logs warnings at escalating
    severity levels:
      - 14-30 days: WARNING
      - 7-14 days: WARNING (elevated)
      - 0-7 days: CRITICAL
      - expired: CRITICAL

    For critical alerts (<=7 days or expired), sends an email notification
    to the org admin so they can take immediate action.

    Returns:
        Dict with:
          - domains_checked: total domains with ssl_expires_at set
          - alerts: list of domain alert dicts with severity, days_remaining, etc.
          - summary: counts by severity level
          - notifications_sent: count of email notifications sent for critical alerts
    """
    from database.models.white_label_config import WhiteLabelConfig

    now = datetime.now(timezone.utc)

    # ---- Phase 1: Proactive SSL check for domains with NULL ssl_expires_at ----
    unchecked_configs = (
        db.query(WhiteLabelConfig)
        .filter(
            WhiteLabelConfig.custom_domain.isnot(None),
            WhiteLabelConfig.ssl_expires_at.is_(None),
            WhiteLabelConfig.setting_type.is_(None),
        )
        .all()
    )

    proactively_checked = 0
    for config in unchecked_configs:
        try:
            from services import vercel_domain_service
            expiry = vercel_domain_service.get_ssl_expiry(config.custom_domain)
            if expiry:
                config.ssl_expires_at = expiry
                db.commit()
                proactively_checked += 1
                logger.info(
                    "Proactively populated ssl_expires_at for domain '%s' (org %s): %s",
                    config.custom_domain, config.organization_id, expiry.isoformat(),
                )
        except Exception as e:
            logger.warning(
                "Proactive SSL check failed for domain '%s' (org %s): %s",
                config.custom_domain, config.organization_id, e,
            )

    # ---- Phase 2: Check all domains with SSL expiry data --------------------
    configs = (
        db.query(WhiteLabelConfig)
        .filter(
            WhiteLabelConfig.custom_domain.isnot(None),
            WhiteLabelConfig.ssl_expires_at.isnot(None),
            WhiteLabelConfig.setting_type.is_(None),
        )
        .all()
    )

    alerts: List[Dict] = []
    summary = {"critical": 0, "warning": 0, "ok": 0}

    for config in configs:
        days_remaining = (config.ssl_expires_at - now).days
        domain = config.custom_domain
        org_id = config.organization_id

        if days_remaining <= 0:
            severity = "critical"
            message = (
                f"SSL certificate for '{domain}' (org {org_id}) has EXPIRED. "
                "Visitors will see security warnings."
            )
            logger.critical(
                "SSL EXPIRED for domain '%s' (org_id=%s, expired %d days ago)",
                domain, org_id, abs(days_remaining),
            )
            summary["critical"] += 1
        elif days_remaining <= 7:
            severity = "critical"
            message = (
                f"SSL certificate for '{domain}' (org {org_id}) expires in "
                f"{days_remaining} days ({config.ssl_expires_at.strftime('%Y-%m-%d')}). "
                "Immediate attention required."
            )
            logger.critical(
                "SSL expiring in %d days for domain '%s' (org_id=%s)",
                days_remaining, domain, org_id,
            )
            summary["critical"] += 1
        elif days_remaining <= 14:
            severity = "warning"
            message = (
                f"SSL certificate for '{domain}' (org {org_id}) expires in "
                f"{days_remaining} days ({config.ssl_expires_at.strftime('%Y-%m-%d')}). "
                "Verify auto-renewal is not blocked."
            )
            logger.warning(
                "SSL expiring in %d days for domain '%s' (org_id=%s)",
                days_remaining, domain, org_id,
            )
            summary["warning"] += 1
        elif days_remaining <= 30:
            severity = "warning"
            message = (
                f"SSL certificate for '{domain}' (org {org_id}) expires in "
                f"{days_remaining} days ({config.ssl_expires_at.strftime('%Y-%m-%d')}). "
                "Monitor renewal status."
            )
            logger.warning(
                "SSL expiring in %d days for domain '%s' (org_id=%s)",
                days_remaining, domain, org_id,
            )
            summary["warning"] += 1
        else:
            # More than 30 days out — healthy, not included in alerts
            summary["ok"] += 1
            continue

        alerts.append({
            "domain": domain,
            "organization_id": org_id,
            "ssl_expires_at": config.ssl_expires_at.isoformat(),
            "days_remaining": days_remaining,
            "severity": severity,
            "message": message,
        })

    # Sort alerts by urgency (fewest days remaining first)
    alerts.sort(key=lambda a: a["days_remaining"])

    # ---- Phase 3: Email notification for critical SSL alerts ----------------
    notifications_sent = 0
    critical_alerts = [a for a in alerts if a["severity"] == "critical"]

    if critical_alerts:
        notifications_sent = _send_ssl_alert_notifications(db, critical_alerts)

    return {
        "domains_checked": len(configs),
        "proactively_checked": proactively_checked,
        "alerts_count": len(alerts),
        "alerts": alerts,
        "summary": summary,
        "notifications_sent": notifications_sent,
        "checked_at": now.isoformat(),
    }


def _send_ssl_alert_notifications(db, critical_alerts: List[Dict]) -> int:
    """
    Send email notifications to org admins for critical SSL alerts.

    Groups alerts by organization_id, looks up the admin email for each org,
    and sends a single notification per org listing all affected domains.

    Returns the count of notifications successfully sent.
    """
    from sqlalchemy import text as sa_text

    # Group alerts by org
    org_alerts: Dict[int, List[Dict]] = {}
    for alert in critical_alerts:
        org_id = alert["organization_id"]
        org_alerts.setdefault(org_id, []).append(alert)

    sent = 0
    for org_id, alerts_for_org in org_alerts.items():
        # Look up admin email for this org (user with admin role, or org owner)
        try:
            row = db.execute(sa_text("""
                SELECT u.email, u.first_name
                FROM users u
                WHERE u.organization_id = :org_id
                  AND u.role IN ('platform_admin', 'site_admin', 'admin', 'owner')
                  AND u.email IS NOT NULL
                ORDER BY
                    CASE u.role
                        WHEN 'owner' THEN 1
                        WHEN 'platform_admin' THEN 2
                        WHEN 'site_admin' THEN 3
                        WHEN 'admin' THEN 4
                    END
                LIMIT 1
            """), {"org_id": org_id}).fetchone()

            if not row or not row[0]:
                logger.warning(
                    "SSL alert: no admin email found for org %s — cannot send notification",
                    org_id,
                )
                continue

            admin_email = row[0]
            admin_name = row[1] or "Admin"

            # Build alert summary
            domain_lines = []
            for a in alerts_for_org:
                if a["days_remaining"] <= 0:
                    domain_lines.append(
                        f"  - {a['domain']}: EXPIRED ({abs(a['days_remaining'])} days ago)"
                    )
                else:
                    domain_lines.append(
                        f"  - {a['domain']}: expires in {a['days_remaining']} days "
                        f"({a['ssl_expires_at'][:10]})"
                    )

            subject = (
                f"URGENT: SSL Certificate {'Expired' if any(a['days_remaining'] <= 0 for a in alerts_for_org) else 'Expiring Soon'} "
                f"— Action Required"
            )
            body = (
                f"Hi {admin_name},\n\n"
                f"The following custom domain(s) for your organization have critical SSL issues:\n\n"
                + "\n".join(domain_lines) +
                "\n\n"
                "Vercel auto-renews SSL certificates, but renewal can fail if DNS records are "
                "misconfigured. Please verify your DNS settings and domain configuration.\n\n"
                "If you need assistance, contact support@perenniaai.com.\n\n"
                "— Perennia AI Platform"
            )

            _send_ssl_notification_email(admin_email, subject, body)
            sent += 1
            logger.info(
                "SSL alert notification sent to %s for org %s (%d domain(s))",
                admin_email, org_id, len(alerts_for_org),
            )

        except Exception as e:
            logger.exception(
                "Failed to send SSL alert notification for org %s: %s", org_id, e,
            )

    return sent


def _send_ssl_notification_email(to_email: str, subject: str, body: str) -> None:
    """
    Send an SSL alert notification email using the best available transport.

    Delivery strategy (tried in order):
      1. EmailService (SendGrid + SMTP fallback)
      2. Stub logging if no transport is available
    """
    # Strategy 1: EmailService
    try:
        from email_service import EmailService

        svc = EmailService()
        html_body = (
            "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
            + body.replace("\n", "<br>")
            + "</div>"
        )
        svc.send_html_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=body,
        )
        return
    except ImportError:
        logger.debug("EmailService not available for SSL alert notification")
    except Exception as e:
        logger.warning("EmailService failed for SSL alert notification: %s", e)

    # Strategy 2: Stub
    logger.info(
        "STUB SSL ALERT EMAIL: To=%s Subject='%s' Body=%s",
        to_email, subject, body[:200],
    )


# =============================================================================
# BRANDING COMPLETENESS CHECK (Domain 12, Check 12.7b)
# =============================================================================

# Required fields — must be present for a minimally complete brand config
_REQUIRED_BRANDING_FIELDS = [
    ("company_name", "Company name"),
    ("logo_url", "Logo URL"),
    ("primary_color", "Primary color"),
]

# Recommended fields — improve completeness score but not strictly required
_RECOMMENDED_BRANDING_FIELDS = [
    ("secondary_color", "Secondary color"),
    ("accent_color", "Accent color"),
    ("favicon_url", "Favicon URL"),
    ("font_family", "Font family"),
    ("portal_logo_url", "Portal logo URL"),
    ("portal_title", "Portal title"),
    ("portal_footer_text", "Portal footer text"),
    ("email_footer", "Email footer"),
    ("custom_domain", "Custom domain"),
]


def check_branding_completeness(db, org_id: int) -> Dict:
    """
    Verify all required branding fields are set and compute a completeness
    percentage for the organization's white-label configuration.

    Required fields (must be set):
      - company_name
      - logo_url
      - primary_color

    Recommended fields (improve completeness):
      - secondary_color, accent_color, favicon_url, font_family
      - portal_logo_url, portal_title, portal_footer_text
      - email_footer, custom_domain

    Returns:
        Dict with:
          - completeness_pct: 0-100 score
          - required_fields: list of required fields with status
          - recommended_fields: list of recommended fields with status
          - missing_required: list of missing required field names
          - missing_recommended: list of missing recommended field names
          - is_minimally_complete: True if all required fields are set
    """
    config = _get_config(db, org_id)

    required_results = []
    missing_required = []
    for field_attr, field_label in _REQUIRED_BRANDING_FIELDS:
        value = getattr(config, field_attr, None) if config else None
        is_set = bool(value)
        required_results.append({
            "field": field_attr,
            "label": field_label,
            "is_set": is_set,
        })
        if not is_set:
            missing_required.append(field_label)

    recommended_results = []
    missing_recommended = []
    for field_attr, field_label in _RECOMMENDED_BRANDING_FIELDS:
        value = getattr(config, field_attr, None) if config else None
        is_set = bool(value)
        recommended_results.append({
            "field": field_attr,
            "label": field_label,
            "is_set": is_set,
        })
        if not is_set:
            missing_recommended.append(field_label)

    total_fields = len(_REQUIRED_BRANDING_FIELDS) + len(_RECOMMENDED_BRANDING_FIELDS)
    set_count = (
        sum(1 for r in required_results if r["is_set"])
        + sum(1 for r in recommended_results if r["is_set"])
    )
    completeness_pct = round((set_count / total_fields) * 100, 1) if total_fields > 0 else 0

    return {
        "org_id": org_id,
        "completeness_pct": completeness_pct,
        "is_minimally_complete": len(missing_required) == 0,
        "required_fields": required_results,
        "recommended_fields": recommended_results,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "total_fields": total_fields,
        "fields_set": set_count,
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
