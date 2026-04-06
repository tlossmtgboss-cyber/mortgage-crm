"""
Referral Nurture Agent

Manages realtor / CPA / financial planner partner relationships by:
- Sending milestone updates on loans involving their referrals (target: within 15 min of stage change)
- Generating co-branded content for partners
- Delivering scheduled market reports
- Running automated nurture cycles across the partner book

Usage:
    agent = ReferralNurtureAgent()
    result = await agent.send_milestone_update(partner_id=12, loan_id=99, milestone="CTC", db=session)
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports
# ---------------------------------------------------------------------------
_models_loaded = False


def _ensure_models():
    global _models_loaded
    if _models_loaded:
        return
    global ReferralPartner, Lead, Loan, User
    try:
        from database.models.referral import ReferralPartner
    except ImportError:
        ReferralPartner = None
    try:
        from database.models.lead_loan import Lead, Loan
    except ImportError:
        Lead = None
        Loan = None
    try:
        from database.models.user import User
    except ImportError:
        User = None
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Loan stages that trigger partner notifications
NOTIFICATION_MILESTONES = {
    "APPLICATION": "Application received",
    "DISCLOSED": "Initial disclosures sent",
    "PROCESSING": "File entered processing",
    "SUBMITTED": "Submitted to underwriting",
    "CONDITIONAL_APPROVAL": "Conditional approval received",
    "CTC": "Clear to close",
    "CLEAR_TO_CLOSE": "Clear to close",
    "CLOSING": "Closing scheduled",
    "FUNDED": "Loan funded — congratulations!",
}

# SLA: partner notification within 15 minutes of stage change
MILESTONE_SLA_MINUTES = 15

# Nurture cadence tiers based on partner loyalty
NURTURE_CADENCE_DAYS = {
    "platinum": 7,
    "gold": 14,
    "silver": 21,
    "bronze": 30,
}


class ReferralNurtureAgent:
    """
    Manages referral partner relationships with automated milestone
    updates, co-branded content, and market reports.
    """

    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    # ======================================================================
    # MILESTONE UPDATES
    # ======================================================================

    async def send_milestone_update(
        self,
        partner_id: int,
        loan_id: int,
        milestone: str,
        db: Session,
    ) -> dict:
        """
        Send a milestone update to a referral partner when a referred
        loan reaches a key stage. Target SLA: within 15 minutes of the
        stage change event.

        Returns status dict with notification details.
        """
        _ensure_models()

        now = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "partner_id": partner_id,
            "loan_id": loan_id,
            "milestone": milestone,
            "timestamp": now.isoformat(),
            "notification_sent": False,
            "channels": [],
        }

        # Load partner
        partner = self._load_partner(partner_id, db)
        if partner is None:
            result["error"] = "Partner not found"
            return result

        # Load loan info (no borrower PII shared with partner)
        loan_info = self._load_loan_summary(loan_id, db)
        if loan_info is None:
            result["error"] = "Loan not found"
            return result

        # Build notification content
        milestone_label = NOTIFICATION_MILESTONES.get(
            milestone.upper(), f"Stage update: {milestone}"
        )

        notification = {
            "subject": f"Loan Update: {milestone_label}",
            "body": self._build_milestone_body(partner, loan_info, milestone_label),
            "partner_name": partner.get("name", "Partner"),
            "partner_email": partner.get("email"),
            "partner_phone": partner.get("phone"),
        }

        # Determine notification channels
        channels: List[str] = []
        if notification["partner_email"]:
            channels.append("email")
        if notification["partner_phone"]:
            channels.append("sms")

        result["notification"] = notification
        result["channels"] = channels
        result["notification_sent"] = len(channels) > 0
        result["sla_target_minutes"] = MILESTONE_SLA_MINUTES

        # Update partner's last_interaction timestamp
        self._touch_partner_interaction(partner_id, db)

        logger.info(
            "Milestone update for partner %s on loan %s: %s via %s",
            partner_id, loan_id, milestone, channels,
        )
        return result

    # ======================================================================
    # MARKET REPORTS
    # ======================================================================

    async def generate_market_report(
        self,
        partner_id: int,
        db: Session,
    ) -> dict:
        """
        Generate a co-branded market report for a specific referral partner.
        Includes local market data, recent activity summary, and pipeline
        status for their referrals.
        """
        _ensure_models()

        partner = self._load_partner(partner_id, db)
        if partner is None:
            return {"error": "Partner not found", "partner_id": partner_id}

        # Aggregate referral stats
        stats = self._get_partner_referral_stats(partner_id, db)

        report = {
            "id": str(uuid.uuid4()),
            "partner_id": partner_id,
            "partner_name": partner.get("name", ""),
            "partner_company": partner.get("company", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "referral_stats": stats,
            "market_snapshot": self._build_market_snapshot(),
            "co_branded": True,
            "status": "ready",
        }

        # Touch last_interaction
        self._touch_partner_interaction(partner_id, db)

        return report

    # ======================================================================
    # NURTURE CYCLE
    # ======================================================================

    async def run_nurture_cycle(
        self,
        org_id: int,
        db: Session,
    ) -> dict:
        """
        Execute a nurture cycle for all active partners in the org.
        Partners are contacted based on their loyalty tier cadence.
        Returns a summary of actions taken.
        """
        _ensure_models()

        if ReferralPartner is None:
            return {"error": "ReferralPartner model not available"}

        now = datetime.now(timezone.utc)
        actions: List[Dict[str, Any]] = []
        skipped = 0

        try:
            partners = db.query(ReferralPartner).filter(
                and_(
                    ReferralPartner.organization_id == org_id,
                    ReferralPartner.status == "active",
                )
            ).all()
        except Exception as e:
            logger.exception("Error loading partners for org %s: %s", org_id, e)
            return {"error": str(e)}

        for partner in partners:
            tier = (partner.loyalty_tier or "bronze").lower()
            cadence_days = NURTURE_CADENCE_DAYS.get(tier, 30)
            cutoff = now - timedelta(days=cadence_days)

            last = partner.last_interaction
            if last and last.replace(tzinfo=timezone.utc) > cutoff:
                skipped += 1
                continue

            # Partner is due for a touchpoint
            action = await self._execute_nurture_touch(partner, db)
            actions.append(action)

        return {
            "org_id": org_id,
            "cycle_run_at": now.isoformat(),
            "partners_evaluated": len(partners),
            "actions_taken": len(actions),
            "skipped_not_due": skipped,
            "actions": actions,
        }

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    def _load_partner(self, partner_id: int, db: Session) -> Optional[dict]:
        """Load a referral partner by ID, return as dict."""
        _ensure_models()
        if ReferralPartner is None:
            return None
        try:
            p = db.query(ReferralPartner).filter(
                ReferralPartner.id == partner_id
            ).first()
            if p is None:
                return None
            return {
                "id": p.id,
                "name": p.name,
                "company": p.company,
                "email": p.email,
                "phone": p.phone,
                "category": p.category,
                "loyalty_tier": p.loyalty_tier,
                "referrals_in": p.referrals_in,
                "closed_loans": p.closed_loans,
                "status": p.status,
            }
        except Exception as e:
            logger.exception("Error loading partner %s: %s", partner_id, e)
            return None

    def _load_loan_summary(self, loan_id: int, db: Session) -> Optional[dict]:
        """
        Load a minimal loan summary for milestone notifications.
        Excludes borrower PII — partners only see stage and property info.
        """
        _ensure_models()
        if Loan is None:
            return None
        try:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if loan is None:
                return None
            return {
                "id": loan.id,
                "stage": loan.stage,
                "loan_amount": float(loan.loan_amount) if hasattr(loan, "loan_amount") and loan.loan_amount else None,
                "property_address": getattr(loan, "property_address", None),
                "property_city": getattr(loan, "property_city", None),
                "property_state": getattr(loan, "property_state", None),
            }
        except Exception as e:
            logger.exception("Error loading loan %s: %s", loan_id, e)
            return None

    def _build_milestone_body(
        self, partner: dict, loan_info: dict, milestone_label: str,
    ) -> str:
        """Build notification body text for a milestone update."""
        property_loc = ""
        if loan_info.get("property_city") and loan_info.get("property_state"):
            property_loc = f" for the property in {loan_info['property_city']}, {loan_info['property_state']}"

        return (
            f"Hi {partner.get('name', 'Partner')},\n\n"
            f"Great news! The loan you referred{property_loc} has reached a new milestone:\n\n"
            f"  Status: {milestone_label}\n\n"
            f"Thank you for your continued partnership. I'll keep you posted as "
            f"we move toward closing.\n\n"
            f"Best regards"
        )

    def _get_partner_referral_stats(self, partner_id: int, db: Session) -> dict:
        """Aggregate referral statistics for a partner."""
        _ensure_models()
        if ReferralPartner is None:
            return {}
        try:
            p = db.query(ReferralPartner).filter(
                ReferralPartner.id == partner_id
            ).first()
            if p is None:
                return {}
            return {
                "referrals_in": p.referrals_in or 0,
                "referrals_out": p.referrals_out or 0,
                "closed_loans": p.closed_loans or 0,
                "volume": float(p.volume) if p.volume else 0.0,
                "reciprocity_score": float(p.reciprocity_score) if p.reciprocity_score else 0.0,
            }
        except Exception as e:
            logger.exception("Error getting referral stats for partner %s: %s", partner_id, e)
            return {}

    def _build_market_snapshot(self) -> dict:
        """
        Build a generic market snapshot. In production this would pull
        from a rate feed or market data service.
        """
        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "note": "Market data integration pending — placeholder snapshot",
            "trends": [
                "Mortgage applications remain steady quarter over quarter",
                "Inventory levels improving in suburban markets",
                "First-time buyer programs seeing increased activity",
            ],
        }

    def _touch_partner_interaction(self, partner_id: int, db: Session) -> None:
        """Update the partner's last_interaction timestamp."""
        _ensure_models()
        if ReferralPartner is None:
            return
        try:
            partner = db.query(ReferralPartner).filter(
                ReferralPartner.id == partner_id
            ).first()
            if partner:
                partner.last_interaction = datetime.now(timezone.utc)
                db.flush()
        except Exception as e:
            logger.exception("Failed to update last_interaction for partner %s: %s", partner_id, e)

    async def _execute_nurture_touch(
        self, partner: Any, db: Session,
    ) -> Dict[str, Any]:
        """
        Execute a single nurture touchpoint for a partner.
        Selects the appropriate touchpoint type based on partner tier
        and recent history.
        """
        tier = (partner.loyalty_tier or "bronze").lower()
        partner_id = partner.id

        # High-tier partners get market reports; others get check-in messages
        if tier in ("platinum", "gold"):
            report = await self.generate_market_report(partner_id, db)
            return {
                "partner_id": partner_id,
                "partner_name": partner.name,
                "tier": tier,
                "touch_type": "market_report",
                "status": "generated",
            }
        else:
            # Simple check-in notification
            self._touch_partner_interaction(partner_id, db)
            return {
                "partner_id": partner_id,
                "partner_name": partner.name,
                "tier": tier,
                "touch_type": "check_in",
                "status": "queued",
                "message": f"Automated check-in with {partner.name} ({partner.company or 'N/A'})",
            }
