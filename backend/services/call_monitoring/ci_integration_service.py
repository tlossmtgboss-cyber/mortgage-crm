"""
CI Voice Integration Service

Bridges the existing CI Voice platform with the Call Monitoring AI agents.
When a call recording is transcribed, this service:
1. Creates a CallSession linked to the CI recording
2. Pulls the transcript and participant info
3. Triggers the 3 AI agents (Scribe, Junior LO, Underwriter)
4. Stores artifacts for review in the Call Intelligence tab
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class CIIntegrationService:
    """
    Integrates CI Voice recordings with Call Monitoring AI agents.
    """

    def __init__(self, db: Session):
        self.db = db

    async def process_completed_transcription(
        self,
        recording_id: str,
        transcription_id: str,
        run_agents: bool = True
    ) -> Dict[str, Any]:
        """
        Called when a CI Voice transcription completes.
        Creates a CallSession and optionally runs AI agents.

        Args:
            recording_id: UUID of the ci_call_recordings entry
            transcription_id: UUID of the ci_call_transcriptions entry
            run_agents: Whether to immediately run the AI agents

        Returns:
            Dict with session_id and processing status
        """
        try:
            logger.info(f"Processing completed transcription for recording {recording_id}")

            # 1. Get recording details
            recording = self._get_recording(recording_id)
            if not recording:
                logger.error(f"Recording {recording_id} not found")
                return {"error": "Recording not found", "recording_id": recording_id}

            # 2. Get transcription details
            transcription = self._get_transcription(transcription_id)
            if not transcription:
                logger.error(f"Transcription {transcription_id} not found")
                return {"error": "Transcription not found", "transcription_id": transcription_id}

            # 3. Check if CallSession already exists for this recording
            existing_session = self._get_existing_session(recording_id)
            if existing_session:
                logger.info(f"CallSession already exists for recording {recording_id}: {existing_session['id']}")
                session_id = existing_session['id']
            else:
                # 4. Create CallSession
                session_id = await self._create_call_session(recording, transcription)

            # 5. Run AI agents if requested
            if run_agents:
                asyncio.create_task(self._run_agents_async(str(session_id)))

            return {
                "status": "success",
                "session_id": str(session_id),
                "recording_id": recording_id,
                "agents_triggered": run_agents
            }

        except Exception as e:
            logger.error(f"Error processing transcription: {e}")
            return {"error": "Internal server error", "recording_id": recording_id}

    def _get_recording(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Get CI recording details."""
        result = self.db.execute(text("""
            SELECT
                id, external_call_id, call_type, direction,
                agent_user_id, contact_id, loan_id, lead_id,
                phone_from, phone_to, started_at, ended_at,
                duration_seconds, recording_url, status
            FROM ci_call_recordings
            WHERE id = :id
        """), {"id": recording_id}).fetchone()

        if result:
            return dict(result._mapping)
        return None

    def _get_transcription(self, transcription_id: str) -> Optional[Dict[str, Any]]:
        """Get transcription details including segments."""
        # Get main transcription
        result = self.db.execute(text("""
            SELECT
                id, recording_id, transcript_text, word_count,
                confidence_score, status
            FROM ci_call_transcriptions
            WHERE id = :id
        """), {"id": transcription_id}).fetchone()

        if not result:
            return None

        transcription = dict(result._mapping)

        # Get segments with speaker labels
        segments = self.db.execute(text("""
            SELECT
                speaker_label, start_time, end_time, text, confidence
            FROM ci_transcription_segments
            WHERE transcription_id = :id
            ORDER BY start_time
        """), {"id": transcription_id}).fetchall()

        transcription["segments"] = [dict(s._mapping) for s in segments]

        return transcription

    def _get_existing_session(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Check if a CallSession already exists for this recording."""
        result = self.db.execute(text("""
            SELECT id, status FROM call_sessions
            WHERE recording_id = :recording_id
        """), {"recording_id": recording_id}).fetchone()

        if result:
            return dict(result._mapping)
        return None

    async def _create_call_session(
        self,
        recording: Dict[str, Any],
        transcription: Dict[str, Any]
    ) -> UUID:
        """Create a CallSession from CI recording and transcription."""
        session_id = uuid4()

        # Determine capture mode based on recording metadata
        capture_mode = self._determine_capture_mode(recording)

        # Format transcript with speaker labels
        full_transcript = self._format_transcript(transcription)

        # Build participants list from segments
        participants = self._extract_participants(transcription, recording)

        # Create the session
        self.db.execute(text("""
            INSERT INTO call_sessions (
                id, capture_mode, recording_id,
                loan_id, lead_id, contact_id, user_id,
                status, transcript_state, full_transcript, transcript_word_count,
                participants, metadata,
                started_at, ended_at, duration_seconds,
                created_at, updated_at
            ) VALUES (
                :id, :capture_mode, :recording_id,
                :loan_id, :lead_id, :contact_id, :user_id,
                'processing', 'complete', :transcript, :word_count,
                :participants, :metadata,
                :started_at, :ended_at, :duration_seconds,
                NOW(), NOW()
            )
        """), {
            "id": str(session_id),
            "capture_mode": capture_mode,
            "recording_id": str(recording["id"]),
            "loan_id": str(recording["loan_id"]) if recording.get("loan_id") else None,
            "lead_id": str(recording["lead_id"]) if recording.get("lead_id") else None,
            "contact_id": str(recording["contact_id"]) if recording.get("contact_id") else None,
            "user_id": str(recording["agent_user_id"]) if recording.get("agent_user_id") else None,
            "transcript": full_transcript,
            "word_count": transcription.get("word_count"),
            "participants": json.dumps(participants),
            "metadata": json.dumps({
                "external_call_id": recording.get("external_call_id"),
                "direction": recording.get("direction"),
                "phone_from": recording.get("phone_from"),
                "phone_to": recording.get("phone_to"),
                "recording_url": recording.get("recording_url"),
                "transcription_confidence": transcription.get("confidence_score")
            }),
            "started_at": recording.get("started_at"),
            "ended_at": recording.get("ended_at"),
            "duration_seconds": recording.get("duration_seconds")
        })

        # Create participant records
        for participant in participants:
            self.db.execute(text("""
                INSERT INTO call_participants (
                    id, session_id, role, name, speaker_label,
                    contact_id, user_id, created_at
                ) VALUES (
                    :id, :session_id, :role, :name, :speaker_label,
                    :contact_id, :user_id, NOW()
                )
            """), {
                "id": str(uuid4()),
                "session_id": str(session_id),
                "role": participant.get("role", "other"),
                "name": participant.get("name"),
                "speaker_label": participant.get("speaker_label"),
                "contact_id": participant.get("contact_id"),
                "user_id": participant.get("user_id")
            })

        self.db.commit()
        logger.info(f"Created CallSession {session_id} for recording {recording['id']}")

        return session_id

    def _determine_capture_mode(self, recording: Dict[str, Any]) -> str:
        """Determine capture mode from recording metadata."""
        # Check for video call indicators
        metadata = recording.get("metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse recording metadata in _determine_capture_mode: {e}")
                metadata = {}

        if metadata.get("meeting_platform") in ["zoom", "teams", "meet"]:
            return "video_call"

        # Check for mobile app
        if metadata.get("source") == "mobile_app":
            return "mobile_app"

        # Check for ambient
        if metadata.get("capture_type") == "ambient":
            return "ambient_mic"

        # Default to CRM web call
        return "crm_web_call"

    def _format_transcript(self, transcription: Dict[str, Any]) -> str:
        """Format transcript with speaker labels."""
        segments = transcription.get("segments", [])

        if not segments:
            # Fall back to plain transcript text
            return transcription.get("transcript_text", "")

        lines = []
        for segment in segments:
            speaker = segment.get("speaker_label", "Speaker")
            text = segment.get("text", "").strip()
            if text:
                lines.append(f"[{speaker}]: {text}")

        return "\n".join(lines)

    def _extract_participants(
        self,
        transcription: Dict[str, Any],
        recording: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract unique participants from transcription segments."""
        segments = transcription.get("segments", [])
        speakers = set()

        for segment in segments:
            speaker = segment.get("speaker_label")
            if speaker:
                speakers.add(speaker)

        participants = []

        # Try to identify agent vs customer
        for i, speaker in enumerate(sorted(speakers)):
            role = "loan_officer" if i == 0 else "borrower"

            # Use recording metadata to improve role assignment
            participant = {
                "speaker_label": speaker,
                "role": role,
                "name": None,
                "contact_id": None,
                "user_id": None
            }

            # Link first speaker to agent
            if i == 0 and recording.get("agent_user_id"):
                participant["user_id"] = str(recording["agent_user_id"])
                participant["role"] = "loan_officer"

                # Get agent name
                agent = self.db.execute(text("""
                    SELECT name FROM users WHERE id = :id
                """), {"id": recording["agent_user_id"]}).fetchone()
                if agent:
                    participant["name"] = agent[0]

            # Link second speaker to contact
            elif i == 1 and recording.get("contact_id"):
                participant["contact_id"] = str(recording["contact_id"])
                participant["role"] = "borrower"

                # Get contact name
                contact = self.db.execute(text("""
                    SELECT first_name, last_name FROM contacts WHERE id = :id
                """), {"id": recording["contact_id"]}).fetchone()
                if contact:
                    participant["name"] = f"{contact[0]} {contact[1]}".strip()

            participants.append(participant)

        return participants

    async def _run_agents_async(self, session_id: str):
        """Run AI agents in the background."""
        try:
            from services.call_monitoring.orchestrator_service import CallMonitoringOrchestrator
            from database import get_db

            # Get new DB session for async task
            db = next(get_db())

            try:
                orchestrator = CallMonitoringOrchestrator(db)
                result = await orchestrator.run_agents(UUID(session_id))
                logger.info(f"Agents completed for session {session_id}: {result}")

                # Update CI recording status to 'analyzed'
                db.execute(text("""
                    UPDATE ci_call_recordings
                    SET status = 'analyzed',
                        analysis_status = 'completed',
                        updated_at = NOW()
                    WHERE id = (SELECT recording_id FROM call_sessions WHERE id = :session_id)
                """), {"session_id": session_id})
                db.commit()

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error running agents for session {session_id}: {e}")
            # Update session status to failed
            try:
                db = next(get_db())
                db.execute(text("""
                    UPDATE call_sessions
                    SET status = 'failed',
                        metadata = jsonb_set(
                            COALESCE(metadata, '{}'::jsonb),
                            '{agent_error}',
                            :error
                        ),
                        updated_at = NOW()
                    WHERE id = :session_id
                """), {"session_id": session_id, "error": json.dumps(str(e))})
                db.commit()
                db.close()
            except Exception as e:
                logger.error(f"Failed to update session status to failed in _run_agents_async: {e}")


async def trigger_call_monitoring_agents(
    db: Session,  # Not used - kept for API compatibility
    recording_id: str,
    transcription_id: str
) -> Dict[str, Any]:
    """
    Convenience function to trigger Call Monitoring agents.
    Call this from CI Voice routes when transcription completes.

    Note: Gets its own database session to avoid issues with the caller
    closing their session before this async task completes.
    """
    from database import get_db

    # Get our own database session for this async task
    db_session = next(get_db())

    try:
        service = CIIntegrationService(db_session)
        result = await service.process_completed_transcription(
            recording_id=recording_id,
            transcription_id=transcription_id,
            run_agents=True
        )
        return result
    except Exception as e:
        logger.error(f"Error in trigger_call_monitoring_agents: {e}")
        return {"error": "Internal server error", "recording_id": recording_id}
    finally:
        db_session.close()
