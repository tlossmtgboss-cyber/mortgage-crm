"""AI-powered email composition for mortgage lead engagement."""
import logging
import os
import re
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES = {
    "purchase": {
        "pre_approval_intro": {"subject": "Your Pre-Approval Options, {first_name}", "tone": "helpful, encouraging", "context": "New purchase lead, not yet pre-approved"},
        "rate_environment": {"subject": "What Today's Rates Mean for Your Purchase", "tone": "informative, advisory", "context": "Active purchase lead, nurture phase"},
        "market_update": {"subject": "{city} Home Market Update", "tone": "expert, data-driven", "context": "Long-term nurture, geographic relevance"},
        "first_time_buyer": {"subject": "First-Time Buyer? Here's What You Need to Know", "tone": "educational, supportive", "context": "First-time homebuyer education"},
    },
    "refinance": {
        "rate_alert": {"subject": "Rates Dropped — Your Refi Savings Estimate", "tone": "urgent but professional", "context": "Rate-triggered alert for refi candidates"},
        "break_even": {"subject": "How Long Until Your Refi Pays Off?", "tone": "analytical, helpful", "context": "Educational nurture for refi leads"},
        "cash_out_education": {"subject": "Is a Cash-Out Refi Right for You?", "tone": "consultative", "context": "Cash-out refinance education"},
    },
    "post_close": {
        "anniversary": {"subject": "Happy Home Anniversary, {first_name}!", "tone": "warm, celebratory", "context": "1-year anniversary, equity update"},
        "referral_ask": {"subject": "Know Anyone Looking to Buy or Refi?", "tone": "casual, appreciative", "context": "Referral generation from past clients"},
        "rate_watch": {"subject": "When to Consider Refinancing Your Current Loan", "tone": "advisory", "context": "Post-close rate monitoring"},
    },
    "appointment": {
        "confirmation": {"subject": "Your Consultation with {lo_name} — {date}", "tone": "professional, reassuring", "context": "Appointment just booked"},
        "reminder": {"subject": "Reminder: Your Call with {lo_name} Tomorrow", "tone": "friendly, preparatory", "context": "T-24h appointment reminder"},
        "no_show_followup": {"subject": "We Missed You — Let's Reschedule", "tone": "warm, no judgment", "context": "Post no-show re-engagement"},
    },
}

COMPLIANCE_RULES = [
    "Never promise or quote a specific interest rate unless referencing a locked rate",
    "Include NMLS# in every email footer",
    "Include Equal Housing Lender text in footer",
    "Include physical mailing address (CAN-SPAM)",
    "Include unsubscribe link (CAN-SPAM)",
    "Never reference race, sex, religion, national origin, marital status, age, disability (ECOA)",
    "No kickback language or undisclosed referral arrangements (RESPA)",
]

FALLBACK_BODIES = {
    "pre_approval_intro": """<p>Hi {first_name},</p>
<p>Thank you for your interest in exploring mortgage options. I'd love to help you find the best solution for your home financing needs.</p>
<p>Getting pre-approved is a great first step — it takes about 10 minutes and gives you a clear picture of your buying power. Here's what I can help with:</p>
<ul>
<li>Compare multiple loan program options</li>
<li>Find competitive rates tailored to your situation</li>
<li>Streamline the approval process</li>
</ul>
<p>Would you have 15 minutes this week for a quick call? I'm happy to answer any questions.</p>
<p>Best regards,<br>{lo_name}</p>""",

    "rate_alert": """<p>Hi {first_name},</p>
<p>Rates have moved recently, and I wanted to make sure you have the latest information for your refinance consideration.</p>
<p>Based on current market conditions, now could be a good time to explore your options. I can run a quick analysis to show you potential monthly savings.</p>
<p>Want me to put together a comparison for you? It only takes a few minutes.</p>
<p>Best regards,<br>{lo_name}</p>""",

    "referral_ask": """<p>Hi {first_name},</p>
<p>I hope you're enjoying your home! It's been a pleasure working with you.</p>
<p>If you know anyone who's thinking about buying a home or refinancing, I'd love the opportunity to help them the same way. A personal referral means the world to me.</p>
<p>Thanks again for your trust!</p>
<p>Warm regards,<br>{lo_name}</p>""",
}


