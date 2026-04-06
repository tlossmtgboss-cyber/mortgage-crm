"""
Marketing Manager Agent

Top-level orchestrator for the marketing agent fleet. Accepts natural language
campaign descriptions from the LO, decomposes them into task queues for
sub-agents (ContentFactory, ReferralNurture, ReviewRequest), and generates
weekly marketing performance reports.

Usage:
    agent = MarketingManagerAgent(db, org_id=1)
    campaign = await agent.create_campaign(
        description="Spring purchase campaign targeting first-time buyers",
        audience={"segment": "first_time_buyer", "zip_codes": ["29401", "29403"]},
        org_id=1,
        db=session,
    )
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports to avoid circular dependencies at module load time
# ---------------------------------------------------------------------------
_models_loaded = False


def _ensure_models():
    global _models_loaded
    if _models_loaded:
        return
    # Deferred imports — only resolved when actually called
    global MarketingCampaign, Lead, Loan, ReferralPartner, User
    try:
        from models.business_operations import MarketingCampaign
    except ImportError:
        MarketingCampaign = None
    try:
        from database.models.lead_loan import Lead, Loan
    except ImportError:
        Lead = None
        Loan = None
    try:
        from database.models.referral import ReferralPartner
    except ImportError:
        ReferralPartner = None
    try:
        from database.models.user import User
    except ImportError:
        User = None
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CAMPAIGN_CHANNELS = {
    "email", "social", "content", "referral", "events",
    "google_ads", "facebook", "linkedin", "organic", "other",
}

VALID_CAMPAIGN_TYPES = {
    "awareness", "acquisition", "retention", "reactivation",
}

# Sub-agent task types that the manager can dispatch
TASK_TYPES = {
    "content_blog",
    "content_social",
    "content_email",
    "referral_nurture",
    "referral_market_report",
    "review_sequence",
}


class MarketingManagerAgent:
    """
    Top-level marketing orchestrator.

    Coordinates ContentFactory, ReferralNurture, ReviewRequest, and
    (future) ListingPartner / SeminarHost agents by decomposing
    campaign descriptions into structured task queues.
    """

    def __init__(self, db: Optional[Session] = None, org_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    # ======================================================================
    # CAMPAIGN LIFECYCLE
    # ======================================================================

    async def create_campaign(
        self,
        description: str,
        audience: dict,
        org_id: int,
        db: Session,
    ) -> dict:
        """
        Accept a natural-language campaign brief, decompose into a task queue
        for sub-agents, and persist the campaign record.

        Returns a dict with campaign metadata and the generated task queue.
        """
        _ensure_models()

        # 1. Parse the description into structured components
        parsed = self._parse_campaign_description(description, audience)

        # 2. Build the task queue for sub-agents
        task_queue = self._build_task_queue(parsed)

        # 3. Persist campaign record (if model is available)
        campaign_id = str(uuid.uuid4())
        campaign_record: Dict[str, Any] = {
            "id": campaign_id,
            "org_id": org_id,
            "name": parsed.get("name", description[:80]),
            "description": description,
            "channel": parsed.get("channel", "content"),
            "campaign_type": parsed.get("campaign_type", "acquisition"),
            "target_audience": audience,
            "status": "draft",
            "task_queue": task_queue,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if MarketingCampaign is not None:
            try:
                mc = MarketingCampaign(
                    organization_id=org_id,
                    name=parsed.get("name", description[:80]),
                    channel=parsed.get("channel", "content"),
                    campaign_type=parsed.get("campaign_type", "acquisition"),
                    target_audience=audience,
                    status="draft",
                    description=description,
                    start_date=datetime.now(timezone.utc).date(),
                )
                db.add(mc)
                db.flush()
                campaign_record["id"] = str(mc.id)
                logger.info("Campaign %s persisted for org %s", mc.id, org_id)
            except Exception as e:
                logger.exception("Failed to persist campaign: %s", e)
                db.rollback()

        return {
            "campaign": campaign_record,
            "task_queue": task_queue,
            "task_count": len(task_queue),
        }

    async def get_campaign_status(self, campaign_id: int, db: Session) -> dict:
        """
        Return current status and metrics for a campaign.
        """
        _ensure_models()

        if MarketingCampaign is None:
            return {"error": "MarketingCampaign model not available"}

        try:
            campaign = db.query(MarketingCampaign).filter(
                MarketingCampaign.id == campaign_id,
            ).first()
        except Exception as e:
            logger.exception("Error fetching campaign %s: %s", campaign_id, e)
            return {"error": str(e)}

        if campaign is None:
            return {"error": "Campaign not found", "campaign_id": campaign_id}

        return {
            "id": str(campaign.id),
            "name": campaign.name,
            "channel": campaign.channel,
            "campaign_type": campaign.campaign_type,
            "status": campaign.status,
            "budget": float(campaign.budget) if campaign.budget else None,
            "spend_to_date": float(campaign.spend_to_date) if campaign.spend_to_date else 0.0,
            "target_audience": campaign.target_audience,
            "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
            "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        }

    # ======================================================================
    # WEEKLY PERFORMANCE REPORT
    # ======================================================================

    async def generate_weekly_report(self, org_id: int, db: Session) -> dict:
        """
        Aggregate marketing metrics over the past 7 days and produce a
        structured performance report covering campaigns, content output,
        referral activity, and review collection.
        """
        _ensure_models()

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        report: Dict[str, Any] = {
            "org_id": org_id,
            "period_start": week_ago.isoformat(),
            "period_end": now.isoformat(),
            "generated_at": now.isoformat(),
            "campaigns": {},
            "content": {},
            "referrals": {},
            "reviews": {},
            "summary": "",
        }

        # --- Campaign metrics ---
        if MarketingCampaign is not None:
            try:
                active_campaigns = db.query(MarketingCampaign).filter(
                    and_(
                        MarketingCampaign.organization_id == org_id,
                        MarketingCampaign.status.in_(["active", "draft"]),
                    )
                ).all()
                report["campaigns"] = {
                    "active_count": len(active_campaigns),
                    "total_budget": sum(
                        float(c.budget) for c in active_campaigns if c.budget
                    ),
                    "total_spend": sum(
                        float(c.spend_to_date) for c in active_campaigns if c.spend_to_date
                    ),
                }
            except Exception as e:
                logger.exception("Campaign metrics query failed: %s", e)
                report["campaigns"] = {"error": str(e)}

        # --- Lead acquisition this week ---
        if Lead is not None:
            try:
                new_leads = db.query(func.count(Lead.id)).filter(
                    and_(
                        Lead.organization_id == org_id,
                        Lead.created_at >= week_ago,
                    )
                ).scalar() or 0
                report["leads_acquired"] = new_leads
            except Exception as e:
                logger.exception("Lead count query failed: %s", e)

        # --- Referral partner activity ---
        if ReferralPartner is not None:
            try:
                active_partners = db.query(func.count(ReferralPartner.id)).filter(
                    and_(
                        ReferralPartner.organization_id == org_id,
                        ReferralPartner.status == "active",
                    )
                ).scalar() or 0
                report["referrals"] = {"active_partners": active_partners}
            except Exception as e:
                logger.exception("Referral partner query failed: %s", e)

        # --- Funded loans (review pipeline) ---
        if Loan is not None:
            try:
                funded_this_week = db.query(func.count(Loan.id)).filter(
                    and_(
                        Loan.organization_id == org_id,
                        Loan.stage == "FUNDED",
                        Loan.updated_at >= week_ago,
                    )
                ).scalar() or 0
                report["reviews"]["funded_loans_eligible"] = funded_this_week
            except Exception as e:
                logger.exception("Funded loan query failed: %s", e)

        report["summary"] = self._build_report_summary(report)
        return report

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    def _parse_campaign_description(
        self, description: str, audience: dict
    ) -> Dict[str, Any]:
        """
        Extract structured campaign parameters from a natural-language brief.
        Uses keyword heuristics; can be upgraded to LLM-based extraction.
        """
        desc_lower = description.lower()

        # Infer channel
        channel = "content"
        for ch in VALID_CAMPAIGN_CHANNELS:
            if ch.replace("_", " ") in desc_lower:
                channel = ch
                break

        # Infer campaign type
        campaign_type = "acquisition"
        for ct in VALID_CAMPAIGN_TYPES:
            if ct in desc_lower:
                campaign_type = ct
                break

        # Derive campaign name from first sentence or first 80 chars
        name = description.split(".")[0].strip()[:80] if "." in description else description[:80]

        # Extract content types mentioned
        content_types: List[str] = []
        if any(w in desc_lower for w in ("blog", "article", "post")):
            content_types.append("blog")
        if any(w in desc_lower for w in ("social", "linkedin", "facebook", "instagram")):
            content_types.append("social")
        if any(w in desc_lower for w in ("email", "drip", "newsletter")):
            content_types.append("email")
        if any(w in desc_lower for w in ("referral", "partner", "realtor")):
            content_types.append("referral")
        if any(w in desc_lower for w in ("review", "testimonial")):
            content_types.append("review")

        if not content_types:
            content_types = ["blog", "social", "email"]

        return {
            "name": name,
            "channel": channel,
            "campaign_type": campaign_type,
            "content_types": content_types,
            "audience": audience,
        }

    def _build_task_queue(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Translate parsed campaign parameters into an ordered task queue
        for the sub-agents.
        """
        tasks: List[Dict[str, Any]] = []
        priority = 0

        for ct in parsed.get("content_types", []):
            priority += 1
            if ct == "blog":
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "content_blog",
                    "agent": "ContentFactoryAgent",
                    "priority": priority,
                    "status": "pending",
                    "params": {
                        "topic": parsed.get("name", ""),
                        "audience": parsed.get("audience", {}),
                    },
                })
            elif ct == "social":
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "content_social",
                    "agent": "ContentFactoryAgent",
                    "priority": priority,
                    "status": "pending",
                    "params": {
                        "topic": parsed.get("name", ""),
                        "platforms": ["linkedin", "facebook", "instagram"],
                        "audience": parsed.get("audience", {}),
                    },
                })
            elif ct == "email":
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "content_email",
                    "agent": "ContentFactoryAgent",
                    "priority": priority,
                    "status": "pending",
                    "params": {
                        "campaign_name": parsed.get("name", ""),
                        "audience": parsed.get("audience", {}),
                    },
                })
            elif ct == "referral":
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "referral_nurture",
                    "agent": "ReferralNurtureAgent",
                    "priority": priority,
                    "status": "pending",
                    "params": {"audience": parsed.get("audience", {})},
                })
            elif ct == "review":
                tasks.append({
                    "id": str(uuid.uuid4()),
                    "type": "review_sequence",
                    "agent": "ReviewRequestAgent",
                    "priority": priority,
                    "status": "pending",
                    "params": {},
                })

        return tasks

    def _build_report_summary(self, report: Dict[str, Any]) -> str:
        """Generate a human-readable one-paragraph summary from report data."""
        parts: List[str] = []

        campaigns = report.get("campaigns", {})
        if isinstance(campaigns, dict) and "active_count" in campaigns:
            parts.append(
                f"{campaigns['active_count']} active campaign(s) "
                f"with ${campaigns.get('total_spend', 0):,.2f} spend "
                f"of ${campaigns.get('total_budget', 0):,.2f} budget"
            )

        leads = report.get("leads_acquired")
        if leads is not None:
            parts.append(f"{leads} new lead(s) acquired")

        referrals = report.get("referrals", {})
        if isinstance(referrals, dict) and "active_partners" in referrals:
            parts.append(f"{referrals['active_partners']} active referral partner(s)")

        reviews = report.get("reviews", {})
        if isinstance(reviews, dict) and "funded_loans_eligible" in reviews:
            parts.append(
                f"{reviews['funded_loans_eligible']} funded loan(s) eligible for review requests"
            )

        return ". ".join(parts) + "." if parts else "No data available for this period."
