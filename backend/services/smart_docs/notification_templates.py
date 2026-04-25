"""
Smart Docs Notification Template Service

Comprehensive HTML email templates for the Smart Docs system covering:
- Document request lifecycle (initial, reminder, urgent, final)
- Document status updates (received, approved, rejected, expiring)
- E-signature workflows (request, reminder, completed, voided)
- Income/review notifications (review complete, task assigned, findings)
- Appointment management (scheduled, reminder, cancelled)

Each template produces both HTML and plain-text versions with inline CSS
for broad email client compatibility, mobile-responsive layout, and
company branding placeholders.
"""

from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

_BRAND_PRIMARY = "#1e3a5f"
_BRAND_ACCENT = "#2563eb"
_COLOR_SUCCESS = "#059669"
_COLOR_WARNING = "#d97706"
_COLOR_DANGER = "#dc2626"
_COLOR_INFO = "#3b82f6"
_COLOR_MUTED = "#6b7280"

_DEFAULT_COMPANY_NAME = "Perennia AI"
_DEFAULT_FROM_NAME = "Sarah from Perennia AI"

_APP_URL = os.getenv("APP_URL", "https://app.perenniaai.com")
_UNSUBSCRIBE_URL = f"{_APP_URL}/settings/notifications"


# =============================================================================
# DATACLASS FOR RENDERED OUTPUT
# =============================================================================

@dataclass
class RenderedTemplate:
    """Result of rendering a notification template."""
    subject: str
    html_body: str
    plain_text: str
    template_name: str
    variables_used: List[str] = field(default_factory=list)


# =============================================================================
# BASE HTML SCAFFOLD
# =============================================================================

def _html_scaffold(
    header_title: str,
    header_subtitle: str,
    body_html: str,
    footer_extra: str = "",
    header_bg: str = _BRAND_PRIMARY,
    company_name: str = _DEFAULT_COMPANY_NAME,
    unsubscribe_url: str = _UNSUBSCRIBE_URL,
    company_logo_url: str = "",
) -> str:
    """Wrap body content in the standard email scaffold with header, footer, and branding."""
    logo_block = ""
    safe_logo_url = _safe_url(company_logo_url)
    if safe_logo_url:
        logo_block = (
            f'<img src="{_safe(safe_logo_url)}" alt="{_safe(company_name)}" '
            f'style="max-height:40px;margin-bottom:12px;" /><br>'
        )

    subtitle_block = ""
    if header_subtitle:
        subtitle_block = (
            f'<p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">'
            f'{_esc(header_subtitle)}</p>'
        )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{_esc(header_title)}</title>
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#f4f5f7;-webkit-text-size-adjust:100%;">
<div style="max-width:600px;margin:0 auto;padding:24px 16px;">
<div style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

<!-- Header -->
<div style="background:{header_bg};padding:28px 24px;text-align:center;">
{logo_block}
<h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;line-height:1.3;">{_esc(header_title)}</h1>
{subtitle_block}
</div>

<!-- Body -->
<div style="padding:28px 24px;">
{body_html}
</div>

<!-- Footer -->
<div style="background:#f9fafb;padding:20px 24px;border-top:1px solid #e5e7eb;text-align:center;">
<p style="margin:0 0 8px;color:#9ca3af;font-size:12px;line-height:1.5;">
This is an automated message from {_esc(company_name)}.
</p>
{footer_extra}
<p style="margin:8px 0 0;color:#9ca3af;font-size:11px;">
<a href="{_safe(_safe_url(unsubscribe_url))}" style="color:#9ca3af;text-decoration:underline;">
Manage notification preferences
</a>
</p>
</div>