class AIEmailComposer:
    """Composes personalized mortgage emails using AI + templates."""

    def __init__(self):
        self.client = None
        try:
            from openai import AsyncOpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.client = AsyncOpenAI(api_key=api_key)
        except ImportError:
            logger.debug("OpenAI not available, using template fallbacks")

    async def compose_email(self, template_category: str, template_key: str,
                           lead_data: dict, lo_data: dict, org_config: dict,
                           custom_context: str = None) -> dict:
        """Generate personalized email. Returns {"subject": str, "html_body": str, "plain_body": str}."""
        template = EMAIL_TEMPLATES.get(template_category, {}).get(template_key)
        if not template:
            raise ValueError(f"Template {template_category}/{template_key} not found")

        variables = self._build_variables(lead_data, lo_data, org_config)
        subject = self._render_variables(template["subject"], variables)

        if self.client:
            body = await self._generate_with_llm(template, lead_data, lo_data, org_config, custom_context)
        else:
            body = self._generate_fallback(template_key, variables)

        footer = self._build_compliance_footer(lo_data, org_config)
        html_body = self._wrap_html(body, footer)
        plain_body = self._strip_html(body) + "\n\n" + self._strip_html(footer)

        return {"subject": subject, "html_body": html_body, "plain_body": plain_body}

    async def compose_followup(self, previous_subject: str, lead_data: dict,
                               lo_data: dict, org_config: dict,
                               engagement_data: dict = None) -> dict:
        """Generate follow-up email based on previous interaction."""
        variables = self._build_variables(lead_data, lo_data, org_config)
        subject = f"Re: {previous_subject}"

        if self.client:
            engagement_context = ""
            if engagement_data:
                if engagement_data.get("opened"):
                    engagement_context = "The borrower opened your previous email."
                if engagement_data.get("clicked"):
                    engagement_context += " They clicked a link in it."

            prompt = (
                f"Write a brief follow-up email from {lo_data.get('name', 'the loan officer')} to "
                f"{lead_data.get('first_name', 'the borrower')}. Previous subject: '{previous_subject}'. "
                f"{engagement_context} Keep it under 100 words, warm and professional."
            )

            body = await self._call_llm(prompt, "warm, follow-up", org_config)
        else:
            body = f"""<p>Hi {variables.get('first_name', '')},</p>
<p>I wanted to follow up on my previous message. I'm here to help whenever you're ready — no rush at all.</p>
<p>Feel free to reply to this email or call me directly if you have any questions.</p>
<p>Best,<br>{variables.get('lo_name', '')}</p>"""

        footer = self._build_compliance_footer(lo_data, org_config)
        html_body = self._wrap_html(body, footer)
        plain_body = self._strip_html(body) + "\n\n" + self._strip_html(footer)

        return {"subject": subject, "html_body": html_body, "plain_body": plain_body}

    def list_templates(self) -> dict:
        """List available template categories and keys."""
        return {
            category: [
                {"key": key, "subject": tmpl["subject"], "tone": tmpl["tone"]}
                for key, tmpl in templates.items()
            ]
            for category, templates in EMAIL_TEMPLATES.items()
        }

    def _build_variables(self, lead_data: dict, lo_data: dict, org_config: dict) -> dict:
        return {
            "first_name": lead_data.get("first_name", ""),
            "last_name": lead_data.get("last_name", ""),
            "lo_name": lo_data.get("name", ""),
            "lo_phone": lo_data.get("phone", ""),
            "lo_email": lo_data.get("email", ""),
            "company": org_config.get("company_name", ""),
            "nmls": lo_data.get("nmls_number", ""),
            "city": lead_data.get("city", ""),
            "date": lead_data.get("appointment_date", ""),
            "loan_type": lead_data.get("loan_purpose", "home loan"),
            "month": datetime.now().strftime("%B"),
            "year": str(datetime.now().year),
        }

    def _render_variables(self, template: str, variables: dict) -> str:
        for key, value in variables.items():
            template = template.replace("{" + key + "}", str(value or ""))
        return template

    async def _generate_with_llm(self, template: dict, lead_data: dict,
                                  lo_data: dict, org_config: dict,
                                  custom_context: str = None) -> str:
        """Use LLM to generate email body with compliance guardrails."""
        prompt = (
            f"Write a mortgage marketing email.\n"
            f"Borrower: {lead_data.get('first_name', 'the borrower')}\n"
            f"Loan officer: {lo_data.get('name', '')}\n"
            f"Company: {org_config.get('company_name', '')}\n"
            f"Context: {template.get('context', '')}\n"
            f"Loan interest: {lead_data.get('loan_purpose', 'not specified')}\n"
        )
        if custom_context:
            prompt += f"Additional context: {custom_context}\n"

        prompt += (
            "\nRequirements:\n"
            "- 80-150 words\n"
            "- Use HTML tags (<p>, <ul>, <li>) for formatting\n"
            "- Include a clear call-to-action\n"
            "- Sign off with the loan officer's name\n"
            "- Do NOT include a subject line — only the body\n"
        )

        return await self._call_llm(prompt, template.get("tone", "professional"), org_config)

    async def _call_llm(self, user_prompt: str, tone: str, org_config: dict) -> str:
        """Call LLM with compliance system prompt."""
        system_prompt = (
            f"You are a mortgage email writer for {org_config.get('company_name', 'a mortgage company')}. "
            f"Write professional, warm emails. Tone: {tone}.\n\n"
            f"COMPLIANCE RULES (MUST FOLLOW):\n"
            + "\n".join(f"- {r}" for r in COMPLIANCE_RULES)
            + "\n\nNever include subject lines. Only write the email body in HTML."
        )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as _exc:  # noqa: BLE001
            logger.exception("LLM email generation failed, using fallback")
            return "<p>We'd love to help with your mortgage needs. Please reach out at your convenience.</p>"

    def _generate_fallback(self, template_key: str, variables: dict) -> str:
        """Deterministic fallback when LLM is unavailable."""
        body = FALLBACK_BODIES.get(template_key)
        if body:
            return self._render_variables(body, variables)
        return self._render_variables(
            "<p>Hi {first_name},</p><p>Thank you for your interest. I'm here to help with your mortgage needs. "
            "Please don't hesitate to reach out.</p><p>Best regards,<br>{lo_name}</p>",
            variables,
        )

    def _build_compliance_footer(self, lo_data: dict, org_config: dict) -> str:
        nmls = lo_data.get("nmls_number", "")
        company = org_config.get("company_name", "")
        address = org_config.get("address", "")
        lo_nmls = lo_data.get("individual_nmls", "")

        return f"""<div style="margin-top:30px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:11px;color:#888;line-height:1.6;">
<p>{company} | NMLS# {nmls}{f' | LO NMLS# {lo_nmls}' if lo_nmls else ''}</p>
<p>{address}</p>
<p>Equal Housing Lender | Equal Housing Opportunity</p>
<p><a href="{{{{unsubscribe_url}}}}" style="color:#888;">Unsubscribe</a> | <a href="{{{{preferences_url}}}}" style="color:#888;">Email Preferences</a></p>
</div>"""

    def _wrap_html(self, body: str, footer: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;font-size:15px;line-height:1.6;">
{body}
{footer}
</body>
</html>"""

    def _strip_html(self, html: str) -> str:
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'</p>', '\n\n', text)
        text = re.sub(r'<li>', '  - ', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()


_composer = None


def get_composer() -> AIEmailComposer:
    global _composer
    if _composer is None:
        _composer = AIEmailComposer()
    return _composer
