"""Pre-built 12-month campaign templates for mortgage lead engagement."""

PURCHASE_LEAD_SEQUENCE = {
    "name": "Purchase Lead - 12 Month Nurture",
    "description": "Comprehensive nurture sequence for purchase leads with adaptive phases",
    "phases": [
        {
            "name": "Phase 1 - Hot Lead",
            "days_range": "0-7",
            "frequency": "daily",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "immediate_intro",
                 "content": "Hi {first_name}, thanks for your mortgage inquiry! I'm {lo_name} with {company}. What type of home are you looking for? Reply anytime. Reply STOP to opt out."},
                {"day": 0, "delay_min": 15, "channel": "sms", "template": "vm_followup",
                 "condition": "voicemail_left",
                 "content": "Just left you a voicemail, {first_name}. Feel free to text me here — happy to answer any mortgage questions!"},
                {"day": 1, "channel": "email", "template": "pre_approval_intro", "content": None},
                {"day": 2, "channel": "sms", "template": "check_in",
                 "content": "Hi {first_name}, still thinking about your mortgage? Happy to answer questions anytime. - {lo_name}"},
                {"day": 3, "channel": "email", "template": "rate_environment", "content": None},
                {"day": 5, "channel": "sms", "template": "pre_approval_cta",
                 "content": "Did you know pre-approval takes less than 10 minutes? Gives you an edge when making offers. Want me to get you started?"},
                {"day": 7, "channel": "email", "template": "market_update", "content": None},
            ],
        },
        {
            "name": "Phase 2 - Warm Nurture",
            "days_range": "8-90",
            "frequency": "weekly",
            "steps": [
                {"day": 14, "channel": "email", "template": "educational_closing_costs", "content": None},
                {"day": 21, "channel": "sms", "template": "gentle_check_in",
                 "content": "Hi {first_name}, just checking in. Still exploring your home buying options? I'm here when you're ready. - {lo_name}"},
                {"day": 28, "channel": "email", "template": "market_update", "content": None},
                {"day": 35, "channel": "sms", "template": "value_prop",
                 "content": "Quick tip: Getting pre-approved before house hunting shows sellers you're serious and can speed up the process. Want to chat?"},
                {"day": 42, "channel": "email", "template": "educational_credit", "content": None},
                {"day": 56, "channel": "email", "template": "rate_update", "content": None},
                {"day": 70, "channel": "sms", "template": "still_looking",
                 "content": "Hey {first_name}, still thinking about buying? The market's been moving — happy to give you an update anytime."},
                {"day": 84, "channel": "email", "template": "success_story", "content": None},
            ],
        },
        {
            "name": "Phase 3 - Long Nurture",
            "days_range": "91-365",
            "frequency": "monthly",
            "steps": [
                {"day": 120, "channel": "email", "template": "quarterly_market_review", "content": None},
                {"day": 150, "channel": "sms", "template": "monthly_check",
                 "content": "Hi {first_name}, hope all is well! Let me know if your home buying plans have changed. Always here to help. - {lo_name}"},
                {"day": 180, "channel": "email", "template": "half_year_update", "content": None},
                {"day": 210, "channel": "sms", "template": "monthly_check_2",
                 "content": "Hey {first_name}, just a friendly check-in. If you're thinking about buying, I'd love to chat about your options."},
                {"day": 240, "channel": "email", "template": "rate_watch", "content": None},
                {"day": 270, "channel": "sms", "template": "monthly_check_3",
                 "content": "Hi {first_name}, rates have been shifting. Want a quick update on what today's rates mean for your budget?"},
                {"day": 300, "channel": "email", "template": "year_end_review", "content": None},
                {"day": 330, "channel": "sms", "template": "almost_a_year",
                 "content": "Hi {first_name}, it's been a while since we connected! Are you still thinking about buying a home? I'm here whenever you're ready."},
                {"day": 365, "channel": "email", "template": "anniversary_re_engage", "content": None},
            ],
        },
    ],
    "exit_conditions": [
        "Lead responds to any message — pause drip, route to live conversation",
        "Appointment booked — switch to appointment prep sequence",
        "Application submitted — switch to loan lifecycle sequence",
        "STOP received — permanently exit all sequences",
        "Loan closed — switch to post-close referral sequence",
    ],
}