</div>
</div>
</body>
</html>"""


# =============================================================================
# HTML BUILDING BLOCKS
# =============================================================================

def _esc(value: Any) -> str:
    """HTML-escape a value, handling None gracefully."""
    if value is None:
        return ""
    return html.escape(str(value))


def _safe(value: Any) -> str:
    """HTML-escape a value for safe insertion into templates.

    Handles None by returning empty string. Converts non-string types
    to string before escaping.
    """
    if value is None:
        return ""
    return html.escape(str(value))


def _safe_url(url: Any) -> str:
    """Validate and return a URL safe for use in href attributes.

    Only allows http:// and https:// schemes. Returns empty string
    for None, empty, or unsafe URLs (e.g. javascript:, data:, vbscript:).
    """
    if url is None:
        return ""
    url_str = str(url).strip()
    if not url_str:
        return ""
    # Only allow http and https schemes
    url_lower = url_str.lower()
    if url_lower.startswith("https://") or url_lower.startswith("http://"):
        return url_str
    # Also allow protocol-relative URLs (//example.com)
    if url_lower.startswith("//"):
        return url_str
    # Reject everything else (javascript:, data:, vbscript:, etc.)
    return ""


def _cta_button(label: str, url: str, color: str = _BRAND_ACCENT) -> str:
    """Render a call-to-action button."""
    safe_url = _safe_url(url)
    if not safe_url:
        return ""
    return (
        f'<div style="text-align:center;margin:24px 0;">'
        f'<a href="{_safe(safe_url)}" style="display:inline-block;padding:14px 32px;'
        f'background:{color};color:#ffffff;text-decoration:none;border-radius:8px;'
        f'font-weight:600;font-size:15px;line-height:1;">{_safe(label)}</a>'
        f'</div>'
    )


def _info_row(label: str, value: str) -> str:
    """Render a label-value info row."""
    return (
        f'<tr>'
        f'<td style="padding:6px 12px 6px 0;color:{_COLOR_MUTED};font-size:14px;white-space:nowrap;vertical-align:top;">'
        f'{_esc(label)}:</td>'
        f'<td style="padding:6px 0;color:#1f2937;font-size:14px;font-weight:500;">'
        f'{_esc(value)}</td>'
        f'</tr>'
    )


def _info_table(rows: List[tuple]) -> str:
    """Render a compact info table from (label, value) tuples."""
    inner = "".join(_info_row(label, value) for label, value in rows if value)
    return f'<table style="border-collapse:collapse;width:100%;margin:16px 0;">{inner}</table>'


def _badge(text: str, bg_color: str = _COLOR_INFO) -> str:
    """Render a small colored badge."""
    return (
        f'<span style="display:inline-block;padding:3px 10px;background:{bg_color}20;'
        f'color:{bg_color};border-radius:4px;font-size:12px;font-weight:600;">'
        f'{_esc(text)}</span>'
    )


def _card(title: str, content_html: str, border_color: str = _COLOR_INFO) -> str:
    """Render a bordered card section."""
    return (
        f'<div style="border:1px solid #e5e7eb;border-left:4px solid {border_color};'
        f'border-radius:8px;padding:16px;margin:16px 0;">'
        f'<h3 style="margin:0 0 8px;color:#1f2937;font-size:16px;">{_esc(title)}</h3>'
        f'{content_html}'
        f'</div>'
    )


def _document_checklist_html(documents: List[Dict[str, Any]]) -> str:
    """Render a document checklist with status indicators."""
    if not documents:
        return ""
    items = []
    for doc in documents:
        name = _esc(doc.get("name", doc.get("title", "Document")))
        status = doc.get("status", "needed")
        note = doc.get("note", "")

        if status == "received":
            icon = "&#9989;"  # check mark
            color = _COLOR_SUCCESS
        elif status == "rejected":
            icon = "&#10060;"  # X
            color = _COLOR_DANGER
        elif status == "urgent":
            icon = "&#9888;"  # warning
            color = _COLOR_WARNING
        else:
            icon = "&#9744;"  # empty checkbox
            color = "#374151"

        note_html = f'<br><span style="color:{_COLOR_MUTED};font-size:12px;">{_esc(note)}</span>' if note else ""
        items.append(
            f'<li style="margin:8px 0;color:{color};font-size:14px;list-style:none;">'
            f'{icon} {name}{note_html}</li>'
        )
    return f'<ul style="margin:12px 0;padding:0;">{"".join(items)}</ul>'


def _document_checklist_plain(documents: List[Dict[str, Any]]) -> str:
    """Render a document checklist as plain text."""
    if not documents:
        return ""
    lines = []
    for i, doc in enumerate(documents, 1):
        name = doc.get("name", doc.get("title", "Document"))
        status = doc.get("status", "needed")
        marker = "[x]" if status == "received" else "[ ]"
        note = doc.get("note", "")
        line = f"  {marker} {name}"
        if note:
            line += f" -- {note}"
        lines.append(line)
    return "\n".join(lines)


# =============================================================================
# TEMPLATE DEFINITIONS
# =============================================================================

# ---- Document Request Templates ----

def _template_document_request_initial(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    documents = v.get("document_list", [])
    due_date = v.get("due_date", "")
    portal_url = v.get("portal_url", "")
    loan_number = v.get("loan_number", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    due_html = ""
    if due_date:
        due_html = (
            f'<p style="margin:12px 0;padding:10px 14px;background:#fef3c7;border-radius:6px;'
            f'color:#92400e;font-size:14px;">'
            f'<strong>Please submit by:</strong> {_esc(due_date)}</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'To keep your loan application moving forward, we need the following documents. '
        f'Please upload them through our secure portal at your earliest convenience.</p>'
        f'{_document_checklist_html(documents)}'
        f'{due_html}'
        f'{_cta_button("Upload Documents", portal_url) if portal_url else ""}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'If you have any questions about what is needed, please reply to this email or '
        f'contact {_esc(lo_name)} directly.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"To keep your loan application moving forward, we need the following documents:\n\n"
        f"{_document_checklist_plain(documents)}\n\n"
        f"{'Please submit by: ' + due_date + chr(10) + chr(10) if due_date else ''}"
        f"{'Upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"If you have questions, reply to this email or contact {lo_name}.\n\n"
        f"Best regards,\n{lo_name}"
    )

    subtitle = f"{len(documents)} document{'s' if len(documents) != 1 else ''} needed"
    if loan_number:
        subtitle += f" | Loan #{loan_number}"

    return RenderedTemplate(
        subject=f"Documents Needed for Your Loan Application ({len(documents)} items)",
        html_body=_html_scaffold(
            "Documents Needed", subtitle, body,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_request_initial",
        variables_used=["borrower_name", "document_list", "due_date", "portal_url",
                        "loan_officer_name", "loan_number"],
    )


def _template_document_request_reminder(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    documents = v.get("document_list", [])
    due_date = v.get("due_date", "")
    portal_url = v.get("portal_url", "")
    days_waiting = v.get("days_waiting", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    waiting_note = ""
    if days_waiting:
        waiting_note = (
            f'<p style="margin:0 0 16px;color:#92400e;font-size:14px;'
            f'padding:10px 14px;background:#fef3c7;border-radius:6px;">'
            f'These documents have been outstanding for {_esc(str(days_waiting))} days.</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'This is a friendly reminder that we are still waiting on the following documents '
        f'for your loan application:</p>'
        f'{waiting_note}'
        f'{_document_checklist_html(documents)}'
        f'{_cta_button("Upload Documents", portal_url) if portal_url else ""}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'Submitting these documents promptly helps us keep your loan on track. '
        f'If you need help locating any of these, please reach out.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"This is a friendly reminder that we still need the following documents:\n\n"
        f"{_document_checklist_plain(documents)}\n\n"
        f"{'These have been outstanding for ' + str(days_waiting) + ' days.' + chr(10) + chr(10) if days_waiting else ''}"
        f"{'Upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Submitting promptly helps keep your loan on track.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Reminder: {len(documents)} Document{'s' if len(documents) != 1 else ''} Still Needed",
        html_body=_html_scaffold(
            "Document Reminder", f"{len(documents)} outstanding", body,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_request_reminder",
        variables_used=["borrower_name", "document_list", "due_date", "portal_url",
                        "loan_officer_name", "days_waiting"],
    )


def _template_document_request_urgent(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    documents = v.get("document_list", [])
    due_date = v.get("due_date", "")
    closing_date = v.get("closing_date", "")
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    closing_note = ""
    if closing_date:
        closing_note = (
            f'<div style="margin:0 0 16px;padding:14px;background:#fef2f2;border:1px solid #fecaca;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#991b1b;font-weight:600;">Your closing is scheduled for '
            f'{_esc(closing_date)}.</p>'
            f'<p style="margin:6px 0 0;color:#b91c1c;font-size:13px;">'
            f'Missing documents may delay your closing date.</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#991b1b;font-weight:600;line-height:1.6;">'
        f'We urgently need the following documents to avoid delays with your loan:</p>'
        f'{closing_note}'
        f'{_document_checklist_html(documents)}'
        f'{_cta_button("Upload Now", portal_url, _COLOR_DANGER) if portal_url else ""}'
        f'<p style="margin:20px 0 0;color:#4b5563;font-size:14px;line-height:1.6;">'
        f'Please upload these as soon as possible. If you are having trouble obtaining any '
        f'of these documents, please call {_esc(lo_name)} immediately so we can discuss '
        f'alternatives.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"URGENT: We need the following documents immediately to avoid delays:\n\n"
        f"{_document_checklist_plain(documents)}\n\n"
        f"{'CLOSING DATE: ' + closing_date + chr(10) + 'Missing documents may delay your closing.' + chr(10) + chr(10) if closing_date else ''}"
        f"{'Upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Please upload ASAP or call {lo_name} if you need help.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject="URGENT: Documents Needed to Avoid Closing Delay",
        html_body=_html_scaffold(
            "Urgent: Documents Needed", "Action required immediately",
            body, header_bg=_COLOR_DANGER,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_request_urgent",
        variables_used=["borrower_name", "document_list", "due_date", "closing_date",
                        "portal_url", "loan_officer_name"],
    )


def _template_document_request_final(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    documents = v.get("document_list", [])
    escalation_date = v.get("escalation_date", "")
    portal_url = v.get("portal_url", "")
    lo_phone = v.get("loan_officer_phone", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    escalation_html = ""
    if escalation_date:
        escalation_html = (
            f'<div style="margin:16px 0;padding:14px;background:#fef2f2;border:1px solid #fecaca;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#991b1b;font-size:14px;">'
            f'If we do not receive these documents by <strong>{_esc(escalation_date)}</strong>, '
            f'your file may be placed on hold, which could impact your closing timeline.</p>'
            f'</div>'
        )

    phone_line = ""
    if lo_phone:
        phone_line = f' or call <strong>{_esc(lo_phone)}</strong>'

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'This is our final notice regarding outstanding documents for your loan. '
        f'We have reached out several times and still need the following:</p>'
        f'{_document_checklist_html(documents)}'
        f'{escalation_html}'
        f'{_cta_button("Upload Documents Now", portal_url, _COLOR_DANGER) if portal_url else ""}'
        f'<p style="margin:20px 0 0;color:#4b5563;font-size:14px;line-height:1.6;">'
        f'We want to help you close your loan on time. Please reply to this email{phone_line} '
        f'so we can assist you.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"FINAL NOTICE: We still need the following documents for your loan:\n\n"
        f"{_document_checklist_plain(documents)}\n\n"
        f"{'If not received by ' + escalation_date + ', your file may be placed on hold.' + chr(10) + chr(10) if escalation_date else ''}"
        f"{'Upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Please reply or call {lo_name}{' at ' + lo_phone if lo_phone else ''} for help.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject="Final Notice: Documents Required for Your Loan",
        html_body=_html_scaffold(
            "Final Document Notice", "Immediate action required",
            body, header_bg="#7f1d1d",
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_request_final",
        variables_used=["borrower_name", "document_list", "escalation_date",
                        "portal_url", "loan_officer_name", "loan_officer_phone"],
    )


# ---- Document Status Templates ----

def _template_document_received(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    document_name = v.get("document_name", "your document")
    received_date = v.get("received_date", "")
    remaining_count = v.get("remaining_count", 0)
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    remaining_html = ""
    if remaining_count and int(remaining_count) > 0:
        remaining_html = (
            f'<div style="margin:16px 0;padding:14px;background:#f0fdf4;border:1px solid #bbf7d0;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#166534;font-size:14px;">'
            f'You have <strong>{_esc(str(remaining_count))}</strong> remaining document'
            f'{"s" if int(remaining_count) != 1 else ""} to submit.</p>'
            f'</div>'
        )
    elif remaining_count == 0:
        remaining_html = (
            f'<div style="margin:16px 0;padding:14px;background:#f0fdf4;border:1px solid #bbf7d0;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#166534;font-size:14px;font-weight:600;">'
            f'All documents have been received. Your file is complete!</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'We have received <strong>{_esc(document_name)}</strong>'
        f'{" on " + _esc(received_date) if received_date else ""}. '
        f'Thank you for submitting this promptly.</p>'
        f'{remaining_html}'
        f'{_cta_button("View Your Documents", portal_url) if portal_url else ""}'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"We have received {document_name}"
        f"{' on ' + received_date if received_date else ''}. Thank you!\n\n"
        f"{'You have ' + str(remaining_count) + ' document(s) remaining.' + chr(10) + chr(10) if remaining_count else ''}"
        f"{'All documents received - your file is complete!' + chr(10) + chr(10) if remaining_count == 0 else ''}"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Document Received: {_safe(document_name)}",
        html_body=_html_scaffold(
            "Document Received", document_name, body,
            header_bg=_COLOR_SUCCESS,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_received",
        variables_used=["borrower_name", "document_name", "received_date",
                        "remaining_count", "portal_url", "loan_officer_name"],
    )


def _template_document_approved(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    document_name = v.get("document_name", "your document")
    next_step = v.get("next_step", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    next_step_html = ""
    if next_step:
        next_step_html = (
            f'<div style="margin:16px 0;padding:14px;background:#eff6ff;border:1px solid #bfdbfe;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#1e40af;font-size:14px;">'
            f'<strong>Next step:</strong> {_esc(next_step)}</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'Great news! <strong>{_esc(document_name)}</strong> has been reviewed and '
        f'<span style="color:{_COLOR_SUCCESS};font-weight:600;">approved</span>.</p>'
        f'{next_step_html}'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Great news! {document_name} has been reviewed and approved.\n\n"
        f"{'Next step: ' + next_step + chr(10) + chr(10) if next_step else ''}"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Approved: {_safe(document_name)}",
        html_body=_html_scaffold(
            "Document Approved", document_name, body,
            header_bg=_COLOR_SUCCESS,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_approved",
        variables_used=["borrower_name", "document_name", "next_step", "loan_officer_name"],
    )


def _template_document_rejected(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    document_name = v.get("document_name", "your document")
    rejection_reason = v.get("rejection_reason", "The document did not meet requirements.")
    instructions = v.get("reupload_instructions", "")
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    instructions_html = ""
    if instructions:
        instructions_html = (
            f'<div style="margin:16px 0;padding:14px;background:#f3f4f6;border-radius:8px;">'
            f'<p style="margin:0 0 6px;color:#374151;font-weight:600;font-size:14px;">'
            f'How to fix this:</p>'
            f'<p style="margin:0;color:#4b5563;font-size:14px;line-height:1.6;">'
            f'{_esc(instructions)}</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 12px;color:#4b5563;line-height:1.6;">'
        f'Unfortunately, <strong>{_esc(document_name)}</strong> could not be accepted.</p>'
        f'{_card("Reason", f"<p style=&quot;margin:0;color:#4b5563;font-size:14px;&quot;>{_esc(rejection_reason)}</p>", _COLOR_DANGER)}'
        f'{instructions_html}'
        f'{_cta_button("Re-upload Document", portal_url) if portal_url else ""}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'If you need help, please reply to this email or contact {_esc(lo_name)}.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Unfortunately, {document_name} could not be accepted.\n\n"
        f"Reason: {rejection_reason}\n\n"
        f"{'How to fix: ' + instructions + chr(10) + chr(10) if instructions else ''}"
        f"{'Re-upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"If you need help, reply or contact {lo_name}.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Action Required: {_safe(document_name)} Needs Resubmission",
        html_body=_html_scaffold(
            "Document Needs Resubmission", document_name, body,
            header_bg=_COLOR_DANGER,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_rejected",
        variables_used=["borrower_name", "document_name", "rejection_reason",
                        "reupload_instructions", "portal_url", "loan_officer_name"],
    )


def _template_document_expiring(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    document_name = v.get("document_name", "your document")
    expiration_date = v.get("expiration_date", "")
    days_until_expiry = v.get("days_until_expiry", "")
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    urgency_color = _COLOR_WARNING
    urgency_text = "expiring soon"
    if days_until_expiry and int(days_until_expiry) <= 7:
        urgency_color = _COLOR_DANGER
        urgency_text = f"expires in {days_until_expiry} day{'s' if int(days_until_expiry) != 1 else ''}"

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'Your <strong>{_esc(document_name)}</strong> is {_esc(urgency_text)}'
        f'{" on " + _esc(expiration_date) if expiration_date else ""}. '
        f'We need a current version to continue processing your loan.</p>'
        f'<div style="margin:16px 0;padding:14px;background:#fffbeb;border:1px solid #fde68a;'
        f'border-radius:8px;">'
        f'<p style="margin:0;color:#92400e;font-size:14px;">'
        f'Please upload an updated version as soon as possible to avoid delays.</p>'
        f'</div>'
        f'{_cta_button("Upload Updated Document", portal_url, urgency_color) if portal_url else ""}'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Your {document_name} is {urgency_text}"
        f"{' on ' + expiration_date if expiration_date else ''}.\n\n"
        f"Please upload an updated version to avoid delays.\n\n"
        f"{'Upload here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Document Expiring: {_safe(document_name)}",
        html_body=_html_scaffold(
            "Document Expiring", document_name, body,
            header_bg=urgency_color,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="document_expiring",
        variables_used=["borrower_name", "document_name", "expiration_date",
                        "days_until_expiry", "portal_url", "loan_officer_name"],
    )


# ---- E-Signature Templates ----

def _template_esign_request(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    envelope_name = v.get("envelope_name", "Loan Documents")
    signing_url = v.get("signing_url", "")
    document_list = v.get("document_list", [])
    expiration = v.get("signing_expiration", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    doc_list_html = ""
    if document_list:
        items = "".join(
            f'<li style="margin:6px 0;color:#4b5563;font-size:14px;">{_esc(d.get("name", d) if isinstance(d, dict) else d)}</li>'
            for d in document_list
        )
        doc_list_html = (
            f'<div style="margin:16px 0;">'
            f'<p style="margin:0 0 8px;color:#374151;font-weight:600;font-size:14px;">'
            f'Documents to sign:</p>'
            f'<ul style="margin:0;padding-left:20px;">{items}</ul>'
            f'</div>'
        )

    expiry_html = ""
    if expiration:
        expiry_html = (
            f'<p style="margin:12px 0;color:{_COLOR_MUTED};font-size:13px;">'
            f'This signing link expires on {_esc(expiration)}.</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'You have documents ready for your electronic signature: '
        f'<strong>{_esc(envelope_name)}</strong>.</p>'
        f'{doc_list_html}'
        f'{_cta_button("Review & Sign Documents", signing_url, _BRAND_ACCENT) if signing_url else ""}'
        f'{expiry_html}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'This is a secure electronic signature process. Your signature is legally binding.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"You have documents ready for electronic signature: {envelope_name}.\n\n"
        + ("Documents to sign:\n" + "\n".join(
            f"  - {d.get('name', d) if isinstance(d, dict) else d}" for d in document_list
        ) + "\n\n" if document_list else "")
        + (f"Sign here: {signing_url}\n\n" if signing_url else "")
        + (f"Link expires: {expiration}\n\n" if expiration else "")
        + f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Signature Required: {_safe(envelope_name)}",
        html_body=_html_scaffold(
            "Signature Required", envelope_name, body,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="esign_request",
        variables_used=["borrower_name", "envelope_name", "signing_url",
                        "document_list", "signing_expiration", "loan_officer_name"],
    )


def _template_esign_reminder(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    envelope_name = v.get("envelope_name", "Loan Documents")
    signing_url = v.get("signing_url", "")
    days_pending = v.get("days_pending", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    pending_note = ""
    if days_pending:
        pending_note = (
            f'<p style="margin:0 0 16px;padding:10px 14px;background:#fef3c7;'
            f'border-radius:6px;color:#92400e;font-size:14px;">'
            f'This signing request has been pending for {_esc(str(days_pending))} days.</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'This is a reminder that <strong>{_esc(envelope_name)}</strong> is still '
        f'awaiting your signature. The signing process takes just a few minutes.</p>'
        f'{pending_note}'
        f'{_cta_button("Sign Now", signing_url, _COLOR_WARNING) if signing_url else ""}'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Reminder: {envelope_name} is still awaiting your signature.\n\n"
        f"{'Pending for ' + str(days_pending) + ' days.' + chr(10) + chr(10) if days_pending else ''}"
        f"{'Sign here: ' + signing_url + chr(10) + chr(10) if signing_url else ''}"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Reminder: Signature Needed - {_safe(envelope_name)}",
        html_body=_html_scaffold(
            "Signature Reminder", envelope_name, body,
            header_bg=_COLOR_WARNING,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="esign_reminder",
        variables_used=["borrower_name", "envelope_name", "signing_url",
                        "days_pending", "loan_officer_name"],
    )


def _template_esign_completed(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    envelope_name = v.get("envelope_name", "Loan Documents")
    completed_date = v.get("completed_date", "")
    download_url = v.get("download_url", "")
    next_step = v.get("next_step", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    next_step_html = ""
    if next_step:
        next_step_html = (
            f'<div style="margin:16px 0;padding:14px;background:#eff6ff;border:1px solid #bfdbfe;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#1e40af;font-size:14px;">'
            f'<strong>What happens next:</strong> {_esc(next_step)}</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'All signatures have been completed for <strong>{_esc(envelope_name)}</strong>'
        f'{" on " + _esc(completed_date) if completed_date else ""}. '
        f'Thank you!</p>'
        f'{next_step_html}'
        f'{_cta_button("Download Signed Documents", download_url) if download_url else ""}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'A copy of the signed documents has been saved to your file.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"All signatures completed for {envelope_name}"
        f"{' on ' + completed_date if completed_date else ''}. Thank you!\n\n"
        f"{'Next: ' + next_step + chr(10) + chr(10) if next_step else ''}"
        f"{'Download: ' + download_url + chr(10) + chr(10) if download_url else ''}"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Signing Complete: {_safe(envelope_name)}",
        html_body=_html_scaffold(
            "Signing Complete", "All signatures received", body,
            header_bg=_COLOR_SUCCESS,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="esign_completed",
        variables_used=["borrower_name", "envelope_name", "completed_date",
                        "download_url", "next_step", "loan_officer_name"],
    )


def _template_esign_voided(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    envelope_name = v.get("envelope_name", "Loan Documents")
    void_reason = v.get("void_reason", "The document package has been updated.")
    next_action = v.get("next_action", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    next_html = ""
    if next_action:
        next_html = (
            f'<div style="margin:16px 0;padding:14px;background:#eff6ff;border:1px solid #bfdbfe;'
            f'border-radius:8px;">'
            f'<p style="margin:0;color:#1e40af;font-size:14px;">{_esc(next_action)}</p>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'The signing request for <strong>{_esc(envelope_name)}</strong> has been voided. '
        f'Any previous signing links are no longer valid.</p>'
        f'{_card("Reason", f"<p style=&quot;margin:0;color:#4b5563;font-size:14px;&quot;>{_esc(void_reason)}</p>", _COLOR_MUTED)}'
        f'{next_html}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'No action is needed from you at this time unless you receive a new signing request.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"The signing request for {envelope_name} has been voided.\n\n"
        f"Reason: {void_reason}\n\n"
        f"{'Next: ' + next_action + chr(10) + chr(10) if next_action else ''}"
        f"No action needed unless you receive a new signing request.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Signing Voided: {_safe(envelope_name)}",
        html_body=_html_scaffold(
            "Signing Request Voided", envelope_name, body,
            header_bg=_COLOR_MUTED,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="esign_voided",
        variables_used=["borrower_name", "envelope_name", "void_reason",
                        "next_action", "loan_officer_name"],
    )


# ---- Income / Review Templates ----

def _template_income_review_complete(v: Dict[str, Any]) -> RenderedTemplate:
    lo_name = v.get("loan_officer_name", "Loan Officer")
    borrower = v.get("borrower_name", "the borrower")
    loan_number = v.get("loan_number", "")
    income_total = v.get("income_total", "")
    income_sources = v.get("income_sources", [])
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    sources_html = ""
    if income_sources:
        rows = "".join(
            f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:#374151;font-size:14px;">'
            f'{_esc(s.get("type", "Income"))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:#374151;font-size:14px;text-align:right;font-weight:500;">'
            f'{_esc(s.get("amount", ""))}</td></tr>'
            for s in income_sources
        )
        sources_html = (
            f'<table style="width:100%;border-collapse:collapse;margin:16px 0;">'
            f'<tr style="background:#f9fafb;">'
            f'<th style="padding:8px 12px;text-align:left;color:{_COLOR_MUTED};font-size:12px;text-transform:uppercase;">Source</th>'
            f'<th style="padding:8px 12px;text-align:right;color:{_COLOR_MUTED};font-size:12px;text-transform:uppercase;">Monthly Amount</th>'
            f'</tr>{rows}'
            f'<tr style="background:#f0fdf4;">'
            f'<td style="padding:10px 12px;font-weight:700;color:#166534;font-size:14px;">Total</td>'
            f'<td style="padding:10px 12px;font-weight:700;color:#166534;font-size:14px;text-align:right;">'
            f'{_esc(income_total)}</td></tr>'
            f'</table>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(lo_name)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'The income calculation for <strong>{_esc(borrower)}</strong>'
        f'{" (Loan #" + _esc(loan_number) + ")" if loan_number else ""} '
        f'has been completed and is ready for your review.</p>'
        f'{sources_html}'
        f'{_cta_button("Review Income Calculation", portal_url) if portal_url else ""}'
        f'<p style="margin:16px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'Please review and approve or request adjustments.</p>'
    )

    sources_plain = ""
    if income_sources:
        sources_plain = "\nIncome Breakdown:\n" + "\n".join(
            f"  {s.get('type', 'Income')}: {s.get('amount', '')}" for s in income_sources
        ) + f"\n  Total: {income_total}\n"

    plain = (
        f"Hi {lo_name},\n\n"
        f"Income calculation for {borrower}"
        f"{' (Loan #' + loan_number + ')' if loan_number else ''} is ready for review.\n"
        f"{sources_plain}\n"
        f"{'Review here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Please review and approve or request adjustments."
    )

    return RenderedTemplate(
        subject=f"Income Review Ready: {_safe(borrower)}" + (f" - Loan #{_safe(loan_number)}" if loan_number else ""),
        html_body=_html_scaffold(
            "Income Calculation Complete", f"Ready for review", body,
            header_bg=_COLOR_INFO,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="income_review_complete",
        variables_used=["loan_officer_name", "borrower_name", "loan_number",
                        "income_total", "income_sources", "portal_url"],
    )


def _template_income_task_assigned(v: Dict[str, Any]) -> RenderedTemplate:
    lo_name = v.get("loan_officer_name", "Loan Officer")
    borrower = v.get("borrower_name", "the borrower")
    loan_number = v.get("loan_number", "")
    task_description = v.get("task_description", "Income verification task")
    due_date = v.get("due_date", "")
    assigned_by = v.get("assigned_by", "")
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    info_rows = [
        ("Borrower", borrower),
        ("Loan", f"#{loan_number}" if loan_number else ""),
        ("Task", task_description),
        ("Due", due_date),
        ("Assigned by", assigned_by),
    ]

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(lo_name)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'An income verification task has been assigned to you:</p>'
        f'{_info_table(info_rows)}'
        f'{_cta_button("View Task", portal_url) if portal_url else ""}'
    )

    plain = (
        f"Hi {lo_name},\n\n"
        f"An income verification task has been assigned to you:\n\n"
        f"  Borrower: {borrower}\n"
        f"{'  Loan: #' + loan_number + chr(10) if loan_number else ''}"
        f"  Task: {task_description}\n"
        f"{'  Due: ' + due_date + chr(10) if due_date else ''}"
        f"{'  Assigned by: ' + assigned_by + chr(10) if assigned_by else ''}\n"
        f"{'View: ' + portal_url + chr(10) if portal_url else ''}"
    )

    return RenderedTemplate(
        subject=f"Task Assigned: Income Verification - {_safe(borrower)}",
        html_body=_html_scaffold(
            "Task Assigned", "Income Verification", body,
            header_bg=_COLOR_INFO,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="income_task_assigned",
        variables_used=["loan_officer_name", "borrower_name", "loan_number",
                        "task_description", "due_date", "assigned_by", "portal_url"],
    )


def _template_review_findings(v: Dict[str, Any]) -> RenderedTemplate:
    lo_name = v.get("loan_officer_name", "Loan Officer")
    borrower = v.get("borrower_name", "the borrower")
    loan_number = v.get("loan_number", "")
    findings = v.get("findings", [])
    severity = v.get("overall_severity", "medium")
    portal_url = v.get("portal_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    severity_colors = {"critical": _COLOR_DANGER, "high": "#ea580c", "medium": _COLOR_WARNING, "low": _COLOR_INFO}
    sev_color = severity_colors.get(severity, _COLOR_WARNING)

    findings_html = ""
    if findings:
        items = ""
        for f_item in findings:
            f_sev = f_item.get("severity", "medium")
            f_color = severity_colors.get(f_sev, _COLOR_WARNING)
            items += (
                f'<div style="margin:8px 0;padding:12px;border-left:3px solid {f_color};'
                f'background:#fafafa;border-radius:0 6px 6px 0;">'
                f'{_badge(f_sev.upper(), f_color)} '
                f'<span style="color:#1f2937;font-size:14px;font-weight:500;">'
                f'{_esc(f_item.get("title", "Finding"))}</span>'
                f'<p style="margin:6px 0 0;color:#4b5563;font-size:13px;">'
                f'{_esc(f_item.get("description", ""))}</p>'
                f'</div>'
            )
        findings_html = f'<div style="margin:16px 0;">{items}</div>'

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(lo_name)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'The AI document review for <strong>{_esc(borrower)}</strong>'
        f'{" (Loan #" + _esc(loan_number) + ")" if loan_number else ""} '
        f'found <strong>{len(findings)}</strong> item{"s" if len(findings) != 1 else ""} '
        f'requiring your attention.</p>'
        f'{findings_html}'
        f'{_cta_button("Review Findings", portal_url) if portal_url else ""}'
        f'<p style="margin:16px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'Please review these findings and take appropriate action.</p>'
    )

    findings_plain = ""
    if findings:
        findings_plain = "\nFindings:\n" + "\n".join(
            f"  [{f_item.get('severity', 'medium').upper()}] "
            f"{f_item.get('title', 'Finding')}: {f_item.get('description', '')}"
            for f_item in findings
        ) + "\n"

    plain = (
        f"Hi {lo_name},\n\n"
        f"AI review for {borrower}"
        f"{' (Loan #' + loan_number + ')' if loan_number else ''} "
        f"found {len(findings)} item(s) requiring attention.\n"
        f"{findings_plain}\n"
        f"{'Review here: ' + portal_url + chr(10) + chr(10) if portal_url else ''}"
        f"Please review and take appropriate action."
    )

    return RenderedTemplate(
        subject=f"Review Findings: {len(findings)} Issue{'s' if len(findings) != 1 else ''} - {_safe(borrower)}",
        html_body=_html_scaffold(
            "Review Findings", f"{len(findings)} item{'s' if len(findings) != 1 else ''} need attention",
            body, header_bg=sev_color,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="review_findings",
        variables_used=["loan_officer_name", "borrower_name", "loan_number",
                        "findings", "overall_severity", "portal_url"],
    )


# ---- Appointment Templates ----

def _template_appointment_scheduled(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    appointment_date = v.get("appointment_date", "")
    appointment_time = v.get("appointment_time", "")
    location = v.get("location", "")
    meeting_url = v.get("meeting_url", "")
    notes = v.get("appointment_notes", "")
    documents_to_bring = v.get("documents_to_bring", [])
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    info_rows = [
        ("Date", appointment_date),
        ("Time", appointment_time),
        ("Location", location if location else ("Virtual Meeting" if meeting_url else "")),
    ]

    meeting_button = ""
    if meeting_url:
        meeting_button = _cta_button("Join Virtual Meeting", meeting_url)

    docs_html = ""
    if documents_to_bring:
        items = "".join(
            f'<li style="margin:4px 0;color:#4b5563;font-size:14px;">'
            f'{_esc(d.get("name", d) if isinstance(d, dict) else d)}</li>'
            for d in documents_to_bring
        )
        docs_html = (
            f'<div style="margin:16px 0;padding:14px;background:#f3f4f6;border-radius:8px;">'
            f'<p style="margin:0 0 8px;color:#374151;font-weight:600;font-size:14px;">'
            f'Please bring or prepare:</p>'
            f'<ul style="margin:0;padding-left:20px;">{items}</ul>'
            f'</div>'
        )

    notes_html = ""
    if notes:
        notes_html = (
            f'<p style="margin:12px 0;color:{_COLOR_MUTED};font-size:13px;">'
            f'<strong>Notes:</strong> {_esc(notes)}</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'Your document collection appointment has been confirmed.</p>'
        f'{_info_table(info_rows)}'
        f'{meeting_button}'
        f'{docs_html}'
        f'{notes_html}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'Need to reschedule? Reply to this email or contact {_esc(lo_name)}.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    docs_plain = ""
    if documents_to_bring:
        docs_plain = "\nPlease bring or prepare:\n" + "\n".join(
            f"  - {d.get('name', d) if isinstance(d, dict) else d}" for d in documents_to_bring
        ) + "\n"

    plain = (
        f"Hi {borrower},\n\n"
        f"Your document collection appointment is confirmed.\n\n"
        f"  Date: {appointment_date}\n"
        f"  Time: {appointment_time}\n"
        f"  Location: {location or ('Virtual Meeting' if meeting_url else 'TBD')}\n"
        f"{'  Meeting link: ' + meeting_url + chr(10) if meeting_url else ''}"
        f"{docs_plain}\n"
        f"{'Notes: ' + notes + chr(10) + chr(10) if notes else ''}"
        f"Need to reschedule? Reply or contact {lo_name}.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Appointment Confirmed: {_safe(appointment_date)} at {_safe(appointment_time)}",
        html_body=_html_scaffold(
            "Appointment Confirmed", f"{appointment_date} at {appointment_time}",
            body, header_bg=_COLOR_SUCCESS,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="appointment_scheduled",
        variables_used=["borrower_name", "appointment_date", "appointment_time",
                        "location", "meeting_url", "appointment_notes",
                        "documents_to_bring", "loan_officer_name"],
    )


def _template_appointment_reminder(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    appointment_date = v.get("appointment_date", "")
    appointment_time = v.get("appointment_time", "")
    location = v.get("location", "")
    meeting_url = v.get("meeting_url", "")
    hours_until = v.get("hours_until", "")
    documents_to_bring = v.get("documents_to_bring", [])
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    time_label = "coming up soon"
    if hours_until:
        hrs = int(hours_until)
        if hrs >= 24:
            time_label = f"tomorrow" if hrs < 48 else f"in {hrs // 24} days"
        else:
            time_label = f"in {hrs} hour{'s' if hrs != 1 else ''}"

    info_rows = [
        ("Date", appointment_date),
        ("Time", appointment_time),
        ("Location", location if location else ("Virtual Meeting" if meeting_url else "")),
    ]

    docs_html = ""
    if documents_to_bring:
        items = "".join(
            f'<li style="margin:4px 0;color:#4b5563;font-size:14px;">'
            f'{_esc(d.get("name", d) if isinstance(d, dict) else d)}</li>'
            for d in documents_to_bring
        )
        docs_html = (
            f'<div style="margin:16px 0;padding:14px;background:#f3f4f6;border-radius:8px;">'
            f'<p style="margin:0 0 8px;color:#374151;font-weight:600;font-size:14px;">'
            f'Remember to bring:</p>'
            f'<ul style="margin:0;padding-left:20px;">{items}</ul>'
            f'</div>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'This is a reminder that your appointment is <strong>{_esc(time_label)}</strong>.</p>'
        f'{_info_table(info_rows)}'
        f'{_cta_button("Join Meeting", meeting_url) if meeting_url else ""}'
        f'{docs_html}'
        f'<p style="margin:20px 0 0;color:{_COLOR_MUTED};font-size:13px;">'
        f'Need to reschedule? Reply to this email or contact {_esc(lo_name)}.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Reminder: Your appointment is {time_label}.\n\n"
        f"  Date: {appointment_date}\n"
        f"  Time: {appointment_time}\n"
        f"  Location: {location or ('Virtual' if meeting_url else 'TBD')}\n"
        f"{'  Meeting link: ' + meeting_url + chr(10) if meeting_url else ''}\n"
        f"Need to reschedule? Reply or contact {lo_name}.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Appointment Reminder: {_safe(time_label.capitalize())} - {_safe(appointment_date)}",
        html_body=_html_scaffold(
            "Appointment Reminder", f"{appointment_date} at {appointment_time}",
            body, header_bg=_COLOR_INFO,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="appointment_reminder",
        variables_used=["borrower_name", "appointment_date", "appointment_time",
                        "location", "meeting_url", "hours_until",
                        "documents_to_bring", "loan_officer_name"],
    )


def _template_appointment_cancelled(v: Dict[str, Any]) -> RenderedTemplate:
    borrower = v.get("borrower_name", "Valued Client")
    lo_name = v.get("loan_officer_name", "Your Loan Officer")
    appointment_date = v.get("appointment_date", "")
    appointment_time = v.get("appointment_time", "")
    cancellation_reason = v.get("cancellation_reason", "")
    reschedule_url = v.get("reschedule_url", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    reason_html = ""
    if cancellation_reason:
        reason_html = (
            f'<p style="margin:12px 0;color:{_COLOR_MUTED};font-size:14px;">'
            f'<strong>Reason:</strong> {_esc(cancellation_reason)}</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'<p style="margin:0 0 16px;color:#4b5563;line-height:1.6;">'
        f'Your appointment'
        f'{" on " + _esc(appointment_date) if appointment_date else ""}'
        f'{" at " + _esc(appointment_time) if appointment_time else ""}'
        f' has been cancelled.</p>'
        f'{reason_html}'
        f'{_cta_button("Reschedule Appointment", reschedule_url) if reschedule_url else ""}'
        f'<p style="margin:20px 0 0;color:#4b5563;font-size:14px;line-height:1.6;">'
        f'We apologize for any inconvenience. Please reschedule at your earliest convenience '
        f'so we can keep your loan on track.</p>'
        f'<p style="margin:16px 0 0;color:#374151;">Best regards,<br>'
        f'<strong>{_esc(lo_name)}</strong></p>'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"Your appointment"
        f"{' on ' + appointment_date if appointment_date else ''}"
        f"{' at ' + appointment_time if appointment_time else ''}"
        f" has been cancelled.\n\n"
        f"{'Reason: ' + cancellation_reason + chr(10) + chr(10) if cancellation_reason else ''}"
        f"{'Reschedule here: ' + reschedule_url + chr(10) + chr(10) if reschedule_url else ''}"
        f"We apologize for any inconvenience.\n\n"
        f"Best regards,\n{lo_name}"
    )

    return RenderedTemplate(
        subject=f"Appointment Cancelled" + (f": {_safe(appointment_date)}" if appointment_date else ""),
        html_body=_html_scaffold(
            "Appointment Cancelled",
            f"{appointment_date} at {appointment_time}" if appointment_date and appointment_time else "",
            body, header_bg=_COLOR_MUTED,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="appointment_cancelled",
        variables_used=["borrower_name", "appointment_date", "appointment_time",
                        "cancellation_reason", "reschedule_url", "loan_officer_name"],
    )


# ---- Generic Document Status Update ----

def _template_doc_status_update(v: Dict[str, Any]) -> RenderedTemplate:
    """Generic document status update notification.

    Used by NotificationCenterService for email delivery of in-app
    notifications. Handles various status transitions (uploaded, approved,
    rejected, needs_review, expiring, etc.) via template variables.
    """
    borrower = v.get("borrower_name", "Team Member")
    document_title = v.get("document_title", "Document Update")
    status = v.get("status", "info")
    status_message = v.get("status_message", "A document status has changed.")
    action_url = v.get("action_url", "")
    action_label = v.get("action_label", "View Details")
    loan_number = v.get("loan_number", "")
    company_name = v.get("company_name", _DEFAULT_COMPANY_NAME)
    company_logo_url = v.get("company_logo_url", "")

    # Map severity to color
    severity_colors = {
        "info": _COLOR_INFO,
        "warning": _COLOR_WARNING,
        "urgent": _COLOR_DANGER,
        "critical": _COLOR_DANGER,
    }
    status_color = severity_colors.get(status, _COLOR_INFO)

    loan_html = ""
    if loan_number:
        loan_html = (
            f'<p style="margin:0 0 16px;color:{_COLOR_MUTED};font-size:13px;">'
            f'Loan: {_esc(loan_number)}</p>'
        )

    body = (
        f'<p style="margin:0 0 16px;color:#374151;">Hi {_esc(borrower)},</p>'
        f'{loan_html}'
        f'<div style="margin:16px 0;padding:14px;border-left:4px solid {status_color};'
        f'background:#f9fafb;border-radius:0 8px 8px 0;">'
        f'<h3 style="margin:0 0 8px;color:#1f2937;font-size:16px;">'
        f'{_esc(document_title)}</h3>'
        f'<p style="margin:0;color:#4b5563;font-size:14px;line-height:1.6;">'
        f'{_esc(status_message)}</p>'
        f'</div>'
        f'{_cta_button(action_label, action_url, status_color) if action_url else ""}'
    )

    plain = (
        f"Hi {borrower},\n\n"
        f"{'Loan: ' + loan_number + chr(10) + chr(10) if loan_number else ''}"
        f"{document_title}\n\n"
        f"{status_message}\n\n"
        f"{'View details: ' + action_url + chr(10) + chr(10) if action_url else ''}"
    )

    return RenderedTemplate(
        subject=f"[Smart Docs] {_safe(document_title)}",
        html_body=_html_scaffold(
            document_title, "", body,
            header_bg=status_color,
            company_name=company_name, company_logo_url=company_logo_url,
        ),
        plain_text=plain,
        template_name="doc_status_update",
        variables_used=["borrower_name", "document_title", "status",
                        "status_message", "action_url", "action_label",
                        "loan_number"],
    )


# =============================================================================
# TEMPLATE REGISTRY
# =============================================================================

_TEMPLATE_REGISTRY: Dict[str, Any] = {
    # Document requests
    "document_request_initial": _template_document_request_initial,
    "document_request_reminder": _template_document_request_reminder,
    "document_request_urgent": _template_document_request_urgent,
    "document_request_final": _template_document_request_final,
    # Document status
    "document_received": _template_document_received,
    "document_approved": _template_document_approved,
    "document_rejected": _template_document_rejected,
    "document_expiring": _template_document_expiring,
    # E-signature
    "esign_request": _template_esign_request,
    "esign_reminder": _template_esign_reminder,
    "esign_completed": _template_esign_completed,
    "esign_voided": _template_esign_voided,
    # Income / review
    "income_review_complete": _template_income_review_complete,
    "income_task_assigned": _template_income_task_assigned,
    "review_findings": _template_review_findings,
    # Appointments
    "appointment_scheduled": _template_appointment_scheduled,
    "appointment_reminder": _template_appointment_reminder,
    "appointment_cancelled": _template_appointment_cancelled,
    # Generic status update (used by NotificationCenterService for email delivery)
    "doc_status_update": _template_doc_status_update,
}


def get_available_templates() -> List[str]:
    """Return a sorted list of all registered template names."""
    return sorted(_TEMPLATE_REGISTRY.keys())


# =============================================================================
# PUBLIC API
# =============================================================================

def render_template(template_name: str, variables: Dict[str, Any]) -> RenderedTemplate:
    """
    Render a notification template by name.

    Args:
        template_name: One of the registered template names (e.g. 'document_request_initial').
        variables: Dict of template variables. Common keys include:
            - borrower_name: Recipient name
            - loan_officer_name: LO name for signature
            - document_list: List of dicts with 'name', 'status', 'note' keys
            - due_date: Formatted due date string
            - portal_url: URL to borrower portal / upload page
            - signing_url: URL for e-signature
            - company_name: Override company name in branding
            - company_logo_url: URL to company logo image

    Returns:
        RenderedTemplate with subject, html_body, plain_text, and metadata.

    Raises:
        ValueError: If template_name is not found in the registry.
    """
    renderer = _TEMPLATE_REGISTRY.get(template_name)
    if renderer is None:
        available = ", ".join(sorted(_TEMPLATE_REGISTRY.keys()))
        raise ValueError(
            f"Unknown template '{template_name}'. Available templates: {available}"
        )
    return renderer(variables)


def send_notification(
    template_name: str,
    recipient_email: str,
    variables: Dict[str, Any],
    db: Session,
    reply_to: Optional[str] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    Render a template and send it as an email via the EmailService.

    Args:
        template_name: Registered template name.
        recipient_email: Destination email address.
        variables: Template variables dict.
        db: SQLAlchemy session (for logging / audit trail).
        reply_to: Optional reply-to email address.
        from_email: Optional override for sender address.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    try:
        rendered = render_template(template_name, variables)
    except ValueError as e:
        logger.error(f"Template rendering failed: {e}")
        return False

    try:
        from email_service import EmailService

        email_service = EmailService()
        success = email_service.send_html_email(
            to_email=recipient_email,
            subject=rendered.subject,
            html_body=rendered.html_body,
            plain_text_body=rendered.plain_text,
            reply_to=reply_to,
            from_email=from_email,
        )

        if success:
            logger.info(
                f"Notification sent: template={template_name} to={recipient_email}"
            )
            # Log to DB if we have a notification_logs table
            _log_notification(
                db=db,
                template_name=template_name,
                recipient_email=recipient_email,
                subject=rendered.subject,
                success=True,
            )
        else:
            logger.warning(
                f"Notification send returned failure: template={template_name} to={recipient_email}"
            )
            _log_notification(
                db=db,
                template_name=template_name,
                recipient_email=recipient_email,
                subject=rendered.subject,
                success=False,
                error="EmailService returned False",
            )

        return success

    except Exception as e:
        logger.exception(f"Failed to send notification: template={template_name} to={recipient_email}")
        _log_notification(
            db=db,
            template_name=template_name,
            recipient_email=recipient_email,
            subject=rendered.subject if rendered else template_name,
            success=False,
            error=str(e),
        )
        return False


def _log_notification(
    db: Session,
    template_name: str,
    recipient_email: str,
    subject: str,
    success: bool,
    error: Optional[str] = None,
) -> None:
    """
    Best-effort audit log of notification sends. Uses raw SQL to avoid
    model import issues if the notification_logs table does not exist.
    """
    try:
        from sqlalchemy import text as sa_text

        db.execute(
            sa_text("""
                INSERT INTO notification_logs (template_name, recipient_email, subject, success, error, sent_at)
                VALUES (:template, :email, :subject, :success, :error, :sent_at)
            """),
            {
                "template": template_name,
                "email": recipient_email,
                "subject": subject,
                "success": success,
                "error": error,
                "sent_at": datetime.now(timezone.utc),
            },
        )
        db.commit()
    except Exception:
        # Table may not exist; silently skip audit logging
        db.rollback()
