"""
Autonomous Lead Nurturing Agent

Proactive agent that runs on a schedule to identify cold/stale leads
and automatically generate follow-up outreach, updating engagement scores
and notifying assigned loan officers.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from database.models.lead_loan import Lead
from database.models.communication import Activity, ChannelPreference
from database.models.security import Notification
from database.enums import ActivityType

logger = logging.getLogger(__name__)

# Stages where the lead is terminal — no further nurturing needed
TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Higher weight = higher-quality source (used in priority scoring)
SOURCE_QUALITY_WEIGHTS = {
    "referral": 1.0,
    "realtor": 0.9,
    "zillow": 0.8,
    "lendingtree": 0.7,
    "website": 0.6,
    "facebook": 0.5,
    "google": 0.5,
    "cold_call": 0.3,
    "imported": 0.2,
}

# Stage-specific follow-up message templates keyed by uppercase stage
_STAGE_MESSAGES = {
    "NEW": (
        "Hi {first_name}, this is a follow-up from your recent inquiry. "
        "We'd love to help you explore your mortgage options. "
        "Do you have a few minutes to chat this week?"
    ),
    "CONTACTED": (
        "Hi {first_name}, just circling back. "
        "If you have any questions about getting pre-approved, I'm here to help."
    ),
    "PRE_QUALIFIED": (
        "Hi {first_name}, wanted to follow up on your pre-qualification. "
        "Ready to take the next step toward pre-approval?"
    ),
    "APPLICATION": (
        "Hi {first_name}, just checking in on your application. "
        "Do you have any questions about the process or documents needed?"
    ),
    "DISCLOSED": (
        "Hi {first_name}, your disclosures have been sent. "
        "Please review and sign them at your earliest convenience. "
        "Let me know if anything is unclear."
    ),
    "PROCESSING": (
        "Hi {first_name}, your loan is in processing. "
        "We're working on it — is there anything you need from us?"
    ),
    "SUBMITTED": (
        "Hi {first_name}, your file has been submitted to underwriting. "
        "I'll keep you posted on the timeline. Reach out if you have questions."
    ),
    "UNDERWRITING": (
        "Hi {first_name}, your loan is with the underwriter. "
        "We're monitoring progress and will update you as soon as we hear back."
    ),
    "CONDITIONAL_APPROVAL": (
        "Hi {first_name}, great news — you've received conditional approval! "
        "Let's work on clearing the remaining conditions. "
        "Do you have time to go over them?"
    ),
    "APPROVED": (
        "Hi {first_name}, your loan is approved! "
        "We're preparing for closing. Let me know if you have any questions."
    ),
    "CTC": (
        "Hi {first_name}, you're clear to close! "
        "Our closing team will be reaching out to schedule. Almost there!"
    ),
    "CLEAR_TO_CLOSE": (
        "Hi {first_name}, you're clear to close! "
        "Our closing team will be reaching out to schedule. Almost there!"
    ),
    "CLOSING": (
        "Hi {first_name}, closing is coming up. "
        "Make sure to bring your ID and certified funds. See you soon!"
    ),
    "PRE_APPROVED": (
        "Hi {first_name}, wanted to follow up on your pre-approval. "
        "Ready to start looking at homes? Let me know how I can help."
    ),
}

_DEFAULT_MESSAGE = (
    "Hi {first_name}, just wanted to check in and see how things are going. "
    "If you have any questions about your mortgage, I'm here for you."
)


class LeadNurturingAgent:
    """Autonomous agent that identifies and nurtures cold leads.

    Designed to run on a periodic schedule (e.g. daily via cron or APScheduler).
    For each organization, the agent:
      1. Finds leads with no recent activity beyond a configurable threshold.
      2. Scores them by staleness, stage, and source quality.
      3. Generates a stage-appropriate follow-up message.
      4. Records an Activity and creates a Notification for the assigned LO.
    """

    AGENT_TYPE = "lead_nurturing"

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.gateway = gateway
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """Execute the nurturing cycle. Returns an execution summary."""
        days_threshold = self.config.get("days_threshold", 7)
        max_leads = self.config.get("max_leads_per_run", 50)
        min_priority = self.config.get("min_priority_score", 10.0)

        summary: dict = {
            "agent": self.AGENT_TYPE,
            "organization_id": self.org_id,
            "days_threshold": days_threshold,
            "leads_evaluated": 0,
            "leads_contacted": 0,
            "actions": [],
            "errors": [],
        }

        try:
            cold_leads = self._find_cold_leads(days_threshold)
            summary["leads_evaluated"] = len(cold_leads)
            self.logger.info(
                "Found %d cold leads (threshold=%d days) for org %d",
                len(cold_leads), days_threshold, self.org_id,
            )

            # Score and sort descending by priority
            scored: list[tuple[Lead, datetime | None, float]] = []
            for lead, last_activity_date in cold_leads:
                score = self._score_lead_priority(lead, last_activity_date)
                if score >= min_priority:
                    scored.append((lead, last_activity_date, score))

            scored.sort(key=lambda t: t[2], reverse=True)

            for lead, last_activity_date, score in scored[:max_leads]:
                try:
                    channel = self._determine_outreach_channel(lead)
                    message = self._generate_followup_message(lead, channel)
                    self._record_outreach(lead, channel, message)

                    summary["leads_contacted"] += 1
                    summary["actions"].append({
                        "lead_id": lead.id,
                        "lead_name": lead.name,
                        "stage": lead.stage,
                        "channel": channel,
                        "priority_score": round(score, 1),
                        "days_since_contact": (
                            (datetime.now(timezone.utc) - last_activity_date).days
                            if last_activity_date else None
                        ),
                    })
                except Exception as e:
                    self.logger.exception(
                        "Failed to nurture lead %d: %s", lead.id, e,
                    )
                    summary["errors"].append({
                        "lead_id": lead.id,
                        "error": str(e),
                    })

            # Commit all outreach records in one transaction
            self.db.commit()

        except Exception as e:
            self.logger.exception(
                "Lead nurturing run failed for org %d: %s", self.org_id, e,
            )
            self.db.rollback()
            summary["errors"].append({"fatal": str(e)})

        self.logger.info(
            "Nurturing complete for org %d: %d evaluated, %d contacted, %d errors",
            self.org_id,
            summary["leads_evaluated"],
            summary["leads_contacted"],
            len(summary["errors"]),
        )
        return summary

    # ------------------------------------------------------------------
    # Lead discovery
    # ------------------------------------------------------------------

    def _find_cold_leads(
        self, days_threshold: int
    ) -> List[tuple]:
        """Return (Lead, last_activity_date) pairs for leads needing outreach.

        A lead qualifies when:
          - It belongs to this organization
          - Its stage is NOT terminal
          - Its most recent Activity (or created_at if none) is older than
            ``days_threshold`` days
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        # Subquery: most recent activity per lead in this org
        last_activity_sq = (
            self.db.query(
                Activity.lead_id,
                func.max(Activity.created_at).label("last_activity_at"),
            )
            .filter(Activity.organization_id == self.org_id)
            .group_by(Activity.lead_id)
            .subquery("last_activity")
        )

        query = (
            self.db.query(Lead, last_activity_sq.c.last_activity_at)
            .outerjoin(last_activity_sq, Lead.id == last_activity_sq.c.lead_id)
            .filter(
                Lead.organization_id == self.org_id,
                ~Lead.stage.in_(TERMINAL_STAGES),
                or_(
                    # No activity at all and lead created before cutoff
                    and_(
                        last_activity_sq.c.last_activity_at.is_(None),
                        Lead.created_at < cutoff,
                    ),
                    # Last activity older than cutoff
                    last_activity_sq.c.last_activity_at < cutoff,
                ),
            )
            .order_by(
                func.coalesce(
                    last_activity_sq.c.last_activity_at, Lead.created_at
                ).asc()
            )
        )

        return query.all()

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_lead_priority(
        self, lead: Lead, last_activity_date: Optional[datetime]
    ) -> float:
        """Score a lead 0-100 based on staleness, stage, and source quality.

        Components (each 0-~33):
          - Staleness: more days without contact = higher urgency (max 40)
          - Stage weight: active pipeline stages score higher (max 35)
          - Source quality: referral > zillow > cold_call etc. (max 25)
        """
        now = datetime.now(timezone.utc)
        reference_date = last_activity_date or (
            lead.created_at.replace(tzinfo=timezone.utc)
            if lead.created_at and lead.created_at.tzinfo is None
            else lead.created_at
        ) or now

        # -- Staleness component (0-40) --
        days_stale = (now - reference_date).days if reference_date else 0
        # Cap contribution at 60 days
        staleness_score = min(days_stale / 60.0, 1.0) * 40.0

        # -- Stage weight (0-35) --
        stage_weights = {
            "APPLICATION": 0.9,
            "DISCLOSED": 0.85,
            "PROCESSING": 0.8,
            "SUBMITTED": 0.8,
            "UNDERWRITING": 0.75,
            "CONDITIONAL_APPROVAL": 0.95,
            "APPROVED": 0.7,
            "CTC": 0.6,
            "CLEAR_TO_CLOSE": 0.6,
            "CLOSING": 0.5,
            "PRE_APPROVED": 0.85,
            "PRE_QUALIFIED": 0.7,
            "CONTACTED": 0.5,
            "NEW": 0.6,
        }
        stage_upper = (lead.stage or "").upper()
        stage_score = stage_weights.get(stage_upper, 0.4) * 35.0

        # -- Source quality (0-25) --
        source_key = (lead.source or "").lower().replace(" ", "_")
        source_score = SOURCE_QUALITY_WEIGHTS.get(source_key, 0.3) * 25.0

        return staleness_score + stage_score + source_score

    # ------------------------------------------------------------------
    # Channel selection
    # ------------------------------------------------------------------

    def _determine_outreach_channel(self, lead: Lead) -> str:
        """Pick the best outreach channel for a lead.

        Priority:
          1. ChannelPreference record (if exists and not DNC'd)
          2. Lead.preferred_communication field
          3. Fallback: email if available, else sms
        """
        # Check ChannelPreference table
        pref: Optional[ChannelPreference] = (
            self.db.query(ChannelPreference)
            .filter(
                ChannelPreference.organization_id == self.org_id,
                ChannelPreference.lead_id == lead.id,
            )
            .first()
        )

        if pref:
            channels = pref.preferred_channels or ["email", "sms"]
            for ch in channels:
                ch_lower = ch.lower()
                if ch_lower == "email" and not pref.do_not_email and lead.email:
                    return "email"
                if ch_lower in ("sms", "text") and not pref.do_not_sms and lead.phone:
                    return "sms"
            # All preferred channels blocked — fall through

        # Lead-level preference
        lead_pref = (lead.preferred_communication or "").lower()
        if lead_pref in ("email",) and lead.email:
            return "email"
        if lead_pref in ("text", "sms", "phone") and lead.phone:
            return "sms"

        # Default: email first, then sms
        if lead.email:
            return "email"
        if lead.phone:
            return "sms"

        return "email"  # fallback even without address — caller logs the attempt

    # ------------------------------------------------------------------
    # Message generation
    # ------------------------------------------------------------------

    def _generate_followup_message(self, lead: Lead, channel: str) -> str:
        """Build a stage-appropriate follow-up message for the lead."""
        first_name = lead.first_name or lead.name or "there"
        stage_upper = (lead.stage or "").upper()

        template = _STAGE_MESSAGES.get(stage_upper, _DEFAULT_MESSAGE)
        message = template.format(first_name=first_name)

        # SMS messages should be concise (160 char soft limit)
        if channel == "sms" and len(message) > 160:
            message = message[:157] + "..."

        return message

    # ------------------------------------------------------------------
    # Outreach recording
    # ------------------------------------------------------------------

    def _record_outreach(self, lead: Lead, channel: str, message: str) -> None:
        """Create an Activity record and a Notification for the assigned LO."""
        activity_type = (
            ActivityType.SMS if channel == "sms" else ActivityType.EMAIL
        )

        activity = Activity(
            organization_id=self.org_id,
            lead_id=lead.id,
            user_id=lead.owner_id,
            type=activity_type,
            content=message,
            sentiment="neutral",
            user_metadata={
                "source": self.AGENT_TYPE,
                "channel": channel,
                "automated": True,
            },
        )

        def _execute_outreach():
            self.db.add(activity)
            lead.last_contact = datetime.now(timezone.utc)

        if self.gateway:
            action_type = "send_sms" if channel == "sms" else "send_email"
            self.gateway.propose(
                action_type,
                _execute_outreach,
                target_entity="lead",
                target_id=lead.id,
                description=f"Automated {channel} follow-up to {lead.first_name or 'lead'}",
                payload={
                    "lead_id": lead.id,
                    "lo_id": lead.owner_id,
                    "channel": channel,
                    "stage": lead.stage,
                    "phone": lead.phone if channel == "sms" else None,
                    "to_email": lead.email if channel == "email" else None,
                    "message": message,
                    "subject": f"Follow-up: {lead.first_name or 'Your Mortgage Inquiry'}" if channel == "email" else None,
                },
                notify_user_id=lead.owner_id,
            )
        else:
            _execute_outreach()

        # Notify the assigned LO (if any)
        if lead.owner_id:
            notification = Notification(
                organization_id=self.org_id,
                user_id=lead.owner_id,
                type="automated_nurture",
                title="Automated follow-up sent",
                message=(
                    f"An automated {channel.upper()} follow-up was sent to "
                    f"{lead.first_name or lead.name} "
                    f"(stage: {lead.stage or 'Unknown'}). "
                    f"Review and personalize if needed."
                ),
                link=f"/leads/{lead.id}",
                is_read=False,
            )
            if self.gateway:
                self.gateway.propose(
                    "create_notification",
                    lambda: self.db.add(notification),
                    target_entity="lead",
                    target_id=lead.id,
                    description="LO notification for automated nurture outreach",
                    payload={
                        "user_id": lead.owner_id,
                        "lead_id": lead.id,
                        "type": "automated_nurture",
                        "title": "Automated follow-up sent",
                        "message": notification.message,
                        "link": f"/leads/{lead.id}",
                    },
                    notify_user_id=lead.owner_id,
                )
            else:
                self.db.add(notification)

        self.logger.debug(
            "Recorded %s outreach for lead %d (%s)",
            channel, lead.id, lead.stage,
        )
