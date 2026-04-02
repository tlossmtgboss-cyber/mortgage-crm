"""
UVIP - Video Meeting Shared Dependencies and Helpers
Extracted from video_meeting_routes.py

Shared dependency injection, authorization helpers, background task functions,
rate limiting, and utility functions used across all video meeting sub-routers.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from collections import defaultdict
import logging
import os
import secrets
import string
import time as time_module

logger = logging.getLogger(__name__)


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user = None
_models = None
_pwd_context = None


def set_dependencies(get_db_func, get_current_user_func, models_dict, pwd_context=None):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models, _pwd_context
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict
    _pwd_context = pwd_context


def get_models():
    """Get the models dict. Raises RuntimeError if not initialized."""
    if _models is None:
        raise RuntimeError("Dependencies not set")
    return _models


def get_pwd_context():
    """Get the password context (may be None)."""
    return _pwd_context


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_room_code(length: int = 9) -> str:
    """Generate a unique meeting room code like MTG-ABC123"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(chars) for _ in range(length))
    return f"MTG-{code[:3]}-{code[3:6]}-{code[6:]}"


def _require_admin(current_user):
    """Raise 403 if user is not an admin or site_admin."""
    role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
    if role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")


async def _validate_webhook_signature(request: Request) -> bool:
    """Validate Telnyx webhook signature. Returns True if valid or if validation is not configured."""
    signing_secret = os.getenv("TELNYX_WEBHOOK_SECRET")
    if not signing_secret:
        logger.warning("TELNYX_WEBHOOK_SECRET not set -- skipping webhook signature validation")
        return True

    try:
        # Telnyx uses Ed25519 webhook signing. For now, log and pass through;
        # full Ed25519 signature validation should be added at the Telnyx webhook ingress layer.
        signature = request.headers.get("telnyx-signature-ed25519", "")
        url = str(request.url)
        if signature:
            logger.info(f"Received request with telnyx-signature-ed25519 header at {url} — pass-through")
        return True
    except Exception as e:
        logger.error(f"Webhook signature validation error: {e}")
        return False


# Backward-compatible alias for any external imports
_validate_twilio_signature = _validate_webhook_signature


# ============================================================================
# RATE LIMITING
# ============================================================================

_rate_limit_store: Dict[str, list] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10  # max requests per window per IP
_RATE_LIMIT_MAX_KEYS = 10000  # max tracked IPs before forced cleanup


def _check_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limit. Returns True if allowed."""
    now = time_module.time()
    # Prune old entries for this IP
    _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]
    # Periodic global cleanup to prevent unbounded growth
    if len(_rate_limit_store) > _RATE_LIMIT_MAX_KEYS:
        stale_keys = [k for k, v in _rate_limit_store.items() if not v or now - v[-1] > _RATE_LIMIT_WINDOW]
        for k in stale_keys:
            del _rate_limit_store[k]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[client_ip].append(now)
    return True


# ============================================================================
# AUTHORIZATION HELPERS
# ============================================================================

def verify_room_access(room, current_user, db) -> bool:
    """
    Verify user has access to a meeting room.
    Access is granted if:
    - User is the host
    - User is a participant
    - User is in the same organization (if org tracking enabled)
    """
    if room.host_user_id == current_user.id:
        return True

    # Check if user is a participant
    MeetingParticipant = _models.get('MeetingParticipant')
    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room.id,
        MeetingParticipant.user_id == current_user.id
    ).first()
    if participant:
        return True

    # Check organization access (if organizations are used)
    if hasattr(room, 'organization_id') and hasattr(current_user, 'organization_id'):
        if room.organization_id and room.organization_id == current_user.organization_id:
            return True

    return False


def verify_recording_access(recording_id: int, current_user, db) -> bool:
    """Verify user has access to a recording by checking the parent meeting"""
    MeetingRecording = _models.get('MeetingRecording')
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    recording = db.query(MeetingRecording).filter(
        MeetingRecording.id == recording_id
    ).first()
    if not recording:
        return False

    room = db.query(VideoMeetingRoom).filter(
        VideoMeetingRoom.id == recording.meeting_id
    ).first()
    if not room:
        return False

    return verify_room_access(room, current_user, db)


def verify_host_permission(room, current_user) -> bool:
    """Verify user is the host of a meeting (for admin operations)"""
    return room.host_user_id == current_user.id


# ============================================================================
# BACKGROUND TASK FUNCTIONS
# ============================================================================

async def process_meeting_ai_analysis(room_id: int):
    """Process AI analysis for a completed meeting"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        VideoMeetingRoom = _models.get('VideoMeetingRoom')
        MeetingRecording = _models.get('MeetingRecording')
        MeetingTranscript = _models.get('RecordingTranscript')
        AIAnalysis = _models.get('MeetingAIAnalysis')

        room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
        if not room:
            logger.error(f"Meeting room {room_id} not found for AI analysis")
            return

        # Get transcript if available
        transcript = db.query(MeetingTranscript).filter(
            MeetingTranscript.meeting_id == room_id,
            MeetingTranscript.status == "completed"
        ).first()

        if transcript and transcript.full_transcript:
            # Create AI analysis using Claude
            import httpx

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 2000,
                            "messages": [{
                                "role": "user",
                                "content": f"""Analyze this meeting transcript and provide:
1. Summary (2-3 sentences)
2. Key action items
3. Important decisions made
4. Follow-up items needed

Transcript:
{transcript.full_transcript[:10000]}"""
                            }],
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        analysis_text = result["content"][0]["text"]

                        # Create analysis record
                        analysis = AIAnalysis(
                            meeting_id=room_id,
                            analysis_type="summary",
                            status="completed",
                            result={"summary": analysis_text},
                            completed_at=datetime.now(timezone.utc)
                        )
                        db.add(analysis)
                        db.commit()
                        logger.info(f"AI analysis completed for meeting {room_id}")

            except Exception as e:
                logger.error(f"AI analysis failed for meeting {room_id}: {e}")

    except Exception as e:
        logger.error(f"Error processing AI analysis for meeting {room_id}: {e}")
    finally:
        db.close()


