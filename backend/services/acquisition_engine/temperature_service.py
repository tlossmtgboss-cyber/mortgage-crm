"""
Temperature Service for Acquisition Engine
Deterministic lead scoring based on behavioral events
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.acquisition_engine.event_models import AcquisitionEvent, EventType
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature

logger = logging.getLogger(__name__)


class TemperatureService:
    """
    Service for calculating and managing lead temperatures.

    Temperature is calculated deterministically based on:
    - Engagement score: page views, content consumption
    - Intent score: explicit intent signals
    - Recency score: time since last engagement
    - Frequency score: number of sessions
    - Profile score: lead profile completeness

    Temperature levels:
    - HOT: Explicit intent (meeting booked, form submitted, 75%+ video)
    - WARM: Educational engagement (calculator, quiz, pricing)
    - REPEAT: Multi-session visitor (3+ sessions)
    - COLD: First touch, minimal engagement
    """

    # Score weights
    WEIGHTS = {
        'engagement': 0.15,
        'intent': 0.35,
        'recency': 0.25,
        'frequency': 0.15,
        'profile': 0.10,
    }

    # Temperature thresholds
    HOT_THRESHOLD = 70
    WARM_THRESHOLD = 40

    def __init__(self, db: Session):
        self.db = db

    def calculate_temperature(
        self,
        lead_id: int,
        campaign_instance_id: Optional[str] = None,
    ) -> LeadTemperature:
        """
        Calculate or update temperature for a lead.

        This is the main entry point for temperature calculation.
        Called after new events are ingested.

        Returns:
            Updated LeadTemperature record
        """
        # Get or create temperature record
        temp_record = self.db.query(LeadTemperature).filter(
            LeadTemperature.lead_id == lead_id
        ).first()

        if not temp_record:
            temp_record = LeadTemperature(
                id=uuid.uuid4(),
                lead_id=lead_id,
                campaign_instance_id=uuid.UUID(campaign_instance_id) if campaign_instance_id else None,
                temperature=Temperature.COLD.value,
                score=0,
                first_seen_at=datetime.now(timezone.utc),
            )
            self.db.add(temp_record)

        # Get events for calculation
        events = self._get_events_for_scoring(lead_id)

        if not events:
            temp_record.last_calculated_at = datetime.now(timezone.utc)
            self.db.commit()
            return temp_record

        # Calculate score components
        engagement_score = self._calculate_engagement_score(events)
        intent_score = self._calculate_intent_score(events)
        recency_score = self._calculate_recency_score(events)
        frequency_score = self._calculate_frequency_score(lead_id, events)
        profile_score = self._calculate_profile_score(lead_id)

        # Update component scores
        temp_record.engagement_score = engagement_score
        temp_record.intent_score = intent_score
        temp_record.recency_score = recency_score
        temp_record.frequency_score = frequency_score
        temp_record.profile_score = profile_score

        # Calculate weighted total score
        weighted_score = (
            engagement_score * self.WEIGHTS['engagement'] +
            intent_score * self.WEIGHTS['intent'] +
            recency_score * self.WEIGHTS['recency'] +
            frequency_score * self.WEIGHTS['frequency'] +
            profile_score * self.WEIGHTS['profile']
        )
        temp_record.score = min(100, max(0, int(weighted_score)))

        # Update session/event counts
        temp_record.total_events = len(events)
        temp_record.total_page_views = sum(1 for e in events if e.event_type == EventType.PAGE_VIEW.value)
        temp_record.first_seen_at = min(e.event_timestamp for e in events)
        temp_record.last_seen_at = max(e.event_timestamp for e in events)

        # Calculate days since last activity
        temp_record.days_since_last_activity = (datetime.now(timezone.utc) - temp_record.last_seen_at).days

        # Track hot/warm signals
        hot_events = [e for e in events if e.is_hot_signal]
        warm_events = [e for e in events if e.is_warm_signal]

        if hot_events:
            latest_hot = max(hot_events, key=lambda e: e.event_timestamp)
            temp_record.last_hot_signal = latest_hot.event_type
            temp_record.last_hot_signal_at = latest_hot.event_timestamp

        if warm_events:
            latest_warm = max(warm_events, key=lambda e: e.event_timestamp)
            temp_record.last_warm_signal = latest_warm.event_type
            temp_record.last_warm_signal_at = latest_warm.event_timestamp

        # Determine temperature level
        old_temperature = temp_record.temperature
        new_temperature = self._determine_temperature(temp_record)

        if old_temperature != new_temperature:
            temp_record.previous_temperature = old_temperature
            temp_record.temperature_changed_at = datetime.now(timezone.utc)

        temp_record.temperature = new_temperature
        temp_record.last_calculated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(temp_record)

        logger.info(f"Calculated temperature for lead={lead_id}: {new_temperature} (score={temp_record.score})")

        return temp_record

    def _get_events_for_scoring(
        self,
        lead_id: int,
        days: int = 90,
    ) -> list:
        """Get events for temperature scoring."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        return self.db.query(AcquisitionEvent).filter(
            and_(
                AcquisitionEvent.lead_id == lead_id,
                AcquisitionEvent.event_timestamp >= since,
            )
        ).order_by(AcquisitionEvent.event_timestamp.desc()).all()

    def _calculate_engagement_score(self, events: list) -> int:
        """
        Calculate engagement score (0-100).

        Based on content consumption and time on site.
        """
        score = 0

        # Page views: 1 point each, max 20
        page_views = sum(1 for e in events if e.event_type == EventType.PAGE_VIEW.value)
        score += min(20, page_views)

        # Blog reads: 3 points each, max 15
        blog_reads = sum(1 for e in events if e.event_type == EventType.BLOG_READ.value)
        score += min(15, blog_reads * 3)

        # Video watching
        video_25 = sum(1 for e in events if e.event_type == EventType.VIDEO_WATCHED_25_PLUS.value)
        video_50 = sum(1 for e in events if e.event_type == EventType.VIDEO_WATCHED_50_PLUS.value)
        video_75 = sum(1 for e in events if e.event_type == EventType.VIDEO_WATCHED_75_PLUS.value)

        score += min(25, video_25 * 5 + video_50 * 10 + video_75 * 15)

        # FAQ views: 5 points each, max 15
        faq_views = sum(1 for e in events if e.event_type == EventType.FAQ_VIEWED.value)
        score += min(15, faq_views * 5)

        # Email/SMS engagement
        email_clicks = sum(1 for e in events if e.event_type == EventType.EMAIL_LINK_CLICKED.value)
        sms_replies = sum(1 for e in events if e.event_type == EventType.SMS_REPLIED.value)
        score += min(25, email_clicks * 5 + sms_replies * 10)

        return min(100, score)

    def _calculate_intent_score(self, events: list) -> int:
        """
        Calculate intent score (0-100).

        Based on explicit intent signals.
        """
        score = 0

        # Intent signal weights
        intent_weights = {
            EventType.MEETING_BOOKED.value: 40,
            EventType.APPLICATION_STARTED.value: 35,
            EventType.APPLICATION_COMPLETED.value: 50,
            EventType.FORM_SUBMITTED.value: 30,
            EventType.CALLBACK_REQUESTED.value: 35,
            EventType.CHAT_INITIATED.value: 25,
            EventType.CALCULATOR_COMPLETED.value: 20,
            EventType.DOCUMENT_UPLOADED.value: 25,
            EventType.PRICING_PAGE_VIEW.value: 10,
            EventType.CALCULATOR_STARTED.value: 8,
            EventType.QUIZ_COMPLETED.value: 15,
        }

        for event in events:
            if event.event_type in intent_weights:
                score += intent_weights[event.event_type]

        return min(100, score)

    def _calculate_recency_score(self, events: list) -> int:
        """
        Calculate recency score (0-100).

        Based on time since last engagement.
        Decays over time without activity.
        """
        if not events:
            return 0

        last_event = max(events, key=lambda e: e.event_timestamp)
        days_since = (datetime.now(timezone.utc) - last_event.event_timestamp).days

        # Recency decay curve
        if days_since <= 1:
            return 100
        elif days_since <= 2:
            return 90
        elif days_since <= 3:
            return 80
        elif days_since <= 7:
            return 60
        elif days_since <= 14:
            return 40
        elif days_since <= 30:
            return 20
        elif days_since <= 60:
            return 10
        else:
            return 5

    def _calculate_frequency_score(self, lead_id: int, events: list) -> int:
        """
        Calculate frequency score (0-100).

        Based on number of unique sessions.
        """
        if not events:
            return 0

        # Count unique sessions
        sessions = set(e.session_id for e in events if e.session_id)
        session_count = len(sessions) if sessions else 1

        # Frequency scoring
        if session_count >= 10:
            return 100
        elif session_count >= 7:
            return 90
        elif session_count >= 5:
            return 80
        elif session_count >= 4:
            return 70
        elif session_count >= 3:
            return 60
        elif session_count >= 2:
            return 40
        else:
            return 20

    def _calculate_profile_score(self, lead_id: int) -> int:
        """
        Calculate profile score (0-100).

        Based on lead profile completeness.
        """
        try:
            # Import Lead model
            from database.models import Lead

            lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return 0

            # Define fields to check with their weights
            # Higher weight = more important for qualification
            field_weights = {
                # Contact info (20 points total)
                'email': 10,
                'phone': 10,
                # Financial info (35 points total)
                'credit_score': 15,
                'annual_income': 10,
                'employment_status': 10,
                # Property info (20 points total)
                'property_type': 10,
                'property_value': 10,
                # Loan info (25 points total)
                'loan_type': 10,
                'loan_amount': 10,
                'preapproval_amount': 5,
            }

            score = 0
            for field, weight in field_weights.items():
                value = getattr(lead, field, None)
                if value is not None and value != '' and value != 0:
                    score += weight

            return min(score, 100)

        except Exception as e:
            logger.warning(f"Error calculating profile score for lead {lead_id}: {e}")
            return 50  # Default score on error

    def _determine_temperature(self, temp_record: LeadTemperature) -> str:
        """
        Determine temperature level from scores and signals.

        Priority:
        1. Recent hot signals → HOT
        2. Multi-session visitor → REPEAT
        3. Score-based thresholds
        """
        days_since = temp_record.days_since_last_activity or 0

        # Recent hot signal overrides score
        if temp_record.last_hot_signal and temp_record.last_hot_signal_at:
            hot_days = (datetime.now(timezone.utc) - temp_record.last_hot_signal_at).days
            if hot_days <= 3:
                return Temperature.HOT.value

        # Repeat visitor detection (3+ sessions, active in last 7 days)
        if (temp_record.total_sessions or 0) >= 3 and days_since <= 7:
            return Temperature.REPEAT.value

        # Score-based determination
        score = temp_record.score or 0

        if score >= self.HOT_THRESHOLD:
            return Temperature.HOT.value
        elif score >= self.WARM_THRESHOLD:
            return Temperature.WARM.value
        else:
            return Temperature.COLD.value

    def get_temperature(self, lead_id: int) -> Optional[LeadTemperature]:
        """Get current temperature for a lead."""
        return self.db.query(LeadTemperature).filter(
            LeadTemperature.lead_id == lead_id
        ).first()

    def get_hot_leads(
        self,
        organization_id: Optional[int] = None,
        campaign_instance_id: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """Get hot leads, optionally filtered by org or campaign."""
        query = self.db.query(LeadTemperature).filter(
            LeadTemperature.temperature == Temperature.HOT.value
        )

        if campaign_instance_id:
            query = query.filter(
                LeadTemperature.campaign_instance_id == uuid.UUID(campaign_instance_id)
            )

        return query.order_by(LeadTemperature.score.desc()).limit(limit).all()

    def get_temperature_summary(
        self,
        campaign_instance_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get summary of temperature distribution."""
        query = self.db.query(
            LeadTemperature.temperature,
            func.count(LeadTemperature.id).label('count'),
            func.avg(LeadTemperature.score).label('avg_score'),
        ).group_by(LeadTemperature.temperature)

        if campaign_instance_id:
            query = query.filter(
                LeadTemperature.campaign_instance_id == uuid.UUID(campaign_instance_id)
            )

        results = query.all()

        summary = {
            "total": 0,
            "by_temperature": {},
        }

        for temp, count, avg_score in results:
            summary["by_temperature"][temp] = {
                "count": count,
                "avg_score": round(avg_score or 0, 1),
            }
            summary["total"] += count

        return summary

    def recalculate_all(
        self,
        campaign_instance_id: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        """
        Recalculate temperatures for all leads in a campaign.

        Useful for bulk recalculation after rule changes.

        Returns:
            Number of leads recalculated
        """
        query = self.db.query(LeadTemperature)

        if campaign_instance_id:
            query = query.filter(
                LeadTemperature.campaign_instance_id == uuid.UUID(campaign_instance_id)
            )

        temperatures = query.all()
        count = 0

        for temp in temperatures:
            self.calculate_temperature(
                lead_id=temp.lead_id,
                campaign_instance_id=str(temp.campaign_instance_id) if temp.campaign_instance_id else None,
            )
            count += 1

            if count % batch_size == 0:
                logger.info(f"Recalculated {count} temperatures...")

        logger.info(f"Completed recalculation of {count} lead temperatures")
        return count
