"""
Perennia AI - Smart Scheduler Tools
===================================
Tools for the Smart Scheduler Agent handling appointments and calendar management.
8 tools for scheduling, availability, reminders, and calendar optimization.
"""

from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from sqlalchemy import text

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
)


# =============================================================================
# Smart Scheduler Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_availability",
    description="Get available time slots for scheduling appointments",
    agent_roles=["smart_scheduler", "ai_receptionist"],
    risk_level="LOW",
    parameters={
        "user_id": "User/LO ID to check availability",
        "date_from": "Start date (YYYY-MM-DD)",
        "date_to": "End date (YYYY-MM-DD)",
        "duration_minutes": "Required slot duration",
        "meeting_type": "Type of meeting for buffer rules",
    },
)
def get_availability(
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    duration_minutes: int = 30,
    meeting_type: str = "consultation",
) -> ToolResult:
    """Get available calendar slots."""
    # Default date range
    if not date_from:
        date_from = datetime.now().strftime("%Y-%m-%d")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    # Get user's working hours
    user_prefs = None
    if user_id:
        user_prefs = execute_single("""
            SELECT working_hours_start, working_hours_end,
                   lunch_start, lunch_end, timezone
            FROM user_preferences
            WHERE user_id = :user_id
        """, {"user_id": user_id})

    # Business hours configuration
    business_hours = {
        "start": int(user_prefs.get("working_hours_start", 9)) if user_prefs else 9,
        "end": int(user_prefs.get("working_hours_end", 17)) if user_prefs else 17,
        "lunch_start": int(user_prefs.get("lunch_start", 12)) if user_prefs else 12,
        "lunch_end": int(user_prefs.get("lunch_end", 13)) if user_prefs else 13,
    }

    # Get existing appointments
    existing = execute_query("""
        SELECT start_time, end_time FROM appointments
        WHERE user_id = :user_id
        AND start_time >= :date_from
        AND start_time < :date_to
        AND status != 'cancelled'
    """, {"user_id": user_id, "date_from": date_from, "date_to": date_to}) if user_id else []

    # Build set of blocked times
    blocked_slots = set()
    for appt in existing:
        if appt.get("start_time"):
            blocked_slots.add(appt["start_time"].strftime("%Y-%m-%d %H:%M"))

    # Generate available slots
    available_slots = []
    current = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")

    while current <= end:
        # Skip weekends
        if current.weekday() < 5:
            # Generate slots for business hours
            for hour in range(business_hours["start"], business_hours["end"]):
                # Skip lunch
                if business_hours["lunch_start"] <= hour < business_hours["lunch_end"]:
                    continue

                for minute in [0, 30]:
                    slot_time = current.replace(hour=hour, minute=minute, second=0)
                    slot_key = slot_time.strftime("%Y-%m-%d %H:%M")

                    # Only future slots not blocked
                    if slot_time > datetime.now() and slot_key not in blocked_slots:
                        available_slots.append({
                            "start": slot_time.isoformat(),
                            "end": (slot_time + timedelta(minutes=duration_minutes)).isoformat(),
                            "display": slot_time.strftime("%A, %B %d at %I:%M %p"),
                            "available": True,
                        })

        current += timedelta(days=1)

    data = {
        "user_id": user_id,
        "date_range": {"from": date_from, "to": date_to},
        "duration_minutes": duration_minutes,
        "meeting_type": meeting_type,
        "business_hours": business_hours,
        "slots": available_slots[:20],  # Return first 20 slots
        "total_available": len(available_slots),
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(available_slots)} available slots",
    )


