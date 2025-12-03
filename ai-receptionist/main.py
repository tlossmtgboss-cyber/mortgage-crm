#!/usr/bin/env python3
"""
================================================================================
PERENNIA AI RECEPTIONIST - MAIN ENTRY POINT
================================================================================
Start the AI Receptionist server with all components configured.

Usage:
    python main.py              # Start server
    python main.py --test       # Run test scenario
    python main.py --simulate   # Interactive simulation
================================================================================
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("perennia.receptionist")

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def print_startup_banner():
    """Print startup banner"""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║     🎙️  PERENNIA AI RECEPTIONIST                                             ║
║     Intelligent Voice AI for Mortgage Companies                              ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Features:                                                                   ║
║    • Natural conversation powered by Claude/GPT-4                            ║
║    • Emotional intelligence and empathy                                      ║
║    • Full telephony with Twilio                                              ║
║    • 160 integrated CRM tools                                                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)


def check_configuration():
    """Check required configuration"""
    required_vars = [
        ("TWILIO_ACCOUNT_SID", "Twilio Account SID"),
        ("TWILIO_AUTH_TOKEN", "Twilio Auth Token"),
    ]

    llm_vars = [
        ("ANTHROPIC_API_KEY", "Anthropic API Key"),
        ("OPENAI_API_KEY", "OpenAI API Key"),
    ]

    missing = []

    for var, name in required_vars:
        if not os.getenv(var):
            missing.append(name)

    # Check for at least one LLM provider
    has_llm = any(os.getenv(var) for var, _ in llm_vars)
    if not has_llm:
        logger.warning("No LLM API key configured - using rule-based responses")

    if missing:
        logger.error(f"Missing required configuration: {', '.join(missing)}")
        logger.error("Please set environment variables or create .env file")
        return False

    return True


def create_app():
    """Create and configure the FastAPI application"""
    from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
    from fastapi.responses import PlainTextResponse
    from fastapi.middleware.cors import CORSMiddleware

    # Import our modules
    from AI_RECEPTIONIST_PART1_ENGINE import ConversationEngine, ReceptionistPersonality
    from AI_RECEPTIONIST_PART2_TWILIO import TwilioVoiceHandler, TwilioConfig
    from AI_RECEPTIONIST_PART4_INTEGRATION import ReceptionistToolExecutor

    # Create FastAPI app
    app = FastAPI(
        title="Perennia AI Receptionist",
        description="Intelligent voice AI for mortgage companies",
        version="1.0.0",
    )

    # Add CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configuration
    personality = ReceptionistPersonality(
        name=os.getenv("RECEPTIONIST_NAME", "Sarah"),
        company_name=os.getenv("COMPANY_NAME", "Perennia Mortgage"),
    )

    twilio_config = TwilioConfig(
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
        base_url=os.getenv("TWILIO_WEBHOOK_BASE_URL"),
    )

    # Create components
    tool_executor = ReceptionistToolExecutor()

    # Determine LLM provider
    if os.getenv("ANTHROPIC_API_KEY"):
        llm_provider = "claude"
    elif os.getenv("OPENAI_API_KEY"):
        llm_provider = "openai"
    else:
        llm_provider = None

    conversation_engine = ConversationEngine(
        personality=personality,
        llm_provider=llm_provider,
        tool_executor=tool_executor.execute,
    )

    voice_handler = TwilioVoiceHandler(
        config=twilio_config,
        conversation_handler=conversation_engine,
    )

    # Store in app state
    app.state.conversation_engine = conversation_engine
    app.state.voice_handler = voice_handler
    app.state.tool_executor = tool_executor

    # -------------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------------

    @app.get("/")
    async def root():
        return {
            "service": "Perennia AI Receptionist",
            "status": "running",
            "version": "1.0.0",
        }

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "ai-receptionist",
            "components": {
                "conversation_engine": "ok",
                "voice_handler": "ok",
                "twilio_configured": bool(twilio_config.account_sid),
                "llm_provider": llm_provider or "rule-based",
            },
        }

    @app.post("/voice/inbound")
    async def handle_inbound_call(request: Request):
        """Handle incoming Twilio call"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        from_number = params.get("From")
        caller_name = params.get("CallerName")

        logger.info(f"Incoming call: {call_sid} from {from_number}")

        # Start conversation
        state, greeting = await conversation_engine.start_conversation(
            call_sid=call_sid,
            caller_phone=from_number,
            caller_id_name=caller_name,
        )

        # Generate TwiML
        twiml = voice_handler.generate_greeting_twiml(
            greeting=greeting,
            gather_speech=True,
        )

        return Response(content=twiml, media_type="application/xml")

    @app.post("/voice/process-speech")
    async def process_speech(request: Request):
        """Process speech recognition result"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        speech_result = params.get("SpeechResult", "")

        logger.info(f"Speech for {call_sid}: {speech_result}")

        # Process through conversation engine
        if speech_result:
            response_text = await conversation_engine.process_input(
                call_sid=call_sid,
                caller_input=speech_result,
            )
        else:
            response_text = "I'm sorry, I didn't catch that. Could you please repeat?"

        # Generate TwiML
        twiml = voice_handler.generate_response_twiml(
            message=response_text,
            gather_speech=True,
        )

        return Response(content=twiml, media_type="application/xml")

    @app.post("/voice/no-input")
    async def handle_no_input(request: Request):
        """Handle timeout with no speech"""
        twiml = voice_handler.generate_response_twiml(
            message="I'm still here. How can I help you?",
            gather_speech=True,
        )
        return Response(content=twiml, media_type="application/xml")

    @app.post("/voice/status")
    async def call_status(request: Request):
        """Handle call status updates"""
        form_data = await request.form()
        params = dict(form_data)

        call_sid = params.get("CallSid")
        status = params.get("CallStatus")

        logger.info(f"Call {call_sid} status: {status}")

        # End conversation if call completed
        if status in ["completed", "busy", "failed", "no-answer", "canceled"]:
            summary = await conversation_engine.end_conversation(call_sid, reason=status)
            logger.info(f"Call summary: {summary}")

        return PlainTextResponse("OK")

    @app.post("/voice/recording-status")
    async def recording_status(request: Request):
        """Handle recording callbacks"""
        form_data = await request.form()
        params = dict(form_data)

        logger.info(f"Recording status: {params.get('RecordingStatus')}")

        return PlainTextResponse("OK")

    @app.post("/voice/transfer-complete")
    async def transfer_complete(request: Request):
        """Handle transfer completion"""
        form_data = await request.form()
        params = dict(form_data)

        dial_status = params.get("DialCallStatus")

        if dial_status in ["completed", "answered"]:
            return Response(content="", media_type="application/xml")

        # Transfer failed
        twiml = voice_handler.generate_response_twiml(
            message="I'm sorry, I wasn't able to connect that call. Is there something else I can help with?",
            gather_speech=True,
        )
        return Response(content=twiml, media_type="application/xml")

    @app.post("/voice/voicemail-complete")
    async def voicemail_complete(request: Request):
        """Handle voicemail completion"""
        form_data = await request.form()
        call_sid = dict(form_data).get("CallSid")

        # Mark message left
        state = conversation_engine.get_conversation_state(call_sid)
        if state:
            state.message_left = True

        twiml = voice_handler.generate_goodbye_twiml(
            "Thank you for your message. Someone will get back to you shortly. Goodbye!"
        )
        return Response(content=twiml, media_type="application/xml")

    @app.websocket("/voice/stream")
    async def audio_stream(websocket: WebSocket):
        """Handle real-time audio streaming"""
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()
                # Handle streaming audio
                # This would integrate with Deepgram/ElevenLabs
                pass
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")

    return app


def run_server():
    """Run the server"""
    import uvicorn

    print_startup_banner()

    if not check_configuration():
        sys.exit(1)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    webhook_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", f"http://localhost:{port}")

    print(f"""
