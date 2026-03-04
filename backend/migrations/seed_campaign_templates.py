"""
Migration: Seed pre-built mortgage campaign email templates

Adds 20 mortgage-specific email templates to tenant_email_templates
for each organization. Skips if template_type already exists for an org.

Covers: welcome drip (3), rate updates (2), application follow-up (3),
pre-approval congratulations (1), closing countdown (3), post-close nurture (4),
refinance opportunity (2), referral request (2).
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

CAMPAIGN_TEMPLATES = [
    # ===== WELCOME DRIP (3) =====
    {
        "template_type": "welcome_drip_1",
        "name": "Welcome Drip - Day 1: Introduction",
        "subject": "Welcome {{first_name}} — let's get started!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Thank you for choosing <strong>{{company_name}}</strong> for your mortgage needs. I\'m {{lo_name}}, your dedicated loan officer.</p><p>Over the next few days, I\'ll share helpful resources to make your mortgage journey smooth and stress-free.</p><p><strong>First step:</strong> Let\'s schedule a quick 15-minute call to discuss your goals.</p><p>{{cta_button}}</p><p>{{lo_name}}<br>NMLS# {{lo_nmls}}<br>{{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, Welcome to {{company_name}}! I'm {{lo_name}}, your loan officer. Let's schedule a quick call.",
        "cta_text": "Schedule a Call",
        "merge_fields": ["first_name", "company_name", "lo_name", "lo_nmls", "lo_phone"],
        "category": "marketing",
    },
    {
        "template_type": "welcome_drip_2",
        "name": "Welcome Drip - Day 3: What to Expect",
        "subject": "What to expect during your mortgage process",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Here\'s a quick overview of the mortgage process:</p><ol><li><strong>Application</strong> — Submit your info and documents</li><li><strong>Processing</strong> — We verify everything</li><li><strong>Underwriting</strong> — Loan review and approval</li><li><strong>Closing</strong> — Sign and celebrate!</li></ol><p>Most loans close in 30-45 days. I\'ll guide you through every step.</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Here's what to expect: Application, Processing, Underwriting, Closing. Most loans close in 30-45 days.",
        "merge_fields": ["first_name", "lo_name"],
        "category": "marketing",
    },
    {
        "template_type": "welcome_drip_3",
        "name": "Welcome Drip - Day 7: Document Checklist",
        "subject": "Your document checklist — get ahead of the game",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Getting your documents ready early speeds up your loan. Here\'s what you\'ll typically need:</p><ul><li>Recent pay stubs (last 30 days)</li><li>W-2s (last 2 years)</li><li>Bank statements (last 2 months)</li><li>Tax returns (last 2 years)</li><li>Government-issued ID</li></ul><p>Upload them securely through your portal anytime.</p><p>{{cta_button}}</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Get your documents ready: pay stubs, W-2s, bank statements, tax returns, ID.",
        "cta_text": "Upload Documents",
        "merge_fields": ["first_name", "lo_name"],
        "category": "marketing",
    },

    # ===== RATE UPDATE (2) =====
    {
        "template_type": "rate_drop_alert",
        "name": "Rate Drop Alert",
        "subject": "Rates just dropped — now might be the time, {{first_name}}",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Great news — mortgage rates have <strong>dropped</strong> recently:</p><table style="border-collapse:collapse;width:100%;margin:16px 0;"><tr><td style="padding:8px;border:1px solid #ddd;"><strong>30-Year Fixed</strong></td><td style="padding:8px;border:1px solid #ddd;">{{rate_30yr}}%</td></tr><tr><td style="padding:8px;border:1px solid #ddd;"><strong>15-Year Fixed</strong></td><td style="padding:8px;border:1px solid #ddd;">{{rate_15yr}}%</td></tr></table><p>This could mean significant savings on your monthly payment. Want to see what you qualify for?</p><p>{{cta_button}}</p><p>{{lo_name}} | {{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, Rates dropped! 30yr: {{rate_30yr}}%, 15yr: {{rate_15yr}}%. Call {{lo_phone}} to discuss.",
        "cta_text": "Get Your Rate Quote",
        "merge_fields": ["first_name", "rate_30yr", "rate_15yr", "lo_name", "lo_phone"],
        "category": "marketing",
    },
    {
        "template_type": "rate_lock_reminder",
        "name": "Rate Lock Reminder",
        "subject": "Your rate lock expires {{lock_expiration}} — action needed",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Just a heads up — your locked rate of <strong>{{locked_rate}}%</strong> expires on <strong>{{lock_expiration}}</strong>.</p><p>To keep this rate, we need to close by that date. Here\'s where we stand:</p><p>{{status_summary}}</p><p>If you have any outstanding items, please send them ASAP so we can stay on track.</p><p>{{cta_button}}</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Your rate lock of {{locked_rate}}% expires {{lock_expiration}}. Please submit any outstanding items ASAP.",
        "cta_text": "View Your Loan Status",
        "merge_fields": ["first_name", "locked_rate", "lock_expiration", "status_summary", "lo_name"],
        "category": "transactional",
    },

    # ===== APPLICATION FOLLOW-UP (3) =====
    {
        "template_type": "app_started_followup",
        "name": "Application Started - Follow Up",
        "subject": "Finish your application — you're almost there!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>It looks like you started a mortgage application but didn\'t finish. No worries — you can pick up right where you left off!</p><p>Completing your application only takes about 15 minutes, and I\'m here to help if you get stuck.</p><p>{{cta_button}}</p><p>{{lo_name}} | {{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, You started an application but didn't finish. Pick up where you left off — it only takes 15 minutes.",
        "cta_text": "Continue Application",
        "merge_fields": ["first_name", "lo_name", "lo_phone"],
        "category": "transactional",
    },
    {
        "template_type": "app_submitted_confirmation",
        "name": "Application Submitted Confirmation",
        "subject": "Application received! Here's what happens next",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>We\'ve received your mortgage application — great job! Here\'s what happens next:</p><ol><li>We\'ll review your application within 24-48 hours</li><li>You\'ll receive your initial loan estimate</li><li>We\'ll reach out if we need any additional documents</li></ol><p>In the meantime, you can check your application status anytime in your portal.</p><p>{{cta_button}}</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Application received! We'll review within 24-48 hours. Check status in your portal.",
        "cta_text": "Check Status",
        "merge_fields": ["first_name", "lo_name"],
        "category": "transactional",
    },
    {
        "template_type": "app_in_processing",
        "name": "Application In Processing Update",
        "subject": "Update: Your loan is in processing",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Your loan application is now <strong>in processing</strong>. Our team is reviewing your documents and verifying your information.</p><p><strong>Current status:</strong> {{status_detail}}</p><p>If we need anything additional, we\'ll reach out. Otherwise, no action needed from you right now.</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Your loan is in processing. Status: {{status_detail}}. No action needed right now.",
        "merge_fields": ["first_name", "status_detail", "lo_name"],
        "category": "transactional",
    },

    # ===== PRE-APPROVAL CONGRATULATIONS (1) =====
    {
        "template_type": "preapproval_congrats",
        "name": "Pre-Approval Congratulations",
        "subject": "Congratulations {{first_name}} — you're pre-approved!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Congratulations! You\'ve been <strong>pre-approved</strong> for up to <strong>{{preapproval_amount}}</strong>.</p><p>This means sellers and agents will take your offers seriously. Your pre-approval letter is ready to download.</p><p>{{cta_button}}</p><p>A few tips for house hunting:</p><ul><li>Stay within your comfortable payment range</li><li>Avoid opening new credit accounts</li><li>Keep your employment stable</li></ul><p>Happy house hunting!</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Congratulations! You're pre-approved for up to {{preapproval_amount}}. Download your letter now.",
        "cta_text": "Download Pre-Approval Letter",
        "merge_fields": ["first_name", "preapproval_amount", "lo_name"],
        "category": "transactional",
    },

    # ===== CLOSING COUNTDOWN (3) =====
    {
        "template_type": "closing_7day",
        "name": "Closing Countdown - 7 Days",
        "subject": "7 days to closing! Here's your checklist",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Your closing is just <strong>7 days away</strong> on <strong>{{closing_date}}</strong>!</p><p><strong>Your checklist:</strong></p><ul><li>Review your Closing Disclosure (sent separately)</li><li>Confirm wire transfer details with your bank</li><li>Schedule final walk-through of the property</li><li>Gather valid photo ID for closing day</li></ul><p>Questions? I\'m just a call or text away.</p><p>{{lo_name}} | {{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, 7 days to closing on {{closing_date}}! Review your checklist and contact {{lo_name}} with questions.",
        "merge_fields": ["first_name", "closing_date", "lo_name", "lo_phone"],
        "category": "transactional",
    },
    {
        "template_type": "closing_3day",
        "name": "Closing Countdown - 3 Days",
        "subject": "3 days to closing — final reminders",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Just <strong>3 days</strong> until your big day!</p><p><strong>Final reminders:</strong></p><ul><li>Bring government-issued photo ID</li><li>Bring certified/cashier\'s check for <strong>{{cash_to_close}}</strong> (or confirm wire)</li><li>Don\'t make any large purchases or open new credit</li></ul><p><strong>Closing details:</strong><br>Date: {{closing_date}}<br>Time: {{closing_time}}<br>Location: {{closing_location}}</p><p>See you there!</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, 3 days to closing! Bring ID and {{cash_to_close}}. {{closing_date}} at {{closing_location}}.",
        "cta_text": "View Closing Details",
        "merge_fields": ["first_name", "cash_to_close", "closing_date", "closing_time", "closing_location", "lo_name"],
        "category": "transactional",
    },
    {
        "template_type": "closing_congrats",
        "name": "Closing Day Congratulations",
        "subject": "Congratulations on your new home, {{first_name}}!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Congratulations — <strong>you did it!</strong> You are now a homeowner!</p><p>It\'s been a pleasure working with you on this journey. A few helpful reminders:</p><ul><li>Your first mortgage payment is due {{first_payment_date}}</li><li>Keep your closing documents in a safe place</li><li>Consider setting up autopay for your mortgage</li></ul><p>I\'m always here if you have questions about your mortgage or if friends and family need help with theirs.</p><p>Welcome home!</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Congratulations on your new home! First payment due {{first_payment_date}}. I'm always here to help.",
        "merge_fields": ["first_name", "first_payment_date", "lo_name"],
        "category": "transactional",
    },

    # ===== POST-CLOSE NURTURE (4) =====
    {
        "template_type": "postclose_30day",
        "name": "Post-Close Nurture - 30 Day Check-In",
        "subject": "How's the new home, {{first_name}}?",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>It\'s been about a month since you closed — how\'s the new home? I hope you\'re settling in nicely!</p><p>A couple of quick reminders:</p><ul><li>File for your homestead exemption if applicable</li><li>Update your address with USPS, banks, and insurance</li></ul><p>If you have any questions about your mortgage, I\'m always here to help.</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, How's the new home? Remember to file for homestead exemption and update your address.",
        "merge_fields": ["first_name", "lo_name"],
        "category": "marketing",
    },
    {
        "template_type": "postclose_6month",
        "name": "Post-Close Nurture - 6 Month Check-In",
        "subject": "6-month home check-in for {{first_name}}",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Can you believe it\'s been 6 months since you closed? Time flies!</p><p>A few things to think about:</p><ul><li>Review your homeowner\'s insurance — is your coverage still adequate?</li><li>Consider an escrow analysis to ensure your payments are on track</li><li>If rates have dropped, a refinance could save you money</li></ul><p>Let me know if you\'d like a free rate comparison.</p><p>{{lo_name}} | {{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, 6 months in your new home! Review insurance, check escrow, and let me know if you want a rate comparison.",
        "merge_fields": ["first_name", "lo_name", "lo_phone"],
        "category": "marketing",
    },
    {
        "template_type": "postclose_anniversary",
        "name": "Post-Close Nurture - Annual Anniversary",
        "subject": "Happy home anniversary, {{first_name}}!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Happy anniversary in your home! It\'s been a year since you closed, and I hope it\'s been everything you dreamed of.</p><p>This is a great time to:</p><ul><li>Review your property tax assessment</li><li>Check if your home value has increased (it probably has!)</li><li>Consider whether a refinance makes sense at current rates</li></ul><p>I\'d love to hear how you\'re doing. And if anyone you know is looking to buy or refinance, I\'d be honored by the referral.</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Happy home anniversary! Review your tax assessment and property value. Referrals always appreciated!",
        "merge_fields": ["first_name", "lo_name"],
        "category": "marketing",
    },
    {
        "template_type": "postclose_market_update",
        "name": "Post-Close Nurture - Market Update",
        "subject": "Your neighborhood market update, {{first_name}}",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Here\'s a quick update on your local real estate market:</p><p>{{market_summary}}</p><p>Your home\'s estimated value: <strong>{{estimated_value}}</strong></p><p>Want a detailed equity analysis? I can run a free one for you anytime.</p><p>{{cta_button}}</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Market update: {{market_summary}}. Your estimated home value: {{estimated_value}}.",
        "cta_text": "Request Equity Analysis",
        "merge_fields": ["first_name", "market_summary", "estimated_value", "lo_name"],
        "category": "marketing",
    },

    # ===== REFINANCE OPPORTUNITY (2) =====
    {
        "template_type": "refi_rate_opportunity",
        "name": "Refinance Opportunity - Rate Savings",
        "subject": "{{first_name}}, you could save {{monthly_savings}}/month with a refi",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Based on current rates, you may be able to <strong>save {{monthly_savings}} per month</strong> by refinancing your mortgage.</p><table style="border-collapse:collapse;width:100%;margin:16px 0;"><tr><td style="padding:8px;border:1px solid #ddd;">Current Rate</td><td style="padding:8px;border:1px solid #ddd;">{{current_rate}}%</td></tr><tr><td style="padding:8px;border:1px solid #ddd;">Available Rate</td><td style="padding:8px;border:1px solid #ddd;">{{new_rate}}%</td></tr><tr><td style="padding:8px;border:1px solid #ddd;"><strong>Est. Monthly Savings</strong></td><td style="padding:8px;border:1px solid #ddd;"><strong>{{monthly_savings}}</strong></td></tr></table><p>Want to explore your options? It only takes a few minutes.</p><p>{{cta_button}}</p><p>{{lo_name}} | {{lo_phone}}</p></div>',
        "body_text": "Hi {{first_name}}, You could save {{monthly_savings}}/month by refinancing from {{current_rate}}% to {{new_rate}}%. Call {{lo_phone}}.",
        "cta_text": "Check Your Refi Options",
        "merge_fields": ["first_name", "monthly_savings", "current_rate", "new_rate", "lo_name", "lo_phone"],
        "category": "marketing",
    },
    {
        "template_type": "refi_cashout",
        "name": "Refinance Opportunity - Cash-Out",
        "subject": "Tap into your home equity, {{first_name}}",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Your home has built up significant equity, and a <strong>cash-out refinance</strong> could help you:</p><ul><li>Consolidate high-interest debt</li><li>Fund home improvements</li><li>Cover education expenses</li><li>Build an investment portfolio</li></ul><p>Your estimated available equity: <strong>{{available_equity}}</strong></p><p>Let\'s chat about whether this makes sense for your situation.</p><p>{{cta_button}}</p><p>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Your home has {{available_equity}} in available equity. A cash-out refi could help fund your goals.",
        "cta_text": "Explore Cash-Out Options",
        "merge_fields": ["first_name", "available_equity", "lo_name"],
        "category": "marketing",
    },

    # ===== REFERRAL REQUEST (2) =====
    {
        "template_type": "referral_request",
        "name": "Referral Request",
        "subject": "Know someone buying a home, {{first_name}}?",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>I hope you\'re enjoying your home! I\'m reaching out because the best compliment I can receive is a referral from a happy client.</p><p>If you know anyone who\'s thinking about buying, refinancing, or has questions about mortgages, I\'d love to help them the same way I helped you.</p><p>Simply forward this email or share my contact info. Thank you for your trust!</p><p>{{cta_button}}</p><p>{{lo_name}}<br>{{lo_phone}}<br>{{lo_email}}<br>NMLS# {{lo_nmls}}</p></div>',
        "body_text": "Hi {{first_name}}, Know anyone buying or refinancing? I'd love to help them like I helped you. Share my info: {{lo_name}}, {{lo_phone}}.",
        "cta_text": "Refer a Friend",
        "merge_fields": ["first_name", "lo_name", "lo_phone", "lo_email", "lo_nmls"],
        "category": "marketing",
    },
    {
        "template_type": "referral_thank_you",
        "name": "Referral Thank You",
        "subject": "Thank you for the referral, {{first_name}}!",
        "body_html": '<div style="font-family:Arial,sans-serif;max-width:600px;"><p>Hi {{first_name}},</p><p>Thank you so much for referring <strong>{{referral_name}}</strong> to me! It means the world to know you had a great experience and trust me with your friends and family.</p><p>I\'ll take excellent care of them. I\'ll keep you posted on how things go (with their permission, of course).</p><p>Thank you again for your trust and support!</p><p>Warmly,<br>{{lo_name}}</p></div>',
        "body_text": "Hi {{first_name}}, Thank you for referring {{referral_name}}! I'll take excellent care of them.",
        "merge_fields": ["first_name", "referral_name", "lo_name"],
        "category": "transactional",
    },
]


def run_migration(engine):
    """Seed campaign templates for all existing organizations."""
    with engine.connect() as conn:
        try:
            # Check if table exists
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant_email_templates'"
            )).fetchone()

            if not result:
                logger.info("Migration: tenant_email_templates table does not exist, skipping seed")
                return

            # Get all organization IDs
            orgs = conn.execute(text("SELECT id FROM organizations")).fetchall()
            if not orgs:
                logger.info("Migration: No organizations found, skipping template seed")
                return

            total_created = 0
            for org in orgs:
                org_id = org[0]
                for tmpl in CAMPAIGN_TEMPLATES:
                    # Skip if template_type already exists for this org
                    existing = conn.execute(text(
                        "SELECT id FROM tenant_email_templates WHERE organization_id = :org_id AND template_type = :tt"
                    ), {"org_id": org_id, "tt": tmpl["template_type"]}).fetchone()

                    if existing:
                        continue

                    conn.execute(text("""
                        INSERT INTO tenant_email_templates
                            (organization_id, template_type, name, subject, body_html, body_text,
                             cta_text, merge_fields, category, is_active, created_at, updated_at)
                        VALUES
                            (:org_id, :template_type, :name, :subject, :body_html, :body_text,
                             :cta_text, :merge_fields::jsonb, :category, true, NOW(), NOW())
                    """), {
                        "org_id": org_id,
                        "template_type": tmpl["template_type"],
                        "name": tmpl["name"],
                        "subject": tmpl["subject"],
                        "body_html": tmpl["body_html"],
                        "body_text": tmpl.get("body_text", ""),
                        "cta_text": tmpl.get("cta_text"),
                        "merge_fields": str(tmpl.get("merge_fields", [])).replace("'", '"'),
                        "category": tmpl.get("category", "marketing"),
                    })
                    total_created += 1

            conn.commit()
            logger.info(f"Migration: Seeded {total_created} campaign templates across {len(orgs)} org(s)")

        except Exception as e:
            logger.warning(f"Migration: Campaign template seed skipped: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
