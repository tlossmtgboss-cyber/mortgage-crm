"""
Autonomous Lead Scoring Agent

Runs on a schedule to score and prioritize leads based on engagement,
profile completeness, demographic fit, and behavioral signals.  Stores
the composite score in Lead.ai_score and a detailed breakdown in
Lead.user_metadata["score_breakdown"].
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database.models.lead_loan import Lead
from database.models.communication import Activity
from database.models.document import Document
from database.models.security import Notification
from database.enums import ActivityType

logger = logging.getLogger(__name__)

# Leads in terminal stages are excluded from scoring.
TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Re-score interval — skip leads scored within this window.
DEFAULT_RESCORE_HOURS = 24


class LeadScoringAgent:
    """Autonomous agent that scores every active lead in an organization.

    Designed to run on a periodic schedule (e.g. daily via cron or APScheduler).
    The agent:
      1. Finds leads that haven't been scored recently (or ever).
      2. Computes a 0-100 composite score across four dimensions.
      3. Updates Lead.ai_score and persists the breakdown in user_metadata.
      4. Identifies "hot" leads (score >= 70) and notifies assigned LOs.
    """

    AGENT_TYPE = "lead_scoring"

    def __init__(self, db: Session, org_id: int, config: dict | None = None):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """Score all eligible leads and return an execution summary."""
        summary: dict[str, Any] = {
            "agent": self.AGENT_TYPE,
            "organization_id": self.org_id,
            "leads_scored": 0,
            "avg_score": 0.0,
            "hot_leads_found": 0,
            "score_distribution": {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0},
            "errors": [],
        }

        try:
            leads = self._get_leads_to_score()
            self.logger.info(
                "Found %d leads to score for org %d", len(leads), self.org_id,
            )

            scored_leads: list[dict] = []
            total_score = 0.0

            for lead in leads:
                try:
                    score_data = self._calculate_score(lead)
                    self._update_lead_score(lead, score_data)
                    scored_leads.append(score_data)
                    total_score += score_data["total"]

                    # Bucket for distribution
                    bucket = self._score_bucket(score_data["total"])
                    summary["score_distribution"][bucket] += 1

                except Exception as e:
                    self.logger.exception("Error scoring lead %d: %s", lead.id, e)
                    summary["errors"].append({"lead_id": lead.id, "error": str(e)})

            self.db.commit()

            summary["leads_scored"] = len(scored_leads)
            if scored_leads:
                summary["avg_score"] = round(total_score / len(scored_leads), 1)

            hot_leads = self._identify_hot_leads(scored_leads)
            summary["hot_leads_found"] = len(hot_leads)
            if hot_leads:
                self._notify_hot_leads(hot_leads)
                self.db.commit()

        except Exception as e:
            self.logger.exception("Lead scoring run failed for org %d: %s", self.org_id, e)
            summary["errors"].append({"error": str(e)})

        self.logger.info(
            "Scoring complete — org=%d scored=%d avg=%.1f hot=%d",
            self.org_id,
            summary["leads_scored"],
            summary["avg_score"],
            summary["hot_leads_found"],
        )
        return summary

    # ------------------------------------------------------------------
    # Lead selection
    # ------------------------------------------------------------------

    def _get_leads_to_score(self) -> list[Lead]:
        """Return leads that haven't been scored within the rescore window."""
        rescore_hours = self.config.get("rescore_hours", DEFAULT_RESCORE_HOURS)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=rescore_hours)

        query = (
            self.db.query(Lead)
            .filter(
                Lead.organization_id == self.org_id,
                ~Lead.stage.in_(TERMINAL_STAGES),
            )
        )

        # Only include leads not scored recently.  We track the last scoring
        # timestamp inside user_metadata["last_scored_at"], but for leads that
        # have never been scored we accept them unconditionally.
        all_leads = query.all()
        result: list[Lead] = []
        for lead in all_leads:
            meta = lead.user_metadata or {}
            last_scored = meta.get("last_scored_at")
            if last_scored is None:
                result.append(lead)
                continue
            try:
                scored_dt = datetime.fromisoformat(last_scored)
                if scored_dt < cutoff:
                    result.append(lead)
            except (ValueError, TypeError):
                result.append(lead)

        return result

    # ------------------------------------------------------------------
    # Score calculation
    # ------------------------------------------------------------------

    def _calculate_score(self, lead: Lead) -> dict:
        """Compute the full score breakdown for a single lead."""
        engagement = self._calculate_engagement_score(lead.id)
        profile = self._calculate_profile_score(lead)
        demographic = self._calculate_demographic_score(lead)
        behavioral = self._calculate_behavioral_score(lead.id)

        total = round(min(engagement + profile + demographic + behavioral, 100), 1)

        return {
            "lead_id": lead.id,
            "owner_id": lead.owner_id,
            "lead_name": lead.name,
            "total": total,
            "engagement": round(engagement, 1),
            "profile": round(profile, 1),
            "demographic": round(demographic, 1),
            "behavioral": round(behavioral, 1),
        }

    # -- 1. Engagement (0-30) ------------------------------------------------

    def _calculate_engagement_score(self, lead_id: int) -> float:
        """Score based on Activity volume, recency, and diversity."""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        activities = (
            self.db.query(Activity)
            .filter(
                Activity.lead_id == lead_id,
                Activity.organization_id == self.org_id,
                Activity.created_at >= thirty_days_ago,
            )
            .all()
        )

        if not activities:
            return 0.0

        # Volume: up to 15 pts (1.5 pts per activity, capped at 10 activities)
        volume_score = min(len(activities) * 1.5, 15.0)

        # Recency: up to 10 pts — how recent is the newest activity?
        newest = max(a.created_at for a in activities)
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - newest).days
        if days_since <= 1:
            recency_score = 10.0
        elif days_since <= 3:
            recency_score = 8.0
        elif days_since <= 7:
            recency_score = 6.0
        elif days_since <= 14:
            recency_score = 3.0
        else:
            recency_score = 1.0

        # Diversity: up to 5 pts (1.25 pts per distinct type, max 4 types)
        distinct_types = {a.type for a in activities}
        diversity_score = min(len(distinct_types) * 1.25, 5.0)

        return volume_score + recency_score + diversity_score

    # -- 2. Profile completeness (0-20) --------------------------------------

    def _calculate_profile_score(self, lead: Lead) -> float:
        """Score based on how complete the lead's profile data is."""
        score = 0.0
        if lead.email:
            score += 5.0
        if lead.phone:
            score += 5.0
        if lead.loan_amount is not None:
            score += 3.0
        if lead.credit_score is not None:
            score += 4.0
        if lead.source:
            score += 3.0
        return score

    # -- 3. Demographic fit (0-25) -------------------------------------------

    def _calculate_demographic_score(self, lead: Lead) -> float:
        """Score based on credit-score tier and loan-amount sweet spot."""
        score = 0.0

        if lead.credit_score is not None:
            cs = lead.credit_score
            if cs >= 740:
                score += 25.0
            elif cs >= 700:
                score += 20.0
            elif cs >= 660:
                score += 15.0
            else:
                score += 5.0
        # No credit score → 0 demographic points.

        # Loan-amount sweet spot bonus
        if lead.loan_amount is not None:
            amt = float(lead.loan_amount)
            if 200_000 <= amt <= 800_000:
                score += 5.0

        return min(score, 25.0)

    # -- 4. Behavioral signals (0-25) ----------------------------------------

    def _calculate_behavioral_score(self, lead_id: int) -> float:
        """Score based on document uploads, portal logins, and outreach responses."""
        score = 0.0

        # Documents uploaded: +5 per doc, max 15
        doc_count = (
            self.db.query(func.count(Document.id))
            .filter(
                Document.borrower_id == lead_id,
                Document.organization_id == self.org_id,
                Document.status == "active",
            )
            .scalar()
        ) or 0
        score += min(doc_count * 5.0, 15.0)

        # Portal login activity (look for "portal_login" type activities)
        portal_logins = (
            self.db.query(func.count(Activity.id))
            .filter(
                Activity.lead_id == lead_id,
                Activity.organization_id == self.org_id,
                Activity.content.ilike("%portal%login%"),
            )
            .scalar()
        ) or 0
        if portal_logins > 0:
            score += 5.0

        # Responded to outreach (inbound email/call after outbound)
        responses = (
            self.db.query(func.count(Activity.id))
            .filter(
                Activity.lead_id == lead_id,
                Activity.organization_id == self.org_id,
                Activity.content.ilike("%responded%"),
            )
            .scalar()
        ) or 0
        if responses > 0:
            score += 5.0

        return min(score, 25.0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _update_lead_score(self, lead: Lead, score_data: dict) -> None:
        """Write the composite score to the lead and log an Activity."""
        previous_score = lead.ai_score or 0
        new_score = int(round(score_data["total"]))

        lead.ai_score = new_score

        # Persist breakdown in user_metadata
        meta = dict(lead.user_metadata or {})
        meta["score_breakdown"] = {
            "engagement": score_data["engagement"],
            "profile": score_data["profile"],
            "demographic": score_data["demographic"],
            "behavioral": score_data["behavioral"],
        }
        meta["last_scored_at"] = datetime.now(timezone.utc).isoformat()
        lead.user_metadata = meta

        # Record score-change activity only when the score actually changed
        if new_score != previous_score:
            direction = "increased" if new_score > previous_score else "decreased"
            activity = Activity(
                organization_id=self.org_id,
                lead_id=lead.id,
                type=ActivityType.NOTE,
                content=(
                    f"AI score {direction}: {previous_score} -> {new_score} "
                    f"(E:{score_data['engagement']} P:{score_data['profile']} "
                    f"D:{score_data['demographic']} B:{score_data['behavioral']})"
                ),
            )
            self.db.add(activity)

    # ------------------------------------------------------------------
    # Hot-lead identification & notifications
    # ------------------------------------------------------------------

    def _identify_hot_leads(self, scored_leads: list[dict]) -> list[dict]:
        """Return leads whose score is >= the hot threshold."""
        threshold = self.config.get("hot_threshold", 70)
        return [s for s in scored_leads if s["total"] >= threshold]

    def _notify_hot_leads(self, hot_leads: list[dict]) -> None:
        """Create a Notification for each hot lead's assigned LO."""
        for lead_data in hot_leads:
            owner_id = lead_data.get("owner_id")
            if not owner_id:
                continue

            notification = Notification(
                organization_id=self.org_id,
                user_id=owner_id,
                type="hot_lead",
                title="Hot Lead Alert",
                message=(
                    f"{lead_data['lead_name']} scored {int(lead_data['total'])}/100 — "
                    f"engagement {lead_data['engagement']}, profile {lead_data['profile']}, "
                    f"demographic {lead_data['demographic']}, behavioral {lead_data['behavioral']}. "
                    "Review and follow up promptly."
                ),
                link=f"/leads/{lead_data['lead_id']}",
            )
            self.db.add(notification)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_bucket(score: float) -> str:
        if score <= 25:
            return "0-25"
        if score <= 50:
            return "26-50"
        if score <= 75:
            return "51-75"
        return "76-100"
