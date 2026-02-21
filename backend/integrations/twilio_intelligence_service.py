"""
Twilio Voice Intelligence Service

Provides AI-powered transcription and analysis of call recordings:
- Automatic transcription with speaker diarization
- PII redaction (phone, SSN, etc.)
- Sentiment analysis and insights
- Entity recognition (names, amounts, dates)
- Conversation summarization
- Escalation detection
- Compliance monitoring (recording disclosure)

Requires:
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_INTELLIGENCE_SERVICE_SID (created once via create_intelligence_service())

Supported Audio Formats:
- WAV (PCM-encoded), MP3, FLAC
- Max file size: 3GB
- Max duration: 8 hours
- Min sample rate: 8kHz (16kHz recommended)
- Dual-channel recommended for speaker differentiation

Setup Steps:
1. service_sid = intelligence_service.create_intelligence_service()
2. intelligence_service.attach_operators_to_service(service_sid)
3. Add TWILIO_INTELLIGENCE_SERVICE_SID to .env
"""

import os
import logging
from typing import Optional, Dict, List, Any
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from datetime import datetime

logger = logging.getLogger(__name__)

# Available language operators for analysis
# Names matched against Twilio's friendly_name (case-insensitive, hyphen/space normalized)
RECOMMENDED_OPERATORS = [
    'sentiment',               # Matches "Sentiment Analysis"
    'summary',                 # Matches "Conversation Summary"
    'entity',                  # Matches "Entity Recognition"
    'escalation',              # Matches "Escalation Request"
    'recording disclosure',    # Matches "Recording Disclosure"
]


