"""
Voice Routes - Call Recording & Transcript Processing

Contains:
- /call-status webhook
- /recording-ready webhook
- /transcript-complete webhook (deprecated)
- /transcripts endpoints (list, detail, customer)
- /voicemail-transcription webhook
- process_call_recording helper
- create_call_summary_email_draft helper
- parse_operator_results helper
- link_transcript_to_customer helper
- submit_to_voice_intelligence (deprecated stub)
"""
import os
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from database import get_db
from ai_receptionist_dashboard_models import AIReceptionistActivity

from .utils import mask_phone, get_models, voice_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# CALL STATUS & RECORDING WEBHOOKS
# ============================================================================

@router.post("/call-status")
async def handle_call_status(request: Request, db: Session = Depends(get_db)):
    """Webhook for call status updates"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        duration = form_data.get("CallDuration", "0")
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")

        logger.info(f"Call {call_sid} status: {call_status}, duration: {duration}s")

        # Update AI Receptionist Dashboard activity if it exists
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                # Update with final status
                activity.outcome_status = 'completed' if call_status == 'completed' else call_status
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['duration'] = int(duration)
                activity.extra_data['final_status'] = call_status
                db.commit()
                logger.info(f"Updated AI Receptionist activity for call {call_sid}")
        except Exception as update_error:
            logger.warning(f"Could not update activity for call {call_sid}: {update_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling call status: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.post("/recording-ready")
async def handle_recording_ready(request: Request, db: Session = Depends(get_db)):
    """Webhook when call recording is ready - transcribes, summarizes, and creates email draft"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        recording_url = form_data.get("RecordingUrl")
        recording_sid = form_data.get("RecordingSid")
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_duration = form_data.get("RecordingDuration", "0")

        logger.info(f"Recording ready for call {call_sid}: {recording_url}")

        # Update AI Receptionist Dashboard activity with recording URL
        activity = None
        user_id = None
        lead_id = None
        lead_name = None
        user_email = None

        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['recording_url'] = recording_url
                activity.extra_data['recording_sid'] = recording_sid
                # Use getattr since these columns may not exist in all versions
                user_id = getattr(activity, 'user_id', None) or (activity.extra_data.get('user_id') if activity.extra_data else None)
                lead_id = getattr(activity, 'lead_id', None) or (activity.extra_data.get('lead_id') if activity.extra_data else None)
                db.commit()
                logger.info(f"Updated activity with recording for call {call_sid}")

                # Get user email for draft creation
                if user_id:
                    from database.models import User
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        user_email = user.email

                # Get lead name if available
                if lead_id:
                    from database.models import Lead
                    lead = db.query(Lead).filter(Lead.id == lead_id).first()
                    if lead:
                        lead_name = lead.name

        except Exception as update_error:
            logger.warning(f"Could not update recording for call {call_sid}: {update_error}")

        # Process recording asynchronously (transcribe, summarize, create draft)
        asyncio.create_task(
            process_call_recording(
                recording_url=recording_url,
                recording_sid=recording_sid,
                call_sid=call_sid,
                caller_number=caller_number,
                call_duration=call_duration,
                user_id=user_id,
                user_email=user_email,
                lead_id=lead_id,
                lead_name=lead_name,
                db=db
            )
        )

        # Legacy Voice Intelligence removed — Deepgram handles transcription now.
        # No-op: intelligence submission skipped.

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling recording: {e}")
        return {"status": "error"}


