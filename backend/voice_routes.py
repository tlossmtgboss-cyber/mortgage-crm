"""
Voice AI Receptionist Routes
Handles Telnyx voice webhooks and OpenAI Realtime API integration

DECOMPOSED: This file is now a thin re-export wrapper.
All implementation lives in backend/routes/voice/ sub-modules.
"""

# Re-export router and all public symbols for backward compatibility
from routes.voice import (
    # The assembled router (same prefix/tags as before)
    router,
    # Shared state / utilities
    voice_client,
    ai_config,
    mask_phone,
    _validate_webhook_signature,
    _validate_twilio_signature,
    get_models,
    get_current_user_flexible,
    # Tool handlers
    VoiceToolRateLimiter,
    handle_browser_function_call,
    handle_ai_function_call,
    # OpenAI Realtime
    connect_to_openai_realtime,
    connect_to_openai_realtime_browser,
    extract_lead_info,
    # Recording / transcripts
    process_call_recording,
    create_call_summary_email_draft,
    submit_to_voice_intelligence,
    submit_to_twilio_intelligence,
    parse_operator_results,
    link_transcript_to_customer,
    # Telnyx WS helpers
    save_call_summary,
    # WebSocket connection state (H-12)
    _ws_connections_lock,
    _ws_connections_by_user,
    _ws_connections_total,
    MAX_WS_PER_USER,
    MAX_WS_PER_ORG,
    MAX_WS_TOTAL,
)

__all__ = [
    "router",
    "voice_client",
    "ai_config",
    "mask_phone",
    "_validate_webhook_signature",
    "_validate_twilio_signature",
    "get_models",
    "get_current_user_flexible",
    "VoiceToolRateLimiter",
    "handle_browser_function_call",
    "handle_ai_function_call",
    "connect_to_openai_realtime",
    "connect_to_openai_realtime_browser",
    "extract_lead_info",
    "process_call_recording",
    "create_call_summary_email_draft",
    "submit_to_voice_intelligence",
    "submit_to_twilio_intelligence",
    "parse_operator_results",
    "link_transcript_to_customer",
    "save_call_summary",
    "_ws_connections_lock",
    "_ws_connections_by_user",
    "_ws_connections_total",
    "MAX_WS_PER_USER",
    "MAX_WS_PER_ORG",
    "MAX_WS_TOTAL",
]
