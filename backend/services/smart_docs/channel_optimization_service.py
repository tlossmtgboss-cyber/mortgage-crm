"""
Smart Docs Channel Optimization Service

Data-driven channel selection for borrower document collection outreach.
Analyzes historical response patterns across email, SMS, phone, and portal
to recommend the channel and time most likely to yield a document upload.

Key capabilities:
  - Per-borrower channel preference learning from outcome data
  - Channel scoring model (email open/click, SMS response, call answer, portal login)
  - Recommendation engine with TCPA consent + DNC gating
  - Channel fatigue detection (excessive contacts => reduce frequency)
  - Cross-channel coordination (prevent same-day multi-channel bombardment)
  - A/B test framework for channel strategy experiments
  - Channel performance analytics for dashboards
  - Demographic-based defaults when no history is available
  - Time zone awareness for scheduling
  - Blackout rules (no outreach during closing week, etc.)

Usage:
    from services.smart_docs.channel_optimization_service import (
        ChannelOptimizationService,
        ChannelRecommendation,
        FatigueStatus,
    )

    service = ChannelOptimizationService(db=db, org_id=42)
    rec = await service.get_optimal_channel(borrower_id=100, context="document_reminder")
    # rec.channel == "sms", rec.optimal_time == "10:00", rec.confidence == 0.82

    await service.record_channel_outcome(
        borrower_id=100,
        channel="sms",
        outcome="document_uploaded",
        response_time_minutes=45,
    )
"""

import enum
import hashlib
import logging
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Try pytz first, fall back to zoneinfo (same pattern as tcpa_compliance_service.py)
try:
    import pytz

    _HAS_PYTZ = True
except ImportError:
    from zoneinfo import ZoneInfo

    _HAS_PYTZ = False


# =============================================================================
# ENUMS
# =============================================================================


class Channel(str, enum.Enum):
    """Supported outreach channels."""
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    PORTAL = "portal"


class OutcomeType(str, enum.Enum):
    """Possible outcomes after a channel contact."""
    DOCUMENT_UPLOADED = "document_uploaded"
    RESPONDED = "responded"
    OPENED = "opened"
    CLICKED = "clicked"
    ANSWERED_CALL = "answered_call"
    VOICEMAIL_CALLBACK = "voicemail_callback"
    PORTAL_LOGIN = "portal_login"
    NO_RESPONSE = "no_response"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    OPTED_OUT = "opted_out"