@router.post("/transcript-complete")
async def handle_transcript_complete(request: Request, db: Session = Depends(get_db)):
    """
    Webhook from legacy Voice Intelligence when transcription is complete (DEPRECATED).

    Event type: voice_intelligence_transcript_available

    Receives transcript with:
    - Speaker-labeled sentences
    - PII redaction
    - Sentiment analysis (via operator)
    - Summarization (via operator)
    - Entity recognition (via operator)
    - Escalation detection (via operator)
    - Recording disclosure check (via operator)
    """
    try:
        # Try JSON first, then form data (provider sometimes uses either)
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            form_data = await request.form()
            data = dict(form_data)

        transcript_sid = data.get("transcript_sid") or data.get("TranscriptSid")
        service_sid = data.get("service_sid") or data.get("ServiceSid")
        customer_key = data.get("customer_key") or data.get("CustomerKey")
        event_type = data.get("event_type") or data.get("EventType")
        status = data.get("status") or data.get("Status")

        logger.info(f"Transcript webhook received: {transcript_sid}, event: {event_type}, status: {status}")

        # Handle specific event type
        if event_type and event_type != "voice_intelligence_transcript_available":
            logger.info(f"Ignoring event type: {event_type}")
            return {"status": "acknowledged", "event_type": event_type}

        # Also check status for non-event webhooks
        if not event_type and status and status != "completed":
            logger.info(f"Transcript {transcript_sid} status: {status}, waiting for completion")
            return {"status": "acknowledged"}

        # Legacy Intelligence service removed — Deepgram handles transcription now.
        # This webhook endpoint is kept for backward compatibility but returns a deprecation notice.
        logger.warning(f"Legacy Intelligence transcript-complete webhook called for {transcript_sid} — service has been removed. Deepgram handles transcription now.")
        return {
            "status": "deprecated",
            "message": "Legacy Intelligence service removed. Deepgram handles transcription.",
            "transcript_sid": transcript_sid
        }

    except Exception as e:
        logger.error(f"Error handling transcript webhook: {e}")
        return {"status": "error", "message": "Internal server error"}


# ============================================================================
# TRANSCRIPT RETRIEVAL ENDPOINTS
# ============================================================================

