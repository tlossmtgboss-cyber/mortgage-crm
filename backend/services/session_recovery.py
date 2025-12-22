"""
Session Recovery Service - Cross-Device Session Continuity

This service handles session recovery and continuity across devices/browsers:
- Multiple fallback strategies for finding existing sessions
- Session merging for authenticated users
- Smart recovery based on phone number from call requests
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from chat_state_machine_models import (
    ChatSession, ChatMessage, CallRequest,
    ChatPhase, UrgencyLevel, CTAType
)

logger = logging.getLogger(__name__)


class SessionRecoveryService:
    """Handle session recovery and continuity across devices/browsers"""

    def __init__(self, db: Session):
        self.db = db

    async def recover_or_create_session(
        self,
        visitor_id: str,
        microsite_id: Optional[int] = None,
        user_id: Optional[UUID] = None,
        phone_number: Optional[str] = None,
        source_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[ChatSession, bool]:
        """
        Smart session recovery with multiple fallback strategies:
        1. Active session by visitor_id (last 24h)
        2. Active session by authenticated user_id
        3. Active session by phone_number (if provided during call request)
        4. Create new session

        Returns:
            Tuple of (session, is_returning_user)
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        # Strategy 1: Visitor ID match (most common)
        session = self.db.query(ChatSession).filter(
            and_(
                ChatSession.visitor_id == visitor_id,
                ChatSession.is_active == True,
                ChatSession.created_at > cutoff_time,
                ChatSession.microsite_id == microsite_id if microsite_id else True
            )
        ).order_by(ChatSession.created_at.desc()).first()

        if session:
            logger.info(f"Recovered session by visitor_id: {session.id}")
            return session, True

        # Strategy 2: Authenticated user match
        if user_id:
            session = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.user_id == user_id,
                    ChatSession.is_active == True,
                    ChatSession.created_at > cutoff_time
                )
            ).order_by(ChatSession.created_at.desc()).first()

            if session:
                # Update visitor_id for future continuity
                session.visitor_id = visitor_id
                self.db.commit()
                logger.info(f"Recovered session by user_id, updated visitor_id: {session.id}")
                return session, True

        # Strategy 3: Phone number match (cross-device continuity)
        if phone_number:
            normalized_phone = self._normalize_phone(phone_number)

            # Find recent call requests with this phone
            recent_call = self.db.query(CallRequest).filter(
                and_(
                    CallRequest.caller_phone == normalized_phone,
                    CallRequest.created_at > cutoff_time
                )
            ).order_by(CallRequest.created_at.desc()).first()

            if recent_call:
                session = self.db.query(ChatSession).filter(
                    ChatSession.id == recent_call.session_id
                ).first()

                if session and session.is_active:
                    # Update visitor_id for future continuity
                    session.visitor_id = visitor_id
                    self.db.commit()
                    logger.info(f"Recovered session by phone number: {session.id}")
                    return session, True

        # Strategy 4: Create new session
        session = self._create_new_session(
            visitor_id=visitor_id,
            microsite_id=microsite_id,
            user_id=user_id,
            source_url=source_url,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        logger.info(f"Created new session: {session.id}")
        return session, False

    def _create_new_session(
        self,
        visitor_id: str,
        microsite_id: Optional[int] = None,
        user_id: Optional[UUID] = None,
        source_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> ChatSession:
        """Create a new session with proper initialization"""
        session = ChatSession(
            visitor_id=visitor_id,
            microsite_id=microsite_id,
            user_id=user_id,
            source_url=source_url,
            user_agent=user_agent,
            ip_address=ip_address,
            current_phase=1,
            turn_count=0,
            intent_score=0,
            urgency=UrgencyLevel.LOW.value,
            cta_offered=None,
            cta_declined_count=0,
            intent_signals=[]
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    async def merge_sessions(
        self,
        primary_session_id: UUID,
        secondary_session_id: UUID
    ) -> ChatSession:
        """
        Merge two sessions (e.g., when user authenticates and we discover
        they have both an anonymous and authenticated session)

        Args:
            primary_session_id: The session to keep (usually newer or more active)
            secondary_session_id: The session to merge into primary

        Returns:
            The merged primary session
        """
        primary = self.db.query(ChatSession).filter_by(id=primary_session_id).first()
        secondary = self.db.query(ChatSession).filter_by(id=secondary_session_id).first()

        if not primary or not secondary:
            raise ValueError("One or both sessions not found")

        if primary.id == secondary.id:
            return primary

        logger.info(f"Merging session {secondary_session_id} into {primary_session_id}")

        # Merge intent signals (dedupe by type, keep highest confidence)
        combined_signals = {}
        for signal in (primary.intent_signals or []):
            signal_type = signal.get('signal')
            existing = combined_signals.get(signal_type)
            if not existing or signal.get('confidence', 0) > existing.get('confidence', 0):
                combined_signals[signal_type] = signal

        for signal in (secondary.intent_signals or []):
            signal_type = signal.get('signal')
            existing = combined_signals.get(signal_type)
            if not existing or signal.get('confidence', 0) > existing.get('confidence', 0):
                combined_signals[signal_type] = signal

        primary.intent_signals = list(combined_signals.values())

        # Take highest intent score
        primary.intent_score = max(primary.intent_score or 0, secondary.intent_score or 0)

        # Take highest urgency
        urgency_order = ['low', 'medium', 'high']
        primary_urgency_idx = urgency_order.index(primary.urgency) if primary.urgency in urgency_order else 0
        secondary_urgency_idx = urgency_order.index(secondary.urgency) if secondary.urgency in urgency_order else 0
        if secondary_urgency_idx > primary_urgency_idx:
            primary.urgency = secondary.urgency

        # Take highest phase
        if (secondary.current_phase or 1) > (primary.current_phase or 1):
            primary.current_phase = secondary.current_phase

        # Combine turn counts
        primary.turn_count = (primary.turn_count or 0) + (secondary.turn_count or 0)

        # Merge contact info (prefer non-null values)
        if secondary.contact_name and not primary.contact_name:
            primary.contact_name = secondary.contact_name
        if secondary.contact_email and not primary.contact_email:
            primary.contact_email = secondary.contact_email
        if secondary.contact_phone and not primary.contact_phone:
            primary.contact_phone = secondary.contact_phone

        # Transfer CTA status if secondary had success
        if secondary.cta_accepted and not primary.cta_accepted:
            primary.cta_accepted = True
            primary.cta_accepted_at = secondary.cta_accepted_at
            primary.cta_offered = secondary.cta_offered

        # Merge messages: re-assign secondary messages to primary
        secondary_messages = self.db.query(ChatMessage).filter_by(
            session_id=secondary_session_id
        ).all()

        for msg in secondary_messages:
            msg.session_id = primary_session_id

        # Merge call requests
        secondary_calls = self.db.query(CallRequest).filter_by(
            session_id=secondary_session_id
        ).all()

        for call in secondary_calls:
            call.session_id = primary_session_id

        # Mark secondary as inactive (don't delete for audit trail)
        secondary.is_active = False
        secondary.ended_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(primary)

        logger.info(f"Session merge complete. Primary session now has {primary.turn_count} turns")
        return primary

    def find_sessions_to_merge(
        self,
        user_id: Optional[UUID] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        hours_lookback: int = 48
    ) -> List[ChatSession]:
        """
        Find sessions that might belong to the same user and could be merged.

        Args:
            user_id: Authenticated user ID
            email: Email address
            phone: Phone number

        Returns:
            List of sessions that could potentially be merged
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
        filters = [ChatSession.created_at > cutoff]

        conditions = []
        if user_id:
            conditions.append(ChatSession.user_id == user_id)
        if email:
            conditions.append(ChatSession.contact_email == email)
        if phone:
            normalized_phone = self._normalize_phone(phone)
            conditions.append(ChatSession.contact_phone == normalized_phone)

        if not conditions:
            return []

        sessions = self.db.query(ChatSession).filter(
            and_(*filters),
            or_(*conditions)
        ).order_by(ChatSession.created_at.desc()).all()

        return sessions

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for consistent matching"""
        if not phone:
            return ""
        # Remove all non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        # Add US country code if not present
        if len(digits) == 10:
            digits = '1' + digits
        return digits

    def get_session_context_summary(self, session: ChatSession) -> Dict[str, Any]:
        """
        Generate a summary of session context for returning users.
        Used for continuity messaging.
        """
        signals = session.intent_signals or []
        signal_types = {s.get('signal') for s in signals}

        context_parts = []
        if 'property' in signal_types:
            prop = next((s for s in signals if s.get('signal') == 'property'), {})
            context_parts.append(f"property type ({prop.get('value', 'identified')})")
        if 'price' in signal_types:
            price = next((s for s in signals if s.get('signal') == 'price'), {})
            context_parts.append(f"budget ({price.get('value', 'discussed')})")
        if 'timeline' in signal_types:
            timeline = next((s for s in signals if s.get('signal') == 'timeline'), {})
            context_parts.append(f"timeline ({timeline.get('value', 'established')})")
        if 'loan_type' in signal_types:
            loan = next((s for s in signals if s.get('signal') == 'loan_type'), {})
            context_parts.append(f"loan type ({loan.get('value', 'explored')})")

        return {
            "session_id": str(session.id),
            "turn_count": session.turn_count,
            "current_phase": session.current_phase,
            "intent_score": session.intent_score,
            "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
            "known_context": context_parts,
            "context_summary": ", ".join(context_parts) if context_parts else "early exploration",
            "has_contact_info": bool(session.contact_name or session.contact_email or session.contact_phone),
            "cta_history": {
                "offered": session.cta_offered,
                "accepted": session.cta_accepted,
                "declined_count": session.cta_declined_count,
            }
        }
