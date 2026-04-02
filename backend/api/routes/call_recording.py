# backend/api/routes/call_recording.py
"""
Call Recording Processing API
- Receives audio from mobile app
- Transcribes via OpenAI Whisper
- Summarizes with GPT-4
- Creates task with draft email
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import base64
import tempfile
import os
import hmac
import hashlib
import time
import httpx
from sqlalchemy.orm import Session

from database import get_db
from database.models import User, Task, Lead, Loan
from auth.dependencies import get_current_user
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

# Get OpenAI API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


SUPPORTED_AUDIO_FORMATS = {"wav", "mp3", "flac", "m4a", "ogg", "webm", "mp4", "mpeg"}


class CallProcessRequest(BaseModel):
    audioBase64: str
    audioFormat: str = "m4a"

    @property
    def validated_audio_format(self) -> str:
        fmt = self.audioFormat.lower().strip(".")
        if fmt not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(
                f"Unsupported audio format '{self.audioFormat}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
            )
        return fmt
    contactName: Optional[str] = None
    contactId: Optional[str] = None
    contactPhone: Optional[str] = None
    loanId: Optional[str] = None
    duration: Optional[int] = None  # seconds
    startTime: Optional[str] = None
    endTime: Optional[str] = None


class CallSummary(BaseModel):
    overview: str
    keyPoints: List[str]
    actionItems: List[str]
    followUpDate: Optional[str] = None
    sentiment: str  # positive, neutral, negative
    draftEmail: dict  # { subject: str, body: str }


class CallProcessResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    summary: Optional[CallSummary] = None
    taskId: Optional[int] = None
    error: Optional[str] = None


@router.post("/process", response_model=CallProcessResponse)
async def process_call_recording(
    request: CallProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Process a call recording:
    1. Transcribe audio
    2. Generate AI summary
    3. Create task with draft email
    """
    try:
        # Validate audio format
        try:
            audio_fmt = request.validated_audio_format
        except ValueError as e:
            return CallProcessResponse(success=False, error=str(e))

        # Decode audio
        audio_data = base64.b64decode(request.audioBase64)

        # Save to temp file
        with tempfile.NamedTemporaryFile(
            suffix=f".{audio_fmt}",
            delete=False
        ) as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name

        try:
            # Step 1: Transcribe with Whisper
            transcript = await transcribe_audio(temp_path)

            if not transcript:
                return CallProcessResponse(
                    success=False,
                    error="Failed to transcribe audio"
                )

            # Step 2: Get contact info if available
            contact_info = None
            if request.contactId:
                lead = db.query(Lead).filter(Lead.id == int(request.contactId)).first()
                if lead:
                    contact_info = {
                        "name": f"{lead.first_name} {lead.last_name}",
                        "email": lead.email,
                        "phone": lead.phone,
                    }
            elif request.contactName:
                contact_info = {"name": request.contactName}

            # Get loan info if available
            loan_info = None
            if request.loanId:
                loan = db.query(Loan).filter(Loan.id == int(request.loanId)).first()
                if loan:
                    loan_info = {
                        "loan_number": loan.loan_number,
                        "property_address": loan.property_address,
                        "loan_amount": str(loan.amount) if loan.amount else None,
                    }

            # Step 3: Generate summary with GPT
            summary = await generate_call_summary(
                transcript=transcript,
                contact_info=contact_info,
                loan_info=loan_info,
                user_name=current_user.full_name or current_user.email,
                duration=request.duration,
            )

            # Step 4: Create task with draft email
            task = create_followup_task(
                db=db,
                user_id=current_user.id,
                contact_id=request.contactId,
                loan_id=request.loanId,
                summary=summary,
                transcript=transcript,
            )

            return CallProcessResponse(
                success=True,
                transcript=transcript,
                summary=summary,
                taskId=task.id if task else None,
            )

        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Error processing call recording: {e}")
        return CallProcessResponse(
            success=False,
            error=str(e)
        )