@router.get("/transcripts")
async def list_transcripts(
    db: Session = Depends(get_db),
    sentiment: str = None,
    escalation: bool = None,
    keyword: str = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List and search call transcripts.

    Args:
        sentiment: Filter by sentiment (positive, negative, neutral, mixed)
        escalation: Filter by escalation detection (true/false)
        keyword: Search transcripts by keyword
        limit: Max results to return
        offset: Pagination offset
    """
    try:
        from sqlalchemy import text

        # Build query with filters
        conditions = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if sentiment:
            conditions.append("sentiment->>'sentiment' = :sentiment OR sentiment = :sentiment_raw")
            params["sentiment"] = sentiment
            params["sentiment_raw"] = f'"{sentiment}"'

        if escalation is not None:
            # Check in entities or a dedicated field
            conditions.append("(entities::text ILIKE '%escalation%') = :escalation")
            params["escalation"] = escalation

        if keyword:
            conditions.append("full_text ILIKE :keyword")
            params["keyword"] = f"%{keyword}%"

        where_clause = " AND ".join(conditions)

        result = db.execute(text(f"""
            SELECT
                id, transcript_sid, status, duration_seconds,
                full_text, sentiment, summary, entities,
                topics, action_items, pii_detected, created_at
            FROM call_transcripts
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params)

        transcripts = []
        for row in result.fetchall():
            transcripts.append({
                "id": row[0],
                "transcript_sid": row[1],
                "status": row[2],
                "duration_seconds": row[3],
                "full_text": row[4][:500] + "..." if row[4] and len(row[4]) > 500 else row[4],
                "sentiment": row[5],
                "summary": row[6],
                "entities": row[7],
                "topics": row[8],
                "action_items": row[9],
                "pii_detected": row[10],
                "created_at": row[11].isoformat() if row[11] else None,
            })

        return {
            "transcripts": transcripts,
            "count": len(transcripts),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing transcripts: {e}")
        return {"transcripts": [], "error": "Internal server error"}


@router.get("/transcripts/{transcript_sid}")
async def get_transcript_detail(
    transcript_sid: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed transcript by SID.

    Returns full transcript with all sentences and AI insights.
    """
    try:
        from sqlalchemy import text

        result = db.execute(text("""
            SELECT
                id, transcript_sid, call_sid, recording_sid, activity_id,
                status, duration_seconds, language_code, full_text,
                sentences, sentiment, topics, action_items, entities,
                summary, redaction_enabled, pii_detected, created_at, updated_at
            FROM call_transcripts
            WHERE transcript_sid = :transcript_sid
        """), {"transcript_sid": transcript_sid})

        row = result.fetchone()
        if not row:
            return {"error": "Transcript not found"}

        return {
            "id": row[0],
            "transcript_sid": row[1],
            "call_sid": row[2],
            "recording_sid": row[3],
            "activity_id": row[4],
            "status": row[5],
            "duration_seconds": row[6],
            "language_code": row[7],
            "full_text": row[8],
            "sentences": row[9],
            "sentiment": row[10],
            "topics": row[11],
            "action_items": row[12],
            "entities": row[13],
            "summary": row[14],
            "redaction_enabled": row[15],
            "pii_detected": row[16],
            "created_at": row[17].isoformat() if row[17] else None,
            "updated_at": row[18].isoformat() if row[18] else None,
        }

    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        return {"error": "Internal server error"}


@router.get("/transcripts/customer/{customer_id}")
async def get_customer_transcripts(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all transcripts for a customer/lead.

    Searches by customer_key used when creating the transcript.
    """
    try:
        from sqlalchemy import text

        # Look for transcripts linked via activity or directly
        result = db.execute(text("""
            SELECT
                ct.id, ct.transcript_sid, ct.status, ct.duration_seconds,
                ct.sentiment, ct.summary, ct.created_at
            FROM call_transcripts ct
            LEFT JOIN ai_receptionist_activities ara ON
                ara.extra_data->>'transcript_sid' = ct.transcript_sid
            WHERE ara.lead_id::text = :customer_id
               OR ara.conversation_id = :customer_id
               OR ct.activity_id = :customer_id
            ORDER BY ct.created_at DESC
        """), {"customer_id": customer_id})

        transcripts = []
        for row in result.fetchall():
            transcripts.append({
                "id": row[0],
                "transcript_sid": row[1],
                "status": row[2],
                "duration_seconds": row[3],
                "sentiment": row[4],
                "summary": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            })

        return {
            "customer_id": customer_id,
            "total_conversations": len(transcripts),
            "transcripts": transcripts
        }

    except Exception as e:
        logger.error(f"Error getting customer transcripts: {e}")
        return {"customer_id": customer_id, "transcripts": [], "error": "Internal server error"}


@router.post("/voicemail-transcription")
async def handle_voicemail_transcription(request: Request, db: Session = Depends(get_db)):
    """Webhook for voicemail transcription"""
    try:
        _, _, Task, _, _ = get_models()

        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        transcription_text = form_data.get("TranscriptionText", "")
        caller = form_data.get("From", "Unknown")

        logger.info(f"Voicemail transcription from {mask_phone(caller)}: {transcription_text[:100]}")

        # Create task for team to follow up
        task = Task(
            title=f"Voicemail from {caller}",
            description=f"Transcription: {transcription_text}",
            status="PENDING",
            priority="MEDIUM",
            metadata={
                "call_sid": call_sid,
                "caller": caller,
                "type": "voicemail"
            }
        )
        db.add(task)
        db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling voicemail transcription: {e}")
        return {"status": "error"}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_operator_results(operator_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse operator results into structured insights.

    Operators may include:
    - sentiment-analysis: positive, negative, neutral, mixed
    - summarization: AI-generated summary
    - entity-recognition: names, amounts, dates, etc.
    - escalation-request: customer wants to escalate
    - recording-disclosure: recording was disclosed
    """
    insights = {
        "sentiment": None,
        "summary": None,
        "entities": [],
        "topics": [],
        "action_items": [],
        "escalation_detected": False,
        "recording_disclosed": False,
    }

    for result in operator_results:
        operator_type = result.get("operator_type", "").lower()
        operator_name = result.get("name", "").lower()
        results_data = result.get("results", {})

        # Handle different operator types
        if "sentiment" in operator_type or "sentiment" in operator_name:
            insights["sentiment"] = results_data.get("predicted_label") or results_data.get("sentiment")

        elif "summar" in operator_type or "summar" in operator_name:
            insights["summary"] = results_data.get("transcript_text") or results_data.get("summary")

        elif "entity" in operator_type or "entity" in operator_name:
            entities = results_data.get("extraction_results") or results_data.get("entities") or []
            insights["entities"] = entities

        elif "escalation" in operator_type or "escalation" in operator_name:
            label = results_data.get("predicted_label", "").lower()
            insights["escalation_detected"] = label in ["true", "yes", "escalation"]

        elif "recording" in operator_type or "disclosure" in operator_name:
            label = results_data.get("predicted_label", "").lower()
            insights["recording_disclosed"] = label in ["true", "yes", "disclosed"]

        elif "topic" in operator_type:
            topics = results_data.get("topics", [])
            insights["topics"] = topics

        elif "action" in operator_type:
            items = results_data.get("items", [])
            insights["action_items"] = items

    return insights


async def link_transcript_to_customer(
    db: Session,
    transcript_sid: str,
    customer_key: str,
    insights: Dict[str, Any]
):
    """Link transcript to customer/lead records and update with insights."""
    try:
        from sqlalchemy import text

        # Try to find and update related activity
        result = db.execute(text("""
            UPDATE ai_receptionist_activities
            SET extra_data = COALESCE(extra_data, '{}'::jsonb) || :insights_data
            WHERE conversation_id = :customer_key
               OR extra_data->>'customer_id' = :customer_key
        """), {
            "customer_key": customer_key,
            "insights_data": json.dumps({
                "transcript_sid": transcript_sid,
                "sentiment": insights.get("sentiment"),
                "summary": insights.get("summary"),
                "escalation_detected": insights.get("escalation_detected"),
            })
        })
        db.commit()

        if result.rowcount > 0:
            logger.info(f"Linked transcript {transcript_sid} to activity {customer_key}")

    except Exception as e:
        logger.warning(f"Could not link transcript to customer: {e}")


async def process_call_recording(
    recording_url: str,
    recording_sid: str,
    call_sid: str,
    caller_number: str,
    call_duration: str,
    user_id: int,
    user_email: str,
    lead_id: int,
    lead_name: str,
    db: Session
):
    """Process call recording: transcribe, summarize with AI, create email draft"""
    import httpx
    from anthropic import Anthropic

    logger.info(f"Processing call recording {recording_sid}...")

    try:
        # Step 1: Download the recording from Telnyx
        telnyx_api_key = os.getenv("TELNYX_API_KEY")

        if not telnyx_api_key:
            logger.error("TELNYX_API_KEY not configured — cannot download recording")
            return

        # Recording URL needs authentication
        recording_mp3_url = f"{recording_url}.mp3"

        async with httpx.AsyncClient() as client:
            # Download recording
            logger.info(f"Downloading recording from {recording_mp3_url}")
            recording_response = await client.get(
                recording_mp3_url,
                headers={"Authorization": f"Bearer {telnyx_api_key}"},
                timeout=60.0
            )

            if recording_response.status_code != 200:
                logger.error(f"Failed to download recording: {recording_response.status_code}")
                return

            audio_data = recording_response.content
            logger.info(f"Downloaded {len(audio_data)} bytes of audio")

            # Step 2: Transcribe with OpenAI Whisper
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.error("OpenAI API key not configured")
                return

            logger.info("Transcribing audio with Whisper...")
            transcribe_response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": ("recording.mp3", audio_data, "audio/mpeg")},
                data={"model": "whisper-1", "language": "en"},
                timeout=120.0
            )

            if transcribe_response.status_code != 200:
                logger.error(f"Transcription failed: {transcribe_response.text}")
                return

            transcript = transcribe_response.json().get("text", "")
            logger.info(f"Transcription complete: {len(transcript)} characters")

        # Step 3: Summarize with Claude
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            logger.error("Anthropic API key not configured")
            return

        logger.info("Generating professional summary with Claude...")
        anthropic_client = Anthropic(api_key=anthropic_key)

        client_identifier = lead_name or caller_number

        summary_prompt = f"""You are a professional assistant for a mortgage loan officer.
Summarize the following phone call transcript into a professional call summary.

Call Details:
- Client: {client_identifier}
- Phone: {caller_number}
- Duration: {call_duration} seconds
- Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

Transcript:
{transcript}

Create a professional call summary with the following sections:
1. **Call Overview** - Brief 1-2 sentence summary
2. **Key Discussion Points** - Bullet points of main topics discussed
3. **Client Needs/Requests** - What the client is looking for
4. **Action Items** - Any follow-up tasks or commitments made
5. **Next Steps** - Recommended next actions

Keep the summary concise but comprehensive. Use professional language appropriate for client records."""

        summary_response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            messages=[{"role": "user", "content": summary_prompt}]
        )

        summary = summary_response.content[0].text
        logger.info(f"Summary generated: {len(summary)} characters")

        # Step 4: Create email draft in user's Outlook
        if user_email:
            await create_call_summary_email_draft(
                user_email=user_email,
                client_name=client_identifier,
                caller_number=caller_number,
                call_duration=call_duration,
                summary=summary,
                transcript=transcript,
                recording_url=recording_url
            )
        else:
            logger.warning("No user email available, skipping draft creation")

        # Step 5: Store summary in database
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['transcript'] = transcript
                activity.extra_data['summary'] = summary
                activity.summary = summary[:500] if len(summary) > 500 else summary
                db.commit()
                logger.info(f"Stored summary for call {call_sid}")
        except Exception as db_error:
            logger.error(f"Failed to store summary: {db_error}")

        logger.info(f"Call recording processing complete for {call_sid}")

    except Exception as e:
        logger.error(f"Error processing call recording: {e}")


async def submit_to_voice_intelligence(
    recording_sid: str,
    caller_name: str = None,
    call_sid: str = None
):
    """
    Submit a recording to Voice Intelligence for enhanced transcription.
    DEPRECATED: Legacy Intelligence service has been removed. Deepgram handles transcription now.
    This function is a no-op stub kept for backward compatibility.
    """
    logger.warning(f"submit_to_voice_intelligence called for {recording_sid} — service removed. Deepgram handles transcription now.")
    return None

# Backward-compatible alias
submit_to_twilio_intelligence = submit_to_voice_intelligence


async def create_call_summary_email_draft(
    user_email: str,
    client_name: str,
    caller_number: str,
    call_duration: str,
    summary: str,
    transcript: str,
    recording_url: str
):
    """Create an email draft in the user's Outlook drafts folder"""
    import httpx
    from msal import ConfidentialClientApplication

    logger.info(f"Creating email draft for {user_email}...")

    try:
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
        duration_mins = int(call_duration) // 60 if call_duration.isdigit() else 0
        duration_secs = int(call_duration) % 60 if call_duration.isdigit() else 0

        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
<h2 style="color: #2c3e50;">Call Summary - {client_name}</h2>

<table style="margin-bottom: 20px; border-collapse: collapse;">
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Client:</td><td>{client_name}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Phone:</td><td>{caller_number}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Duration:</td><td>{duration_mins}m {duration_secs}s</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Date:</td><td>{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td></tr>
</table>

<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
{summary.replace(chr(10), '<br>')}
</div>

<details style="margin-top: 20px;">
<summary style="cursor: pointer; font-weight: bold; color: #3498db;">View Full Transcript</summary>
<div style="background: #f0f0f0; padding: 15px; margin-top: 10px; border-radius: 5px; white-space: pre-wrap; font-size: 13px;">
{transcript}
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
            "subject": f"Call Summary - {client_name} - {datetime.now().strftime('%m/%d/%Y')}",
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
                logger.info(f"Email draft created successfully: {draft_id}")
            else:
                logger.error(f"Failed to create draft: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error creating email draft: {e}")
