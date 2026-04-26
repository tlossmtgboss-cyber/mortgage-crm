"""
Smart Docs V2 - Document Template Engine Service

Generates mortgage documents from Jinja2 templates with sandboxed execution,
variable substitution from loan/borrower data, PDF generation, versioning,
and multi-org template management.

Capabilities:
    - Sandboxed Jinja2 rendering (no filesystem/OS access)
    - Built-in templates for common mortgage documents
    - Variable substitution from Loan, Lead, User, Organization models
    - PDF generation via ReportLab (optional dependency)
    - Template versioning (new version on edit, old versions preserved)
    - Template validation (check all variables are resolvable)
    - Merge fields catalog (list available variables per template type)
    - Batch document generation
    - Template import/export for multi-org deployment

Usage:
    engine = TemplateEngineService(db)

    # Render a template
    result = await engine.render_template(
        template_id=42,
        org_id=1,
        loan_id=100,
        extra_variables={"custom_note": "Rush processing requested"},
    )

    # Generate PDF
    pdf_bytes = await engine.render_to_pdf(
        template_id=42,
        org_id=1,
        loan_id=100,
    )
"""

from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: Jinja2 SandboxedEnvironment
# ---------------------------------------------------------------------------

try:
    from jinja2.sandbox import SandboxedEnvironment, ImmutableSandboxedEnvironment
    from jinja2 import TemplateSyntaxError, UndefinedError, BaseLoader, TemplateNotFound
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False
    logger.warning("jinja2 not installed -- template rendering will not work")

# ---------------------------------------------------------------------------
# Optional dependency: ReportLab for PDF generation
# ---------------------------------------------------------------------------

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, ListFlowable, ListItem,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ===========================================================================
# Constants
# ===========================================================================

TEMPLATE_TYPES = frozenset({
    "NEEDS_LIST",
    "LOE",
    "COVER_LETTER",
    "CHECKLIST",
    "STACKING_ORDER",
    "CONDITION_CLEARANCE",
})

TEMPLATE_CATEGORIES = frozenset({
    "INCOME",
    "ASSETS",
    "COMPLIANCE",
    "GENERAL",
})

# Maximum template size to prevent abuse (512 KB)
MAX_TEMPLATE_SIZE_BYTES = 512 * 1024

# Maximum render time before aborting (seconds)
MAX_RENDER_SECONDS = 10

# Jinja2 sandboxing limits
_JINJA2_MAX_RANGE = 1000


# ===========================================================================
# Merge field definitions -- available variables per template type
# ===========================================================================

_LOAN_FIELDS: Dict[str, str] = {
    "loan.loan_number": "Loan number (e.g., 2024-001234)",
    "loan.borrower_name": "Primary borrower full name",
    "loan.borrower_email": "Primary borrower email",
    "loan.borrower_phone": "Primary borrower phone",
    "loan.coborrower_name": "Co-borrower full name",
    "loan.co_borrower_email": "Co-borrower email",
    "loan.amount": "Loan amount (numeric)",
    "loan.amount_formatted": "Loan amount formatted as currency",
    "loan.purchase_price": "Purchase price (numeric)",
    "loan.purchase_price_formatted": "Purchase price formatted as currency",
    "loan.down_payment": "Down payment amount",
    "loan.down_payment_formatted": "Down payment formatted as currency",
    "loan.rate": "Interest rate (numeric, e.g., 6.875)",
    "loan.rate_formatted": "Interest rate formatted (e.g., 6.875%)",
    "loan.term": "Loan term in months (e.g., 360)",
    "loan.term_years": "Loan term in years (e.g., 30)",
    "loan.loan_type": "Loan type (conventional, FHA, VA, etc.)",
    "loan.program": "Loan program name",
    "loan.stage": "Current pipeline stage",
    "loan.property_address": "Property street address",
    "loan.property_city": "Property city",
    "loan.property_state": "Property state",
    "loan.property_zip": "Property ZIP code",
    "loan.property_full_address": "Full property address (address, city, state ZIP)",
    "loan.property_type": "Property type (single_family, condo, etc.)",
    "loan.occupancy_type": "Occupancy type (primary, second_home, investment)",
    "loan.closing_date": "Scheduled closing date",
    "loan.closing_date_formatted": "Closing date formatted as MM/DD/YYYY",
    "loan.lock_date": "Rate lock date",
    "loan.lock_expiration_date": "Rate lock expiration date",
    "loan.ltv": "Loan-to-value ratio",
    "loan.cltv": "Combined loan-to-value ratio",
    "loan.appraisal_value": "Appraised value",
    "loan.appraisal_value_formatted": "Appraised value formatted as currency",
    "loan.monthly_payment": "Monthly P&I payment",
    "loan.monthly_payment_formatted": "Monthly payment formatted as currency",
    "loan.property_tax": "Monthly property tax",
    "loan.hazard_insurance": "Monthly hazard insurance",
    "loan.mortgage_insurance": "Monthly mortgage insurance",
    "loan.hoa_amount": "Monthly HOA dues",
    "loan.loan_purpose": "Loan purpose (purchase, refinance, cash-out)",
    "loan.lender": "Lender/investor name",
    "loan.title_company": "Title company name",
}

_TEAM_FIELDS: Dict[str, str] = {
    "lo.full_name": "Loan officer full name",
    "lo.first_name": "Loan officer first name",
    "lo.last_name": "Loan officer last name",
    "lo.email": "Loan officer email",
    "lo.phone": "Loan officer phone",
    "lo.nmls_number": "Loan officer NMLS number",
    "lo.title": "Loan officer title",
    "loan.processor": "Processor name",
    "loan.processor_email": "Processor email",
    "loan.underwriter": "Underwriter name",
    "loan.closer": "Closer name",
    "loan.closer_email": "Closer email",
    "loan.realtor_agent": "Realtor/agent name",
}

_ORG_FIELDS: Dict[str, str] = {
    "org.name": "Organization/company name",
    "org.id": "Organization ID",
}

_META_FIELDS: Dict[str, str] = {
    "today": "Current date (YYYY-MM-DD)",
    "today_formatted": "Current date formatted as MM/DD/YYYY",
    "generated_at": "Generation timestamp",
}

MERGE_FIELDS_BY_TYPE: Dict[str, Dict[str, str]] = {
    "NEEDS_LIST": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
                   "missing_docs": "List of missing document dicts (type, category, required)",
                   "received_docs": "List of received document dicts (type, category, status)"},
    "LOE": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
            "explanation_subject": "Subject of explanation (e.g., 'Large Deposit')",
            "explanation_body": "Body text of the explanation",
            "explanation_date": "Date of the event being explained"},
    "COVER_LETTER": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
                     "submission_type": "Submission type (initial, resubmission, conditions)",
                     "included_documents": "List of documents included in submission package",
                     "notes": "Additional notes for underwriter"},
    "CHECKLIST": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
                  "checklist_items": "List of checklist item dicts (item, checked, category)"},
    "STACKING_ORDER": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
                       "investor": "Investor/lender name for stacking order",
                       "stacking_sections": "List of stacking section dicts (section, documents)"},
    "CONDITION_CLEARANCE": {**_LOAN_FIELDS, **_TEAM_FIELDS, **_ORG_FIELDS, **_META_FIELDS,
                            "conditions": "List of condition dicts (id, description, status, response)",
                            "cleared_by": "Name of person clearing conditions",
                            "clearance_date": "Date conditions were cleared"},
}


