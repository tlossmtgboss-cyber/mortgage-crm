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

from urllib.parse import urlparse
import ipaddress

logger = logging.getLogger(__name__)


def _is_safe_url(url: str) -> bool:
    """Validate URL is not targeting internal/private networks (SSRF protection)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        blocked = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]",
                   "169.254.169.254", "metadata.google.internal"}
        if hostname in blocked:
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass  # Not an IP literal, allow
        return True
    except Exception:
        return False


# Recall.ai Configuration
RECALLAI_API_KEY = os.getenv("RECALLAI_API_KEY", "")
RECALLAI_WEBHOOK_SECRET = os.getenv("RECALLAI_WEBHOOK_SECRET", "")
RECALLAI_API_BASE = "https://us-west-2.recall.ai/api/v1"

# Import get_db and auth from main
# Note: RecallAIBot model does not exist yet - guarded to prevent import crash
try:
    from main import get_db, get_current_user, User
    from main import RecallAIBot
except ImportError:
    RecallAIBot = None


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
    current_user: User = Depends(get_current_user)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/bot/{bot_id}")
async def get_bot_status(
    bot_id: str,
    current_user: User = Depends(get_current_user)
):
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
        if bot_data.get("transcript_url") and _is_safe_url(bot_data["transcript_url"]):
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
                transcript_text = ""
                if bot_data.get("transcript_url"):
                    try:
                        transcript_response = requests.get(bot_data["transcript_url"], timeout=30)
                        if transcript_response.status_code == 200:
                            transcript_data = transcript_response.json()
                            words = transcript_data.get("words", [])
                            transcript_text = " ".join([w.get("text", "") for w in words])
                            bot_record.transcript_text = transcript_text
                    except Exception as e:
                        logger.warning(f"Could not fetch transcript: {e}")

                db.commit()

                # Process the video call: summarize and create email draft
                if transcript_text:
                    import asyncio
                    asyncio.create_task(
                        process_video_call_recording(
                            bot_record=bot_record,
                            transcript=transcript_text,
                            video_url=bot_data.get("video_url"),
                            db=db
                        )
                    )

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/bots")
async def list_bots(
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
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
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_video_call_recording(
    bot_record,
    transcript: str,
    video_url: str,
    db: Session
):
    """Process video call recording: summarize with AI and create email draft"""
    import os
    import httpx
    from anthropic import Anthropic
    from msal import ConfidentialClientApplication

    logger.info(f"Processing video call recording for bot {bot_record.bot_id}...")

    try:
        # Get user email for draft creation
        user_email = None
        lead_name = None

        if bot_record.user_id:
            from main import User
            user = db.query(User).filter(User.id == bot_record.user_id).first()
            if user:
                user_email = user.email

        if bot_record.lead_id:
            from main import Lead
            lead = db.query(Lead).filter(Lead.id == bot_record.lead_id).first()
            if lead:
                lead_name = lead.name

        # Step 1: Summarize with Claude
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            logger.error("Anthropic API key not configured")
            return

        logger.info("Generating professional summary with Claude...")
        anthropic_client = Anthropic(api_key=anthropic_key)

        client_identifier = lead_name or "Client"
        meeting_platform = "Video Meeting"
        if "zoom" in (bot_record.meeting_url or "").lower():
            meeting_platform = "Zoom Meeting"
        elif "teams" in (bot_record.meeting_url or "").lower():
            meeting_platform = "Microsoft Teams Meeting"
        elif "meet.google" in (bot_record.meeting_url or "").lower():
            meeting_platform = "Google Meet"

        summary_prompt = f"""You are a professional assistant for a mortgage loan officer.
Summarize the following video meeting transcript into a professional meeting summary.

Meeting Details:
- Client: {client_identifier}
- Platform: {meeting_platform}
- Date: {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p')}

Transcript:
{transcript[:15000]}

Create a professional meeting summary with the following sections:
1. **Meeting Overview** - Brief 1-2 sentence summary
2. **Key Discussion Points** - Bullet points of main topics discussed
3. **Client Needs/Requests** - What the client is looking for
4. **Decisions Made** - Any decisions or agreements reached
5. **Action Items** - Any follow-up tasks or commitments made
6. **Next Steps** - Recommended next actions

Keep the summary concise but comprehensive. Use professional language appropriate for client records."""

        summary_response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1500,
            messages=[{"role": "user", "content": summary_prompt}]
        )

        summary = summary_response.content[0].text
        logger.info(f"Summary generated: {len(summary)} characters")

        # Store summary in database
        bot_record.summary = summary
        db.commit()

        # Step 2: Create email draft in user's Outlook
        if not user_email:
            logger.warning("No user email available, skipping draft creation")
            return

        # Get Microsoft Graph token
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID")

        if not all([client_id, client_secret, tenant_id]):
            logger.warning("Microsoft Graph credentials not configured, skipping draft creation")
            return

        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}"
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            logger.error(f"Failed to get Graph token: {result.get('error_description')}")
            return

        token = result["access_token"]

        # Format email body
        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
<h2 style="color: #2c3e50;">🎥 {meeting_platform} Summary - {client_identifier}</h2>

<table style="margin-bottom: 20px; border-collapse: collapse;">
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Client:</td><td>{client_identifier}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Platform:</td><td>{meeting_platform}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Date:</td><td>{datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p')}</td></tr>
{f'<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Recording:</td><td><a href="{video_url}">View Recording</a></td></tr>' if video_url else ''}
</table>

<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
{summary.replace(chr(10), '<br>')}
</div>

<details style="margin-top: 20px;">
<summary style="cursor: pointer; font-weight: bold; color: #3498db;">📝 View Full Transcript</summary>
<div style="background: #f0f0f0; padding: 15px; margin-top: 10px; border-radius: 5px; white-space: pre-wrap; font-size: 13px; max-height: 500px; overflow-y: auto;">
{transcript[:10000]}{'...' if len(transcript) > 10000 else ''}
</div>
</details>

<p style="margin-top: 20px; color: #7f8c8d; font-size: 12px;">
<em>This summary was automatically generated by Perennia AI. Please review before sending to the client.</em>
</p>
</body>
</html>
"""

        # Create draft email via Microsoft Graph
        draft_data = {
            "subject": f"{meeting_platform} Summary - {client_identifier} - {datetime.now(timezone.utc).strftime('%m/%d/%Y')}",
            "body": {
                "contentType": "HTML",
                "content": email_body
            },
            "importance": "normal"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=draft_data,
                timeout=30.0
            )

            if response.status_code in [200, 201]:
                draft_id = response.json().get("id")
                logger.info(f"Email draft created successfully for video meeting: {draft_id}")

                # Update bot record with draft info
                if bot_record.meeting_metadata is None:
                    bot_record.meeting_metadata = {}
                bot_record.meeting_metadata['email_draft_id'] = draft_id
                db.commit()
            else:
                logger.error(f"Failed to create draft: {response.status_code} - {response.text}")

        logger.info(f"Video call recording processing complete for bot {bot_record.bot_id}")

    except Exception as e:
        logger.error(f"Error processing video call recording: {e}")


# Export router
__all__ = ["router", "StartRecordingRequest", "BotStatusResponse"]
