"""
Voice Routes Package

Assembles the voice router from focused sub-modules:
- inbound: Telnyx webhooks, call screening
- browser_ws: Browser voice WebSocket (OpenAI Realtime)
- telnyx_ws: Telnyx voice stream WebSocket
- recording: Call recording, transcripts, voicemail transcription
- dashboard: Config, management, intelligence stubs, voicemail drops
- tool_handlers: CRM function call handlers
- openai_realtime: OpenAI Realtime API connection management
- utils: Shared utilities (mask_phone, webhook validation, etc.)
"""
from fastapi import APIRouter

from .inbound import router as inbound_router
from .browser_ws import router as browser_ws_router
from .telnyx_ws import router as telnyx_ws_router
from .recording import router as recording_router
from .dashboard import router as dashboard_router

# Re-export key symbols for backward compatibility
from .utils import (
    voice_client,
    ai_config,
    mask_phone,
    _validate_webhook_signature,
    _validate_twilio_signature,
    get_models,
    get_current_user_flexible,
)
from .tool_handlers import (
    VoiceToolRateLimiter,
    handle_browser_function_call,
    handle_ai_function_call,
)
from .ci_tools import CI_TOOL_HANDLERS
from .openai_realtime import (
    connect_to_openai_realtime,
    connect_to_openai_realtime_browser,
    extract_lead_info,
)
from .recording import (
    process_call_recording,
    create_call_summary_email_draft,
    submit_to_voice_intelligence,
    submit_to_twilio_intelligence,
    parse_operator_results,
    link_transcript_to_customer,
)
from .telnyx_ws import save_call_summary
from .browser_ws import (
    _ws_connections_lock,
    _ws_connections_by_user,
    _ws_connections_total,
    MAX_WS_PER_USER,
    MAX_WS_PER_ORG,
    MAX_WS_TOTAL,
)

# Assemble the combined router with the same prefix/tags as the original
router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

# Include all sub-routers (they use no prefix since the parent has /api/v1/voice)
router.include_router(inbound_router)
router.include_router(browser_ws_router)
router.include_router(telnyx_ws_router)
router.include_router(recording_router)
router.include_router(dashboard_router)
