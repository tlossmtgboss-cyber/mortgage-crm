"""
Event Service for Acquisition Engine
Handles event ingestion, processing, and trigger execution
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.acquisition_engine.event_models import AcquisitionEvent, EventType, EventSource
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature

logger = logging.getLogger(__name__)


class EventService:
    """
    Service for processing acquisition events.

    Responsibilities:
    - Event ingestion and validation
    - Identity linking (anonymous → known)
    - Trigger evaluation and execution
    - Event querying for temperature calculation
    """

    def __init__(self, db: Session):
        self.db = db

    def ingest_event(
        self,
        organization_id: int,
        event_type: str,
        event_payload: Dict[str, Any] = None,
        lead_id: Optional[int] = None,
        anonymous_visitor_id: Optional[str] = None,
        campaign_instance_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source: Optional[str] = None,
        utm_params: Optional[Dict[str, str]] = None,
        user_context: Optional[Dict[str, str]] = None,
        geo_context: Optional[Dict[str, str]] = None,
    ) -> AcquisitionEvent:
        """
        Ingest a new acquisition event.

        Args:
            organization_id: Organization ID
            event_type: Type of event (EventType enum value)
            event_payload: Event-specific data
            lead_id: Lead ID if known
            anonymous_visitor_id: Anonymous visitor ID (cookie/fingerprint)
            campaign_instance_id: Campaign that sourced this event
            session_id: Browser session ID
            source: Event source (funnel, sms, email, etc.)
            utm_params: UTM parameters for attribution
            user_context: Device/browser info
            geo_context: Geographic info

        Returns:
            Created AcquisitionEvent
        """
        # Create event
        event = AcquisitionEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            event_type=event_type,
            event_payload=event_payload or {},
            lead_id=lead_id,
            anonymous_visitor_id=anonymous_visitor_id,
            campaign_instance_id=uuid.UUID(campaign_instance_id) if campaign_instance_id else None,
            session_id=session_id,
            event_source=source,
            event_timestamp=datetime.now(timezone.utc),
        )

        # Add UTM parameters
        if utm_params:
            event.utm_source = utm_params.get('utm_source')
            event.utm_medium = utm_params.get('utm_medium')
            event.utm_campaign = utm_params.get('utm_campaign')
            event.utm_term = utm_params.get('utm_term')
            event.utm_content = utm_params.get('utm_content')

        # Add user context
        if user_context:
            event.user_agent = user_context.get('user_agent')
            event.device_type = user_context.get('device_type')
            event.browser = user_context.get('browser')
            event.os = user_context.get('os')

        # Add geo context
        if geo_context:
            event.ip_address = geo_context.get('ip_address')
            event.geo_country = geo_context.get('country')
            event.geo_state = geo_context.get('state')
            event.geo_city = geo_context.get('city')
            event.geo_zip = geo_context.get('zip')

        # Check if this is a first touch
        if lead_id:
            existing = self.db.query(AcquisitionEvent).filter(
                AcquisitionEvent.lead_id == lead_id
            ).first()
            event.first_touch = existing is None

        # Check if conversion event
        event.conversion_event = event.is_conversion_event

        # Calculate temperature impact
        event.temperature_impact = self._calculate_temperature_impact(event_type)

        # Save event
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Ingested event: {event_type} for lead={lead_id} org={organization_id}")

        # Process triggers asynchronously (in production, use background task)
        self._process_triggers(event)

        return event

    def _calculate_temperature_impact(self, event_type: str) -> int:
        """Calculate temperature point impact for an event type."""
        # Hot signals: 20-40 points
        hot_impacts = {
            EventType.MEETING_BOOKED.value: 40,
            EventType.APPLICATION_STARTED.value: 35,
            EventType.APPLICATION_COMPLETED.value: 40,
            EventType.FORM_SUBMITTED.value: 30,
            EventType.CALLBACK_REQUESTED.value: 35,
            EventType.CHAT_INITIATED.value: 25,
            EventType.VIDEO_WATCHED_75_PLUS.value: 25,
            EventType.CALCULATOR_COMPLETED.value: 20,
            EventType.DOCUMENT_UPLOADED.value: 25,
        }

        # Warm signals: 5-15 points
        warm_impacts = {
            EventType.PRICING_PAGE_VIEW.value: 10,
            EventType.CALCULATOR_STARTED.value: 8,
            EventType.QUIZ_STARTED.value: 8,
            EventType.QUIZ_COMPLETED.value: 15,
            EventType.VIDEO_WATCHED_25_PLUS.value: 5,
            EventType.VIDEO_WATCHED_50_PLUS.value: 10,
            EventType.FAQ_VIEWED.value: 5,
            EventType.BLOG_READ.value: 5,
            EventType.EMAIL_LINK_CLICKED.value: 8,
            EventType.SMS_REPLIED.value: 15,
            EventType.MULTIPLE_PAGE_VIEWS.value: 5,
        }

        # Cold signals: 1-3 points
        cold_impacts = {
            EventType.PAGE_VIEW.value: 1,
            EventType.FUNNEL_VISIT.value: 2,
            EventType.EMAIL_OPENED.value: 2,
            EventType.AD_CLICK.value: 3,
        }

        return (
            hot_impacts.get(event_type) or
            warm_impacts.get(event_type) or
            cold_impacts.get(event_type) or
            0
        )

    def _process_triggers(self, event: AcquisitionEvent):
        """
        Process triggers based on event type.
        Dispatches to the conversion orchestrator for processing.
        """
        triggered_actions = []

        # Hot lead triggers - dispatch to speed-to-lead
        if event.is_hot_signal and event.lead_id:
            triggered_actions.append({
                "action": "speed_to_lead",
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"Hot lead trigger: lead_id={event.lead_id}")

            # Dispatch to conversion orchestrator (runs in background)
            try:
                import asyncio
                from services.acquisition_engine.conversion_orchestrator import ConversionOrchestrator

                orchestrator = ConversionOrchestrator(self.db)

                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule as task if loop is already running
                        asyncio.create_task(orchestrator.process_event(event))
                    else:
                        # Run directly if no loop
                        loop.run_until_complete(orchestrator.process_event(event))
                except RuntimeError:
                    # No event loop - create one
                    asyncio.run(orchestrator.process_event(event))

                triggered_actions[-1]["dispatched"] = True
            except Exception as e:
                logger.error(f"Failed to dispatch to conversion orchestrator: {e}")
                triggered_actions[-1]["error"] = str(e)

        # Update event with triggered actions
        event.triggered_actions = triggered_actions
        event.processed_at = datetime.now(timezone.utc)
        self.db.commit()

    def link_identity(
        self,
        organization_id: int,
        anonymous_visitor_id: str,
        lead_id: int,
    ) -> int:
        """
        Link anonymous visitor events to a known lead.

        When a visitor identifies themselves (form submission, login),
        update all their anonymous events to be associated with the lead.

        Returns:
            Number of events linked
        """
        events = self.db.query(AcquisitionEvent).filter(
            and_(
                AcquisitionEvent.organization_id == organization_id,
                AcquisitionEvent.anonymous_visitor_id == anonymous_visitor_id,
                AcquisitionEvent.lead_id.is_(None),
            )
        ).all()

        for event in events:
            event.lead_id = lead_id
            event.identity_linked_at = datetime.now(timezone.utc)
            event.identity_linked_from = "visitor_identification"

        self.db.commit()

        logger.info(f"Linked {len(events)} events for visitor={anonymous_visitor_id} to lead={lead_id}")
        return len(events)

    def get_lead_events(
        self,
        lead_id: int,
        limit: int = 100,
        event_types: Optional[List[str]] = None,
        since: Optional[datetime] = None,
    ) -> List[AcquisitionEvent]:
        """Get events for a specific lead."""
        query = self.db.query(AcquisitionEvent).filter(
            AcquisitionEvent.lead_id == lead_id
        )

        if event_types:
            query = query.filter(AcquisitionEvent.event_type.in_(event_types))

        if since:
            query = query.filter(AcquisitionEvent.event_timestamp >= since)

        return query.order_by(AcquisitionEvent.event_timestamp.desc()).limit(limit).all()

    def get_campaign_events(
        self,
        campaign_instance_id: str,
        limit: int = 1000,
        event_types: Optional[List[str]] = None,
    ) -> List[AcquisitionEvent]:
        """Get events for a campaign."""
        query = self.db.query(AcquisitionEvent).filter(
            AcquisitionEvent.campaign_instance_id == uuid.UUID(campaign_instance_id)
        )

        if event_types:
            query = query.filter(AcquisitionEvent.event_type.in_(event_types))

        return query.order_by(AcquisitionEvent.event_timestamp.desc()).limit(limit).all()

    def get_hot_signals_count(
        self,
        lead_id: int,
        days: int = 7,
    ) -> int:
        """Count hot signals for a lead in the given period."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        hot_event_types = [
            EventType.MEETING_BOOKED.value,
            EventType.APPLICATION_STARTED.value,
            EventType.APPLICATION_COMPLETED.value,
            EventType.FORM_SUBMITTED.value,
            EventType.CALLBACK_REQUESTED.value,
            EventType.CHAT_INITIATED.value,
            EventType.VIDEO_WATCHED_75_PLUS.value,
            EventType.CALCULATOR_COMPLETED.value,
            EventType.DOCUMENT_UPLOADED.value,
        ]

        return self.db.query(AcquisitionEvent).filter(
            and_(
                AcquisitionEvent.lead_id == lead_id,
                AcquisitionEvent.event_type.in_(hot_event_types),
                AcquisitionEvent.event_timestamp >= since,
            )
        ).count()

    def get_session_count(
        self,
        lead_id: int,
        anonymous_visitor_id: Optional[str] = None,
    ) -> int:
        """Count unique sessions for a lead or visitor."""
        if lead_id:
            query = self.db.query(func.count(func.distinct(AcquisitionEvent.session_id))).filter(
                AcquisitionEvent.lead_id == lead_id
            )
        elif anonymous_visitor_id:
            query = self.db.query(func.count(func.distinct(AcquisitionEvent.session_id))).filter(
                AcquisitionEvent.anonymous_visitor_id == anonymous_visitor_id
            )
        else:
            return 0

        return query.scalar() or 0

    def get_event_summary(
        self,
        lead_id: int,
    ) -> Dict[str, Any]:
        """Get summary of events for a lead."""
        events = self.get_lead_events(lead_id, limit=1000)

        if not events:
            return {
                "total_events": 0,
                "hot_signals": 0,
                "warm_signals": 0,
                "cold_signals": 0,
                "sessions": 0,
                "first_seen": None,
                "last_seen": None,
            }

        hot_count = sum(1 for e in events if e.is_hot_signal)
        warm_count = sum(1 for e in events if e.is_warm_signal)
        cold_count = len(events) - hot_count - warm_count

        return {
            "total_events": len(events),
            "hot_signals": hot_count,
            "warm_signals": warm_count,
            "cold_signals": cold_count,
            "sessions": self.get_session_count(lead_id),
            "first_seen": min(e.event_timestamp for e in events).isoformat() if events else None,
            "last_seen": max(e.event_timestamp for e in events).isoformat() if events else None,
            "last_event_type": events[0].event_type if events else None,
        }