REFINANCE_LEAD_SEQUENCE = {
    "name": "Refinance Lead - 12 Month Nurture",
    "description": "Rate-focused nurture for refinance leads",
    "phases": [
        {
            "name": "Phase 1 - Hot Lead",
            "days_range": "0-7",
            "frequency": "daily",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "refi_intro",
                 "content": "Hi {first_name}, thanks for your refinance inquiry! I'm {lo_name}. I can run a quick savings analysis for you — what's your current rate? Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "refi_savings_intro", "content": None},
                {"day": 3, "channel": "sms", "template": "refi_follow",
                 "content": "Hi {first_name}, did you get a chance to see my email about your refi options? I can show you potential monthly savings in minutes."},
                {"day": 5, "channel": "email", "template": "break_even_education", "content": None},
                {"day": 7, "channel": "sms", "template": "refi_cta",
                 "content": "Many homeowners are saving $200-400/month by refinancing right now. Want me to run the numbers for you?"},
            ],
        },
        {
            "name": "Phase 2 - Rate Watch",
            "days_range": "8-90",
            "frequency": "biweekly",
            "steps": [
                {"day": 14, "channel": "email", "template": "rate_alert", "content": None},
                {"day": 28, "channel": "sms", "template": "rate_check",
                 "content": "Hi {first_name}, rates moved this week. Want a fresh look at your refinance savings?"},
                {"day": 42, "channel": "email", "template": "cash_out_education", "content": None},
                {"day": 56, "channel": "sms", "template": "equity_update",
                 "content": "Home values in your area have been climbing. You might have more equity than you think. Want an estimate?"},
                {"day": 70, "channel": "email", "template": "refi_success_story", "content": None},
                {"day": 84, "channel": "email", "template": "rate_environment_update", "content": None},
            ],
        },
        {
            "name": "Phase 3 - Long Nurture",
            "days_range": "91-365",
            "frequency": "monthly",
            "steps": [
                {"day": 120, "channel": "email", "template": "quarterly_rate_review", "content": None},
                {"day": 180, "channel": "sms", "template": "refi_half_year",
                 "content": "Hi {first_name}, checking in on your refinance plans. Market conditions may have changed in your favor. Want a quick update?"},
                {"day": 240, "channel": "email", "template": "rate_watch_update", "content": None},
                {"day": 300, "channel": "sms", "template": "year_end_refi",
                 "content": "Hi {first_name}, year-end can be a great time to lock in rates. Still thinking about refinancing?"},
                {"day": 365, "channel": "email", "template": "annual_refi_review", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

POST_CLOSE_SEQUENCE = {
    "name": "Post-Close - Referral & Retention",
    "description": "Stay top-of-mind with funded borrowers for referrals and future business",
    "phases": [
        {
            "name": "Phase 1 - Celebration",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "congratulations", "content": None},
                {"day": 7, "channel": "sms", "template": "settle_in",
                 "content": "Hi {first_name}, hope you're settling into your new home! Remember, I'm always here if you have any mortgage questions."},
                {"day": 14, "channel": "email", "template": "homeowner_tips", "content": None},
                {"day": 30, "channel": "email", "template": "first_payment_reminder", "content": None},
            ],
        },
        {
            "name": "Phase 2 - Relationship Building",
            "days_range": "31-365",
            "frequency": "monthly",
            "steps": [
                {"day": 90, "channel": "email", "template": "quarterly_update", "content": None},
                {"day": 120, "channel": "sms", "template": "referral_soft",
                 "content": "Hi {first_name}, hope you're loving the new home! If you know anyone thinking about buying or refinancing, I'd love to help them too."},
                {"day": 180, "channel": "email", "template": "half_year_equity", "content": None},
                {"day": 270, "channel": "email", "template": "tax_season_reminder", "content": None},
                {"day": 365, "channel": "email", "template": "anniversary", "content": None},
                {"day": 365, "channel": "sms", "template": "anniversary_sms",
                 "content": "Happy home anniversary, {first_name}! Hard to believe it's been a year. Hope you're loving it!"},
            ],
        },
    ],
    "exit_conditions": [
        "STOP received — permanently exit",
        "New loan application — switch to active pipeline sequence",
    ],
}

REENGAGEMENT_SEQUENCE = {
    "name": "Stale Lead Re-Engagement",
    "description": "Re-engage leads that went cold (30+ days no contact)",
    "phases": [
        {
            "name": "Re-Engagement Burst",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "channel": "sms", "template": "reengagement_sms",
                 "content": "Hi {first_name}, it's {lo_name}. We chatted a while back about your mortgage. Are you still in the market? I have some new options that might interest you."},
                {"day": 3, "channel": "email", "template": "reengagement_email", "content": None},
                {"day": 7, "channel": "sms", "template": "reengagement_value",
                 "content": "Hey {first_name}, rates have changed since we last spoke. Want a quick update on what's available now?"},
                {"day": 14, "channel": "email", "template": "reengagement_final", "content": None},
            ],
        },
    ],
    "exit_conditions": [
        "Any response — switch to Phase 1 of appropriate sequence",
        "No response after 14 days — move to Phase 3 long nurture",
        "STOP received — permanently exit",
    ],
}

