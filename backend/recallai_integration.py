"""
Recall.ai Integration for Meeting Recording and Transcription
Provides bot-based meeting recording for Zoom, Teams, Google Meet
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import requests
import os
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)

# Recall.ai Configuration
RECALLAI_API_KEY = "2710d1a040a03295045e0ad6bb2535997da8acd0"
RECALLAI_WEBHOOK_SECRET = os.getenv("RECALLAI_WEBHOOK_SECRET", "whsec_suIiYYXb7fgjFjOtVWT0spOfalxNKtldS/MI13wAGV3thi5JbpPjpCUYU2Y0BcxN")
RECALLAI_API_BASE = "https://us-west-2.recall.ai/api/v1"

# Import get_db from main
from main import get_db, RecallAIBot


# Pydantic Models
class StartRecordingRequest(BaseModel):
    meeting_url: str
    lead_id: Optional[int] = None
    bot_name: Optional[str] = "Mortgage CRM Assistant"


class BotStatusResponse(BaseModel):
    bot_id: str
    status: str
    meeting_url: str
    transcript: Optional[str] = None
    summary: Optional[str] = None


# API Router
router = APIRouter(prefix="/api/v1/recallai", tags=["Recall.ai"])


def get_recallai_headers():
    """Get headers for Recall.ai API requests"""
    return {
        "Authorization": f"Token {RECALLAI_API_KEY}",
        "Content-Type": "application/json"
    }


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Recall.ai webhook signature"""
    try:
        expected_signature = hmac.new(
            RECALLAI_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected_signature}", signature)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


