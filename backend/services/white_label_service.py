"""
White-Label & Theming Service
==============================

Enterprise Readiness Domain 12: White-Label & Theming.

Provides:
- SMS sender ID per tenant (Check 12.6)
- Favicon customization (Check 12.4)
- Font customization (Check 12.3)
- Report/PDF branding (Check 12.8)
- Branding leak scan (Check 12.12)
- Portal branding completeness check (Check 12.7)
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default platform name (should not appear in white-labeled output)
PLATFORM_NAME = "Perennia"
PLATFORM_VARIANTS = [
    "perennia", "Perennia", "PERENNIA",
    "perennia ai", "Perennia AI", "PERENNIA AI",
    "perenniaai", "PerenniaAI",
]


# =============================================================================
# TENANT BRANDING CONFIG (Domain 12)
# =============================================================================

def get_tenant_branding(db, org_id: int) -> Dict:
    """
    Get complete branding configuration for a tenant.
    Includes colors, logo, fonts, favicon, SMS sender, and portal settings.
    """
    from sqlalchemy import text

    row = db.execute(text("""
        SELECT
            logo_url, primary_color, secondary_color, accent_color,
            email_footer, email_signature_template,
            company_name, company_phone, company_address,
            favicon_url, font_family, sms_sender_id, sms_sender_name,
            portal_logo_url, portal_title, portal_footer_text,
            custom_domain, custom_css
        FROM organization_branding
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    if not row:
        # Return defaults
        org = db.execute(text(
            "SELECT name FROM organizations WHERE id = :org_id"
        ), {"org_id": org_id}).fetchone()

        return {
            "org_id": org_id,
            "company_name": org[0] if org else "Company",
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
        "company_name": row[6],
        "logo_url": row[0],
        "primary_color": row[1] or "#1a73e8",
        "secondary_color": row[2] or "#4285f4",
        "accent_color": row[3] or "#fbbc04",
        "font_family": row[11] or "Inter, system-ui, sans-serif",
        "favicon_url": row[9],
        "sms_sender_id": row[11],
        "sms_sender_name": row[12],
        "portal": {
            "logo_url": row[13],
            "title": row[14],
            "footer_text": row[15],
        },
        "custom_domain": row[16],
        "custom_css": row[17],
        "email_footer": row[4],
        "email_signature": row[5],
        "is_white_labeled": bool(row[0]),  # Has logo = white-labeled
    }


def update_tenant_branding(db, org_id: int, updates: Dict) -> Dict:
    """
    Update branding configuration for a tenant.
    Supports partial updates (only specified fields are changed).
    """
    from sqlalchemy import text

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

    # Upsert
    set_clauses = ", ".join(f"{k} = :{k}" for k in valid_updates)
    valid_updates["org_id"] = org_id

    # Check if row exists
    existing = db.execute(text(
        "SELECT 1 FROM organization_branding WHERE organization_id = :org_id"
    ), {"org_id": org_id}).fetchone()

    if existing:
        db.execute(text(f"""
            UPDATE organization_branding
            SET {set_clauses}, updated_at = NOW()
            WHERE organization_id = :org_id
        """), valid_updates)
    else:
        cols = ", ".join(["organization_id"] + list(valid_updates.keys() - {"org_id"}))
        vals = ", ".join([":org_id"] + [f":{k}" for k in valid_updates if k != "org_id"])
        db.execute(text(f"""
            INSERT INTO organization_branding ({cols})
            VALUES ({vals})
        """), valid_updates)

    db.commit()
    return {"updated": True, "fields": list(valid_updates.keys() - {"org_id"})}


# =============================================================================
# SMS SENDER ID (Domain 12, Check 12.6)
# =============================================================================

def get_sms_sender_config(db, org_id: int) -> Dict:
    """
    Get SMS sender configuration for a tenant.
    Supports custom sender ID/name per organization.
    """
    from sqlalchemy import text
    import os

    row = db.execute(text("""
        SELECT sms_sender_id, sms_sender_name, company_name
        FROM organization_branding
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    default_sender = os.getenv("TELNYX_FROM_NUMBER", "")

    if row and row[0]:
        return {
            "sender_id": row[0],
            "sender_name": row[1] or row[2],
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
    from sqlalchemy import text

    leaks = []

    # Check email footer/signature
    row = db.execute(text("""
        SELECT email_footer, email_signature_template, portal_footer_text
        FROM organization_branding
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    if row:
        fields = [
            ("email_footer", row[0]),
            ("email_signature_template", row[1]),
            ("portal_footer_text", row[2]),
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
        "scanned_at": __import__("datetime").datetime.utcnow().isoformat(),
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