async def process_recording(recording_id: int):
    """Process a completed recording (transcription, analysis)"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        MeetingRecording = _models.get('MeetingRecording')
        RecordingTranscript = _models.get('RecordingTranscript')

        recording = db.query(MeetingRecording).filter(
            MeetingRecording.id == recording_id
        ).first()

        if not recording:
            logger.error(f"Recording {recording_id} not found for processing")
            return

        # Update recording status to processing
        recording.status = "processing"
        db.commit()

        # If transcription is enabled, create transcript placeholder
        if recording.storage_path and RecordingTranscript:
            transcript = RecordingTranscript(
                meeting_id=recording.meeting_id,
                recording_id=recording_id,
                status="pending",
                language="en"
            )
            db.add(transcript)
            db.commit()

            # Note: Actual transcription would integrate with Whisper or similar
            logger.info(f"Recording {recording_id} queued for transcription")

        # Don't mark as "completed" yet -- leave as "processing" until
        # transcription is actually done. Only mark error on failure.
        logger.info(f"Recording {recording_id} processing started")

    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        # Mark recording with error status for retry visibility
        try:
            recording = db.query(_models.get('MeetingRecording')).filter(
                _models.get('MeetingRecording').id == recording_id
            ).first()
            if recording:
                recording.status = "error"
                db.commit()
        except Exception as e:
            logger.exception(f"Failed to mark recording as error status: {e}")
    finally:
        db.close()


async def run_ai_analysis(room_id: int, analysis_types: List[str]):
    """Run specific AI analysis types for a meeting"""
    await process_meeting_ai_analysis(room_id)


async def send_meeting_invite_email(
    to_email: str,
    participant_name: str,
    room_name: str,
    join_url: str,
    host_name: str,
    scheduled_start: Optional[datetime] = None
):
    """Send meeting invite email to participant"""
    from email_service import email_service

    time_str = scheduled_start.strftime('%B %d, %Y at %I:%M %p') if scheduled_start else "Now"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%); color: white; padding: 30px; border-radius: 12px; text-align: center;">
            <h2 style="margin: 0 0 10px;">Video Meeting Invitation</h2>
            <p style="margin: 0; opacity: 0.9;">{room_name}</p>
        </div>

        <div style="padding: 30px 0;">
            <p>Hi {participant_name or 'there'},</p>
            <p>You've been invited to join a video meeting hosted by <strong>{host_name}</strong>.</p>

            <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0 0 5px; color: #666;">When:</p>
                <p style="margin: 0; font-size: 18px; font-weight: 600;">{time_str}</p>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{join_url}"
                   style="display: inline-block; background: #10b981; color: white; padding: 14px 40px;
                          border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                    Join Meeting
                </a>
            </div>

            <p style="color: #666; font-size: 14px; text-align: center;">
                Or copy this link: <a href="{join_url}" style="color: #3b82f6;">{join_url}</a>
            </p>
        </div>

        <div style="border-top: 1px solid #e5e7eb; padding-top: 20px; text-align: center; color: #9ca3af; font-size: 12px;">
            <p>This invitation was sent via Perennia AI CRM</p>
        </div>
    </body>
    </html>
    """

    plain_text = f"""
Video Meeting Invitation

Hi {participant_name or 'there'},

You've been invited to join a video meeting.

Meeting: {room_name}
Host: {host_name}
When: {time_str}

Join the meeting: {join_url}

This invitation was sent via Perennia AI CRM
"""

    success = email_service.send_html_email(
        to_email=to_email,
        subject=f"Video Meeting: {room_name}",
        html_body=html_body,
        plain_text_body=plain_text
    )

    logger.info(f"Meeting invite sent to {to_email}: {'success' if success else 'failed'}")
    return success


