"""
Waitlist Service - Queue management for appointment scheduling.

Handles:
- Adding/removing people from the waitlist
- Position management (auto-recalculate on changes)
- Offering cancelled slots to waitlisted people
- Expiring stale offers (24-hour timeout)
- Converting accepted offers into booked appointments
- Auto-offer logic on appointment cancellation
"""

import logging
from datetime import datetime, timedelta, timezone, date, time
from typing import Dict, List, Optional, Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database.models.waiting_room import WaitlistEntry, WaitlistStatus

logger = logging.getLogger(__name__)

# Offer expiration timeout in hours
OFFER_TIMEOUT_HOURS = 24


class WaitlistService:
    """Service for managing appointment waitlists / queues."""

    def __init__(self, db: Session, models: Dict[str, Any]):
        """
        Args:
            db: SQLAlchemy session
            models: Dict of scheduler model classes (Appointment, AppointmentType, etc.)
        """
        self.db = db
        self.models = models

    # ========================================================================
    # JOIN / LEAVE
    # ========================================================================

    def join_waitlist(self, data: Dict[str, Any]) -> WaitlistEntry:
        """Add a person to the waitlist, assigning the next available position.

        Args:
            data: Dict with keys: organization_id, appointment_type_id, name, email,
                  phone (optional), preferred_dates (optional), preferred_times (optional),
                  user_id (optional), notes (optional)

        Returns:
            The created WaitlistEntry.
        """
        org_id = data["organization_id"]
        appt_type_id = data["appointment_type_id"]

        # Check for duplicate: same email + same appointment type + still waiting/offered
        existing = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.appointment_type_id == appt_type_id,
            WaitlistEntry.email == data["email"],
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        ).first()

        if existing:
            raise ValueError("Already on the waitlist for this appointment type")

        # Get next position
        max_pos = self.db.query(func.max(WaitlistEntry.position)).filter(
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.appointment_type_id == appt_type_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        ).scalar() or 0

        entry = WaitlistEntry(
            organization_id=org_id,
            appointment_type_id=appt_type_id,
            user_id=data.get("user_id"),
            name=data["name"],
            email=data["email"],
            phone=data.get("phone"),
            preferred_dates=data.get("preferred_dates", []),
            preferred_times=data.get("preferred_times", []),
            position=max_pos + 1,
            status=WaitlistStatus.WAITING,
            notes=data.get("notes"),
        )

        self.db.add(entry)
        self.db.flush()

        logger.info(
            f"Waitlist join: {entry.email} at position {entry.position} "
            f"for appointment_type_id={appt_type_id}, org={org_id}"
        )
        return entry

    def leave_waitlist(self, entry_id: int, org_id: Optional[int] = None) -> bool:
        """Remove an entry from the waitlist and recalculate positions.

        Args:
            entry_id: The waitlist entry ID
            org_id: Optional org_id for tenant isolation

        Returns:
            True if entry was cancelled.
        """
        filters = [WaitlistEntry.id == entry_id]
        if org_id is not None:
            filters.append(WaitlistEntry.organization_id == org_id)

        entry = self.db.query(WaitlistEntry).filter(*filters).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status not in (WaitlistStatus.WAITING, WaitlistStatus.OFFERED):
            raise ValueError(f"Cannot leave waitlist with status '{entry.status.value}'")

        old_position = entry.position
        appt_type_id = entry.appointment_type_id
        entry_org_id = entry.organization_id

        entry.status = WaitlistStatus.CANCELLED
        entry.updated_at = datetime.now(timezone.utc)

        # Recalculate positions for remaining entries
        self._recalculate_positions(entry_org_id, appt_type_id)

        logger.info(
            f"Waitlist leave: entry {entry_id} (was position {old_position}), "
            f"appointment_type_id={appt_type_id}"
        )
        return True

    # ========================================================================
    # POSITION / QUERY
    # ========================================================================

    def get_position(self, entry_id: int, org_id: Optional[int] = None) -> Dict[str, Any]:
        """Get position info for a waitlist entry.

        Returns:
            Dict with position, total_waiting, status, etc.
        """
        filters = [WaitlistEntry.id == entry_id]
        if org_id is not None:
            filters.append(WaitlistEntry.organization_id == org_id)

        entry = self.db.query(WaitlistEntry).filter(*filters).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        total_waiting = self.db.query(func.count(WaitlistEntry.id)).filter(
            WaitlistEntry.organization_id == entry.organization_id,
            WaitlistEntry.appointment_type_id == entry.appointment_type_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        ).scalar() or 0

        result = {
            "id": entry.id,
            "position": entry.position,
            "total_waiting": total_waiting,
            "status": entry.status.value,
            "name": entry.name,
            "email": entry.email,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }

        if entry.status == WaitlistStatus.OFFERED:
            result["offered_at"] = entry.offered_at.isoformat() if entry.offered_at else None
            result["offered_slot_time"] = entry.offered_slot_time.isoformat() if entry.offered_slot_time else None
            result["expires_at"] = entry.expires_at.isoformat() if entry.expires_at else None

        return result

    def get_waitlist(
        self,
        org_id: int,
        appointment_type_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get the full waitlist for an org, optionally filtered.

        Returns:
            Dict with entries list and total count.
        """
        query = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.organization_id == org_id,
        )

        if appointment_type_id is not None:
            query = query.filter(WaitlistEntry.appointment_type_id == appointment_type_id)

        if status:
            try:
                status_enum = WaitlistStatus(status)
                query = query.filter(WaitlistEntry.status == status_enum)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")

        total = query.count()

        entries = query.order_by(
            WaitlistEntry.status.asc(),  # WAITING first
            WaitlistEntry.position.asc(),
        ).offset(offset).limit(limit).all()

        return {
            "entries": [self._entry_to_dict(e) for e in entries],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ========================================================================
    # OFFER / ACCEPT
    # ========================================================================

    def offer_slot(
        self,
        entry_id: int,
        slot_time: datetime,
        org_id: Optional[int] = None,
    ) -> WaitlistEntry:
        """Offer a specific time slot to a waitlist entry.

        Args:
            entry_id: The waitlist entry to offer to
            slot_time: The datetime of the slot being offered
            org_id: Optional org_id for tenant isolation

        Returns:
            The updated WaitlistEntry.
        """
        filters = [WaitlistEntry.id == entry_id]
        if org_id is not None:
            filters.append(WaitlistEntry.organization_id == org_id)

        entry = self.db.query(WaitlistEntry).filter(*filters).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status != WaitlistStatus.WAITING:
            raise ValueError(f"Can only offer to entries with WAITING status, got '{entry.status.value}'")

        now = datetime.now(timezone.utc)
        entry.status = WaitlistStatus.OFFERED
        entry.offered_at = now
        entry.offered_slot_time = slot_time
        entry.expires_at = now + timedelta(hours=OFFER_TIMEOUT_HOURS)
        entry.updated_at = now

        self.db.flush()

        logger.info(
            f"Waitlist offer: entry {entry_id} offered slot at {slot_time.isoformat()}, "
            f"expires {entry.expires_at.isoformat()}"
        )
        return entry

    def accept_offer(
        self,
        entry_id: int,
        org_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Accept an offered slot, creating an appointment.

        Args:
            entry_id: The waitlist entry with the offer
            org_id: Optional org_id for tenant isolation

        Returns:
            Dict with the created appointment info and waitlist entry.
        """
        filters = [WaitlistEntry.id == entry_id]
        if org_id is not None:
            filters.append(WaitlistEntry.organization_id == org_id)

        entry = self.db.query(WaitlistEntry).filter(*filters).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status != WaitlistStatus.OFFERED:
            raise ValueError(f"Can only accept offers with OFFERED status, got '{entry.status.value}'")

        # Check if offer has expired
        now = datetime.now(timezone.utc)
        if entry.expires_at and entry.expires_at < now:
            entry.status = WaitlistStatus.EXPIRED
            entry.updated_at = now
            self.db.flush()
            raise ValueError("This offer has expired")

        # Get the appointment type for default settings
        AppointmentType = self.models.get("AppointmentType")
        appt_type = None
        if AppointmentType:
            appt_type = self.db.query(AppointmentType).filter(
                AppointmentType.id == entry.appointment_type_id,
            ).first()

        duration_minutes = 30
        title = "Waitlist Appointment"
        if appt_type:
            duration_minutes = appt_type.default_duration_minutes or 30
            title = appt_type.type_name or title

        # Create the appointment
        Appointment = self.models.get("Appointment")
        if not Appointment:
            raise ValueError("Appointment model not available")

        slot_start = entry.offered_slot_time
        slot_end = slot_start + timedelta(minutes=duration_minutes)

        appointment = Appointment(
            organization_id=entry.organization_id,
            appointment_type_id=entry.appointment_type_id,
            title=f"{title} - {entry.name}",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            duration_minutes=duration_minutes,
            attendee_name=entry.name,
            attendee_email=entry.email,
            attendee_phone=entry.phone,
            attendee_notes=f"Booked from waitlist (entry #{entry.id})",
            status=self._get_booked_status(),
        )

        self.db.add(appointment)
        self.db.flush()

        # Update waitlist entry
        entry.status = WaitlistStatus.ACCEPTED
        entry.accepted_at = now
        entry.appointment_id = appointment.id
        entry.updated_at = now

        # Recalculate positions
        self._recalculate_positions(entry.organization_id, entry.appointment_type_id)

        self.db.flush()

        logger.info(
            f"Waitlist accepted: entry {entry_id} -> appointment {appointment.id} "
            f"at {slot_start.isoformat()}"
        )

        return {
            "waitlist_entry": self._entry_to_dict(entry),
            "appointment": {
                "id": appointment.id,
                "title": appointment.title,
                "scheduled_start": appointment.scheduled_start.isoformat(),
                "scheduled_end": appointment.scheduled_end.isoformat(),
                "duration_minutes": appointment.duration_minutes,
                "attendee_name": appointment.attendee_name,
                "attendee_email": appointment.attendee_email,
            },
        }

    # ========================================================================
    # CANCELLATION / AUTO-OFFER
    # ========================================================================

    def process_cancellation(self, appointment_id: int, org_id: int) -> Optional[Dict[str, Any]]:
        """When an appointment is cancelled, auto-offer the slot to the next matching waitlister.

        Args:
            appointment_id: The cancelled appointment ID
            org_id: Organization ID

        Returns:
            Dict with the offered entry info, or None if no match found.
        """
        Appointment = self.models.get("Appointment")
        if not Appointment:
            return None

        appointment = self.db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == org_id,
        ).first()

        if not appointment:
            logger.warning(f"Cancelled appointment {appointment_id} not found for waitlist processing")
            return None

        appt_type_id = appointment.appointment_type_id
        if not appt_type_id:
            logger.debug(f"Cancelled appointment {appointment_id} has no appointment_type_id, skipping waitlist")
            return None

        slot_time = appointment.scheduled_start
        if not slot_time:
            return None

        return self.notify_next(appt_type_id, org_id, slot_time=slot_time)

    def notify_next(
        self,
        appointment_type_id: int,
        org_id: int,
        slot_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Offer the slot to the next eligible person on the waitlist.

        Finds the first WAITING entry matching the given appointment type, with
        optional preference matching against slot_time.

        Args:
            appointment_type_id: The appointment type
            org_id: Organization ID
            slot_time: Optional specific slot time to match against preferences

        Returns:
            Dict with the offered entry info, or None if no one is waiting.
        """
        # Get all waiting entries in position order
        waiting = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.appointment_type_id == appointment_type_id,
            WaitlistEntry.status == WaitlistStatus.WAITING,
        ).order_by(WaitlistEntry.position.asc()).all()

        if not waiting:
            return None

        # If we have a specific slot time, try to match preferences first
        if slot_time:
            best_match = self._find_best_match(waiting, slot_time)
            if best_match:
                self.offer_slot(best_match.id, slot_time, org_id=org_id)
                return {
                    "entry_id": best_match.id,
                    "name": best_match.name,
                    "email": best_match.email,
                    "position": best_match.position,
                    "offered_slot_time": slot_time.isoformat(),
                    "match_type": "preference",
                }

        # No preference match -- offer to first in line
        first = waiting[0]
        if slot_time:
            self.offer_slot(first.id, slot_time, org_id=org_id)
        else:
            # No specific slot time -- just mark as offered with no time (admin will follow up)
            now = datetime.now(timezone.utc)
            first.status = WaitlistStatus.OFFERED
            first.offered_at = now
            first.expires_at = now + timedelta(hours=OFFER_TIMEOUT_HOURS)
            first.updated_at = now
            self.db.flush()

        return {
            "entry_id": first.id,
            "name": first.name,
            "email": first.email,
            "position": first.position,
            "offered_slot_time": slot_time.isoformat() if slot_time else None,
            "match_type": "position",
        }

    # ========================================================================
    # EXPIRATION
    # ========================================================================

    def expire_offers(self) -> int:
        """Expire all offers that have passed their expiration time.

        Returns:
            Number of expired offers.
        """
        now = datetime.now(timezone.utc)

        expired_entries = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.status == WaitlistStatus.OFFERED,
            WaitlistEntry.expires_at < now,
        ).all()

        count = 0
        org_type_pairs = set()

        for entry in expired_entries:
            entry.status = WaitlistStatus.EXPIRED
            entry.updated_at = now
            org_type_pairs.add((entry.organization_id, entry.appointment_type_id))
            count += 1

        # Recalculate positions for affected queues
        for org_id, appt_type_id in org_type_pairs:
            self._recalculate_positions(org_id, appt_type_id)

        if count > 0:
            self.db.flush()
            logger.info(f"Expired {count} waitlist offers")

        return count

    # ========================================================================
    # REORDER
    # ========================================================================

    def reorder_entry(
        self,
        entry_id: int,
        new_position: int,
        org_id: int,
    ) -> WaitlistEntry:
        """Move a waitlist entry to a new position (admin action).

        Args:
            entry_id: The entry to move
            new_position: Target position (1-based)
            org_id: Organization ID

        Returns:
            The updated entry.
        """
        entry = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.id == entry_id,
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.status == WaitlistStatus.WAITING,
        ).first()

        if not entry:
            raise ValueError("Waitlist entry not found or not in WAITING status")

        old_position = entry.position
        appt_type_id = entry.appointment_type_id

        if new_position < 1:
            new_position = 1

        # Get all active entries for this queue (excluding the one being moved)
        others = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.appointment_type_id == appt_type_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
            WaitlistEntry.id != entry_id,
        ).order_by(WaitlistEntry.position.asc()).all()

        # Cap new_position
        max_pos = len(others) + 1
        if new_position > max_pos:
            new_position = max_pos

        # Rebuild positions: insert entry at new_position
        pos = 1
        for other in others:
            if pos == new_position:
                pos += 1
            other.position = pos
            pos += 1

        entry.position = new_position
        entry.updated_at = datetime.now(timezone.utc)

        self.db.flush()

        logger.info(
            f"Waitlist reorder: entry {entry_id} moved from position {old_position} to {new_position}"
        )
        return entry

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    def _recalculate_positions(self, org_id: int, appointment_type_id: int) -> None:
        """Recalculate sequential positions for all active entries in a queue."""
        entries = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.organization_id == org_id,
            WaitlistEntry.appointment_type_id == appointment_type_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        ).order_by(WaitlistEntry.position.asc(), WaitlistEntry.created_at.asc()).all()

        for i, entry in enumerate(entries, start=1):
            if entry.position != i:
                entry.position = i

    def _find_best_match(
        self,
        entries: List[WaitlistEntry],
        slot_time: datetime,
    ) -> Optional[WaitlistEntry]:
        """Find the best matching waitlist entry for a given slot time.

        Matches against preferred_dates and preferred_times.
        Returns the first entry whose preferences match, or None.
        """
        slot_date_str = slot_time.strftime("%Y-%m-%d")
        slot_hour = slot_time.hour

        for entry in entries:
            date_match = True
            time_match = True

            # Check date preferences
            pref_dates = entry.preferred_dates or []
            if pref_dates:
                date_match = slot_date_str in pref_dates

            # Check time preferences
            pref_times = entry.preferred_times or []
            if pref_times:
                time_match = False
                for pref in pref_times:
                    pref_lower = pref.lower() if isinstance(pref, str) else ""
                    if pref_lower == "morning" and 6 <= slot_hour < 12:
                        time_match = True
                        break
                    elif pref_lower == "afternoon" and 12 <= slot_hour < 17:
                        time_match = True
                        break
                    elif pref_lower == "evening" and 17 <= slot_hour < 21:
                        time_match = True
                        break
                    elif "-" in pref_lower:
                        # Range format: "09:00-12:00"
                        try:
                            start_str, end_str = pref_lower.split("-")
                            start_h = int(start_str.strip().split(":")[0])
                            end_h = int(end_str.strip().split(":")[0])
                            if start_h <= slot_hour < end_h:
                                time_match = True
                                break
                        except (ValueError, IndexError):
                            continue

            if date_match and time_match:
                return entry

        return None

    def _get_booked_status(self):
        """Get the BOOKED enum value from the scheduler models."""
        try:
            from smart_scheduler_models import AppointmentStatus
            return AppointmentStatus.BOOKED
        except ImportError:
            return "booked"

    def _entry_to_dict(self, entry: WaitlistEntry) -> Dict[str, Any]:
        """Convert a WaitlistEntry to a serializable dict."""
        return {
            "id": entry.id,
            "organization_id": entry.organization_id,
            "appointment_type_id": entry.appointment_type_id,
            "user_id": entry.user_id,
            "name": entry.name,
            "email": entry.email,
            "phone": entry.phone,
            "preferred_dates": entry.preferred_dates or [],
            "preferred_times": entry.preferred_times or [],
            "position": entry.position,
            "status": entry.status.value if entry.status else None,
            "offered_at": entry.offered_at.isoformat() if entry.offered_at else None,
            "offered_slot_time": entry.offered_slot_time.isoformat() if entry.offered_slot_time else None,
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            "accepted_at": entry.accepted_at.isoformat() if entry.accepted_at else None,
            "appointment_id": entry.appointment_id,
            "notes": entry.notes,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
