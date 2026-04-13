"""
aria/documents/document_generator.py
Perennia AI — AI Mortgage Document Generator

Generates mortgage documents using Claude + Jinja2 templates.
All documents are rendered as both PDF (for sending) and markdown preview
(for Aria to show in the confirmation step).

Documents:
  - Pre-approval letters
  - Conditional approval letters
  - Adverse action notices (ECOA/FCRA compliant)
  - Letters of Explanation (LOE)
"""

import io
import uuid
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from jinja2 import Environment, BaseLoader
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib import colors

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

# ─── Letter templates (Jinja2) ────────────────────────────────────────────────
PREAPPROVAL_TEMPLATE = """
{{ lo_name }}
{{ lo_title }}
{{ lo_phone }} | {{ lo_email }}
NMLS# {{ lo_nmls }}
{{ org_name }}
{{ org_address }}

{{ today }}

{% if recipient_name %}{{ recipient_name }}{% endif %}
{% if recipient_email %}{{ recipient_email }}{% endif %}

Re: Pre-Approval — {{ borrower_name }}{% if property_address %} / {{ property_address }}{% endif %}

Dear {% if recipient_name %}{{ recipient_name }}{% else %}Agent{% endif %},

This letter is to confirm that {{ borrower_name }} has been pre-approved for a mortgage loan
with the following terms:

  Pre-Approved Loan Amount:   ${{ amount_formatted }}
  Loan Type:                  {{ loan_type }}
  {% if rate_lock %}Rate Lock Period:           {{ rate_lock }} days{% endif %}
  Letter Valid Through:       {{ expiry_date }}

This pre-approval is subject to the following conditions:
  - Final underwriting approval
  - Satisfactory appraisal of subject property
  - Verification that all information provided by the borrower remains accurate
  - No significant changes to the borrower's financial profile

{% if custom_note %}
{{ custom_note }}
{% endif %}

Please do not hesitate to contact me directly with any questions. I look forward to working
with you on this transaction.

Sincerely,

{{ lo_name }}
{{ lo_title }} | NMLS# {{ lo_nmls }}
{{ lo_phone }}
{{ lo_email }}
"""

CONDITIONAL_APPROVAL_TEMPLATE = """
{{ lo_name }}
{{ lo_title }}
NMLS# {{ lo_nmls }}
{{ org_name }}

{{ today }}

Re: Conditional Loan Approval — {{ borrower_name }}

Dear {{ recipient_name | default('Agent', true) }},

We are pleased to inform you that {{ borrower_name }} has received a CONDITIONAL APPROVAL
for a mortgage in the amount of ${{ amount_formatted }}.

OUTSTANDING CONDITIONS:
{% for condition in conditions_list %}
  {{ loop.index }}. {{ condition }}
{% endfor %}

{% if due_date %}All conditions must be satisfied by {{ due_date }}.{% endif %}

Once all conditions are cleared, we will issue a Clear to Close. Please reach out with
any questions.

Sincerely,
{{ lo_name }} | NMLS# {{ lo_nmls }}
"""

ADVERSE_ACTION_TEMPLATE = """
NOTICE OF ADVERSE ACTION

Date: {{ today }}
Applicant: {{ borrower_name }}
Application #: {{ loan_number }}

Dear {{ borrower_name }},

We regret to inform you that your application for a mortgage loan has been denied.

REASON(S) FOR DENIAL:
{% for reason in reasons_list %}
  {{ loop.index }}. {{ reason }}
{% endfor %}

CREDIT SCORE DISCLOSURE:
Your credit score of {{ credit_score }} was used in this decision.
Credit score range: 300-850. Score obtained from: {{ credit_bureau }}.
Scores below {{ score_threshold }} did not meet our minimum requirements.

Under the Equal Credit Opportunity Act (ECOA), you have the right to:
  - Request a statement of reasons within 60 days
  - Know that the CFPB oversees compliance: (855) 411-2372

This notice is provided pursuant to 15 U.S.C. 1691 et seq. (ECOA)
and 15 U.S.C. 1681 et seq. (FCRA).

{{ lo_name }} | {{ org_name }} | NMLS# {{ lo_nmls }}
"""

LOE_TEMPLATE = """
LETTER OF EXPLANATION

Date: {{ today }}
Borrower: {{ borrower_name }}
Loan Number: {{ loan_number }}
Re: {{ topic }}

To Whom It May Concern:

{{ explanation_body }}

I certify that the information provided above is true and accurate to the best of my knowledge.

________________________
{{ borrower_name }}
Date: ___________________
"""