@router.post("/start-recording")
async def start_recording(
    request: StartRecordingRequest,
    db: Session = Depends(get_db),
    current_user: Any = None  # TODO: Add current user dependency when integrated
):
    """
    Start a Recall.ai bot to record a meeting

    - **meeting_url**: Zoom, Teams, or Google Meet URL
    - **lead_id**: Optional ID of lead this meeting is for
    - **bot_name**: Name to display for the bot in the meeting
    """
    try:
        # Create bot via Recall.ai API
        payload = {
            "meeting_url": request.meeting_url,
            "bot_name": request.bot_name,
            "recording_mode": "speaker_view",  # or "gallery_view"
            "automatic_leave": {
                "waiting_room_timeout": 600,  # 10 minutes
                "noone_joined_timeout": 600
            },
            "automatic_video_output": {
                "in_call_recording": {
                    "b64_data": None  # Let Recall.ai handle video
                }
            },
            "automatic_audio_output": {
                "in_call_recording": {
                    "b64_data": None  # Let Recall.ai handle audio
                }
            }
        }

        response = requests.post(
            f"{RECALLAI_API_BASE}/bot/",
            headers=get_recallai_headers(),
            json=payload,
            timeout=30
        )

        if response.status_code not in [200, 201]:
            logger.error(f"Recall.ai API error: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to create bot: {response.text}"
            )

        bot_data = response.json()
        bot_id = bot_data.get("id")

        logger.info(f"✅ Created Recall.ai bot: {bot_id}")

        # Store in database
        bot_record = RecallAIBot(
            user_id=current_user.id if current_user else None,
            lead_id=request.lead_id,
            bot_id=bot_id,
            meeting_url=request.meeting_url,
            bot_name=request.bot_name,
            status=bot_data.get("status_changes", [{}])[-1].get("code", "joining"),
            meeting_metadata=bot_data
        )
        db.add(bot_record)
        db.commit()
        db.refresh(bot_record)

        return {
            "success": True,
            "bot_id": bot_id,
            "status": bot_data.get("status_changes", [{}])[-1].get("code", "joining"),
            "message": "Bot is joining the meeting. Transcript will be available when the meeting ends."
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error calling Recall.ai API: {e}")
        raise HTTPException(status_code=503, detail="Failed to connect to Recall.ai service")
    except Exception as e:
        logger.error(f"Error starting recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot/{bot_id}")
async def get_bot_status(bot_id: str):
    """Get status and transcript of a recording bot"""
    try:
        response = requests.get(
            f"{RECALLAI_API_BASE}/bot/{bot_id}/",
            headers=get_recallai_headers(),
            timeout=30
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Bot not found")

        bot_data = response.json()

        # Get latest status
        status_changes = bot_data.get("status_changes", [])
        current_status = status_changes[-1].get("code") if status_changes else "unknown"

        # Get transcript if available
        transcript_text = None
        if bot_data.get("transcript_url"):
            try:
                transcript_response = requests.get(bot_data["transcript_url"], timeout=30)
                if transcript_response.status_code == 200:
                    transcript_data = transcript_response.json()
                    # Combine all transcript words into text
                    words = transcript_data.get("words", [])
                    transcript_text = " ".join([w.get("text", "") for w in words])
            except Exception as e:
                logger.warning(f"Could not fetch transcript: {e}")

        return {
            "bot_id": bot_id,
            "status": current_status,
            "meeting_url": bot_data.get("meeting_url"),
            "video_url": bot_data.get("video_url"),
            "transcript_url": bot_data.get("transcript_url"),
            "transcript": transcript_text,
            "created_at": bot_data.get("created_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching bot status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def webhook_handler(request: Request, db: Session = Depends(get_db)):
    """
    Receive webhooks from Recall.ai when bot status changes
    Events: bot.status_change, bot.transcription_ready, etc.
    """
    try:
        # Verify signature
        signature = request.headers.get("Recall-Signature")
        body = await request.body()

        if not signature or not verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse webhook data
        data = await request.json()
        event_type = data.get("event")
        bot_data = data.get("data", {})
        bot_id = bot_data.get("id")

        logger.info(f"📥 Received webhook: {event_type} for bot {bot_id}")

        # Handle different event types
        if event_type == "bot.status_change":
            status = bot_data.get("status_changes", [{}])[-1].get("code")
            logger.info(f"Bot {bot_id} status: {status}")

            # Update database with new status
            bot_record = db.query(RecallAIBot).filter(RecallAIBot.bot_id == bot_id).first()
            if bot_record:
                bot_record.status = status
                bot_record.webhook_data = data
                if status == "in_meeting":
                    bot_record.join_at = datetime.now(timezone.utc)
                elif status in ["done", "fatal", "error"]:
                    bot_record.leave_at = datetime.now(timezone.utc)
                db.commit()

        elif event_type == "bot.transcription_ready":
            logger.info(f"Transcript ready for bot {bot_id}")

            # Update database with transcript URLs
            bot_record = db.query(RecallAIBot).filter(RecallAIBot.bot_id == bot_id).first()
            if bot_record:
                bot_record.transcript_url = bot_data.get("transcript_url")
                bot_record.video_url = bot_data.get("video_url")

                # Fetch transcript text
                if bot_data.get("transcript_url"):
                    try:
                        transcript_response = requests.get(bot_data["transcript_url"], timeout=30)
                        if transcript_response.status_code == 200:
                            transcript_data = transcript_response.json()
                            words = transcript_data.get("words", [])
                            bot_record.transcript_text = " ".join([w.get("text", "") for w in words])
                    except Exception as e:
                        logger.warning(f"Could not fetch transcript: {e}")

                db.commit()

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/bots")
async def list_bots(limit: int = 10):
    """List all bots created by this account"""
    try:
        response = requests.get(
            f"{RECALLAI_API_BASE}/bot/",
            headers=get_recallai_headers(),
            params={"limit": limit},
            timeout=30
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch bots")

        bots = response.json().get("results", [])

        return {
            "bots": [
                {
                    "bot_id": bot.get("id"),
                    "meeting_url": bot.get("meeting_url"),
                    "status": bot.get("status_changes", [{}])[-1].get("code", "unknown"),
                    "created_at": bot.get("created_at")
                }
                for bot in bots
            ]
        }

    except Exception as e:
        logger.error(f"Error listing bots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Export router
__all__ = ["router", "StartRecordingRequest", "BotStatusResponse"]