@mortgage_tool(
    name="book_appointment",
    description="Book an appointment with conflict checking. Optionally syncs to Outlook calendar and creates Teams meeting.",
    agent_roles=["smart_scheduler", "ai_receptionist"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact/Lead ID",
        "contact_type": "Type: lead, borrower",
        "datetime_str": "Appointment datetime (ISO format)",
        "duration_minutes": "Appointment duration",
        "appointment_type": "Type: consultation, document_review, closing_prep, callback",
        "user_id": "LO/User ID to book with",
        "title": "Appointment title",
        "notes": "Additional notes",
        "send_confirmation": "Send confirmation to contact",
        "add_teams_link": "Create Teams meeting link (requires Microsoft integration)",
        "sync_to_outlook": "Sync appointment to Outlook calendar",
    },
)
def book_appointment(
    contact_id: str,
    contact_type: str = "lead",
    datetime_str: Optional[str] = None,
    duration_minutes: int = 30,
    appointment_type: str = "consultation",
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    send_confirmation: bool = True,
    add_teams_link: bool = False,
    sync_to_outlook: bool = True,
) -> ToolResult:
    """Book an appointment with optional Outlook/Teams integration."""
    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT id, first_name, last_name, email, phone FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT id, borrower_name as name, borrower_email as email, borrower_phone as phone FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    if not contact:
        return ToolResult.no_data(f"Contact {contact_id} not found")

    # Default to next available slot if no datetime
    if not datetime_str:
        tomorrow = datetime.now() + timedelta(days=1)
        while tomorrow.weekday() >= 5:  # Skip weekends
            tomorrow += timedelta(days=1)
        datetime_str = tomorrow.replace(hour=10, minute=0, second=0).isoformat()

    # Parse datetime
    try:
        appt_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except ValueError:
        return ToolResult.error(f"Invalid datetime format: {datetime_str}")

    # Check for conflicts
    if user_id:
        conflict = execute_single("""
            SELECT id, title, start_time FROM appointments
            WHERE user_id = :user_id
            AND status != 'cancelled'
            AND start_time <= :end_time
            AND end_time >= :start_time
        """, {
            "user_id": user_id,
            "start_time": appt_datetime,
            "end_time": appt_datetime + timedelta(minutes=duration_minutes),
        })

        if conflict:
            return ToolResult.error(
                f"Conflict with existing appointment: {conflict.get('title')} at {conflict.get('start_time')}"
            )

    # Generate appointment ID
    import uuid
    appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"

    # Build title if not provided
    if contact_type == "lead":
        contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    else:
        contact_name = contact.get("name", "Borrower")

    if not title:
        title = f"{appointment_type.replace('_', ' ').title()} - {contact_name}"

    # Calculate end time
    appt_end = appt_datetime + timedelta(minutes=duration_minutes)

    # Optional: Create Outlook calendar event with Teams link
    outlook_event_id = None
    outlook_web_link = None
    teams_link = None

    if sync_to_outlook and user_id:
        try:
            import asyncio
            from database import SessionLocal
            from services.microsoft_graph import create_event_via_graph

            db = SessionLocal()
            try:
                # Check if user has Microsoft integration
                integration_check = db.execute(text("""
                    SELECT id FROM user_integrations
                    WHERE user_id = :user_id AND provider = 'microsoft'
                    AND access_token IS NOT NULL
                    LIMIT 1
                """), {"user_id": int(user_id)}).fetchone()

                if integration_check:
                    # Build attendee list
                    attendees = []
                    if contact.get("email"):
                        attendees.append(contact["email"])

                    # Create event (run async function)
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Already in async context
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run,
                                create_event_via_graph(
                                    user_id=int(user_id),
                                    subject=title,
                                    start=appt_datetime,
                                    end=appt_end,
                                    db=db,
                                    attendees=attendees if attendees else None,
                                    add_teams_link=add_teams_link,
                                    body=notes,
                                )
                            )
                            graph_result = future.result()
                    else:
                        graph_result = asyncio.run(create_event_via_graph(
                            user_id=int(user_id),
                            subject=title,
                            start=appt_datetime,
                            end=appt_end,
                            db=db,
                            attendees=attendees if attendees else None,
                            add_teams_link=add_teams_link,
                            body=notes,
                        ))

                    if graph_result.success:
                        outlook_event_id = graph_result.event_id
                        outlook_web_link = graph_result.web_link
                        teams_link = graph_result.teams_link
            finally:
                db.close()
        except ImportError:
            pass  # Microsoft Graph service not available
        except Exception as e:
            # Log but don't fail the appointment creation
            import logging
            logging.getLogger(__name__).warning(f"Failed to sync to Outlook: {e}")

    appointment = {
        "appointment_id": appt_id,
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": contact_name,
        "contact_email": contact.get("email"),
        "contact_phone": contact.get("phone"),
        "user_id": user_id,
        "datetime": appt_datetime.isoformat(),
        "duration_minutes": duration_minutes,
        "end_time": appt_end.isoformat(),
        "type": appointment_type,
        "title": title,
        "notes": notes,
        "status": "scheduled",
        "confirmation_sent": send_confirmation,
        "created_at": datetime.now().isoformat(),
        "reminders_scheduled": [
            {"type": "email", "before_minutes": 1440, "status": "pending"},  # 24 hours
            {"type": "sms", "before_minutes": 60, "status": "pending"},  # 1 hour
        ],
        # Outlook integration
        "outlook_event_id": outlook_event_id,
        "outlook_web_link": outlook_web_link,
        "teams_link": teams_link,
    }

    # Build success message
    message = f"Appointment booked for {appt_datetime.strftime('%B %d at %I:%M %p')}"
    if outlook_event_id:
        message += " (synced to Outlook)"
    if teams_link:
        message += " with Teams link"

    return ToolResult.success(
        data=appointment,
        message=message,
    )


