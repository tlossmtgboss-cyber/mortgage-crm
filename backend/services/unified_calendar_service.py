"""
Unified Calendar Service

Fetches and merges events from 3 calendar sources:
1. CalendarEvent - User calendar events (/api/v1/calendar/events)
2. ScheduledAppointment - Scheduled appointments (/api/v1/scheduler/appointments)
3. CRMCalendarEvent - CRM events synced with Salesforce (/api/calendar/events)

Handles partial failures gracefully - if one source fails, others still return.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class UnifiedCalendarService:
    """Service for fetching and merging calendar events from multiple sources."""

    def __init__(self, db: Session, user_id: int, organization_id: int):
        self.db = db
        self.user_id = user_id
        if not organization_id:
            raise ValueError("organization_id is required for tenant isolation")
        self.organization_id = organization_id

    def get_unified_events(
        self,
        start_date: datetime,
        end_date: datetime,
        include_cancelled: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch events from all sources and return merged, sorted results.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            include_cancelled: Whether to include cancelled events

        Returns:
            Dict with events, total_count, warnings, and sources_queried
        """
        events = []
        warnings = []
        sources_queried = []

        # Fetch from each source with individual error handling
        calendar_events, calendar_warning = self._fetch_calendar_events(
            start_date, end_date, include_cancelled
        )
        if calendar_warning:
            warnings.append(calendar_warning)
        else:
            sources_queried.append("calendar")
        events.extend(calendar_events)

        appointment_events, appointment_warning = self._fetch_appointments(
            start_date, end_date, include_cancelled
        )
        if appointment_warning:
            warnings.append(appointment_warning)
        else:
            sources_queried.append("scheduler")
        events.extend(appointment_events)

        crm_events, crm_warning = self._fetch_crm_events(
            start_date, end_date, include_cancelled
        )
        if crm_warning:
            warnings.append(crm_warning)
        else:
            sources_queried.append("crm")
        events.extend(crm_events)

        # Sort by start_time
        events.sort(key=lambda e: e.get("start_time") or "")

        # RT3: Detect scheduling conflicts
        conflicts = self._detect_conflicts(events)

        return {
            "events": events,
            "total_count": len(events),
            "warnings": warnings,
            "sources_queried": sources_queried,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "has_hard_conflicts": any(c["type"] == "hard" for c in conflicts),
        }

    def _fetch_calendar_events(
        self, start_date: datetime, end_date: datetime, include_cancelled: bool
    ) -> tuple[List[Dict], Optional[str]]:
        """Fetch events from CalendarEvent table."""
        try:
            # Import here to avoid circular imports
            import main
            CalendarEvent = main.CalendarEvent

            query = self.db.query(CalendarEvent).filter(
                CalendarEvent.user_id == self.user_id,
                CalendarEvent.start_time >= start_date,
                CalendarEvent.start_time <= end_date,
            )

            query = query.filter(CalendarEvent.organization_id == self.organization_id)

            if not include_cancelled:
                query = query.filter(CalendarEvent.status != "cancelled")

            events = query.order_by(CalendarEvent.start_time).all()

            return [self._transform_calendar_event(e) for e in events], None

        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e}", exc_info=True)
            return [], f"calendar: {str(e)}"

    def _fetch_appointments(
        self, start_date: datetime, end_date: datetime, include_cancelled: bool
    ) -> tuple[List[Dict], Optional[str]]:
        """Fetch events from ScheduledAppointment table with tenant isolation."""
        try:
            # Import model only (service is deprecated but model defines the table)
            from services.smart_scheduler_service import ScheduledAppointment

            query = self.db.query(ScheduledAppointment).filter(
                ScheduledAppointment.loan_officer_id == self.user_id,
                ScheduledAppointment.start_time >= start_date,
                ScheduledAppointment.start_time <= end_date,
            )

            query = query.filter(
                ScheduledAppointment.organization_id == self.organization_id
            )

            if not include_cancelled:
                query = query.filter(ScheduledAppointment.status != "CANCELLED")

            appointments = query.order_by(ScheduledAppointment.start_time).all()

            return [self._transform_appointment(a) for a in appointments], None

        except Exception as e:
            logger.error(f"Failed to fetch appointments: {e}", exc_info=True)
            return [], f"scheduler: {str(e)}"

    def _fetch_crm_events(
        self, start_date: datetime, end_date: datetime, include_cancelled: bool
    ) -> tuple[List[Dict], Optional[str]]:
        """Fetch events from CRMCalendarEvent table."""
        try:
            from models.calendar_sync_models import CRMCalendarEvent

            query = self.db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.owner_user_id == self.user_id,
                CRMCalendarEvent.start_at >= start_date,
                CRMCalendarEvent.start_at <= end_date,
            )

            query = query.filter(CRMCalendarEvent.organization_id == self.organization_id)

            if not include_cancelled:
                query = query.filter(CRMCalendarEvent.status != "canceled")

            events = query.order_by(CRMCalendarEvent.start_at).all()

            return [self._transform_crm_event(e) for e in events], None

        except Exception as e:
            logger.error(f"Failed to fetch CRM events: {e}", exc_info=True)
            return [], f"crm: {str(e)}"

    def _transform_calendar_event(self, event) -> Dict[str, Any]:
        """
        Transform CalendarEvent to unified format.
        Matches frontend logic: direct mapping with 'event-{id}' prefix.
        """
        return {
            "id": f"event-{event.id}",
            "title": event.title or "",
            "description": event.description or "",
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "end_time": event.end_time.isoformat() if event.end_time else None,
            "event_type": event.event_type or "meeting",
            "location": event.location or "",
            "source": "calendar",
            "related_lead_id": event.lead_id,
            "related_loan_id": event.loan_id,
            "attendee_name": None,
            "status": event.status or "scheduled",
            "is_appointment": False,
            "is_crm_event": False,
            "all_day": event.all_day or False,
            "attendees": event.attendees or [],
        }

    def _transform_appointment(self, appt) -> Dict[str, Any]:
        """
        Transform ScheduledAppointment to unified format.
        Matches frontend appointmentToEvent() logic.
        """
        # Determine event_type and location based on appointment_type and meeting context
        appointment_type = appt.appointment_type or "consultation"

        # Map appointment type to event type (matching frontend logic)
        if appointment_type == "consultation":
            event_type = "consultation"
        else:
            event_type = "meeting"

        # Determine location (frontend checks meeting_mode first, then booked_via)
        location = appt.location or ""
        if not location:
            if appt.booked_via == "ai_assistant":
                location = "Phone Call"

        return {
            "id": f"appt-{appt.id}",
            "title": f"Appointment with {appt.contact_name or 'Client'}",
            "description": appt.notes or "",
            "start_time": appt.start_time.isoformat() if appt.start_time else None,
            "end_time": appt.end_time.isoformat() if appt.end_time else None,
            "event_type": event_type,
            "location": location,
            "source": "scheduler",
            "related_lead_id": appt.contact_id,
            "related_loan_id": None,
            "attendee_name": appt.contact_name,
            "attendee_email": appt.contact_email,
            "status": appt.status or "BOOKED",
            "is_appointment": True,
            "is_crm_event": False,
            "appointment_id": appt.appointment_id,
            "booked_via": appt.booked_via,
            "meeting_link": appt.meeting_link,
            "duration_minutes": appt.duration_minutes,
            "attendee_phone": appt.contact_phone,
            "assigned_user_id": appt.loan_officer_id,
            "meeting_mode": (
                "PHONE" if (appt.booked_via == "ai_assistant" or location == "Phone Call")
                else "VIDEO" if appt.meeting_link
                else "IN_PERSON"
            ),
        }

    def _transform_crm_event(self, event) -> Dict[str, Any]:
        """
        Transform CRMCalendarEvent to unified format.
        Matches frontend crmEventToEvent() logic.
        API returns start_at/end_at, we convert to start_time/end_time.
        """
        return {
            "id": f"crm-{event.id}",
            "title": event.title or "CRM Event",
            "description": event.notes or "",
            "start_time": event.start_at.isoformat() if event.start_at else None,
            "end_time": event.end_at.isoformat() if event.end_at else None,
            "event_type": "meeting",
            "location": event.location or "",
            "source": "crm",
            "related_lead_id": event.related_entity_id if event.related_entity_type == "lead" else None,
            "related_loan_id": event.related_entity_id if event.related_entity_type == "loan" else None,
            "related_contact_id": event.related_entity_id if event.related_entity_type == "contact" else None,
            "attendee_name": None,
            "status": event.status or "scheduled",
            "is_appointment": False,
            "is_crm_event": True,
            "crm_event_id": event.id,
            "attendees": event.attendees or [],
            "sync_status": event.sync_status,
            "salesforce_event_id": event.sync_mapping.salesforce_event_id if event.sync_mapping else None,
        }


    def _detect_conflicts(self, events: List[Dict]) -> List[Dict]:
        """
        Scan sorted events for time overlaps and flag conflicts.
        - "hard": Two events overlap (double-booked)
        - "soft": Two events are back-to-back with < 5 min gap
        """
        conflicts = []
        BACK_TO_BACK_THRESHOLD_MINUTES = 5

        for i in range(len(events) - 1):
            curr = events[i]
            next_ev = events[i + 1]

            curr_end = curr.get("end_time")
            next_start = next_ev.get("start_time")

            if not curr_end or not next_start:
                continue

            try:
                c_end = datetime.fromisoformat(curr_end.replace("Z", "+00:00"))
                n_start = datetime.fromisoformat(next_start.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            if c_end > n_start:
                # Hard conflict: overlap
                conflicts.append({
                    "type": "hard",
                    "severity": "double_booked",
                    "event_a_id": curr.get("id"),
                    "event_a_title": curr.get("title"),
                    "event_b_id": next_ev.get("id"),
                    "event_b_title": next_ev.get("title"),
                    "overlap_start": next_start,
                    "overlap_end": curr_end,
                })
            else:
                gap_minutes = (n_start - c_end).total_seconds() / 60
                if gap_minutes < BACK_TO_BACK_THRESHOLD_MINUTES:
                    conflicts.append({
                        "type": "soft",
                        "severity": "back_to_back",
                        "event_a_id": curr.get("id"),
                        "event_a_title": curr.get("title"),
                        "event_b_id": next_ev.get("id"),
                        "event_b_title": next_ev.get("title"),
                        "gap_minutes": round(gap_minutes, 1),
                    })

        return conflicts


def get_unified_calendar_service(db: Session, user_id: int, organization_id: int) -> UnifiedCalendarService:
    """Factory function to create UnifiedCalendarService instance."""
    return UnifiedCalendarService(db, user_id, organization_id=organization_id)
