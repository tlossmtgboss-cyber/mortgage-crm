"""Call disposition endpoints with voice notes and AI summarization"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import logging
from datetime import datetime, timezone
import time
import os
import base64

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


# Import dependencies directly from main
from auth.dependencies import get_current_user
from database import get_db


# Keep set_dependencies for backwards compatibility (no-op now)
def set_dependencies(db_dependency, user_dependency):
    """Legacy function - dependencies now imported directly from main"""
    pass


# =============================================================================
# Enhanced Disposition Endpoints
# =============================================================================

@router.post("/task/{session_task_id}/disposition")
async def submit_task_disposition(
    session_task_id: int,
    disposition: str,
    notes: Optional[str] = None,
    follow_up_date: Optional[datetime] = None,
    voice_note_audio: Optional[str] = None,
    follow_up_required: bool = False,
    referral_opportunity: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Submit disposition for a dialer session task

    Enhanced features:
    - Voice note transcription via Whisper
    - AI-powered note summarization
    - Auto-task creation for follow-ups and referrals
    - DNC flag handling
    """
    from database.enums import DialerSessionStatus
    from database.models import DialerSessionTask, CallLog, DialerSession, Task, Lead as Contact
    from telephony.websocket import ws_manager
    from telephony.dialer_engine import DialerEngine

    # Find the task
    task = db.query(DialerSessionTask).filter(
        DialerSessionTask.id == session_task_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update task with disposition
    task.disposition = disposition
    task.notes = notes
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)

    # Update call log if exists
    if task.call_sid:
        call_log = db.query(CallLog).filter(
            CallLog.call_sid == task.call_sid
        ).first()

        if call_log:
            call_log.disposition = disposition
            call_log.notes = notes

    # Update session counters
    session = db.query(DialerSession).filter(
        DialerSession.id == task.session_id
    ).first()

    if session:
        session.completed_tasks = session.completed_tasks + 1 if session.completed_tasks else 1
        session.current_task_id = None

    db.commit()

    # Handle task creation based on disposition flags
    task_created = None

    if follow_up_required and follow_up_date:
        # Create follow-up task
        new_task = Task(
            user_id=current_user.id,
            title=f"Follow up: {task.contact_name}",
            description=f"Follow up from call: {notes or 'No notes'}",
            due_date=follow_up_date,
            priority="high",
            lead_id=task.lead_id,
            loan_id=task.loan_id,
            task_type="follow_up"
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)

        task_created = {
            "id": new_task.id,
            "type": "follow_up",
            "due_date": follow_up_date.isoformat() if follow_up_date else None
        }

    elif referral_opportunity:
        # Create referral opportunity task
        new_task = Task(
            user_id=current_user.id,
            title=f"Referral opportunity: {task.contact_name}",
            description=f"Referral opportunity from call: {notes or 'No notes'}",
            priority="medium",
            lead_id=task.lead_id,
            loan_id=task.loan_id,
            task_type="referral"
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)

        task_created = {
            "id": new_task.id,
            "type": "referral_opportunity",
            "due_date": None
        }

    # Handle DNC if applicable
    if disposition.lower() in ["do not call", "do not call again", "dnc"]:
        if task.lead_id:
            contact = db.query(Contact).filter(Contact.id == task.lead_id).first()
            if contact:
                contact.dnc_flag = True
                db.commit()
                logger.info(f"Added contact {task.lead_id} to DNC list")

    # Process voice note if provided
    ai_summary = None
    if voice_note_audio:
        try:
            ai_summary = await _process_voice_note(voice_note_audio, notes or "")
            if ai_summary:
                task.ai_note_summary = ai_summary
                if task.call_sid:
                    call_log = db.query(CallLog).filter(
                        CallLog.call_sid == task.call_sid
                    ).first()
                    if call_log:
                        call_log.ai_note_summary = ai_summary
                db.commit()
        except Exception as e:
            logger.error(f"Error processing voice note: {e}")

    # Send WebSocket update
    try:
        await ws_manager.send_to_agent(str(current_user.id), {
            "type": "disposition_saved",
            "task_id": session_task_id,
            "disposition": disposition,
            "task_created": task_created,
            "ai_summary": ai_summary
        })
    except Exception as e:
        logger.error(f"WebSocket notification error: {e}")

    # If session is still active, auto-advance to next call after delay
    if session and session.status == DialerSessionStatus.ACTIVE:
        # Don't block - let frontend handle the timing
        pass

    return {
        "success": True,
        "task_id": session_task_id,
        "disposition": disposition,
        "ai_note_summary": ai_summary,
        "task_created": task_created
    }