class FatigueLevel(str, enum.Enum):
    """Contact fatigue severity."""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ABTestStatus(str, enum.Enum):
    """A/B test lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# =============================================================================
# RESULT DATACLASSES
# =============================================================================


@dataclass
class ChannelScore:
    """Score components for a single channel."""
    channel: str
    total_score: float  # 0-100
    open_rate: float = 0.0
    click_rate: float = 0.0
    response_rate: float = 0.0
    response_time_avg_minutes: float = 0.0
    upload_rate: float = 0.0
    delivery_rate: float = 0.0
    answer_rate: float = 0.0  # phone only
    callback_rate: float = 0.0  # phone only
    login_frequency: float = 0.0  # portal only
    sample_count: int = 0


@dataclass
class ChannelRecommendation:
    """Result of the channel optimization recommendation engine."""
    channel: str
    optimal_time: str  # HH:MM format
    optimal_day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    confidence: float = 0.0  # 0.0-1.0
    scores: Dict[str, ChannelScore] = field(default_factory=dict)
    fallback_channel: Optional[str] = None
    blocked_channels: Dict[str, str] = field(default_factory=dict)  # channel -> reason
    reasoning: str = ""
    ab_test_variant: Optional[str] = None  # if borrower is in an A/B test

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "channel": self.channel,
            "optimal_time": self.optimal_time,
            "optimal_day_of_week": self.optimal_day_of_week,
            "confidence": round(self.confidence, 3),
            "fallback_channel": self.fallback_channel,
            "blocked_channels": self.blocked_channels,
            "reasoning": self.reasoning,
            "ab_test_variant": self.ab_test_variant,
            "scores": {
                ch: {
                    "total_score": round(s.total_score, 2),
                    "response_rate": round(s.response_rate, 3),
                    "upload_rate": round(s.upload_rate, 3),
                    "sample_count": s.sample_count,
                }
                for ch, s in self.scores.items()
            },
        }


@dataclass
class FatigueStatus:
    """Result of fatigue detection for a borrower."""
    borrower_id: int
    fatigue_level: str  # FatigueLevel value
    total_contacts_7d: int = 0
    total_contacts_30d: int = 0
    contacts_by_channel_7d: Dict[str, int] = field(default_factory=dict)
    days_since_last_contact: Optional[int] = None
    recommended_cooldown_hours: int = 0
    should_reduce_frequency: bool = False
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "borrower_id": self.borrower_id,
            "fatigue_level": self.fatigue_level,
            "total_contacts_7d": self.total_contacts_7d,
            "total_contacts_30d": self.total_contacts_30d,
            "contacts_by_channel_7d": self.contacts_by_channel_7d,
            "days_since_last_contact": self.days_since_last_contact,
            "recommended_cooldown_hours": self.recommended_cooldown_hours,
            "should_reduce_frequency": self.should_reduce_frequency,
            "reasoning": self.reasoning,
        }


@dataclass
class ChannelAnalytics:
    """Aggregated channel performance analytics for dashboards."""
    org_id: int
    date_range_start: str
    date_range_end: str
    total_outreach_events: int = 0
    by_channel: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    avg_time_to_document_by_channel: Dict[str, float] = field(default_factory=dict)  # hours
    cost_per_collection_by_channel: Dict[str, float] = field(default_factory=dict)
    best_performing_channel: Optional[str] = None
    worst_performing_channel: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "date_range": {
                "start": self.date_range_start,
                "end": self.date_range_end,
            },
            "total_outreach_events": self.total_outreach_events,
            "by_channel": self.by_channel,
            "avg_time_to_document_by_channel": {
                ch: round(v, 1) for ch, v in self.avg_time_to_document_by_channel.items()
            },
            "cost_per_collection_by_channel": {
                ch: round(v, 2) for ch, v in self.cost_per_collection_by_channel.items()
            },
            "best_performing_channel": self.best_performing_channel,
            "worst_performing_channel": self.worst_performing_channel,
        }


# =============================================================================
# CONSTANTS
# =============================================================================

# Fatigue thresholds: contacts in past 7 days
_FATIGUE_THRESHOLDS = {
    FatigueLevel.NONE: (0, 2),      # 0-2 contacts
    FatigueLevel.LOW: (3, 4),       # 3-4 contacts
    FatigueLevel.MODERATE: (5, 6),  # 5-6 contacts
    FatigueLevel.HIGH: (7, 9),      # 7-9 contacts
    FatigueLevel.CRITICAL: (10, 999),  # 10+
}

# Cooldown hours by fatigue level
_FATIGUE_COOLDOWN_HOURS = {
    FatigueLevel.NONE: 0,
    FatigueLevel.LOW: 12,
    FatigueLevel.MODERATE: 24,
    FatigueLevel.HIGH: 48,
    FatigueLevel.CRITICAL: 96,
}

# Approximate cost per outreach (USD), used for cost-per-collection analytics
_CHANNEL_COST = {
    Channel.EMAIL: 0.003,   # ~$3/1000 via SendGrid/SES
    Channel.SMS: 0.015,     # ~$0.015/segment via Telnyx
    Channel.PHONE: 0.12,    # ~$0.12/minute average
    Channel.PORTAL: 0.0,    # no marginal cost
}

# Score weights for channel ranking (sum to 1.0)
_SCORE_WEIGHTS = {
    "upload_rate": 0.40,       # primary goal: did borrower upload a doc?
    "response_rate": 0.25,     # did they respond at all?
    "response_time": 0.15,     # how quickly did they respond?
    "delivery_rate": 0.10,     # was the message successfully delivered?
    "cost_efficiency": 0.10,   # cost per successful collection
}

# Demographic-based channel defaults (age brackets, when no history exists)
_DEMOGRAPHIC_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "18-34": {"primary": Channel.SMS, "secondary": Channel.EMAIL, "optimal_hour": 11},
    "35-49": {"primary": Channel.EMAIL, "secondary": Channel.SMS, "optimal_hour": 10},
    "50-64": {"primary": Channel.EMAIL, "secondary": Channel.PHONE, "optimal_hour": 9},
    "65+": {"primary": Channel.PHONE, "secondary": Channel.EMAIL, "optimal_hour": 10},
    "unknown": {"primary": Channel.EMAIL, "secondary": Channel.SMS, "optimal_hour": 10},
}

# Area-code-to-timezone (subset; full list in tcpa_compliance_service.py)
_AREA_CODE_TZ = {
    "201": "America/New_York", "212": "America/New_York", "312": "America/Chicago",
    "415": "America/Los_Angeles", "602": "America/Phoenix", "713": "America/Chicago",
    "808": "Pacific/Honolulu", "907": "America/Anchorage",
}

# Default timezone for scheduling
_DEFAULT_TIMEZONE = "America/New_York"

# Cross-channel coordination: minimum hours between contacts on different channels
_CROSS_CHANNEL_MIN_GAP_HOURS = 8

# Blackout: stages during which outreach should be suppressed
_BLACKOUT_STAGES = frozenset({
    "CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING", "FUNDED",
    "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY",
})

# Maximum contacts per day across all channels
_MAX_DAILY_CONTACTS_ALL_CHANNELS = 4


# =============================================================================
# SERVICE
# =============================================================================


class ChannelOptimizationService:
    """
    Data-driven channel optimization for document collection outreach.

    All methods enforce org_id isolation. The service integrates with the
    existing TCPA compliance and follow-up automation infrastructure.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
    """

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id

    # =========================================================================
    # 1. RECOMMENDATION ENGINE
    # =========================================================================

    async def get_optimal_channel(
        self,
        borrower_id: int,
        context: str = "document_reminder",
        loan_id: Optional[int] = None,
    ) -> ChannelRecommendation:
        """Recommend the best channel and time to contact a borrower.

        Decision flow:
        1. Check blackout rules (closing week, terminal stages)
        2. Load channel scores from historical outcome data
        3. If insufficient history, use demographic defaults
        4. Check TCPA consent + DNC for each candidate channel
        5. Check fatigue status to potentially suppress or downgrade
        6. Check cross-channel coordination (no same-day duplication)
        7. Apply A/B test override if borrower is in an active experiment
        8. Return top channel with time zone-aware optimal time

        Args:
            borrower_id: The borrower (lead) to optimize for.
            context: Outreach context (document_reminder, urgent, etc.).
            loan_id: Optional loan ID for stage-based blackout checks.

        Returns:
            ChannelRecommendation with channel, time, confidence, and reasoning.
        """
        blocked_channels: Dict[str, str] = {}
        reasoning_parts: List[str] = []

        # --- Blackout check ---
        if loan_id:
            blackout = self._check_blackout(loan_id)
            if blackout:
                return ChannelRecommendation(
                    channel="none",
                    optimal_time="",
                    confidence=1.0,
                    blocked_channels={"all": blackout},
                    reasoning=f"Blackout active: {blackout}",
                )

        # --- Score all channels ---
        scores = self._calculate_channel_scores(borrower_id)
        has_history = any(s.sample_count >= 3 for s in scores.values())

        # --- Demographic fallback ---
        if not has_history:
            demographic = self._get_demographic_bracket(borrower_id)
            defaults = _DEMOGRAPHIC_DEFAULTS.get(demographic, _DEMOGRAPHIC_DEFAULTS["unknown"])
            reasoning_parts.append(
                f"No sufficient history (demographic={demographic}); using defaults"
            )
            # Seed scores from defaults
            primary = defaults["primary"].value
            secondary = defaults["secondary"].value
            if primary not in scores:
                scores[primary] = ChannelScore(channel=primary, total_score=0.0)
            if secondary not in scores:
                scores[secondary] = ChannelScore(channel=secondary, total_score=0.0)
            scores[primary].total_score = max(scores[primary].total_score, 70.0)
            scores[secondary].total_score = max(scores[secondary].total_score, 50.0)
        else:
            reasoning_parts.append("Scored from historical outcome data")

        # --- TCPA / DNC gating ---
        borrower_phone = self._get_borrower_phone(borrower_id)
        consent_status = self._check_consent_all_channels(borrower_id, borrower_phone)
        for ch, reason in consent_status.items():
            if reason:
                blocked_channels[ch] = reason
                if ch in scores:
                    scores[ch].total_score = 0.0

        # --- Fatigue check ---
        fatigue = await self.detect_fatigue(borrower_id)
        if fatigue.fatigue_level in (FatigueLevel.HIGH.value, FatigueLevel.CRITICAL.value):
            reasoning_parts.append(
                f"Fatigue={fatigue.fatigue_level}; suppressing non-essential outreach"
            )
            if context not in ("urgent", "sla_breach"):
                return ChannelRecommendation(
                    channel="none",
                    optimal_time="",
                    confidence=0.95,
                    scores=scores,
                    blocked_channels={
                        **blocked_channels,
                        "all": f"Fatigue level {fatigue.fatigue_level}",
                    },
                    reasoning="; ".join(reasoning_parts),
                )
        elif fatigue.should_reduce_frequency:
            reasoning_parts.append(f"Fatigue={fatigue.fatigue_level}; reducing frequency")
            # Halve scores for channels already used today
            for ch, count in fatigue.contacts_by_channel_7d.items():
                if ch in scores and count > 2:
                    scores[ch].total_score *= 0.5

        # --- Cross-channel coordination ---
        recently_used = self._get_channels_used_today(borrower_id)
        for ch in recently_used:
            if ch in scores:
                blocked_channels[ch] = "Already contacted on this channel today"
                scores[ch].total_score = 0.0

        # --- A/B test override ---
        ab_variant = self._get_ab_test_variant(borrower_id, context)

        # --- Rank channels ---
        ranked = sorted(scores.values(), key=lambda s: s.total_score, reverse=True)
        eligible = [s for s in ranked if s.total_score > 0 and s.channel not in blocked_channels]

        if not eligible:
            return ChannelRecommendation(
                channel="none",
                optimal_time="",
                confidence=0.0,
                scores=scores,
                blocked_channels=blocked_channels,
                reasoning="All channels blocked or scored zero",
            )

        best = eligible[0]
        fallback = eligible[1] if len(eligible) > 1 else None

        # --- Apply A/B override if active ---
        if ab_variant and ab_variant in scores and ab_variant not in blocked_channels:
            reasoning_parts.append(f"A/B test override to channel={ab_variant}")
            best = scores[ab_variant]

        # --- Optimal time ---
        optimal_time, optimal_dow = self._get_optimal_contact_time(borrower_id, best.channel)

        # --- Confidence calculation ---
        confidence = self._calculate_confidence(best, has_history)

        return ChannelRecommendation(
            channel=best.channel,
            optimal_time=optimal_time,
            optimal_day_of_week=optimal_dow,
            confidence=confidence,
            scores=scores,
            fallback_channel=fallback.channel if fallback else None,
            blocked_channels=blocked_channels,
            reasoning="; ".join(reasoning_parts),
            ab_test_variant=ab_variant,
        )

    # =========================================================================
    # 2. OUTCOME RECORDING
    # =========================================================================

    async def record_channel_outcome(
        self,
        borrower_id: int,
        channel: str,
        outcome: str,
        response_time_minutes: Optional[float] = None,
        campaign_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record the outcome of a channel contact for future optimization.

        Writes to the document_followup_events table augmented with outcome
        data in the metadata JSON column, and updates channel_outcome_stats
        for fast aggregation.

        Args:
            borrower_id: The borrower contacted.
            channel: Channel used (email, sms, phone, portal).
            outcome: OutcomeType value string.
            response_time_minutes: Time from outreach to response, if applicable.
            campaign_id: Related follow-up campaign, if any.
            metadata: Additional context (template_used, ab_variant, etc.).
        """
        now = datetime.now(timezone.utc)
        outcome_data = {
            "optimization_outcome": outcome,
            "response_time_minutes": response_time_minutes,
            "recorded_at": now.isoformat(),
            **(metadata or {}),
        }

        # Insert into channel_outcome_log (lightweight table for analytics)
        self.db.execute(
            text("""
                INSERT INTO channel_outcome_log
                    (organization_id, borrower_id, channel, outcome, response_time_minutes,
                     campaign_id, metadata, created_at)
                VALUES
                    (:org_id, :borrower_id, :channel, :outcome, :response_time_minutes,
                     :campaign_id, CAST(:metadata AS jsonb), :created_at)
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "channel": channel,
                "outcome": outcome,
                "response_time_minutes": response_time_minutes,
                "campaign_id": campaign_id,
                "metadata": _json_dumps(outcome_data),
                "created_at": now,
            },
        )

        # Update running stats in channel_outcome_stats (upsert)
        is_success = outcome in (
            OutcomeType.DOCUMENT_UPLOADED.value,
            OutcomeType.RESPONDED.value,
            OutcomeType.ANSWERED_CALL.value,
            OutcomeType.VOICEMAIL_CALLBACK.value,
            OutcomeType.PORTAL_LOGIN.value,
        )
        is_upload = outcome == OutcomeType.DOCUMENT_UPLOADED.value

        self.db.execute(
            text("""
                INSERT INTO channel_outcome_stats
                    (organization_id, borrower_id, channel, total_contacts,
                     total_responses, total_uploads, total_response_time_minutes,
                     last_contact_at, last_outcome, updated_at)
                VALUES
                    (:org_id, :borrower_id, :channel, 1,
                     :is_response, :is_upload, COALESCE(:response_time, 0),
                     :now, :outcome, :now)
                ON CONFLICT (organization_id, borrower_id, channel)
                DO UPDATE SET
                    total_contacts = channel_outcome_stats.total_contacts + 1,
                    total_responses = channel_outcome_stats.total_responses + :is_response,
                    total_uploads = channel_outcome_stats.total_uploads + :is_upload,
                    total_response_time_minutes = channel_outcome_stats.total_response_time_minutes
                        + COALESCE(:response_time, 0),
                    last_contact_at = :now,
                    last_outcome = :outcome,
                    updated_at = :now
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "channel": channel,
                "is_response": 1 if is_success else 0,
                "is_upload": 1 if is_upload else 0,
                "response_time": response_time_minutes,
                "now": now,
                "outcome": outcome,
            },
        )

        self.db.flush()

        logger.info(
            "Channel outcome recorded: org=%d borrower=%d channel=%s outcome=%s",
            self.org_id, borrower_id, channel, outcome,
        )

    # =========================================================================
    # 3. CHANNEL ANALYTICS
    # =========================================================================

    async def get_channel_analytics(
        self,
        date_range_start: Optional[date] = None,
        date_range_end: Optional[date] = None,
    ) -> ChannelAnalytics:
        """Get channel performance analytics for the organization.

        Aggregates outcome data across all borrowers within the org for the
        specified date range.

        Args:
            date_range_start: Start date (default: 30 days ago).
            date_range_end: End date (default: today).

        Returns:
            ChannelAnalytics with per-channel metrics.
        """
        if date_range_start is None:
            date_range_start = date.today() - timedelta(days=30)
        if date_range_end is None:
            date_range_end = date.today()

        # Aggregate from channel_outcome_log
        rows = self.db.execute(
            text("""
                SELECT
                    channel,
                    COUNT(*) AS total_events,
                    COUNT(CASE WHEN outcome IN ('document_uploaded', 'responded',
                        'answered_call', 'voicemail_callback', 'portal_login')
                        THEN 1 END) AS total_responses,
                    COUNT(CASE WHEN outcome = 'document_uploaded' THEN 1 END) AS total_uploads,
                    COUNT(CASE WHEN outcome = 'bounced' THEN 1 END) AS total_bounced,
                    COUNT(CASE WHEN outcome = 'opened' THEN 1 END) AS total_opened,
                    COUNT(CASE WHEN outcome = 'clicked' THEN 1 END) AS total_clicked,
                    AVG(CASE WHEN outcome = 'document_uploaded'
                        THEN response_time_minutes END) AS avg_upload_time_minutes,
                    AVG(response_time_minutes) FILTER (WHERE response_time_minutes IS NOT NULL)
                        AS avg_response_time_minutes
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND created_at >= :start_date
                    AND created_at < :end_date + INTERVAL '1 day'
                GROUP BY channel
                ORDER BY total_events DESC
            """),
            {
                "org_id": self.org_id,
                "start_date": date_range_start,
                "end_date": date_range_end,
            },
        ).fetchall()

        columns = [
            "channel", "total_events", "total_responses", "total_uploads",
            "total_bounced", "total_opened", "total_clicked",
            "avg_upload_time_minutes", "avg_response_time_minutes",
        ]

        analytics = ChannelAnalytics(
            org_id=self.org_id,
            date_range_start=date_range_start.isoformat(),
            date_range_end=date_range_end.isoformat(),
        )

        best_rate = -1.0
        worst_rate = 2.0
        best_ch = None
        worst_ch = None

        for row in rows:
            r = dict(zip(columns, row))
            ch = r["channel"]
            total = r["total_events"] or 0
            responses = r["total_responses"] or 0
            uploads = r["total_uploads"] or 0
            bounced = r["total_bounced"] or 0
            opened = r["total_opened"] or 0
            clicked = r["total_clicked"] or 0

            response_rate = responses / total if total > 0 else 0.0
            upload_rate = uploads / total if total > 0 else 0.0
            delivery_rate = 1.0 - (bounced / total) if total > 0 else 1.0

            analytics.total_outreach_events += total

            cost = _CHANNEL_COST.get(Channel(ch), 0.01) if ch in Channel.__members__.values() else 0.01
            cost_per_collection = (cost * total) / uploads if uploads > 0 else 0.0

            analytics.by_channel[ch] = {
                "total_events": total,
                "total_responses": responses,
                "total_uploads": uploads,
                "response_rate": round(response_rate, 4),
                "upload_rate": round(upload_rate, 4),
                "delivery_rate": round(delivery_rate, 4),
                "open_rate": round(opened / total, 4) if total > 0 else 0.0,
                "click_rate": round(clicked / total, 4) if total > 0 else 0.0,
                "avg_response_time_minutes": round(float(r["avg_response_time_minutes"] or 0), 1),
            }

            if r["avg_upload_time_minutes"] is not None:
                analytics.avg_time_to_document_by_channel[ch] = float(
                    r["avg_upload_time_minutes"]
                ) / 60.0  # convert to hours

            analytics.cost_per_collection_by_channel[ch] = cost_per_collection

            if upload_rate > best_rate:
                best_rate = upload_rate
                best_ch = ch
            if upload_rate < worst_rate:
                worst_rate = upload_rate
                worst_ch = ch

        analytics.best_performing_channel = best_ch
        analytics.worst_performing_channel = worst_ch

        return analytics

    # =========================================================================
    # 4. FATIGUE DETECTION
    # =========================================================================

    async def detect_fatigue(self, borrower_id: int) -> FatigueStatus:
        """Detect channel fatigue for a borrower.

        Examines recent contact frequency across all channels and determines
        whether the borrower is being over-contacted. Returns a fatigue level
        and a recommended cooldown period.

        Args:
            borrower_id: The borrower to evaluate.

        Returns:
            FatigueStatus with fatigue level and recommendations.
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # Count contacts in the last 7 and 30 days from channel_outcome_log
        rows = self.db.execute(
            text("""
                SELECT
                    channel,
                    COUNT(*) AS count_7d,
                    COUNT(*) FILTER (WHERE created_at >= :thirty_days_ago) AS count_30d,
                    MAX(created_at) AS last_contact_at
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND created_at >= :seven_days_ago
                GROUP BY channel

                UNION ALL

                SELECT
                    'all_30d' AS channel,
                    0 AS count_7d,
                    COUNT(*) AS count_30d,
                    MAX(created_at) AS last_contact_at
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND created_at >= :thirty_days_ago
                    AND created_at < :seven_days_ago
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "seven_days_ago": seven_days_ago,
                "thirty_days_ago": thirty_days_ago,
            },
        ).fetchall()

        contacts_7d_by_channel: Dict[str, int] = {}
        total_7d = 0
        total_30d = 0
        last_contact: Optional[datetime] = None

        for row in rows:
            ch, count_7d, count_30d, last_at = row
            if ch == "all_30d":
                total_30d += count_30d or 0
                continue
            contacts_7d_by_channel[ch] = count_7d or 0
            total_7d += count_7d or 0
            total_30d += count_7d or 0  # 7d is subset of 30d
            if last_at is not None:
                if last_contact is None or last_at > last_contact:
                    last_contact = last_at

        # Determine fatigue level
        fatigue_level = FatigueLevel.NONE
        for level, (low, high) in _FATIGUE_THRESHOLDS.items():
            if low <= total_7d <= high:
                fatigue_level = level
                break

        cooldown = _FATIGUE_COOLDOWN_HOURS.get(fatigue_level, 0)
        should_reduce = fatigue_level in (
            FatigueLevel.MODERATE, FatigueLevel.HIGH, FatigueLevel.CRITICAL
        )

        days_since = None
        if last_contact:
            delta = now - last_contact
            days_since = max(0, delta.days)

        reasoning_parts = [f"{total_7d} contacts in past 7 days"]
        if should_reduce:
            reasoning_parts.append(
                f"recommend {cooldown}h cooldown before next outreach"
            )
        if total_30d > 15:
            reasoning_parts.append(
                f"{total_30d} contacts in past 30 days (high cumulative)"
            )

        return FatigueStatus(
            borrower_id=borrower_id,
            fatigue_level=fatigue_level.value,
            total_contacts_7d=total_7d,
            total_contacts_30d=total_30d,
            contacts_by_channel_7d=contacts_7d_by_channel,
            days_since_last_contact=days_since,
            recommended_cooldown_hours=cooldown,
            should_reduce_frequency=should_reduce,
            reasoning="; ".join(reasoning_parts),
        )

    # =========================================================================
    # 5. A/B TEST FRAMEWORK
    # =========================================================================

    async def create_ab_test(
        self,
        name: str,
        description: str,
        control_channel: str,
        variant_channel: str,
        context: str = "document_reminder",
        sample_pct: float = 0.5,
    ) -> Dict[str, Any]:
        """Create a new A/B test for channel strategy comparison.

        Borrowers are assigned deterministically to control/variant based on
        a hash of (borrower_id, test_id) so assignments are stable.

        Args:
            name: Human-readable test name.
            description: What this test is evaluating.
            control_channel: The default channel (control group).
            variant_channel: The experimental channel (variant group).
            context: Outreach context this test applies to.
            sample_pct: Fraction of borrowers assigned to variant (0.0-1.0).

        Returns:
            Dict with the created test details.
        """
        now = datetime.now(timezone.utc)

        result = self.db.execute(
            text("""
                INSERT INTO channel_ab_tests
                    (organization_id, name, description, control_channel,
                     variant_channel, context, sample_pct, status, created_at, updated_at)
                VALUES
                    (:org_id, :name, :description, :control_channel,
                     :variant_channel, :context, :sample_pct, :status, :now, :now)
                RETURNING id
            """),
            {
                "org_id": self.org_id,
                "name": name,
                "description": description,
                "control_channel": control_channel,
                "variant_channel": variant_channel,
                "context": context,
                "sample_pct": sample_pct,
                "status": ABTestStatus.DRAFT.value,
                "now": now,
            },
        )
        test_id = result.fetchone()[0]
        self.db.flush()

        logger.info(
            "A/B test created: id=%d org=%d name=%s control=%s variant=%s",
            test_id, self.org_id, name, control_channel, variant_channel,
        )

        return {
            "id": test_id,
            "name": name,
            "control_channel": control_channel,
            "variant_channel": variant_channel,
            "context": context,
            "sample_pct": sample_pct,
            "status": ABTestStatus.DRAFT.value,
        }

    async def activate_ab_test(self, test_id: int) -> Dict[str, Any]:
        """Activate a draft A/B test, making it apply to new outreach decisions.

        Args:
            test_id: The A/B test to activate.

        Returns:
            Dict with updated test status.
        """
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE channel_ab_tests
                SET status = :status, started_at = :now, updated_at = :now
                WHERE id = :test_id AND organization_id = :org_id AND status = :draft
            """),
            {
                "status": ABTestStatus.ACTIVE.value,
                "now": now,
                "test_id": test_id,
                "org_id": self.org_id,
                "draft": ABTestStatus.DRAFT.value,
            },
        )
        self.db.flush()

        logger.info("A/B test activated: id=%d org=%d", test_id, self.org_id)
        return {"id": test_id, "status": ABTestStatus.ACTIVE.value}

    async def complete_ab_test(self, test_id: int) -> Dict[str, Any]:
        """Complete an A/B test and compute results.

        Args:
            test_id: The A/B test to complete.

        Returns:
            Dict with test results including per-group metrics.
        """
        now = datetime.now(timezone.utc)

        # Fetch test config
        test_row = self.db.execute(
            text("""
                SELECT id, name, control_channel, variant_channel, context,
                       sample_pct, started_at
                FROM channel_ab_tests
                WHERE id = :test_id AND organization_id = :org_id
            """),
            {"test_id": test_id, "org_id": self.org_id},
        ).fetchone()

        if not test_row:
            return {"error": f"A/B test {test_id} not found"}

        test = dict(zip(
            ["id", "name", "control_channel", "variant_channel", "context",
             "sample_pct", "started_at"],
            test_row,
        ))

        # Aggregate outcomes per group since test started
        started = test["started_at"] or now - timedelta(days=30)

        group_stats = self.db.execute(
            text("""
                SELECT
                    col.channel,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN col.outcome = 'document_uploaded' THEN 1 END) AS uploads,
                    COUNT(CASE WHEN col.outcome IN ('document_uploaded', 'responded',
                        'answered_call', 'voicemail_callback') THEN 1 END) AS responses,
                    AVG(col.response_time_minutes) FILTER (WHERE col.response_time_minutes IS NOT NULL)
                        AS avg_response_time
                FROM channel_outcome_log col
                WHERE col.organization_id = :org_id
                    AND col.created_at >= :started
                    AND col.channel IN (:control, :variant)
                    AND col.metadata->>'ab_test_id' = :test_id_str
                GROUP BY col.channel
            """),
            {
                "org_id": self.org_id,
                "started": started,
                "control": test["control_channel"],
                "variant": test["variant_channel"],
                "test_id_str": str(test_id),
            },
        ).fetchall()

        results = {}
        for row in group_stats:
            ch, total, uploads, responses, avg_rt = row
            group = "control" if ch == test["control_channel"] else "variant"
            results[group] = {
                "channel": ch,
                "total_contacts": total,
                "uploads": uploads,
                "responses": responses,
                "upload_rate": round(uploads / total, 4) if total > 0 else 0.0,
                "response_rate": round(responses / total, 4) if total > 0 else 0.0,
                "avg_response_time_minutes": round(float(avg_rt or 0), 1),
            }

        # Mark test as completed
        self.db.execute(
            text("""
                UPDATE channel_ab_tests
                SET status = :status, ended_at = :now, results = CAST(:results AS jsonb),
                    updated_at = :now
                WHERE id = :test_id AND organization_id = :org_id
            """),
            {
                "status": ABTestStatus.COMPLETED.value,
                "now": now,
                "results": _json_dumps(results),
                "test_id": test_id,
                "org_id": self.org_id,
            },
        )
        self.db.flush()

        # Determine winner
        control = results.get("control", {})
        variant = results.get("variant", {})
        winner = None
        if control.get("upload_rate", 0) > variant.get("upload_rate", 0):
            winner = "control"
        elif variant.get("upload_rate", 0) > control.get("upload_rate", 0):
            winner = "variant"
        else:
            winner = "tie"

        return {
            "test_id": test_id,
            "name": test["name"],
            "status": ABTestStatus.COMPLETED.value,
            "winner": winner,
            "results": results,
        }

    # =========================================================================
    # 6. CROSS-CHANNEL COORDINATION
    # =========================================================================

    def check_cross_channel_ok(
        self,
        borrower_id: int,
        proposed_channel: str,
    ) -> Tuple[bool, Optional[str]]:
        """Check whether it is safe to contact on the proposed channel today.

        Prevents contacting a borrower on multiple channels within the same
        day (configurable gap). Returns (True, None) if OK, or (False, reason)
        if blocked.

        Args:
            borrower_id: The borrower to check.
            proposed_channel: Channel being considered.

        Returns:
            Tuple of (is_ok, reason_if_blocked).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_CROSS_CHANNEL_MIN_GAP_HOURS)

        row = self.db.execute(
            text("""
                SELECT channel, MAX(created_at) AS last_at
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND created_at >= :cutoff
                    AND channel != :proposed
                GROUP BY channel
                ORDER BY last_at DESC
                LIMIT 1
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "cutoff": cutoff,
                "proposed": proposed_channel,
            },
        ).fetchone()

        if row:
            other_ch, last_at = row
            hours_ago = (datetime.now(timezone.utc) - last_at).total_seconds() / 3600
            return False, (
                f"Contacted via {other_ch} {hours_ago:.1f}h ago; "
                f"minimum gap is {_CROSS_CHANNEL_MIN_GAP_HOURS}h"
            )

        # Also check total daily contacts across all channels
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        total_today = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND created_at >= :today_start
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "today_start": today_start,
            },
        ).scalar() or 0

        if total_today >= _MAX_DAILY_CONTACTS_ALL_CHANNELS:
            return False, (
                f"Daily contact limit reached ({total_today}/{_MAX_DAILY_CONTACTS_ALL_CHANNELS})"
            )

        return True, None

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _calculate_channel_scores(self, borrower_id: int) -> Dict[str, ChannelScore]:
        """Calculate per-channel scores from historical outcome stats.

        Reads from the channel_outcome_stats aggregation table for fast
        lookups, then normalizes into 0-100 scores.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    channel,
                    total_contacts,
                    total_responses,
                    total_uploads,
                    total_response_time_minutes,
                    last_contact_at,
                    last_outcome
                FROM channel_outcome_stats
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
            """),
            {"org_id": self.org_id, "borrower_id": borrower_id},
        ).fetchall()

        scores: Dict[str, ChannelScore] = {}
        columns = [
            "channel", "total_contacts", "total_responses", "total_uploads",
            "total_response_time_minutes", "last_contact_at", "last_outcome",
        ]

        # Also fetch org-wide averages as benchmarks
        org_avgs = self._get_org_channel_averages()

        for row in rows:
            r = dict(zip(columns, row))
            ch = r["channel"]
            total = r["total_contacts"] or 0
            responses = r["total_responses"] or 0
            uploads = r["total_uploads"] or 0
            total_rt = r["total_response_time_minutes"] or 0

            if total == 0:
                continue

            response_rate = responses / total
            upload_rate = uploads / total
            avg_rt = total_rt / responses if responses > 0 else 0.0

            # Normalize response time: faster = higher score, capped at 1440 min (24h)
            rt_score = max(0.0, 1.0 - (avg_rt / 1440.0)) if avg_rt > 0 else 0.5

            # Delivery rate: assume 1.0 unless we have bounce data
            # (bounced outcomes are tracked separately in channel_outcome_log)
            delivery_rate = 1.0  # conservative default

            # Cost efficiency: compare to org average cost-per-upload
            org_avg_cost = org_avgs.get(ch, {}).get("cost_per_upload", 1.0)
            ch_cost = _CHANNEL_COST.get(Channel(ch), 0.01) if ch in [c.value for c in Channel] else 0.01
            cost_per_upload = (ch_cost * total) / uploads if uploads > 0 else ch_cost * 100
            cost_score = max(0.0, min(1.0, org_avg_cost / cost_per_upload)) if cost_per_upload > 0 else 0.5

            # Weighted total score (0-100)
            total_score = (
                _SCORE_WEIGHTS["upload_rate"] * upload_rate * 100
                + _SCORE_WEIGHTS["response_rate"] * response_rate * 100
                + _SCORE_WEIGHTS["response_time"] * rt_score * 100
                + _SCORE_WEIGHTS["delivery_rate"] * delivery_rate * 100
                + _SCORE_WEIGHTS["cost_efficiency"] * cost_score * 100
            )

            scores[ch] = ChannelScore(
                channel=ch,
                total_score=total_score,
                response_rate=response_rate,
                upload_rate=upload_rate,
                response_time_avg_minutes=avg_rt,
                delivery_rate=delivery_rate,
                sample_count=total,
            )

        return scores

    def _get_org_channel_averages(self) -> Dict[str, Dict[str, float]]:
        """Get organization-wide average channel performance for benchmarking."""
        rows = self.db.execute(
            text("""
                SELECT
                    channel,
                    AVG(CASE WHEN total_contacts > 0
                        THEN total_responses::float / total_contacts END) AS avg_response_rate,
                    AVG(CASE WHEN total_contacts > 0
                        THEN total_uploads::float / total_contacts END) AS avg_upload_rate,
                    AVG(CASE WHEN total_responses > 0
                        THEN total_response_time_minutes::float / total_responses END) AS avg_rt
                FROM channel_outcome_stats
                WHERE organization_id = :org_id
                    AND total_contacts >= 3
                GROUP BY channel
            """),
            {"org_id": self.org_id},
        ).fetchall()

        result = {}
        for row in rows:
            ch, avg_rr, avg_ur, avg_rt = row
            cost = _CHANNEL_COST.get(Channel(ch), 0.01) if ch in [c.value for c in Channel] else 0.01
            avg_uploads = (avg_ur or 0.01) * 10  # rough normalization
            result[ch] = {
                "avg_response_rate": float(avg_rr or 0),
                "avg_upload_rate": float(avg_ur or 0),
                "avg_response_time": float(avg_rt or 0),
                "cost_per_upload": cost / max(avg_uploads, 0.001),
            }
        return result

    def _check_blackout(self, loan_id: int) -> Optional[str]:
        """Check if the loan is in a stage where outreach should be suppressed.

        Returns None if outreach is OK, or a reason string if blocked.
        """
        row = self.db.execute(
            text("""
                SELECT stage, closing_date
                FROM loans
                WHERE id = :loan_id AND organization_id = :org_id
            """),
            {"loan_id": loan_id, "org_id": self.org_id},
        ).fetchone()

        if not row:
            return None  # loan not found; let caller handle

        stage, closing_date = row

        if stage and stage.upper() in _BLACKOUT_STAGES:
            return f"Loan is in {stage} stage (blackout)"

        # Suppress during closing week (7 days before closing_date)
        if closing_date:
            close_dt = closing_date if isinstance(closing_date, date) else closing_date.date()
            days_to_close = (close_dt - date.today()).days
            if 0 <= days_to_close <= 7:
                return f"Closing in {days_to_close} days (closing week blackout)"

        return None

    def _get_borrower_phone(self, borrower_id: int) -> Optional[str]:
        """Look up borrower phone number from leads table."""
        row = self.db.execute(
            text("""
                SELECT phone FROM leads
                WHERE id = :borrower_id
                    AND (organization_id = :org_id OR organization_id IS NULL)
                LIMIT 1
            """),
            {"borrower_id": borrower_id, "org_id": self.org_id},
        ).fetchone()

        return row[0] if row else None

    def _check_consent_all_channels(
        self,
        borrower_id: int,
        phone: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """Check consent/DNC status for all channels.

        Returns a dict mapping channel -> reason if BLOCKED, or channel -> None if OK.
        Email and portal are always considered consented (no TCPA restriction).
        SMS and phone require explicit consent.
        """
        result: Dict[str, Optional[str]] = {
            Channel.EMAIL.value: None,  # Email does not require TCPA consent
            Channel.PORTAL.value: None,  # Portal is passive
            Channel.SMS.value: None,
            Channel.PHONE.value: None,
        }

        if not phone:
            result[Channel.SMS.value] = "No phone number on file"
            result[Channel.PHONE.value] = "No phone number on file"
            return result

        # Use the existing TCPA compliance service
        from services.smart_docs.tcpa_compliance_service import TCPAComplianceService

        tcpa = TCPAComplianceService(self.db)

        # DNC check
        if tcpa.check_dnc_list(phone):
            result[Channel.SMS.value] = "Phone is on Do Not Contact list"
            result[Channel.PHONE.value] = "Phone is on Do Not Contact list"
            return result

        # SMS consent
        sms_check = tcpa.check_sms_consent(phone, self.org_id)
        if not sms_check.allowed:
            result[Channel.SMS.value] = sms_check.reason

        # Call consent
        call_check = tcpa.check_call_consent(phone, self.org_id)
        if not call_check.allowed:
            result[Channel.PHONE.value] = call_check.reason

        # Quiet hours (block SMS and phone during quiet hours)
        if tcpa.check_quiet_hours(phone):
            if not result[Channel.SMS.value]:
                result[Channel.SMS.value] = "TCPA quiet hours"
            if not result[Channel.PHONE.value]:
                result[Channel.PHONE.value] = "TCPA quiet hours"

        # Check borrower explicit preferences
        pref = self._get_borrower_channel_preference(borrower_id)
        if pref and pref.get("opted_out_channels"):
            for ch in pref["opted_out_channels"]:
                if ch in result and not result[ch]:
                    result[ch] = "Borrower opted out of this channel"

        return result

    def _get_borrower_channel_preference(self, borrower_id: int) -> Optional[Dict]:
        """Get borrower's explicit channel preferences if stored.

        Looks in the leads table preferred_communication column and
        communication_preferences if available.
        """
        row = self.db.execute(
            text("""
                SELECT preferred_communication
                FROM leads
                WHERE id = :borrower_id
                    AND (organization_id = :org_id OR organization_id IS NULL)
                LIMIT 1
            """),
            {"borrower_id": borrower_id, "org_id": self.org_id},
        ).fetchone()

        if not row or not row[0]:
            return None

        preferred = row[0]

        # Map common values to structured preferences
        opted_out: List[str] = []
        if preferred == "email_only":
            opted_out = [Channel.SMS.value, Channel.PHONE.value]
        elif preferred == "no_calls":
            opted_out = [Channel.PHONE.value]
        elif preferred == "no_sms":
            opted_out = [Channel.SMS.value]

        return {
            "preferred": preferred,
            "opted_out_channels": opted_out,
        }

    def _get_demographic_bracket(self, borrower_id: int) -> str:
        """Infer age bracket from borrower data for demographic defaults.

        Uses date_of_birth if available on the lead record, otherwise
        returns 'unknown'.
        """
        row = self.db.execute(
            text("""
                SELECT date_of_birth
                FROM leads
                WHERE id = :borrower_id
                    AND (organization_id = :org_id OR organization_id IS NULL)
                LIMIT 1
            """),
            {"borrower_id": borrower_id, "org_id": self.org_id},
        ).fetchone()

        if not row or not row[0]:
            return "unknown"

        dob = row[0]
        if isinstance(dob, datetime):
            dob = dob.date()

        age = (date.today() - dob).days // 365

        if age < 35:
            return "18-34"
        elif age < 50:
            return "35-49"
        elif age < 65:
            return "50-64"
        else:
            return "65+"

    def _get_optimal_contact_time(
        self,
        borrower_id: int,
        channel: str,
    ) -> Tuple[str, Optional[int]]:
        """Determine optimal contact time from historical response data.

        Analyzes the hour of day and day of week when the borrower was most
        responsive (had the fastest or most frequent positive outcomes).

        Falls back to demographic defaults or 10:00 AM.

        Returns:
            Tuple of (time_str "HH:MM", day_of_week 0-6 or None).
        """
        # Get response-time-weighted hour distribution
        rows = self.db.execute(
            text("""
                SELECT
                    EXTRACT(HOUR FROM created_at) AS hour,
                    EXTRACT(DOW FROM created_at) AS dow,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN outcome IN ('document_uploaded', 'responded',
                        'answered_call') THEN 1 END) AS positive_count
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND channel = :channel
                GROUP BY EXTRACT(HOUR FROM created_at), EXTRACT(DOW FROM created_at)
                ORDER BY positive_count DESC, count DESC
                LIMIT 10
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "channel": channel,
            },
        ).fetchall()

        if rows and rows[0][3] > 0:  # has positive outcomes
            best_hour = int(rows[0][0])
            best_dow = int(rows[0][1])
            # PostgreSQL DOW: 0=Sunday, but we want 0=Monday
            best_dow_iso = (best_dow - 1) % 7 if best_dow > 0 else 6
            return f"{best_hour:02d}:00", best_dow_iso

        # Fallback: demographic-based optimal hour
        demo = self._get_demographic_bracket(borrower_id)
        defaults = _DEMOGRAPHIC_DEFAULTS.get(demo, _DEMOGRAPHIC_DEFAULTS["unknown"])
        optimal_hour = defaults.get("optimal_hour", 10)

        # Adjust for borrower timezone
        tz_name = self._resolve_borrower_timezone(borrower_id)
        if tz_name and tz_name != _DEFAULT_TIMEZONE:
            # Convert optimal hour from borrower-local to UTC for scheduling
            # But we return the local time for display
            pass  # optimal_hour is already in borrower's local time

        return f"{optimal_hour:02d}:00", None

    def _resolve_borrower_timezone(self, borrower_id: int) -> str:
        """Resolve timezone for a borrower from phone area code or property state."""
        phone = self._get_borrower_phone(borrower_id)
        if phone:
            digits = re.sub(r"\D", "", phone)
            if len(digits) == 10:
                digits = "1" + digits
            if len(digits) >= 11 and digits[0] == "1":
                area_code = digits[1:4]
                tz = _AREA_CODE_TZ.get(area_code)
                if tz:
                    return tz

        return _DEFAULT_TIMEZONE

    def _get_channels_used_today(self, borrower_id: int) -> List[str]:
        """Get channels already used to contact this borrower today."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        rows = self.db.execute(
            text("""
                SELECT DISTINCT channel
                FROM channel_outcome_log
                WHERE organization_id = :org_id
                    AND borrower_id = :borrower_id
                    AND created_at >= :today_start
            """),
            {
                "org_id": self.org_id,
                "borrower_id": borrower_id,
                "today_start": today_start,
            },
        ).fetchall()

        return [row[0] for row in rows]

    def _get_ab_test_variant(
        self,
        borrower_id: int,
        context: str,
    ) -> Optional[str]:
        """Determine if borrower is in an active A/B test and which variant.

        Assignment is deterministic via hash(borrower_id, test_id) so
        borrowers always get the same variant for a given test.

        Returns the channel name for the assigned variant, or None if no
        active test applies.
        """
        tests = self.db.execute(
            text("""
                SELECT id, control_channel, variant_channel, sample_pct
                FROM channel_ab_tests
                WHERE organization_id = :org_id
                    AND status = :active
                    AND context = :context
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {
                "org_id": self.org_id,
                "active": ABTestStatus.ACTIVE.value,
                "context": context,
            },
        ).fetchone()

        if not tests:
            return None

        test_id, control_ch, variant_ch, sample_pct = tests

        # Deterministic assignment via hash
        hash_input = f"{borrower_id}:{test_id}".encode()
        hash_val = int(hashlib.sha256(hash_input).hexdigest()[:8], 16)
        threshold = int(sample_pct * 0xFFFFFFFF)

        if hash_val < threshold:
            return variant_ch
        else:
            return control_ch

    def _calculate_confidence(
        self,
        best_score: ChannelScore,
        has_history: bool,
    ) -> float:
        """Calculate confidence in the recommendation (0.0-1.0).

        Based on sample size and score magnitude.
        """
        if not has_history:
            return 0.3  # demographic default only

        n = best_score.sample_count
        if n < 3:
            return 0.3
        elif n < 10:
            base = 0.5
        elif n < 30:
            base = 0.7
        else:
            base = 0.85

        # Boost confidence if score is clearly dominant
        score_boost = min(0.15, best_score.total_score / 1000.0)

        return min(1.0, base + score_boost)