class TwilioIntelligenceService:
    """Twilio Voice Intelligence for call transcription and analysis"""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        self.service_sid = os.getenv("TWILIO_INTELLIGENCE_SERVICE_SID", "")

        # Webhook URL for transcript completion
        self.webhook_base = os.getenv("PRODUCTION_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN", "")

        # Check if we have credentials
        has_credentials = self.account_sid and self.auth_token

        if has_credentials:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("Twilio Intelligence Service initialized successfully")
                self.enabled = True
            except Exception as e:
                self.client = None
                self.enabled = False
                logger.error(f"Failed to initialize Twilio Intelligence: {e}")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio Intelligence credentials not configured")

    def create_intelligence_service(
        self,
        unique_name: str = "MortgageCRMService",
        friendly_name: str = "Mortgage CRM Intelligence Service"
    ) -> Optional[str]:
        """
        Create a new Intelligence Service for the CRM.
        This only needs to be done ONCE - store the returned SID in env vars.

        Returns:
            Service SID if successful, None otherwise
        """
        if not self.enabled:
            logger.error("Twilio client not enabled")
            return None

        try:
            webhook_url = f"https://{self.webhook_base}/api/v1/voice/transcript-complete" if self.webhook_base else None

            service = self.client.intelligence.v2.services.create(
                unique_name=unique_name,
                friendly_name=friendly_name,
                auto_transcribe=True,      # Auto-transcribe all recordings
                auto_redaction=True,       # Auto-redact PII (SSN, phone numbers, etc.)
                media_redaction=False,     # Set True to also redact audio (costs more)
                language_code="en-US",
                webhook_url=webhook_url,
                webhook_http_method="POST"
            )

            logger.info(f"Intelligence Service Created: {service.sid}")
            logger.info(f"Service Name: {service.unique_name}")
            logger.info(f"Add this to your environment: TWILIO_INTELLIGENCE_SERVICE_SID={service.sid}")

            return service.sid

        except TwilioRestException as e:
            logger.error(f"Twilio error creating service: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating intelligence service: {e}")
            return None

    def get_service_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the configured Intelligence Service"""
        if not self.enabled or not self.service_sid:
            logger.warning("Intelligence service not configured")
            return None

        try:
            service = self.client.intelligence.v2.services(self.service_sid).fetch()

            return {
                "sid": service.sid,
                "unique_name": service.unique_name,
                "friendly_name": service.friendly_name,
                "auto_transcribe": service.auto_transcribe,
                "auto_redaction": service.auto_redaction,
                "media_redaction": service.media_redaction,
                "language_code": service.language_code,
                "webhook_url": service.webhook_url,
                "date_created": service.date_created.isoformat() if service.date_created else None,
            }

        except TwilioRestException as e:
            logger.error(f"Error fetching service info: {e}")
            return None

    def attach_operators_to_service(
        self,
        service_sid: Optional[str] = None,
        operator_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Attach language operators to the Intelligence Service.
        This enables automatic AI analysis of all transcripts.

        Should be called once after creating the service.

        Args:
            service_sid: Service SID (uses configured one if not provided)
            operator_names: List of operator names to attach (uses recommended if not provided)

        Returns:
            List of attached operators
        """
        if not self.enabled:
            logger.error("Twilio client not enabled")
            return []

        sid = service_sid or self.service_sid
        if not sid:
            logger.error("No service SID provided")
            return []

        names_to_attach = operator_names or RECOMMENDED_OPERATORS

        try:
            # List available operators for English (general-availability)
            available_operators = self.client.intelligence.v2.operators.list(
                availability='general-availability',
                language_code='en'
            )

            attached = []

            for operator in available_operators:
                # Check if this operator matches any we want
                # Normalize both names: remove hyphens, lowercase
                operator_normalized = operator.friendly_name.lower().replace("-", " ")
                should_attach = any(
                    name.lower().replace("-", " ") in operator_normalized or
                    name.lower().replace("-", "") in operator_normalized.replace(" ", "")
                    for name in names_to_attach
                )

                if should_attach:
                    try:
                        # Attach operator to service using correct API path
                        attachment = self.client.intelligence.v2.operator_attachment(
                            service_sid=sid,
                            operator_sid=operator.sid
                        ).create()

                        attached.append({
                            "operator_sid": operator.sid,
                            "operator_name": operator.friendly_name,
                            "status": "attached"
                        })
                        logger.info(f"Attached operator: {operator.friendly_name} ({operator.sid})")

                    except TwilioRestException as e:
                        if "already attached" in str(e).lower():
                            logger.info(f"Operator already attached: {operator.friendly_name}")
                            attached.append({
                                "operator_sid": operator.sid,
                                "operator_name": operator.friendly_name,
                                "already_attached": True
                            })
                        else:
                            logger.warning(f"Could not attach {operator.friendly_name}: {e}")

            logger.info(f"Attached {len(attached)} operators to service {sid}")
            return attached

        except TwilioRestException as e:
            logger.error(f"Error attaching operators: {e}")
            return []

    def list_available_operators(self, language_code: str = "en") -> List[Dict[str, Any]]:
        """List all available public operators for a language"""
        if not self.enabled:
            return []

        try:
            operators = self.client.intelligence.v2.operators.list(
                availability='general-availability',
                language_code=language_code
            )

            return [
                {
                    "sid": op.sid,
                    "friendly_name": op.friendly_name,
                    "operator_type": op.operator_type,
                    "description": getattr(op, 'description', None),
                }
                for op in operators
            ]

        except TwilioRestException as e:
            logger.error(f"Error listing operators: {e}")
            return []

    async def transcribe_recording(
        self,
        recording_url: str,
        participants: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Submit a recording for transcription and analysis.

        Args:
            recording_url: URL to the recording (Twilio recording URL or external)
            participants: Optional list of participants with roles
                         [{"role": "customer", "channel": 1}, {"role": "agent", "channel": 2}]
            metadata: Optional metadata to attach to the transcript

        Returns:
            Transcript object info if successful
        """
        if not self.enabled or not self.service_sid:
            logger.warning("Intelligence service not configured")
            return None

        try:
            # Build participant list for speaker diarization
            channel_participants = []
            if participants:
                for p in participants:
                    channel_participants.append({
                        "channel_participant": p.get("channel", 1),
                        "user_id": p.get("user_id"),
                        "role": p.get("role", "unknown"),
                        "full_name": p.get("name"),
                        "email": p.get("email"),
                        "phone_number": p.get("phone"),
                    })
            else:
                # Default: 2-party call (customer and agent)
                channel_participants = [
                    {"channel_participant": 1, "role": "customer"},
                    {"channel_participant": 2, "role": "agent"}
                ]

            # Create transcript
            transcript = self.client.intelligence.v2.transcripts.create(
                service_sid=self.service_sid,
                channel={
                    "media_properties": {
                        "source_sid": recording_url if recording_url.startswith("RE") else None,
                        "media_url": recording_url if not recording_url.startswith("RE") else None,
                    },
                    "participants": channel_participants
                }
            )

            logger.info(f"Transcript job created: {transcript.sid}")

            return {
                "transcript_sid": transcript.sid,
                "status": transcript.status,
                "service_sid": transcript.service_sid,
                "date_created": transcript.date_created.isoformat() if transcript.date_created else None,
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error creating transcript: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating transcript: {e}")
            return None

    async def get_transcript(self, transcript_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get a transcript by SID.

        Returns transcript with:
        - Full text (redacted if auto_redaction is enabled)
        - Speaker-labeled sentences
        - Sentiment analysis
        - Detected entities
        """
        if not self.enabled:
            return None

        try:
            transcript = self.client.intelligence.v2.transcripts(transcript_sid).fetch()

            result = {
                "sid": transcript.sid,
                "status": transcript.status,
                "duration": transcript.duration,
                "language_code": transcript.language_code,
                "date_created": transcript.date_created.isoformat() if transcript.date_created else None,
                "date_updated": transcript.date_updated.isoformat() if transcript.date_updated else None,
                "redaction": transcript.redaction,
            }

            # If completed, get the full transcript text
            if transcript.status == "completed":
                # Get sentences with speaker labels
                sentences = self.client.intelligence.v2.transcripts(
                    transcript_sid
                ).sentences.list(limit=1000)

                result["sentences"] = [
                    {
                        "text": s.transcript,
                        "speaker": s.participant_role,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "confidence": s.confidence,
                    }
                    for s in sentences
                ]

                # Build full transcript text
                result["full_text"] = "\n".join([
                    f"{s['speaker']}: {s['text']}" for s in result["sentences"]
                ])

            return result

        except TwilioRestException as e:
            logger.error(f"Error fetching transcript: {e}")
            return None

    async def get_transcript_media(self, transcript_sid: str) -> Optional[Dict[str, Any]]:
        """Get media information for a transcript (recording details)"""
        if not self.enabled:
            return None

        try:
            media = self.client.intelligence.v2.transcripts(
                transcript_sid
            ).media.fetch()

            return {
                "media_url": media.media_url,
                "duration": media.duration,
                "content_type": media.content_type,
            }

        except TwilioRestException as e:
            logger.error(f"Error fetching transcript media: {e}")
            return None

    async def get_operator_results(
        self,
        transcript_sid: str,
        operator_type: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get AI operator results (insights) for a transcript.

        Operator types include:
        - sentiment: Overall and per-sentence sentiment
        - entities: Detected entities (names, dates, amounts)
        - topics: Detected topics and categories
        - summary: AI-generated call summary
        - action_items: Detected action items

        Args:
            transcript_sid: The transcript SID
            operator_type: Optional filter for specific operator type
        """
        if not self.enabled:
            return None

        try:
            operators = self.client.intelligence.v2.transcripts(
                transcript_sid
            ).operator_results.list()

            results = []
            for op in operators:
                if operator_type and op.operator_type != operator_type:
                    continue

                results.append({
                    "operator_type": op.operator_type,
                    "name": op.name,
                    "status": op.status,
                    "results": op.results,
                    "date_created": op.date_created.isoformat() if op.date_created else None,
                })

            return results

        except TwilioRestException as e:
            logger.error(f"Error fetching operator results: {e}")
            return None

    async def get_call_summary(self, transcript_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get AI-generated summary and insights for a call.

        Returns:
        - summary: Brief summary of the call
        - sentiment: Overall call sentiment
        - topics: Main topics discussed
        - action_items: Any action items identified
        - entities: Key entities (names, amounts, dates)
        """
        if not self.enabled:
            return None

        try:
            # Get all operator results
            operators = await self.get_operator_results(transcript_sid)

            if not operators:
                return None

            summary = {
                "transcript_sid": transcript_sid,
                "summary": None,
                "sentiment": None,
                "topics": [],
                "action_items": [],
                "entities": [],
            }

            for op in operators:
                if op["operator_type"] == "summary":
                    summary["summary"] = op.get("results", {}).get("summary")
                elif op["operator_type"] == "sentiment":
                    summary["sentiment"] = op.get("results")
                elif op["operator_type"] == "topics":
                    summary["topics"] = op.get("results", {}).get("topics", [])
                elif op["operator_type"] == "action_items":
                    summary["action_items"] = op.get("results", {}).get("items", [])
                elif op["operator_type"] == "entities":
                    summary["entities"] = op.get("results", {}).get("entities", [])

            return summary

        except Exception as e:
            logger.error(f"Error getting call summary: {e}")
            return None

    async def list_transcripts(
        self,
        status: Optional[str] = None,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List transcripts with optional filters.

        Args:
            status: Filter by status (queued, in-progress, completed, failed)
            before: Only transcripts created before this date
            after: Only transcripts created after this date
            limit: Maximum number to return
        """
        if not self.enabled:
            return []

        try:
            kwargs = {"limit": limit}
            if status:
                kwargs["status"] = status
            if before:
                kwargs["before_date_created"] = before
            if after:
                kwargs["after_date_created"] = after

            transcripts = self.client.intelligence.v2.transcripts.list(**kwargs)

            return [
                {
                    "sid": t.sid,
                    "status": t.status,
                    "duration": t.duration,
                    "language_code": t.language_code,
                    "date_created": t.date_created.isoformat() if t.date_created else None,
                }
                for t in transcripts
            ]

        except TwilioRestException as e:
            logger.error(f"Error listing transcripts: {e}")
            return []

    async def delete_transcript(self, transcript_sid: str) -> bool:
        """Delete a transcript (for data retention compliance)"""
        if not self.enabled:
            return False

        try:
            self.client.intelligence.v2.transcripts(transcript_sid).delete()
            logger.info(f"Deleted transcript: {transcript_sid}")
            return True

        except TwilioRestException as e:
            logger.error(f"Error deleting transcript: {e}")
            return False


# Global instance
intelligence_service = TwilioIntelligenceService()


# Convenience functions
async def transcribe_call_recording(
    recording_sid_or_url: str,
    caller_name: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to transcribe a Twilio recording.

    Args:
        recording_sid_or_url: Twilio recording SID (RExxxxx) or recording URL
        caller_name: Optional name of the caller
        agent_name: Optional name of the agent
    """
    participants = [
        {"role": "customer", "channel": 1, "name": caller_name},
        {"role": "agent", "channel": 2, "name": agent_name or "Agent"},
    ]

    return await intelligence_service.transcribe_recording(
        recording_url=recording_sid_or_url,
        participants=participants
    )


async def get_call_insights(transcript_sid: str) -> Optional[Dict[str, Any]]:
    """
    Get full insights for a call including transcript and AI analysis.
    """
    transcript = await intelligence_service.get_transcript(transcript_sid)
    if not transcript:
        return None

    summary = await intelligence_service.get_call_summary(transcript_sid)

    return {
        "transcript": transcript,
        "insights": summary,
    }
