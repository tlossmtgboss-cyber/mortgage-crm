"""
White-Label Template Service for Smart Docs V2

Full-featured white-label service for per-organization branding, email template
customization, portal theming, PDF cover pages, and document watermarking.

Capabilities:
    1. Organization branding management (logo, colors, fonts)
    2. Email template customization per org
    3. Portal theming (CSS generation from brand config)
    4. Document watermarking with org branding
    5. PDF cover page generation with org branding
    6. Email rendering with org-specific templates + branding
    7. Default templates for all 8 email types (with merge fields)
    8. Template preview mode (render with sample data)
    9. Brand validation (logo dimensions, color contrast accessibility)
   10. Multi-org template management (copy templates between orgs)
   11. Compliance footer management (NMLS, Equal Housing, disclaimers)
   12. Custom domain configuration for portal

Usage:
    from services.smart_docs.white_label_service import WhiteLabelService

    service = WhiteLabelService(db)
    config = await service.get_brand_config(org_id=42)
    email = await service.render_email(org_id=42, template_key="doc_request", variables={...})
    css = await service.get_portal_theme(org_id=42)
    cover_pdf = await service.generate_cover_page(org_id=42, loan_data={...})
"""

from __future__ import annotations

import copy
import html
import io
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors as rl_colors
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APP_URL = os.getenv("APP_URL", "https://app.perenniaai.com")
_PAGE_WIDTH, _PAGE_HEIGHT = 612, 792  # US Letter in points
_MARGIN = 72  # 1 inch

# WCAG AA minimum contrast ratio for normal text
_MIN_CONTRAST_RATIO = 4.5
# WCAG AA minimum contrast ratio for large text (>=18pt or >=14pt bold)
_MIN_CONTRAST_RATIO_LARGE = 3.0

# Merge-field pattern: {{field_name}}
_MERGE_FIELD_RE = re.compile(r"\{\{(\w+)\}\}")

