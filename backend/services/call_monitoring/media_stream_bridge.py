"""
Call Audio Bridge — captures audio from actual telephony calls into CI sessions.

Supports two modes:
1. Real-time: Fork Telnyx call media stream into CI transcription pipeline
2. Post-call: Fetch Telnyx/Twilio recording after call ends, transcribe, feed to agents
"""

import os
import logging
import json
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CallAudioBridge:
    """Bridges telephony call audio into Call Intelligence sessions."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    async def attach_telephony_call(
        self,
        session_id: str,
        telephony_call_id: str,
        provider: str = "telnyx",  # "telnyx" or "twilio"
    ) -> Dict[str, Any]:
        """
        Link a telephony call to a CI session.
        Stores the call ID so we can fetch the recording later.
        """
        self.db.execute(text("""
            UPDATE call_sessions
            SET metadata = COALESCE(metadata, '{}'::jsonb) || :call_data::jsonb,
                updated_at = NOW()
            WHERE id = :session_id AND organization_id = :org_id
        """), {
            "session_id": session_id,
            "org_id": self.organization_id,
            "call_data": json.dumps({
                "telephony_call_id": telephony_call_id,
                "call_provider": provider,
                "attached_at": datetime.utcnow().isoformat(),
            }),
        })
        self.db.flush()

        logger.info(
            f"Telephony call attached to CI session",
            extra={
                "session_id": session_id,
                "telephony_call_id": telephony_call_id,
                "provider": provider,
            },
        )
        return {"success": True, "session_id": session_id, "provider": provider}

    async def fetch_call_recording_url(
        self,
        telephony_call_id: str,
        provider: str = "telnyx",
    ) -> Optional[str]:
        """Fetch the recording URL from the telephony provider."""
        if provider == "telnyx":
            return await self._fetch_telnyx_recording(telephony_call_id)
        elif provider == "twilio":
            return await self._fetch_twilio_recording(telephony_call_id)
        else:
            logger.error(f"Unknown provider: {provider}")
            return None

    async def transcribe_recording(
        self,
        audio_url: str,
        session_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Transcribe a call recording using Deepgram API.
        Saves transcript to call_sessions.full_transcript.
        Returns transcript text and word count.
        """
        deepgram_key = os.getenv("DEEPGRAM_API_KEY")
        if not deepgram_key:
            return {"success": False, "error": "DEEPGRAM_API_KEY not configured"}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {deepgram_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "url": audio_url,
                        "model": "nova-2",
                        "language": language,
                        "smart_format": True,
                        "diarize": True,
                        "punctuate": True,
                        "utterances": True,
                    },
                )
                response.raise_for_status()
                result = response.json()

            # Extract transcript with speaker labels
            utterances = result.get("results", {}).get("utterances", [])
            if utterances:
                transcript_lines = []
                for utt in utterances:
                    speaker = f"Speaker {utt.get('speaker', '?')}"
                    text_content = utt.get("transcript", "")
                    transcript_lines.append(f"[{speaker}]: {text_content}")
                transcript_text = "\n".join(transcript_lines)
            else:
                # Fallback to channels/alternatives
                channels = result.get("results", {}).get("channels", [])
                if channels:
                    alternatives = channels[0].get("alternatives", [])
                    transcript_text = alternatives[0].get("transcript", "") if alternatives else ""
                else:
                    transcript_text = ""

            if not transcript_text:
                return {"success": False, "error": "No transcript generated from recording"}

            word_count = len(transcript_text.split())

            # Save to call_sessions
            self.db.execute(text("""
                UPDATE call_sessions
                SET full_transcript = :transcript,
                    transcript_word_count = :word_count,
                    transcript_state = 'complete',
                    updated_at = NOW()
                WHERE id = :session_id AND organization_id = :org_id
            """), {
                "transcript": transcript_text,
                "word_count": word_count,
                "session_id": session_id,
                "org_id": self.organization_id,
            })
            self.db.flush()

            logger.info(
                f"Recording transcribed and saved",
                extra={
                    "session_id": session_id,
                    "word_count": word_count,
                    "utterance_count": len(utterances),
                },
            )

            return {
                "success": True,
                "session_id": session_id,
                "word_count": word_count,
                "utterance_count": len(utterances),
                "has_diarization": len(utterances) > 0,
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Deepgram API error: {e.response.status_code} {e.response.text}")
            return {"success": False, "error": f"Transcription API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_post_call(
        self,
        session_id: str,
        trigger_agents: bool = True,
    ) -> Dict[str, Any]:
        """
        Full post-call processing pipeline:
        1. Get telephony call ID from session metadata
        2. Fetch recording URL from provider
        3. Transcribe via Deepgram
        4. Optionally trigger agent pipeline
        """
        # Get session metadata
        row = self.db.execute(text("""
            SELECT metadata FROM call_sessions
            WHERE id = :session_id AND organization_id = :org_id
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchone()

        if not row or not row.metadata:
            return {"success": False, "error": "Session not found or no metadata"}

        metadata = row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata)
        call_id = metadata.get("telephony_call_id")
        provider = metadata.get("call_provider", "telnyx")

        if not call_id:
            return {"success": False, "error": "No telephony call linked to this session"}

        # Fetch recording URL
        audio_url = await self.fetch_call_recording_url(call_id, provider)
        if not audio_url:
            return {"success": False, "error": f"Could not fetch recording from {provider}"}

        # Transcribe
        transcript_result = await self.transcribe_recording(audio_url, session_id)
        if not transcript_result.get("success"):
            return transcript_result

        # Trigger agents if requested
        agents_triggered = False
        if trigger_agents:
            try:
                from services.voice_ci_bridge_service import VoiceCIBridgeService
                bridge = VoiceCIBridgeService(self.db, self.organization_id, 0)
                triggered, method = await bridge._trigger_agent_pipeline(session_id)
                agents_triggered = triggered
            except Exception as e:
                logger.error(f"Failed to trigger agents after post-call processing: {e}")

        return {
            "success": True,
            "session_id": session_id,
            "word_count": transcript_result.get("word_count", 0),
            "has_diarization": transcript_result.get("has_diarization", False),
            "agents_triggered": agents_triggered,
        }

    # -------------------------------------------------------------------------
    # Private: Provider-specific recording fetch
    # -------------------------------------------------------------------------

    async def _fetch_telnyx_recording(self, call_control_id: str) -> Optional[str]:
        """Fetch recording URL from Telnyx API."""
        api_key = os.getenv("TELNYX_API_KEY")
        if not api_key:
            logger.error("TELNYX_API_KEY not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # List recordings for this call
                response = await client.get(
                    "https://api.telnyx.com/v2/recordings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params={"filter[call_control_id]": call_control_id},
                )
                response.raise_for_status()
                data = response.json()

                recordings = data.get("data", [])
                if not recordings:
                    logger.warning(f"No recordings found for call {call_control_id}")
                    return None

                # Get the most recent recording's download URL
                recording = recordings[0]
                recording_id = recording.get("id")
                if not recording_id:
                    return None

                # Get download URL
                dl_response = await client.get(
                    f"https://api.telnyx.com/v2/recordings/{recording_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                dl_response.raise_for_status()
                dl_data = dl_response.json().get("data", {})

                return dl_data.get("download_urls", {}).get("mp3") or dl_data.get("download_urls", {}).get("wav")

        except Exception as e:
            logger.error(f"Failed to fetch Telnyx recording: {e}")
            return None

    async def _fetch_twilio_recording(self, call_sid: str) -> Optional[str]:
        """Fetch recording URL from Twilio API."""
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        if not account_sid or not auth_token:
            logger.error("Twilio credentials not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}/Recordings.json",
                    auth=(account_sid, auth_token.strip()),
                )
                response.raise_for_status()
                data = response.json()

                recordings = data.get("recordings", [])
                if not recordings:
                    logger.warning(f"No recordings found for Twilio call {call_sid}")
                    return None

                recording_sid = recordings[0].get("sid")
                return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{recording_sid}.mp3"

        except Exception as e:
            logger.error(f"Failed to fetch Twilio recording: {e}")
            return None