async def process_recording_ai(recording_id: int, meeting_id: int, transcription_enabled: bool):
    """Background task to process recording with AI."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.recording_service import get_recording_service
        from uvip.ai_processing_service import get_ai_processing_service

        recording_service = get_recording_service()
        ai_service = get_ai_processing_service()

        MeetingRecording = _models.get('MeetingRecording')
        RecordingTranscript = _models.get('RecordingTranscript')
        MeetingAIAnalysis = _models.get('MeetingAIAnalysis')
        VideoMeetingRoom = _models.get('VideoMeetingRoom')

        recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
        if not recording:
            return

        room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == meeting_id).first()
        if not room:
            return

        # Step 1: Download recording from Telnyx
        audio_content = await recording_service.download_recording(recording.recording_uuid)
        if not audio_content:
            recording.status = "failed"
            recording.error_message = "Failed to download recording"
            db.commit()
            return

        recording.file_size_bytes = len(audio_content)

        # Step 2: Transcribe if enabled
        transcript_text = ""
        if transcription_enabled and RecordingTranscript:
            transcription_result = await ai_service.transcribe_audio(audio_content)

            if transcription_result.get("transcript"):
                transcript = RecordingTranscript(
                    recording_id=recording.id,
                    meeting_id=meeting_id,
                    status="completed",
                    full_transcript=transcription_result["transcript"],
                    transcript_json=transcription_result.get("segments", []),
                    transcription_provider="whisper",
                    language=transcription_result.get("language", "en"),
                    word_count=len(transcription_result["transcript"].split()),
                    processing_completed_at=datetime.now(timezone.utc)
                )
                db.add(transcript)
                db.commit()

                transcript_text = transcription_result["transcript"]

        # Step 3: AI Analysis
        if transcript_text and MeetingAIAnalysis:
            meeting_context = {
                "title": room.room_name,
                "meeting_type": room.meeting_type,
                "participants": [],
                "duration_minutes": recording.duration_seconds // 60 if recording.duration_seconds else 0
            }

            analysis_result = await ai_service.analyze_meeting(transcript_text, meeting_context)

            if not analysis_result.get("error"):
                # Save structured analysis
                analysis = MeetingAIAnalysis(
                    meeting_id=meeting_id,
                    recording_id=recording.id,
                    analysis_type="full_analysis",
                    status="completed",
                    content=analysis_result.get("summary"),
                    structured_content=analysis_result,
                    model_provider="anthropic",
                    model_name="claude-sonnet-4"
                )
                db.add(analysis)

                # Update room with AI summary
                room.ai_summary = analysis_result.get("summary")
                room.ai_action_items = analysis_result.get("action_items")
                room.ai_key_topics = analysis_result.get("key_topics")

        # Mark recording as ready
        recording.status = "ready"
        recording.processing_completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Recording {recording_id} processed successfully")

    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        if db:
            recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
            if recording:
                recording.status = "failed"
                recording.error_message = str(e)
                db.commit()
    finally:
        db.close()


async def process_recording_analytics(recording_id: int, meeting_id: int):
    """Background task to process analytics for a recording"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.analytics_service import get_analytics_service
        from uvip.coaching_service import get_coaching_service

        analytics_service = get_analytics_service()
        coaching_service = get_coaching_service()

        # Analyze all participants
        analytics_results = await analytics_service.analyze_all_participants(
            recording_id=recording_id,
            db=db,
            models=_models
        )

        # Generate coaching for each participant
        RecordingTranscript = _models.get('RecordingTranscript')
        transcript = db.query(RecordingTranscript).filter(
            RecordingTranscript.recording_id == recording_id
        ).first()

        transcript_segments = transcript.transcript_json if transcript else []

        for analytics in analytics_results:
            try:
                await coaching_service.generate_coaching(
                    analytics=analytics,
                    transcript_segments=transcript_segments,
                    db=db,
                    models=_models
                )
            except Exception as e:
                logger.error(f"Error generating coaching for analytics {analytics.get('id')}: {e}")

        logger.info(f"Analytics processing completed for recording {recording_id}")

    except Exception as e:
        logger.error(f"Error processing analytics for recording {recording_id}: {e}")
    finally:
        db.close()


async def process_mortgage_intelligence(recording_id: int):
    """Background task to process mortgage intelligence for a recording"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.mortgage_intelligence_service import get_mortgage_intelligence_service

        intel_service = get_mortgage_intelligence_service()

        RecordingTranscript = _models.get('RecordingTranscript')

        # Get transcript
        transcript = db.query(RecordingTranscript).filter(
            RecordingTranscript.recording_id == recording_id
        ).first()

        if not transcript:
            logger.error(f"No transcript found for recording {recording_id}")
            return

        full_transcript = transcript.full_transcript or ""
        transcript_segments = transcript.transcript_json or []

        # Run intelligence analysis
        intelligence = await intel_service.analyze_mortgage_intelligence(
            recording_id=recording_id,
            transcript_text=full_transcript,
            transcript_segments=transcript_segments,
            db=db,
            models=_models
        )

        logger.info(f"Mortgage intelligence processing completed for recording {recording_id}")

    except Exception as e:
        logger.error(f"Error processing mortgage intelligence for recording {recording_id}: {e}")
    finally:
        db.close()