# =============================================================================
# TABLE CREATION SQL
# =============================================================================

CHANNEL_OPTIMIZATION_TABLES_SQL = """
-- Outcome log: every channel contact and its result
CREATE TABLE IF NOT EXISTS channel_outcome_log (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    borrower_id INTEGER NOT NULL,
    channel VARCHAR(20) NOT NULL,
    outcome VARCHAR(50) NOT NULL,
    response_time_minutes REAL,
    campaign_id INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_col_org_borrower ON channel_outcome_log (organization_id, borrower_id);
CREATE INDEX IF NOT EXISTS ix_col_org_channel ON channel_outcome_log (organization_id, channel);
CREATE INDEX IF NOT EXISTS ix_col_org_created ON channel_outcome_log (organization_id, created_at);
CREATE INDEX IF NOT EXISTS ix_col_borrower_created ON channel_outcome_log (borrower_id, created_at);

-- Running stats per borrower per channel (upsert target)
CREATE TABLE IF NOT EXISTS channel_outcome_stats (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    borrower_id INTEGER NOT NULL,
    channel VARCHAR(20) NOT NULL,
    total_contacts INTEGER NOT NULL DEFAULT 0,
    total_responses INTEGER NOT NULL DEFAULT 0,
    total_uploads INTEGER NOT NULL DEFAULT 0,
    total_response_time_minutes REAL NOT NULL DEFAULT 0,
    last_contact_at TIMESTAMPTZ,
    last_outcome VARCHAR(50),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, borrower_id, channel)
);
CREATE INDEX IF NOT EXISTS ix_cos_org_borrower ON channel_outcome_stats (organization_id, borrower_id);

-- A/B test configuration
CREATE TABLE IF NOT EXISTS channel_ab_tests (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    control_channel VARCHAR(20) NOT NULL,
    variant_channel VARCHAR(20) NOT NULL,
    context VARCHAR(50) NOT NULL DEFAULT 'document_reminder',
    sample_pct REAL NOT NULL DEFAULT 0.5,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    results JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_cat_org_status ON channel_ab_tests (organization_id, status);
CREATE INDEX IF NOT EXISTS ix_cat_org_context ON channel_ab_tests (organization_id, context);
"""


def ensure_tables(db: Session) -> None:
    """Create channel optimization tables if they do not exist.

    Safe to call on every startup (uses IF NOT EXISTS).
    """
    try:
        for statement in CHANNEL_OPTIMIZATION_TABLES_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                db.execute(text(stmt))
        db.commit()
        logger.info("Channel optimization tables ensured")
    except Exception as e:
        db.rollback()
        logger.warning("Could not create channel optimization tables: %s", e)


# =============================================================================
# JSON SERIALIZER
# =============================================================================

def _json_dumps(obj: Any) -> str:
    """Serialize to JSON string, handling datetimes."""
    import json

    def _default(o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, default=_default)
