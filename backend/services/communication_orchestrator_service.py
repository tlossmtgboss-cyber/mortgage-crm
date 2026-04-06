"""
CommunicationOrchestrator (Domain 2 — Unified Communications)

Routes all inbound communications (SMS, email, call) to the correct loan
file and ensures every message is visible to all authorized file
collaborators.

Flow:
    1. Identify the loan file from the sender's phone / email.
    2. Create a unified ``FileCommunication`` record.
    3. Push real-time notifications to all ``CommunicationParticipant`` users.
    4. Trigger ``CommunicationDraftAgent`` for auto-reply drafts.

Usage:
    from services.communication_orchestrator_service import CommunicationOrchestrator

    orch = CommunicationOrchestrator(db=session)
    result = await orch.route_inbound_sms(
        from_phone="+15551234567",
        body="When is my closing date?",
    )
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phone normalization helper
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> Optional[str]:
    """Strip a phone number down to 10 US digits for matching.

    Handles +1, 1-prefix, parentheses, dashes, dots, and spaces.
    Returns ``None`` when the input cannot be coerced to 10 digits.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


# ---------------------------------------------------------------------------
# CommunicationOrchestrator
# ---------------------------------------------------------------------------

class CommunicationOrchestrator:
    """Routes all inbound comms (SMS, email, call) to the correct loan file.

    Ensures every communication is visible to all authorized file
    collaborators via the ``FileCommunication`` timeline and pushes
    real-time WebSocket events so the UI updates instantly.
    """

    def __init__(self, db: Session):
        self.db = db

    # =====================================================================
    # Public API
    # =====================================================================

    async def route_inbound_sms(
        self,
        from_phone: str,
        body: str,
        media_urls: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route an inbound SMS to the correct loan file.

        Creates a ``FileCommunication`` record with ``channel='sms'``,
        notifies all collaborators, and triggers auto-draft generation.

        Returns a dict with keys:
            routed (bool), file_id, lead_id, communication_id,
            collaborators_notified (int), error (str | None).
        """
        # 1. Resolve loan file by phone number
        file_info = await self._find_file_by_phone(from_phone)
        if not file_info:
            logger.warning(
                "Inbound SMS from %s could not be routed — no matching file",
                from_phone,
            )
            return {
                "routed": False,
                "file_id": None,
                "lead_id": None,
                "communication_id": None,
                "collaborators_notified": 0,
                "error": "no_matching_file",
            }

        file_id: int = file_info["file_id"]
        org_id: int = file_info["organization_id"]

        # 2. Build attachment payload from media URLs
        attachments = (
            [{"url": url, "type": "media"} for url in media_urls]
            if media_urls
            else None
        )

        # 3. Create the unified FileCommunication record
        comm = await self._create_file_communication(
            file_id=file_id,
            org_id=org_id,
            direction="inbound",
            channel="sms",
            body=body,
            from_party=from_phone,
            to_party=file_info.get("lo_identifier", "system"),
            attachments=attachments,
            extra_metadata=metadata,
            source_table="sms_messages",
        )

        # 4. Notify all collaborators via WebSocket
        notified = await self._notify_collaborators(file_id, org_id, comm)

        # 5. Fire-and-forget auto-draft generation
        await self._trigger_auto_draft(file_id, comm["id"])

        return {
            "routed": True,
            "file_id": file_id,
            "lead_id": file_info.get("lead_id"),
            "communication_id": comm["id"],
            "collaborators_notified": notified,
            "error": None,
        }

    async def route_inbound_email(
        self,
        from_email: str,
        subject: str,
        body: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route an inbound email to the correct loan file.

        Creates a ``FileCommunication`` record with ``channel='email'``,
        notifies all collaborators, and triggers auto-draft generation.
        """
        file_info = await self._find_file_by_email(from_email)
        if not file_info:
            logger.warning(
                "Inbound email from %s could not be routed — no matching file",
                from_email,
            )
            return {
                "routed": False,
                "file_id": None,
                "lead_id": None,
                "communication_id": None,
                "collaborators_notified": 0,
                "error": "no_matching_file",
            }

        file_id: int = file_info["file_id"]
        org_id: int = file_info["organization_id"]

        comm = await self._create_file_communication(
            file_id=file_id,
            org_id=org_id,
            direction="inbound",
            channel="email",
            body=body,
            from_party=from_email,
            to_party=file_info.get("lo_identifier", "system"),
            subject=subject,
            attachments=attachments,
            extra_metadata=metadata,
            source_table="email_messages",
        )

        notified = await self._notify_collaborators(file_id, org_id, comm)
        await self._trigger_auto_draft(file_id, comm["id"])

        return {
            "routed": True,
            "file_id": file_id,
            "lead_id": file_info.get("lead_id"),
            "communication_id": comm["id"],
            "collaborators_notified": notified,
            "error": None,
        }

    async def route_call_event(
        self,
        call_id: str,
        event_type: str,
        from_phone: Optional[str] = None,
        transcript: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route a call event (start, end, transcript) to the correct file.

        ``event_type`` should be one of: ``start``, ``end``,
        ``transcript``, ``voicemail``.

        For ``start`` / ``voicemail`` events, ``from_phone`` is required to
        resolve the file.  For ``transcript`` and ``end`` events the
        ``call_id`` stored in ``extra_metadata`` on a prior ``start``
        record is used for correlation.
        """
        # Resolve file — prefer phone lookup, fall back to call_id correlation
        file_info: Optional[Dict[str, Any]] = None

        if from_phone:
            file_info = await self._find_file_by_phone(from_phone)

        if not file_info and call_id:
            file_info = await self._find_file_by_call_id(call_id)

        if not file_info:
            logger.warning(
                "Call event %s (call_id=%s) could not be routed",
                event_type,
                call_id,
            )
            return {
                "routed": False,
                "file_id": None,
                "lead_id": None,
                "communication_id": None,
                "collaborators_notified": 0,
                "error": "no_matching_file",
            }

        file_id: int = file_info["file_id"]
        org_id: int = file_info["organization_id"]

        # Build body depending on event type
        body_map = {
            "start": f"Inbound call started (call_id={call_id})",
            "end": f"Call ended (call_id={call_id})",
            "transcript": transcript or f"Call transcript (call_id={call_id})",
            "voicemail": transcript or f"Voicemail received (call_id={call_id})",
        }
        body = body_map.get(event_type, f"Call event '{event_type}' (call_id={call_id})")

        event_metadata = dict(metadata or {})
        event_metadata["call_id"] = call_id
        event_metadata["event_type"] = event_type

        comm = await self._create_file_communication(
            file_id=file_id,
            org_id=org_id,
            direction="inbound",
            channel="call",
            body=body,
            from_party=from_phone or call_id,
            to_party=file_info.get("lo_identifier", "system"),
            extra_metadata=event_metadata,
            source_table="call_logs",
            source_id=call_id,
        )

        notified = await self._notify_collaborators(file_id, org_id, comm)

        # Auto-draft only for transcripts / voicemails (text content to reply to)
        if event_type in ("transcript", "voicemail") and transcript:
            await self._trigger_auto_draft(file_id, comm["id"])

        return {
            "routed": True,
            "file_id": file_id,
            "lead_id": file_info.get("lead_id"),
            "communication_id": comm["id"],
            "collaborators_notified": notified,
            "error": None,
        }

    # =====================================================================
    # File resolution helpers
    # =====================================================================

    async def _find_file_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Find the most relevant loan file by borrower phone number.

        Search order:
            1. ``loans.borrower_phone`` / ``loans.co_borrower_phone`` — active files first.
            2. ``leads.phone`` / ``leads.co_applicant_phone`` — match lead, then its loan.

        Returns a dict with ``file_id``, ``organization_id``, ``lead_id``,
        ``lo_identifier`` or ``None``.
        """
        normalized = _normalize_phone(phone)
        if not normalized:
            return None

        # Build a LIKE pattern that matches the 10-digit tail regardless of
        # stored format (+1, dashes, parens, etc.).
        like_pattern = f"%{normalized[-10:]}"

        # --- Try loans table first (active pipeline prioritized) ---
        terminal_stages = (
            "'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'"
        )
        row = self.db.execute(
            text(
                f"""
                SELECT id, organization_id, loan_officer_id, borrower_name
                FROM loans
                WHERE (
                    REPLACE(REPLACE(REPLACE(REPLACE(borrower_phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :pattern
                    OR
                    REPLACE(REPLACE(REPLACE(REPLACE(co_borrower_phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :pattern
                )
                ORDER BY
                    CASE WHEN stage NOT IN ({terminal_stages}) THEN 0 ELSE 1 END,
                    created_at DESC
                LIMIT 1
                """
            ),
            {"pattern": like_pattern},
        ).fetchone()

        if row:
            return {
                "file_id": row[0],
                "organization_id": row[1],
                "lead_id": None,
                "lo_identifier": f"user:{row[2]}" if row[2] else "system",
            }

        # --- Fall back to leads table ---
        lead_row = self.db.execute(
            text(
                """
                SELECT l.id, l.organization_id, l.owner_id, l.loan_number
                FROM leads l
                WHERE (
                    REPLACE(REPLACE(REPLACE(REPLACE(l.phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :pattern
                    OR
                    REPLACE(REPLACE(REPLACE(REPLACE(l.co_applicant_phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :pattern
                )
                ORDER BY l.created_at DESC
                LIMIT 1
                """
            ),
            {"pattern": like_pattern},
        ).fetchone()

        if not lead_row:
            return None

        lead_id = lead_row[0]
        org_id = lead_row[1]
        owner_id = lead_row[2]
        loan_number = lead_row[3]

        # If the lead has a linked loan_number, resolve to that loan file
        file_id: Optional[int] = None
        if loan_number:
            loan_row = self.db.execute(
                text(
                    "SELECT id FROM loans WHERE loan_number = :ln LIMIT 1"
                ),
                {"ln": loan_number},
            ).fetchone()
            if loan_row:
                file_id = loan_row[0]

        # If no loan file found, the lead itself is returned with file_id=None
        # so the caller can decide how to handle pre-loan communications.
        if file_id is None:
            logger.info(
                "Phone %s matched lead %s but no linked loan file", phone, lead_id,
            )
            return None

        return {
            "file_id": file_id,
            "organization_id": org_id,
            "lead_id": lead_id,
            "lo_identifier": f"user:{owner_id}" if owner_id else "system",
        }

    async def _find_file_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find the most relevant loan file by borrower email.

        Search order mirrors ``_find_file_by_phone``: loans first, then
        leads with a linked loan.  Email matching is case-insensitive.
        """
        if not email:
            return None

        lower_email = email.strip().lower()

        # --- Loans table ---
        terminal_stages = (
            "'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'"
        )
        row = self.db.execute(
            text(
                f"""
                SELECT id, organization_id, loan_officer_id, borrower_name
                FROM loans
                WHERE LOWER(borrower_email) = :email
                   OR LOWER(co_borrower_email) = :email
                ORDER BY
                    CASE WHEN stage NOT IN ({terminal_stages}) THEN 0 ELSE 1 END,
                    created_at DESC
                LIMIT 1
                """
            ),
            {"email": lower_email},
        ).fetchone()

        if row:
            return {
                "file_id": row[0],
                "organization_id": row[1],
                "lead_id": None,
                "lo_identifier": f"user:{row[2]}" if row[2] else "system",
            }

        # --- Leads table ---
        lead_row = self.db.execute(
            text(
                """
                SELECT l.id, l.organization_id, l.owner_id, l.loan_number
                FROM leads l
                WHERE LOWER(l.email) = :email
                   OR LOWER(l.co_applicant_email) = :email
                ORDER BY l.created_at DESC
                LIMIT 1
                """
            ),
            {"email": lower_email},
        ).fetchone()

        if not lead_row:
            return None

        lead_id = lead_row[0]
        org_id = lead_row[1]
        owner_id = lead_row[2]
        loan_number = lead_row[3]

        file_id: Optional[int] = None
        if loan_number:
            loan_row = self.db.execute(
                text("SELECT id FROM loans WHERE loan_number = :ln LIMIT 1"),
                {"ln": loan_number},
            ).fetchone()
            if loan_row:
                file_id = loan_row[0]

        if file_id is None:
            logger.info(
                "Email %s matched lead %s but no linked loan file", email, lead_id,
            )
            return None

        return {
            "file_id": file_id,
            "organization_id": org_id,
            "lead_id": lead_id,
            "lo_identifier": f"user:{owner_id}" if owner_id else "system",
        }

    async def _find_file_by_call_id(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Correlate a call event back to a file via a prior FileCommunication record.

        Used when a ``transcript`` or ``end`` event arrives without a phone
        number — we look up the ``start`` record by its ``source_id``.
        """
        row = self.db.execute(
            text(
                """
                SELECT file_id, organization_id
                FROM file_communications
                WHERE source_id = :call_id AND channel = 'call'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"call_id": call_id},
        ).fetchone()

        if not row:
            return None

        return {
            "file_id": row[0],
            "organization_id": row[1],
            "lead_id": None,
            "lo_identifier": "system",
        }

    # =====================================================================
    # Record creation
    # =====================================================================

    async def _create_file_communication(
        self,
        file_id: int,
        org_id: int,
        direction: str,
        channel: str,
        body: str,
        from_party: str,
        to_party: str,
        subject: Optional[str] = None,
        attachments: Optional[Any] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        source_table: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a ``FileCommunication`` row and return its dict representation."""
        from database.models.file_communication import FileCommunication

        record = FileCommunication(
            organization_id=org_id,
            file_id=file_id,
            direction=direction,
            channel=channel,
            body=body,
            from_party=from_party,
            to_party=to_party,
            subject=subject,
            attachments=attachments,
            extra_metadata=extra_metadata,
            source_table=source_table,
            source_id=source_id,
            read_by=[],
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        self.db.flush()  # Assigns record.id without full commit

        logger.info(
            "Created FileCommunication id=%s file=%s channel=%s direction=%s",
            record.id, file_id, channel, direction,
        )

        return {
            "id": record.id,
            "file_id": file_id,
            "organization_id": org_id,
            "direction": direction,
            "channel": channel,
            "body": body,
            "from_party": from_party,
            "to_party": to_party,
            "subject": subject,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    # =====================================================================
    # Collaborator notifications
    # =====================================================================

    async def _notify_collaborators(
        self,
        file_id: int,
        org_id: int,
        communication: Dict[str, Any],
    ) -> int:
        """Push a real-time notification to every collaborator on the file.

        Queries ``CommunicationParticipant`` for users with ``notify=True``
        and dispatches a WebSocket event per user.

        Returns the number of users notified.
        """
        from database.models.file_communication import CommunicationParticipant

        participants = (
            self.db.query(CommunicationParticipant)
            .filter(
                CommunicationParticipant.file_id == file_id,
                CommunicationParticipant.organization_id == org_id,
                CommunicationParticipant.notify.is_(True),
            )
            .all()
        )

        if not participants:
            logger.debug("No collaborators to notify for file %s", file_id)
            return 0

        event_payload = {
            "type": "file_communication_new",
            "file_id": file_id,
            "communication_id": communication["id"],
            "channel": communication["channel"],
            "direction": communication["direction"],
            "from_party": communication["from_party"],
            "body_preview": (communication["body"] or "")[:120],
            "created_at": communication.get("created_at"),
        }

        notified = 0
        for participant in participants:
            try:
                await self._push_ws_event(participant.user_id, event_payload)
                notified += 1
            except Exception as e:
                logger.exception(
                    "Failed to push WS event to user %s for file %s: %s",
                    participant.user_id, file_id, e,
                )

        logger.info(
            "Notified %d/%d collaborators for file %s comm %s",
            notified, len(participants), file_id, communication["id"],
        )
        return notified

    async def _push_ws_event(self, user_id: int, payload: Dict[str, Any]) -> None:
        """Send a WebSocket event to a single user.

        Uses the application's ``ConnectionManager`` if available.
        Falls back to a no-op when WebSocket infrastructure is not loaded
        (e.g. during tests or offline processing).
        """
        try:
            from services.portal_websocket_service import connection_manager
            if connection_manager is not None:
                await connection_manager.send_personal_message(
                    user_id=user_id, message=payload,
                )
        except (ImportError, AttributeError):
            # WebSocket infrastructure not available — silently skip
            logger.debug(
                "WS push skipped for user %s (no connection_manager)", user_id,
            )

    # =====================================================================
    # Auto-draft trigger
    # =====================================================================

    async def _trigger_auto_draft(
        self,
        file_id: int,
        communication_id: int,
    ) -> None:
        """Trigger ``CommunicationDraftAgent`` for an inbound message.

        Runs in a fire-and-forget style: failures are logged but never
        propagated so that inbound routing is not blocked by draft
        generation errors.
        """
        try:
            from services.communication_draft_agent import CommunicationDraftAgent

            agent = CommunicationDraftAgent()
            from database.models.file_communication import FileCommunication

            comm = self.db.query(FileCommunication).filter(
                FileCommunication.id == communication_id,
            ).first()

            if comm:
                await agent.auto_draft_inbound(
                    file_id=file_id,
                    communication=comm,
                    db=self.db,
                )
                logger.info(
                    "Auto-draft triggered for file=%s comm=%s",
                    file_id, communication_id,
                )
            else:
                logger.warning(
                    "Auto-draft skipped — comm %s not found", communication_id,
                )
        except Exception as e:
            logger.exception(
                "Auto-draft failed for file=%s comm=%s: %s",
                file_id, communication_id, e,
            )