async def transcribe_audio(audio_path: str) -> Optional[str]:
    """Transcribe audio file using OpenAI Whisper API."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key not configured")
            return None

        async with httpx.AsyncClient() as client:
            with open(audio_path, "rb") as audio_file:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": audio_file},
                    data={
                        "model": "whisper-1",
                        "language": "en",
                        "response_format": "text",
                    },
                    timeout=120.0,  # Long timeout for audio processing
                )

                if response.status_code != 200:
                    logger.error(f"Whisper API error: {response.text}")
                    return None

                return response.text.strip()

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None


async def generate_call_summary(
    transcript: str,
    contact_info: Optional[dict],
    loan_info: Optional[dict],
    user_name: str,
    duration: Optional[int],
) -> CallSummary:
    """Generate call summary using GPT-4."""
    try:
        if not OPENAI_API_KEY:
            raise Exception("OpenAI API key not configured")

        # Build context
        context_parts = []
        if contact_info:
            context_parts.append(f"Contact: {contact_info.get('name', 'Unknown')}")
        if loan_info:
            if loan_info.get('loan_number'):
                context_parts.append(f"Loan #: {loan_info['loan_number']}")
            if loan_info.get('property_address'):
                context_parts.append(f"Property: {loan_info['property_address']}")
        if duration:
            minutes = duration // 60
            seconds = duration % 60
            context_parts.append(f"Duration: {minutes}m {seconds}s")

        context = "\n".join(context_parts) if context_parts else "No additional context"

        prompt = f"""You are an AI assistant for a mortgage loan officer named {user_name}.
Analyze this phone call transcript and provide a structured summary.

CONTEXT:
{context}

TRANSCRIPT:
{transcript}

Provide a JSON response with:
1. "overview": A 2-3 sentence summary of the call
2. "keyPoints": Array of 3-5 key points discussed
3. "actionItems": Array of specific action items or follow-ups needed
4. "followUpDate": Suggested follow-up date if mentioned or appropriate (ISO format or null)
5. "sentiment": Overall call sentiment - "positive", "neutral", or "negative"
6. "draftEmail": An object with "subject" and "body" for a follow-up email summarizing the call and next steps

The draft email should:
- Be professional but friendly
- Reference specific items discussed
- Include any promised follow-up items
- Have a clear call to action if appropriate

Respond with valid JSON only, no markdown."""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4-turbo-preview",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                },
                timeout=60.0,
            )

            if response.status_code != 200:
                logger.error(f"GPT API error: {response.text}")
                raise Exception("Failed to generate summary")

            result = response.json()
            content = result["choices"][0]["message"]["content"]
            summary_data = json.loads(content)

            return CallSummary(
                overview=summary_data.get("overview", "Call summary not available"),
                keyPoints=summary_data.get("keyPoints", []),
                actionItems=summary_data.get("actionItems", []),
                followUpDate=summary_data.get("followUpDate"),
                sentiment=summary_data.get("sentiment", "neutral"),
                draftEmail=summary_data.get("draftEmail", {
                    "subject": "Follow-up from our call",
                    "body": "Thank you for your time on our call today."
                }),
            )

    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        # Return basic summary on error
        return CallSummary(
            overview="Call recorded. Manual review required.",
            keyPoints=["Call transcript available"],
            actionItems=["Review call transcript"],
            sentiment="neutral",
            draftEmail={
                "subject": "Follow-up from our call",
                "body": "Thank you for your time on our call today. Please let me know if you have any questions.",
            },
        )


def create_followup_task(
    db: Session,
    user_id: int,
    contact_id: Optional[str],
    loan_id: Optional[str],
    summary: CallSummary,
    transcript: str,
) -> Optional[Task]:
    """Create a task for the user to send follow-up email."""
    try:
        # Calculate due date (tomorrow if no follow-up date specified)
        if summary.followUpDate:
            try:
                due_date = datetime.fromisoformat(summary.followUpDate.replace("Z", "+00:00"))
            except Exception as e:
                logger.exception(f"Failed to parse followUpDate '{summary.followUpDate}': {e}")
                due_date = datetime.now(timezone.utc) + timedelta(days=1)
        else:
            due_date = datetime.now(timezone.utc) + timedelta(days=1)

        # Build task description
        description = f"""**Call Summary:**
{summary.overview}