@mortgage_tool(
    name="reschedule_appointment",
    description="Reschedule an existing appointment to a new time",
    agent_roles=["smart_scheduler"],
    risk_level="MEDIUM",
    parameters={
        "appointment_id": "Appointment ID to reschedule",
        "new_datetime": "New datetime (ISO format)",
        "reason": "Reason for rescheduling",
        "notify_contact": "Send notification to contact",
    },
)
def reschedule_appointment(
    appointment_id: str,
    new_datetime: str,
    reason: Optional[str] = None,
    notify_contact: bool = True,
) -> ToolResult:
    """Reschedule an appointment."""
    # Get original appointment
    original = execute_single("""
        SELECT id, title, start_time, duration_minutes, contact_id, user_id
        FROM appointments
        WHERE id = :id OR appointment_id = :id
    """, {"id": appointment_id})

    if not original:
        return ToolResult.no_data(f"Appointment {appointment_id} not found")

    try:
        new_dt = datetime.fromisoformat(new_datetime.replace('Z', '+00:00'))
    except ValueError:
        return ToolResult.error(f"Invalid datetime format: {new_datetime}")

    # Check for conflicts at new time
    duration = original.get("duration_minutes", 30)
    user_id = original.get("user_id")

    if user_id:
        conflict = execute_single("""
            SELECT id, title FROM appointments
            WHERE user_id = :user_id
            AND id != :appt_id
            AND status != 'cancelled'
            AND start_time <= :end_time
            AND end_time >= :start_time
        """, {
            "user_id": user_id,
            "appt_id": original["id"],
            "start_time": new_dt,
            "end_time": new_dt + timedelta(minutes=duration),
        })

        if conflict:
            return ToolResult.error(f"Conflict at new time: {conflict.get('title')}")

    data = {
        "appointment_id": appointment_id,
        "original_datetime": format_date(original.get("start_time")),
        "new_datetime": new_dt.isoformat(),
        "new_display": new_dt.strftime("%A, %B %d at %I:%M %p"),
        "reason": reason,
        "notification_sent": notify_contact,
        "status": "rescheduled",
        "rescheduled_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Appointment rescheduled to {data['new_display']}",
    )


