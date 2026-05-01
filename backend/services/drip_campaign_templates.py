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

# ---------------------------------------------------------------------------
# Loan-Type Specific Nurture Campaigns
# ---------------------------------------------------------------------------

INVESTMENT_PROPERTY_SEQUENCE = {
    "name": "Investment Property Buyer Nurture",
    "description": "Nurture investors looking to purchase rental or flip properties",
    "phases": [
        {
            "name": "Phase 1 - Investor Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "investment_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Investment property financing is my specialty — whether it's your 1st rental or your 10th. Let's discuss your strategy. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "investment_financing_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "investment_down_payment",
                 "content": "Investment tip: Down payment requirements vary from 15-25% depending on property type and occupancy. Want me to run scenarios for your deal?"},
                {"day": 7, "channel": "email", "template": "investment_dscr_vs_conventional", "content": None},
                {"day": 10, "channel": "email", "template": "investment_cash_flow_analysis", "content": None},
                {"day": 14, "channel": "sms", "template": "investment_preapproval_cta",
                 "content": "Ready to lock down financing for your next investment? Pre-approval strengthens your offer with sellers. Let me know!"},
            ],
        },
        {
            "name": "Phase 2 - Deal Flow",
            "days_range": "15-180",
            "frequency": "biweekly",
            "steps": [
                {"day": 28, "channel": "email", "template": "investment_market_trends", "content": None},
                {"day": 42, "channel": "sms", "template": "investment_portfolio_check",
                 "content": "Hi {first_name}, have you found any deals worth analyzing? I can run quick cash flow numbers on any property you're considering."},
                {"day": 60, "channel": "email", "template": "investment_tax_benefits", "content": None},
                {"day": 90, "channel": "email", "template": "investment_rate_update", "content": None},
                {"day": 120, "channel": "sms", "template": "investment_refi_portfolio",
                 "content": "Quick thought: if you already own rentals, refinancing at today's rates could boost your cash flow. Want me to check?"},
                {"day": 180, "channel": "email", "template": "investment_half_year_review", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

SECOND_HOME_SEQUENCE = {
    "name": "Second Home / Vacation Property Nurture",
    "description": "Nurture buyers looking for vacation homes or second residences",
    "phases": [
        {
            "name": "Phase 1 - Second Home Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "second_home_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. A second home is a great investment in your lifestyle! I can walk you through financing options. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "second_home_financing_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "second_home_rates",
                 "content": "Good news — second home rates are often close to primary residence rates, with as little as 10% down. Want to see what you qualify for?"},
                {"day": 7, "channel": "email", "template": "second_home_tax_benefits", "content": None},
                {"day": 10, "channel": "email", "template": "second_home_rental_income", "content": None},
                {"day": 14, "channel": "sms", "template": "second_home_cta",
                 "content": "Whether it's a beach house or a mountain cabin, I can get you pre-approved quickly so you're ready when you find the one. Interested?"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

CONSTRUCTION_LOAN_SEQUENCE = {
    "name": "Construction Loan Nurture",
    "description": "Guide borrowers through the unique construction-to-permanent loan process",
    "phases": [
        {
            "name": "Phase 1 - Construction Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "construction_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Building your dream home? Construction loans work differently from traditional mortgages — I can walk you through it. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "construction_loan_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "construction_one_close",
                 "content": "Pro tip: A one-time-close construction loan saves you from two closings and two sets of fees. Ask me how it works!"},
                {"day": 7, "channel": "email", "template": "construction_builder_requirements", "content": None},
                {"day": 10, "channel": "email", "template": "construction_draw_schedule", "content": None},
                {"day": 14, "channel": "sms", "template": "construction_cta",
                 "content": "Have a builder and lot picked out? Let's get your construction financing pre-approved so your project stays on schedule."},
            ],
        },
        {
            "name": "Phase 2 - Builder Ready",
            "days_range": "15-90",
            "frequency": "biweekly",
            "steps": [
                {"day": 28, "channel": "email", "template": "construction_rate_locks", "content": None},
                {"day": 42, "channel": "sms", "template": "construction_progress",
                 "content": "Hi {first_name}, have you selected a builder yet? I work with many local builders and can share recommendations."},
                {"day": 56, "channel": "email", "template": "construction_timeline_planning", "content": None},
                {"day": 90, "channel": "email", "template": "construction_quarterly_check", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

RENOVATION_203K_SEQUENCE = {
    "name": "FHA 203(k) Renovation Loan Nurture",
    "description": "Educate borrowers on renovation financing to buy and fix up properties",
    "phases": [
        {
            "name": "Phase 1 - 203(k) Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "renovation_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Looking to buy a fixer-upper? An FHA 203(k) loan lets you finance the purchase AND renovations in one mortgage. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "renovation_203k_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "renovation_limited_vs_standard",
                 "content": "FHA 203(k) comes in two flavors: Limited (up to $35k in repairs) and Standard (major renovations). I can help you figure out which fits your project."},
                {"day": 7, "channel": "email", "template": "renovation_contractor_tips", "content": None},
                {"day": 10, "channel": "email", "template": "renovation_eligible_repairs", "content": None},
                {"day": 14, "channel": "sms", "template": "renovation_cta",
                 "content": "Found a property with potential? Let's see if 203(k) financing can turn it into your dream home. Happy to run the numbers!"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

REVERSE_MORTGAGE_SEQUENCE = {
    "name": "Reverse Mortgage (HECM) Nurture",
    "description": "Educate seniors on reverse mortgage options for retirement planning",
    "phases": [
        {
            "name": "Phase 1 - HECM Education",
            "days_range": "0-21",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "reverse_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. A reverse mortgage can turn your home equity into tax-free income — with no monthly payments required. Want to learn more? Reply STOP to opt out."},
                {"day": 2, "channel": "email", "template": "reverse_hecm_basics", "content": None},
                {"day": 5, "channel": "sms", "template": "reverse_myths",
                 "content": "Common myth: \"The bank takes your home.\" Not true — you keep the title and can stay as long as you want. Let me clear up any other concerns."},
                {"day": 9, "channel": "email", "template": "reverse_payout_options", "content": None},
                {"day": 14, "channel": "email", "template": "reverse_eligibility_checklist", "content": None},
                {"day": 21, "channel": "sms", "template": "reverse_counseling_cta",
                 "content": "The first step in a reverse mortgage is a HUD-approved counseling session. I can connect you with a counselor and walk you through the entire process."},
            ],
        },
        {
            "name": "Phase 2 - Decision Support",
            "days_range": "22-120",
            "frequency": "biweekly",
            "steps": [
                {"day": 35, "channel": "email", "template": "reverse_vs_heloc", "content": None},
                {"day": 49, "channel": "sms", "template": "reverse_family_discussion",
                 "content": "Hi {first_name}, many families discuss reverse mortgages together. I'm happy to join a call with you and your family to answer questions."},
                {"day": 70, "channel": "email", "template": "reverse_case_study", "content": None},
                {"day": 90, "channel": "email", "template": "reverse_quarterly_check", "content": None},
                {"day": 120, "channel": "sms", "template": "reverse_gentle_follow",
                 "content": "Hi {first_name}, still considering a reverse mortgage? Your home equity may have grown since we last spoke. Happy to run updated numbers."},
            ],
        },
    ],
    "exit_conditions": ["Counseling session completed", "Application submitted", "STOP received"],
}

ITIN_LOAN_SEQUENCE = {
    "name": "ITIN Loan Nurture",
    "description": "Guide ITIN holders through the home buying process with non-traditional documentation",
    "phases": [
        {
            "name": "Phase 1 - ITIN Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "itin_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Homeownership is possible with an ITIN — no SSN required. I specialize in helping ITIN holders get approved. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "itin_loan_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "itin_documentation",
                 "content": "ITIN loans accept alternative credit history like rent, utilities, and insurance payments. I can help you build your file. Want to get started?"},
                {"day": 7, "channel": "email", "template": "itin_down_payment_options", "content": None},
                {"day": 10, "channel": "email", "template": "itin_success_stories", "content": None},
                {"day": 14, "channel": "sms", "template": "itin_cta",
                 "content": "Ready to explore your options? I've helped many ITIN holders become homeowners. Let's see what you qualify for — no obligation."},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

NON_QM_SEQUENCE = {
    "name": "Non-QM / Alternative Income Nurture",
    "description": "Nurture self-employed and non-traditional income borrowers with non-QM solutions",
    "phases": [
        {
            "name": "Phase 1 - Non-QM Education",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "nonqm_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Self-employed or non-traditional income? I have loan programs that use bank statements instead of tax returns. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "nonqm_program_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "nonqm_bank_statement",
                 "content": "Bank statement loans use 12-24 months of deposits to qualify — no tax returns needed. Great for business owners, freelancers, and gig workers."},
                {"day": 7, "channel": "email", "template": "nonqm_dscr_investors", "content": None},
                {"day": 10, "channel": "email", "template": "nonqm_asset_depletion", "content": None},
                {"day": 14, "channel": "sms", "template": "nonqm_cta",
                 "content": "Been turned down by a traditional lender? Non-QM loans are designed for borrowers like you. Let me show you what's possible."},
            ],
        },
        {
            "name": "Phase 2 - Solution Matching",
            "days_range": "15-90",
            "frequency": "biweekly",
            "steps": [
                {"day": 28, "channel": "email", "template": "nonqm_rate_comparison", "content": None},
                {"day": 42, "channel": "sms", "template": "nonqm_scenario_check",
                 "content": "Hi {first_name}, non-QM rates and programs change frequently. Want me to run your scenario with the latest options?"},
                {"day": 56, "channel": "email", "template": "nonqm_success_story", "content": None},
                {"day": 90, "channel": "email", "template": "nonqm_quarterly_update", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

# ---------------------------------------------------------------------------
# Milestone / Status Update Campaigns
# ---------------------------------------------------------------------------

APPLICATION_RECEIVED_SEQUENCE = {
    "name": "Application Received - Milestone Updates",
    "description": "Keep borrowers informed after application submission through processing",
    "phases": [
        {
            "name": "Application Acknowledgment",
            "days_range": "0-7",
            "frequency": "daily",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "app_received",
                 "content": "Great news, {first_name}! Your mortgage application has been received. I'll be reviewing it today and will reach out with next steps. - {lo_name}"},
                {"day": 0, "channel": "email", "template": "app_received_checklist", "content": None},
                {"day": 1, "channel": "sms", "template": "app_documents_needed",
                 "content": "Hi {first_name}, I've started reviewing your application. I may need a few documents — check your email for the list. The sooner we get them, the faster we move!"},
                {"day": 3, "channel": "email", "template": "app_what_to_expect", "content": None},
                {"day": 7, "channel": "sms", "template": "app_status_update",
                 "content": "Hi {first_name}, quick update on your loan — we're making progress! Feel free to text me anytime with questions. - {lo_name}"},
            ],
        },
    ],
    "exit_conditions": ["Loan moves to processing", "Loan withdrawn", "STOP received"],
}

PROCESSING_UPDATE_SEQUENCE = {
    "name": "Processing Status Updates",
    "description": "Regular status updates while the loan is in processing",
    "phases": [
        {
            "name": "Processing Updates",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "sms", "template": "processing_started",
                 "content": "Hi {first_name}, your loan has moved to processing! Our team is working on verifying everything. I'll keep you posted on progress. - {lo_name}"},
                {"day": 0, "channel": "email", "template": "processing_timeline", "content": None},
                {"day": 7, "channel": "sms", "template": "processing_week1",
                 "content": "Hi {first_name}, processing update: things are moving along. If we need anything from you, I'll reach out right away. No news is good news!"},
                {"day": 14, "channel": "email", "template": "processing_midpoint", "content": None},
                {"day": 21, "channel": "sms", "template": "processing_week3",
                 "content": "Hi {first_name}, we're getting closer! Your file is being prepared for underwriting submission. I'll update you as soon as it's submitted."},
            ],
        },
    ],
    "exit_conditions": ["Submitted to underwriting", "STOP received"],
}

APPRAISAL_ORDERED_SEQUENCE = {
    "name": "Appraisal Ordered - Status Updates",
    "description": "Keep borrowers informed during the appraisal process",
    "phases": [
        {
            "name": "Appraisal Updates",
            "days_range": "0-21",
            "frequency": "as milestones occur",
            "steps": [
                {"day": 0, "channel": "sms", "template": "appraisal_ordered",
                 "content": "Hi {first_name}, the appraisal for {property_address} has been ordered! The appraiser will contact you or your agent to schedule. Typically takes 7-14 days."},
                {"day": 0, "channel": "email", "template": "appraisal_what_to_expect", "content": None},
                {"day": 5, "channel": "sms", "template": "appraisal_scheduled_check",
                 "content": "Hi {first_name}, has the appraiser reached out to schedule yet? Let me know if there are any issues — I can follow up with them."},
                {"day": 10, "channel": "email", "template": "appraisal_tips", "content": None},
                {"day": 14, "channel": "sms", "template": "appraisal_follow_up",
                 "content": "Hi {first_name}, checking on the appraisal status. Once it's completed, I'll review it right away and let you know the results."},
            ],
        },
    ],
    "exit_conditions": ["Appraisal received", "STOP received"],
}

CONDITIONAL_APPROVAL_SEQUENCE = {
    "name": "Conditional Approval - Next Steps",
    "description": "Guide borrowers through clearing underwriting conditions",
    "phases": [
        {
            "name": "Condition Clearing",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "conditional_approval",
                 "content": "Great news, {first_name}! Your loan has received conditional approval! We just need a few items to get to Clear to Close. Check your email for the list."},
                {"day": 0, "channel": "email", "template": "conditions_checklist", "content": None},
                {"day": 2, "channel": "sms", "template": "conditions_reminder",
                 "content": "Hi {first_name}, friendly reminder — the sooner we clear those conditions, the sooner we can schedule your closing. Need help with any of them?"},
                {"day": 5, "channel": "email", "template": "conditions_progress", "content": None},
                {"day": 7, "channel": "sms", "template": "conditions_urgent",
                 "content": "Hi {first_name}, just checking in on those remaining conditions. We want to keep your closing on track. Let me know if you need anything!"},
            ],
        },
    ],
    "exit_conditions": ["All conditions cleared", "Loan suspended", "STOP received"],
}

CLEAR_TO_CLOSE_SEQUENCE = {
    "name": "Clear to Close - Closing Prep",
    "description": "Celebrate CTC milestone and prepare borrower for closing day",
    "phases": [
        {
            "name": "Closing Preparation",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "ctc_congrats",
                 "content": "Congratulations, {first_name}! You are CLEAR TO CLOSE! We're in the final stretch. I'll be coordinating with the title company to schedule your closing."},
                {"day": 0, "channel": "email", "template": "ctc_closing_prep_guide", "content": None},
                {"day": 2, "channel": "sms", "template": "ctc_wire_warning",
                 "content": "IMPORTANT, {first_name}: Never wire funds based on email instructions alone. Always call the title company directly to verify wiring details. Scammers target real estate closings."},
                {"day": 3, "channel": "email", "template": "ctc_what_to_bring", "content": None},
                {"day": 5, "channel": "sms", "template": "ctc_final_walkthrough",
                 "content": "Hi {first_name}, don't forget to schedule your final walkthrough before closing day! Let me know once your closing is confirmed."},
            ],
        },
    ],
    "exit_conditions": ["Loan funded", "STOP received"],
}

FUNDING_CONGRATS_SEQUENCE = {
    "name": "Funding Congratulations - Welcome Home",
    "description": "Celebrate funding and transition to post-close relationship building",
    "phases": [
        {
            "name": "Celebration & Onboarding",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "funded_congrats",
                 "content": "YOUR LOAN HAS FUNDED, {first_name}! Congratulations — you are officially a homeowner! It's been an honor helping you. Enjoy your new home!"},
                {"day": 0, "channel": "email", "template": "funded_welcome_packet", "content": None},
                {"day": 3, "channel": "sms", "template": "funded_first_payment",
                 "content": "Hi {first_name}, heads up — your first mortgage payment will be due on the 1st of next month. Your servicer will send you details. Questions? I'm here!"},
                {"day": 7, "channel": "email", "template": "funded_homeowner_checklist", "content": None},
                {"day": 14, "channel": "sms", "template": "funded_settling_in",
                 "content": "Hi {first_name}, how are you settling in? If you ever have mortgage questions or know someone who needs help buying, don't hesitate to reach out!"},
                {"day": 30, "channel": "email", "template": "funded_30_day_check", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Transition to post-close sequence", "STOP received"],
}

# ---------------------------------------------------------------------------
# Seasonal / Market Campaigns
# ---------------------------------------------------------------------------

SPRING_BUYING_SEASON_SEQUENCE = {
    "name": "Spring Buying Season Campaign",
    "description": "Seasonal campaign targeting spring home buyers with urgency and market data",
    "phases": [
        {
            "name": "Spring Campaign",
            "days_range": "0-60",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "spring_market_outlook", "content": None},
                {"day": 3, "channel": "sms", "template": "spring_inventory_alert",
                 "content": "Hi {first_name}, spring is here and new listings are hitting the market! Pre-approved buyers are getting first pick. Ready to get started? - {lo_name}"},
                {"day": 14, "channel": "email", "template": "spring_rate_snapshot", "content": None},
                {"day": 21, "channel": "sms", "template": "spring_competition",
                 "content": "Spring is the busiest season for home buying. Getting pre-approved now gives you an edge over other buyers. Takes less than 10 minutes!"},
                {"day": 35, "channel": "email", "template": "spring_open_house_tips", "content": None},
                {"day": 49, "channel": "sms", "template": "spring_closing_timeline",
                 "content": "Hi {first_name}, if you start the process now, you could be in your new home before summer. Want to explore your options?"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

YEAR_END_TAX_PLANNING_SEQUENCE = {
    "name": "Year-End Tax Planning & Mortgage",
    "description": "Year-end campaign highlighting mortgage tax benefits and refi opportunities",
    "phases": [
        {
            "name": "Tax Season Outreach",
            "days_range": "0-45",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "year_end_tax_benefits", "content": None},
                {"day": 3, "channel": "sms", "template": "year_end_deductions",
                 "content": "Hi {first_name}, did you know closing on a home before Dec 31 could give you mortgage interest deductions this tax year? Let's talk timing. - {lo_name}"},
                {"day": 14, "channel": "email", "template": "year_end_refi_savings", "content": None},
                {"day": 28, "channel": "sms", "template": "year_end_deadline",
                 "content": "Year-end is approaching! If you're considering a purchase or refinance, now is the time to lock in rates and maximize your tax benefits."},
                {"day": 42, "channel": "email", "template": "year_end_final_push", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

NEW_YEAR_REFI_CHECK_SEQUENCE = {
    "name": "New Year Refinance Check-In",
    "description": "Start-of-year campaign to review rates and refinance opportunities",
    "phases": [
        {
            "name": "New Year Outreach",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "new_year_rate_outlook", "content": None},
                {"day": 3, "channel": "sms", "template": "new_year_resolution",
                 "content": "Hi {first_name}, new year, new rates! Have you checked your refinance savings lately? A quick rate check could save you hundreds per month. - {lo_name}"},
                {"day": 14, "channel": "email", "template": "new_year_savings_calculator", "content": None},
                {"day": 21, "channel": "sms", "template": "new_year_equity_check",
                 "content": "Your home has likely appreciated over the past year. More equity = better refi terms. Want me to run the numbers?"},
                {"day": 30, "channel": "email", "template": "new_year_action_plan", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Refinance application submitted", "STOP received"],
}

BACK_TO_SCHOOL_EQUITY_SEQUENCE = {
    "name": "Back-to-School Home Equity Campaign",
    "description": "Late summer campaign promoting home equity for education expenses and upgrades",
    "phases": [
        {
            "name": "Back-to-School Outreach",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "back_to_school_equity", "content": None},
                {"day": 5, "channel": "sms", "template": "back_to_school_heloc",
                 "content": "Hi {first_name}, back-to-school season is here! Your home equity could fund renovations, tuition, or that home office upgrade. Want to explore your options? - {lo_name}"},
                {"day": 14, "channel": "email", "template": "back_to_school_cash_out", "content": None},
                {"day": 21, "channel": "sms", "template": "back_to_school_rates",
                 "content": "HELOC and cash-out refi rates are competitive right now. Tap into your equity for whatever your family needs this fall."},
                {"day": 30, "channel": "email", "template": "back_to_school_comparison", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Application submitted", "STOP received"],
}

HOLIDAY_CLIENT_APPRECIATION_SEQUENCE = {
    "name": "Holiday Client Appreciation",
    "description": "Year-end holiday outreach to past clients for relationship building and referrals",
    "phases": [
        {
            "name": "Holiday Outreach",
            "days_range": "0-21",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "holiday_greeting", "content": None},
                {"day": 0, "channel": "sms", "template": "holiday_sms",
                 "content": "Happy holidays, {first_name}! Wishing you and your family a wonderful season. Thank you for trusting me with your mortgage — it means the world. - {lo_name}"},
                {"day": 7, "channel": "email", "template": "holiday_year_in_review", "content": None},
                {"day": 14, "channel": "sms", "template": "holiday_referral",
                 "content": "Hi {first_name}, if anyone in your circle is thinking about buying or refinancing in the new year, I'd be honored to help. Enjoy the holidays!"},
                {"day": 21, "channel": "email", "template": "holiday_new_year_preview", "content": None},
            ],
        },
    ],
    "exit_conditions": ["STOP received"],
}

# ---------------------------------------------------------------------------
# Re-Engagement Campaigns
# ---------------------------------------------------------------------------

SIX_MONTH_DORMANT_SEQUENCE = {
    "name": "6-Month Dormant Lead Re-Engagement",
    "description": "Re-engage leads who have been inactive for 6 months with fresh value",
    "phases": [
        {
            "name": "6-Month Re-Engagement",
            "days_range": "0-21",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "dormant_6_month_check", "content": None},
                {"day": 3, "channel": "sms", "template": "dormant_6_month_sms",
                 "content": "Hi {first_name}, it's {lo_name}. It's been a few months since we connected. A lot has changed in the market — want a quick update on rates and your options?"},
                {"day": 10, "channel": "email", "template": "dormant_6_month_market_update", "content": None},
                {"day": 14, "channel": "sms", "template": "dormant_6_month_value",
                 "content": "Hi {first_name}, I recently helped someone in a similar situation save over $300/month. If your housing plans have changed, I'm here to help."},
                {"day": 21, "channel": "email", "template": "dormant_6_month_final", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Lead re-engages", "STOP received", "No response → move to 12-month cadence"],
}

TWELVE_MONTH_DORMANT_SEQUENCE = {
    "name": "12-Month Dormant Lead Re-Engagement",
    "description": "Last-chance re-engagement for leads dormant over a year",
    "phases": [
        {
            "name": "12-Month Re-Engagement",
            "days_range": "0-14",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "dormant_12_month_check", "content": None},
                {"day": 3, "channel": "sms", "template": "dormant_12_month_sms",
                 "content": "Hi {first_name}, it's been about a year since we last spoke about your mortgage plans. Still thinking about buying or refinancing? The market looks very different now. - {lo_name}"},
                {"day": 7, "channel": "email", "template": "dormant_12_month_comparison", "content": None},
                {"day": 14, "channel": "sms", "template": "dormant_12_month_final",
                 "content": "Hi {first_name}, I don't want to bother you, so this will be my last check-in for a while. If your plans change, I'm always a text away. - {lo_name}"},
            ],
        },
    ],
    "exit_conditions": ["Lead re-engages", "STOP received", "No response → archive lead"],
}

RATE_IMPROVEMENT_REQUOTE_SEQUENCE = {
    "name": "Rate Improvement Since Last Quote",
    "description": "Re-engage leads when rates drop below their last quoted rate",
    "phases": [
        {
            "name": "Rate Drop Alert",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "rate_drop_alert",
                 "content": "Hi {first_name}, rates have dropped since we last talked! Your scenario could be significantly better now. Want me to run updated numbers? - {lo_name}"},
                {"day": 0, "channel": "email", "template": "rate_drop_comparison", "content": None},
                {"day": 3, "channel": "sms", "template": "rate_drop_savings",
                 "content": "Quick update: based on your last scenario, the rate improvement could save you around {savings_estimate}/month. Worth a fresh look?"},
                {"day": 7, "channel": "email", "template": "rate_drop_urgency", "content": None},
                {"day": 14, "channel": "sms", "template": "rate_drop_final",
                 "content": "Hi {first_name}, rates can move quickly. If you want to take advantage of today's lower rates, let me know and I can lock you in fast."},
            ],
        },
    ],
    "exit_conditions": ["Lead re-engages", "Rates move back up", "STOP received"],
}

# ---------------------------------------------------------------------------
# Education-Focused Campaigns
# ---------------------------------------------------------------------------

FIRST_TIME_BUYER_EDUCATION_SEQUENCE = {
    "name": "First-Time Buyer Education Series",
    "description": "Comprehensive education drip for first-time home buyers covering the entire process",
    "phases": [
        {
            "name": "Phase 1 - Foundations",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "ftb_welcome",
                 "content": "Hi {first_name}, I'm {lo_name}! Buying your first home is exciting. I'm going to walk you through the entire process step by step. Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "ftb_buying_process_overview", "content": None},
                {"day": 4, "channel": "sms", "template": "ftb_credit_tip",
                 "content": "First-time buyer tip #1: Check your credit score before you start. Even small improvements can lower your rate and save you thousands. Want me to review your credit?"},
                {"day": 7, "channel": "email", "template": "ftb_loan_types_explained", "content": None},
                {"day": 10, "channel": "email", "template": "ftb_down_payment_myths", "content": None},
                {"day": 14, "channel": "sms", "template": "ftb_preapproval_importance",
                 "content": "Tip #2: Get pre-approved BEFORE you start house hunting. It shows sellers you're serious and gives you a clear budget. Takes about 10 minutes!"},
            ],
        },
        {
            "name": "Phase 2 - Deep Dive",
            "days_range": "15-60",
            "frequency": "weekly",
            "steps": [
                {"day": 21, "channel": "email", "template": "ftb_closing_costs_explained", "content": None},
                {"day": 28, "channel": "sms", "template": "ftb_home_inspection",
                 "content": "Tip #3: Never skip the home inspection! It can save you from costly surprises. I can recommend trusted inspectors in your area."},
                {"day": 35, "channel": "email", "template": "ftb_making_an_offer", "content": None},
                {"day": 42, "channel": "email", "template": "ftb_appraisal_explained", "content": None},
                {"day": 49, "channel": "sms", "template": "ftb_earnest_money",
                 "content": "Tip #4: Earnest money (usually 1-3% of purchase price) shows the seller you're serious. It goes toward your down payment at closing."},
                {"day": 56, "channel": "email", "template": "ftb_closing_day_guide", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

CREDIT_IMPROVEMENT_SEQUENCE = {
    "name": "Credit Improvement Tips Series",
    "description": "Help leads improve their credit score to qualify for better rates",
    "phases": [
        {
            "name": "Credit Building",
            "days_range": "0-90",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "credit_score_basics", "content": None},
                {"day": 3, "channel": "sms", "template": "credit_tip_1",
                 "content": "Credit tip: Payment history is 35% of your score. Set up autopay on all accounts to never miss a payment. Small step, big impact! - {lo_name}"},
                {"day": 14, "channel": "email", "template": "credit_utilization_guide", "content": None},
                {"day": 21, "channel": "sms", "template": "credit_tip_2",
                 "content": "Credit tip: Keep credit card balances below 30% of your limit. Below 10% is even better. This alone can boost your score 20-50 points."},
                {"day": 35, "channel": "email", "template": "credit_disputes_guide", "content": None},
                {"day": 49, "channel": "sms", "template": "credit_tip_3",
                 "content": "Credit tip: Don't close old credit cards — account age matters. And avoid opening new accounts while preparing to buy a home."},
                {"day": 63, "channel": "email", "template": "credit_rapid_rescore", "content": None},
                {"day": 77, "channel": "sms", "template": "credit_check_in",
                 "content": "Hi {first_name}, have you been working on your credit? I can pull your score and see where you stand for a mortgage. Ready for a check-up?"},
                {"day": 90, "channel": "email", "template": "credit_90_day_review", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Credit score reaches target", "Pre-approval application", "STOP received"],
}

DOWN_PAYMENT_ASSISTANCE_SEQUENCE = {
    "name": "Down Payment Assistance Programs",
    "description": "Educate buyers on DPA grants, bonds, and assistance programs available in their area",
    "phases": [
        {
            "name": "DPA Education",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "dpa_overview", "content": None},
                {"day": 3, "channel": "sms", "template": "dpa_intro_sms",
                 "content": "Hi {first_name}, did you know there are programs that can help cover your down payment? Some offer grants you don't have to repay. Want me to check what's available in your area? - {lo_name}"},
                {"day": 10, "channel": "email", "template": "dpa_state_programs", "content": None},
                {"day": 14, "channel": "sms", "template": "dpa_eligibility",
                 "content": "Many DPA programs have income limits up to $100k+. Even if you don't think you qualify, it's worth checking — you might be surprised!"},
                {"day": 21, "channel": "email", "template": "dpa_combined_with_fha", "content": None},
                {"day": 28, "channel": "sms", "template": "dpa_cta",
                 "content": "I've helped many buyers use DPA programs to get into their first home with little to nothing out of pocket. Want to see your options?"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

# ---------------------------------------------------------------------------
# Co-Marketing Campaigns
# ---------------------------------------------------------------------------

OPEN_HOUSE_FOLLOW_UP_SEQUENCE = {
    "name": "Open House Follow-Up",
    "description": "Follow up with leads captured at open house events",
    "phases": [
        {
            "name": "Post-Open House",
            "days_range": "0-14",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 30, "channel": "sms", "template": "open_house_thanks",
                 "content": "Hi {first_name}, thanks for visiting the open house today! I'm {lo_name}, the lender working with the listing agent. Happy to answer any mortgage questions about this property or others."},
                {"day": 1, "channel": "email", "template": "open_house_financing_overview", "content": None},
                {"day": 3, "channel": "sms", "template": "open_house_preapproval",
                 "content": "Hi {first_name}, interested in the home you saw? Getting pre-approved is the first step to making a competitive offer. It takes about 10 minutes!"},
                {"day": 7, "channel": "email", "template": "open_house_market_context", "content": None},
                {"day": 14, "channel": "sms", "template": "open_house_still_looking",
                 "content": "Hi {first_name}, still looking at homes? I can get you pre-approved so you're ready to act when you find the right one. No obligation!"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

LISTING_AGENT_INTRODUCTION_SEQUENCE = {
    "name": "Listing Agent Partnership Introduction",
    "description": "Introduce your lending services to listing agents for referral partnerships",
    "phases": [
        {
            "name": "Agent Introduction",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "agent_intro_value_prop", "content": None},
                {"day": 3, "channel": "sms", "template": "agent_intro_sms",
                 "content": "Hi {first_name}, I'm {lo_name} with {company_name}. I help agents close deals faster with same-day pre-approvals and reliable on-time closings. Can I buy you a coffee?"},
                {"day": 10, "channel": "email", "template": "agent_closing_stats", "content": None},
                {"day": 17, "channel": "sms", "template": "agent_comarketing_offer",
                 "content": "I offer free co-branded marketing materials, open house support, and buyer seminars. Would you be open to exploring a partnership?"},
                {"day": 24, "channel": "email", "template": "agent_testimonials", "content": None},
                {"day": 30, "channel": "sms", "template": "agent_final_touch",
                 "content": "Hi {first_name}, just wanted to follow up one more time. I'd love the chance to earn your referrals by delivering a great experience for your buyers. - {lo_name}"},
            ],
        },
    ],
    "exit_conditions": ["Agent responds", "Partnership established", "STOP received"],
}

BUILDER_PARTNERSHIP_SEQUENCE = {
    "name": "Builder Partnership Nurture",
    "description": "Develop lending partnerships with home builders and developers",
    "phases": [
        {
            "name": "Builder Outreach",
            "days_range": "0-45",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "builder_intro", "content": None},
                {"day": 5, "channel": "sms", "template": "builder_intro_sms",
                 "content": "Hi {first_name}, I'm {lo_name} with {company_name}. I specialize in construction and new-build financing. Can we discuss how I can help your buyers close smoothly?"},
                {"day": 14, "channel": "email", "template": "builder_value_proposition", "content": None},
                {"day": 28, "channel": "sms", "template": "builder_onsite_offer",
                 "content": "I offer on-site pre-approval events for your model homes and communities. Your buyers get approved on the spot. Interested?"},
                {"day": 42, "channel": "email", "template": "builder_case_studies", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Builder responds", "Partnership established", "STOP received"],
}

FINANCIAL_PLANNER_REFERRAL_SEQUENCE = {
    "name": "Financial Planner Referral Partnership",
    "description": "Build referral relationships with financial planners and wealth advisors",
    "phases": [
        {
            "name": "Financial Planner Outreach",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "fp_intro_partnership", "content": None},
                {"day": 5, "channel": "sms", "template": "fp_intro_sms",
                 "content": "Hi {first_name}, I'm {lo_name}. Many financial planners partner with me to ensure their clients get the best mortgage strategy aligned with their overall financial plan. Coffee?"},
                {"day": 14, "channel": "email", "template": "fp_client_scenarios", "content": None},
                {"day": 21, "channel": "sms", "template": "fp_mutual_referral",
                 "content": "A mortgage is often the biggest financial decision your clients make. I provide detailed analysis so they can see how it fits their wealth strategy. Want to discuss?"},
                {"day": 30, "channel": "email", "template": "fp_joint_seminar", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Planner responds", "Partnership established", "STOP received"],
}

# ---------------------------------------------------------------------------
# Compliance Campaigns
# ---------------------------------------------------------------------------

ESCROW_ANALYSIS_REMINDER_SEQUENCE = {
    "name": "Annual Escrow Analysis Reminder",
    "description": "Remind homeowners about annual escrow analysis and potential payment changes",
    "phases": [
        {
            "name": "Escrow Notification",
            "days_range": "0-14",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "escrow_analysis_annual", "content": None},
                {"day": 3, "channel": "sms", "template": "escrow_analysis_sms",
                 "content": "Hi {first_name}, your annual escrow analysis is coming up. This could affect your monthly payment. Want me to review it and explain any changes? - {lo_name}"},
                {"day": 7, "channel": "email", "template": "escrow_shortage_options", "content": None},
                {"day": 14, "channel": "sms", "template": "escrow_follow_up",
                 "content": "Hi {first_name}, did you receive your escrow analysis statement? If your payment changed and you have questions, I'm happy to walk through it with you."},
            ],
        },
    ],
    "exit_conditions": ["Client responds", "Analysis reviewed", "STOP received"],
}

PMI_REMOVAL_NOTIFICATION_SEQUENCE = {
    "name": "PMI Removal Notification",
    "description": "Alert homeowners when they may be eligible to remove private mortgage insurance",
    "phases": [
        {
            "name": "PMI Removal Outreach",
            "days_range": "0-21",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "pmi_removal_eligible", "content": None},
                {"day": 0, "channel": "sms", "template": "pmi_removal_alert",
                 "content": "Hi {first_name}, great news! Based on your home's value and loan balance, you may be eligible to drop your PMI — that could save you ${pmi_amount}/month! - {lo_name}"},
                {"day": 7, "channel": "email", "template": "pmi_removal_process", "content": None},
                {"day": 14, "channel": "sms", "template": "pmi_removal_action",
                 "content": "Hi {first_name}, removing PMI is usually straightforward — you may just need a new appraisal. Want me to walk you through the steps?"},
                {"day": 21, "channel": "email", "template": "pmi_removal_comparison", "content": None},
            ],
        },
    ],
    "exit_conditions": ["PMI removal requested", "Refinance application", "STOP received"],
}

ARM_ADJUSTMENT_NOTIFICATION_SEQUENCE = {
    "name": "ARM Adjustment Notification",
    "description": "Proactively notify borrowers before their adjustable rate mortgage adjusts",
    "phases": [
        {
            "name": "ARM Adjustment Alert",
            "days_range": "180-0 before adjustment",
            "frequency": "decreasing interval",
            "steps": [
                {"day": -180, "channel": "email", "template": "arm_6_month_warning", "content": None},
                {"day": -180, "channel": "sms", "template": "arm_6_month_sms",
                 "content": "Hi {first_name}, your ARM adjusts in about 6 months. Now is a great time to explore refinancing to a fixed rate and lock in predictable payments. - {lo_name}"},
                {"day": -90, "channel": "email", "template": "arm_3_month_analysis", "content": None},
                {"day": -90, "channel": "sms", "template": "arm_3_month_sms",
                 "content": "Hi {first_name}, 3 months until your rate adjusts. Based on current indexes, your payment could change significantly. Want me to run a fixed-rate comparison?"},
                {"day": -30, "channel": "email", "template": "arm_1_month_urgent", "content": None},
                {"day": -30, "channel": "sms", "template": "arm_1_month_sms",
                 "content": "IMPORTANT: {first_name}, your ARM adjusts next month. If you want to refinance to a fixed rate, we need to act now to close in time. Call me: {lo_phone}"},
            ],
        },
    ],
    "exit_conditions": ["Refinance application submitted", "Client declines to refinance", "STOP received"],
}

# ---------------------------------------------------------------------------
# Additional Specialty Campaigns
# ---------------------------------------------------------------------------

DEBT_CONSOLIDATION_SEQUENCE = {
    "name": "Debt Consolidation Refinance",
    "description": "Nurture homeowners who could benefit from consolidating debt through a cash-out refinance",
    "phases": [
        {
            "name": "Debt Consolidation Education",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "debt_consolidation_intro", "content": None},
                {"day": 3, "channel": "sms", "template": "debt_consolidation_sms",
                 "content": "Hi {first_name}, carrying high-interest credit card debt? A cash-out refinance could consolidate it into one low payment. Want to see the math? - {lo_name}"},
                {"day": 10, "channel": "email", "template": "debt_consolidation_savings", "content": None},
                {"day": 17, "channel": "sms", "template": "debt_consolidation_example",
                 "content": "Example: $30k in credit card debt at 22% APR = $550/month in interest alone. Rolled into your mortgage at {rate}%, that drops dramatically. Want your numbers?"},
                {"day": 24, "channel": "email", "template": "debt_consolidation_case_study", "content": None},
                {"day": 30, "channel": "sms", "template": "debt_consolidation_cta",
                 "content": "Hi {first_name}, I can run a free debt consolidation analysis for you in minutes. No obligation. Just reply or call me at {lo_phone}."},
            ],
        },
    ],
    "exit_conditions": ["Application submitted", "Client declines", "STOP received"],
}

DIVORCE_MORTGAGE_SEQUENCE = {
    "name": "Divorce Mortgage Solutions",
    "description": "Sensitive outreach for borrowers navigating divorce and mortgage decisions",
    "phases": [
        {
            "name": "Sensitive Outreach",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "divorce_mortgage_options", "content": None},
                {"day": 5, "channel": "sms", "template": "divorce_intro_sms",
                 "content": "Hi {first_name}, I'm {lo_name}. I understand you may be navigating some changes. I specialize in helping people through mortgage transitions with care and discretion. I'm here if you need me."},
                {"day": 14, "channel": "email", "template": "divorce_refinance_buyout", "content": None},
                {"day": 21, "channel": "sms", "template": "divorce_options_sms",
                 "content": "Hi {first_name}, whether you're refinancing to remove a co-borrower or buying a new home, I can guide you through the process confidentially. No rush — I'm here when you're ready."},
                {"day": 30, "channel": "email", "template": "divorce_fresh_start", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Client engages", "STOP received"],
}

RELOCATION_SEQUENCE = {
    "name": "Relocation Buyer Nurture",
    "description": "Assist buyers relocating for work with time-sensitive home purchase guidance",
    "phases": [
        {
            "name": "Relocation Support",
            "days_range": "0-21",
            "frequency": "every few days",
            "steps": [
                {"day": 0, "delay_min": 0, "channel": "sms", "template": "relocation_intro",
                 "content": "Hi {first_name}, I'm {lo_name}. Relocating can be stressful — I specialize in helping relocation buyers close quickly and smoothly. Let me take the mortgage piece off your plate! Reply STOP to opt out."},
                {"day": 1, "channel": "email", "template": "relocation_guide", "content": None},
                {"day": 4, "channel": "sms", "template": "relocation_remote_process",
                 "content": "Good news: the entire mortgage process can be done remotely! Digital application, e-signatures, and virtual closings available. No need to fly back and forth."},
                {"day": 7, "channel": "email", "template": "relocation_market_intro", "content": None},
                {"day": 10, "channel": "sms", "template": "relocation_timeline",
                 "content": "Typical relocation timeline: pre-approval (day 1), house hunting (weeks 1-3), offer to close (30-45 days). Let's get started so you're settled by your start date."},
                {"day": 14, "channel": "email", "template": "relocation_employer_benefits", "content": None},
                {"day": 21, "channel": "sms", "template": "relocation_agent_connection",
                 "content": "Hi {first_name}, I work with great agents in your new area. Want me to connect you with someone who knows the neighborhoods? Happy to help!"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

NEWLYWED_FIRST_HOME_SEQUENCE = {
    "name": "Newlywed First Home Buyer",
    "description": "Congratulate newlyweds and guide them toward their first home purchase",
    "phases": [
        {
            "name": "Newlywed Nurture",
            "days_range": "0-60",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "newlywed_congrats", "content": None},
                {"day": 3, "channel": "sms", "template": "newlywed_intro_sms",
                 "content": "Congratulations on your marriage, {first_name}! When you're ready to find your first home together, I'd love to help. No rush — enjoy the honeymoon first! - {lo_name}"},
                {"day": 14, "channel": "email", "template": "newlywed_buying_guide", "content": None},
                {"day": 28, "channel": "sms", "template": "newlywed_combined_income",
                 "content": "Fun fact: combining incomes on a mortgage application can significantly increase your buying power. Want to see what you two qualify for together?"},
                {"day": 42, "channel": "email", "template": "newlywed_financial_planning", "content": None},
                {"day": 56, "channel": "sms", "template": "newlywed_cta",
                 "content": "Hi {first_name}, when you're ready to start looking for your first home together, pre-approval takes just 10 minutes. I'm here whenever you're ready!"},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

GROWING_FAMILY_UPGRADE_SEQUENCE = {
    "name": "Growing Family - Home Upgrade",
    "description": "Target existing homeowners who may need to upsize for a growing family",
    "phases": [
        {
            "name": "Upgrade Outreach",
            "days_range": "0-45",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "growing_family_upgrade", "content": None},
                {"day": 5, "channel": "sms", "template": "growing_family_sms",
                 "content": "Hi {first_name}, growing family means you might be outgrowing your current home! With today's equity, moving up could be easier than you think. - {lo_name}"},
                {"day": 14, "channel": "email", "template": "growing_family_equity_analysis", "content": None},
                {"day": 28, "channel": "sms", "template": "growing_family_bridge",
                 "content": "Worried about selling and buying at the same time? I have bridge financing options that let you buy first, then sell. Want to learn more?"},
                {"day": 42, "channel": "email", "template": "growing_family_neighborhoods", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

EMPTY_NESTER_DOWNSIZE_SEQUENCE = {
    "name": "Empty Nester - Downsize & Unlock Equity",
    "description": "Help empty nesters explore downsizing options and equity strategies",
    "phases": [
        {
            "name": "Downsize Education",
            "days_range": "0-45",
            "frequency": "biweekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "empty_nester_options", "content": None},
                {"day": 5, "channel": "sms", "template": "empty_nester_sms",
                 "content": "Hi {first_name}, thinking about downsizing? You've built incredible equity that could fund a simpler lifestyle — or a dream retirement. Let me show you the possibilities. - {lo_name}"},
                {"day": 14, "channel": "email", "template": "empty_nester_equity_report", "content": None},
                {"day": 28, "channel": "sms", "template": "empty_nester_options_sms",
                 "content": "Downsizing options: buy a smaller home outright, invest the difference, or keep a small mortgage for tax benefits. Want to explore which makes sense for you?"},
                {"day": 42, "channel": "email", "template": "empty_nester_lifestyle", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

RENT_VS_BUY_SEQUENCE = {
    "name": "Rent vs. Buy Analysis Campaign",
    "description": "Help renters understand when buying makes more financial sense than renting",
    "phases": [
        {
            "name": "Rent vs Buy Education",
            "days_range": "0-45",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "rent_vs_buy_analysis", "content": None},
                {"day": 3, "channel": "sms", "template": "rent_vs_buy_intro",
                 "content": "Hi {first_name}, paying ${rent_amount}+ in rent? You might be surprised how close that is to a mortgage payment — except you'd be building equity. Want to see the comparison? - {lo_name}"},
                {"day": 10, "channel": "email", "template": "rent_vs_buy_tax_benefits", "content": None},
                {"day": 17, "channel": "sms", "template": "rent_vs_buy_wealth",
                 "content": "Homeowners build an average of $250k+ in wealth over 30 years through appreciation alone. Renters build $0. Ready to switch sides?"},
                {"day": 28, "channel": "email", "template": "rent_vs_buy_low_down", "content": None},
                {"day": 35, "channel": "sms", "template": "rent_vs_buy_programs",
                 "content": "First-time buyer programs offer as little as 3% down, plus DPA grants in many areas. You might be closer to homeownership than you think!"},
                {"day": 42, "channel": "email", "template": "rent_vs_buy_next_steps", "content": None},
            ],
        },
    ],
    "exit_conditions": PURCHASE_LEAD_SEQUENCE["exit_conditions"],
}

CASH_OUT_REFI_SEQUENCE = {
    "name": "Cash-Out Refinance Nurture",
    "description": "Educate homeowners on using equity through cash-out refinancing",
    "phases": [
        {
            "name": "Cash-Out Education",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "cashout_equity_estimate", "content": None},
                {"day": 3, "channel": "sms", "template": "cashout_intro_sms",
                 "content": "Hi {first_name}, your home equity is a powerful financial tool. A cash-out refi lets you access it at mortgage rates — much lower than credit cards or personal loans. - {lo_name}"},
                {"day": 10, "channel": "email", "template": "cashout_use_cases", "content": None},
                {"day": 17, "channel": "sms", "template": "cashout_example",
                 "content": "Popular uses for cash-out: home renovations (adds more value!), paying off high-interest debt, investing, or funding education. What would you use yours for?"},
                {"day": 24, "channel": "email", "template": "cashout_rate_comparison", "content": None},
                {"day": 30, "channel": "sms", "template": "cashout_cta",
                 "content": "Hi {first_name}, I can estimate your available equity and show you cash-out options in minutes. Want to see the numbers? No obligation."},
            ],
        },
    ],
    "exit_conditions": ["Application submitted", "Client declines", "STOP received"],
}

RATE_AND_TERM_REFI_SEQUENCE = {
    "name": "Rate-and-Term Refinance Nurture",
    "description": "Target homeowners who could benefit from a lower rate or shorter term",
    "phases": [
        {
            "name": "Rate/Term Education",
            "days_range": "0-30",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "rate_term_savings_analysis", "content": None},
                {"day": 3, "channel": "sms", "template": "rate_term_intro",
                 "content": "Hi {first_name}, if your current rate is above {rate}%, refinancing could save you real money each month — with no cash out of pocket at closing. Want to check? - {lo_name}"},
                {"day": 10, "channel": "email", "template": "rate_term_break_even", "content": None},
                {"day": 17, "channel": "sms", "template": "rate_term_shorter_term",
                 "content": "Another option: switch from a 30-year to a 15-year mortgage. Higher payment, but you could save tens of thousands in interest and own your home sooner."},
                {"day": 24, "channel": "email", "template": "rate_term_comparison_chart", "content": None},
                {"day": 30, "channel": "sms", "template": "rate_term_cta",
                 "content": "Hi {first_name}, I can run a free refinance comparison in under 5 minutes. See exactly what you'd save. Interested?"},
            ],
        },
    ],
    "exit_conditions": ["Refinance application submitted", "Client declines", "STOP received"],
}

STREAMLINE_REFI_SEQUENCE = {
    "name": "FHA/VA Streamline Refinance",
    "description": "Targeted outreach for FHA or VA borrowers eligible for streamline refinancing",
    "phases": [
        {
            "name": "Streamline Education",
            "days_range": "0-21",
            "frequency": "weekly",
            "steps": [
                {"day": 0, "channel": "email", "template": "streamline_intro", "content": None},
                {"day": 0, "channel": "sms", "template": "streamline_alert",
                 "content": "Hi {first_name}, as an FHA/VA borrower, you may qualify for a Streamline Refinance — less paperwork, no appraisal needed, and potentially a lower rate. Want details? - {lo_name}"},
                {"day": 7, "channel": "email", "template": "streamline_benefits", "content": None},
                {"day": 14, "channel": "sms", "template": "streamline_process",
                 "content": "Streamline refis are the fastest way to lower your rate. Minimal documentation, no income verification in many cases, and we can usually close in 2-3 weeks."},
                {"day": 21, "channel": "email", "template": "streamline_cta", "content": None},
            ],
        },
    ],
    "exit_conditions": ["Application submitted", "Client declines", "STOP received"],
}

# Template registry
ALL_TEMPLATES = {
    # Original 17 templates
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
    # Loan-type specific nurture
    "investment_property": INVESTMENT_PROPERTY_SEQUENCE,
    "second_home": SECOND_HOME_SEQUENCE,
    "construction_loan": CONSTRUCTION_LOAN_SEQUENCE,
    "renovation_203k": RENOVATION_203K_SEQUENCE,
    "reverse_mortgage": REVERSE_MORTGAGE_SEQUENCE,
    "itin_loan": ITIN_LOAN_SEQUENCE,
    "non_qm": NON_QM_SEQUENCE,
    # Milestone / status updates
    "application_received": APPLICATION_RECEIVED_SEQUENCE,
    "processing_update": PROCESSING_UPDATE_SEQUENCE,
    "appraisal_ordered": APPRAISAL_ORDERED_SEQUENCE,
    "conditional_approval": CONDITIONAL_APPROVAL_SEQUENCE,
    "clear_to_close": CLEAR_TO_CLOSE_SEQUENCE,
    "funding_congrats": FUNDING_CONGRATS_SEQUENCE,
    # Seasonal / market
    "spring_buying_season": SPRING_BUYING_SEASON_SEQUENCE,
    "year_end_tax_planning": YEAR_END_TAX_PLANNING_SEQUENCE,
    "new_year_refi_check": NEW_YEAR_REFI_CHECK_SEQUENCE,
    "back_to_school_equity": BACK_TO_SCHOOL_EQUITY_SEQUENCE,
    "holiday_client_appreciation": HOLIDAY_CLIENT_APPRECIATION_SEQUENCE,
    # Re-engagement
    "six_month_dormant": SIX_MONTH_DORMANT_SEQUENCE,
    "twelve_month_dormant": TWELVE_MONTH_DORMANT_SEQUENCE,
    "rate_improvement_requote": RATE_IMPROVEMENT_REQUOTE_SEQUENCE,
    # Education-focused
    "first_time_buyer_education": FIRST_TIME_BUYER_EDUCATION_SEQUENCE,
    "credit_improvement": CREDIT_IMPROVEMENT_SEQUENCE,
    "down_payment_assistance": DOWN_PAYMENT_ASSISTANCE_SEQUENCE,
    # Co-marketing
    "open_house_follow_up": OPEN_HOUSE_FOLLOW_UP_SEQUENCE,
    "listing_agent_introduction": LISTING_AGENT_INTRODUCTION_SEQUENCE,
    "builder_partnership": BUILDER_PARTNERSHIP_SEQUENCE,
    "financial_planner_referral": FINANCIAL_PLANNER_REFERRAL_SEQUENCE,
    # Compliance
    "escrow_analysis_reminder": ESCROW_ANALYSIS_REMINDER_SEQUENCE,
    "pmi_removal_notification": PMI_REMOVAL_NOTIFICATION_SEQUENCE,
    "arm_adjustment_notification": ARM_ADJUSTMENT_NOTIFICATION_SEQUENCE,
    # Additional specialty
    "debt_consolidation": DEBT_CONSOLIDATION_SEQUENCE,
    "divorce_mortgage": DIVORCE_MORTGAGE_SEQUENCE,
    "relocation_buyer": RELOCATION_SEQUENCE,
    "newlywed_first_home": NEWLYWED_FIRST_HOME_SEQUENCE,
    "growing_family_upgrade": GROWING_FAMILY_UPGRADE_SEQUENCE,
    "empty_nester_downsize": EMPTY_NESTER_DOWNSIZE_SEQUENCE,
    "rent_vs_buy": RENT_VS_BUY_SEQUENCE,
    "cash_out_refi": CASH_OUT_REFI_SEQUENCE,
    "rate_and_term_refi": RATE_AND_TERM_REFI_SEQUENCE,
    "streamline_refi": STREAMLINE_REFI_SEQUENCE,
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