Server starting...

  URL: http://{host}:{port}

Endpoints:
  POST /voice/inbound       - Twilio call webhook
  POST /voice/process-speech - Speech processing
  POST /voice/status        - Call status updates
  GET  /health              - Health check

Twilio Webhook URL:
  {webhook_url}/voice/inbound

Press Ctrl+C to stop
    """)

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


async def run_test():
    """Run test scenario"""
    from AI_RECEPTIONIST_PART4_INTEGRATION import ReceptionistTester

    print_startup_banner()
    print("Running test scenario...\n")

    tester = ReceptionistTester()

    await tester.run_scenario([
        "Hi, I'd like to schedule an appointment with a loan officer",
        "I'm looking to refinance my home",
        "How about tomorrow afternoon around 2pm?",
        "My name is John Smith",
        "Perfect, thank you!",
    ])


async def run_simulation():
    """Run interactive simulation"""
    from AI_RECEPTIONIST_PART4_INTEGRATION import ReceptionistTester

    print_startup_banner()
    print("Interactive simulation mode")
    print("Type your message as the caller")
    print("Type 'quit' to exit\n")

    tester = ReceptionistTester()
    await tester.simulate_call("+15551234567")

    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ["quit", "exit", "bye"]:
                break
            if user_input:
                await tester.say(user_input)
        except KeyboardInterrupt:
            break

    await tester.end()


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        arg = sys.argv[1]

        if arg == "--test":
            asyncio.run(run_test())
        elif arg == "--simulate":
            asyncio.run(run_simulation())
        elif arg == "--help":
            print(__doc__)
        else:
            run_server()
    else:
        run_server()


if __name__ == "__main__":
    main()
