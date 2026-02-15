"""
Voice Integration Routes
Transcription, text-to-speech, and voice chat endpoints using OpenAI
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
import os
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai/voice")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Lead': main.Lead,
        'Task': main.Task,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


def get_log_ai_action():
    """Get AI action logging function"""
    import main
    return main.log_ai_action_to_mission_control


@router.post("/transcribe")
async def voice_transcribe(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Transcribe audio to text using OpenAI Whisper
    Accepts base64 audio or audio file
    """
    try:
        from openai import OpenAI
        import base64
        import tempfile

        data = await request.json()
        audio_base64 = data.get("audio")
        audio_format = data.get("format", "webm")

        if not audio_base64:
            raise HTTPException(status_code=400, detail="Audio data required")

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_base64)

        # Save to temp file for Whisper
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        try:
            # Transcribe with Whisper
            with open(temp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return {
            "transcript": transcript,
            "success": True
        }

    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat")
async def voice_chat(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Full voice chat: transcribe → process → generate speech
    Returns both text and audio response
    """
    try:
        from openai import OpenAI
        import base64
        import tempfile
        import pytz

        models = get_models()
        Lead = models['Lead']
        Task = models['Task']
        log_ai_action = get_log_ai_action()

        data = await request.json()
        audio_base64 = data.get("audio")
        text_input = data.get("text")  # Alternative: direct text input
        audio_format = data.get("format", "webm")
        voice = data.get("voice", "alloy")  # alloy, echo, fable, onyx, nova, shimmer

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Step 1: Transcribe audio if provided
        if audio_base64:
            audio_bytes = base64.b64decode(audio_base64)

            with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            try:
                with open(temp_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="text"
                    )
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            user_message = transcript
        elif text_input:
            user_message = text_input
        else:
            raise HTTPException(status_code=400, detail="Audio or text input required")

        # Step 2: Process through orchestrator
        all_leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
        all_tasks = db.query(Task).filter(Task.owner_id == current_user.id).all()

        # Get user's local time
        user_timezone = getattr(current_user, 'timezone', None) or "America/Chicago"
        try:
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)
        except Exception:
            user_timezone = "America/Chicago"
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)
        today = user_local_time.date()

        tasks_today = [t for t in all_tasks if t.due_date and t.due_date.date() == today and t.status != "completed"]

        # Simple AI response for voice
        voice_prompt = f"""You are a helpful voice assistant for a mortgage CRM.
User: {current_user.full_name or current_user.email}
Today: {user_local_time.strftime('%A, %B %d at %I:%M %p')}

Quick stats:
- {len(tasks_today)} tasks due today
- {len(all_leads)} total leads

Respond conversationally and concisely (1-2 sentences for voice).
Be natural and helpful. Keep responses under 50 words for voice output."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": voice_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=150
        )

        ai_response = response.choices[0].message.content

        # Step 3: Generate speech from response
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=ai_response
        )

        # Convert to base64
        audio_content = speech_response.content
        audio_base64_response = base64.b64encode(audio_content).decode('utf-8')

        # Log to Mission Control
        await log_ai_action(
            db=db,
            agent_name="Voice Assistant",
            action_type="voice_chat",
            user_id=current_user.id,
            context={"input": user_message[:100], "voice": voice},
            autonomy_level="autonomous",
            status="completed"
        )

        return {
            "transcript": user_message,
            "response": ai_response,
            "audio": audio_base64_response,
            "audio_format": "mp3",
            "voice": voice,
            "success": True
        }

    except Exception as e:
        logger.error(f"Voice chat error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/synthesize")
async def voice_synthesize(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Text-to-speech synthesis
    Convert text to spoken audio
    """
    try:
        from openai import OpenAI
        import base64

        data = await request.json()
        text = data.get("text")
        voice = data.get("voice", "alloy")  # alloy, echo, fable, onyx, nova, shimmer
        speed = data.get("speed", 1.0)

        if not text:
            raise HTTPException(status_code=400, detail="Text is required")

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Generate speech
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            speed=speed
        )

        # Convert to base64
        audio_content = speech_response.content
        audio_base64 = base64.b64encode(audio_content).decode('utf-8')

        return {
            "audio": audio_base64,
            "audio_format": "mp3",
            "voice": voice,
            "text_length": len(text),
            "success": True
        }

    except Exception as e:
        logger.error(f"Voice synthesis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/phone-webhook")
async def voice_phone_webhook(
    request: Request,
    db: Session = Depends(lambda: get_db_dep())
):
    """
    Webhook for incoming phone calls (Twilio/Vapi integration)
    Processes voice input and returns TwiML or Vapi response
    """
    try:
        from openai import OpenAI

        data = await request.json()

        # Handle different webhook formats (Twilio, Vapi)
        caller = data.get("From") or data.get("caller") or "Unknown"
        speech_result = data.get("SpeechResult") or data.get("transcript") or ""
        call_sid = data.get("CallSid") or data.get("call_id") or ""

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Generate AI response for phone
        phone_prompt = """You are an AI receptionist for a mortgage company.
Be professional, helpful, and concise.
If asked about rates or loans, offer to connect them with a loan officer.
Keep responses under 30 words for phone conversations."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": phone_prompt},
                {"role": "user", "content": speech_result or "Hello"}
            ],
            temperature=0.7,
            max_tokens=100
        )

        ai_response = response.choices[0].message.content

        # Log the call
        logger.info(f"Phone webhook - Caller: {caller}, Input: {speech_result}, Response: {ai_response}")

        return {
            "response": ai_response,
            "caller": caller,
            "call_sid": call_sid,
            "success": True
        }

    except Exception as e:
        logger.error(f"Phone webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