PRE_APPROVAL_EXPIRATION_SEQUENCE = {
    "name": "Pre-Approval Expiration Reminder",
    "description": "Remind leads as their pre-approval letter approaches expiration",
    "phases": [
        {
            "name": "Expiration Countdown",
            "days_range": "30-0 before expiry",
            "frequency": "decreasing interval",
            "steps": [
                {"day": -30, "channel": "email", "template": "preapproval_30_day", "content": None},
                {"day": -14, "channel": "sms", "template": "preapproval_14_day",
                 "content": "Hi {first_name}, your pre-approval expires in 2 weeks. Renewing takes just a few minutes. Want me to get that started?"},
                {"day": -7, "channel": "email", "template": "preapproval_7_day", "content": None},
                {"day": -1, "channel": "sms", "template": "preapproval_tomorrow",
                 "content": "Hey {first_name}, heads up — your pre-approval expires tomorrow. I can renew it in minutes. Just say the word!"},
            ],
        },
    ],
    "exit_conditions": ["Pre-approval renewed", "Loan application submitted", "STOP received"],
}

HELOC_LEAD_SEQUENCE = {
    "name": "HELOC Lead - 6 Month Nurture",
    "description": "Educate and nurture homeowners interested in home equity lines of credit",
    "phases": [
        {
            "name": "Phase 1 - Education",
            "days_range": "0-7",
            "frequency": "daily",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "heloc_intro",
                 "content": "Hi {first_name}, thanks for your HELOC inquiry! I'm {lo_name}. I can give you a quick estimate of your available equity. What's your property address? Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "heloc_vs_cashout", "content": None},
                {"day": 3, "channel": "sms", "template": "heloc_uses",
                 "content": "Did you know a HELOC can be used for home improvements, debt consolidation, or even investment? Let's explore your options."},
                {"day": 5, "channel": "email", "template": "heloc_tax_benefits", "content": None},
            ],
        },
        {
            "name": "Phase 2 - Rate Watch",
            "days_range": "8-180",
            "frequency": "biweekly",
            "steps": [
                {"day": 14, "channel": "email", "template": "heloc_rate_comparison", "content": None},
                {"day": 28, "channel": "sms", "template": "heloc_equity_update",
                 "content": "Hi {first_name}, home values in your area just updated. You may have more equity than you think. Want me to check?"},
                {"day": 60, "channel": "email", "template": "heloc_success_story", "content": None},
                {"day": 90, "channel": "sms", "template": "heloc_quarterly",
                 "content": "Hi {first_name}, still considering a HELOC? Rates and your equity position may have changed. Happy to run fresh numbers."},
                {"day": 120, "channel": "email", "template": "heloc_market_update", "content": None},
                {"day": 180, "channel": "email", "template": "heloc_half_year_review", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

FHA_LEAD_SEQUENCE = {
    "name": "FHA First-Time Buyer Nurture",
    "description": "Guide first-time buyers through FHA loan education and preparation",
    "phases": [
        {
            "name": "Phase 1 - FHA Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "fha_intro",
                 "content": "Hi {first_name}, I'm {lo_name}! FHA loans are a great option for first-time buyers — as low as 3.5% down. Want to see what you qualify for? Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "fha_basics_guide", "content": None},
                {"day": 3, "channel": "sms", "template": "fha_down_payment",
                 "content": "Quick tip: Many first-time buyers use down payment assistance programs with FHA loans. I can check what's available in your area."},
                {"day": 7, "channel": "email", "template": "fha_credit_requirements", "content": None},
                {"day": 10, "channel": "email", "template": "fha_vs_conventional", "content": None},
                {"day": 14, "channel": "sms", "template": "fha_preapproval_cta",
                 "content": "Ready to see what you qualify for? FHA pre-approval takes about 10 minutes and gives you a clear budget for house hunting."},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

VA_LEAD_SEQUENCE = {
    "name": "VA Loan - Veteran Nurture",
    "description": "Veteran-specific nurture for VA loan benefits education",
    "phases": [
        {
            "name": "Phase 1 - VA Benefits Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "va_intro",
                 "content": "Hi {first_name}, thank you for your service! I'm {lo_name}. VA loans offer incredible benefits — $0 down, no PMI. Want to learn more? Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "va_benefits_guide", "content": None},
                {"day": 3, "channel": "sms", "template": "va_no_pmi",
                 "content": "One of the best VA benefits: no private mortgage insurance, even with $0 down. That can save you $200+/month compared to conventional."},
                {"day": 7, "channel": "email", "template": "va_coe_guide", "content": None},
                {"day": 10, "channel": "email", "template": "va_funding_fee", "content": None},
                {"day": 14, "channel": "sms", "template": "va_preapproval_cta",
                 "content": "Ready to use your VA benefit? Pre-approval is quick and I handle the COE for you. Let me know!"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

RATE_WATCH_SEQUENCE = {
    "name": "Rate Watch Alerts",
    "description": "Automated rate movement alerts for rate-sensitive leads",
    "phases": [
        {
            "name": "Weekly Rate Alerts",
            "days_range": "0-180",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "rate_watch_enrollment", "content": None},
                {"day": 7, "channel": "email", "template": "weekly_rate_update", "content": None},
                {"day": 14, "channel": "email", "template": "weekly_rate_update", "content": None},
                {"day": 21, "channel": "sms", "template": "rate_movement",
                 "content": "Hi {first_name}, rates moved this week. Current 30yr fixed is around {current_rate}%. Want me to update your scenario?"},
            ],
        },
    ],
    "exit_conditions": ["Lead applies for loan", "STOP received", "6 months without engagement"],
}

BIRTHDAY_ANNIVERSARY_SEQUENCE = {
    "name": "Birthday & Home Anniversary",
    "description": "Personal touch milestones for relationship building",
    "phases": [
        {
            "name": "Milestone Messages",
            "days_range": "annual",
            "frequency": "annual",
            "steps": [
                {"day": 0, "channel": "sms", "template": "birthday",
                 "content": "Happy birthday, {first_name}! Wishing you a wonderful day. - {lo_name}"},
                {"day": 0, "channel": "email", "template": "birthday_email", "content": None},
            ],
        },
    ],
    "exit_conditions": ["STOP received"],
}

CLOSING_ANNIVERSARY_SEQUENCE = {
    "name": "Closing Anniversary - Annual",
    "description": "Annual closing anniversary with home value update and referral ask",
    "phases": [
        {
            "name": "Anniversary Outreach",
            "days_range": "annual",
            "frequency": "annual",
            "steps": [
                {"day": 0, "channel": "email", "template": "closing_anniversary_email", "content": None},
                {"day": 0, "channel": "sms", "template": "closing_anniversary_sms",
                 "content": "Happy home anniversary, {first_name}! It's been {years} year(s) since closing. Your home has likely gained value — want a quick equity check?"},
                {"day": 3, "channel": "email", "template": "equity_update_annual", "content": None},
            ],
        },
    ],
    "exit_conditions": ["STOP received", "New loan application"],
}

REALTOR_PARTNER_COMARKETING = {
    "name": "Realtor Partner Co-Marketing",
    "description": "Co-branded outreach with realtor partners for shared leads",
    "phases": [
        {
            "name": "Co-Marketing Outreach",
            "days_range": "0-90",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "comarketing_intro",
                 "content": None},
                {"day": 14, "channel": "email", "template": "comarketing_market_update", "content": None},
                {"day": 28, "channel": "email", "template": "comarketing_buyer_tips", "content": None},
                {"day": 42, "channel": "email", "template": "comarketing_open_house", "content": None},
                {"day": 56, "channel": "email", "template": "comarketing_success_story", "content": None},
                {"day": 70, "channel": "email", "template": "comarketing_quarterly_recap", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Partner relationship ended", "STOP received"],
}

PAST_CLIENT_ANNUAL_REVIEW = {
    "name": "Past Client Annual Mortgage Review",
    "description": "Annual outreach to past clients for rate review and referral opportunity",
    "phases": [
        {
            "name": "Annual Review",
            "days_range": "annual",
            "frequency": "annual",
            "steps": [
                {"day": 0, "channel": "email", "template": "annual_review_invite", "content": None},
                {"day": 3, "channel": "sms", "template": "annual_review_sms",
                 "content": "Hi {first_name}, it's time for your annual mortgage review! Rates may have changed since we last spoke. Want a free rate check? - {lo_name}"},
                {"day": 7, "channel": "email", "template": "annual_review_followup", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Review completed", "New loan application", "STOP received"],
}

LOST_LEAD_RECOVERY = {
    "name": "Lost Lead Recovery",
    "description": "Win-back sequence for leads who chose another lender or went cold",
    "phases": [
        {
            "name": "Recovery Outreach",
            "days_range": "0-60",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "lost_lead_check_in", "content": None},
                {"day": 14, "channel": "sms", "template": "lost_lead_sms",
                 "content": "Hi {first_name}, it's {lo_name}. I know we didn't connect last time, but I'm still here if your plans change. No pressure — just want you to know."},
                {"day": 30, "channel": "email", "template": "lost_lead_value_add", "content": None},
                {"day": 60, "channel": "email", "template": "lost_lead_final", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Lead re-engages", "STOP received", "60 days without response → move to long nurture"],
}

REVIEW_REQUEST_SEQUENCE = {
    "name": "Post-Close Review Request",
    "description": "Request Google/Zillow reviews after successful closing",
    "phases": [
        {
            "name": "Review Request",
            "days_range": "7-30 post-close",
            "frequency": "weekly",
            "steps": [
                {"day": 7, "channel": "sms", "template": "review_request_sms",
                 "content": "Hi {first_name}, congratulations again on your new home! If you had a great experience, would you mind leaving a quick review? It really helps: {review_link}"},
                {"day": 14, "channel": "email", "template": "review_request_email", "content": None},
                {"day": 30, "channel": "sms", "template": "review_reminder",
                 "content": "Hi {first_name}, just a gentle reminder — a quick review means the world to me: {review_link}. Thank you!"},
            ],
        },
    ],
    "exit_conditions": ["Review submitted", "STOP received"],
}

JUMBO_LEAD_SEQUENCE = {
    "name": "Jumbo Loan - High-Value Nurture",
    "description": "Premium nurture for high-net-worth borrowers seeking jumbo financing",
    "phases": [
        {
            "name": "Phase 1 - White Glove",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "jumbo_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. For homes above the conforming limit, jumbo loans offer competitive rates with flexible terms. Let's discuss your options. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "jumbo_guide", "content": None},
                {"day": 5, "channel": "email", "template": "jumbo_asset_based", "content": None},
                {"day": 10, "channel": "sms", "template": "jumbo_portfolio",
                 "content": "Did you know portfolio jumbo lenders can be more flexible on income documentation? Let me match you with the right fit."},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

USDA_LEAD_SEQUENCE = {
    "name": "USDA Rural Development Nurture",
    "description": "Educate eligible borrowers on USDA zero-down rural loans",
    "phases": [
        {
            "name": "Phase 1 - USDA Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "usda_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. If you're buying in an eligible area, USDA loans offer $0 down and low rates! Want me to check eligibility for your area? Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "usda_eligibility_guide", "content": None},
                {"day": 5, "channel": "email", "template": "usda_income_limits", "content": None},
                {"day": 10, "channel": "sms", "template": "usda_preapproval_cta",
                 "content": "USDA loans: $0 down, competitive rates, and no PMI. If your area qualifies, this could save you thousands. Want to check?"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

# Template registry
ALL_TEMPLATES = {
    "purchase_12_month": PURCHASE_LEAD_SEQUENCE,
    "refinance_12_month": REFINANCE_LEAD_SEQUENCE,
    "post_close": POST_CLOSE_SEQUENCE,
    "reengagement": REENGAGEMENT_SEQUENCE,
    "pre_approval_expiration": PRE_APPROVAL_EXPIRATION_SEQUENCE,
    "heloc_6_month": HELOC_LEAD_SEQUENCE,
    "fha_first_time_buyer": FHA_LEAD_SEQUENCE,
    "va_veteran": VA_LEAD_SEQUENCE,
    "rate_watch_alerts": RATE_WATCH_SEQUENCE,
    "birthday_anniversary": BIRTHDAY_ANNIVERSARY_SEQUENCE,
    "closing_anniversary": CLOSING_ANNIVERSARY_SEQUENCE,
    "realtor_comarketing": REALTOR_PARTNER_COMARKETING,
    "past_client_annual_review": PAST_CLIENT_ANNUAL_REVIEW,
    "lost_lead_recovery": LOST_LEAD_RECOVERY,
    "post_close_review_request": REVIEW_REQUEST_SEQUENCE,
    "jumbo_high_value": JUMBO_LEAD_SEQUENCE,
    "usda_rural": USDA_LEAD_SEQUENCE,
}


def get_template(name: str) -> dict:
    """Get a campaign template by name."""
    return ALL_TEMPLATES.get(name)


def list_templates() -> list:
    """List all available campaign templates."""
    return [
        {"key": key, "name": t["name"], "description": t["description"]}
        for key, t in ALL_TEMPLATES.items()
    ]