# ===========================================================================
# Built-in system templates
# ===========================================================================

BUILT_IN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "template_name": "Standard Needs List",
        "template_type": "NEEDS_LIST",
        "category": "GENERAL",
        "content_template": """\
<h2>Document Needs List</h2>
<p><strong>Borrower:</strong> {{ loan.borrower_name }}</p>
<p><strong>Loan #:</strong> {{ loan.loan_number }}</p>
<p><strong>Property:</strong> {{ loan.property_full_address }}</p>
<p><strong>Loan Type:</strong> {{ loan.loan_type | upper }} | <strong>Amount:</strong> {{ loan.amount_formatted }}</p>
<p><strong>Loan Officer:</strong> {{ lo.full_name }} | NMLS# {{ lo.nmls_number }}</p>
<p><strong>Date:</strong> {{ today_formatted }}</p>
<hr>

<h3>Outstanding Documents Required</h3>
{% if missing_docs %}
<table border="1" cellpadding="6" cellspacing="0" width="100%">
    <thead>
        <tr style="background-color: #f0f0f0;">
            <th>#</th>
            <th>Document</th>
            <th>Category</th>
            <th>Required</th>
        </tr>
    </thead>
    <tbody>
    {% for doc in missing_docs %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ doc.type | replace('_', ' ') | title }}</td>
            <td>{{ doc.category | title }}</td>
            <td>{{ 'Yes' if doc.required else 'If Applicable' }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% else %}
<p><em>All required documents have been received.</em></p>
{% endif %}

{% if received_docs %}
<h3>Documents Received</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
    <thead>
        <tr style="background-color: #e8f5e9;">
            <th>#</th>
            <th>Document</th>
            <th>Category</th>
            <th>Status</th>
        </tr>
    </thead>
    <tbody>
    {% for doc in received_docs %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ doc.type | replace('_', ' ') | title }}</td>
            <td>{{ doc.category | title }}</td>
            <td>{{ doc.status | title }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% endif %}

<br>
<p><em>Please upload documents to your secure portal or email to {{ lo.email }}.</em></p>
<p><em>Generated {{ generated_at }}</em></p>
""",
        "metadata_schema": {
            "required": ["loan", "lo"],
            "optional": ["missing_docs", "received_docs"],
        },
    },

    {
        "template_name": "Letter of Explanation - General",
        "template_type": "LOE",
        "category": "GENERAL",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<p style="text-align: right;">{{ today_formatted }}</p>

<p>
To Whom It May Concern,
</p>

<p>
<strong>Re: {{ explanation_subject | default('Letter of Explanation') }}</strong><br>
Loan Number: {{ loan.loan_number }}<br>
Borrower: {{ loan.borrower_name }}{% if loan.coborrower_name %} &amp; {{ loan.coborrower_name }}{% endif %}<br>
Property: {{ loan.property_full_address }}
</p>

<p>
{{ explanation_body | default('I am writing to provide an explanation regarding the matter referenced above.') }}
</p>

{% if explanation_date %}
<p>
The event in question occurred on or about {{ explanation_date }}.
</p>
{% endif %}

<p>
I certify that the information provided above is true and accurate to the best of my knowledge.
</p>

<br><br>
<p>
____________________________________<br>
{{ loan.borrower_name }}<br>
Date: _______________
</p>

{% if loan.coborrower_name %}
<br>
<p>
____________________________________<br>
{{ loan.coborrower_name }}<br>
Date: _______________
</p>
{% endif %}
</div>
""",
        "metadata_schema": {
            "required": ["loan", "explanation_subject"],
            "optional": ["explanation_body", "explanation_date"],
        },
    },

    {
        "template_name": "LOE - Large Deposit",
        "template_type": "LOE",
        "category": "ASSETS",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<p style="text-align: right;">{{ today_formatted }}</p>

<p>To Whom It May Concern,</p>

<p>
<strong>Re: Explanation of Large Deposit</strong><br>
Loan Number: {{ loan.loan_number }}<br>
Borrower: {{ loan.borrower_name }}<br>
Property: {{ loan.property_full_address }}
</p>

<p>
I am writing to explain the large deposit of {{ deposit_amount | default('$_______') }}
that appeared in my {{ account_type | default('bank account') }}
on or about {{ explanation_date | default('___/___/______') }}.
</p>

<p>
{{ explanation_body | default('The source of this deposit was: _________________________________') }}
</p>

<p>
This deposit {% if is_gift | default(false) %}is a gift and does not require repayment{% else %}is not a loan and does not require repayment{% endif %}.
</p>

<p>
I certify that the information provided above is true and accurate to the best of my knowledge.
</p>

<br><br>
<p>
____________________________________<br>
{{ loan.borrower_name }}<br>
Date: _______________
</p>
</div>
""",
        "metadata_schema": {
            "required": ["loan"],
            "optional": ["deposit_amount", "account_type", "explanation_date",
                         "explanation_body", "is_gift"],
        },
    },

    {
        "template_name": "LOE - Employment Gap",
        "template_type": "LOE",
        "category": "INCOME",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<p style="text-align: right;">{{ today_formatted }}</p>

<p>To Whom It May Concern,</p>

<p>
<strong>Re: Explanation of Employment Gap</strong><br>
Loan Number: {{ loan.loan_number }}<br>
Borrower: {{ loan.borrower_name }}<br>
Property: {{ loan.property_full_address }}
</p>

<p>
I am writing to explain the gap in my employment history
from {{ gap_start_date | default('___/___/______') }}
to {{ gap_end_date | default('___/___/______') }}.
</p>

<p>
{{ explanation_body | default('During this period, I was: _________________________________') }}
</p>

<p>
I am currently employed at {{ current_employer | default('___________________') }}
as a {{ current_position | default('___________________') }}
since {{ employment_start_date | default('___/___/______') }}.
</p>

<p>
I certify that the information provided above is true and accurate to the best of my knowledge.
</p>

<br><br>
<p>
____________________________________<br>
{{ loan.borrower_name }}<br>
Date: _______________
</p>
</div>
""",
        "metadata_schema": {
            "required": ["loan"],
            "optional": ["gap_start_date", "gap_end_date", "explanation_body",
                         "current_employer", "current_position", "employment_start_date"],
        },
    },

    {
        "template_name": "Underwriting Cover Letter",
        "template_type": "COVER_LETTER",
        "category": "GENERAL",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<h2>Submission Cover Letter</h2>
<hr>

<table cellpadding="4" cellspacing="0" width="100%">
    <tr><td width="30%"><strong>Date:</strong></td><td>{{ today_formatted }}</td></tr>
    <tr><td><strong>Loan Number:</strong></td><td>{{ loan.loan_number }}</td></tr>
    <tr><td><strong>Borrower(s):</strong></td><td>{{ loan.borrower_name }}{% if loan.coborrower_name %} &amp; {{ loan.coborrower_name }}{% endif %}</td></tr>
    <tr><td><strong>Property:</strong></td><td>{{ loan.property_full_address }}</td></tr>
    <tr><td><strong>Loan Amount:</strong></td><td>{{ loan.amount_formatted }}</td></tr>
    <tr><td><strong>Loan Type:</strong></td><td>{{ loan.loan_type | upper | default('N/A') }}</td></tr>
    <tr><td><strong>Rate / Term:</strong></td><td>{{ loan.rate_formatted | default('N/A') }} / {{ loan.term_years | default('30') }} years</td></tr>
    <tr><td><strong>LTV:</strong></td><td>{{ loan.ltv | default('N/A') }}%</td></tr>
    <tr><td><strong>Purpose:</strong></td><td>{{ loan.loan_purpose | default('Purchase') | title }}</td></tr>
    <tr><td><strong>Submission Type:</strong></td><td>{{ submission_type | default('Initial Submission') | title }}</td></tr>
</table>

<h3>Loan Officer</h3>
<p>{{ lo.full_name }} | NMLS# {{ lo.nmls_number }}<br>
{{ lo.email }} | {{ lo.phone | default('') }}</p>

{% if notes %}
<h3>Notes for Underwriter</h3>
<p>{{ notes }}</p>
{% endif %}

{% if included_documents %}
<h3>Documents Included</h3>
<ol>
{% for doc in included_documents %}
    <li>{{ doc }}</li>
{% endfor %}
</ol>
{% endif %}

<hr>
<p><em>{{ org.name }} | Generated {{ generated_at }}</em></p>
</div>
""",
        "metadata_schema": {
            "required": ["loan", "lo", "org"],
            "optional": ["submission_type", "notes", "included_documents"],
        },
    },

    {
        "template_name": "Standard Stacking Order",
        "template_type": "STACKING_ORDER",
        "category": "GENERAL",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<h2>Stacking Order</h2>
<p><strong>Loan #:</strong> {{ loan.loan_number }} |
   <strong>Borrower:</strong> {{ loan.borrower_name }} |
   <strong>Investor:</strong> {{ investor | default(loan.lender) | default('N/A') }}</p>
<hr>

{% if stacking_sections %}
{% for section in stacking_sections %}
<h3>{{ loop.index }}. {{ section.section }}</h3>
<table border="1" cellpadding="4" cellspacing="0" width="100%">
    <thead>
        <tr style="background-color: #f0f0f0;">
            <th width="5%">#</th>
            <th width="55%">Document</th>
            <th width="20%">Status</th>
            <th width="20%">Pages</th>
        </tr>
    </thead>
    <tbody>
    {% for doc in section.documents %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ doc.name }}</td>
            <td>{{ doc.status | default('Pending') }}</td>
            <td>{{ doc.pages | default('') }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
<br>
{% endfor %}
{% else %}
<ol>
<li>1003/1008 (Uniform Residential Loan Application)</li>
<li>Credit Report</li>
<li>Income Documentation (W-2s, Pay Stubs, Tax Returns)</li>
<li>Asset Documentation (Bank Statements)</li>
<li>Purchase Contract</li>
<li>Appraisal Report</li>
<li>Title Commitment</li>
<li>Homeowners Insurance</li>
<li>Flood Certification</li>
<li>Disclosures (LE, CD)</li>
</ol>
{% endif %}

<hr>
<p><em>Generated {{ generated_at }} | {{ org.name }}</em></p>
</div>
""",
        "metadata_schema": {
            "required": ["loan", "org"],
            "optional": ["investor", "stacking_sections"],
        },
    },

    {
        "template_name": "Condition Clearance Letter",
        "template_type": "CONDITION_CLEARANCE",
        "category": "COMPLIANCE",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<h2>Condition Clearance Submission</h2>
<hr>

<table cellpadding="4" cellspacing="0" width="100%">
    <tr><td width="30%"><strong>Date:</strong></td><td>{{ today_formatted }}</td></tr>
    <tr><td><strong>Loan Number:</strong></td><td>{{ loan.loan_number }}</td></tr>
    <tr><td><strong>Borrower:</strong></td><td>{{ loan.borrower_name }}</td></tr>
    <tr><td><strong>Property:</strong></td><td>{{ loan.property_full_address }}</td></tr>
    <tr><td><strong>Cleared By:</strong></td><td>{{ cleared_by | default(lo.full_name) }}</td></tr>
    <tr><td><strong>Clearance Date:</strong></td><td>{{ clearance_date | default(today_formatted) }}</td></tr>
</table>

{% if conditions %}
<h3>Conditions Addressed</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
    <thead>
        <tr style="background-color: #f0f0f0;">
            <th>#</th>
            <th>Condition</th>
            <th>Response / Documentation</th>
        </tr>
    </thead>
    <tbody>
    {% for cond in conditions %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ cond.description }}</td>
            <td>{{ cond.response | default('See attached documentation') }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% else %}
<p><em>No conditions specified.</em></p>
{% endif %}

{% if notes %}
<h3>Additional Notes</h3>
<p>{{ notes }}</p>
{% endif %}

<hr>
<p>{{ lo.full_name }} | NMLS# {{ lo.nmls_number }}<br>
{{ lo.email }}<br>
{{ org.name }}</p>
<p><em>Generated {{ generated_at }}</em></p>
</div>
""",
        "metadata_schema": {
            "required": ["loan", "lo", "org"],
            "optional": ["conditions", "cleared_by", "clearance_date", "notes"],
        },
    },

    {
        "template_name": "Processing Checklist",
        "template_type": "CHECKLIST",
        "category": "GENERAL",
        "content_template": """\
<div style="font-family: Arial, sans-serif; max-width: 700px;">
<h2>Loan Processing Checklist</h2>
<p><strong>Loan #:</strong> {{ loan.loan_number }} |
   <strong>Borrower:</strong> {{ loan.borrower_name }} |
   <strong>Processor:</strong> {{ loan.processor | default('Unassigned') }}</p>
<hr>

{% if checklist_items %}
{% set ns = namespace(current_category='') %}
{% for item in checklist_items %}
{% if item.category != ns.current_category %}
{% set ns.current_category = item.category %}
<h3>{{ item.category | title }}</h3>
{% endif %}
<p>
{% if item.checked %}&#9745;{% else %}&#9744;{% endif %}
 {{ item.item }}
</p>
{% endfor %}
{% else %}
<h3>Application</h3>
<p>&#9744; 1003 completed and signed</p>
<p>&#9744; Credit report pulled</p>
<p>&#9744; Initial disclosures sent</p>
<p>&#9744; Disclosures signed by borrower</p>

<h3>Income</h3>
<p>&#9744; Pay stubs (most recent 30 days)</p>
<p>&#9744; W-2s (2 years)</p>
<p>&#9744; Tax returns (2 years, if applicable)</p>

<h3>Assets</h3>
<p>&#9744; Bank statements (2 months)</p>
<p>&#9744; Gift letter (if applicable)</p>

<h3>Property</h3>
<p>&#9744; Purchase contract</p>
<p>&#9744; Appraisal ordered</p>
<p>&#9744; Appraisal received</p>
<p>&#9744; Title ordered</p>
<p>&#9744; Title received</p>
<p>&#9744; Homeowners insurance</p>

<h3>Compliance</h3>
<p>&#9744; TRID LE timing verified</p>
<p>&#9744; CD sent (3-day rule)</p>
<p>&#9744; Tolerance check passed</p>
{% endif %}

<hr>
<p><em>Generated {{ generated_at }} | {{ org.name }}</em></p>
</div>
""",
        "metadata_schema": {
            "required": ["loan", "org"],
            "optional": ["checklist_items"],
        },
    },
]


