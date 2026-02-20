"""
Perennia AI - UVIP (Unified Video Intelligence Platform) Tools
==============================================================
Tools for video consultations, async video, and meeting analytics.
8 tools for video meetings, recordings, summaries, and insights.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import secrets

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    db_session,
    format_date,
)


# =============================================================================
# UVIP Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="schedule_video_meeting",
    description="Schedule video consultation with borrower or realtor",
    agent_roles=["uvip"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower, realtor",
        "meeting_type": "Type: consultation, document_review, closing_prep",
        "scheduled_time": "Meeting time (ISO)",
        "duration_minutes": "Duration in minutes",
        "attendees": "Additional attendee emails",
    },
)
def schedule_video_meeting(
    contact_id: str,
    contact_type: str = "lead",
    meeting_type: str = "consultation",
    scheduled_time: Optional[str] = None,
    duration_minutes: int = 30,
    attendees: Optional[List[str]] = None,
) -> ToolResult:
    """Schedule video meeting."""
    import uuid
    meeting_id = str(uuid.uuid4())[:8].upper()

    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, email FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as name, borrower_email as email FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    # Default to tomorrow 10 AM if not specified
    if not scheduled_time:
        tomorrow = datetime.now() + timedelta(days=1)
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=10, minute=0, second=0).isoformat()

    meeting_data = {
        "meeting_id": f"MTG-{meeting_id}",
        "meeting_link": f"https://meet.perennia.ai/{meeting_id}",
        "host_link": f"https://meet.perennia.ai/{meeting_id}?host=true",
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": f"{contact.get('first_name', '')} {contact.get('last_name', contact.get('name', ''))}".strip() if contact else "Unknown",
        "contact_email": contact.get("email") if contact else None,
        "meeting_type": meeting_type,
        "scheduled_time": scheduled_time,
        "duration_minutes": duration_minutes,
        "attendees": attendees or [],
        "status": "scheduled",
        "created_at": datetime.now().isoformat(),
    }

    # Persist to calendar_events table
    try:
        from sqlalchemy import text as sa_text
        with db_session() as session:
            session.execute(sa_text("""
                INSERT INTO calendar_events (
                    title, event_type, start_time, end_time,
                    contact_id, description, meeting_link, status, created_at
                ) VALUES (
                    :title, 'video_meeting', :start_time,
                    :start_time::timestamp + :duration * interval '1 minute',
                    :contact_id, :description, :meeting_link, 'scheduled', CURRENT_TIMESTAMP
                )
            """), {
                "title": f"Video {meeting_type} with {meeting_data['contact_name']}",
                "start_time": scheduled_time,
                "duration": duration_minutes,
                "contact_id": contact_id,
                "description": f"{meeting_type} meeting",
                "meeting_link": meeting_data["meeting_link"],
            })
        meeting_data["persisted"] = True
    except Exception:
        meeting_data["persisted"] = False

    return ToolResult.success(
        data=meeting_data,
        message=f"Meeting scheduled for {scheduled_time}",
    )


@mortgage_tool(
    name="get_meeting_recordings",
    description="Get recordings for a meeting or contact",
    agent_roles=["uvip"],
    risk_level="LOW",
    parameters={
        "meeting_id": "Optional meeting ID",
        "contact_id": "Optional contact ID",
        "limit": "Max results",
    },
)
def get_meeting_recordings(
    meeting_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = 10,
) -> ToolResult:
    """Get meeting recordings."""
    params = {"limit": limit}
    filters = ["1=1"]

    if meeting_id:
        filters.append("meeting_id = :meeting_id")
        params["meeting_id"] = meeting_id
    if contact_id:
        filters.append("contact_id = :contact_id")
        params["contact_id"] = contact_id

    recordings = execute_query(f"""
        SELECT
            id, meeting_id, contact_id, recording_url,
            duration_seconds, recorded_at, transcription_status
        FROM meeting_recordings
        WHERE {" AND ".join(filters)}
        ORDER BY recorded_at DESC
        LIMIT :limit
    """, params)

    if not recordings:
        recordings = []

    recording_list = []
    for rec in recordings:
        recording_list.append({
            "id": rec.get("id"),
            "meeting_id": rec.get("meeting_id"),
            "recording_url": rec.get("recording_url"),
            "duration_minutes": round((rec.get("duration_seconds", 0) or 0) / 60, 1),
            "recorded_at": format_date(rec.get("recorded_at")),
            "transcription_status": rec.get("transcription_status", "pending"),
        })

    return ToolResult.success(
        data={
            "recordings": recording_list,
            "count": len(recording_list),
        },
        message=f"Found {len(recording_list)} recordings",
    )


@mortgage_tool(
    name="analyze_meeting",
    description="Analyze meeting recording for sentiment and insights",
    agent_roles=["uvip"],
    risk_level="LOW",
    parameters={
        "meeting_id": "Meeting ID to analyze",
        "analysis_type": "Type: sentiment, engagement, topics, all",
    },
)
def analyze_meeting(
    meeting_id: str,
    analysis_type: str = "all",
) -> ToolResult:
    """Analyze meeting by querying associated call logs and calendar event data."""
    # Query calendar event for meeting context
    meeting = execute_single("""
        SELECT id, title, event_type, start_time, end_time,
               contact_id, description, status
        FROM calendar_events
        WHERE id::text = :meeting_id OR title LIKE '%' || :meeting_id || '%'
        ORDER BY created_at DESC LIMIT 1
    """, {"meeting_id": meeting_id})

    # Query associated call logs for sentiment/engagement data
    call_data = execute_query("""
        SELECT id, duration, disposition, ai_note_summary, sentiment,
               talk_time_seconds, hold_time_seconds
        FROM call_logs
        WHERE notes LIKE '%' || :meeting_id || '%'
           OR id::text = :meeting_id
        ORDER BY created_at DESC LIMIT 5
    """, {"meeting_id": meeting_id})

    analysis = {
        "meeting_id": meeting_id,
        "analysis_type": analysis_type,
        "status": "analyzed" if (meeting or call_data) else "pending",
        "meeting_found": meeting is not None,
        "call_records_found": len(call_data) if call_data else 0,
    }

    if meeting:
        analysis["meeting_context"] = {
            "title": meeting.get("title"),
            "type": meeting.get("event_type"),
            "status": meeting.get("status"),
            "scheduled": meeting.get("start_time").isoformat() if meeting.get("start_time") else None,
        }

    if analysis_type in ["sentiment", "all"]:
        # Use call log sentiment if available
        sentiments = [c.get("sentiment") for c in (call_data or []) if c.get("sentiment")]
        ai_summaries = [c.get("ai_note_summary") for c in (call_data or []) if c.get("ai_note_summary")]
        analysis["sentiment"] = {
            "overall": sentiments[0] if sentiments else "neutral",
            "borrower_sentiment": sentiments[0] if sentiments else "neutral",
            "ai_summaries": ai_summaries[:3],
            "sentiment_progression": sentiments,
            "key_moments": [],
        }

    if analysis_type in ["engagement", "all"]:
        total_talk = sum(float(c.get("talk_time_seconds", 0) or 0) for c in (call_data or []))
        total_duration = sum(float(c.get("duration", 0) or 0) for c in (call_data or []))
        analysis["engagement"] = {
            "score": round((total_talk / total_duration) * 100, 1) if total_duration > 0 else 0,
            "total_talk_time_seconds": total_talk,
            "total_duration_seconds": total_duration,
            "questions_asked": 0,
            "active_participation": round((total_talk / total_duration) * 100, 1) if total_duration > 0 else 0,
            "attention_drops": [],
        }

    if analysis_type in ["topics", "all"]:
        analysis["topics"] = {
            "discussed": [],
            "time_per_topic": {},
            "questions_by_topic": {},
        }

    analysis["analyzed_at"] = datetime.now().isoformat()

    return ToolResult.success(
        data=analysis,
        message=f"Meeting analysis: {analysis_type}" + (" — data from call logs" if call_data else " — pending transcript"),
    )


@mortgage_tool(
    name="send_async_video",
    description="Send asynchronous video message to contact",
    agent_roles=["uvip"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "video_type": "Type: intro, rate_update, status_update, thank_you",
        "template_id": "Optional template ID",
        "custom_script": "Optional custom script",
    },
)
def send_async_video(
    contact_id: str,
    contact_type: str = "lead",
    video_type: str = "intro",
    template_id: Optional[str] = None,
    custom_script: Optional[str] = None,
) -> ToolResult:
    """Send async video message."""
    import uuid
    video_id = str(uuid.uuid4())[:8].upper()

    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, email FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as first_name, borrower_email as email FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    # Video templates
    templates = {
        "intro": "Hi {name}! I'm excited to help you with your home financing journey...",
        "rate_update": "Hi {name}! Great news - I have a rate update for you...",
        "status_update": "Hi {name}! I wanted to give you a quick update on your loan...",
        "thank_you": "Hi {name}! I just wanted to thank you for choosing us...",
    }

    script = custom_script or templates.get(video_type, templates["intro"])
    if contact:
        script = script.format(name=contact.get("first_name", "there"))

    video_data = {
        "video_id": f"VID-{video_id}",
        "contact_id": contact_id,
        "contact_type": contact_type,
        "recipient_email": contact.get("email") if contact else None,
        "video_type": video_type,
        "template_id": template_id,
        "script": script,
        "view_link": f"https://video.perennia.ai/v/{video_id}",
        "status": "pending_record",
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=video_data,
        message=f"Async video prepared for {contact.get('first_name', 'contact') if contact else 'contact'}",
    )


@mortgage_tool(
    name="get_video_analytics",
    description="Get video engagement analytics",
    agent_roles=["uvip", "team_coach"],
    risk_level="LOW",
    parameters={
        "lo_id": "Optional LO ID",
        "period": "Period: week, month, quarter",
        "video_type": "Optional video type filter",
    },
)
def get_video_analytics(
    lo_id: Optional[str] = None,
    period: str = "month",
    video_type: Optional[str] = None,
) -> ToolResult:
    """Get video analytics aggregated from CalendarEvent meeting data."""
    # Calculate date range
    today = datetime.now().date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "quarter":
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=30)

    # Query real meeting data from calendar_events
    params = {"start_date": start_date.isoformat(), "end_date": today.isoformat()}
    lo_filter = ""
    if lo_id:
        lo_filter = "AND ce.user_id = :lo_id"
        params["lo_id"] = lo_id

    meeting_stats = execute_single(f"""
        SELECT
            COUNT(*) as total_meetings,
            COUNT(CASE WHEN ce.status = 'completed' THEN 1 END) as completed_meetings,
            COUNT(CASE WHEN ce.status = 'no_show' THEN 1 END) as no_shows,
            COUNT(CASE WHEN ce.status = 'cancelled' THEN 1 END) as cancelled,
            COALESCE(AVG(EXTRACT(EPOCH FROM (ce.end_time - ce.start_time)) / 60), 0) as avg_duration_min
        FROM calendar_events ce
        WHERE ce.event_type IN ('video_meeting', 'meeting', 'consultation')
          AND ce.start_time >= :start_date::date
          AND ce.start_time <= :end_date::date + interval '1 day'
          {lo_filter}
    """, params)

    total = meeting_stats.get("total_meetings", 0) if meeting_stats else 0
    completed = meeting_stats.get("completed_meetings", 0) if meeting_stats else 0
    no_shows = meeting_stats.get("no_shows", 0) if meeting_stats else 0
    avg_duration = float(meeting_stats.get("avg_duration_min", 0) or 0) if meeting_stats else 0

    analytics = {
        "period": period,
        "date_range": {
            "start": start_date.isoformat(),
            "end": today.isoformat(),
        },
        "summary": {
            "total_videos_sent": 0,
            "total_views": 0,
            "view_rate": 0,
            "avg_watch_time_seconds": 0,
            "total_meetings": total,
            "meeting_duration_minutes": round(avg_duration, 1),
        },
        "by_type": {
            "async_videos": {
                "sent": 0,
                "viewed": 0,
                "avg_completion": 0,
            },
            "live_meetings": {
                "scheduled": total,
                "completed": completed,
                "no_show_rate": round((no_shows / total) * 100, 1) if total > 0 else 0,
            },
        },
        "top_performing": [],
        "lo_id": lo_id,
        "source": "database",
    }

    return ToolResult.success(
        data=analytics,
        message=f"Video analytics for {period}: {total} meetings, {completed} completed",
    )


@mortgage_tool(
    name="extract_meeting_action_items",
    description="Extract action items from meeting recording/transcript",
    agent_roles=["uvip"],
    risk_level="LOW",
    parameters={
        "meeting_id": "Meeting ID",
        "create_tasks": "Auto-create tasks from action items",
    },
)
def extract_meeting_action_items(
    meeting_id: str,
    create_tasks: bool = False,
) -> ToolResult:
    """Extract action items from meeting."""
    # In production, would use NLP on transcript
    action_items = {
        "meeting_id": meeting_id,
        "extracted_at": datetime.now().isoformat(),
        "action_items": [],
        "tasks_created": [],
        "status": "pending_transcript",
    }

    # Sample structure for when transcript is available
    action_items["sample_structure"] = {
        "action_item": {
            "description": "Action item description",
            "assignee": "Person responsible",
            "due_date": "Suggested due date",
            "priority": "high/medium/low",
            "context": "Related discussion excerpt",
        }
    }

    if create_tasks:
        action_items["tasks_will_be_created"] = True
        action_items["task_creation_status"] = "pending_extraction"

    return ToolResult.success(
        data=action_items,
        message="Action item extraction pending transcript",
    )


@mortgage_tool(
    name="generate_meeting_summary",
    description="Generate AI summary of meeting recording",
    agent_roles=["uvip"],
    risk_level="LOW",
    parameters={
        "meeting_id": "Meeting ID",
        "summary_type": "Type: brief, detailed, executive",
        "include_transcript": "Include full transcript",
    },
)
def generate_meeting_summary(
    meeting_id: str,
    summary_type: str = "brief",
    include_transcript: bool = False,
) -> ToolResult:
    """Generate meeting summary."""
    summary = {
        "meeting_id": meeting_id,
        "summary_type": summary_type,
        "generated_at": datetime.now().isoformat(),
        "status": "pending_transcript",
    }

    if summary_type == "brief":
        summary["summary_template"] = {
            "overview": "2-3 sentence overview",
            "key_decisions": [],
            "next_steps": [],
        }
    elif summary_type == "detailed":
        summary["summary_template"] = {
            "overview": "Comprehensive overview",
            "discussion_points": [],
            "key_decisions": [],
            "action_items": [],
            "follow_up_required": [],
            "timeline": [],
        }
    elif summary_type == "executive":
        summary["summary_template"] = {
            "headline": "One-line summary",
            "key_outcomes": [],
            "risks_identified": [],
            "recommendations": [],
        }

    if include_transcript:
        summary["transcript"] = {
            "status": "pending",
            "text": None,
        }

    return ToolResult.success(
        data=summary,
        message=f"Meeting summary ({summary_type}) pending",
    )


@mortgage_tool(
    name="get_participant_insights",
    description="Get insights about meeting participants and engagement",
    agent_roles=["uvip"],
    risk_level="LOW",
    parameters={
        "meeting_id": "Meeting ID",
        "participant_email": "Optional specific participant",
    },
)
def get_participant_insights(
    meeting_id: str,
    participant_email: Optional[str] = None,
) -> ToolResult:
    """Get participant insights."""
    insights = {
        "meeting_id": meeting_id,
        "analyzed_at": datetime.now().isoformat(),
        "participants": [],
        "status": "pending_analysis",
    }

    # Structure for participant insights
    insights["insight_template"] = {
        "email": "participant@example.com",
        "name": "Participant Name",
        "join_time": "When they joined",
        "leave_time": "When they left",
        "duration_minutes": 0,
        "engagement": {
            "attention_score": 0,
            "questions_asked": 0,
            "speaking_time_seconds": 0,
            "camera_on_percentage": 0,
        },
        "sentiment": "positive/neutral/negative",
        "key_interests": [],
        "concerns_raised": [],
    }

    if participant_email:
        insights["filtered_for"] = participant_email

    return ToolResult.success(
        data=insights,
        message="Participant insights pending analysis",
    )
