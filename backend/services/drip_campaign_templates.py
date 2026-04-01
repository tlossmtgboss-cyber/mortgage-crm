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

# Template registry
ALL_TEMPLATES = {
    "purchase_12_month": PURCHASE_LEAD_SEQUENCE,
    "refinance_12_month": REFINANCE_LEAD_SEQUENCE,
    "post_close": POST_CLOSE_SEQUENCE,
    "reengagement": REENGAGEMENT_SEQUENCE,
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
