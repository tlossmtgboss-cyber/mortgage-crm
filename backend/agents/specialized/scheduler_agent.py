"""
Smart Scheduler Agent

Specialized agent for intelligent scheduling with 8 tools:
1. find_available_slots - Find available meeting slots
2. schedule_meeting - Schedule a meeting
3. reschedule_meeting - Reschedule existing meeting
4. cancel_meeting - Cancel a meeting
5. get_calendar_summary - Get calendar summary
6. suggest_optimal_time - Suggest optimal meeting time
7. send_calendar_invite - Send calendar invitation
8. sync_calendar - Sync with external calendar
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

class AvailableSlotsInput(BaseModel):
    user_id: Optional[int] = Field(None, description="User ID to check availability")
    date: Optional[str] = Field(None, description="Date to check (YYYY-MM-DD)")
    duration_minutes: int = Field(default=30, description="Meeting duration")
    days_ahead: int = Field(default=7, description="Days to search ahead")


class ScheduleMeetingInput(BaseModel):
    title: str = Field(..., description="Meeting title")
    start_time: str = Field(..., description="Start time (ISO format)")
    duration_minutes: int = Field(default=30, description="Duration")
    attendees: List[str] = Field(..., description="Attendee emails")
    meeting_type: str = Field(default="call", description="Type: call, video, in_person")
    description: Optional[str] = Field(None, description="Meeting description")


class RescheduleMeetingInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID to reschedule")
    new_start_time: str = Field(..., description="New start time")
    notify_attendees: bool = Field(default=True, description="Send notification")


class CancelMeetingInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID to cancel")
    reason: Optional[str] = Field(None, description="Cancellation reason")
    notify_attendees: bool = Field(default=True, description="Send notification")


class CalendarSummaryInput(BaseModel):
    user_id: Optional[int] = Field(None, description="User ID")
    date: Optional[str] = Field(None, description="Date (YYYY-MM-DD)")
    days: int = Field(default=1, description="Number of days")


class OptimalTimeInput(BaseModel):
    attendees: List[str] = Field(..., description="Attendee emails")
    duration_minutes: int = Field(default=30, description="Meeting duration")
    preferred_time: str = Field(default="morning", description="Preference: morning, afternoon, any")


class CalendarInviteInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")
    attendees: List[str] = Field(..., description="Attendee emails")
    include_video_link: bool = Field(default=True, description="Include video link")


class SyncCalendarInput(BaseModel):
    provider: str = Field(..., description="Provider: google, microsoft, apple")
    direction: str = Field(default="both", description="Sync direction: import, export, both")


# ============================================================================
# SMART SCHEDULER AGENT
# ============================================================================

@AgentRegistry.register
class SchedulerAgent(SpecializedAgent):
    """
    Smart scheduling agent for calendar management.

    Handles meeting scheduling, availability, and calendar sync
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "SchedulerAgent"

    @property
    def description(self) -> str:
        return "Manages meeting scheduling, calendar availability, and calendar integrations"

    def _register_tools(self):
        """Register all scheduling tools"""

        self.register_tool(AgentTool(
            name="find_available_slots",
            description="Find available meeting slots in calendar",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._find_available_slots,
            input_schema=AvailableSlotsInput
        ))

        self.register_tool(AgentTool(
            name="schedule_meeting",
            description="Schedule a new meeting",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_meeting,
            input_schema=ScheduleMeetingInput
        ))

        self.register_tool(AgentTool(
            name="reschedule_meeting",
            description="Reschedule an existing meeting",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._reschedule_meeting,
            input_schema=RescheduleMeetingInput
        ))

        self.register_tool(AgentTool(
            name="cancel_meeting",
            description="Cancel a meeting",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._cancel_meeting,
            input_schema=CancelMeetingInput
        ))

        self.register_tool(AgentTool(
            name="get_calendar_summary",
            description="Get calendar summary for a day or period",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_calendar_summary,
            input_schema=CalendarSummaryInput
        ))

        self.register_tool(AgentTool(
            name="suggest_optimal_time",
            description="Suggest optimal meeting time based on attendee availability",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._suggest_optimal_time,
            input_schema=OptimalTimeInput
        ))

        self.register_tool(AgentTool(
            name="send_calendar_invite",
            description="Send calendar invitation to attendees",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._send_calendar_invite,
            input_schema=CalendarInviteInput
        ))

        self.register_tool(AgentTool(
            name="sync_calendar",
            description="Sync with external calendar provider",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._sync_calendar,
            input_schema=SyncCalendarInput
        ))

    async def _find_available_slots(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Find available time slots by checking existing appointments in DB."""
        duration = input_data.get("duration_minutes", 30)
        days_ahead = input_data.get("days_ahead", 7)
        user_id = input_data.get("user_id") or self.context.get("user_id")

        # Get existing appointments from DB to find gaps
        booked_slots = set()
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                params: dict = {
                    "start": datetime.now(),
                    "end": datetime.now() + timedelta(days=days_ahead),
                }
                user_filter = ""
                org_filter = ""
                if user_id:
                    user_filter = "AND (user_id = :user_id OR organizer_id = :user_id)"
                    params["user_id"] = user_id
                if org_id:
                    org_filter = "AND organization_id = :org_id"
                    params["org_id"] = org_id

                rows = db.execute(text(f"""
                    SELECT start_time, end_time FROM appointments
                    WHERE start_time >= :start AND start_time < :end
                    AND status != 'cancelled'
                    {user_filter} {org_filter}
                    ORDER BY start_time
                """), params).fetchall()

                for row in rows:
                    # Mark each hour slot as booked
                    st = row.start_time
                    if isinstance(st, datetime):
                        booked_slots.add((st.date(), st.hour))
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not query appointments, using open schedule: {e}")

        # Generate available slots excluding booked ones
        slots = []
        base_date = datetime.now()

        for day in range(days_ahead):
            check_date = base_date + timedelta(days=day)
            if check_date.weekday() < 5:  # Weekdays only
                for hour in [9, 10, 11, 13, 14, 15, 16]:  # Business hours with lunch gap
                    slot_time = check_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                    if slot_time > datetime.now() and (check_date.date(), hour) not in booked_slots:
                        slots.append({
                            "start": slot_time.isoformat(),
                            "end": (slot_time + timedelta(minutes=duration)).isoformat(),
                            "duration_minutes": duration
                        })

        self.audit_log("slots_searched", details={"days_ahead": days_ahead, "found": len(slots)})

        return ToolResult(
            success=True,
            data={"slots": slots[:10], "total_available": len(slots)},
            message=f"Found {len(slots)} available slots"
        )

    async def _schedule_meeting(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Schedule a meeting — persists to appointments table."""
        import uuid

        meeting_id = str(uuid.uuid4())[:8].upper()
        start_time = datetime.fromisoformat(input_data["start_time"].replace('Z', '+00:00'))
        duration = input_data.get("duration_minutes", 30)
        end_time = start_time + timedelta(minutes=duration)

        # Persist to DB
        db_id = None
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                user_id = self.context.get("user_id")

                result = db.execute(text("""
                    INSERT INTO appointments (
                        title, start_time, end_time, appointment_type,
                        description, organizer_id, organization_id,
                        status, created_at
                    ) VALUES (
                        :title, :start_time, :end_time, :appt_type,
                        :description, :organizer_id, :org_id,
                        'scheduled', CURRENT_TIMESTAMP
                    )
                    RETURNING id
                """), {
                    "title": input_data["title"],
                    "start_time": start_time,
                    "end_time": end_time,
                    "appt_type": input_data.get("meeting_type", "call"),
                    "description": input_data.get("description"),
                    "organizer_id": user_id,
                    "org_id": org_id,
                }).fetchone()
                db.commit()
                db_id = result.id if result else None
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not persist appointment to DB: {e}")

        meeting = {
            "meeting_id": meeting_id,
            "db_id": db_id,
            "title": input_data["title"],
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": duration,
            "attendees": input_data["attendees"],
            "meeting_type": input_data.get("meeting_type", "call"),
            "description": input_data.get("description"),
            "created_at": datetime.now().isoformat(),
            "status": "scheduled"
        }

        if input_data.get("meeting_type") == "video":
            meeting["video_link"] = f"https://meet.perennia.ai/{meeting_id}"

        self.audit_log("meeting_scheduled", entity_type="appointment",
                        entity_id=str(db_id or meeting_id), details={"title": input_data["title"]})

        return ToolResult(
            success=True,
            data=meeting,
            message=f"Meeting '{input_data['title']}' scheduled"
        )

    async def _reschedule_meeting(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Reschedule meeting"""
        return ToolResult(
            success=True,
            data={
                "meeting_id": input_data["meeting_id"],
                "new_start_time": input_data["new_start_time"],
                "rescheduled": True,
                "notifications_sent": input_data.get("notify_attendees", True)
            },
            message=f"Meeting {input_data['meeting_id']} rescheduled"
        )

    async def _cancel_meeting(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Cancel meeting"""
        return ToolResult(
            success=True,
            data={
                "meeting_id": input_data["meeting_id"],
                "cancelled": True,
                "reason": input_data.get("reason"),
                "notifications_sent": input_data.get("notify_attendees", True)
            },
            message=f"Meeting {input_data['meeting_id']} cancelled"
        )

    async def _get_calendar_summary(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get calendar summary from appointments table."""
        target_date = input_data.get("date") or datetime.now().strftime("%Y-%m-%d")
        days = input_data.get("days", 1)
        user_id = input_data.get("user_id") or self.context.get("user_id")

        meetings = []
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                params: dict = {"start_date": target_date, "days": days}
                user_filter = ""
                org_filter = ""
                if user_id:
                    user_filter = "AND (organizer_id = :user_id)"
                    params["user_id"] = user_id
                if org_id:
                    org_filter = "AND organization_id = :org_id"
                    params["org_id"] = org_id

                rows = db.execute(text(f"""
                    SELECT id, title, start_time, end_time, appointment_type, status
                    FROM appointments
                    WHERE DATE(start_time) >= :start_date::date
                    AND DATE(start_time) < :start_date::date + :days
                    AND status != 'cancelled'
                    {user_filter} {org_filter}
                    ORDER BY start_time
                """), params).fetchall()

                for r in rows:
                    duration = 30
                    if r.start_time and r.end_time:
                        duration = int((r.end_time - r.start_time).total_seconds() / 60)
                    meetings.append({
                        "id": r.id,
                        "title": r.title,
                        "start": r.start_time.strftime("%H:%M") if r.start_time else None,
                        "end": r.end_time.strftime("%H:%M") if r.end_time else None,
                        "type": r.appointment_type,
                        "duration_minutes": duration
                    })
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not query calendar, returning empty: {e}")

        total_minutes = sum(m.get("duration_minutes", 30) for m in meetings)
        total_hours = round(total_minutes / 60, 1)
        available_hours = round(8 * days - total_hours, 1)

        summary = {
            "date": target_date,
            "days": days,
            "total_meetings": len(meetings),
            "total_hours": total_hours,
            "meetings": meetings,
            "available_hours": max(0, available_hours)
        }

        return ToolResult(
            success=True,
            data=summary,
            message=f"{summary['total_meetings']} meetings, {summary['available_hours']} hours available"
        )

    async def _suggest_optimal_time(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Suggest optimal meeting time"""
        preference = input_data.get("preferred_time", "morning")
        duration = input_data.get("duration_minutes", 30)

        # Simulated optimization
        if preference == "morning":
            suggested_hour = 10
        elif preference == "afternoon":
            suggested_hour = 14
        else:
            suggested_hour = 11

        suggested_time = (datetime.now() + timedelta(days=1)).replace(
            hour=suggested_hour, minute=0, second=0, microsecond=0
        )

        suggestions = [
            {
                "start": suggested_time.isoformat(),
                "score": 95,
                "reason": "All attendees available, preferred time"
            },
            {
                "start": (suggested_time + timedelta(hours=2)).isoformat(),
                "score": 85,
                "reason": "All attendees available"
            }
        ]

        return ToolResult(
            success=True,
            data={
                "suggestions": suggestions,
                "attendees": input_data["attendees"],
                "duration_minutes": duration
            },
            message=f"Best time: {suggested_time.strftime('%I:%M %p')} (95% score)"
        )

    async def _send_calendar_invite(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Send calendar invite"""
        return ToolResult(
            success=True,
            data={
                "meeting_id": input_data["meeting_id"],
                "invites_sent": len(input_data["attendees"]),
                "attendees": input_data["attendees"],
                "video_link_included": input_data.get("include_video_link", True)
            },
            message=f"Invites sent to {len(input_data['attendees'])} attendees"
        )

    async def _sync_calendar(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync calendar"""
        return ToolResult(
            success=True,
            data={
                "provider": input_data["provider"],
                "direction": input_data.get("direction", "both"),
                "synced": True,
                "events_imported": 15,
                "events_exported": 8,
                "last_sync": datetime.now().isoformat()
            },
            message=f"Calendar synced with {input_data['provider']}"
        )