**Key Points:**
{chr(10).join('• ' + point for point in summary.keyPoints)}

**Action Items:**
{chr(10).join('• ' + item for item in summary.actionItems)}

**Draft Email Ready** - Review and send the follow-up email.

---
*Transcript available in task metadata*"""

        task = Task(
            title=f"Send follow-up email: {summary.draftEmail.get('subject', 'Call follow-up')}",
            description=description,
            due_date=due_date,
            priority="high" if summary.sentiment == "negative" else "medium",
            status="pending",
            user_id=user_id,
            lead_id=int(contact_id) if contact_id else None,
            loan_id=int(loan_id) if loan_id else None,
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        logger.info(f"Created call follow-up task {task.id} for user {user_id}")
        return task

    except Exception as e:
        logger.error(f"Error creating task: {e}")
        db.rollback()
        return None


# ============================================================================
# SIGNED PLAYBACK URLS (CR-005)
# ============================================================================

_PLAYBACK_SECRET = os.getenv("SECRET_KEY", "fallback-dev-secret-key")
_PLAYBACK_TOKEN_TTL = 3600  # 1 hour


def generate_signed_playback_url(recording_id: str, base_url: str = "") -> dict:
    """Generate a time-limited signed URL for recording playback."""
    expires_at = int(time.time()) + _PLAYBACK_TOKEN_TTL
    payload = f"{recording_id}:{expires_at}"
    signature = hmac.new(
        _PLAYBACK_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    playback_path = f"/api/v1/calls/playback/{recording_id}?expires={expires_at}&sig={signature}"
    url = f"{base_url}{playback_path}" if base_url else playback_path

    return {
        "url": url,
        "expires_at": datetime.utcfromtimestamp(expires_at).isoformat() + "Z",
        "ttl_seconds": _PLAYBACK_TOKEN_TTL,
    }


def _verify_playback_signature(recording_id: str, expires: int, sig: str) -> bool:
    """Verify HMAC signature and expiration for playback URL."""
    if int(time.time()) > expires:
        return False
    payload = f"{recording_id}:{expires}"
    expected = hmac.new(
        _PLAYBACK_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig, expected)


@router.get("/playback/{recording_id}")
async def playback_recording(
    recording_id: str,
    expires: int = Query(..., description="Token expiration timestamp"),
    sig: str = Query(..., description="HMAC signature"),
):
    """
    Serve a recording with a signed, expiring token.
    Returns a redirect to the actual recording URL after verification.
    """
    if not _verify_playback_signature(recording_id, expires, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired playback token")

    # In production, look up the actual recording storage URL
    # (Telnyx recording URL, S3 presigned URL, etc.)
    recording_url = f"https://api.telnyx.com/v2/recordings/{recording_id}"

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=recording_url, status_code=302)


@router.post("/playback-url")
async def create_playback_url(
    recording_id: str,
    current_user: User = Depends(get_current_user),
):
    """Generate a signed, time-limited playback URL for a recording."""
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
    if base_url and not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    signed = generate_signed_playback_url(recording_id, base_url=base_url)
    return {
        "success": True,
        "playback": signed,
    }


@router.get("/history")
async def get_call_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's call recording history (via tasks)."""
    try:
        # Get tasks that are call follow-ups
        tasks = db.query(Task).filter(
            Task.user_id == current_user.id,
            Task.title.like("Send follow-up email:%"),
        ).order_by(Task.created_at.desc()).limit(limit).all()

        return {
            "calls": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                    "createdAt": task.created_at.isoformat() if task.created_at else None,
                    "dueDate": task.due_date.isoformat() if task.due_date else None,
                }
                for task in tasks
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching call history: {e}")
        raise HTTPException(500, "Failed to fetch call history")
