"""
Aria Voice Agent Configuration
Guardrails, AMD config, voicemail templates, graduation criteria.
Pure config — no database or service imports.
"""
from typing import Dict, Optional

# --- AMD Confidence Thresholds ------------------------------------------------
AMD_HIGH_CONFIDENCE = 0.92
AMD_MEDIUM_CONFIDENCE = 0.75

# --- Voicemail ----------------------------------------------------------------
MAX_VOICEMAIL_SECONDS = 28  # Telnyx cuts at 30s — 2s buffer

VOICEMAIL_TEMPLATES: Dict[str, str] = {
    "appointment_reminder": (
        "Hi {first_name}, this is Aria from Perennia. "
        "Quick reminder — you have a call with {lo_name} tomorrow at {time}. "
        "If you need to reschedule, just reply to the text I'm sending you now. "
        "Talk soon."
    ),
    "rate_lock_expiry": (
        "Hi {first_name}, Aria from Perennia. "
        "Your rate lock on the {loan_amount} {loan_type} expires {expiry_day}. "
        "{lo_name} has a couple of options to discuss — "
        "call us back at {company_phone} or just reply to my text. "
        "Thanks."
    ),
    "document_chase": (
        "Hi {first_name}, Aria from Perennia. "
        "The one thing holding up your file right now is {top_missing_doc}. "
        "You can upload it directly at the link I'm texting you — takes two minutes. "
        "Any questions, reply to that text. Thanks."
    ),
    "post_close": (
        "Hi {first_name}, Aria from Perennia — just calling to say congratulations "
        "on closing! {lo_name} wanted to check in and make sure everything's going smoothly. "
        "Give us a call at {company_phone} whenever you get a chance. "
        "Enjoy the new home."
    ),
}

# --- Telnyx AMD Configuration ------------------------------------------------
OUTBOUND_CALL_CONFIG = {
    "answering_machine_detection": "premium",
    "answering_machine_detection_config": {
        "total_analysis_time_millis": 6000,
        "after_greeting_silence_millis": 1000,
        "between_words_silence_millis": 1000,
        "greeting_duration_millis": 3500,
        "initial_silence_millis": 4000,
        "maximum_number_of_words": 5,
        "silence_threshold": 256,
    },
    "timeout_secs": 30,
}

# --- Autonomous Call Guardrails -----------------------------------------------
AUTONOMOUS_CALL_GUARDRAILS = {
    "calling_hours": "08:00-20:00 local borrower time",
    "days_allowed": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    "no_call_days": "Federal holidays + state-specific",
    "max_calls_per_lead_day": 1,
    "max_calls_per_lead_week": 3,
    "max_attempts_no_answer": 3,
    "cooling_off_after_dnc": "permanent",
    "permitted_intents": [
        "appointment_reminder",
        "document_chase",
        "rate_lock_expiry_warning",
        "closing_date_reminder",
        "post_close_satisfaction",
    ],
    "never_autonomous": [
        "first_touch",
        "rate_renegotiation",
        "price_objection_handling",
        "complaint_resolution",
        "legal_reference_in_file",
    ],
    "immediate_lo_alert": [
        "borrower_mentions_lawyer",
        "borrower_mentions_complaint",
        "borrower_expresses_distress",
        "dnc_request",
        "three_consecutive_no_answers",
        "call_duration_under_15_seconds",
    ],
}

# --- Graduation Criteria (Phase B -> C) --------------------------------------
GRADUATION_CRITERIA = {
    "appointment_reminder": {
        "min_calls": 50,
        "lo_override_rate": 0.05,
        "call_success_rate": 0.80,
        "complaint_rate": 0.00,
    },
    "rate_lock_reminder": {
        "min_calls": 30,
        "lo_override_rate": 0.08,
        "call_success_rate": 0.75,
        "complaint_rate": 0.00,
    },
    "document_chase": {
        "min_calls": 40,
        "lo_override_rate": 0.10,
        "call_success_rate": 0.70,
        "complaint_rate": 0.00,
    },
}


# --- Helper Functions ---------------------------------------------------------

def render_voicemail_template(template_name: str, context: Dict[str, str]) -> Optional[str]:
    template = VOICEMAIL_TEMPLATES.get(template_name)
    if template is None:
        return None
    try:
        return template.format(**context)
    except KeyError:
        return template.format_map({**{k: "" for k in _extract_placeholders(template)}, **context})


def _extract_placeholders(template: str) -> list:
    import re
    return re.findall(r"\{(\w+)\}", template)


def is_intent_autonomous_eligible(intent: str) -> bool:
    if intent in AUTONOMOUS_CALL_GUARDRAILS["never_autonomous"]:
        return False
    return intent in AUTONOMOUS_CALL_GUARDRAILS["permitted_intents"]


def get_amd_action(result: str, confidence: float) -> str:
    if result == "human":
        return "route_to_agent"
    if result == "machine" and confidence >= AMD_HIGH_CONFIDENCE:
        return "voicemail_full"
    if result == "machine" and confidence >= AMD_MEDIUM_CONFIDENCE:
        return "voicemail_short"
    return "no_voicemail"
