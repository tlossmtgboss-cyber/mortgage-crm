"""
Content Library Seeder

Seeds the database with 50 professionally written, compliance-friendly
mortgage marketing templates across all content types and lifecycle stages.

These serve as the platform-default library that every organization gets
out of the box. Organizations can fork and customize any template or add
their own pieces on top of the library.

Template categories:
    - 10 New lead nurture emails
    - 5  Application stage emails
    - 5  Processing / underwriting update emails
    - 5  Closing stage emails
    - 10 Post-close nurture emails
    - 5  SMS templates
    - 5  Social media posts
    - 5  Refinance outreach emails

All templates include Equal Housing Lender language in HTML footers,
CAN-SPAM-compliant unsubscribe links, and NMLS# placeholders to meet
federal advertising requirements.

Usage:
    from services.content_library_seeder import seed_content_library

    # Idempotent — safe to call multiple times
    count = seed_content_library(db)
    print(f"Seeded {count} templates")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models.content_library import ContentLibraryItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Equal Housing / Compliance footer blocks
# (appended to HTML bodies at seed-time)
# ---------------------------------------------------------------------------

_COMPLIANCE_FOOTER_HTML = """
<p style="font-size:11px;color:#666;margin-top:32px;border-top:1px solid #e0e0e0;padding-top:12px;">
  {{company_name}} | NMLS #{{company_nmls}} | {{company_address}}<br>
  Equal Housing Lender. This is not a commitment to lend or extend credit. Programs, rates, terms and conditions
  are subject to change without notice. Subject to underwriting approval.<br>
  <a href="{{unsubscribe_link}}" style="color:#666;">Unsubscribe</a>
</p>
"""

_COMPLIANCE_FOOTER_TEXT = (
    "\n\n---\n"
    "{{company_name}} | NMLS #{{company_nmls}} | {{company_address}}\n"
    "Equal Housing Lender. Programs, rates, terms and conditions subject to change without notice.\n"
    "To unsubscribe: {{unsubscribe_link}}"
)

_EQUAL_HOUSING_TAG = "equal_housing"
_NLMS_TAG = "nmls_compliant"


def _html(title: str, headline: str, body_paragraphs: List[str]) -> str:
    """Build a simple but professional HTML email body."""
    paragraphs_html = "".join(f"<p>{p}</p>" for p in body_paragraphs)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;font-size:15px;color:#222;max-width:600px;margin:0 auto;padding:24px;">
  <h2 style="color:#1a3c6e;">{headline}</h2>
  {paragraphs_html}
  <p>Warm regards,<br>
  <strong>{{{{loan_officer_name}}}}</strong><br>
  {{{{company_name}}}}<br>
  {{{{loan_officer_phone}}}} | {{{{loan_officer_email}}}}<br>
  NMLS #{{{{loan_officer_nmls}}}}</p>
  {_COMPLIANCE_FOOTER_HTML}
</body>
</html>"""


def _text(paragraphs: List[str]) -> str:
    """Build a plain-text email body."""
    body = "\n\n".join(paragraphs)
    return (
        f"{body}\n\n"
        "Warm regards,\n"
        "{{loan_officer_name}}\n"
        "{{company_name}}\n"
        "{{loan_officer_phone}} | {{loan_officer_email}}\n"
        "NMLS #{{loan_officer_nmls}}"
        f"{_COMPLIANCE_FOOTER_TEXT}"
    )


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------
# Each dict maps directly to ContentLibraryItem columns.
# All items are platform defaults: organization_id=None, is_platform_default=True,
# compliance_approved=True.
# ---------------------------------------------------------------------------

