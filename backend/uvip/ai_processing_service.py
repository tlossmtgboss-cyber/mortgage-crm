"""
UVIP AI Processing Service
Handles transcription and AI analysis of meeting recordings
"""
import os
import logging
import json
import re
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from openai import OpenAI
import anthropic

logger = logging.getLogger(__name__)


class AIProcessingService:
    """
    AI service for processing meeting recordings.
    - Transcription via OpenAI Whisper
    - Analysis via Claude (mortgage-specific insights)
    """

    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        # Initialize OpenAI client
        self.openai_client = None
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
            logger.info("OpenAI client initialized for UVIP")

        # Initialize Anthropic client
        self.anthropic_client = None
        if self.anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            logger.info("Anthropic client initialized for UVIP")

    async def transcribe_audio(
        self,
        audio_content: bytes,
        language: str = "en",
        audio_format: str = "mp3"
    ) -> Dict[str, Any]:
        """
        Transcribe audio using OpenAI Whisper.

        Args:
            audio_content: Raw audio bytes
            language: Language code (default: English)
            audio_format: Audio format (mp3, wav, etc.)

        Returns:
            Dict with transcript text and segments
        """
        if not self.openai_client:
            return {"error": "OpenAI not configured", "transcript": "", "segments": []}

        try:
            # Create a temporary file-like object for Whisper
            import io
            audio_file = io.BytesIO(audio_content)
            audio_file.name = f"recording.{audio_format}"

            # Use Whisper for transcription with word timestamps
            response = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]
            )

            # Parse response
            result = {
                "transcript": response.text,
                "language": response.language,
                "duration": response.duration,
                "segments": []
            }

            # Add segments if available
            if hasattr(response, 'segments') and response.segments:
                result["segments"] = [
                    {
                        "id": i,
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", ""),
                        "speaker": "Speaker 1"  # Whisper doesn't do diarization
                    }
                    for i, seg in enumerate(response.segments)
                ]

            logger.info(f"Transcribed {response.duration:.1f}s of audio")
            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {"error": "Internal server error", "transcript": "", "segments": []}

    async def analyze_meeting(
        self,
        transcript: str,
        meeting_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze meeting transcript using Claude with mortgage-specific insights.

        Args:
            transcript: Full transcript text
            meeting_context: Context about the meeting (type, participants, etc.)

        Returns:
            Dict with analysis results
        """
        if not self.anthropic_client:
            return {"error": "Anthropic not configured"}

        try:
            # Build analysis prompt
            prompt = self._build_analysis_prompt(transcript, meeting_context)

            # Call Claude for analysis
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Parse the JSON response
            analysis_text = response.content[0].text
            analysis = self._parse_analysis_response(analysis_text)

            logger.info("Meeting analysis completed successfully")
            return analysis

        except Exception as e:
            logger.error(f"Meeting analysis failed: {e}")
            return {"error": "Internal server error"}

    def _build_analysis_prompt(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> str:
        """Build the mortgage-specific analysis prompt."""

        meeting_title = context.get("title", "Meeting")
        meeting_type = context.get("meeting_type", "general")
        participants = context.get("participants", [])
        duration = context.get("duration_minutes", 0)

        participant_list = ", ".join(participants) if participants else "Unknown"

        prompt = f"""You are an expert mortgage industry analyst. Analyze this meeting recording transcript and provide comprehensive insights.

Meeting Context:
- Title: {meeting_title}
- Type: {meeting_type}
- Participants: {participant_list}
- Duration: {duration} minutes

Transcript:
---
{transcript}
---

Provide a structured analysis in JSON format with the following fields:

{{
    "summary": "2-3 sentence executive summary of the meeting",
    "key_topics": [
        {{
            "topic": "Topic name",
            "summary": "Brief description of what was discussed",
            "timestamp_hint": "Approximate location in meeting (early/middle/late)"
        }}
    ],
    "action_items": [
        {{
            "description": "Specific task that needs to be done",
            "assignee": "Person responsible (or 'Unassigned')",
            "priority": "high/medium/low",
            "due_hint": "Any mentioned deadline or urgency",
            "category": "document/followup/review/approval/other"
        }}
    ],
    "decisions_made": [
        {{
            "decision": "What was decided",
            "context": "Why or how this decision was reached"
        }}
    ],
    "questions_discussed": [
        {{
            "question": "Question that was asked",
            "answer": "Answer provided (if any)",
            "resolved": true/false
        }}
    ],
    "sentiment": {{
        "overall": "positive/neutral/negative/mixed",
        "borrower_sentiment": "positive/neutral/negative/concerned (if applicable)",
        "notes": "Brief explanation of sentiment"
    }},
    "engagement_metrics": {{
        "participation_balance": "balanced/one-sided/varied",
        "energy_level": "high/medium/low",
        "collaboration_score": 0.0-1.0
    }},
    "mortgage_insights": {{
        "loan_type_mentioned": "Conventional/FHA/VA/USDA/Jumbo/null",
        "loan_amount_mentioned": "Amount or null",
        "rate_discussed": true/false,
        "rate_mentioned": "Rate value or null",
        "timeline_mentioned": "Days/weeks timeline or null",
        "property_type": "SFR/Condo/Multi-family/null",
        "purchase_vs_refi": "Purchase/Refinance/null",
        "current_stage": "Pre-qualification/Application/Processing/Underwriting/Closing/null",
        "next_milestone": "What's the next step mentioned",
        "potential_issues": ["List of any concerns or red flags mentioned"],
        "competitor_mentions": ["Any other lenders mentioned"]
    }},
    "compliance_notes": [
        "Any potential compliance items to review"
    ],
    "follow_up_recommendations": [
        "Recommended follow-up actions based on the meeting"
    ]
}}

IMPORTANT:
- Return ONLY valid JSON, no additional text or markdown
- If a field is not applicable, use null or empty array
- Be specific and actionable in action items
- Flag any potential compliance concerns"""

        return prompt

    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response, handling common issues."""

        # Strip markdown code blocks if present
        response_text = re.sub(r'```json\s*\n?', '', response_text)
        response_text = re.sub(r'```\s*\n?', '', response_text)
        response_text = response_text.strip()

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}...")

            # Return a minimal valid structure
            return {
                "summary": "Analysis parsing failed. Raw response saved.",
                "raw_response": response_text,
                "key_topics": [],
                "action_items": [],
                "decisions_made": [],
                "error": "Internal server error"
            }

    async def generate_meeting_summary_email(
        self,
        analysis: Dict[str, Any],
        meeting_context: Dict[str, Any],
        recipient_type: str = "internal"  # internal or borrower
    ) -> str:
        """
        Generate a formatted email summary of the meeting.

        Args:
            analysis: The analysis results
            meeting_context: Meeting context
            recipient_type: Who will receive this (internal team or borrower)

        Returns:
            Formatted email body
        """
        if not self.anthropic_client:
            return self._generate_basic_email(analysis, meeting_context)

        try:
            prompt = f"""Generate a professional {recipient_type} email summarizing this meeting.

Meeting: {meeting_context.get('title', 'Meeting')}
Date: {meeting_context.get('date', 'Today')}

Analysis:
{json.dumps(analysis, indent=2)}

Guidelines:
- For internal emails: Include all action items and detailed notes
- For borrower emails: Be warm, professional, highlight next steps clearly
- Keep it concise but comprehensive
- Include any important deadlines
- End with clear next steps

Return just the email body text (no subject line needed)."""

            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}]
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Failed to generate email: {e}")
            return self._generate_basic_email(analysis, meeting_context)

    def _generate_basic_email(
        self,
        analysis: Dict[str, Any],
        meeting_context: Dict[str, Any]
    ) -> str:
        """Generate a basic email without AI."""

        title = meeting_context.get('title', 'Meeting')
        summary = analysis.get('summary', 'Meeting completed.')
        action_items = analysis.get('action_items', [])

        email = f"""Hi,

Thank you for joining our meeting: {title}

Summary:
{summary}

"""
        if action_items:
            email += "Action Items:\n"
            for item in action_items:
                email += f"- {item.get('description', 'Task')}"
                if item.get('assignee') and item['assignee'] != 'Unassigned':
                    email += f" (Assigned to: {item['assignee']})"
                email += "\n"

        email += """
Please let me know if you have any questions.

Best regards"""

        return email

    async def extract_action_items_for_tasks(
        self,
        analysis: Dict[str, Any],
        meeting_room_id: str,
        created_by_id: int,
        organization_id: int
    ) -> List[Dict[str, Any]]:
        """
        Extract action items in a format ready for task creation.

        Returns:
            List of task-ready dictionaries
        """
        tasks = []

        for item in analysis.get('action_items', []):
            task = {
                "title": item.get('description', 'Follow-up from meeting'),
                "description": f"From meeting: {analysis.get('summary', '')[:200]}",
                "task_type": "meeting_followup",
                "priority": item.get('priority', 'medium'),
                "status": "pending",
                "source": "ai_meeting_analysis",
                "source_reference_id": meeting_room_id,
                "source_reference_type": "meeting_recording",
                "created_by_id": created_by_id,
                "organization_id": organization_id,
                "category": item.get('category', 'followup'),
                "assignee_hint": item.get('assignee', 'Unassigned'),
                "due_hint": item.get('due_hint')
            }
            tasks.append(task)

        return tasks


# Singleton instance
_ai_service: Optional[AIProcessingService] = None


def get_ai_processing_service() -> AIProcessingService:
    """Get or create the AI processing service singleton."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIProcessingService()
    return _ai_service