@router.post("/call-log/{call_log_id}/disposition")
async def submit_call_log_disposition(
    call_log_id: int,
    disposition: str,
    notes: Optional[str] = None,
    follow_up_date: Optional[datetime] = None,
    voice_note_audio: Optional[str] = None,
    follow_up_required: bool = False,
    referral_opportunity: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Submit disposition for a click-to-dial call log

    Use this endpoint for standalone calls (not part of a dialer session)
    """
    from database.models import CallLog, Task, Lead as Contact

    call_log = db.query(CallLog).filter(
        CallLog.id == call_log_id,
        CallLog.agent_id == current_user.id
    ).first()

    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found")

    call_log.disposition = disposition
    call_log.notes = notes

    # Handle task creation
    task_created = None

    if follow_up_required and follow_up_date:
        new_task = Task(
            user_id=current_user.id,
            title=f"Follow up call",
            description=f"Follow up from call: {notes or 'No notes'}",
            due_date=follow_up_date,
            priority="high",
            lead_id=call_log.lead_id,
            loan_id=call_log.loan_id,
            task_type="follow_up"
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)

        task_created = {
            "id": new_task.id,
            "type": "follow_up",
            "due_date": follow_up_date.isoformat() if follow_up_date else None
        }

    elif referral_opportunity:
        new_task = Task(
            user_id=current_user.id,
            title=f"Referral opportunity",
            description=f"Referral opportunity from call: {notes or 'No notes'}",
            priority="medium",
            lead_id=call_log.lead_id,
            loan_id=call_log.loan_id,
            task_type="referral"
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)

        task_created = {
            "id": new_task.id,
            "type": "referral_opportunity",
            "due_date": None
        }

    # Handle DNC
    if disposition.lower() in ["do not call", "do not call again", "dnc"]:
        if call_log.lead_id:
            contact = db.query(Contact).filter(Contact.id == call_log.lead_id).first()
            if contact:
                contact.dnc_flag = True

    db.commit()

    # Process voice note
    ai_summary = None
    if voice_note_audio:
        try:
            ai_summary = await _process_voice_note(voice_note_audio, notes or "")
            if ai_summary:
                call_log.ai_note_summary = ai_summary
                db.commit()
        except Exception as e:
            logger.error(f"Error processing voice note: {e}")

    return {
        "success": True,
        "call_log_id": call_log_id,
        "disposition": disposition,
        "ai_note_summary": ai_summary,
        "task_created": task_created
    }


# =============================================================================
# Voice Note Processing
# =============================================================================

async def _process_voice_note(audio_base64: str, context_notes: str) -> Optional[str]:
    """
    Process voice note with transcription and AI summary

    Args:
        audio_base64: Base64 encoded audio (webm/mp3/wav)
        context_notes: Additional context from written notes

    Returns:
        AI-generated summary or None if processing fails
    """
    try:
        from openai import OpenAI

        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            logger.warning("OPENAI_API_KEY not set, skipping voice note processing")
            return None

        # Decode base64 audio
        audio_data = base64.b64decode(audio_base64)

        # Save temporarily
        temp_file = f"/tmp/voice_note_{datetime.now(timezone.utc).timestamp()}.webm"
        try:
            with open(temp_file, 'wb') as f:
                f.write(audio_data)

            # Transcribe with Whisper
            client = OpenAI(api_key=openai_key)

            with open(temp_file, 'rb') as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

            if not transcript.text:
                return None

            # Generate summary with GPT-4
            prompt = f"""The loan officer just completed a call and provided this voice note recap:

{transcript.text}

Additional context notes: {context_notes}

Generate a structured summary including:
1. Call outcome and next steps
2. Action items (if any)
3. Referral opportunities mentioned (if any)
4. Buyer psychology indicators or concerns

Keep it concise and professional. Format as bullet points."""

            completion = client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": "You are a mortgage CRM assistant helping summarize call notes. Be concise and actionable."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )

            summary = completion.choices[0].message.content
            return summary

        finally:
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    except Exception as e:
        logger.error(f"Error in voice note processing: {e}")
        return None


# =============================================================================
# Disposition Options Endpoint
# =============================================================================

@router.get("/dispositions")
async def get_disposition_options():
    """Get available disposition options for the UI"""
    return {
        "dispositions": [
            {"code": "connected", "label": "Connected - Spoke with contact", "category": "success"},
            {"code": "voicemail", "label": "Left Voicemail", "category": "neutral"},
            {"code": "no_answer", "label": "No Answer", "category": "neutral"},
            {"code": "busy", "label": "Busy Signal", "category": "neutral"},
            {"code": "callback_scheduled", "label": "Callback Scheduled", "category": "success"},
            {"code": "not_interested", "label": "Not Interested", "category": "closed"},
            {"code": "wrong_number", "label": "Wrong Number", "category": "closed"},
            {"code": "do_not_call", "label": "Do Not Call Again", "category": "dnc"},
            {"code": "application_taken", "label": "Application Taken", "category": "success"},
            {"code": "referral_given", "label": "Referral Given", "category": "success"},
        ],
        "flags": [
            {"code": "follow_up_required", "label": "Schedule Follow-up"},
            {"code": "referral_opportunity", "label": "Referral Opportunity"},
            {"code": "hot_lead", "label": "Hot Lead"},
        ]
    }
