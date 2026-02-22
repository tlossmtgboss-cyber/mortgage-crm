"""
Perennia AI - AI Receptionist Module
=====================================
Real-time voice AI system for mortgage CRM.

Components:
- audio_processor: STT/TTS with Deepgram, ElevenLabs, Whisper
- call_handler: Telnyx integration and call routing
- tool_executor: CRM tool integration (160+ Perennia tools)

Usage:
    # Quick start
    from ai_receptionist import create_receptionist

    receptionist = create_receptionist(company_name="My Mortgage Co")

    greeting = await receptionist.handle_incoming_call(
        call_sid="CA123",
        from_number="+15551234567"
    )

    response = await receptionist.process_speech(
        call_sid="CA123",
        speech_text="I'd like to schedule an appointment"
    )

    # Low-level audio processing
    from ai_receptionist import create_audio_processor

    async with create_audio_processor() as processor:
        text = await processor.transcribe_audio(audio_data)
        audio = await processor.synthesize_for_telephony("Hello!")
"""

from .audio_processor import (
    # Core classes
    AudioProcessor,
    VoiceActivityDetector,
    # Configuration
    STTConfig,
    TTSConfig,
    AudioFormat,
    # Providers
    DeepgramSTT,
    WhisperSTT,
    ElevenLabsTTS,
    OpenAITTS,
    # Utilities
    convert_mulaw_to_pcm,
    convert_pcm_to_mulaw,
    create_wav_header,
    audio_to_base64,
    base64_to_audio,
    # Factory
    create_audio_processor,
    # Metrics
    AudioMetrics,
    get_audio_metrics,
    # Convenience functions
    transcribe_audio,
    synthesize_speech,
)

from .call_handler import (
    # State management
    CallState,
    CallDirection,
    CallContext,
    # Handlers
    TelnyxStreamHandler,
    RealtimeConversation,
    # Factory
    create_call_handler,
    # Integration
    handle_voice_stream_websocket,
)

from .tool_executor import (
    # Results
    ToolExecutionResult,
    # Executor
    ReceptionistToolExecutor,
    # Complete system
    AIReceptionist,
    # Testing
    ReceptionistTester,
    # Factory functions
    create_receptionist,
    create_tool_executor,
)

__all__ = [
    # Audio processor
    "AudioProcessor",
    "VoiceActivityDetector",
    "STTConfig",
    "TTSConfig",
    "AudioFormat",
    "DeepgramSTT",
    "WhisperSTT",
    "ElevenLabsTTS",
    "OpenAITTS",
    "convert_mulaw_to_pcm",
    "convert_pcm_to_mulaw",
    "create_wav_header",
    "audio_to_base64",
    "base64_to_audio",
    "create_audio_processor",
    "AudioMetrics",
    "get_audio_metrics",
    "transcribe_audio",
    "synthesize_speech",
    # Call handler
    "CallState",
    "CallDirection",
    "CallContext",
    "TelnyxStreamHandler",
    "RealtimeConversation",
    "create_call_handler",
    "handle_voice_stream_websocket",
    # Tool executor
    "ToolExecutionResult",
    "ReceptionistToolExecutor",
    "AIReceptionist",
    "ReceptionistTester",
    "create_receptionist",
    "create_tool_executor",
]