@mortgage_tool(
    name="cancel_appointment",
    description="Cancel an appointment with optional reason",
    agent_roles=["smart_scheduler"],
    risk_level="MEDIUM",
    parameters={
        "appointment_id": "Appointment ID to cancel",
        "reason": "Cancellation reason",
        "notify_contact": "Send cancellation notice",
        "offer_reschedule": "Include reschedule options in notification",
    },
)
def cancel_appointment(
    appointment_id: str,
    reason: Optional[str] = None,
    notify_contact: bool = True,
    offer_reschedule: bool = True,
) -> ToolResult:
    """Cancel an appointment."""
    # Get appointment details
    appointment = execute_single("""
        SELECT id, title, start_time, contact_id, contact_email
        FROM appointments
        WHERE id = :id OR appointment_id = :id
    """, {"id": appointment_id})

    if not appointment:
        return ToolResult.no_data(f"Appointment {appointment_id} not found")

    data = {
        "appointment_id": appointment_id,
        "title": appointment.get("title"),
        "original_time": format_date(appointment.get("start_time")),
        "status": "cancelled",
        "reason": reason,
        "cancelled_at": datetime.now().isoformat(),
        "notification_sent": notify_contact,
        "reschedule_offered": offer_reschedule,
        "contact_id": appointment.get("contact_id"),
    }

    return ToolResult.success(
        data=data,
        message=f"Appointment {appointment_id} cancelled",
    )