# Valid hex color pattern
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Template keys
TEMPLATE_KEYS = (
    "doc_request",
    "doc_reminder",
    "doc_approved",
    "doc_rejected",
    "signature_request",
    "welcome",
    "checklist_update",
    "condition_added",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RenderedEmail:
    """Result of rendering an email template."""
    subject: str
    body_html: str
    body_text: str
    from_name: Optional[str] = None
    from_address: Optional[str] = None
    reply_to: Optional[str] = None


@dataclass
class ThemeCSS:
    """Generated portal theme CSS."""
    css: str
    variables: Dict[str, str]
    org_id: int


@dataclass
class BrandValidationResult:
    """Result of brand config validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ComplianceFooter:
    """Rendered compliance footer (HTML and plain text)."""
    html: str
    text: str


# ---------------------------------------------------------------------------
# Sample data for template preview
# ---------------------------------------------------------------------------

_PREVIEW_SAMPLE_DATA: Dict[str, Dict[str, Any]] = {
    "doc_request": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "document_name": "2024 W-2 Forms",
        "document_description": "Please provide your W-2 wage and tax statements from your current employer for the most recent tax year.",
        "due_date": "March 25, 2026",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
        "priority": "High",
    },
    "doc_reminder": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "document_name": "2024 W-2 Forms",
        "days_overdue": "3",
        "due_date": "March 22, 2026",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
        "reminder_count": "2",
    },
    "doc_approved": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "document_name": "2024 W-2 Forms",
        "approved_date": "March 20, 2026",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
        "remaining_count": "3",
    },
    "doc_rejected": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "document_name": "Bank Statements",
        "rejection_reason": "The uploaded document is missing pages 2 and 3. Please upload the complete statement including all pages.",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
    },
    "signature_request": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "document_name": "Loan Estimate Disclosure",
        "signing_url": f"{_APP_URL}/portal/sign/abc123",
        "expiration_date": "March 28, 2026",
        "loan_number": "LN-2026-001234",
    },
    "welcome": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "portal_url": f"{_APP_URL}/portal",
        "loan_number": "LN-2026-001234",
        "property_address": "123 Main St, Anytown, CA 90210",
    },
    "checklist_update": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "completed_count": "5",
        "total_count": "8",
        "remaining_items": "Bank Statements, Tax Returns, Insurance Quote",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
        "progress_percent": "63",
    },
    "condition_added": {
        "borrower_name": "Jane Doe",
        "lo_name": "John Smith",
        "lo_title": "Senior Loan Officer",
        "lo_phone": "(555) 123-4567",
        "lo_email": "john.smith@example.com",
        "condition_title": "Explanation of Large Deposit",
        "condition_description": "Please provide a written explanation and source documentation for the $15,000 deposit on 03/01/2026.",
        "due_date": "March 28, 2026",
        "portal_url": f"{_APP_URL}/portal/documents",
        "loan_number": "LN-2026-001234",
    },
}


# =============================================================================
# DEFAULT EMAIL TEMPLATES
# =============================================================================

def _base_html_wrapper(
    primary_color: str,
    header_bg: str,
    company_name: str,
    inner_html: str,
    footer_html: str,
    font_family: str = "Inter, sans-serif",
) -> str:
    """Wrap inner content in a branded email shell with inline CSS."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(company_name)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:{html.escape(font_family)},-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:24px;">
<div style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<!-- Header -->
<div style="background:{html.escape(header_bg)};padding:28px 24px;text-align:center;">
<h1 style="margin:0;color:{html.escape(_contrast_text(header_bg))};font-size:22px;font-weight:700;">{html.escape(company_name)}</h1>
</div>
<!-- Content -->
<div style="padding:28px 24px;">
{inner_html}
</div>
<!-- Footer -->
<div style="background:#f9fafb;padding:20px 24px;border-top:1px solid #e5e7eb;">
{footer_html}
</div>
</div>
</div>
</body>
</html>"""


# Each default template is a tuple: (subject_template, body_html_inner, body_text)
# They use {{variable}} merge fields and are wrapped in the base layout at render time.

_DEFAULT_TEMPLATES: Dict[str, Dict[str, str]] = {

    # ----- doc_request -----
    "doc_request": {
        "subject": "Document Needed: {{document_name}}",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">We need the following document to continue processing your loan application <strong>{{loan_number}}</strong>:</p>
<div style="border:1px solid #e5e7eb;border-left:4px solid {{primary_color}};border-radius:8px;padding:16px;margin:0 0 20px;">
<h2 style="margin:0 0 8px;color:#1f2937;font-size:18px;">{{document_name}}</h2>
<p style="margin:0;color:#6b7280;">{{document_description}}</p>
</div>
<p style="margin:0 0 8px;color:#4b5563;"><strong>Due Date:</strong> {{due_date}}</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Upload Document</a>
</div>
<p style="margin:0;color:#6b7280;font-size:14px;">If you have questions, contact {{lo_name}} at {{lo_phone}} or reply to this email.</p>""",
        "text": """Hi {{borrower_name}},

We need the following document for your loan {{loan_number}}:

DOCUMENT: {{document_name}}
{{document_description}}

Due Date: {{due_date}}

Upload here: {{portal_url}}

Questions? Contact {{lo_name}} at {{lo_phone}} or {{lo_email}}.

Best regards,
{{lo_name}}
{{lo_title}}""",
    },

    # ----- doc_reminder -----
    "doc_reminder": {
        "subject": "Reminder: {{document_name}} Still Needed",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">This is a friendly reminder that we are still waiting for a document needed to process your loan <strong>{{loan_number}}</strong>.</p>
<div style="border:1px solid #fde68a;background:#fffbeb;border-radius:8px;padding:16px;margin:0 0 20px;">
<h3 style="margin:0 0 8px;color:#92400e;font-size:16px;">{{document_name}}</h3>
<p style="margin:0;color:#92400e;font-size:14px;">Originally due: {{due_date}} &mdash; {{days_overdue}} day(s) overdue</p>
</div>
<p style="margin:0 0 20px;color:#4b5563;">Submitting this document promptly helps us keep your loan on schedule and avoid delays.</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Upload Now</a>
</div>
<p style="margin:0;color:#6b7280;font-size:14px;">Need help? Reach {{lo_name}} at {{lo_phone}}.</p>""",
        "text": """Hi {{borrower_name}},

Reminder: We still need the following document for loan {{loan_number}}:

DOCUMENT: {{document_name}}
Originally due: {{due_date}} ({{days_overdue}} day(s) overdue)

Please upload it here: {{portal_url}}

Need help? Contact {{lo_name}} at {{lo_phone}} or {{lo_email}}.

Best regards,
{{lo_name}}""",
    },

    # ----- doc_approved -----
    "doc_approved": {
        "subject": "Document Approved: {{document_name}}",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">Great news! The following document for loan <strong>{{loan_number}}</strong> has been reviewed and approved:</p>
<div style="border:1px solid #a7f3d0;background:#ecfdf5;border-radius:8px;padding:16px;margin:0 0 20px;">
<div style="display:flex;align-items:center;">
<span style="color:#059669;font-size:24px;margin-right:12px;">&#10003;</span>
<div>
<h3 style="margin:0;color:#065f46;font-size:16px;">{{document_name}}</h3>
<p style="margin:4px 0 0;color:#047857;font-size:14px;">Approved on {{approved_date}}</p>
</div>
</div>
</div>
<p style="margin:0 0 20px;color:#4b5563;">You have <strong>{{remaining_count}}</strong> remaining document(s) to complete your file.</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">View Checklist</a>
</div>""",
        "text": """Hi {{borrower_name}},

Great news! Your document has been approved for loan {{loan_number}}:

APPROVED: {{document_name}}
Approved on: {{approved_date}}

You have {{remaining_count}} remaining document(s).

View your checklist: {{portal_url}}

Best regards,
{{lo_name}}""",
    },

    # ----- doc_rejected -----
    "doc_rejected": {
        "subject": "Action Required: {{document_name}} Needs Resubmission",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">Unfortunately, the document you submitted for loan <strong>{{loan_number}}</strong> could not be accepted:</p>
<div style="border:1px solid #fecaca;background:#fef2f2;border-radius:8px;padding:16px;margin:0 0 20px;">
<h3 style="margin:0 0 8px;color:#991b1b;font-size:16px;">{{document_name}}</h3>
<p style="margin:0 0 8px;color:#991b1b;font-size:14px;font-weight:600;">Reason:</p>
<p style="margin:0;color:#7f1d1d;">{{rejection_reason}}</p>
</div>
<p style="margin:0 0 20px;color:#4b5563;">Please review the feedback and upload a corrected version at your earliest convenience.</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:#dc2626;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Resubmit Document</a>
</div>
<p style="margin:0;color:#6b7280;font-size:14px;">Questions? Contact {{lo_name}} at {{lo_phone}}.</p>""",
        "text": """Hi {{borrower_name}},

The document you submitted for loan {{loan_number}} could not be accepted:

DOCUMENT: {{document_name}}
REASON: {{rejection_reason}}

Please upload a corrected version: {{portal_url}}

Questions? Contact {{lo_name}} at {{lo_phone}} or {{lo_email}}.

Best regards,
{{lo_name}}""",
    },

    # ----- signature_request -----
    "signature_request": {
        "subject": "Signature Required: {{document_name}}",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">A document for loan <strong>{{loan_number}}</strong> requires your electronic signature:</p>
<div style="border:1px solid #c7d2fe;background:#eef2ff;border-radius:8px;padding:16px;margin:0 0 20px;">
<h3 style="margin:0 0 8px;color:#3730a3;font-size:16px;">{{document_name}}</h3>
<p style="margin:0;color:#4338ca;font-size:14px;">Please sign by: {{expiration_date}}</p>
</div>
<div style="text-align:center;margin:24px 0;">
<a href="{{signing_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Review &amp; Sign</a>
</div>
<p style="margin:0;color:#6b7280;font-size:14px;">This link expires on {{expiration_date}}. If you have questions, contact {{lo_name}} at {{lo_phone}}.</p>""",
        "text": """Hi {{borrower_name}},

A document for loan {{loan_number}} requires your signature:

DOCUMENT: {{document_name}}
Sign by: {{expiration_date}}

Sign here: {{signing_url}}

Questions? Contact {{lo_name}} at {{lo_phone}} or {{lo_email}}.

Best regards,
{{lo_name}}""",
    },

    # ----- welcome -----
    "welcome": {
        "subject": "Welcome to Your Loan Portal",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">Welcome! Your secure loan portal is ready for loan <strong>{{loan_number}}</strong> at <strong>{{property_address}}</strong>.</p>
<p style="margin:0 0 20px;color:#4b5563;">Through your portal you can:</p>
<ul style="color:#4b5563;padding-left:20px;margin:0 0 20px;">
<li style="margin:6px 0;">Upload requested documents securely</li>
<li style="margin:6px 0;">Track your loan progress in real time</li>
<li style="margin:6px 0;">Sign documents electronically</li>
<li style="margin:6px 0;">Message your loan team directly</li>
</ul>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Access Your Portal</a>
</div>
<p style="margin:0;color:#374151;">Your loan officer, <strong>{{lo_name}}</strong> ({{lo_title}}), is here to help.<br>Phone: {{lo_phone}} | Email: {{lo_email}}</p>""",
        "text": """Hi {{borrower_name}},

Welcome! Your secure loan portal is ready for loan {{loan_number}} at {{property_address}}.

Through your portal you can:
- Upload requested documents securely
- Track your loan progress in real time
- Sign documents electronically
- Message your loan team directly

Access your portal: {{portal_url}}

Your loan officer, {{lo_name}} ({{lo_title}}), is here to help.
Phone: {{lo_phone}} | Email: {{lo_email}}""",
    },

    # ----- checklist_update -----
    "checklist_update": {
        "subject": "Document Checklist Update: {{completed_count}}/{{total_count}} Complete",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">Here is a progress update on your document checklist for loan <strong>{{loan_number}}</strong>:</p>
<div style="background:#f3f4f6;border-radius:8px;padding:16px;margin:0 0 20px;">
<div style="display:flex;justify-content:space-between;margin-bottom:8px;">
<span style="color:#374151;font-weight:600;">Progress</span>
<span style="color:#374151;font-weight:600;">{{completed_count}} of {{total_count}}</span>
</div>
<div style="background:#e5e7eb;border-radius:9999px;height:12px;overflow:hidden;">
<div style="background:{{primary_color}};height:100%;width:{{progress_percent}}%;border-radius:9999px;"></div>
</div>
</div>
<p style="margin:0 0 8px;color:#4b5563;font-weight:600;">Remaining items:</p>
<p style="margin:0 0 20px;color:#6b7280;">{{remaining_items}}</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">View Full Checklist</a>
</div>""",
        "text": """Hi {{borrower_name}},

Progress update for loan {{loan_number}}:

Completed: {{completed_count}} of {{total_count}} ({{progress_percent}}%)

Remaining items:
{{remaining_items}}

View your checklist: {{portal_url}}

Best regards,
{{lo_name}}""",
    },

    # ----- condition_added -----
    "condition_added": {
        "subject": "New Condition: {{condition_title}}",
        "html_inner": """<p style="margin:0 0 16px;color:#374151;">Hi {{borrower_name}},</p>
<p style="margin:0 0 20px;color:#4b5563;">A new underwriting condition has been added to your loan <strong>{{loan_number}}</strong>:</p>
<div style="border:1px solid #fde68a;background:#fffbeb;border-radius:8px;padding:16px;margin:0 0 20px;">
<h3 style="margin:0 0 8px;color:#92400e;font-size:16px;">{{condition_title}}</h3>
<p style="margin:0 0 8px;color:#78350f;">{{condition_description}}</p>
<p style="margin:0;color:#92400e;font-size:14px;"><strong>Due by:</strong> {{due_date}}</p>
</div>
<p style="margin:0 0 20px;color:#4b5563;">Please address this condition promptly to keep your loan on track.</p>
<div style="text-align:center;margin:24px 0;">
<a href="{{portal_url}}" style="display:inline-block;padding:14px 32px;background:{{primary_color}};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">View &amp; Respond</a>
</div>
<p style="margin:0;color:#6b7280;font-size:14px;">Questions? Contact {{lo_name}} at {{lo_phone}}.</p>""",
        "text": """Hi {{borrower_name}},

A new condition has been added to your loan {{loan_number}}:

CONDITION: {{condition_title}}
{{condition_description}}

Due by: {{due_date}}

Respond here: {{portal_url}}

Questions? Contact {{lo_name}} at {{lo_phone}} or {{lo_email}}.

Best regards,
{{lo_name}}""",
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B) tuple."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def _relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.0 formula."""
    def _linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(color1: str, color2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    r1, g1, b1 = _hex_to_rgb(color1)
    r2, g2, b2 = _hex_to_rgb(color2)
    l1 = _relative_luminance(r1, g1, b1)
    l2 = _relative_luminance(r2, g2, b2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _contrast_text(bg_hex: str) -> str:
    """Return #ffffff or #1f2937 depending on which has better contrast on bg."""
    try:
        r, g, b = _hex_to_rgb(bg_hex)
        lum = _relative_luminance(r, g, b)
        return "#ffffff" if lum < 0.5 else "#1f2937"
    except Exception:
        return "#1f2937"


def _merge_fields(template: str, variables: Dict[str, Any]) -> str:
    """Replace {{field}} placeholders with variable values."""
    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return match.group(0)  # leave unreplaced
        return html.escape(str(value))

    return _MERGE_FIELD_RE.sub(_replacer, template)


def _merge_fields_plain(template: str, variables: Dict[str, Any]) -> str:
    """Replace {{field}} placeholders without HTML escaping (for plain text)."""
    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return match.group(0)
        return str(value)

    return _MERGE_FIELD_RE.sub(_replacer, template)


# =============================================================================
# SERVICE
# =============================================================================

class WhiteLabelService:
    """Async white-label template service with per-org isolation.

    All public methods accept ``org_id`` and enforce tenant isolation through
    query filters. The service never returns data belonging to a different org.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 1. Brand config management
    # ------------------------------------------------------------------

    async def get_brand_config(self, org_id: int) -> Optional[Any]:
        """Get the active WhiteLabelConfig for an organization.

        Returns None if no config exists (callers should fall back to defaults).
        """
        from database.models.white_label_config import WhiteLabelConfig

        config = (
            self.db.query(WhiteLabelConfig)
            .filter(
                WhiteLabelConfig.organization_id == org_id,
                WhiteLabelConfig.is_active.is_(True),
                WhiteLabelConfig.setting_type.is_(None),
            )
            .first()
        )
        return config

    async def upsert_brand_config(
        self,
        org_id: int,
        data: Dict[str, Any],
    ) -> Any:
        """Create or update brand config for an organization.

        Args:
            org_id: Organization ID.
            data: Dict of column values to set (company_name, logo_url, colors, etc.).

        Returns:
            Updated WhiteLabelConfig instance.
        """
        from database.models.white_label_config import WhiteLabelConfig

        config = (
            self.db.query(WhiteLabelConfig)
            .filter(
                WhiteLabelConfig.organization_id == org_id,
                WhiteLabelConfig.setting_type.is_(None),
            )
            .first()
        )

        if config is None:
            config = WhiteLabelConfig(organization_id=org_id)
            self.db.add(config)

        # Apply allowed fields
        allowed_fields = {
            "company_name", "logo_url", "favicon_url",
            "primary_color", "secondary_color", "accent_color", "header_bg_color",
            "font_family",
            "email_from_name", "email_from_address", "email_reply_to", "email_footer_html",
            "portal_welcome_message", "portal_custom_css",
            "sms_sender_name",
            "support_email", "support_phone",
            "privacy_policy_url", "terms_of_service_url",
            "nmls_number", "equal_housing_logo", "disclaimer_text",
            "custom_domain",
            "is_active",
        }

        for key, value in data.items():
            if key in allowed_fields:
                # Sanitize CSS fields to prevent XSS
                if key == "portal_custom_css" and value:
                    from input_validation import sanitize_custom_css
                    value = sanitize_custom_css(value)
                setattr(config, key, value)

        config.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        return config

    async def delete_brand_config(self, org_id: int) -> bool:
        """Soft-delete brand config by marking inactive."""
        from database.models.white_label_config import WhiteLabelConfig

        config = (
            self.db.query(WhiteLabelConfig)
            .filter(
                WhiteLabelConfig.organization_id == org_id,
                WhiteLabelConfig.setting_type.is_(None),
            )
            .first()
        )
        if config is None:
            return False

        config.is_active = False
        config.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return True

    # ------------------------------------------------------------------
    # 2. Email template management
    # ------------------------------------------------------------------

    async def get_email_template(
        self,
        org_id: int,
        template_key: str,
        language: str = "en",
    ) -> Optional[Any]:
        """Get a specific email template for an org, falling back to defaults."""
        from database.models.white_label_config import EmailTemplate

        template = (
            self.db.query(EmailTemplate)
            .filter(
                EmailTemplate.organization_id == org_id,
                EmailTemplate.template_key == template_key,
                EmailTemplate.language == language,
                EmailTemplate.is_active.is_(True),
            )
            .order_by(EmailTemplate.version.desc())
            .first()
        )
        return template

    async def upsert_email_template(
        self,
        org_id: int,
        template_key: str,
        subject_template: str,
        body_html_template: str,
        body_text_template: Optional[str] = None,
        language: str = "en",
    ) -> Any:
        """Create or update (with version bump) an email template.

        If a template with the same key/language exists, its version is
        incremented. Previous versions are kept for audit purposes but
        marked inactive.
        """
        from database.models.white_label_config import EmailTemplate

        if template_key not in TEMPLATE_KEYS:
            raise ValueError(
                f"Invalid template_key '{template_key}'. "
                f"Must be one of: {', '.join(TEMPLATE_KEYS)}"
            )

        # Deactivate previous versions
        existing = (
            self.db.query(EmailTemplate)
            .filter(
                EmailTemplate.organization_id == org_id,
                EmailTemplate.template_key == template_key,
                EmailTemplate.language == language,
                EmailTemplate.is_active.is_(True),
            )
            .all()
        )

        max_version = 0
        for tmpl in existing:
            tmpl.is_active = False
            tmpl.updated_at = datetime.now(timezone.utc)
            if tmpl.version and tmpl.version > max_version:
                max_version = tmpl.version

        new_template = EmailTemplate(
            organization_id=org_id,
            template_key=template_key,
            subject_template=subject_template,
            body_html_template=body_html_template,
            body_text_template=body_text_template,
            language=language,
            version=max_version + 1,
            is_active=True,
        )
        self.db.add(new_template)
        self.db.flush()

        return new_template

    async def list_email_templates(
        self,
        org_id: int,
        language: str = "en",
        include_inactive: bool = False,
    ) -> List[Any]:
        """List all email templates for an org."""
        from database.models.white_label_config import EmailTemplate

        query = self.db.query(EmailTemplate).filter(
            EmailTemplate.organization_id == org_id,
            EmailTemplate.language == language,
        )

        if not include_inactive:
            query = query.filter(EmailTemplate.is_active.is_(True))

        return query.order_by(EmailTemplate.template_key, EmailTemplate.version.desc()).all()

    async def delete_email_template(
        self,
        org_id: int,
        template_key: str,
        language: str = "en",
    ) -> int:
        """Soft-delete all versions of a template. Returns count of deactivated rows."""
        from database.models.white_label_config import EmailTemplate

        templates = (
            self.db.query(EmailTemplate)
            .filter(
                EmailTemplate.organization_id == org_id,
                EmailTemplate.template_key == template_key,
                EmailTemplate.language == language,
                EmailTemplate.is_active.is_(True),
            )
            .all()
        )

        for tmpl in templates:
            tmpl.is_active = False
            tmpl.updated_at = datetime.now(timezone.utc)

        self.db.flush()
        return len(templates)

    # ------------------------------------------------------------------
    # 3. Portal theming (CSS generation)
    # ------------------------------------------------------------------

    async def get_portal_theme(self, org_id: int) -> ThemeCSS:
        """Generate a CSS theme from the org's brand config.

        Falls back to sensible defaults when no config exists.
        """
        config = await self.get_brand_config(org_id)

        primary = getattr(config, "primary_color", None) or "#1a56db"
        secondary = getattr(config, "secondary_color", None) or "#7c3aed"
        accent = getattr(config, "accent_color", None) or "#059669"
        header_bg = getattr(config, "header_bg_color", None) or "#ffffff"
        font_family = getattr(config, "font_family", None) or "Inter, sans-serif"
        custom_css = getattr(config, "portal_custom_css", None) or ""

        variables = {
            "--wl-primary": primary,
            "--wl-secondary": secondary,
            "--wl-accent": accent,
            "--wl-header-bg": header_bg,
            "--wl-header-text": _contrast_text(header_bg),
            "--wl-font-family": font_family,
            "--wl-primary-hover": self._darken(primary, 0.15),
            "--wl-primary-light": self._lighten(primary, 0.90),
            "--wl-secondary-light": self._lighten(secondary, 0.90),
            "--wl-accent-light": self._lighten(accent, 0.90),
        }

        css_vars = "\n".join(f"  {k}: {v};" for k, v in variables.items())

        css = f""":root {{
{css_vars}
}}

/* ---- Base ---- */
body {{
  font-family: var(--wl-font-family), -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1f2937;
}}

/* ---- Header ---- */
.portal-header {{
  background-color: var(--wl-header-bg);
  color: var(--wl-header-text);
}}

/* ---- Primary actions ---- */
.btn-primary,
button[data-variant="primary"] {{
  background-color: var(--wl-primary);
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
}}
.btn-primary:hover,
button[data-variant="primary"]:hover {{
  background-color: var(--wl-primary-hover);
}}

/* ---- Secondary actions ---- */
.btn-secondary,
button[data-variant="secondary"] {{
  background-color: var(--wl-secondary);
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-weight: 600;
  cursor: pointer;
}}

/* ---- Accent / success ---- */
.badge-accent,
.text-accent {{
  color: var(--wl-accent);
}}
.bg-accent {{
  background-color: var(--wl-accent);
}}

/* ---- Links ---- */
a {{
  color: var(--wl-primary);
}}
a:hover {{
  color: var(--wl-primary-hover);
}}

/* ---- Cards and surfaces ---- */
.card {{
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  background: #ffffff;
}}

/* ---- Progress bar ---- */
.progress-bar {{
  background-color: var(--wl-primary-light);
  border-radius: 9999px;
  height: 8px;
}}
.progress-bar-fill {{
  background-color: var(--wl-primary);
  height: 100%;
  border-radius: 9999px;
  transition: width 0.3s ease;
}}

/* ---- Sidebar nav highlight ---- */
.nav-item.active {{
  background-color: var(--wl-primary-light);
  color: var(--wl-primary);
  font-weight: 600;
}}

/* ---- Focus ring ---- */
*:focus-visible {{
  outline: 2px solid var(--wl-primary);
  outline-offset: 2px;
}}

{custom_css}"""

        return ThemeCSS(css=css, variables=variables, org_id=org_id)

    # ------------------------------------------------------------------
    # 4. Document watermarking
    # ------------------------------------------------------------------

    async def watermark_pdf(
        self,
        org_id: int,
        pdf_bytes: bytes,
        watermark_text: Optional[str] = None,
    ) -> bytes:
        """Add org-branded watermark to a PDF.

        Uses the org's company name as watermark text if not specified.
        Falls back to returning the original PDF if dependencies are missing.
        """
        if not HAS_REPORTLAB or not HAS_PYPDF:
            logger.warning("reportlab or pypdf not available; skipping watermark")
            return pdf_bytes

        config = await self.get_brand_config(org_id)
        company_name = getattr(config, "company_name", None) or "CONFIDENTIAL"
        text = watermark_text or company_name

        try:
            # Create watermark page
            watermark_buf = io.BytesIO()
            c = rl_canvas.Canvas(watermark_buf, pagesize=letter)
            c.saveState()
            c.setFont("Helvetica", 48)
            c.setFillColorRGB(0.85, 0.85, 0.85, alpha=0.3)
            c.translate(_PAGE_WIDTH / 2, _PAGE_HEIGHT / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, text)
            c.restoreState()

            # Add org branding line at bottom
            if config and config.nmls_number:
                c.setFont("Helvetica", 7)
                c.setFillColorRGB(0.7, 0.7, 0.7)
                c.drawCentredString(
                    _PAGE_WIDTH / 2, 20,
                    f"{company_name} | NMLS #{config.nmls_number}",
                )

            c.save()
            watermark_buf.seek(0)

            watermark_reader = PdfReader(watermark_buf)
            watermark_page = watermark_reader.pages[0]

            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()

            for page in reader.pages:
                page.merge_page(watermark_page)
                writer.add_page(page)

            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()

        except Exception as e:
            logger.exception(f"Watermarking failed for org {org_id}: {e}")
            return pdf_bytes

    # ------------------------------------------------------------------
    # 5. PDF cover page generation
    # ------------------------------------------------------------------

    async def generate_cover_page(
        self,
        org_id: int,
        loan_data: Dict[str, Any],
    ) -> bytes:
        """Generate a branded PDF cover page for a loan package.

        Args:
            org_id: Organization ID.
            loan_data: Dict with keys such as:
                borrower_name, loan_number, property_address,
                loan_amount, loan_type, lo_name, lo_phone, lo_email,
                prepared_date (optional, defaults to today).

        Returns:
            PDF content as bytes.
        """
        config = await self.get_brand_config(org_id)
        company_name = getattr(config, "company_name", None) or "Mortgage Services"
        primary_color = getattr(config, "primary_color", None) or "#1a56db"
        nmls_number = getattr(config, "nmls_number", None)
        equal_housing = getattr(config, "equal_housing_logo", True)
        disclaimer = getattr(config, "disclaimer_text", None)
        logo_url = getattr(config, "logo_url", None)

        if HAS_REPORTLAB:
            return self._generate_cover_page_reportlab(
                company_name=company_name,
                primary_color=primary_color,
                nmls_number=nmls_number,
                equal_housing=equal_housing,
                disclaimer=disclaimer,
                logo_url=logo_url,
                loan_data=loan_data,
            )
        else:
            return self._generate_cover_page_fallback(
                company_name=company_name,
                nmls_number=nmls_number,
                loan_data=loan_data,
            )

    def _generate_cover_page_reportlab(
        self,
        company_name: str,
        primary_color: str,
        nmls_number: Optional[str],
        equal_housing: bool,
        disclaimer: Optional[str],
        logo_url: Optional[str],
        loan_data: Dict[str, Any],
    ) -> bytes:
        """Generate cover page using ReportLab."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # Parse brand color
        try:
            pr, pg, pb = _hex_to_rgb(primary_color)
            brand_r, brand_g, brand_b = pr / 255.0, pg / 255.0, pb / 255.0
        except Exception:
            brand_r, brand_g, brand_b = 0.10, 0.34, 0.86

        # -- Header band --
        c.setFillColorRGB(brand_r, brand_g, brand_b)
        c.rect(0, height - 160, width, 160, fill=True, stroke=False)

        # Company name in header
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 28)
        c.drawCentredString(width / 2, height - 80, company_name)

        if nmls_number:
            c.setFont("Helvetica", 11)
            c.drawCentredString(width / 2, height - 100, f"NMLS #{nmls_number}")

        # -- "Loan Package" title --
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(width / 2, height - 220, "Loan Package")

        # -- Loan details table --
        y_pos = height - 280
        details = [
            ("Borrower", loan_data.get("borrower_name", "")),
            ("Loan Number", loan_data.get("loan_number", "")),
            ("Property", loan_data.get("property_address", "")),
            ("Loan Amount", loan_data.get("loan_amount", "")),
            ("Loan Type", loan_data.get("loan_type", "")),
            ("Loan Officer", loan_data.get("lo_name", "")),
            ("Phone", loan_data.get("lo_phone", "")),
            ("Email", loan_data.get("lo_email", "")),
            ("Prepared", loan_data.get("prepared_date", datetime.now(timezone.utc).strftime("%B %d, %Y"))),
        ]

        for label, value in details:
            if not value:
                continue
            c.setFont("Helvetica-Bold", 11)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.drawString(_MARGIN, y_pos, f"{label}:")
            c.setFont("Helvetica", 11)
            c.setFillColorRGB(0.12, 0.12, 0.12)
            c.drawString(_MARGIN + 120, y_pos, str(value))
            y_pos -= 22

        # -- Divider --
        y_pos -= 20
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y_pos, width - _MARGIN, y_pos)

        # -- Disclaimer --
        if disclaimer:
            y_pos -= 30
            c.setFont("Helvetica", 8)
            c.setFillColorRGB(0.5, 0.5, 0.5)
            # Word-wrap disclaimer
            max_chars_per_line = 90
            words = disclaimer.split()
            lines = []
            current_line = ""
            for word in words:
                test = f"{current_line} {word}".strip()
                if len(test) <= max_chars_per_line:
                    current_line = test
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            for line in lines[:8]:  # max 8 lines
                c.drawString(_MARGIN, y_pos, line)
                y_pos -= 12

        # -- Footer --
        footer_y = 40
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        footer_parts = [company_name]
        if nmls_number:
            footer_parts.append(f"NMLS #{nmls_number}")
        if equal_housing:
            footer_parts.append("Equal Housing Lender")
        c.drawCentredString(width / 2, footer_y, " | ".join(footer_parts))

        # -- Accent line at bottom --
        c.setStrokeColorRGB(brand_r, brand_g, brand_b)
        c.setLineWidth(3)
        c.line(0, 25, width, 25)

        c.save()
        return buf.getvalue()

    def _generate_cover_page_fallback(
        self,
        company_name: str,
        nmls_number: Optional[str],
        loan_data: Dict[str, Any],
    ) -> bytes:
        """Minimal plain-text-in-PDF fallback when ReportLab is unavailable.

        Produces a minimal valid PDF with text content.
        """
        lines = [
            company_name,
            f"NMLS #{nmls_number}" if nmls_number else "",
            "",
            "LOAN PACKAGE",
            "",
        ]
        for label, key in [
            ("Borrower", "borrower_name"),
            ("Loan Number", "loan_number"),
            ("Property", "property_address"),
            ("Loan Amount", "loan_amount"),
            ("Loan Type", "loan_type"),
            ("Loan Officer", "lo_name"),
        ]:
            val = loan_data.get(key)
            if val:
                lines.append(f"{label}: {val}")

        text_content = "\n".join(line for line in lines if line is not None)

        # Build minimal PDF (single-page, Courier font)
        stream = (
            f"BT\n/F1 12 Tf\n72 720 Td\n14 TL\n"
        )
        for line in text_content.split("\n"):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream += f"({safe}) '\n"
        stream += "ET\n"

        stream_bytes = stream.encode("latin-1")

        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length " + str(len(stream_bytes)).encode() + b">>\n"
            b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Courier>>endobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        )
        return pdf

    # ------------------------------------------------------------------
    # 6. Email rendering
    # ------------------------------------------------------------------

    async def render_email(
        self,
        org_id: int,
        template_key: str,
        variables: Dict[str, Any],
        language: str = "en",
    ) -> RenderedEmail:
        """Render an email using org template or default, with brand wrapping.

        Variables are merged into the template using {{field}} syntax.
        The rendered HTML is wrapped in the org's branded email shell.

        Args:
            org_id: Organization ID.
            template_key: One of the TEMPLATE_KEYS constants.
            variables: Merge field values.
            language: ISO language code (default "en").

        Returns:
            RenderedEmail with subject, body_html, body_text, sender info.
        """
        if template_key not in TEMPLATE_KEYS:
            raise ValueError(f"Unknown template_key: {template_key}")

        config = await self.get_brand_config(org_id)
        company_name = getattr(config, "company_name", None) or "Mortgage Services"
        primary_color = getattr(config, "primary_color", None) or "#1a56db"
        header_bg = getattr(config, "header_bg_color", None) or primary_color
        font_family = getattr(config, "font_family", None) or "Inter, sans-serif"

        # Inject brand variables into the merge context
        enriched_vars = dict(variables)
        enriched_vars.setdefault("company_name", company_name)
        enriched_vars.setdefault("primary_color", primary_color)

        # Try org-specific template first
        custom_template = await self.get_email_template(org_id, template_key, language)

        if custom_template:
            subject = _merge_fields_plain(custom_template.subject_template, enriched_vars)
            html_inner = _merge_fields(custom_template.body_html_template, enriched_vars)
            text_body = _merge_fields_plain(
                custom_template.body_text_template or "", enriched_vars
            )
        else:
            # Fall back to defaults
            default = _DEFAULT_TEMPLATES.get(template_key)
            if not default:
                raise ValueError(f"No default template for key: {template_key}")

            subject = _merge_fields_plain(default["subject"], enriched_vars)
            html_inner = _merge_fields(default["html_inner"], enriched_vars)
            text_body = _merge_fields_plain(default["text"], enriched_vars)

        # Build compliance footer
        footer = await self._build_compliance_footer(org_id)

        # Wrap in branded shell
        body_html = _base_html_wrapper(
            primary_color=primary_color,
            header_bg=header_bg,
            company_name=company_name,
            inner_html=html_inner,
            footer_html=footer.html,
            font_family=font_family,
        )

        # Append compliance to plain text
        full_text = f"{text_body}\n\n---\n{footer.text}"

        return RenderedEmail(
            subject=subject,
            body_html=body_html,
            body_text=full_text,
            from_name=getattr(config, "email_from_name", None),
            from_address=getattr(config, "email_from_address", None),
            reply_to=getattr(config, "email_reply_to", None),
        )

    # ------------------------------------------------------------------
    # 7. Template preview
    # ------------------------------------------------------------------

    async def preview_template(
        self,
        org_id: int,
        template_key: str,
        sample_data: Optional[Dict[str, Any]] = None,
        language: str = "en",
    ) -> RenderedEmail:
        """Render a template with sample data for preview purposes.

        Uses built-in sample data if none is provided.
        """
        data = sample_data or _PREVIEW_SAMPLE_DATA.get(template_key, {})
        return await self.render_email(org_id, template_key, data, language)

    # ------------------------------------------------------------------
    # 8. Brand validation
    # ------------------------------------------------------------------

    async def validate_brand_config(
        self,
        org_id: Optional[int] = None,
        config_data: Optional[Dict[str, Any]] = None,
    ) -> BrandValidationResult:
        """Validate brand config for accessibility and correctness.

        Either pass org_id to validate the stored config, or config_data
        to validate before saving.

        Checks:
            - Hex color format validity
            - WCAG AA contrast ratios (primary on white, header text on header bg)
            - Logo URL format
            - Required fields
        """
        errors: List[str] = []
        warnings: List[str] = []

        if org_id and not config_data:
            config = await self.get_brand_config(org_id)
            if config is None:
                return BrandValidationResult(
                    is_valid=False,
                    errors=["No brand config found for this organization."],
                )
            config_data = {
                "company_name": config.company_name,
                "primary_color": config.primary_color,
                "secondary_color": config.secondary_color,
                "accent_color": config.accent_color,
                "header_bg_color": config.header_bg_color,
                "logo_url": config.logo_url,
                "favicon_url": config.favicon_url,
            }

        if not config_data:
            return BrandValidationResult(
                is_valid=False,
                errors=["No config data provided for validation."],
            )

        # Required fields
        if not config_data.get("company_name"):
            errors.append("company_name is required.")

        # Color validation
        color_fields = [
            "primary_color", "secondary_color", "accent_color", "header_bg_color",
        ]
        for field_name in color_fields:
            color = config_data.get(field_name)
            if color and not _HEX_COLOR_RE.match(color):
                errors.append(f"{field_name} must be a valid hex color (#RRGGBB). Got: {color}")

        # Contrast checks
        primary = config_data.get("primary_color", "#1a56db")
        header_bg = config_data.get("header_bg_color", "#ffffff")

        if _HEX_COLOR_RE.match(primary or ""):
            # Primary color on white background (for buttons)
            ratio = _contrast_ratio(primary, "#ffffff")
            if ratio < _MIN_CONTRAST_RATIO:
                warnings.append(
                    f"Primary color {primary} on white has contrast ratio {ratio:.1f}:1 "
                    f"(WCAG AA requires {_MIN_CONTRAST_RATIO}:1 for normal text). "
                    f"Consider using a darker shade."
                )

        if _HEX_COLOR_RE.match(header_bg or ""):
            header_text = _contrast_text(header_bg)
            ratio = _contrast_ratio(header_bg, header_text)
            if ratio < _MIN_CONTRAST_RATIO_LARGE:
                warnings.append(
                    f"Header background {header_bg} with auto-selected text color "
                    f"has contrast ratio {ratio:.1f}:1 (minimum {_MIN_CONTRAST_RATIO_LARGE}:1)."
                )

        # Logo URL format
        logo = config_data.get("logo_url")
        if logo:
            if not (logo.startswith("https://") or logo.startswith("http://")):
                warnings.append("logo_url should use HTTPS for security.")
            if not any(logo.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".svg", ".webp")):
                warnings.append(
                    "logo_url does not end with a recognized image extension "
                    "(.png, .jpg, .svg, .webp)."
                )

        favicon = config_data.get("favicon_url")
        if favicon and not (favicon.startswith("https://") or favicon.startswith("http://")):
            warnings.append("favicon_url should use HTTPS.")

        return BrandValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def validate_logo_dimensions(
        self,
        image_bytes: bytes,
        max_width: int = 600,
        max_height: int = 200,
        min_width: int = 100,
        min_height: int = 30,
    ) -> BrandValidationResult:
        """Validate logo image dimensions.

        Requires Pillow (PIL). Returns validation errors/warnings.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not HAS_PIL:
            warnings.append("Pillow not installed; cannot validate image dimensions.")
            return BrandValidationResult(is_valid=True, warnings=warnings)

        try:
            img = PILImage.open(io.BytesIO(image_bytes))
            w, h = img.size

            if w > max_width or h > max_height:
                errors.append(
                    f"Logo dimensions {w}x{h} exceed maximum {max_width}x{max_height}. "
                    f"Please resize."
                )
            if w < min_width or h < min_height:
                warnings.append(
                    f"Logo dimensions {w}x{h} are below recommended minimum "
                    f"{min_width}x{min_height}. May appear blurry."
                )

            # Check file size (< 500KB recommended)
            if len(image_bytes) > 500 * 1024:
                warnings.append(
                    f"Logo file size ({len(image_bytes) // 1024}KB) exceeds "
                    f"recommended 500KB. Large images slow email rendering."
                )

            # Check aspect ratio
            aspect = w / h if h > 0 else 0
            if aspect > 6:
                warnings.append(
                    f"Logo aspect ratio {aspect:.1f}:1 is very wide. "
                    f"Consider a more balanced ratio."
                )
            elif aspect < 1:
                warnings.append(
                    f"Logo aspect ratio {aspect:.1f}:1 is portrait-oriented. "
                    f"Landscape logos work better in email headers."
                )

        except Exception as e:
            errors.append(f"Could not read image: {e}")

        return BrandValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    # ------------------------------------------------------------------
    # 9. Multi-org template management
    # ------------------------------------------------------------------

    async def copy_templates_between_orgs(
        self,
        source_org_id: int,
        target_org_id: int,
        template_keys: Optional[List[str]] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Copy email templates from one org to another.

        Args:
            source_org_id: Org to copy from.
            target_org_id: Org to copy to.
            template_keys: Specific keys to copy (None = all).
            overwrite: If True, overwrite existing templates in target.

        Returns:
            Dict with counts of copied, skipped, and error keys.
        """
        from database.models.white_label_config import EmailTemplate

        source_templates = (
            self.db.query(EmailTemplate)
            .filter(
                EmailTemplate.organization_id == source_org_id,
                EmailTemplate.is_active.is_(True),
            )
        )

        if template_keys:
            source_templates = source_templates.filter(
                EmailTemplate.template_key.in_(template_keys)
            )

        source_templates = source_templates.all()

        copied = 0
        skipped = 0
        errored = 0

        for src in source_templates:
            try:
                # Check if target already has this template
                existing = (
                    self.db.query(EmailTemplate)
                    .filter(
                        EmailTemplate.organization_id == target_org_id,
                        EmailTemplate.template_key == src.template_key,
                        EmailTemplate.language == src.language,
                        EmailTemplate.is_active.is_(True),
                    )
                    .first()
                )

                if existing and not overwrite:
                    skipped += 1
                    continue

                await self.upsert_email_template(
                    org_id=target_org_id,
                    template_key=src.template_key,
                    subject_template=src.subject_template,
                    body_html_template=src.body_html_template,
                    body_text_template=src.body_text_template,
                    language=src.language,
                )
                copied += 1

            except Exception as e:
                logger.error(
                    f"Error copying template {src.template_key} from org "
                    f"{source_org_id} to {target_org_id}: {e}"
                )
                errored += 1

        self.db.flush()

        return {
            "source_org_id": source_org_id,
            "target_org_id": target_org_id,
            "copied": copied,
            "skipped": skipped,
            "errored": errored,
            "total_source": len(source_templates),
        }

    async def seed_default_templates(self, org_id: int) -> int:
        """Seed all default email templates for an org.

        Only creates templates that do not already exist. Returns count created.
        """
        created = 0
        for key in TEMPLATE_KEYS:
            existing = await self.get_email_template(org_id, key)
            if existing:
                continue

            default = _DEFAULT_TEMPLATES.get(key)
            if not default:
                continue

            await self.upsert_email_template(
                org_id=org_id,
                template_key=key,
                subject_template=default["subject"],
                body_html_template=default["html_inner"],
                body_text_template=default["text"],
            )
            created += 1

        self.db.flush()
        return created

    # ------------------------------------------------------------------
    # 10. Compliance footer management
    # ------------------------------------------------------------------

    async def _build_compliance_footer(self, org_id: int) -> ComplianceFooter:
        """Build compliance footer HTML and text for an org."""
        config = await self.get_brand_config(org_id)

        company_name = getattr(config, "company_name", None) or "Mortgage Services"
        nmls_number = getattr(config, "nmls_number", None)
        equal_housing = getattr(config, "equal_housing_logo", True)
        disclaimer = getattr(config, "disclaimer_text", None)
        privacy_url = getattr(config, "privacy_policy_url", None)
        terms_url = getattr(config, "terms_of_service_url", None)
        support_email = getattr(config, "support_email", None)
        support_phone = getattr(config, "support_phone", None)
        custom_footer_html = getattr(config, "email_footer_html", None)

        # Build HTML footer
        html_parts = []

        # Custom footer HTML (if org provided one)
        if custom_footer_html:
            html_parts.append(custom_footer_html)

        # Company + NMLS
        identity_line = html.escape(company_name)
        if nmls_number:
            identity_line += f" | NMLS #{html.escape(nmls_number)}"
        html_parts.append(
            f'<p style="margin:0 0 4px;color:#9ca3af;font-size:12px;">{identity_line}</p>'
        )

        # Equal Housing Lender
        if equal_housing:
            html_parts.append(
                '<p style="margin:0 0 4px;color:#9ca3af;font-size:11px;">'
                'Equal Housing Lender</p>'
            )

        # Support contact
        support_parts = []
        if support_email:
            support_parts.append(f'<a href="mailto:{html.escape(support_email)}" style="color:#6b7280;text-decoration:underline;">{html.escape(support_email)}</a>')
        if support_phone:
            support_parts.append(html.escape(support_phone))
        if support_parts:
            html_parts.append(
                f'<p style="margin:0 0 4px;color:#9ca3af;font-size:11px;">'
                f'Support: {" | ".join(support_parts)}</p>'
            )

        # Legal links
        legal_links = []
        if privacy_url:
            legal_links.append(f'<a href="{html.escape(privacy_url)}" style="color:#6b7280;text-decoration:underline;font-size:11px;">Privacy Policy</a>')
        if terms_url:
            legal_links.append(f'<a href="{html.escape(terms_url)}" style="color:#6b7280;text-decoration:underline;font-size:11px;">Terms of Service</a>')
        if legal_links:
            html_parts.append(
                f'<p style="margin:0 0 4px;color:#9ca3af;font-size:11px;">'
                f'{" | ".join(legal_links)}</p>'
            )

        # Disclaimer
        if disclaimer:
            html_parts.append(
                f'<p style="margin:8px 0 0;color:#9ca3af;font-size:10px;line-height:1.4;">'
                f'{html.escape(disclaimer)}</p>'
            )

        footer_html = "\n".join(html_parts)

        # Build plain-text footer
        text_parts = []
        text_identity = company_name
        if nmls_number:
            text_identity += f" | NMLS #{nmls_number}"
        text_parts.append(text_identity)

        if equal_housing:
            text_parts.append("Equal Housing Lender")

        support_text = []
        if support_email:
            support_text.append(support_email)
        if support_phone:
            support_text.append(support_phone)
        if support_text:
            text_parts.append(f"Support: {' | '.join(support_text)}")

        if privacy_url:
            text_parts.append(f"Privacy Policy: {privacy_url}")
        if terms_url:
            text_parts.append(f"Terms of Service: {terms_url}")

        if disclaimer:
            text_parts.append("")
            text_parts.append(disclaimer)

        footer_text = "\n".join(text_parts)

        return ComplianceFooter(html=footer_html, text=footer_text)

    async def get_compliance_footer(self, org_id: int) -> ComplianceFooter:
        """Public method to get the rendered compliance footer for an org."""
        return await self._build_compliance_footer(org_id)

    # ------------------------------------------------------------------
    # 11. Custom domain configuration
    # ------------------------------------------------------------------

    async def set_custom_domain(
        self,
        org_id: int,
        domain: str,
    ) -> Dict[str, Any]:
        """Set a custom portal domain for the org.

        Returns config data including DNS records that need to be created.
        """
        # Normalize domain
        domain = domain.lower().strip()
        if domain.startswith("http://") or domain.startswith("https://"):
            domain = domain.split("://", 1)[1]
        domain = domain.rstrip("/")

        config = await self.upsert_brand_config(org_id, {"custom_domain": domain})

        return {
            "domain": domain,
            "status": "pending_verification",
            "dns_records": [
                {
                    "type": "CNAME",
                    "name": domain,
                    "value": "portal.perenniaai.com",
                    "ttl": 3600,
                },
                {
                    "type": "TXT",
                    "name": f"_perennia-verify.{domain}",
                    "value": f"perennia-org-{org_id}",
                    "ttl": 3600,
                },
            ],
            "instructions": (
                "Add these DNS records to your domain registrar. "
                "Verification typically takes 5-30 minutes after DNS propagation."
            ),
        }

    async def get_custom_domain(self, org_id: int) -> Optional[Dict[str, Any]]:
        """Get current custom domain configuration."""
        config = await self.get_brand_config(org_id)
        domain = getattr(config, "custom_domain", None)
        if not domain:
            return None

        return {
            "domain": domain,
            "portal_url": f"https://{domain}",
            "org_id": org_id,
        }

    # ------------------------------------------------------------------
    # 12. Utility / internal helpers
    # ------------------------------------------------------------------

    def _darken(self, hex_color: str, amount: float = 0.15) -> str:
        """Darken a hex color by a percentage."""
        try:
            r, g, b = _hex_to_rgb(hex_color)
            r = max(0, int(r * (1 - amount)))
            g = max(0, int(g * (1 - amount)))
            b = max(0, int(b * (1 - amount)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _lighten(self, hex_color: str, amount: float = 0.90) -> str:
        """Lighten a hex color (mix toward white by amount)."""
        try:
            r, g, b = _hex_to_rgb(hex_color)
            r = int(r + (255 - r) * amount)
            g = int(g + (255 - g) * amount)
            b = int(b + (255 - b) * amount)
            return f"#{min(r, 255):02x}{min(g, 255):02x}{min(b, 255):02x}"
        except Exception:
            return hex_color

    async def get_default_template(self, template_key: str) -> Optional[Dict[str, str]]:
        """Get the built-in default template content for a given key.

        Useful for resetting a template or viewing the baseline.
        """
        return copy.deepcopy(_DEFAULT_TEMPLATES.get(template_key))

    async def list_available_template_keys(self) -> List[Dict[str, str]]:
        """List all available template keys with descriptions."""
        descriptions = {
            "doc_request": "Initial document request sent to borrower",
            "doc_reminder": "Follow-up reminder for outstanding documents",
            "doc_approved": "Notification that a submitted document was approved",
            "doc_rejected": "Notification that a document was rejected with reason",
            "signature_request": "E-signature request for a document",
            "welcome": "Welcome email when borrower portal is activated",
            "checklist_update": "Progress update on the document checklist",
            "condition_added": "New underwriting condition notification",
        }
        return [
            {"key": key, "description": descriptions.get(key, "")}
            for key in TEMPLATE_KEYS
        ]

    async def get_merge_fields_for_template(self, template_key: str) -> List[str]:
        """Extract all merge field names from a default template.

        Useful for UI to show which variables are available.
        """
        default = _DEFAULT_TEMPLATES.get(template_key)
        if not default:
            return []

        fields: set = set()
        for part in (default["subject"], default["html_inner"], default["text"]):
            fields.update(_MERGE_FIELD_RE.findall(part))

        # Sort for consistent output
        return sorted(fields)


# =============================================================================
# MODULE-LEVEL CONVENIENCE
# =============================================================================

def get_white_label_service(db: Session) -> WhiteLabelService:
    """Factory function for WhiteLabelService."""
    return WhiteLabelService(db)