class DocumentGenerator:

    def __init__(self):
        self.jinja = Environment(loader=BaseLoader())

    async def generate_preapproval_letter(
        self,
        borrower: Dict,
        loan: Dict,
        lo: Dict,
        approval_amount: float,
        property_address: Optional[str] = None,
        expiry_days: int = 30,
        custom_note: Optional[str] = None,
    ) -> Dict:
        today      = datetime.now().strftime("%B %d, %Y")
        expiry     = (date.today() + timedelta(days=expiry_days)).strftime("%B %d, %Y")
        amount_fmt = f"{approval_amount:,.0f}"

        context = dict(
            lo_name=lo.get("full_name", ""),
            lo_title=lo.get("title", "Loan Officer"),
            lo_phone=lo.get("phone", ""),
            lo_email=lo.get("email", ""),
            lo_nmls=lo.get("nmls_number", ""),
            org_name=lo.get("org_name", ""),
            org_address=lo.get("org_address", ""),
            today=today,
            borrower_name=borrower["full_name"],
            amount_formatted=amount_fmt,
            loan_type=loan.get("loan_type", "Conventional"),
            rate_lock=loan.get("rate_lock_days"),
            expiry_date=expiry,
            property_address=property_address,
            recipient_name=None,
            recipient_email=None,
            custom_note=custom_note,
        )

        letter_text = self.jinja.from_string(PREAPPROVAL_TEMPLATE).render(**context)
        pdf_bytes = self._render_pdf("Pre-Approval Letter", letter_text, lo.get("org_name", ""))

        preview = (
            f"Pre-Approval Letter for **{borrower['full_name']}**\n"
            f"Amount: **${amount_fmt}**  |  Valid through: **{expiry}**\n"
            f"Loan type: {loan.get('loan_type', 'Conventional')}"
        )

        doc_id = str(uuid.uuid4())
        return {"document_id": doc_id, "pdf_bytes": pdf_bytes, "preview_text": preview, "letter_text": letter_text}

    async def generate_conditional_approval(
        self, borrower: Dict, loan: Dict, lo: Dict,
        conditions: str, due_date: Optional[str] = None,
    ) -> Dict:
        conditions_list = [c.strip() for c in conditions.split("\n") if c.strip()]
        today = datetime.now().strftime("%B %d, %Y")
        amount_fmt = f"{loan.get('loan_amount', 0):,.0f}"

        context = dict(
            lo_name=lo.get("full_name"), lo_title=lo.get("title", "Loan Officer"),
            lo_nmls=lo.get("nmls_number"), org_name=lo.get("org_name"),
            today=today, borrower_name=borrower["full_name"],
            amount_formatted=amount_fmt, conditions_list=conditions_list, due_date=due_date,
        )

        letter_text = self.jinja.from_string(CONDITIONAL_APPROVAL_TEMPLATE).render(**context)
        pdf_bytes   = self._render_pdf("Conditional Approval Letter", letter_text, lo.get("org_name", ""))
        doc_id      = str(uuid.uuid4())

        return {"document_id": doc_id, "pdf_bytes": pdf_bytes,
                "preview_text": f"Conditional approval for {borrower['full_name']} with {len(conditions_list)} outstanding conditions."}

    async def generate_adverse_action_notice(
        self, borrower: Dict, lo: Dict,
        denial_reasons: str, credit_score: int,
    ) -> Dict:
        reasons_list = [r.strip() for r in denial_reasons.split("\n") if r.strip()]
        today = datetime.now().strftime("%B %d, %Y")

        context = dict(
            today=today, borrower_name=borrower["full_name"],
            loan_number=borrower.get("loan_number", "N/A"),
            reasons_list=reasons_list, credit_score=credit_score,
            credit_bureau="Equifax, Experian, TransUnion",
            score_threshold=620,
            lo_name=lo.get("full_name"), org_name=lo.get("org_name"),
            lo_nmls=lo.get("nmls_number"),
        )

        letter_text = self.jinja.from_string(ADVERSE_ACTION_TEMPLATE).render(**context)
        pdf_bytes   = self._render_pdf("Notice of Adverse Action", letter_text, lo.get("org_name", ""))
        doc_id      = str(uuid.uuid4())

        return {"document_id": doc_id, "pdf_bytes": pdf_bytes,
                "preview_text": f"Adverse action notice for {borrower['full_name']} — {len(reasons_list)} denial reason(s)."}

    async def generate_loe(
        self, borrower: Dict, lo: Dict,
        topic: str, details: str = "",
    ) -> Dict:
        today = datetime.now().strftime("%B %d, %Y")

        prompt = f"""Write a professional Letter of Explanation (LOE) body paragraph for a mortgage underwriter.

Borrower: {borrower['full_name']}
Topic: {topic}
Additional details: {details if details else 'None provided'}

Requirements:
- Written in first person (from borrower's perspective)
- Professional but conversational tone
- 2-4 sentences maximum
- Factual and specific — no vague language
- Explains the situation clearly and provides resolution where applicable
- Does NOT include greetings, signatures, or headers (those are in the template)

Write ONLY the explanation paragraph body text.
"""
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        explanation_body = response.content[0].text.strip()

        context = dict(
            today=today, borrower_name=borrower["full_name"],
            loan_number=borrower.get("loan_number", "N/A"),
            topic=topic, explanation_body=explanation_body,
        )

        letter_text = self.jinja.from_string(LOE_TEMPLATE).render(**context)
        pdf_bytes   = self._render_pdf("Letter of Explanation", letter_text, lo.get("org_name", ""))
        doc_id      = str(uuid.uuid4())

        return {
            "document_id": doc_id,
            "pdf_bytes": pdf_bytes,
            "preview_text": f"**LOE — {topic}**\n\n{explanation_body}\n\n*(Borrower signature required)*",
            "letter_text": letter_text,
        }

    def _render_pdf(self, title: str, content: str, org_name: str) -> bytes:
        """Render document text to a styled PDF using ReportLab."""
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=1 * inch, leftMargin=1 * inch,
            topMargin=1 * inch, bottomMargin=1 * inch,
        )

        styles = getSampleStyleSheet()

        header_style = ParagraphStyle(
            "Header", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1a3a6b"), spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica",
            leading=16, spaceAfter=6,
        )

        story = []
        story.append(Paragraph(org_name.upper(), header_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a3a6b")))
        story.append(Spacer(1, 12))

        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
                continue
            story.append(Paragraph(line, body_style))

        doc.build(story)
        return buffer.getvalue()