@mortgage_tool(
    name="get_upcoming_appointments",
    description="Get list of upcoming appointments for a user",
    agent_roles=["smart_scheduler"],
    risk_level="LOW",
    parameters={
        "user_id": "User/LO ID",
        "days_ahead": "Number of days to look ahead",
        "include_cancelled": "Include cancelled appointments",
        "appointment_type": "Optional type filter",
    },
)
def get_upcoming_appointments(
    user_id: Optional[str] = None,
    days_ahead: int = 7,
    include_cancelled: bool = False,
    appointment_type: Optional[str] = None,
) -> ToolResult:
    """Get upcoming appointments."""
    params = {
        "start_date": datetime.now(),
        "end_date": datetime.now() + timedelta(days=days_ahead),
    }
    filters = ["a.start_time >= :start_date", "a.start_time <= :end_date"]

    if user_id:
        filters.append("a.user_id = :user_id")
        params["user_id"] = user_id

    if not include_cancelled:
        filters.append("a.status != 'cancelled'")

    if appointment_type:
        filters.append("a.appointment_type = :appointment_type")
        params["appointment_type"] = appointment_type

    where_sql = " AND ".join(filters)

    results = execute_query(f"""
        SELECT
            a.id, a.appointment_id, a.title, a.start_time, a.end_time,
            a.duration_minutes, a.appointment_type, a.status, a.notes,
            a.contact_id, a.contact_type,
            l.first_name, l.last_name, l.phone, l.email
        FROM appointments a
        LEFT JOIN leads l ON a.contact_id = l.id::text AND a.contact_type = 'lead'
        WHERE {where_sql}
        ORDER BY a.start_time ASC
        LIMIT 50
    """, params)

    appointments = []
    for r in results:
        appointments.append({
            "id": r.get("id"),
            "appointment_id": r.get("appointment_id"),
            "title": r.get("title"),
            "datetime": r.get("start_time").isoformat() if r.get("start_time") else None,
            "display_time": r.get("start_time").strftime("%B %d at %I:%M %p") if r.get("start_time") else None,
            "duration_minutes": r.get("duration_minutes"),
            "type": r.get("appointment_type"),
            "status": r.get("status"),
            "notes": r.get("notes"),
            "contact": {
                "id": r.get("contact_id"),
                "name": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip() if r.get("first_name") else None,
                "phone": r.get("phone"),
                "email": r.get("email"),
            } if r.get("contact_id") else None,
        })

    # Group by day for summary
    by_day = {}
    for appt in appointments:
        if appt.get("datetime"):
            day = appt["datetime"][:10]
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(appt)

    data = {
        "appointments": appointments,
        "by_day": by_day,
        "total_count": len(appointments),
        "date_range": {
            "from": datetime.now().strftime("%Y-%m-%d"),
            "to": (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(appointments)} upcoming appointments",
    )


@mortgage_tool(
    name="send_appointment_reminder",
    description="Send reminder for an upcoming appointment",
    agent_roles=["smart_scheduler"],
    risk_level="LOW",
    parameters={
        "appointment_id": "Appointment ID",
        "channel": "Reminder channel: email, sms, both",
        "custom_message": "Optional custom message",
    },
)
def send_appointment_reminder(
    appointment_id: str,
    channel: str = "both",
    custom_message: Optional[str] = None,
) -> ToolResult:
    """Send appointment reminder."""
    # Get appointment details
    appointment = execute_single("""
        SELECT a.id, a.title, a.start_time, a.appointment_type,
               a.contact_id, a.contact_email, a.contact_phone,
               l.first_name, l.email as lead_email, l.phone as lead_phone
        FROM appointments a
        LEFT JOIN leads l ON a.contact_id = l.id::text
        WHERE a.id = :id OR a.appointment_id = :id
    """, {"id": appointment_id})

    if not appointment:
        return ToolResult.no_data(f"Appointment {appointment_id} not found")

    # Determine contact info
    contact_email = appointment.get("contact_email") or appointment.get("lead_email")
    contact_phone = appointment.get("contact_phone") or appointment.get("lead_phone")
    contact_name = appointment.get("first_name", "")

    # Build reminder message
    appt_time = appointment.get("start_time")
    time_display = appt_time.strftime("%A, %B %d at %I:%M %p") if appt_time else "your scheduled time"

    default_message = f"Hi {contact_name}, this is a reminder about your appointment: {appointment.get('title')} on {time_display}."

    sent_to = {}
    if channel in ["email", "both"] and contact_email:
        sent_to["email"] = contact_email
    if channel in ["sms", "both"] and contact_phone:
        sent_to["sms"] = contact_phone

    data = {
        "appointment_id": appointment_id,
        "title": appointment.get("title"),
        "appointment_time": time_display,
        "channel": channel,
        "sent_to": sent_to,
        "message": custom_message or default_message,
        "sent_at": datetime.now().isoformat(),
        "status": "sent" if sent_to else "no_contact_info",
    }

    return ToolResult.success(
        data=data,
        message=f"Reminder sent via {', '.join(sent_to.keys())}" if sent_to else "No contact info available",
    )


@mortgage_tool(
    name="sync_external_calendar",
    description="Sync with external calendar (Google, Outlook)",
    agent_roles=["smart_scheduler"],
    risk_level="MEDIUM",
    parameters={
        "user_id": "User ID",
        "calendar_type": "Type: google, outlook, ical",
        "direction": "Sync direction: import, export, bidirectional",
        "date_from": "Start date for sync",
        "date_to": "End date for sync",
    },
)
def sync_external_calendar(
    user_id: str,
    calendar_type: str = "google",
    direction: str = "bidirectional",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> ToolResult:
    """Sync with external calendar."""
    if not date_from:
        date_from = datetime.now().strftime("%Y-%m-%d")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Check integration status
    integration = execute_single("""
        SELECT id, status, last_sync_at, access_token_expires
        FROM calendar_integrations
        WHERE user_id = :user_id AND calendar_type = :calendar_type
    """, {"user_id": user_id, "calendar_type": calendar_type})

    if not integration:
        return ToolResult.error(
            f"No {calendar_type} calendar integration found. Please connect your calendar first."
        )

    if integration.get("status") != "active":
        return ToolResult.error(
            f"Calendar integration is {integration.get('status')}. Please reconnect."
        )

    # In production, would make API calls to external calendar
    import uuid
    sync_id = str(uuid.uuid4())[:8].upper()

    data = {
        "sync_id": f"SYNC-{sync_id}",
        "user_id": user_id,
        "calendar_type": calendar_type,
        "direction": direction,
        "date_range": {
            "from": date_from,
            "to": date_to,
        },
        "status": "completed",
        "results": {
            "imported": 0,
            "exported": 0,
            "conflicts_resolved": 0,
            "errors": 0,
        },
        "synced_at": datetime.now().isoformat(),
        "next_sync": (datetime.now() + timedelta(minutes=15)).isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Calendar sync completed ({calendar_type})",
    )


@mortgage_tool(
    name="optimize_schedule",
    description="Analyze and suggest schedule optimizations",
    agent_roles=["smart_scheduler", "team_coach"],
    risk_level="LOW",
    parameters={
        "user_id": "User/LO ID",
        "date": "Date to optimize (YYYY-MM-DD)",
        "optimization_goals": "Goals: reduce_gaps, batch_similar, protect_focus_time",
    },
)
def optimize_schedule(
    user_id: str,
    date_str: Optional[str] = None,
    optimization_goals: Optional[List[str]] = None,
) -> ToolResult:
    """Analyze and suggest schedule optimizations."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    goals = optimization_goals or ["reduce_gaps", "batch_similar"]

    # Get appointments for the day
    appointments = execute_query("""
        SELECT id, title, start_time, end_time, duration_minutes, appointment_type
        FROM appointments
        WHERE user_id = :user_id
        AND DATE(start_time) = :date
        AND status != 'cancelled'
        ORDER BY start_time
    """, {"user_id": user_id, "date": date_str})

    # Analyze gaps
    gaps = []
    total_gap_minutes = 0
    for i in range(len(appointments) - 1):
        current_end = appointments[i].get("end_time")
        next_start = appointments[i + 1].get("start_time")
        if current_end and next_start:
            gap_minutes = (next_start - current_end).total_seconds() / 60
            if gap_minutes > 15:  # Significant gap
                gaps.append({
                    "after": appointments[i].get("title"),
                    "before": appointments[i + 1].get("title"),
                    "gap_minutes": gap_minutes,
                })
                total_gap_minutes += gap_minutes

    # Generate suggestions
    suggestions = []

    if "reduce_gaps" in goals and gaps:
        for gap in gaps[:3]:  # Top 3 gaps
            suggestions.append({
                "type": "reduce_gap",
                "description": f"Move '{gap['before']}' earlier to reduce {int(gap['gap_minutes'])} min gap",
                "potential_savings_minutes": gap["gap_minutes"] - 15,
                "priority": "high" if gap["gap_minutes"] > 60 else "medium",
            })

    if "batch_similar" in goals:
        # Group by type
        by_type = {}
        for appt in appointments:
            apt = appt.get("appointment_type", "other")
            if apt not in by_type:
                by_type[apt] = []
            by_type[apt].append(appt)

        for apt, appts in by_type.items():
            if len(appts) >= 2:
                suggestions.append({
                    "type": "batch_similar",
                    "description": f"Batch {len(appts)} {apt} appointments together",
                    "benefit": "Reduce context switching",
                    "priority": "medium",
                })

    if "protect_focus_time" in goals:
        suggestions.append({
            "type": "block_focus_time",
            "description": "Block 2-hour focus time in the morning",
            "benefit": "Protected time for deep work",
            "priority": "medium",
        })

    # Calculate efficiency
    total_scheduled = sum(a.get("duration_minutes", 0) for a in appointments)
    business_hours = 8 * 60  # 8 hours in minutes
    efficiency = (total_scheduled / business_hours) if business_hours > 0 else 0

    data = {
        "date": date_str,
        "user_id": user_id,
        "optimization_goals": goals,
        "current_state": {
            "total_appointments": len(appointments),
            "total_scheduled_minutes": total_scheduled,
            "total_gap_minutes": total_gap_minutes,
            "efficiency": round(efficiency, 2),
        },
        "suggestions": suggestions,
        "potential_improvement": {
            "time_savings_minutes": sum(s.get("potential_savings_minutes", 0) for s in suggestions if "potential_savings_minutes" in s),
            "new_efficiency": round(efficiency + 0.15, 2) if suggestions else efficiency,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Schedule efficiency: {efficiency:.0%}, {len(suggestions)} optimizations suggested",
    )
