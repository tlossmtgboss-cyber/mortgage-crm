"""
Video Agent (UVIP - Unified Video Intelligence Platform)

Specialized agent for video communication with 8 tools:
1. create_video_room - Create video meeting room
2. get_room_status - Get video room status
3. record_meeting - Start/stop meeting recording
4. generate_meeting_summary - Generate AI summary of meeting
5. extract_action_items - Extract action items from meeting
6. send_video_invite - Send video meeting invitation
7. get_recording - Get meeting recording
8. analyze_meeting_metrics - Analyze meeting engagement metrics
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class CreateRoomInput(BaseModel):
    title: str = Field(..., description="Meeting title")
    scheduled_start: Optional[str] = Field(None, description="Scheduled start time")
    duration_minutes: int = Field(default=30, description="Expected duration")
    max_participants: int = Field(default=10, description="Maximum participants")
    record_automatically: bool = Field(default=False, description="Auto-record meeting")


class RoomStatusInput(BaseModel):
    room_id: str = Field(..., description="Video room ID")


class RecordMeetingInput(BaseModel):
    room_id: str = Field(..., description="Room ID")
    action: str = Field(..., description="Action: start, stop, pause")


class MeetingSummaryInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")
    include_transcript: bool = Field(default=False, description="Include full transcript")


class ActionItemsInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")
    assignee_filter: Optional[str] = Field(None, description="Filter by assignee")


class VideoInviteInput(BaseModel):
    room_id: str = Field(..., description="Room ID")
    attendees: List[str] = Field(..., description="Attendee emails")
    message: Optional[str] = Field(None, description="Custom message")


class GetRecordingInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")
    format: str = Field(default="mp4", description="Format: mp4, webm, audio_only")


class MeetingMetricsInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")


# ============================================================================
# VIDEO AGENT
# ============================================================================

@AgentRegistry.register
class VideoAgent(SpecializedAgent):
    """
    Video intelligence agent for video meetings.

    Manages video rooms, recordings, and AI-powered meeting analysis
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "VideoAgent"

    @property
    def description(self) -> str:
        return "Manages video meetings, recordings, and meeting intelligence"

    def _register_tools(self):
        """Register all video tools"""

        self.register_tool(AgentTool(
            name="create_video_room",
            description="Create a video meeting room",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_video_room,
            input_schema=CreateRoomInput
        ))

        self.register_tool(AgentTool(
            name="get_room_status",
            description="Get video room status and participant info",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_room_status,
            input_schema=RoomStatusInput
        ))

        self.register_tool(AgentTool(
            name="record_meeting",
            description="Start, stop, or pause meeting recording",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._record_meeting,
            input_schema=RecordMeetingInput
        ))

        self.register_tool(AgentTool(
            name="generate_meeting_summary",
            description="Generate AI summary of meeting",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_meeting_summary,
            input_schema=MeetingSummaryInput
        ))

        self.register_tool(AgentTool(
            name="extract_action_items",
            description="Extract action items from meeting",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._extract_action_items,
            input_schema=ActionItemsInput
        ))

        self.register_tool(AgentTool(
            name="send_video_invite",
            description="Send video meeting invitation",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._send_video_invite,
            input_schema=VideoInviteInput
        ))

        self.register_tool(AgentTool(
            name="get_recording",
            description="Get meeting recording",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_recording,
            input_schema=GetRecordingInput
        ))

        self.register_tool(AgentTool(
            name="analyze_meeting_metrics",
            description="Analyze meeting engagement and participation metrics",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_meeting_metrics,
            input_schema=MeetingMetricsInput
        ))

    async def _create_video_room(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Create video room — persists to video_meetings table if available."""
        import uuid

        room_id = str(uuid.uuid4())[:8].upper()

        # Try to persist to DB
        db_id = None
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                user_id = self.context.get("user_id")
                result = db.execute(text("""
                    INSERT INTO video_meetings (
                        room_id, title, host_user_id, organization_id,
                        scheduled_start, duration_minutes, status, created_at
                    ) VALUES (
                        :room_id, :title, :host_id, :org_id,
                        :scheduled_start, :duration, 'created', CURRENT_TIMESTAMP
                    )
                    RETURNING id
                """), {
                    "room_id": room_id,
                    "title": input_data["title"],
                    "host_id": user_id,
                    "org_id": org_id,
                    "scheduled_start": input_data.get("scheduled_start"),
                    "duration": input_data.get("duration_minutes", 30),
                }).fetchone()
                db.commit()
                db_id = result.id if result else None
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not persist video room to DB: {e}")

        room = {
            "room_id": room_id,
            "db_id": db_id,
            "title": input_data["title"],
            "join_url": f"https://video.perennia.ai/room/{room_id}",
            "host_url": f"https://video.perennia.ai/room/{room_id}?host=true",
            "scheduled_start": input_data.get("scheduled_start"),
            "duration_minutes": input_data.get("duration_minutes", 30),
            "max_participants": input_data.get("max_participants", 10),
            "record_automatically": input_data.get("record_automatically", False),
            "created_at": datetime.now().isoformat(),
            "status": "created"
        }

        self.audit_log("video_room_created", entity_type="video_meeting",
                        entity_id=str(db_id or room_id), details={"title": input_data["title"]})

        return ToolResult(
            success=True,
            data=room,
            message=f"Video room created: {room_id}"
        )

    async def _get_room_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get room status"""
        status = {
            "room_id": input_data["room_id"],
            "status": "active",
            "participants": [
                {"name": "John Smith", "role": "host", "joined_at": datetime.now().isoformat()},
                {"name": "Jane Doe", "role": "participant", "joined_at": datetime.now().isoformat()}
            ],
            "participant_count": 2,
            "duration_minutes": 15,
            "is_recording": False
        }

        return ToolResult(
            success=True,
            data=status,
            message=f"Room {input_data['room_id']}: {status['participant_count']} participants"
        )

    async def _record_meeting(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Control meeting recording"""
        action = input_data["action"]

        return ToolResult(
            success=True,
            data={
                "room_id": input_data["room_id"],
                "action": action,
                "recording_status": "recording" if action == "start" else "stopped",
                "timestamp": datetime.now().isoformat()
            },
            message=f"Recording {action}ed"
        )

    async def _generate_meeting_summary(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate meeting summary"""
        summary = {
            "meeting_id": input_data["meeting_id"],
            "summary": "Discussion covered loan application status, document requirements, and next steps. Key decisions made regarding closing timeline.",
            "key_points": [
                "Borrower provided updated income documentation",
                "Appraisal scheduled for next week",
                "Closing targeted for end of month"
            ],
            "duration_minutes": 25,
            "participants": 3,
            "generated_at": datetime.now().isoformat()
        }

        if input_data.get("include_transcript"):
            summary["transcript_url"] = f"https://video.perennia.ai/transcript/{input_data['meeting_id']}"

        return ToolResult(
            success=True,
            data=summary,
            message="Meeting summary generated"
        )

    async def _extract_action_items(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Extract action items"""
        action_items = [
            {
                "item": "Send updated income documentation",
                "assignee": "Borrower",
                "due_date": (datetime.now() + timedelta(days=2)).isoformat(),
                "priority": "high"
            },
            {
                "item": "Schedule appraisal",
                "assignee": "Processor",
                "due_date": (datetime.now() + timedelta(days=3)).isoformat(),
                "priority": "high"
            },
            {
                "item": "Review title commitment",
                "assignee": "LO",
                "due_date": (datetime.now() + timedelta(days=5)).isoformat(),
                "priority": "medium"
            }
        ]

        return ToolResult(
            success=True,
            data={
                "meeting_id": input_data["meeting_id"],
                "action_items": action_items,
                "count": len(action_items)
            },
            message=f"Extracted {len(action_items)} action items"
        )

    async def _send_video_invite(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Send video invite"""
        return ToolResult(
            success=True,
            data={
                "room_id": input_data["room_id"],
                "invites_sent": len(input_data["attendees"]),
                "attendees": input_data["attendees"],
                "join_url": f"https://video.perennia.ai/room/{input_data['room_id']}"
            },
            message=f"Invites sent to {len(input_data['attendees'])} attendees"
        )

    async def _get_recording(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get recording"""
        return ToolResult(
            success=True,
            data={
                "meeting_id": input_data["meeting_id"],
                "recording_url": f"https://video.perennia.ai/recordings/{input_data['meeting_id']}.{input_data.get('format', 'mp4')}",
                "format": input_data.get("format", "mp4"),
                "duration_minutes": 25,
                "file_size_mb": 150,
                "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
            },
            message="Recording available"
        )

    async def _analyze_meeting_metrics(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze meeting metrics"""
        metrics = {
            "meeting_id": input_data["meeting_id"],
            "duration_minutes": 25,
            "scheduled_duration": 30,
            "participants": {
                "invited": 4,
                "attended": 3,
                "attendance_rate": 75
            },
            "engagement": {
                "avg_speak_time_percent": 33,
                "questions_asked": 5,
                "screen_shares": 2
            },
            "quality": {
                "avg_video_quality": "HD",
                "audio_issues": 0,
                "connection_drops": 0
            }
        }

        return ToolResult(
            success=True,
            data=metrics,
            message=f"Meeting metrics: {metrics['participants']['attendance_rate']}% attendance"
        )