_TEMPLATES: List[Dict[str, Any]] = [

    # =========================================================================
    # NEW LEAD NURTURE EMAILS (10)
    # =========================================================================

    {
        "title": "Welcome — Thank You for Your Interest",
        "description": "First touch email sent within minutes of a new lead coming in. Warm intro, sets expectations for next steps.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, welcome — let's find your perfect loan",
        "body_html": _html(
            "Welcome",
            "Thanks for reaching out, {{first_name}}!",
            [
                "I'm {{loan_officer_name}}, and I'm thrilled you chose {{company_name}} to help with "
                "your home financing journey. Whether you're buying your first home, upsizing, or "
                "refinancing, my team and I are here to make the process as smooth as possible.",
                "Here's what you can expect next:",
                "<ul>"
                "<li>I'll review your information and reach out within one business day.</li>"
                "<li>We'll schedule a quick 15-minute call to discuss your goals and current rates.</li>"
                "<li>I'll put together personalized loan options — no obligation, no pressure.</li>"
                "</ul>",
                "In the meantime, feel free to reply to this email with any questions, or click below "
                "to schedule a call at a time that works for you.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Schedule My Free Consultation</a></p>',
                "I look forward to speaking with you soon!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Thanks for reaching out to {{company_name}}! I'm {{loan_officer_name}}, and I'm excited "
            "to help you with your home financing journey.",
            "Here's what happens next:\n"
            "1. I'll review your information and reach out within one business day.\n"
            "2. We'll schedule a quick 15-minute call to discuss your goals and current rates.\n"
            "3. I'll put together personalized loan options — no obligation, no pressure.",
            "Schedule a call here: {{calendar_link}}",
            "I look forward to speaking with you soon!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["welcome", "first_touch", "new_lead"],
    },

    {
        "title": "Day 2 Follow-Up — Did You Get My Message?",
        "description": "Second touch sent 2 days after the welcome email if no response.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, quick follow-up on your mortgage inquiry",
        "body_html": _html(
            "Day 2 Follow-Up",
            "Just checking in, {{first_name}}",
            [
                "I wanted to follow up on the information you submitted about your home financing goals. "
                "I know your time is valuable, so I'll keep this brief.",
                "Mortgage rates are moving daily, and I'd hate for you to miss an opportunity to lock in "
                "a great rate. A quick 10-minute call is all it takes to get a clear picture of your options.",
                "If now isn't the right time, no worries at all — just let me know when works best for you.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Pick a Time That Works</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "I wanted to follow up quickly on your mortgage inquiry. Rates are moving daily, and I'd hate "
            "for you to miss a good opportunity.",
            "A 10-minute call is all it takes. You can pick a time here: {{calendar_link}}",
            "If the timing isn't right, just let me know — I'm here whenever you're ready.",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["follow_up", "day_2", "new_lead"],
    },

    {
        "title": "Current Rate Snapshot — Personalized for You",
        "description": "Delivers a rate overview to keep the lead engaged. Use when rates are favorable.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "Today's rates for {{first_name}} — {{current_month}} update",
        "body_html": _html(
            "Rate Snapshot",
            "Here's your personalized rate snapshot, {{first_name}}",
            [
                "Mortgage rates change daily, so I wanted to give you a current picture of what "
                "borrowers like you are qualifying for this month.",
                "<table style='width:100%;border-collapse:collapse;'>"
                "<tr style='background:#f0f4fa;'><th style='text-align:left;padding:8px;'>Loan Type</th><th style='text-align:left;padding:8px;'>Today's Rate*</th></tr>"
                "<tr><td style='padding:8px;'>30-Year Fixed</td><td style='padding:8px;'>Ask me today</td></tr>"
                "<tr style='background:#f0f4fa;'><td style='padding:8px;'>15-Year Fixed</td><td style='padding:8px;'>Ask me today</td></tr>"
                "<tr><td style='padding:8px;'>5/1 ARM</td><td style='padding:8px;'>Ask me today</td></tr>"
                "</table>",
                "<p style='font-size:12px;'>*Rates shown are for illustration purposes. Your actual rate depends on credit score, "
                "down payment, loan amount, and property type. Contact me for a personalized quote.</p>",
                "The best way to get your actual rate is a quick pre-qualification conversation. It's free, "
                "takes about 10 minutes, and there's no impact to your credit score at this stage.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Get My Personalized Rate</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Rates are shifting daily, so I wanted to reach out with a quick update.",
            "The best way to know YOUR exact rate is a free, no-obligation conversation — "
            "no credit pull at this stage. Takes about 10 minutes.",
            "Schedule here: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{current_month}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["rate_snapshot", "market_update", "new_lead"],
    },

    {
        "title": "Pre-Qualification Invitation",
        "description": "Invites lead to start the pre-qual process. Emphasizes speed and no credit impact.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, get pre-qualified in as little as 10 minutes",
        "body_html": _html(
            "Pre-Qualification Invite",
            "Find out how much home you can afford, {{first_name}}",
            [
                "Getting pre-qualified is the smartest first step on your home buying journey — "
                "and it's easier than you might think.",
                "Here's what a pre-qualification with {{company_name}} looks like:",
                "<ul>"
                "<li><strong>Fast:</strong> Most clients complete it in under 10 minutes.</li>"
                "<li><strong>No hard credit pull:</strong> A soft inquiry is used at this stage — no impact to your score.</li>"
                "<li><strong>Know your budget:</strong> You'll walk away knowing your estimated purchase price range.</li>"
                "<li><strong>Stronger offers:</strong> Sellers take pre-qualified buyers more seriously.</li>"
                "</ul>",
                "Ready to get started? Let's set up a quick call.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Start My Pre-Qualification</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Getting pre-qualified is the smartest first step — and it only takes about 10 minutes.",
            "What you get:\n"
            "- Estimated purchase price range\n"
            "- No hard credit pull at this stage\n"
            "- A stronger position when making offers",
            "Let's set up a quick call: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["pre_qual", "cta", "new_lead"],
    },

    {
        "title": "5 Things to Know Before You Get a Mortgage",
        "description": "Educational nurture email. Builds trust and positions LO as an expert.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "5 things every home buyer should know, {{first_name}}",
        "body_html": _html(
            "5 Things to Know",
            "5 things every home buyer should know before getting a mortgage",
            [
                "Buying a home is one of the biggest financial decisions you'll ever make. "
                "I want to make sure you go in fully informed. Here are five things I wish "
                "every buyer knew before they started the process:",
                "<ol>"
                "<li><strong>Your credit score matters — a lot.</strong> Even a 20-point improvement can save you tens of thousands over the life of a loan.</li>"
                "<li><strong>Down payment isn't always 20%.</strong> FHA loans start at 3.5%, conventional loans can be as low as 3%, and VA loans are often 0% down for veterans.</li>"
                "<li><strong>Pre-approval ≠ pre-qualification.</strong> Pre-approval is stronger — it means a lender has reviewed your income and credit. Sellers prefer it.</li>"
                "<li><strong>Closing costs are real.</strong> Budget 2–5% of the loan amount for closing costs beyond your down payment.</li>"
                "<li><strong>Rate shopping is encouraged.</strong> Multiple mortgage inquiries within a 45-day window count as a single hard pull on your credit.</li>"
                "</ol>",
                "Have questions about any of these? I'm happy to talk through what applies to your specific situation.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Let\'s Talk</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Here are 5 things every home buyer should know before getting a mortgage:",
            "1. Your credit score matters — a lot.\n"
            "2. Down payment isn't always 20% (FHA starts at 3.5%).\n"
            "3. Pre-approval is stronger than pre-qualification.\n"
            "4. Budget 2-5% for closing costs.\n"
            "5. Rate shopping within 45 days counts as one hard pull.",
            "Questions? Let's chat: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["educational", "tips", "new_lead"],
    },

    {
        "title": "Rent vs. Own Calculator Invite",
        "description": "Engages fence-sitters by showing the long-term financial case for owning.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "Are you paying your landlord's mortgage, {{first_name}}?",
        "body_html": _html(
            "Rent vs. Own",
            "Renting vs. owning — the numbers might surprise you",
            [
                "I hear it from renters all the time: <em>\"I'm not ready to buy.\"</em> "
                "I get it — but let's look at what that decision is actually costing you.",
                "Consider this: if you're paying $1,800/month in rent, that's $21,600 a year — "
                "$108,000 over five years — going directly to your landlord's equity, not yours.",
                "A comparable mortgage payment could be building <em>your</em> net worth instead.",
                "I'd love to run the actual numbers for your situation — it takes about 5 minutes "
                "and the results are often eye-opening.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Run My Numbers</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Quick question: how much are you paying in rent each month?",
            "Every dollar of rent goes to your landlord's equity — not yours. "
            "I'd love to show you what a comparable mortgage payment would look like "
            "and how much equity you could be building.",
            "It takes 5 minutes. Book here: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["rent_vs_own", "cta", "new_lead"],
    },

    {
        "title": "Down Payment Programs — You May Qualify",
        "description": "Highlights down payment assistance programs. Great for first-time buyers.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, you may qualify for down payment assistance",
        "body_html": _html(
            "Down Payment Programs",
            "Did you know down payment help may be available to you?",
            [
                "One of the biggest myths in home buying is that you need a 20% down payment. "
                "Many first-time — and even repeat — buyers qualify for programs that significantly "
                "reduce the upfront cash needed to buy a home.",
                "Some programs I can help you explore:",
                "<ul>"
                "<li><strong>FHA Loans:</strong> As little as 3.5% down for qualifying borrowers.</li>"
                "<li><strong>Conventional 97:</strong> Just 3% down for first-time buyers.</li>"
                "<li><strong>VA Loans:</strong> 0% down for eligible veterans and active-duty military.</li>"
                "<li><strong>USDA Loans:</strong> 0% down in eligible rural and suburban areas.</li>"
                "<li><strong>State/local DPA programs:</strong> Many offer grants or forgivable loans for down payment and closing costs.</li>"
                "</ul>",
                "Let's find out which programs you qualify for — it's a free conversation.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">See My Options</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "You may qualify for down payment assistance — and that could mean getting into "
            "a home sooner than you think.",
            "Programs include FHA (3.5% down), VA (0% for veterans), USDA (0% in eligible areas), "
            "and many state/local grant programs.",
            "Let's find out which ones fit your situation: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["down_payment", "dpa", "first_time_buyer", "new_lead"],
    },

    {
        "title": "Credit Score Tips — Get Ready to Buy",
        "description": "Educational email for leads who may need credit improvement before qualifying.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, these credit tips could save you thousands",
        "body_html": _html(
            "Credit Tips",
            "Small credit changes = big mortgage savings",
            [
                "Your credit score is one of the most powerful levers in your mortgage. "
                "A difference of even 40–60 points can mean the difference between a great "
                "rate and one that costs you tens of thousands of dollars over 30 years.",
                "Here are five quick wins that can boost your score:",
                "<ol>"
                "<li><strong>Pay down credit cards to below 30% utilization</strong> — this is often the fastest improvement strategy.</li>"
                "<li><strong>Don't close old accounts</strong> — length of credit history matters.</li>"
                "<li><strong>Dispute any errors</strong> on your credit report at annualcreditreport.com.</li>"
                "<li><strong>Avoid opening new credit</strong> in the 6 months before applying for a mortgage.</li>"
                "<li><strong>Set up autopay</strong> — even one missed payment can hurt your score significantly.</li>"
                "</ol>",
                "Wherever you are in the process, I'd love to review your situation and help "
                "you build a plan to get into the best possible position before you apply.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Get My Free Credit Review</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your credit score directly impacts your mortgage rate. Here are 5 quick wins:",
            "1. Pay down credit cards below 30% utilization.\n"
            "2. Don't close old accounts.\n"
            "3. Dispute any errors on your credit report.\n"
            "4. Avoid opening new credit before applying.\n"
            "5. Set up autopay to protect your payment history.",
            "Let me review your credit picture for free: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["credit", "educational", "new_lead"],
    },

    {
        "title": "30-Day Check-In — Still Thinking About It?",
        "description": "Sent at 30 days to re-engage leads who have gone quiet.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, still thinking about buying a home?",
        "body_html": _html(
            "30-Day Check-In",
            "Just checking in, {{first_name}} — no pressure",
            [
                "It's been about a month since you first reached out, and I wanted to touch base. "
                "Life gets busy — I completely understand.",
                "Whether your plans have changed, accelerated, or you're still in research mode, "
                "I'm here as a resource whenever you're ready.",
                "A few things worth knowing about the current market:",
                "<ul>"
                "<li>Rates have been active — it's worth a quick conversation to see where you stand.</li>"
                "<li>Inventory in many markets is still competitive — getting pre-approved puts you first in line.</li>"
                "<li>There's no cost or commitment to get a pre-qualification — just clarity.</li>"
                "</ul>",
                "If now's not the right time, I respect that completely. Just know I'm here when you're ready.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Let\'s Reconnect</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "It's been about a month since you first reached out — just wanted to check in.",
            "No pressure at all. Whether your plans have changed or you're still thinking things through, "
            "I'm here as a resource whenever you're ready.",
            "When you're ready to reconnect: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["30_day", "re_engagement", "nurture", "new_lead"],
    },

    {
        "title": "Mortgage Myth Busters",
        "description": "Fun, engaging email that corrects common mortgage misconceptions.",
        "content_type": "email",
        "category": "new_lead",
        "subject_line": "{{first_name}}, 4 mortgage myths that might be holding you back",
        "body_html": _html(
            "Myth Busters",
            "4 mortgage myths debunked — #3 surprises most people",
            [
                "There's a lot of outdated advice floating around about mortgages. Here are four "
                "myths that may be standing between you and homeownership:",
                "<p><strong>Myth #1: You need a 20% down payment.</strong><br>"
                "<em>Reality:</em> Many programs allow 3–5% down, and VA/USDA loans offer 0% down.</p>",
                "<p><strong>Myth #2: You need perfect credit.</strong><br>"
                "<em>Reality:</em> FHA loans are available with scores as low as 580. Even conventional "
                "loans can be approved with scores in the 620–640 range.</p>",
                "<p><strong>Myth #3: Pre-approval hurts your credit.</strong><br>"
                "<em>Reality:</em> Pre-qualification uses a soft pull. Even a full pre-approval is a "
                "single hard inquiry — typically a 5-point or less temporary impact.</p>",
                "<p><strong>Myth #4: Self-employed people can't get mortgages.</strong><br>"
                "<em>Reality:</em> Self-employed borrowers absolutely can qualify. We use two years "
                "of tax returns and bank statements to verify income.</p>",
                "Which of these surprised you? Reply and let me know — I love these conversations.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "4 mortgage myths that might be holding you back:",
            "Myth 1: You need 20% down. WRONG — many programs allow 3-5%, VA/USDA offer 0%.",
            "Myth 2: You need perfect credit. WRONG — FHA goes as low as 580.",
            "Myth 3: Pre-approval hurts your credit. WRONG — it's typically a 5-point or less impact.",
            "Myth 4: Self-employed people can't qualify. WRONG — we use tax returns and bank statements.",
            "Want to see where YOU stand? {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{calendar_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["educational", "myth_busters", "engaging", "new_lead"],
    },

    # =========================================================================
    # APPLICATION STAGE EMAILS (5)
    # =========================================================================

    {
        "title": "Application Received — What Happens Next",
        "description": "Confirms application receipt and explains the pipeline. Sets clear expectations.",
        "content_type": "email",
        "category": "application",
        "subject_line": "{{first_name}}, your application is in — here's what's next",
        "body_html": _html(
            "Application Received",
            "Great news — your application is submitted, {{first_name}}!",
            [
                "Congratulations on taking this important step toward homeownership! "
                "Your application has been received and we're already getting to work.",
                "Here's a quick overview of the process from here:",
                "<ol>"
                "<li><strong>Document Collection (1–3 days):</strong> We'll request the supporting documents needed to process your file.</li>"
                "<li><strong>Processing (5–10 days):</strong> Our processing team reviews everything and submits to underwriting.</li>"
                "<li><strong>Underwriting (5–10 days):</strong> A licensed underwriter makes the official credit decision.</li>"
                "<li><strong>Clear to Close:</strong> You'll receive your Closing Disclosure and we'll schedule your closing date.</li>"
                "<li><strong>Closing Day!</strong></li>"
                "</ol>",
                "I'll be in touch with any updates. In the meantime, please avoid making "
                "large purchases, opening new credit accounts, or changing jobs — any of "
                "these can affect your loan approval.",
                "Questions? Just reply to this email or call me directly at {{loan_officer_phone}}.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your application is submitted — great work taking this step!",
            "What happens next:\n"
            "1. Document Collection (1-3 days)\n"
            "2. Processing (5-10 days)\n"
            "3. Underwriting (5-10 days)\n"
            "4. Clear to Close + Closing Disclosure\n"
            "5. Closing Day!",
            "IMPORTANT: Please avoid large purchases, new credit accounts, or job changes "
            "until after closing — these can affect your approval.",
            "Questions? Call me at {{loan_officer_phone}} anytime.",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["application", "onboarding", "next_steps"],
    },

    {
        "title": "Documents Needed — Let's Keep Things Moving",
        "description": "Friendly but urgent request for missing documents to keep the file on track.",
        "content_type": "email",
        "category": "application",
        "subject_line": "Action needed: documents required for your loan, {{first_name}}",
        "body_html": _html(
            "Documents Needed",
            "We need a few documents to keep your loan on track",
            [
                "Hi {{first_name}} — great news, your file is moving through processing! "
                "To keep everything on schedule, we still need the following documents from you:",
                "<div style='background:#fff3cd;padding:16px;border-left:4px solid #ffc107;margin:16px 0;'>"
                "<strong>Documents Outstanding (please upload or email as soon as possible):</strong><br>"
                "Your loan officer or processor will specify the exact list for your file."
                "</div>",
                "The fastest way to submit documents is through your secure borrower portal:",
                '<p><a href="{{portal_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Upload Documents Securely</a></p>',
                "Alternatively, you can scan and email them directly to {{loan_officer_email}}. "
                "Every day counts at this stage — getting these in quickly helps ensure we "
                "hit your target closing date of {{closing_date}}.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your file is moving — but we still need a few documents to keep things on track.",
            "Please upload them through your secure portal: {{portal_link}}",
            "Or email them directly to: {{loan_officer_email}}",
            "Every day matters at this stage. Your target closing date is {{closing_date}}.",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{portal_link}}", "{{closing_date}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["documents", "urgent", "application"],
    },

    {
        "title": "Loan Estimate Delivered — Review Explained",
        "description": "Accompanies the Loan Estimate (LE) to help borrower understand what they're seeing.",
        "content_type": "email",
        "category": "application",
        "subject_line": "{{first_name}}, your Loan Estimate is ready — here's what to look for",
        "body_html": _html(
            "Loan Estimate Review",
            "Your Loan Estimate is ready — let me walk you through it",
            [
                "Your official Loan Estimate (LE) has been sent to {{email}}. "
                "This is a federally required document that gives you a clear picture of "
                "your loan terms and estimated costs. Here's what to pay attention to:",
                "<ul>"
                "<li><strong>Page 1 — Loan Terms:</strong> Your loan amount, interest rate, and monthly payment.</li>"
                "<li><strong>Page 2 — Closing Costs:</strong> All fees broken down by category. "
                "These are estimates — final numbers will be on your Closing Disclosure.</li>"
                "<li><strong>Page 3 — Comparisons:</strong> APR, total interest, and how much you'll pay over 5 years.</li>"
                "</ul>",
                "<strong>Important:</strong> Please review and acknowledge receipt within 3 business days. "
                "You can do so through your borrower portal or by replying to this email.",
                "Have questions? I'm happy to walk through any line item with you on a quick call.",
                f'<p><a href="{{{{portal_link}}}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                f'text-decoration:none;border-radius:4px;">View & Acknowledge Your LE</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your Loan Estimate has been sent to {{email}}. Please review it carefully.",
            "Key items to check:\n"
            "- Page 1: Loan amount, rate, monthly payment\n"
            "- Page 2: Estimated closing costs\n"
            "- Page 3: APR and 5-year comparison",
            "IMPORTANT: Please acknowledge receipt within 3 business days.",
            "View and acknowledge through your portal: {{portal_link}}",
            "Questions? Call me at {{loan_officer_phone}}.",
        ]),
        "merge_fields": ["{{first_name}}", "{{email}}", "{{loan_officer_name}}", "{{company_name}}", "{{portal_link}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["loan_estimate", "disclosure", "trid", "application"],
    },

    {
        "title": "Rate Lock Confirmation",
        "description": "Confirms the rate lock and explains the lock period protections.",
        "content_type": "email",
        "category": "application",
        "subject_line": "Confirmed: your rate is locked at {{rate}}, {{first_name}}",
        "body_html": _html(
            "Rate Lock Confirmed",
            "Your rate is locked — here's what that means",
            [
                "Great news, {{first_name}}! Your interest rate has been locked at "
                "<strong>{{rate}}</strong> for your {{loan_type}} loan.",
                "Here's what your rate lock means:",
                "<ul>"
                "<li><strong>Protection from rate increases:</strong> Even if market rates go up before your closing date, your rate stays at {{rate}}.</li>"
                "<li><strong>Lock expiration:</strong> Your rate lock is valid through your expected closing date. If closing is delayed beyond this date, we may need to discuss extension options.</li>"
                "<li><strong>What to avoid:</strong> Do not make any major financial changes (new credit, large purchases, job change) that could affect your loan approval before closing.</li>"
                "</ul>",
                "Your target closing date is <strong>{{closing_date}}</strong>. I'll be in touch as we move toward that milestone!",
                "Questions about your lock? Reply here or call me at {{loan_officer_phone}}.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your rate is locked at {{rate}} for your {{loan_type}} loan.",
            "What this means:\n"
            "- Your rate is protected from market increases.\n"
            "- Your lock is valid through your target closing date of {{closing_date}}.\n"
            "- Avoid major financial changes until after closing.",
            "Questions? Call me at {{loan_officer_phone}}.",
        ]),
        "merge_fields": ["{{first_name}}", "{{rate}}", "{{loan_type}}", "{{closing_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["rate_lock", "confirmation", "application"],
    },

    {
        "title": "Conditional Approval — Conditions Explained",
        "description": "Explains conditional approval status and what conditions mean.",
        "content_type": "email",
        "category": "application",
        "subject_line": "{{first_name}}, great progress — conditional approval received",
        "body_html": _html(
            "Conditional Approval",
            "Congratulations — your loan received a conditional approval!",
            [
                "This is a major milestone, {{first_name}}! Your loan has received a "
                "<strong>conditional approval</strong> from underwriting.",
                "What does \"conditional\" mean? It means the underwriter has reviewed your file "
                "and is prepared to approve the loan once a few outstanding items are satisfied. "
                "This is completely normal — most loans receive conditional approvals.",
                "Your processor will be reaching out shortly with the specific list of conditions "
                "required. Common conditions include:",
                "<ul>"
                "<li>Updated pay stubs or bank statements</li>"
                "<li>A letter of explanation for a specific item in your credit history</li>"
                "<li>Additional documentation for a gift fund</li>"
                "<li>Homeowner's insurance binder</li>"
                "</ul>",
                "Once conditions are cleared, we move to <strong>Clear to Close</strong> — and that's "
                "when we schedule your closing date!",
                "I'll be monitoring your file closely. Questions? Call me at {{loan_officer_phone}}.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Big news — you received a CONDITIONAL APPROVAL! This is a major milestone.",
            "Conditional approval means underwriting is ready to approve once a few items are cleared. "
            "This is very normal — your processor will send the specific list shortly.",
            "Once conditions are cleared, you're Clear to Close!",
            "Questions? Call me at {{loan_officer_phone}}.",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["conditional_approval", "underwriting", "application"],
    },

    # =========================================================================
    # PROCESSING / UNDERWRITING UPDATE EMAILS (5)
    # =========================================================================

    {
        "title": "File Submitted to Underwriting",
        "description": "Notifies borrower that file has been submitted to underwriting.",
        "content_type": "email",
        "category": "processing",
        "subject_line": "Update: your file has been submitted to underwriting, {{first_name}}",
        "body_html": _html(
            "Submitted to UW",
            "Your file is with underwriting — here's what that means",
            [
                "Your loan file has been submitted to the underwriting team for review. "
                "This is an important milestone — it means all your documents have been "
                "collected and your file is complete!",
                "What happens in underwriting?",
                "<ul>"
                "<li>A licensed underwriter reviews your income, assets, credit, and the property appraisal.</li>"
                "<li>They verify that your loan meets all program guidelines.</li>"
                "<li>The typical turnaround is <strong>3–7 business days</strong>.</li>"
                "</ul>",
                "During this time, please:",
                "<ul>"
                "<li>Respond promptly to any requests from my team for additional information.</li>"
                "<li>Avoid major financial changes (new accounts, large deposits, job changes).</li>"
                "<li>Keep your phone and email accessible in case we need to reach you quickly.</li>"
                "</ul>",
                "I'll update you as soon as I have the underwriter's decision. Hang tight — you're almost there!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your file has been submitted to underwriting — this is a big milestone!",
            "Underwriting typically takes 3-7 business days. During this time:\n"
            "- Respond quickly to any requests from my team.\n"
            "- Avoid major financial changes.\n"
            "- Keep your phone accessible.",
            "I'll update you as soon as we have the underwriter's decision. Almost there!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["underwriting", "status_update", "processing"],
    },

    {
        "title": "Appraisal Ordered — What to Expect",
        "description": "Explains the appraisal process and sets expectations for the borrower.",
        "content_type": "email",
        "category": "processing",
        "subject_line": "{{first_name}}, your home appraisal has been ordered",
        "body_html": _html(
            "Appraisal Ordered",
            "Your appraisal is ordered — here's what to expect",
            [
                "Good news — your home appraisal has been ordered! This is a required step "
                "that confirms the property's market value for your lender.",
                "Here's what happens next:",
                "<ol>"
                "<li><strong>Appraiser contact (1–3 days):</strong> A licensed appraiser will contact the listing agent or seller to schedule the inspection visit.</li>"
                "<li><strong>On-site inspection (30–60 minutes):</strong> The appraiser visits the property to assess its condition and features.</li>"
                "<li><strong>Report delivery (3–7 days after inspection):</strong> The appraisal report is submitted to your lender for review.</li>"
                "</ol>",
                "The appraisal is paid for by you as part of your closing costs. "
                "You have the right to receive a copy of the appraisal at least 3 business days "
                "before your closing date.",
                "I'll let you know as soon as the appraisal results are in!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your appraisal is ordered!",
            "What happens next:\n"
            "1. Appraiser contacts listing agent to schedule (1-3 days).\n"
            "2. On-site inspection (30-60 min).\n"
            "3. Report delivered to lender (3-7 days after inspection).",
            "You'll receive a copy of the appraisal at least 3 business days before closing.",
            "I'll update you as soon as the results are in!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["appraisal", "processing", "status_update"],
    },

    {
        "title": "Processing Status — Weekly Update",
        "description": "Keep borrowers informed during the processing stage with a friendly weekly update.",
        "content_type": "email",
        "category": "processing",
        "subject_line": "{{first_name}}, a quick update on your loan file",
        "body_html": _html(
            "Weekly Update",
            "Your loan update — {{current_month}}",
            [
                "Hi {{first_name}} — just a quick update to keep you in the loop on your loan file.",
                "Your file is actively moving through our process. Here's a general status overview:",
                "<ul>"
                "<li>All documents received: &#9989;</li>"
                "<li>File submitted to underwriting: In progress</li>"
                "<li>Target closing date: <strong>{{closing_date}}</strong></li>"
                "</ul>",
                "No action is needed from you at this time. I'll reach out right away if anything changes "
                "or if we need additional information.",
                "In the meantime, here are a few reminders as you approach closing:",
                "<ul>"
                "<li>Do not make large purchases on credit (furniture, appliances, car).</li>"
                "<li>Do not open new credit cards or loans.</li>"
                "<li>Notify me immediately if your employment situation changes.</li>"
                "</ul>",
                "You're in great hands — we'll get you to the finish line. Any questions, just reply!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Quick update on your loan file:",
            "- Documents received: Complete\n"
            "- File status: Active in processing\n"
            "- Target closing: {{closing_date}}",
            "No action needed right now. Remember:\n"
            "- No large purchases or new credit before closing.\n"
            "- Contact me immediately if your employment changes.",
            "You're in great hands! Reply with any questions.",
        ]),
        "merge_fields": ["{{first_name}}", "{{closing_date}}", "{{current_month}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["status_update", "weekly", "processing"],
    },

    {
        "title": "Title Search Update",
        "description": "Explains the title search process and what issues (if any) were found.",
        "content_type": "email",
        "category": "processing",
        "subject_line": "{{first_name}}, an update on the title search for your property",
        "body_html": _html(
            "Title Search Update",
            "Title search update on your property",
            [
                "As part of your mortgage process, a title search has been ordered on "
                "your property at <strong>{{property_address}}</strong>.",
                "What is a title search? A title company researches the property's history "
                "to confirm there are no outstanding liens, judgments, or ownership disputes "
                "that could affect your purchase.",
                "You'll also be purchasing <strong>title insurance</strong> as part of your "
                "closing costs. This protects you (and your lender) from any claims "
                "that may arise from events before your purchase.",
                "I'll update you once the title report is back. In most cases, everything "
                "comes back clean and we move forward without issue.",
                "Questions about title? Happy to explain — it's one of the more confusing "
                "parts of the process for first-time buyers.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "A title search has been ordered on {{property_address}}.",
            "The title company will confirm there are no liens or ownership disputes on the property. "
            "You'll also receive title insurance at closing for your protection.",
            "I'll update you as soon as the report is back!",
        ]),
        "merge_fields": ["{{first_name}}", "{{property_address}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["title", "processing", "educational"],
    },

    {
        "title": "Homeowner's Insurance Reminder",
        "description": "Reminds borrower to obtain homeowner's insurance before closing.",
        "content_type": "email",
        "category": "processing",
        "subject_line": "Action needed: homeowner's insurance required before closing, {{first_name}}",
        "body_html": _html(
            "Insurance Reminder",
            "{{first_name}}, please arrange homeowner's insurance before closing",
            [
                "As we get closer to your closing date, there's an important item you need to "
                "take care of: <strong>homeowner's insurance</strong>.",
                "Your lender requires proof of a homeowner's insurance policy that is active "
                "as of your closing date. Here's what to do:",
                "<ol>"
                "<li>Contact your insurance agent (or shop for quotes at a comparison site).</li>"
                "<li>Request a policy for your new property at {{property_address}}.</li>"
                "<li>Ask for a <strong>declarations page (dec page)</strong> and <strong>mortgagee clause</strong> naming {{company_name}} as the lender.</li>"
                "<li>Send the dec page and mortgagee clause to me at {{loan_officer_email}}.</li>"
                "</ol>",
                "Please have this in no later than <strong>1 week before your closing date of {{closing_date}}</strong>.",
                "Need insurance recommendations? I'm happy to share local agents I've worked with.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Action needed: you must obtain homeowner's insurance before closing.",
            "Steps:\n"
            "1. Contact your insurance agent.\n"
            "2. Request coverage for {{property_address}}.\n"
            "3. Get a declarations page naming {{company_name}} as the mortgagee.\n"
            "4. Send it to me at {{loan_officer_email}}.",
            "Please have this submitted at least 1 week before {{closing_date}}.",
        ]),
        "merge_fields": ["{{first_name}}", "{{property_address}}", "{{closing_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["insurance", "action_required", "processing"],
    },

    # =========================================================================
    # CLOSING STAGE EMAILS (5)
    # =========================================================================

    {
        "title": "Clear to Close — Congratulations!",
        "description": "Announces CTC status. Celebratory tone. Outlines closing day logistics.",
        "content_type": "email",
        "category": "closing",
        "subject_line": "YOU'RE CLEAR TO CLOSE, {{first_name}}! &#127881;",
        "body_html": _html(
            "Clear to Close",
            "&#127881; You're Clear to Close, {{first_name}}!",
            [
                "This is the moment you've been working toward — your loan has received "
                "<strong>Clear to Close (CTC)</strong>! This means underwriting has approved "
                "your loan with no remaining conditions.",
                "Here's what happens between now and closing day:",
                "<ol>"
                "<li><strong>Closing Disclosure (CD):</strong> You'll receive your final CD within the next 1–2 business days. "
                "Federal law requires you have it at least 3 business days before closing.</li>"
                "<li><strong>Final walkthrough:</strong> Schedule a final walkthrough of your new home before closing.</li>"
                "<li><strong>Closing funds:</strong> You'll need to bring your down payment and closing costs via certified check or wire transfer (details in your CD).</li>"
                "<li><strong>Closing Day:</strong> Bring your government-issued photo ID to the closing table.</li>"
                "</ol>",
                "Your closing date is <strong>{{closing_date}}</strong>. I'll be in touch with the exact "
                "time and location.",
                "This is such an exciting milestone — I'm so proud of you for getting here!",
            ],
        ),
        "body_text": _text([
            "{{first_name}}, YOU'RE CLEAR TO CLOSE!",
            "Underwriting has given full approval with no remaining conditions!",
            "What's next:\n"
            "1. Your Closing Disclosure arrives within 1-2 business days.\n"
            "2. Schedule a final walkthrough of your new home.\n"
            "3. Arrange certified funds for closing (down payment + closing costs).\n"
            "4. Bring your photo ID to the closing table.",
            "Your closing date is {{closing_date}}. I'll confirm the time and location soon.",
            "Congratulations — you've earned this!",
        ]),
        "merge_fields": ["{{first_name}}", "{{closing_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["ctc", "clear_to_close", "celebratory", "closing"],
    },

    {
        "title": "Closing Disclosure — Review Guide",
        "description": "Helps borrower understand the Closing Disclosure before signing.",
        "content_type": "email",
        "category": "closing",
        "subject_line": "{{first_name}}, your Closing Disclosure is ready — here's what to review",
        "body_html": _html(
            "Closing Disclosure Guide",
            "Your Closing Disclosure is here — let me help you review it",
            [
                "Your official Closing Disclosure (CD) has been sent to {{email}}. "
                "You must receive this at least 3 business days before closing — "
                "this is a federal requirement designed to protect you.",
                "Here's what to review carefully:",
                "<ul>"
                "<li><strong>Loan Terms (Page 1):</strong> Confirm your loan amount, interest rate, and monthly payment match what you agreed to.</li>"
                "<li><strong>Projected Payments (Page 1):</strong> Includes principal, interest, taxes, and insurance.</li>"
                "<li><strong>Closing Costs (Page 2):</strong> Compare to your Loan Estimate — zero-tolerance fees cannot increase, 10% tolerance fees can increase by up to 10%.</li>"
                "<li><strong>Cash to Close (Page 3):</strong> The exact amount you need to bring on closing day.</li>"
                "</ul>",
                "Please compare this carefully to your Loan Estimate. If anything looks different "
                "than expected, contact me immediately — we want to make sure everything is correct "
                "before closing day.",
                "Your closing is scheduled for <strong>{{closing_date}}</strong>. So excited to get you "
                "into your new home!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your Closing Disclosure has been sent to {{email}}. Review it carefully!",
            "Key items to check:\n"
            "- Page 1: Loan amount, rate, monthly payment (should match your LE)\n"
            "- Page 2: Closing costs breakdown\n"
            "- Page 3: Exact cash to close",
            "Your closing is {{closing_date}}. Contact me immediately if anything looks different "
            "from your Loan Estimate.",
        ]),
        "merge_fields": ["{{first_name}}", "{{email}}", "{{closing_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["closing_disclosure", "cd", "trid", "closing"],
    },

    {
        "title": "Closing Day Checklist",
        "description": "Day-before email with everything the borrower needs to bring to the closing table.",
        "content_type": "email",
        "category": "closing",
        "subject_line": "{{first_name}}, tomorrow is closing day — here's your checklist",
        "body_html": _html(
            "Closing Day Checklist",
            "Tomorrow is the big day — your closing day checklist",
            [
                "You're almost there, {{first_name}}! Your closing is scheduled for <strong>{{closing_date}}</strong>. "
                "Here's everything you need:",
                "<h3 style='color:#1a3c6e;'>Bring with you:</h3>"
                "<ul>"
                "<li>&#9989; <strong>Government-issued photo ID</strong> (driver's license or passport)</li>"
                "<li>&#9989; <strong>Certified check or wire transfer confirmation</strong> for your cash to close amount</li>"
                "<li>&#9989; <strong>Checkbook</strong> (some closing items may require a personal check)</li>"
                "<li>&#9989; If you have a co-borrower — <strong>they must also be present</strong></li>"
                "</ul>",
                "<h3 style='color:#1a3c6e;'>What to expect:</h3>"
                "<ul>"
                "<li>Closing typically takes 60–90 minutes.</li>"
                "<li>You'll sign a significant amount of paperwork — your settlement agent will walk you through each document.</li>"
                "<li>Keys are typically handed over at the end of signing.</li>"
                "</ul>",
                "If you have any last-minute questions, call me directly at {{loan_officer_phone}}. "
                "I'll be monitoring my phone today and tomorrow morning.",
                "<strong>Congratulations — you're about to be a homeowner!</strong>",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Tomorrow is closing day! Here's your checklist:",
            "BRING:\n"
            "- Government-issued photo ID\n"
            "- Certified check or wire confirmation for cash to close\n"
            "- Checkbook\n"
            "- Co-borrower (if applicable)",
            "WHAT TO EXPECT:\n"
            "- Closing takes about 60-90 minutes\n"
            "- Lots of paperwork (your settlement agent will guide you)\n"
            "- Keys at the end!",
            "Questions? Call me directly: {{loan_officer_phone}}",
            "CONGRATULATIONS — you're about to be a homeowner!",
        ]),
        "merge_fields": ["{{first_name}}", "{{closing_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["closing_day", "checklist", "closing"],
    },

    {
        "title": "Congratulations — You're a Homeowner!",
        "description": "Post-closing celebration email. Warm, personal, sets up for long-term relationship.",
        "content_type": "email",
        "category": "closing",
        "subject_line": "Congratulations, {{first_name}} — you're officially a homeowner! &#127968;",
        "body_html": _html(
            "Congratulations Homeowner",
            "&#127968; Welcome home, {{first_name}}!",
            [
                "You did it! Congratulations on closing on your new home at "
                "<strong>{{property_address}}</strong>. "
                "This is an incredible achievement and I'm so honored to have been part of your journey.",
                "A few important things to remember as you settle in:",
                "<ul>"
                "<li><strong>Your first mortgage payment</strong> is typically due on the 1st of the month, "
                "30–60 days after closing. You'll receive payment instructions from your loan servicer.</li>"
                "<li><strong>Homestead exemption:</strong> Check with your county about filing for a homestead exemption to reduce your property tax bill.</li>"
                "<li><strong>Keep records:</strong> Save all your closing documents in a safe place. You'll need them at tax time.</li>"
                "<li><strong>Change your address</strong> with USPS, your bank, employer, and the DMV.</li>"
                "</ul>",
                "It's been a true pleasure working with you. Please don't hesitate to reach out "
                "with any questions — now or in the future. And if anyone you know is thinking "
                "about buying or refinancing, I'd be grateful for the referral.",
                "Enjoy your new home — you've earned it!",
            ],
        ),
        "body_text": _text([
            "{{first_name}}, CONGRATULATIONS!",
            "You're officially a homeowner! Welcome home to {{property_address}}.",
            "A few reminders:\n"
            "- First mortgage payment: due 30-60 days after closing.\n"
            "- File for homestead exemption with your county.\n"
            "- Save your closing documents for tax time.\n"
            "- Update your address everywhere.",
            "It's been a pleasure working with you. If anyone you know is buying or refinancing, "
            "I'd love an introduction!",
            "Enjoy every moment in your new home!",
        ]),
        "merge_fields": ["{{first_name}}", "{{property_address}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["congratulations", "funded", "celebration", "closing"],
    },

    {
        "title": "Moving Tips & New Homeowner Guide",
        "description": "Helpful resource email for new homeowners. Builds goodwill and long-term relationship.",
        "content_type": "email",
        "category": "closing",
        "subject_line": "{{first_name}}, your new homeowner survival guide",
        "body_html": _html(
            "New Homeowner Guide",
            "Your new homeowner survival guide",
            [
                "Congratulations again, {{first_name}}! Now that you have the keys, "
                "here's a quick guide to help you get settled and protect your investment:",
                "<h3 style='color:#1a3c6e;'>First 30 Days</h3>"
                "<ul>"
                "<li>Change the locks — you never know who has a key copy.</li>"
                "<li>Locate your main water shutoff valve and electrical panel.</li>"
                "<li>Test smoke and carbon monoxide detectors.</li>"
                "<li>Set up utilities in your name (if not already done).</li>"
                "<li>Review your homeowner's insurance policy thoroughly.</li>"
                "</ul>",
                "<h3 style='color:#1a3c6e;'>Ongoing Maintenance</h3>"
                "<ul>"
                "<li>Change HVAC filters every 1–3 months.</li>"
                "<li>Clean gutters twice a year (spring and fall).</li>"
                "<li>Have your HVAC serviced annually.</li>"
                "<li>Check your roof after major storms.</li>"
                "</ul>",
                "<h3 style='color:#1a3c6e;'>Financial Housekeeping</h3>"
                "<ul>"
                "<li>Set up autopay for your mortgage — never miss a payment.</li>"
                "<li>Keep an emergency fund of 1–3% of your home's value for repairs.</li>"
                "<li>Save your HUD-1/closing disclosure for tax season.</li>"
                "</ul>",
                "I'm always here if you need anything. Enjoy your new home!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Now that you have the keys, here's your new homeowner guide:",
            "FIRST 30 DAYS:\n"
            "- Change the locks\n"
            "- Locate water shutoff and electrical panel\n"
            "- Test smoke/CO detectors\n"
            "- Set up utilities",
            "ONGOING:\n"
            "- Change HVAC filters every 1-3 months\n"
            "- Clean gutters spring and fall\n"
            "- Have HVAC serviced annually",
            "FINANCIAL:\n"
            "- Set up autopay for your mortgage\n"
            "- Keep a 1-3% repair emergency fund\n"
            "- Save closing documents for tax time",
            "Enjoy your new home!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["new_homeowner", "tips", "moving", "closing"],
    },

    # =========================================================================
    # POST-CLOSE NURTURE EMAILS (10)
    # =========================================================================

    {
        "title": "1-Month Check-In — How's the New Home?",
        "description": "Friendly 1-month check-in. Keeps the relationship warm post-close.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, how's the new home treating you? (1 month in!)",
        "body_html": _html(
            "1-Month Check-In",
            "One month in — how's the new home, {{first_name}}?",
            [
                "Can you believe it's already been a month since you closed on your home? "
                "Time flies when you're getting settled in!",
                "I just wanted to reach out and see how everything is going. "
                "Have you gotten comfortable in the new space? Any surprises — good or not so good?",
                "A couple of reminders:",
                "<ul>"
                "<li>Your first mortgage payment should be coming up if you haven't made it already.</li>"
                "<li>Don't forget to look into your homestead exemption — it can save you hundreds on property taxes.</li>"
                "</ul>",
                "If you have any questions about your loan, your payment, or anything else, "
                "I'm always just a call or email away.",
                "And if any friends or family are thinking about buying a home or refinancing, "
                "I'd love to help them the same way I helped you!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "One month in — how's the new home treating you?",
            "Reminders:\n"
            "- First mortgage payment should be coming up.\n"
            "- Look into homestead exemption for property tax savings.",
            "Any questions, I'm always here. And if friends or family need mortgage help, "
            "please keep me in mind!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["1_month", "check_in", "post_close"],
    },

    {
        "title": "3-Month Anniversary — Home Update",
        "description": "3-month nurture email. Mentions equity building and future goals.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, 3 months as a homeowner — you're building equity!",
        "body_html": _html(
            "3-Month Anniversary",
            "3 months in — you're already building equity, {{first_name}}",
            [
                "Congratulations on 3 months of homeownership! Every mortgage payment you make "
                "is building equity in your most valuable asset.",
                "A quick equity snapshot:",
                "<ul>"
                "<li>Your original loan balance: <strong>{{loan_amount}}</strong></li>"
                "<li>Three months of payments have already started reducing that balance.</li>"
                "<li>As your equity grows, so do your financial options — from a HELOC to future refinance opportunities.</li>"
                "</ul>",
                "I'm always monitoring the market on your behalf. If rates drop significantly "
                "below your current rate of {{rate}}, I'll reach out proactively with a "
                "refinance analysis.",
                "How's the home treating you? Any updates or improvements you're planning? "
                "I'd love to hear — reply and let me know!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Congratulations on 3 months of homeownership! You're already building equity.",
            "Your original loan: {{loan_amount}} at {{rate}}.",
            "As your equity grows, so do your options — HELOCs, refinance opportunities, and more.",
            "I'm watching rates for you. If they drop significantly, I'll reach out.",
            "How's everything going? Reply and let me know!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_amount}}", "{{rate}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["3_month", "equity", "post_close"],
    },

    {
        "title": "6-Month Rate & Market Update",
        "description": "Half-year check-in with a market update. Keeps LO top of mind.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, your 6-month mortgage & market update",
        "body_html": _html(
            "6-Month Update",
            "Your 6-month mortgage and market update",
            [
                "It's been 6 months since you closed — and a lot has happened in the mortgage "
                "market since then! I wanted to share a quick update.",
                "Current market conditions:",
                "<ul>"
                "<li>Rates have been <em>[moving/stabilizing]</em> recently — I'll keep monitoring on your behalf.</li>"
                "<li>Home values in many markets have continued to appreciate, which means your equity position may be stronger than you think.</li>"
                "</ul>",
                "Your current loan snapshot:",
                "<ul>"
                "<li>Original rate: <strong>{{rate}}</strong></li>"
                "<li>Original balance: <strong>{{loan_amount}}</strong></li>"
                "</ul>",
                "If rates have dropped meaningfully since you closed, it might make sense to run "
                "a refinance analysis. A general rule of thumb: if you can reduce your rate by "
                "0.5% or more and plan to stay in the home for 2+ years, a refinance often makes sense.",
                "Interested in a free refinance analysis? Just reply to this email — no obligation.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "It's been 6 months since you closed — here's a quick market update.",
            "Your loan: {{loan_amount}} at {{rate}}.",
            "If rates have dropped 0.5%+ since you closed and you plan to stay 2+ years, "
            "a refinance may make financial sense.",
            "Want a free refinance analysis? Just reply — no obligation.",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_amount}}", "{{rate}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["6_month", "market_update", "post_close"],
    },

    {
        "title": "1-Year Home Anniversary",
        "description": "Celebrates the 1-year home anniversary. Warm, personal, excellent referral opportunity.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "Happy 1-year home anniversary, {{first_name}}! &#127968;",
        "body_html": _html(
            "1-Year Anniversary",
            "&#127968; Happy 1-year home anniversary, {{first_name}}!",
            [
                "One year ago today, you got the keys to your home at "
                "<strong>{{property_address}}</strong>. "
                "What an incredible milestone!",
                "A year of memories, improvements, and equity-building — it all adds up.",
                "Here's a quick look at where you stand:",
                "<ul>"
                "<li>12 months of payments have reduced your loan balance.</li>"
                "<li>Home appreciation in most markets has added to your net worth.</li>"
                "<li>You've earned the right to call yourself a homeowner for a full year — that's worth celebrating!</li>"
                "</ul>",
                "As always, I'm here for you whenever you have mortgage questions — whether "
                "it's a refinance analysis, a second home, an investment property, or "
                "helping a friend or family member buy their first home.",
                "Here's to many more years in your home!",
            ],
        ),
        "body_text": _text([
            "{{first_name}}, HAPPY 1-YEAR HOME ANNIVERSARY!",
            "One year ago you got the keys to {{property_address}}. What a milestone!",
            "You've built equity, made memories, and proven that homeownership was the right call.",
            "I'm always here for your next mortgage need — refinance, investment property, "
            "or helping someone you know. Congrats on a full year!",
        ]),
        "merge_fields": ["{{first_name}}", "{{property_address}}", "{{anniversary_date}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["anniversary", "1_year", "celebration", "post_close"],
    },

    {
        "title": "Birthday Wishes",
        "description": "Simple, warm birthday email. Non-salesy — pure relationship building.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "Happy birthday, {{first_name}}! &#127881;",
        "body_html": _html(
            "Birthday Email",
            "Happy birthday, {{first_name}}!",
            [
                "Just wanted to take a moment to wish you a very happy birthday!",
                "I hope your {{birthday_month}} is filled with joy, great memories, "
                "and of course — time spent in the home you love.",
                "It's been a pleasure being part of your homeownership journey. "
                "I hope this birthday brings everything you're wishing for.",
                "Warmly,",
            ],
        ),
        "body_text": _text([
            "Happy birthday, {{first_name}}!",
            "Wishing you a wonderful {{birthday_month}} filled with joy and great memories.",
            "It's been a pleasure being part of your homeownership journey.",
            "Here's to a fantastic birthday!",
        ]),
        "merge_fields": ["{{first_name}}", "{{birthday_month}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["birthday", "relationship", "personal", "post_close"],
    },

    {
        "title": "Holiday Greetings",
        "description": "Warm, non-denominational holiday greeting. Sent in late December.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "Happy holidays from {{loan_officer_name}} & {{company_name}}",
        "body_html": _html(
            "Holiday Greeting",
            "Season's greetings, {{first_name}}!",
            [
                "As we head into the holiday season, I wanted to take a moment to reach out "
                "and wish you and your family a wonderful time of year.",
                "The holidays are extra special when you have a home to celebrate in — "
                "and I hope yours is full of warmth, laughter, and great memories.",
                "It has been a true privilege helping clients like you achieve homeownership "
                "this year. Thank you for trusting me with such an important milestone.",
                "Wishing you a joyful holiday season and a prosperous New Year!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Wishing you and your family a wonderful holiday season!",
            "There's something special about celebrating the holidays in your own home, "
            "and I hope yours is filled with warmth and great memories.",
            "Thank you for trusting me this year. Happy holidays and Happy New Year!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["holiday", "seasonal", "relationship", "post_close"],
    },

    {
        "title": "Refinance Check-In — Rates Worth Watching",
        "description": "Post-close refinance opportunity email for clients who closed 6-18 months ago.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, are rates favorable enough to refinance?",
        "body_html": _html(
            "Refi Check-In",
            "Could now be the right time to refinance?",
            [
                "Hi {{first_name}} — I'm reaching out because I always keep an eye on "
                "rate movements for my past clients, and I wanted to share a quick analysis "
                "based on your situation.",
                "Your current loan:",
                "<ul>"
                "<li>Rate: <strong>{{current_rate}}</strong></li>"
                "<li>Balance: <strong>{{loan_amount}}</strong></li>"
                "</ul>",
                "If current rates are meaningfully lower, refinancing could:",
                "<ul>"
                "<li>Reduce your monthly payment by <strong>{{monthly_savings}}</strong></li>"
                "<li>Save you significantly over the remaining life of your loan</li>"
                "<li>Give you access to equity for improvements, debt consolidation, or other goals</li>"
                "</ul>",
                "This is a no-cost, no-obligation analysis. If the numbers don't make sense for your situation, "
                "I'll tell you honestly. If they do, we can get started immediately.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Get My Free Refi Analysis</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "I'm keeping an eye on rates for you — wanted to check in.",
            "Your current loan: {{current_rate}} on {{loan_amount}}.",
            "If rates have dropped, refinancing could lower your payment by {{monthly_savings}} or more.",
            "This analysis is free, no-obligation. If the numbers don't work, I'll tell you.",
            "Interested? Let's talk: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{current_rate}}", "{{loan_amount}}", "{{monthly_savings}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["refinance", "post_close", "rate_check"],
    },

    {
        "title": "Referral Request — Who Do You Know?",
        "description": "Asks for referrals from happy past clients. Warm, non-pressuring tone.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, could you help a friend get a great mortgage?",
        "body_html": _html(
            "Referral Request",
            "The greatest compliment is a referral",
            [
                "Hi {{first_name}} — I hope you're loving your home!",
                "I wanted to reach out with a quick ask. The majority of my business comes "
                "from referrals from wonderful clients like you — and it means the world to me.",
                "If you know anyone who is:",
                "<ul>"
                "<li>Thinking about buying their first home</li>"
                "<li>Looking to upsize, downsize, or relocate</li>"
                "<li>Interested in exploring a refinance</li>"
                "<li>Curious about investment properties</li>"
                "</ul>",
                "I would be honored to help them the same way I helped you. "
                "The service is free to explore — no obligation until they decide to move forward.",
                "Simply forward this email to them or share my contact info below. "
                "I'll take great care of them!",
                "Thank you in advance — it genuinely makes a difference.",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Hope you're loving your home!",
            "A quick ask: if you know anyone thinking about buying, refinancing, or exploring "
            "investment properties, I'd love an introduction.",
            "I'll give them the same level of service I gave you — no obligation, just honest guidance.",
            "Simply forward this email or share my number: {{loan_officer_phone}}",
            "Thank you so much — referrals are the highest compliment!",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["referral", "post_close", "relationship"],
    },

    {
        "title": "Market Update — What's Happening in Real Estate",
        "description": "Quarterly market update email. Positions LO as a trusted resource.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, your {{current_month}} real estate & mortgage market update",
        "body_html": _html(
            "Market Update",
            "Your {{current_month}} mortgage & real estate market update",
            [
                "Hi {{first_name}} — here's your quarterly look at what's happening in "
                "the mortgage market and how it might affect your home.",
                "<h3 style='color:#1a3c6e;'>Mortgage Rates</h3>"
                "<p>Rates have been <em>[trending/stabilizing/declining]</em> over the past quarter. "
                "If you're a homeowner, this is worth watching — a rate reduction of 0.5%+ "
                "can often justify a refinance, especially if you plan to stay in your home "
                "for several more years.</p>",
                "<h3 style='color:#1a3c6e;'>Home Values</h3>"
                "<p>Home values in most markets have seen continued appreciation over the past 12 months. "
                "This means your equity position may be stronger than you realize. Growing equity "
                "opens doors to HELOCs, cash-out refinances, and investment property purchases.</p>",
                "<h3 style='color:#1a3c6e;'>What This Means for You</h3>"
                "<p>Even if you're not planning any immediate moves, it's worth knowing where you stand. "
                "I offer free annual mortgage reviews — 15 minutes, no cost, no obligation. "
                "Just a chance to make sure your current mortgage still makes sense for your goals.</p>",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Schedule My Annual Review</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your {{current_month}} mortgage and real estate market update:",
            "RATES: Rates have been moving — a 0.5%+ reduction can often justify a refinance.",
            "HOME VALUES: Most markets have seen continued appreciation — your equity may be "
            "stronger than you think.",
            "MY RECOMMENDATION: Let's do a free 15-minute annual mortgage review to make sure "
            "your loan still makes sense for your goals.",
            "Schedule here: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{current_month}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["market_update", "quarterly", "post_close"],
    },

    {
        "title": "Tax Season Reminder — Mortgage Deduction",
        "description": "Annual tax season reminder about mortgage interest deduction. Valuable to homeowners.",
        "content_type": "email",
        "category": "post_close",
        "subject_line": "{{first_name}}, don't forget this mortgage tax tip",
        "body_html": _html(
            "Tax Season Reminder",
            "Tax season reminder — your mortgage may have tax benefits",
            [
                "Tax season is here, and as a homeowner, you have potential deductions "
                "that renters don't get. Here's a quick reminder:",
                "<ul>"
                "<li><strong>Mortgage Interest Deduction:</strong> You can generally deduct the mortgage interest you paid in {{current_year}} on your primary residence. Check your Form 1098, which your loan servicer will send by January 31st.</li>"
                "<li><strong>Property Taxes:</strong> You may also deduct up to $10,000 in state and local taxes (SALT), which includes property taxes.</li>"
                "<li><strong>Mortgage Insurance Premiums:</strong> If applicable to your loan, MIP/PMI premiums may be deductible. Consult your tax advisor.</li>"
                "<li><strong>Points Paid:</strong> If you paid discount points at closing, they are often deductible in the year paid on a purchase.</li>"
                "</ul>",
                "<strong>Important:</strong> I'm a mortgage professional, not a tax advisor. "
                "Please consult a qualified tax professional (CPA or enrolled agent) for "
                "advice specific to your situation.",
                "Wishing you a smooth tax season!",
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Tax season reminder — as a homeowner, you may have deductions to claim:",
            "- Mortgage interest (see your Form 1098 from your servicer)\n"
            "- Property taxes (up to $10,000 SALT deduction)\n"
            "- Mortgage insurance premiums (if applicable)\n"
            "- Discount points paid at closing",
            "Note: I'm a mortgage professional, not a tax advisor. Please consult a CPA.",
            "Have a great tax season!",
        ]),
        "merge_fields": ["{{first_name}}", "{{current_year}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["tax", "annual", "educational", "post_close"],
    },

    # =========================================================================
    # SMS TEMPLATES (5)
    # =========================================================================

    {
        "title": "Appointment Reminder SMS",
        "description": "Day-before appointment reminder via SMS.",
        "content_type": "sms",
        "category": "new_lead",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "Hi {{first_name}}, this is {{loan_officer_name}} at {{company_name}}! "
            "Just a reminder about our call tomorrow. Looking forward to chatting about your "
            "home financing options."
        ),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}"],
        "tags": ["appointment", "reminder", "sms"],
    },

    {
        "title": "Document Request SMS",
        "description": "Quick SMS nudge when documents are outstanding.",
        "content_type": "sms",
        "category": "application",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "Hi {{first_name}}, {{loan_officer_name}} here. Quick reminder: we still need "
            "a few documents to keep your loan on track. Please check your email or upload "
            "here: {{portal_link}} —"
        ),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{portal_link}}"],
        "tags": ["documents", "action_required", "sms"],
    },

    {
        "title": "Rate Alert SMS",
        "description": "Urgent rate drop notification via SMS.",
        "content_type": "sms",
        "category": "new_lead",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "Hi {{first_name}}! {{loan_officer_name}} at {{company_name}}. Rates dropped "
            "significantly today — this could be a great time to lock! Can we talk? "
            "Call/text me at {{loan_officer_phone}}."
        ),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}"],
        "tags": ["rate_alert", "urgent", "sms"],
    },

    {
        "title": "Closing Congratulations SMS",
        "description": "Quick celebratory SMS on closing day.",
        "content_type": "sms",
        "category": "closing",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "Congratulations {{first_name}}!! You're officially a homeowner! It was a "
            "pleasure working with you. Enjoy your new home at {{property_address}}! "
            "— {{loan_officer_name}}, {{company_name}}"
        ),
        "merge_fields": ["{{first_name}}", "{{property_address}}", "{{loan_officer_name}}", "{{company_name}}"],
        "tags": ["congratulations", "closing_day", "sms"],
    },

    {
        "title": "Referral Ask SMS",
        "description": "Casual referral request text for past clients.",
        "content_type": "sms",
        "category": "post_close",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "Hi {{first_name}}, {{loan_officer_name}} here! Hope you're loving the new home. "
            "If you know anyone buying or refinancing, I'd love an intro — I'll take great "
            "care of them!"
        ),
        "merge_fields": ["{{first_name}}", "{{loan_officer_name}}", "{{loan_officer_phone}}"],
        "tags": ["referral", "post_close", "sms"],
    },

    # =========================================================================
    # SOCIAL MEDIA POSTS (5)
    # =========================================================================

    {
        "title": "Monthly Market Update — Social Post",
        "description": "LinkedIn/Facebook market update post. Positions LO as a local market expert.",
        "content_type": "social_post",
        "category": "market_update",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "📊 {{current_month}} Mortgage Market Update\n\n"
            "Rates are [trending/stabilizing] as we move through {{current_month}}. Here's "
            "what that means for buyers and homeowners:\n\n"
            "🏡 For Buyers: Getting pre-approved NOW locks in your purchasing power before "
            "any rate movement. The best deals go to prepared buyers.\n\n"
            "💰 For Homeowners: If you haven't reviewed your mortgage in the past 12 months, "
            "now is the time. A free analysis takes 15 minutes and could reveal significant savings.\n\n"
            "Questions about rates or your options? Drop a comment below or DM me directly.\n\n"
            "{{loan_officer_name}} | {{company_name}} | NMLS #{{loan_officer_nmls}}\n"
            "Equal Housing Lender"
        ),
        "merge_fields": ["{{current_month}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_nmls}}"],
        "tags": ["market_update", "social", "linkedin", "facebook"],
    },

    {
        "title": "First-Time Buyer Tips — Social Post",
        "description": "Educational tip post for first-time buyers. Drives engagement and leads.",
        "content_type": "social_post",
        "category": "new_lead",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "🏠 Thinking about buying your first home? Here are 3 things I tell every first-time buyer:\n\n"
            "1️⃣ Start earlier than you think. Most people wait until they're \"ready\" — "
            "but getting pre-qualified is FREE and takes 10 minutes. It shows you exactly "
            "where you stand.\n\n"
            "2️⃣ You don't need 20% down. FHA loans start at 3.5%. VA loans are 0% for "
            "veterans. Many states offer down payment assistance programs.\n\n"
            "3️⃣ Your credit score matters more than your income for your rate. "
            "Even a 20-point improvement can save you tens of thousands over the loan.\n\n"
            "What questions do you have about buying? Drop them below — I answer every one! 👇\n\n"
            "{{loan_officer_name}} | {{company_name}} | NMLS #{{loan_officer_nmls}}\n"
            "Equal Housing Lender"
        ),
        "merge_fields": ["{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_nmls}}"],
        "tags": ["first_time_buyer", "educational", "social", "engagement"],
    },

    {
        "title": "Rate Commentary — Social Post",
        "description": "Timely rate commentary for social media. Drives call-to-action.",
        "content_type": "social_post",
        "category": "market_update",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "💡 Rate Talk for {{current_month}}:\n\n"
            "Everyone is asking about mortgage rates right now — and rightfully so. "
            "Here's my honest take:\n\n"
            "Rates are [currently/recently] at [level]. For context, the average 30-year "
            "fixed rate over the past 50 years has been around 8%. That means even today's "
            "rates are historically [favorable/elevated].\n\n"
            "But here's the thing most people miss: the best time to buy a home isn't "
            "\"when rates are perfect\" — it's when YOU are ready financially and personally.\n\n"
            "If you're ready, let's look at your options. If you're not sure, let's talk "
            "through what it would take to get you there.\n\n"
            "No pressure. No sales pitch. Just honest guidance.\n\n"
            "{{loan_officer_name}} | {{company_name}} | NMLS #{{loan_officer_nmls}}\n"
            "Equal Housing Lender"
        ),
        "merge_fields": ["{{current_month}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_nmls}}"],
        "tags": ["rate_commentary", "social", "thought_leadership"],
    },

    {
        "title": "Client Success Story — Social Post (Template)",
        "description": "Template for sharing anonymized client success stories.",
        "content_type": "social_post",
        "category": "post_close",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "🎉 Another family in their dream home!\n\n"
            "I recently had the honor of helping [a first-time buyer / a growing family / "
            "a veteran] close on [a home / a condo] in [city/area].\n\n"
            "What made this transaction special: [brief story — e.g., \"We navigated a "
            "competitive market with multiple offers and still got them an amazing rate.\"].\n\n"
            "Every client's journey is unique, and every closing is a privilege for my team.\n\n"
            "If you or someone you know is ready to start their homeownership journey, "
            "reach out — I'd love to help.\n\n"
            "{{loan_officer_name}} | {{company_name}} | NMLS #{{loan_officer_nmls}}\n"
            "Equal Housing Lender | *Client details shared with permission."
        ),
        "merge_fields": ["{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_nmls}}"],
        "tags": ["success_story", "social", "social_proof"],
    },

    {
        "title": "Community Involvement — Social Post",
        "description": "Highlights community involvement. Humanizes the LO brand.",
        "content_type": "social_post",
        "category": "new_lead",
        "subject_line": None,
        "body_html": None,
        "body_text": (
            "❤️ Community first.\n\n"
            "Being a mortgage professional isn't just about closing loans — it's about "
            "helping families plant roots in this community I love.\n\n"
            "[Share a community involvement story: volunteering, sponsoring a local event, "
            "supporting a local organization, etc.]\n\n"
            "I believe that the strength of our community is directly tied to the strength "
            "of our neighborhoods — and homeownership is a cornerstone of that.\n\n"
            "Proud to serve [city/area]. 🏡\n\n"
            "{{loan_officer_name}} | {{company_name}} | NMLS #{{loan_officer_nmls}}"
        ),
        "merge_fields": ["{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_nmls}}"],
        "tags": ["community", "branding", "social", "relationship"],
    },

    # =========================================================================
    # REFINANCE OUTREACH EMAILS (5)
    # =========================================================================

    {
        "title": "Rate Drop Alert — Refinance Opportunity",
        "description": "Triggered when rates drop significantly below client's current rate.",
        "content_type": "email",
        "category": "refinance",
        "subject_line": "{{first_name}}, rates just dropped — could you save on your mortgage?",
        "body_html": _html(
            "Rate Drop Alert",
            "Rates have dropped — your mortgage may be worth reviewing",
            [
                "Hi {{first_name}} — I'm reaching out because mortgage rates have dropped "
                "recently, and I always alert my past clients when it could mean real savings.",
                "Quick analysis based on your loan:",
                "<table style='width:100%;border-collapse:collapse;'>"
                "<tr style='background:#f0f4fa;'><th style='text-align:left;padding:8px;'></th><th style='padding:8px;'>Current</th><th style='padding:8px;'>Potential</th></tr>"
                "<tr><td style='padding:8px;'>Interest Rate</td><td style='padding:8px;'>{{current_rate}}</td><td style='padding:8px;'>{{new_rate}}</td></tr>"
                "<tr style='background:#f0f4fa;'><td style='padding:8px;'>Monthly Payment</td><td style='padding:8px;'>{{monthly_payment}}</td><td style='padding:8px;'>Estimated savings: {{monthly_savings}}/mo</td></tr>"
                "<tr><td style='padding:8px;'>Loan Balance</td><td colspan='2' style='padding:8px;'>{{loan_amount}}</td></tr>"
                "</table>",
                "<p><em>Note: These are estimates. Actual savings depend on your credit, current loan balance, "
                "and other factors. A full analysis takes about 10 minutes.</em></p>",
                "If the break-even period works for your plans, this could be worth pursuing. "
                "A free, no-obligation analysis is all it takes to know for sure.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Get My Free Refi Analysis</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Rates dropped — wanted to reach out right away.",
            "Your current rate: {{current_rate}} | Potential new rate: {{new_rate}}",
            "Estimated monthly savings: {{monthly_savings}}",
            "This is a free analysis — no obligation. If the numbers work, great. If not, I'll tell you.",
            "Let's look at the numbers: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{current_rate}}", "{{new_rate}}", "{{monthly_payment}}", "{{monthly_savings}}", "{{loan_amount}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["rate_drop", "refinance", "alert", "savings"],
    },

    {
        "title": "Equity Update — Cash-Out Refinance Options",
        "description": "Informs client of their equity position and cash-out refinance potential.",
        "content_type": "email",
        "category": "refinance",
        "subject_line": "{{first_name}}, you may have {{equity_amount}} in home equity to tap",
        "body_html": _html(
            "Cash-Out Equity Update",
            "Your home equity may be working harder for you",
            [
                "Hi {{first_name}} — home values have appreciated significantly over the past "
                "few years, which means your equity position may be much stronger than you realize.",
                "Based on current market estimates and your loan balance:",
                "<ul>"
                "<li>Estimated home value: <strong>{{home_value}}</strong></li>"
                "<li>Remaining loan balance: <strong>{{loan_amount}}</strong></li>"
                "<li>Estimated equity: <strong>{{equity_amount}}</strong></li>"
                "</ul>",
                "With a cash-out refinance, you could access a portion of that equity for:",
                "<ul>"
                "<li>Home improvements that add value</li>"
                "<li>High-interest debt consolidation</li>"
                "<li>College tuition or major expenses</li>"
                "<li>Down payment on an investment property</li>"
                "</ul>",
                "This isn't right for everyone — it depends on current rates, your goals, "
                "and how long you plan to stay in your home. A 15-minute conversation can "
                "clarify whether it makes sense for you.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Discuss My Equity Options</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "Your home has likely appreciated — let me share your equity position.",
            "Estimated home value: {{home_value}}\n"
            "Remaining balance: {{loan_amount}}\n"
            "Estimated equity: {{equity_amount}}",
            "A cash-out refinance could unlock that equity for home improvements, "
            "debt consolidation, investment properties, and more.",
            "Want to explore options? {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{home_value}}", "{{loan_amount}}", "{{equity_amount}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["cash_out", "equity", "refinance"],
    },

    {
        "title": "Rate Comparison — Your Current vs. Today's Market",
        "description": "Side-by-side rate comparison to motivate refinance action.",
        "content_type": "email",
        "category": "refinance",
        "subject_line": "{{first_name}}, here's how your rate compares to today's market",
        "body_html": _html(
            "Rate Comparison",
            "How does your current rate compare?",
            [
                "Hi {{first_name}} — quick question: when did you last compare your "
                "mortgage rate to what's available today?",
                "Even if rates have moved up since you closed, refinancing for the "
                "right reasons — like accessing equity or shortening your loan term — "
                "can still make sense.",
                "Here's a quick comparison:",
                "<table style='width:100%;border-collapse:collapse;'>"
                "<tr style='background:#f0f4fa;'><th style='text-align:left;padding:8px;'>Option</th>"
                "<th style='padding:8px;'>Rate</th><th style='padding:8px;'>Monthly Payment*</th></tr>"
                "<tr><td style='padding:8px;'>Your Current Loan</td><td style='padding:8px;'>{{current_rate}}</td><td style='padding:8px;'>{{monthly_payment}}</td></tr>"
                "<tr style='background:#f0f4fa;'><td style='padding:8px;'>Today's 30-Year Fixed</td><td style='padding:8px;'>{{new_rate}}</td><td style='padding:8px;'>Get a quote</td></tr>"
                "</table>",
                "<p><em>*Estimates only. Actual terms subject to qualification and current rates.</em></p>",
                "The only way to know if a refinance makes sense is to run the numbers. "
                "I'll do that for free — and I'll give you an honest answer.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Run My Rate Comparison</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "When did you last compare your mortgage rate to today's market?",
            "Your current rate: {{current_rate}} | Monthly payment: {{monthly_payment}}",
            "Today's rates may be different — the only way to know if a refi makes sense "
            "is a free analysis. I'll be honest either way.",
            "Let's run the numbers: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{current_rate}}", "{{new_rate}}", "{{monthly_payment}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["rate_comparison", "refinance"],
    },

    {
        "title": "Shorten Your Loan Term — 15-Year Analysis",
        "description": "Promotes switching to a 15-year mortgage to pay off faster and save on interest.",
        "content_type": "email",
        "category": "refinance",
        "subject_line": "{{first_name}}, what if you could pay off your mortgage {{current_year}} years sooner?",
        "body_html": _html(
            "Shorten Loan Term",
            "Could you pay off your mortgage sooner than you think?",
            [
                "Hi {{first_name}} — have you ever thought about what it would mean "
                "to own your home free and clear 10–15 years earlier?",
                "A rate-and-term refinance into a 15-year mortgage can dramatically reduce "
                "the total interest you pay over the life of your loan — often by six figures.",
                "Consider this general illustration:",
                "<table style='width:100%;border-collapse:collapse;'>"
                "<tr style='background:#f0f4fa;'><th style='text-align:left;padding:8px;'></th>"
                "<th style='padding:8px;'>30-Year Remaining</th><th style='padding:8px;'>Refinance to 15-Year</th></tr>"
                "<tr><td style='padding:8px;'>Monthly Payment</td><td style='padding:8px;'>{{monthly_payment}}</td><td style='padding:8px;'>Slightly higher</td></tr>"
                "<tr style='background:#f0f4fa;'><td style='padding:8px;'>Years to Payoff</td><td style='padding:8px;'>Remaining term</td><td style='padding:8px;'>15 years</td></tr>"
                "<tr><td style='padding:8px;'>Total Interest Saved</td><td style='padding:8px;'>—</td><td style='padding:8px;'>Could be significant</td></tr>"
                "</table>",
                "The trade-off is a somewhat higher monthly payment. But for many borrowers "
                "who've had a raise since they bought their home, this is very achievable — "
                "and the long-term savings are substantial.",
                "Let me run your specific numbers. 15 minutes, no obligation.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Show Me the 15-Year Numbers</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "What if you could own your home free and clear 15 years sooner?",
            "Refinancing into a 15-year mortgage means a slightly higher payment, "
            "but the total interest savings can be six figures.",
            "Your current loan: {{loan_amount}} at {{current_rate}}",
            "Let me run your specific numbers — free, 15 minutes, no obligation.",
            "Schedule here: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_amount}}", "{{current_rate}}", "{{monthly_payment}}", "{{calendar_link}}", "{{current_year}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["15_year", "term_reduction", "refinance", "savings"],
    },

    {
        "title": "Monthly Savings Calculator — What Could You Save?",
        "description": "Invites borrower to get a personalized savings projection.",
        "content_type": "email",
        "category": "refinance",
        "subject_line": "{{first_name}}, what could you save on your mortgage each month?",
        "body_html": _html(
            "Savings Calculator",
            "What could you save on your mortgage each month?",
            [
                "Hi {{first_name}} — I love running savings analyses for my clients because "
                "the results are often surprising. Let me explain how it works:",
                "A mortgage savings analysis looks at four factors:",
                "<ol>"
                "<li><strong>Your current rate vs. today's rates</strong> — the spread determines your potential savings per dollar of loan balance.</li>"
                "<li><strong>Your remaining loan balance</strong> — {{loan_amount}} in your case.</li>"
                "<li><strong>Your break-even period</strong> — how long until the closing costs are recouped by monthly savings.</li>"
                "<li><strong>Your time horizon</strong> — how long you plan to stay in the home.</li>"
                "</ol>",
                "If the break-even period is shorter than your time horizon, a refinance is "
                "mathematically beneficial. It's that simple — but only the numbers tell the story.",
                "My analysis is free, takes 10–15 minutes, and I'll give you a clear "
                "recommendation with no pressure either way.",
                '<p><a href="{{calendar_link}}" style="background:#1a3c6e;color:#fff;padding:10px 20px;'
                'text-decoration:none;border-radius:4px;">Calculate My Savings</a></p>',
            ],
        ),
        "body_text": _text([
            "Hi {{first_name}},",
            "A mortgage savings analysis looks at 4 things:\n"
            "1. Your current rate vs. today's\n"
            "2. Your remaining balance ({{loan_amount}})\n"
            "3. Break-even period (closing costs ÷ monthly savings)\n"
            "4. How long you plan to stay",
            "If break-even < your time horizon = refinance makes sense.",
            "I'll run your numbers for free — no pressure either way.",
            "Get my savings analysis: {{calendar_link}}",
        ]),
        "merge_fields": ["{{first_name}}", "{{loan_amount}}", "{{current_rate}}", "{{calendar_link}}", "{{loan_officer_name}}", "{{company_name}}", "{{loan_officer_phone}}", "{{loan_officer_email}}", "{{loan_officer_nmls}}"],
        "tags": ["savings_calculator", "refinance", "educational"],
    },

]


# ---------------------------------------------------------------------------
# Seeder function
# ---------------------------------------------------------------------------

def seed_content_library(db: Session, force_reseed: bool = False) -> int:
    """Seed the content library with platform-default templates.

    This function is idempotent by default: it checks whether platform-default
    items already exist and skips seeding if they do. Pass ``force_reseed=True``
    to wipe existing platform defaults and re-insert (useful during development).

    Args:
        db: SQLAlchemy session.
        force_reseed: If True, delete all existing platform defaults before
            re-seeding. Use with caution in production.

    Returns:
        Number of templates inserted.
    """
    # Check for existing platform defaults
    existing_count = (
        db.query(ContentLibraryItem)
        .filter(ContentLibraryItem.is_platform_default == True)
        .count()
    )

    if existing_count > 0 and not force_reseed:
        logger.info(
            "Content library already seeded (%d platform defaults). "
            "Pass force_reseed=True to re-seed.",
            existing_count,
        )
        return 0

    if force_reseed and existing_count > 0:
        logger.warning(
            "force_reseed=True: deleting %d existing platform defaults.",
            existing_count,
        )
        db.query(ContentLibraryItem).filter(
            ContentLibraryItem.is_platform_default == True
        ).delete(synchronize_session=False)
        db.flush()

    now = datetime.now(timezone.utc)
    inserted = 0

    for template_def in _TEMPLATES:
        item = ContentLibraryItem(
            organization_id=None,             # Platform-wide
            source_template_id=None,
            created_by_id=None,
            updated_by_id=None,
            title=template_def["title"],
            description=template_def.get("description", ""),
            content_type=template_def["content_type"],
            category=template_def["category"],
            body_html=template_def.get("body_html"),
            body_text=template_def.get("body_text"),
            subject_line=template_def.get("subject_line"),
            thumbnail_url=None,
            tags=template_def.get("tags", []),
            merge_fields=template_def.get("merge_fields", []),
            is_platform_default=True,
            is_customizable=True,
            compliance_approved=True,
            compliance_approved_at=now,
            compliance_approved_by_id=None,
            compliance_notes=(
                "Platform default — pre-reviewed. Contains Equal Housing Lender language, "
                "NMLS# placeholder, and CAN-SPAM unsubscribe token in all email bodies."
            ),
            usage_count=0,
            rating=None,
            rating_count=0,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
        inserted += 1

    try:
        db.commit()
        logger.info("Content library seeded: %d templates inserted.", inserted)
    except Exception:
        db.rollback()
        logger.exception("Failed to seed content library.")
        raise

    return inserted


def get_seed_summary() -> Dict[str, Any]:
    """Return a summary of the templates defined in this seeder (no DB needed).

    Useful for documentation, testing, and admin dashboards.
    """
    from collections import Counter

    type_counts: Counter = Counter()
    category_counts: Counter = Counter()

    for t in _TEMPLATES:
        type_counts[t["content_type"]] += 1
        category_counts[t["category"]] += 1

    return {
        "total_templates": len(_TEMPLATES),
        "by_content_type": dict(type_counts),
        "by_category": dict(category_counts),
    }