# ===========================================================================
# Jinja2 custom filters for mortgage-specific formatting
# ===========================================================================

def _filter_currency(value: Any) -> str:
    """Format a numeric value as US currency."""
    if value is None:
        return "$0.00"
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _filter_percentage(value: Any, decimals: int = 3) -> str:
    """Format a numeric value as a percentage."""
    if value is None:
        return "0%"
    try:
        return f"{float(value):.{decimals}f}%"
    except (ValueError, TypeError):
        return str(value)


def _filter_date_format(value: Any, fmt: str = "%m/%d/%Y") -> str:
    """Format a date/datetime value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    return str(value)


def _filter_phone_format(value: Any) -> str:
    """Format a phone number as (XXX) XXX-XXXX."""
    if not value:
        return ""
    digits = "".join(c for c in str(value) if c.isdigit())
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return str(value)


def _filter_yesno(value: Any) -> str:
    """Convert boolean to Yes/No."""
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


# ===========================================================================
# Template rendering context builder
# ===========================================================================

def _safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _build_loan_context(loan) -> Dict[str, Any]:
    """Build template context dict from a Loan ORM object."""
    amount = _safe_float(loan.amount)
    purchase_price = _safe_float(loan.purchase_price)
    down_payment = _safe_float(loan.down_payment)
    rate = _safe_float(loan.rate)
    appraisal_value = _safe_float(loan.appraisal_value)
    monthly_payment = _safe_float(loan.monthly_payment)
    term = loan.term or 360

    # Build full address
    addr_parts = [
        loan.property_address or "",
        loan.property_city or "",
    ]
    state_zip = " ".join(filter(None, [loan.property_state, loan.property_zip]))
    if state_zip:
        addr_parts.append(state_zip)
    full_address = ", ".join(p for p in addr_parts if p)

    return {
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "borrower_email": loan.borrower_email or "",
        "borrower_phone": loan.borrower_phone or "",
        "coborrower_name": loan.coborrower_name or "",
        "co_borrower_email": loan.co_borrower_email or "",
        "amount": amount,
        "amount_formatted": _filter_currency(amount),
        "purchase_price": purchase_price,
        "purchase_price_formatted": _filter_currency(purchase_price),
        "down_payment": down_payment,
        "down_payment_formatted": _filter_currency(down_payment),
        "rate": rate,
        "rate_formatted": _filter_percentage(rate) if rate else "N/A",
        "term": term,
        "term_years": term // 12 if term else 30,
        "loan_type": loan.loan_type or "",
        "program": loan.program or "",
        "stage": loan.stage or "",
        "property_address": loan.property_address or "",
        "property_city": loan.property_city or "",
        "property_state": loan.property_state or "",
        "property_zip": loan.property_zip or "",
        "property_full_address": full_address or "TBD",
        "property_type": loan.property_type or "",
        "occupancy_type": loan.occupancy_type or "",
        "closing_date": loan.closing_date,
        "closing_date_formatted": _filter_date_format(loan.closing_date),
        "lock_date": loan.lock_date,
        "lock_expiration_date": loan.lock_expiration_date,
        "ltv": _safe_float(loan.ltv),
        "cltv": _safe_float(loan.cltv),
        "appraisal_value": appraisal_value,
        "appraisal_value_formatted": _filter_currency(appraisal_value),
        "monthly_payment": monthly_payment,
        "monthly_payment_formatted": _filter_currency(monthly_payment),
        "property_tax": _safe_float(loan.property_tax),
        "hazard_insurance": _safe_float(loan.hazard_insurance),
        "mortgage_insurance": _safe_float(loan.mortgage_insurance),
        "hoa_amount": _safe_float(loan.hoa_amount),
        "loan_purpose": loan.loan_purpose or "",
        "lender": loan.lender or "",
        "title_company": loan.title_company or "",
        "processor": loan.processor or "",
        "processor_email": loan.processor_email or "",
        "underwriter": loan.underwriter or "",
        "closer": loan.closer or "",
        "closer_email": loan.closer_email or "",
        "realtor_agent": loan.realtor_agent or "",
    }


def _build_user_context(user) -> Dict[str, Any]:
    """Build template context dict from a User (loan officer) ORM object."""
    return {
        "full_name": user.full_name if hasattr(user, "full_name") else f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.email or "",
        "phone": getattr(user, "phone", "") or "",
        "nmls_number": getattr(user, "nmls_number", "") or "",
        "title": getattr(user, "title", "") or "",
    }


def _build_org_context(org) -> Dict[str, Any]:
    """Build template context dict from an Organization ORM object."""
    return {
        "name": org.name or "",
        "id": org.id,
    }


# ===========================================================================
# Template Engine Service
# ===========================================================================

class TemplateEngineService:
    """
    Async-compatible service for rendering mortgage documents from Jinja2 templates.

    All queries are scoped to organization_id for tenant isolation.
    System templates (is_system=True) are visible to all orgs.
    """

    def __init__(self, db: Session):
        self.db = db
        self._env: Optional[SandboxedEnvironment] = None

    # ------------------------------------------------------------------
    # Jinja2 environment (lazy, singleton per service instance)
    # ------------------------------------------------------------------

    def _get_env(self) -> "SandboxedEnvironment":
        """Get or create a sandboxed Jinja2 environment."""
        if not HAS_JINJA2:
            raise RuntimeError("jinja2 package is required for template rendering. Install with: pip install jinja2")

        if self._env is None:
            self._env = SandboxedEnvironment(
                autoescape=True,
                trim_blocks=True,
                lstrip_blocks=True,
                # No filesystem loader -- templates are loaded from DB
                loader=None,
                # Security: limit extensions
                extensions=[],
            )

            # Register custom filters
            self._env.filters["currency"] = _filter_currency
            self._env.filters["percentage"] = _filter_percentage
            self._env.filters["date_format"] = _filter_date_format
            self._env.filters["phone_format"] = _filter_phone_format
            self._env.filters["yesno"] = _filter_yesno

            # Override range to prevent abuse
            self._env.globals["range"] = lambda *args: range(*args) if all(
                isinstance(a, int) and abs(a) <= _JINJA2_MAX_RANGE for a in args
            ) else []

        return self._env

    # ------------------------------------------------------------------
    # Template CRUD
    # ------------------------------------------------------------------

    async def get_template(
        self, template_id: int, org_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a single template by ID, scoped to org or system templates."""
        from database.models.document_template import DocumentTemplate

        template = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.is_active == True,  # noqa: E712
            (DocumentTemplate.organization_id == org_id) | (DocumentTemplate.is_system == True),  # noqa: E712
        ).first()

        if not template:
            return None

        return self._template_to_dict(template)

    async def list_templates(
        self,
        org_id: int,
        template_type: Optional[str] = None,
        category: Optional[str] = None,
        include_system: bool = True,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List templates visible to an organization."""
        from database.models.document_template import DocumentTemplate

        query = self.db.query(DocumentTemplate)

        # Org isolation: own templates + system templates
        if include_system:
            query = query.filter(
                (DocumentTemplate.organization_id == org_id) | (DocumentTemplate.is_system == True)  # noqa: E712
            )
        else:
            query = query.filter(DocumentTemplate.organization_id == org_id)

        if active_only:
            query = query.filter(DocumentTemplate.is_active == True)  # noqa: E712

        if template_type:
            query = query.filter(DocumentTemplate.template_type == template_type.upper())

        if category:
            query = query.filter(DocumentTemplate.category == category.upper())

        # Latest version of each template name (within same org)
        templates = query.order_by(
            DocumentTemplate.template_name,
            desc(DocumentTemplate.version),
        ).all()

        # Deduplicate: keep highest version per (org_id, template_name)
        seen: set = set()
        result = []
        for t in templates:
            key = (t.organization_id, t.template_name)
            if key not in seen:
                seen.add(key)
                result.append(self._template_to_dict(t))

        return result

    async def create_template(
        self,
        org_id: int,
        template_name: str,
        template_type: str,
        content_template: str,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        metadata_schema: Optional[Dict] = None,
        is_system: bool = False,
    ) -> Dict[str, Any]:
        """Create a new template."""
        from database.models.document_template import DocumentTemplate

        # Validate
        template_type = template_type.upper()
        if template_type not in TEMPLATE_TYPES:
            raise ValueError(f"Invalid template_type '{template_type}'. Must be one of: {', '.join(sorted(TEMPLATE_TYPES))}")

        if category:
            category = category.upper()
            if category not in TEMPLATE_CATEGORIES:
                raise ValueError(f"Invalid category '{category}'. Must be one of: {', '.join(sorted(TEMPLATE_CATEGORIES))}")

        if len(content_template.encode("utf-8")) > MAX_TEMPLATE_SIZE_BYTES:
            raise ValueError(f"Template content exceeds maximum size of {MAX_TEMPLATE_SIZE_BYTES // 1024} KB")

        # Validate Jinja2 syntax
        self._validate_syntax(content_template)

        template = DocumentTemplate(
            organization_id=org_id,
            template_name=template_name,
            template_type=template_type,
            category=category,
            content_template=content_template,
            metadata_schema=metadata_schema,
            is_system=is_system,
            is_active=True,
            version=1,
            created_by_user_id=user_id,
        )

        self.db.add(template)
        self.db.flush()

        logger.info(
            f"Created template '{template_name}' (id={template.id}, type={template_type}) "
            f"for org_id={org_id}"
        )

        return self._template_to_dict(template)

    async def update_template(
        self,
        template_id: int,
        org_id: int,
        content_template: Optional[str] = None,
        template_name: Optional[str] = None,
        category: Optional[str] = None,
        metadata_schema: Optional[Dict] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update a template by creating a new version.

        The old version is preserved (is_active=False). The new version gets
        version = old_version + 1. This ensures auditability and rollback.
        """
        from database.models.document_template import DocumentTemplate

        # Load existing template (must belong to org; system templates are not editable)
        existing = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.organization_id == org_id,
            DocumentTemplate.is_system == False,  # noqa: E712
        ).first()

        if not existing:
            raise ValueError(
                f"Template {template_id} not found for org_id={org_id}, or is a system template (not editable)"
            )

        new_content = content_template or existing.content_template
        new_name = template_name or existing.template_name
        new_category = (category.upper() if category else existing.category)
        new_schema = metadata_schema if metadata_schema is not None else existing.metadata_schema

        if new_category and new_category not in TEMPLATE_CATEGORIES:
            raise ValueError(f"Invalid category '{new_category}'")

        if content_template:
            if len(content_template.encode("utf-8")) > MAX_TEMPLATE_SIZE_BYTES:
                raise ValueError(f"Template content exceeds maximum size of {MAX_TEMPLATE_SIZE_BYTES // 1024} KB")
            self._validate_syntax(content_template)

        # Deactivate old version
        existing.is_active = False

        # Create new version
        new_version = existing.version + 1
        new_template = DocumentTemplate(
            organization_id=org_id,
            template_name=new_name,
            template_type=existing.template_type,
            category=new_category,
            content_template=new_content,
            metadata_schema=new_schema,
            is_system=False,
            is_active=True,
            version=new_version,
            created_by_user_id=user_id,
        )

        self.db.add(new_template)
        self.db.flush()

        logger.info(
            f"Updated template '{new_name}' from v{existing.version} to v{new_version} "
            f"(old_id={template_id}, new_id={new_template.id}) for org_id={org_id}"
        )

        return self._template_to_dict(new_template)

    async def deactivate_template(
        self, template_id: int, org_id: int
    ) -> bool:
        """Soft-delete a template by marking it inactive."""
        from database.models.document_template import DocumentTemplate

        template = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.organization_id == org_id,
            DocumentTemplate.is_system == False,  # noqa: E712
        ).first()

        if not template:
            return False

        template.is_active = False
        self.db.flush()

        logger.info(f"Deactivated template {template_id} for org_id={org_id}")
        return True

    async def get_template_versions(
        self, org_id: int, template_name: str
    ) -> List[Dict[str, Any]]:
        """Get all versions of a template by name."""
        from database.models.document_template import DocumentTemplate

        templates = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.organization_id == org_id,
            DocumentTemplate.template_name == template_name,
        ).order_by(desc(DocumentTemplate.version)).all()

        return [self._template_to_dict(t) for t in templates]

    # ------------------------------------------------------------------
    # Template rendering
    # ------------------------------------------------------------------

    async def render_template(
        self,
        template_id: int,
        org_id: int,
        loan_id: Optional[int] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Render a template to HTML with variable substitution.

        Variables are resolved from:
            1. Loan record (if loan_id provided)
            2. Loan officer (from loan.loan_officer_id)
            3. Organization
            4. Extra variables (caller-supplied overrides)
            5. Meta fields (today, generated_at)

        Returns:
            Dict with rendered HTML, template info, and metadata.
        """
        from database.models.document_template import DocumentTemplate, DocumentGenerationLog

        start_time = time.monotonic()

        # Load template
        template_row = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.is_active == True,  # noqa: E712
            (DocumentTemplate.organization_id == org_id) | (DocumentTemplate.is_system == True),  # noqa: E712
        ).first()

        if not template_row:
            raise ValueError(f"Template {template_id} not found or inactive for org_id={org_id}")

        # Build context
        context = self._build_context(org_id, loan_id, extra_variables)

        # Render
        try:
            env = self._get_env()
            jinja_template = env.from_string(template_row.content_template)
            rendered_html = jinja_template.render(**context)
        except TemplateSyntaxError as e:
            raise ValueError(f"Template syntax error at line {e.lineno}: {e.message}")
        except UndefinedError as e:
            raise ValueError(f"Template variable error: {e.message}")
        except Exception as e:
            logger.exception(f"Template render failed for template_id={template_id}: {e}")
            raise ValueError(f"Template rendering failed: {str(e)}")

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Log generation
        gen_log = DocumentGenerationLog(
            template_id=template_row.id,
            organization_id=org_id,
            loan_id=loan_id,
            template_version=template_row.version,
            variables_used=self._safe_json_snapshot(context),
            output_format="html",
            output_size_bytes=len(rendered_html.encode("utf-8")),
            generation_time_ms=elapsed_ms,
        )
        self.db.add(gen_log)
        self.db.flush()

        return {
            "template_id": template_row.id,
            "template_name": template_row.template_name,
            "template_type": template_row.template_type,
            "version": template_row.version,
            "rendered_html": rendered_html,
            "output_size_bytes": len(rendered_html.encode("utf-8")),
            "generation_time_ms": elapsed_ms,
            "loan_id": loan_id,
            "generation_log_id": gen_log.id,
        }

    async def render_to_pdf(
        self,
        template_id: int,
        org_id: int,
        loan_id: Optional[int] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> bytes:
        """
        Render a template and convert to PDF.

        Uses ReportLab to generate a PDF from the rendered HTML. Falls back to
        a plain-text PDF if ReportLab's HTML parsing cannot handle the template.

        Returns:
            PDF content as bytes.

        Raises:
            RuntimeError: If reportlab is not installed.
        """
        if not HAS_REPORTLAB:
            raise RuntimeError(
                "reportlab is required for PDF generation. Install with: pip install reportlab"
            )

        from database.models.document_template import DocumentGenerationLog

        start_time = time.monotonic()

        # First render to HTML
        render_result = await self.render_template(
            template_id=template_id,
            org_id=org_id,
            loan_id=loan_id,
            extra_variables=extra_variables,
        )

        rendered_html = render_result["rendered_html"]

        # Build context for header/footer
        context = self._build_context(org_id, loan_id, extra_variables)
        loan_ctx = context.get("loan", {})
        org_ctx = context.get("org", {})

        # Generate PDF using ReportLab
        pdf_buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title=render_result["template_name"],
            author=org_ctx.get("name", "The Tim Loss Team"),
        )

        styles = getSampleStyleSheet()

        # Custom styles
        styles.add(ParagraphStyle(
            name="DocTitle",
            parent=styles["Heading1"],
            fontSize=16,
            spaceAfter=12,
            alignment=TA_CENTER,
        ))
        styles.add(ParagraphStyle(
            name="DocBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            name="DocFooter",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.gray,
            alignment=TA_CENTER,
        ))

        # Convert HTML to ReportLab flowables
        story = self._html_to_flowables(rendered_html, styles)

        # Add footer
        story.append(Spacer(1, 0.3 * inch))
        footer_text = (
            f"{org_ctx.get('name', '')} | "
            f"Loan #{loan_ctx.get('loan_number', 'N/A')} | "
            f"Generated {context.get('generated_at', '')}"
        )
        story.append(Paragraph(footer_text, styles["DocFooter"]))

        doc.build(story)
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Log PDF generation
        gen_log = DocumentGenerationLog(
            template_id=template_id,
            organization_id=org_id,
            loan_id=loan_id,
            generated_by_user_id=user_id,
            template_version=render_result["version"],
            variables_used=self._safe_json_snapshot(context),
            output_format="pdf",
            output_size_bytes=len(pdf_bytes),
            generation_time_ms=elapsed_ms,
        )
        self.db.add(gen_log)
        self.db.flush()

        logger.info(
            f"Generated PDF from template {template_id} ({len(pdf_bytes)} bytes, {elapsed_ms}ms) "
            f"for org_id={org_id}, loan_id={loan_id}"
        )

        return pdf_bytes

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    async def batch_generate(
        self,
        template_ids: List[int],
        org_id: int,
        loan_id: int,
        output_format: str = "html",
        extra_variables: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple documents from multiple templates for a single loan.

        Useful for generating all submission package documents at once (cover letter,
        stacking order, needs list, etc.).

        Returns:
            List of render results, one per template_id. Failed renders include
            an 'error' key instead of 'rendered_html'.
        """
        results = []

        for tid in template_ids:
            try:
                if output_format == "pdf":
                    pdf_bytes = await self.render_to_pdf(
                        template_id=tid,
                        org_id=org_id,
                        loan_id=loan_id,
                        extra_variables=extra_variables,
                    )
                    results.append({
                        "template_id": tid,
                        "output_format": "pdf",
                        "output_size_bytes": len(pdf_bytes),
                        "pdf_content": pdf_bytes,
                        "success": True,
                    })
                else:
                    render_result = await self.render_template(
                        template_id=tid,
                        org_id=org_id,
                        loan_id=loan_id,
                        extra_variables=extra_variables,
                    )
                    render_result["success"] = True
                    results.append(render_result)

            except Exception as e:
                logger.exception(f"Batch render failed for template_id={tid}: {e}")
                results.append({
                    "template_id": tid,
                    "success": False,
                    "error": str(e),
                })

        return results

    # ------------------------------------------------------------------
    # Template validation
    # ------------------------------------------------------------------

    def _validate_syntax(self, template_content: str) -> None:
        """Validate Jinja2 template syntax without rendering."""
        env = self._get_env()
        try:
            env.parse(template_content)
        except TemplateSyntaxError as e:
            raise ValueError(f"Invalid template syntax at line {e.lineno}: {e.message}")

    async def validate_template(
        self,
        template_id: int,
        org_id: int,
        loan_id: Optional[int] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validate a template: check syntax and whether all variables are resolvable.

        Returns a validation report with:
            - syntax_valid: whether the template parses
            - variables_found: variables referenced in the template
            - variables_resolved: which variables would resolve given the context
            - variables_missing: which variables have no value
            - renderable: whether the template would render without errors
        """
        from database.models.document_template import DocumentTemplate

        template_row = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.id == template_id,
            (DocumentTemplate.organization_id == org_id) | (DocumentTemplate.is_system == True),  # noqa: E712
        ).first()

        if not template_row:
            raise ValueError(f"Template {template_id} not found for org_id={org_id}")

        report: Dict[str, Any] = {
            "template_id": template_id,
            "template_name": template_row.template_name,
            "syntax_valid": False,
            "variables_found": [],
            "variables_resolved": [],
            "variables_missing": [],
            "renderable": False,
            "render_error": None,
        }

        # Check syntax
        env = self._get_env()
        try:
            parsed = env.parse(template_row.content_template)
            report["syntax_valid"] = True
        except TemplateSyntaxError as e:
            report["render_error"] = f"Syntax error at line {e.lineno}: {e.message}"
            return report

        # Extract referenced variables (top-level names from the AST)
        from jinja2 import meta as jinja2_meta
        referenced = jinja2_meta.find_undeclared_variables(parsed)
        report["variables_found"] = sorted(referenced)

        # Build context and check resolution
        context = self._build_context(org_id, loan_id, extra_variables)
        resolved = []
        missing = []
        for var in referenced:
            if var in context and context[var] is not None:
                resolved.append(var)
            else:
                missing.append(var)

        report["variables_resolved"] = sorted(resolved)
        report["variables_missing"] = sorted(missing)

        # Try a test render
        try:
            jinja_template = env.from_string(template_row.content_template)
            jinja_template.render(**context)
            report["renderable"] = True
        except Exception as e:
            report["render_error"] = str(e)

        return report

    # ------------------------------------------------------------------
    # Merge fields catalog
    # ------------------------------------------------------------------

    def get_merge_fields(
        self, template_type: Optional[str] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Get available merge fields, optionally filtered by template type.

        Returns a dict of {template_type: {field_name: description}}.
        """
        if template_type:
            template_type = template_type.upper()
            if template_type not in MERGE_FIELDS_BY_TYPE:
                raise ValueError(f"Unknown template_type '{template_type}'")
            return {template_type: MERGE_FIELDS_BY_TYPE[template_type]}

        return MERGE_FIELDS_BY_TYPE.copy()

    # ------------------------------------------------------------------
    # Template import / export
    # ------------------------------------------------------------------

    async def export_templates(
        self, org_id: int, template_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Export templates as portable JSON dicts for multi-org deployment.

        Strips org-specific fields (id, organization_id, created_by_user_id).
        """
        from database.models.document_template import DocumentTemplate

        query = self.db.query(DocumentTemplate).filter(
            DocumentTemplate.organization_id == org_id,
            DocumentTemplate.is_active == True,  # noqa: E712
        )

        if template_ids:
            query = query.filter(DocumentTemplate.id.in_(template_ids))

        templates = query.all()

        return [
            {
                "template_name": t.template_name,
                "template_type": t.template_type,
                "category": t.category,
                "content_template": t.content_template,
                "metadata_schema": t.metadata_schema,
                "version": t.version,
                "is_system": t.is_system,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            for t in templates
        ]

    async def import_templates(
        self,
        org_id: int,
        template_data: List[Dict[str, Any]],
        user_id: Optional[int] = None,
        overwrite_existing: bool = False,
    ) -> Dict[str, Any]:
        """
        Import templates from exported JSON dicts into an organization.

        Args:
            org_id: Target organization ID.
            template_data: List of template dicts (from export_templates).
            user_id: User performing the import.
            overwrite_existing: If True, creates a new version of existing templates
                                with the same name. If False, skips duplicates.

        Returns:
            Import summary with counts of created, skipped, and errored templates.
        """
        from database.models.document_template import DocumentTemplate

        created = 0
        skipped = 0
        errors = []

        for item in template_data:
            try:
                name = item.get("template_name")
                if not name:
                    errors.append({"item": item, "error": "Missing template_name"})
                    continue

                ttype = item.get("template_type", "").upper()
                if ttype not in TEMPLATE_TYPES:
                    errors.append({"item": name, "error": f"Invalid template_type: {ttype}"})
                    continue

                content = item.get("content_template", "")
                if not content:
                    errors.append({"item": name, "error": "Missing content_template"})
                    continue

                # Check syntax
                try:
                    self._validate_syntax(content)
                except ValueError as ve:
                    errors.append({"item": name, "error": str(ve)})
                    continue

                # Check for existing template with same name
                existing = self.db.query(DocumentTemplate).filter(
                    DocumentTemplate.organization_id == org_id,
                    DocumentTemplate.template_name == name,
                    DocumentTemplate.is_active == True,  # noqa: E712
                ).first()

                if existing and not overwrite_existing:
                    skipped += 1
                    continue

                if existing and overwrite_existing:
                    # Deactivate old, create new version
                    existing.is_active = False
                    new_version = existing.version + 1
                else:
                    new_version = 1

                category = item.get("category")
                if category:
                    category = category.upper()

                new_template = DocumentTemplate(
                    organization_id=org_id,
                    template_name=name,
                    template_type=ttype,
                    category=category,
                    content_template=content,
                    metadata_schema=item.get("metadata_schema"),
                    is_system=False,  # Imported templates are never system templates
                    is_active=True,
                    version=new_version,
                    created_by_user_id=user_id,
                )
                self.db.add(new_template)
                created += 1

            except Exception as e:
                logger.exception(f"Import error for template: {e}")
                errors.append({"item": item.get("template_name", "unknown"), "error": str(e)})

        if created > 0:
            self.db.flush()

        return {
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "total_processed": len(template_data),
        }

    # ------------------------------------------------------------------
    # System template seeding
    # ------------------------------------------------------------------

    async def seed_system_templates(self, org_id: int) -> int:
        """
        Seed built-in system templates for an organization.

        Idempotent: skips templates that already exist with the same name.
        Returns the number of templates created.
        """
        from database.models.document_template import DocumentTemplate

        created = 0
        for tpl in BUILT_IN_TEMPLATES:
            existing = self.db.query(DocumentTemplate).filter(
                DocumentTemplate.organization_id == org_id,
                DocumentTemplate.template_name == tpl["template_name"],
                DocumentTemplate.is_system == True,  # noqa: E712
            ).first()

            if existing:
                continue

            template = DocumentTemplate(
                organization_id=org_id,
                template_name=tpl["template_name"],
                template_type=tpl["template_type"],
                category=tpl.get("category"),
                content_template=tpl["content_template"],
                metadata_schema=tpl.get("metadata_schema"),
                is_system=True,
                is_active=True,
                version=1,
            )
            self.db.add(template)
            created += 1

        if created > 0:
            self.db.flush()
            logger.info(f"Seeded {created} system templates for org_id={org_id}")

        return created

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(
        self,
        org_id: int,
        loan_id: Optional[int],
        extra_variables: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the full template rendering context from DB records."""
        from database.models.core import Organization, User

        now = datetime.now(timezone.utc)
        context: Dict[str, Any] = {
            "today": now.strftime("%Y-%m-%d"),
            "today_formatted": now.strftime("%m/%d/%Y"),
            "generated_at": now.strftime("%m/%d/%Y %I:%M %p UTC"),
        }

        # Organization context
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        if org:
            context["org"] = _build_org_context(org)
        else:
            context["org"] = {"name": "", "id": org_id}

        # Loan context
        if loan_id:
            from database.models.lead_loan import Loan
            loan = self.db.query(Loan).filter(
                Loan.id == loan_id,
                Loan.organization_id == org_id,
            ).first()

            if loan:
                context["loan"] = _build_loan_context(loan)

                # Loan officer context
                if loan.loan_officer_id:
                    lo = self.db.query(User).filter(User.id == loan.loan_officer_id).first()
                    if lo:
                        context["lo"] = _build_user_context(lo)

                if "lo" not in context:
                    # Fallback LO context from loan string fields
                    context["lo"] = {
                        "full_name": loan.loan_officer_name or "",
                        "first_name": "",
                        "last_name": "",
                        "email": loan.loan_officer_email or "",
                        "phone": "",
                        "nmls_number": "",
                        "title": "",
                    }
            else:
                logger.warning(f"Loan {loan_id} not found for org_id={org_id} during template render")
                context["loan"] = {}
                context["lo"] = {}
        else:
            context["loan"] = {}
            context["lo"] = {}

        # Extra variables (caller-supplied) override defaults
        if extra_variables:
            for key, value in extra_variables.items():
                # Allow overriding nested dicts (e.g., extra loan fields)
                if key in context and isinstance(context[key], dict) and isinstance(value, dict):
                    context[key].update(value)
                else:
                    context[key] = value

        return context

    def _html_to_flowables(self, html: str, styles) -> list:
        """
        Convert HTML to ReportLab flowables for PDF generation.

        Uses a simple parser that handles common HTML elements. For complex
        HTML, the raw content is wrapped in Paragraph objects which support
        a subset of HTML (b, i, u, br, font, etc.).
        """
        import re

        flowables = []

        # Split HTML by major block elements
        # ReportLab's Paragraph supports inline HTML (b, i, u, br, font, sub, sup, a)
        # but not block elements (div, table, h1-h6, p, hr, ol, ul, li)

        # Strip outer divs
        html = re.sub(r'<div[^>]*>', '', html)
        html = html.replace('</div>', '')

        # Process section by section
        parts = re.split(r'(<h[1-6][^>]*>.*?</h[1-6]>|<hr\s*/?>|<table.*?</table>|<p[^>]*>.*?</p>|<ol>.*?</ol>|<ul>.*?</ul>|<br\s*/?>)',
                         html, flags=re.DOTALL | re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Headings
            h_match = re.match(r'<h([1-6])[^>]*>(.*?)</h[1-6]>', part, re.DOTALL | re.IGNORECASE)
            if h_match:
                level = int(h_match.group(1))
                text = self._strip_html(h_match.group(2))
                style_name = f"Heading{min(level, 6)}"
                if style_name in [s.name for s in styles.byName.values()]:
                    flowables.append(Paragraph(text, styles[style_name]))
                else:
                    flowables.append(Paragraph(f"<b>{text}</b>", styles["Normal"]))
                continue

            # Horizontal rules
            if re.match(r'<hr\s*/?>', part, re.IGNORECASE):
                flowables.append(Spacer(1, 6))
                from reportlab.platypus import HRFlowable
                flowables.append(HRFlowable(
                    width="100%", thickness=1, color=colors.grey, spaceAfter=6
                ))
                continue

            # Tables -- convert to ReportLab Table
            table_match = re.match(r'<table.*?>(.*?)</table>', part, re.DOTALL | re.IGNORECASE)
            if table_match:
                table_flowable = self._html_table_to_flowable(table_match.group(1), styles)
                if table_flowable:
                    flowables.append(table_flowable)
                    flowables.append(Spacer(1, 8))
                continue

            # Lists
            list_match = re.match(r'<(ol|ul)>(.*?)</\1>', part, re.DOTALL | re.IGNORECASE)
            if list_match:
                list_type = list_match.group(1).lower()
                items_html = list_match.group(2)
                items = re.findall(r'<li>(.*?)</li>', items_html, re.DOTALL | re.IGNORECASE)
                bullet_type = "1" if list_type == "ol" else "bullet"
                list_items = []
                for item_text in items:
                    clean = self._strip_html(item_text).strip()
                    if clean:
                        list_items.append(ListItem(Paragraph(clean, styles["Normal"])))
                if list_items:
                    flowables.append(ListFlowable(list_items, bulletType=bullet_type))
                    flowables.append(Spacer(1, 6))
                continue

            # Paragraphs and other content
            p_match = re.match(r'<p[^>]*>(.*?)</p>', part, re.DOTALL | re.IGNORECASE)
            if p_match:
                text = p_match.group(1).strip()
                # Keep inline HTML that ReportLab supports
                text = re.sub(r'<br\s*/?>', '<br/>', text)
                if text:
                    flowables.append(Paragraph(text, styles["Normal"]))
                continue

            # Line breaks
            if re.match(r'<br\s*/?>', part, re.IGNORECASE):
                flowables.append(Spacer(1, 6))
                continue

            # Plain text fallback
            text = self._strip_html(part).strip()
            if text:
                flowables.append(Paragraph(text, styles["Normal"]))

        if not flowables:
            flowables.append(Paragraph("(No content)", styles["Normal"]))

        return flowables

    def _html_table_to_flowable(self, table_inner_html: str, styles):
        """Convert HTML table content to a ReportLab Table flowable."""
        import re

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_inner_html, re.DOTALL | re.IGNORECASE)
        if not rows:
            return None

        table_data = []
        for row_html in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
            row_data = []
            for cell in cells:
                text = self._strip_html(cell).strip()
                row_data.append(Paragraph(text, styles["Normal"]))
            if row_data:
                table_data.append(row_data)

        if not table_data:
            return None

        # Normalize column count
        max_cols = max(len(row) for row in table_data)
        for row in table_data:
            while len(row) < max_cols:
                row.append(Paragraph("", styles["Normal"]))

        col_width = (6.5 * inch) / max_cols if max_cols > 0 else 6.5 * inch

        table = Table(table_data, colWidths=[col_width] * max_cols)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))

        return table

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from a string, preserving text content."""
        import re
        # Decode common HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&#9744;", "[ ]").replace("&#9745;", "[X]")
        # Strip tags
        return re.sub(r'<[^>]+>', '', text)

    @staticmethod
    def _template_to_dict(template) -> Dict[str, Any]:
        """Convert a DocumentTemplate ORM object to a dict."""
        return {
            "id": template.id,
            "organization_id": template.organization_id,
            "template_name": template.template_name,
            "template_type": template.template_type,
            "category": template.category,
            "content_template": template.content_template,
            "metadata_schema": template.metadata_schema,
            "is_system": template.is_system,
            "is_active": template.is_active,
            "version": template.version,
            "created_by_user_id": template.created_by_user_id,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        }

    @staticmethod
    def _safe_json_snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a JSON-safe snapshot of the rendering context for audit logging."""
        snapshot = {}
        for key, value in context.items():
            if isinstance(value, dict):
                safe_dict = {}
                for k, v in value.items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        safe_dict[k] = v
                    elif isinstance(v, Decimal):
                        safe_dict[k] = float(v)
                    elif isinstance(v, (datetime, date)):
                        safe_dict[k] = v.isoformat()
                    elif isinstance(v, list):
                        safe_dict[k] = f"[{len(v)} items]"
                    else:
                        safe_dict[k] = str(v)
                snapshot[key] = safe_dict
            elif isinstance(value, (str, int, float, bool, type(None))):
                snapshot[key] = value
            elif isinstance(value, list):
                snapshot[key] = f"[{len(value)} items]"
            else:
                snapshot[key] = str(value)
        return snapshot


# ===========================================================================
# Factory function
# ===========================================================================

def get_template_engine(db: Session) -> TemplateEngineService:
    """Factory function to create a TemplateEngineService instance."""
    return TemplateEngineService(db)
