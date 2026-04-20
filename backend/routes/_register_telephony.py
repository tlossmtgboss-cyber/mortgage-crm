"""
Telephony & Voice route registrations.

Routes: Telnyx, Vapi, AMD, call screening, IVR, conferences, hold music,
call transfers, voice integration, deepgram, voice workflows, dialer.
"""
import logging

logger = logging.getLogger(__name__)


def register_telephony_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register telephony and voice routes."""

    # Include Voice Integration routes
    try:
        from routes.voice_integration_routes import router as voice_integration_router
        app.include_router(voice_integration_router, tags=["Voice Integration"])
        logger.info("Voice Integration routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Voice Integration routes: {e}")

    # Include AMD Outbound Call routes (Telnyx AMD for voicemail detection)
    try:
        from routes.amd_outbound_routes import router as amd_outbound_router
        app.include_router(amd_outbound_router, tags=["AMD Outbound Calls"])
        logger.info("AMD Outbound Call routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AMD Outbound Call routes: {e}")

    # Include Telnyx Webhook routes
    try:
        from routes.telnyx_webhook_routes import router as telnyx_webhook_router
        app.include_router(telnyx_webhook_router, tags=["Telnyx Webhooks"])
        logger.info("Telnyx Webhook routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Telnyx Webhook routes: {e}")

    # Include Call Screening routes
    try:
        from routes.call_screening_routes import router as call_screening_router
        app.include_router(call_screening_router, tags=["Call Screening"])
        logger.info("Call Screening routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Call Screening routes: {e}")

    # Include State Recording Rules routes
    try:
        from routes.state_recording_rules_routes import router as state_recording_rules_router
        app.include_router(state_recording_rules_router, tags=["State Recording Rules"])
        logger.info("State Recording Rules routes loaded")
    except Exception as e:
        logger.warning(f"Could not load State Recording Rules routes: {e}")

    # Include Quote Language Presets routes
    try:
        from routes.quote_language_routes import router as quote_language_router
        app.include_router(quote_language_router, tags=["Quote Language Presets"])
        logger.info("Quote Language Presets routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Quote Language Presets routes: {e}")

    # Include Voice OS API routes
    try:
        from voice_os_routes import router as voice_os_router, set_auth_dependency as set_voice_os_auth
        set_voice_os_auth(get_current_user)
        app.include_router(voice_os_router, tags=["Voice OS"])
    except Exception as e:
        logger.warning(f"Voice OS routes not loaded: {e}")

    # Include Mobile Voice routes
    try:
        from mobile_voice_routes import router as mobile_voice_router
        app.include_router(mobile_voice_router, tags=["Mobile Voice"])
    except Exception as e:
        logger.warning(f"Mobile Voice routes not loaded: {e}")

    # Include Voice Workflow routes
    try:
        from routes.voice_workflow_routes import router as voice_workflow_router, set_dependencies as set_voice_workflow_deps
        set_voice_workflow_deps(get_db)
        app.include_router(voice_workflow_router, tags=["Voice Workflow"])
        logger.info("Voice Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Voice Workflow routes: {e}")

    # Include Hold Music routes
    try:
        from routes.hold_music_routes import router as hold_music_router
        app.include_router(hold_music_router, tags=["Hold Music"])
        logger.info("Hold Music routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Hold Music routes: {e}")

    # Include Call Transfer routes
    try:
        from routes.call_transfer_routes import router as call_transfer_router
        app.include_router(call_transfer_router, tags=["Call Transfers"])
        logger.info("Call Transfer routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Call Transfer routes: {e}")

    # Include IVR routes
    try:
        from routes.ivr_routes import router as ivr_router
        app.include_router(ivr_router, tags=["IVR"])
        logger.info("IVR routes loaded")
    except Exception as e:
        logger.warning(f"Could not load IVR routes: {e}")

    # Include NL IVR routes (Vapi-powered natural language IVR)
    try:
        from routes.nl_ivr_routes import router as nl_ivr_router
        app.include_router(nl_ivr_router, tags=["NL IVR"])
        logger.info("NL IVR routes loaded")
    except Exception as e:
        logger.warning(f"Could not load NL IVR routes: {e}")

    # Include Conference routes
    try:
        from routes.conference_routes import router as conference_router
        app.include_router(conference_router, tags=["Conferences"])
        logger.info("Conference routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Conference routes: {e}")

    # Include Deepgram Voice Agent routes
    try:
        from deepgram_voice_agent import router as deepgram_voice_agent_router
        app.include_router(deepgram_voice_agent_router, tags=["Voice Agent"])
    except Exception as e:
        logger.warning(f"Voice Agent routes not loaded: {e}")

    # Include Vapi AI Receptionist routes
    try:
        from vapi_routes import router as vapi_router
        app.include_router(vapi_router, tags=["Vapi AI"])
    except Exception as e:
        logger.warning(f"Vapi AI routes not loaded: {e}")

    # Include Voice AI Receptionist routes
    try:
        from voice_routes import router as voice_router
        app.include_router(voice_router, tags=["Voice AI"])
    except Exception as e:
        logger.warning(f"Voice AI routes not loaded: {e}")

    # Power Dialer routes -- DISABLED (telephony/router.py is canonical)
    logger.info("Power Dialer routes skipped (telephony/router.py is canonical)")

    # Include Smart Queue routes (intelligent call queue builder)
    try:
        from routes.dialer_smart_queue_routes import router as smart_queue_router
        app.include_router(smart_queue_router, tags=["Smart Queue"])
        logger.info("Smart Queue routes loaded")
    except Exception as e:
        logger.warning(f"Smart Queue routes not loaded: {e}")

    # Include Disposition routes (voice notes + AI summarization)
    try:
        from telephony.disposition_router import router as disposition_router, set_dependencies as set_disposition_deps
        set_disposition_deps(get_db, get_current_user)
        app.include_router(disposition_router, prefix="/api/v1/dialer", tags=["Dialer Dispositions"])
    except Exception as e:
        logger.warning(f"Dialer Dispositions routes not loaded: {e}")

    # Include Dialer Analytics routes
    try:
        from telephony.analytics_router import router as dialer_analytics_router, set_dependencies as set_analytics_deps
        set_analytics_deps(get_db, get_current_user)
        app.include_router(dialer_analytics_router, prefix="/api/v1/dialer", tags=["Dialer Analytics"])
    except Exception as e:
        logger.warning(f"Dialer Analytics routes not loaded: {e}")

    # Include Dialer Admin routes (caller ID management)
    try:
        from telephony.admin_router import router as dialer_admin_router, set_dependencies as set_admin_deps
        set_admin_deps(get_db, get_current_user)
        app.include_router(dialer_admin_router, prefix="/api/v1/dialer", tags=["Dialer Admin"])
    except Exception as e:
        logger.warning(f"Dialer Admin routes not loaded: {e}")

    # Include main Dialer router (TwiML webhooks, click-to-dial, sessions)
    try:
        from telephony.router import router as dialer_main_router, set_dependencies as set_dialer_deps
        set_dialer_deps(get_db, get_current_user)
        app.include_router(dialer_main_router, tags=["Dialer"])
    except Exception as e:
        logger.warning(f"Dialer routes not loaded: {e}")

    # Include ElevenLabs Voice AI routes
    try:
        from routes.elevenlabs_routes import router as elevenlabs_router, set_dependencies as set_elevenlabs_deps
        from database.models import User
        set_elevenlabs_deps(User, get_current_user, get_db)
        app.include_router(elevenlabs_router, tags=["ElevenLabs"])
        logger.info("ElevenLabs routes loaded")
    except Exception as e:
        logger.warning(f"ElevenLabs routes not loaded: {e}")

    # Telnyx Self-Service Setup routes
    try:
        from routes.telnyx_setup_routes import router as telnyx_setup_router, set_dependencies as set_telnyx_setup_deps
        from database.models import User
        set_telnyx_setup_deps(User, get_current_user, get_db)
        app.include_router(telnyx_setup_router, tags=["Telnyx Setup"])
        logger.info("Telnyx Setup routes loaded")
    except Exception as e:
        logger.warning(f"Telnyx Setup routes not loaded: {e}")

    # Retell AI Voice Platform routes
    try:
        from routes.retell_routes import router as retell_router, set_dependencies as set_retell_deps
        from database.models import User
        set_retell_deps(User, get_current_user, get_db)
        app.include_router(retell_router, tags=["Retell AI"])
        logger.info("Retell AI routes loaded")
    except Exception as e:
        logger.warning(f"Retell AI routes not loaded: {e}")

    # Retell AI Webhook routes (dedicated webhook receiver)
    try:
        from routes.retell_webhook_routes import router as retell_webhook_router
        app.include_router(retell_webhook_router, tags=["Retell Webhooks"])
        logger.info("Retell Webhook routes loaded")
    except Exception as e:
        logger.warning(f"Retell Webhook routes not loaded: {e}")

    # Telnyx-Retell Bridge routes
    try:
        from routes.telnyx_retell_routes import router as telnyx_retell_router, set_dependencies as set_telnyx_retell_deps
        from database.models import User
        set_telnyx_retell_deps(User, get_current_user, get_db)
        app.include_router(telnyx_retell_router, tags=["Telnyx-Retell Bridge"])
        logger.info("Telnyx-Retell Bridge routes loaded")
    except Exception as e:
        logger.warning(f"Telnyx-Retell Bridge routes not loaded: {e}")

    # Include Call Routing routes
    try:
        from routes.call_routing_routes import router as call_routing_router
        app.include_router(call_routing_router, tags=["Call Routing"])
        logger.info("Call Routing routes loaded")
    except Exception as e:
        logger.warning(f"Call Routing routes not loaded: {e}")

    # Include Inbound AI Call Answering routes
    try:
        from routes.inbound_ai_routes import router as inbound_ai_router
        app.include_router(inbound_ai_router, tags=["Inbound AI"])
        logger.info("Inbound AI routes loaded")
    except Exception as e:
        logger.warning(f"Inbound AI routes not loaded: {e}")

    # Include Call Recording retrieval routes
    try:
        from routes.call_recording_routes import router as call_recording_router
        from routes.call_recording_routes import lead_recordings_router
        app.include_router(call_recording_router, tags=["Call Recordings"])
        app.include_router(lead_recordings_router, tags=["Call Recordings"])
        logger.info("Call Recording routes loaded")
    except Exception as e:
        logger.warning(f"Call Recording routes not loaded: {e}")

    # Include Conversation Intelligence routes (unified AI for email + SMS)
    try:
        from routes.conversation_intelligence_routes import router as conversation_intelligence_router
        app.include_router(conversation_intelligence_router, tags=["Conversation Intelligence"])
        logger.info("Conversation Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Conversation Intelligence routes: {e}")

    # Include CI Voice routes (call analysis, QA scoring, real-time coaching)
    try:
        from routes.ci_voice_routes import router as ci_voice_router, set_dependencies as set_ci_voice_deps
        set_ci_voice_deps(get_current_user)
        app.include_router(ci_voice_router, tags=["Conversation Intelligence - Voice"])
        logger.info("CI Voice routes loaded")
    except Exception as e:
        logger.warning(f"Could not load CI Voice routes: {e}")

    # Include Live Call Whisper routes
    try:
        from routes.live_call_whisper_routes import router as live_call_whisper_router
        app.include_router(live_call_whisper_router, tags=["Live Call Whisper"])
        logger.info("Live Call Whisper routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Live Call Whisper routes: {e}")

    # Include Call Monitoring routes
    try:
        from routes.call_monitoring_routes import router as call_monitoring_router, set_dependencies as set_call_monitoring_deps
        set_call_monitoring_deps(get_current_user)
        app.include_router(call_monitoring_router, tags=["Call Monitoring"])
        logger.info("Call Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Call Monitoring routes: {e}")

    # Include Recording Consent Gate routes
    try:
        from routes.recording_consent_routes import router as consent_router, set_dependencies as set_consent_deps
        set_consent_deps(get_current_user)
        app.include_router(consent_router, tags=["Call Intelligence Consent"])
        logger.info("Recording Consent routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recording Consent routes: {e}")

    # Include Call Recording routes (mobile app call recording + AI summary)
    try:
        from api.routes.call_recording import router as call_recording_router
        app.include_router(call_recording_router, tags=["Call Recording"])
    except Exception as e:
        logger.warning(f"Could not load call recording routes: {e}")

    # Phase 3 Advanced Features routes
    try:
        from routes.phase3_routes import bi_router, insights_router, compliance_router, webhook_router
        app.include_router(bi_router, tags=["AI Receptionist Analytics"])
        app.include_router(insights_router, tags=["Conversational Insights"])
        app.include_router(compliance_router, tags=["Call Compliance"])
        app.include_router(webhook_router, tags=["Webhook Automation"])
        logger.info("Phase 3 Advanced Features routes loaded")
    except Exception as e:
        logger.warning(f"Phase 3 routes not loaded: {e}")

    # Phase 5 Premium Features & White-Label routes
    try:
        from routes.phase5_routes import escalation_router, qa_router, biometrics_router, tenant_router
        app.include_router(escalation_router, tags=["Live Agent Escalation"])
        app.include_router(qa_router, tags=["Call Quality Assurance"])
        app.include_router(biometrics_router, tags=["Voice Biometrics"])
        app.include_router(tenant_router, tags=["Multi-Tenant Management"])
        logger.info("Phase 5 Premium Features routes loaded")
    except Exception as e:
        logger.warning(f"Phase 5 routes not loaded: {e}")

    # Include Aria Internal Tool routes (agent-to-backend tool calls)
    try:
        from routes.internal.aria_tool_routes import router as aria_tool_router
        app.include_router(aria_tool_router, tags=["Aria Internal"])
        logger.info("Aria Internal Tool routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Tool routes: {e}")

    # Include Aria Internal Call routes
    try:
        from routes.internal.aria_call_routes import router as aria_call_router
        app.include_router(aria_call_router, tags=["Aria Internal Calls"])
        logger.info("Aria Internal Call routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Call routes: {e}")

    # Include Aria Internal Workflow routes
    try:
        from routes.internal.aria_workflow_routes import router as aria_workflow_router
        app.include_router(aria_workflow_router, tags=["Aria Internal Workflows"])
        logger.info("Aria Internal Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Workflow routes: {e}")

    # Include Aria Internal Memory routes
    try:
        from routes.internal.aria_memory_routes import router as aria_memory_router
        app.include_router(aria_memory_router, tags=["Aria Memory Internal"])
        logger.info("Aria Internal Memory routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Aria Internal Memory routes: {e}")

    logger.info("Telephony & Voice route group loaded")
