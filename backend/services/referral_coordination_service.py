"""
Referral Coordination Service (Module 7)

Manages referral partner relationships, attribution tracking, partner
notifications, and commission coordination.

Integrates with:
    - database/models/referral.py (ReferralPartner, LoanTeamMember, MUMClient)
    - services/notification_service.py (partner notifications)
    - services/channel_adapter_service.py (multi-channel partner updates)

Usage:
    from services.referral_coordination_service import ReferralCoordinationService
    service = ReferralCoordinationService(db)
    result = service.track_referral(lead_id=123, partner_id=456)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# PARTNER TIERS & RULES
# =============================================================================

LOYALTY_TIERS = {
    "bronze": {
        "min_referrals": 0,
        "min_closed": 0,
        "update_frequency": "milestone_only",
        "description": "New or low-activity partner",
    },
    "silver": {
        "min_referrals": 3,
        "min_closed": 1,
        "update_frequency": "weekly_digest",
        "description": "Active partner with conversions",
    },
    "gold": {
        "min_referrals": 10,
        "min_closed": 5,
        "update_frequency": "real_time",
        "description": "High-value partner with strong track record",
    },
    "platinum": {
        "min_referrals": 25,
        "min_closed": 15,
        "update_frequency": "real_time",
        "description": "Top-tier strategic partner",
    },
}

# Milestone notifications sent to partners
PARTNER_MILESTONES = [
    "pre_approved",
    "under_contract",
    "appraisal_ordered",
    "appraisal_received",
    "clear_to_close",
    "closing_scheduled",
    "funded",
]

# Partner categories with display names
PARTNER_CATEGORIES = {
    "realtor": "Real Estate Agent",
    "builder": "Builder/Developer",
    "financial_advisor": "Financial Advisor",
    "cpa": "CPA/Accountant",
    "attorney": "Attorney",
    "insurance_agent": "Insurance Agent",
    "past_client": "Past Client",
    "other": "Other",
}


# =============================================================================
# REFERRAL COORDINATION SERVICE
# =============================================================================

class ReferralCoordinationService:
    """
    Manages referral partner relationships, attribution, and coordination.

    Responsibilities:
    - Track referral sources on leads and loans
    - Maintain partner profiles with activity metrics
    - Send milestone updates to partners
    - Calculate reciprocity scores
    - Manage loyalty tier progression
    - Generate partner performance reports
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # REFERRAL TRACKING
    # =========================================================================

    def track_referral(
        self,
        lead_id: int,
        partner_id: Optional[int] = None,
        partner_name: Optional[str] = None,
        partner_type: str = "realtor",
        source_details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a referral attribution on a lead.

        Args:
            lead_id: The lead being referred
            partner_id: Existing partner ID (if known)
            partner_name: Partner name (used to find or create)
            partner_type: Category of partner
            source_details: Additional context about the referral
        """
        # Find or create partner
        partner = None
        if partner_id:
            partner = self.db.execute(text(
                "SELECT * FROM referral_partners WHERE id = :id"
            ), {"id": partner_id}).mappings().first()
        elif partner_name:
            partner = self.db.execute(text(
                "SELECT * FROM referral_partners WHERE name ILIKE :name LIMIT 1"
            ), {"name": f"%{partner_name}%"}).mappings().first()

        if not partner and partner_name:
            # Create new partner
            self.db.execute(text("""
                INSERT INTO referral_partners (name, business_name, contact_name, category, type, status, created_at)
                VALUES (:name, :name, :name, :category, :type, 'active', NOW())
            """), {
                "name": partner_name,
                "category": partner_type,
                "type": partner_type,
            })
            self.db.flush()
            partner = self.db.execute(text(
                "SELECT * FROM referral_partners WHERE name = :name ORDER BY id DESC LIMIT 1"
            ), {"name": partner_name}).mappings().first()

        if not partner:
            return {"error": "Could not find or create partner", "success": False}

        partner_id = partner["id"]

        # Update lead with referral source
        self.db.execute(text("""
            UPDATE leads
            SET referral_partner_id = :partner_id,
                source = :source,
                source_detail = :details
            WHERE id = :lead_id
        """), {
            "partner_id": partner_id,
            "source": f"referral_{partner_type}",
            "details": source_details or f"Referred by {partner['name']}",
            "lead_id": lead_id,
        })

        # Increment partner referral count
        self.db.execute(text("""
            UPDATE referral_partners
            SET referrals_in = COALESCE(referrals_in, 0) + 1,
                last_interaction = NOW()
            WHERE id = :id
        """), {"id": partner_id})

        self.db.commit()

        # Check tier upgrade
        tier_change = self._check_tier_upgrade(partner_id)

        return {
            "success": True,
            "lead_id": lead_id,
            "partner_id": partner_id,
            "partner_name": partner["name"],
            "partner_type": partner_type,
            "tier_change": tier_change,
        }

    # =========================================================================
    # PARTNER NOTIFICATIONS
    # =========================================================================

    def notify_partner_milestone(
        self,
        loan_id: int,
        milestone: str,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a milestone update to the referral partner on a loan.

        Args:
            loan_id: The loan that reached a milestone
            milestone: The milestone name (e.g., 'clear_to_close')
            details: Additional context
        """
        if milestone not in PARTNER_MILESTONES:
            return {"error": f"Unknown milestone: {milestone}", "sent": False}

        # Find the partner for this loan
        loan_partner = self.db.execute(text("""
            SELECT
                l.id as loan_id, l.loan_number, l.borrower_name,
                rp.id as partner_id, rp.name as partner_name,
                rp.email as partner_email, rp.phone as partner_phone,
                rp.loyalty_tier
            FROM loans l
            JOIN leads ld ON ld.id = l.lead_id
            JOIN referral_partners rp ON rp.id = ld.referral_partner_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).mappings().first()

        if not loan_partner:
            return {"sent": False, "reason": "No referral partner found for this loan"}

        # Check partner preferences for update frequency
        tier = LOYALTY_TIERS.get(loan_partner["loyalty_tier"] or "bronze", LOYALTY_TIERS["bronze"])

        # Milestone-only partners only get key milestones
        key_milestones = {"pre_approved", "clear_to_close", "funded"}
        if tier["update_frequency"] == "milestone_only" and milestone not in key_milestones:
            return {
                "sent": False,
                "reason": f"Partner tier '{loan_partner['loyalty_tier']}' only receives key milestone updates",
            }

        # Build notification
        milestone_display = milestone.replace("_", " ").title()
        message = (
            f"Update on {loan_partner['borrower_name']} "
            f"(Loan #{loan_partner['loan_number']}): {milestone_display}"
        )
        if details:
            message += f" — {details}"

        notification = {
            "partner_id": loan_partner["partner_id"],
            "partner_name": loan_partner["partner_name"],
            "loan_id": loan_id,
            "milestone": milestone,
            "message": message,
            "channel": "email",
            "sent": True,
        }

        # Log the notification
        self.db.execute(text("""
            INSERT INTO integration_logs
                (integration_name, action, status, request_data, created_at)
            VALUES
                ('referral_notification', :action, 'sent', :data, NOW())
        """), {
            "action": f"milestone_{milestone}",
            "data": str(notification),
        })
        self.db.commit()

        logger.info(
            f"Partner notification sent: {loan_partner['partner_name']} "
            f"re: {milestone} on loan {loan_id}"
        )

        return notification

    # =========================================================================
    # RECIPROCITY SCORING
    # =========================================================================

    def calculate_reciprocity_score(self, partner_id: int) -> Dict[str, Any]:
        """
        Calculate a reciprocity score for a partner based on bidirectional activity.

        Scores: referrals sent to us vs referrals we send to them,
        close rates, responsiveness, and engagement.
        """
        partner = self.db.execute(text("""
            SELECT
                rp.*,
                COUNT(DISTINCT ld.id) as total_leads_referred,
                COUNT(DISTINCT CASE WHEN ld.status = 'Converted' THEN ld.id END) as converted_leads,
                COUNT(DISTINCT lo.id) as total_loans,
                COUNT(DISTINCT CASE WHEN lo.status = 'Funded' THEN lo.id END) as funded_loans,
                COALESCE(SUM(CASE WHEN lo.status = 'Funded' THEN lo.loan_amount END), 0) as funded_volume
            FROM referral_partners rp
            LEFT JOIN leads ld ON ld.referral_partner_id = rp.id
            LEFT JOIN loans lo ON lo.lead_id = ld.id
            WHERE rp.id = :id
            GROUP BY rp.id
        """), {"id": partner_id}).mappings().first()

        if not partner:
            return {"error": f"Partner {partner_id} not found"}

        # Calculate score components (0-100 each)
        referral_volume_score = min(int(partner["total_leads_referred"] or 0) * 10, 100)
        conversion_rate = (
            (int(partner["converted_leads"] or 0) / int(partner["total_leads_referred"] or 1)) * 100
            if partner["total_leads_referred"]
            else 0
        )
        conversion_score = min(conversion_rate, 100)
        funding_score = min(int(partner["funded_loans"] or 0) * 15, 100)
        reciprocity_in = int(partner["referrals_in"] or 0)
        reciprocity_out = int(partner["referrals_out"] or 0)
        balance = min(reciprocity_in, reciprocity_out) / max(reciprocity_in, reciprocity_out, 1)
        balance_score = balance * 100

        # Weighted composite
        total = (
            referral_volume_score * 0.25
            + conversion_score * 0.30
            + funding_score * 0.25
            + balance_score * 0.20
        )

        # Update partner record
        self.db.execute(text("""
            UPDATE referral_partners
            SET reciprocity_score = :score
            WHERE id = :id
        """), {"score": round(total, 1), "id": partner_id})
        self.db.commit()

        return {
            "partner_id": partner_id,
            "partner_name": partner["name"],
            "reciprocity_score": round(total, 1),
            "breakdown": {
                "referral_volume": round(referral_volume_score, 1),
                "conversion_rate": round(conversion_score, 1),
                "funding_success": round(funding_score, 1),
                "balance": round(balance_score, 1),
            },
            "stats": {
                "leads_referred": int(partner["total_leads_referred"] or 0),
                "converted": int(partner["converted_leads"] or 0),
                "funded": int(partner["funded_loans"] or 0),
                "funded_volume": float(partner["funded_volume"] or 0),
                "referrals_in": reciprocity_in,
                "referrals_out": reciprocity_out,
            },
            "current_tier": partner["loyalty_tier"],
        }

    # =========================================================================
    # TIER MANAGEMENT
    # =========================================================================

    def _check_tier_upgrade(self, partner_id: int) -> Optional[Dict[str, str]]:
        """Check if a partner qualifies for a tier upgrade."""
        partner = self.db.execute(text("""
            SELECT id, name, referrals_in, closed_loans, loyalty_tier
            FROM referral_partners WHERE id = :id
        """), {"id": partner_id}).mappings().first()

        if not partner:
            return None

        current_tier = partner["loyalty_tier"] or "bronze"
        referrals = int(partner["referrals_in"] or 0)
        closed = int(partner["closed_loans"] or 0)

        # Determine highest qualifying tier
        new_tier = "bronze"
        for tier_name in ["platinum", "gold", "silver"]:
            tier = LOYALTY_TIERS[tier_name]
            if referrals >= tier["min_referrals"] and closed >= tier["min_closed"]:
                new_tier = tier_name
                break

        if new_tier != current_tier:
            tier_order = ["bronze", "silver", "gold", "platinum"]
            if tier_order.index(new_tier) > tier_order.index(current_tier):
                self.db.execute(text("""
                    UPDATE referral_partners SET loyalty_tier = :tier WHERE id = :id
                """), {"tier": new_tier, "id": partner_id})
                self.db.commit()
                return {"from": current_tier, "to": new_tier, "partner": partner["name"]}

        return None

    # =========================================================================
    # PARTNER REPORTS
    # =========================================================================

    def get_partner_leaderboard(
        self,
        days: int = 90,
        limit: int = 20,
        organization_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get a ranked leaderboard of referral partners by performance.

        Args:
            days: Look-back period
            limit: Max partners to return
            organization_id: Filter by organization (multi-tenant)
        """
        params: Dict[str, Any] = {"days": days, "limit": limit}
        org_filter = ""
        if organization_id:
            org_filter = "AND rp.organization_id = :org_id"
            params["org_id"] = organization_id

        partners = self.db.execute(text(f"""
            SELECT
                rp.id, rp.name, rp.type, rp.loyalty_tier,
                rp.reciprocity_score,
                COUNT(DISTINCT ld.id) as period_referrals,
                COUNT(DISTINCT CASE WHEN lo.status = 'Funded' THEN lo.id END) as period_funded,
                COALESCE(SUM(CASE WHEN lo.status = 'Funded' THEN lo.loan_amount END), 0) as period_volume
            FROM referral_partners rp
            LEFT JOIN leads ld ON ld.referral_partner_id = rp.id
                AND ld.created_at >= NOW() - INTERVAL '{days} days'
            LEFT JOIN loans lo ON lo.lead_id = ld.id
            WHERE rp.status = 'active' {org_filter}
            GROUP BY rp.id, rp.name, rp.type, rp.loyalty_tier, rp.reciprocity_score
            HAVING COUNT(DISTINCT ld.id) > 0
            ORDER BY period_volume DESC
            LIMIT :limit
        """), params).mappings().all()

        return {
            "period_days": days,
            "partner_count": len(partners),
            "leaderboard": [
                {
                    "rank": idx + 1,
                    "partner_id": p["id"],
                    "name": p["name"],
                    "type": PARTNER_CATEGORIES.get(p["type"], p["type"]),
                    "tier": p["loyalty_tier"],
                    "reciprocity_score": float(p["reciprocity_score"] or 0),
                    "referrals": int(p["period_referrals"]),
                    "funded": int(p["period_funded"]),
                    "volume": float(p["period_volume"] or 0),
                }
                for idx, p in enumerate(partners)
            ],
        }

    def get_attribution_report(
        self,
        loan_id: Optional[int] = None,
        partner_id: Optional[int] = None,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Get referral attribution report for a loan or partner.

        Shows the full chain: partner → lead → loan → outcome.
        """
        if loan_id:
            result = self.db.execute(text("""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    l.status, l.loan_amount, l.funded_at,
                    ld.source, ld.created_at as lead_created,
                    rp.id as partner_id, rp.name as partner_name,
                    rp.type as partner_type, rp.loyalty_tier
                FROM loans l
                JOIN leads ld ON ld.id = l.lead_id
                LEFT JOIN referral_partners rp ON rp.id = ld.referral_partner_id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).mappings().first()

            if not result:
                return {"error": f"Loan {loan_id} not found"}

            return {
                "loan_id": result["loan_id"],
                "loan_number": result["loan_number"],
                "borrower": result["borrower_name"],
                "status": result["status"],
                "amount": float(result["loan_amount"] or 0),
                "source": result["source"],
                "partner": {
                    "id": result["partner_id"],
                    "name": result["partner_name"],
                    "type": result["partner_type"],
                    "tier": result["loyalty_tier"],
                } if result["partner_id"] else None,
                "timeline": {
                    "lead_created": str(result["lead_created"]) if result["lead_created"] else None,
                    "funded": str(result["funded_at"]) if result["funded_at"] else None,
                },
            }

        # Partner-level attribution
        if partner_id:
            loans = self.db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name,
                    l.status, l.loan_amount, l.funded_at
                FROM loans l
                JOIN leads ld ON ld.id = l.lead_id
                WHERE ld.referral_partner_id = :partner_id
                    AND ld.created_at >= NOW() - INTERVAL ':days days'
                ORDER BY l.created_at DESC
            """), {"partner_id": partner_id, "days": days}).mappings().all()

            return {
                "partner_id": partner_id,
                "period_days": days,
                "loans": [
                    {
                        "loan_id": lo["id"],
                        "loan_number": lo["loan_number"],
                        "borrower": lo["borrower_name"],
                        "status": lo["status"],
                        "amount": float(lo["loan_amount"] or 0),
                        "funded": str(lo["funded_at"]) if lo["funded_at"] else None,
                    }
                    for lo in loans
                ],
                "total_loans": len(loans),
                "total_volume": sum(float(lo["loan_amount"] or 0) for lo in loans),
                "funded_count": len([lo for lo in loans if lo["status"] == "Funded"]),
            }

        return {"error": "Provide either loan_id or partner_id"}
