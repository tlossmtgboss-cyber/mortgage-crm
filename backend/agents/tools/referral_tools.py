"""
Perennia AI - Referral Partner Tools
=====================================
Tools for managing referral partners, tracking referral stats,
and linking leads to referral sources.
4 tools for referral partner management and analytics.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_currency,
    format_date,
    get_db,
)


# =============================================================================
# Referral Partner Tools (4 tools)
# =============================================================================

@mortgage_tool(
    name="get_referral_partners",
    description="List referral partners for the current user, optionally filtered by partner type (realtor, builder, cpa, attorney)",
    agent_roles=["referral_partner_manager", "lead_nurturer", "customer_intelligence"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "partner_type": "Optional filter: realtor, builder, cpa, attorney",
        "limit": "Maximum partners to return (default 50)",
    },
)
def get_referral_partners(
    partner_type: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """List referral partners filtered by owner and optional partner type."""
    from database.models.referral import ReferralPartner

    with get_db() as db:
        query = db.query(ReferralPartner).filter(
            ReferralPartner.status == "active"
        )

        if partner_type:
            query = query.filter(ReferralPartner.type == partner_type)

        query = query.order_by(ReferralPartner.name).limit(limit)
        partners = query.all()

    if not partners:
        return ToolResult.no_data("No referral partners found matching criteria")

    partner_list = []
    for p in partners:
        partner_list.append({
            "id": p.id,
            "name": p.name,
            "company": p.company,
            "type": p.type,
            "email": p.email,
            "phone": p.phone,
            "referrals_in": p.referrals_in or 0,
            "referrals_out": p.referrals_out or 0,
            "closed_loans": p.closed_loans or 0,
            "volume": float(p.volume or 0),
            "volume_formatted": format_currency(p.volume or 0),
            "reciprocity_score": p.reciprocity_score or 0,
            "loyalty_tier": p.loyalty_tier,
            "last_interaction": format_date(p.last_interaction),
            "status": p.status,
        })

    return ToolResult.success(
        data={
            "partners": partner_list,
            "total_count": len(partner_list),
            "filters_applied": {"partner_type": partner_type},
        },
        message=f"Found {len(partner_list)} referral partners",
    )


@mortgage_tool(
    name="add_referral_partner",
    description="Create a new referral partner record with name, contact info, and partner type",
    agent_roles=["referral_partner_manager", "lead_nurturer"],
    risk_level="MEDIUM",
    requires_confirmation=True,
    parameters={
        "name": "Partner full name (required)",
        "partner_type": "Type of partner: realtor, builder, cpa, attorney (required)",
        "email": "Contact email (optional)",
        "phone": "Contact phone (optional)",
        "company": "Company name (optional)",
    },
)
def add_referral_partner(
    name: str,
    partner_type: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
) -> ToolResult:
    """Create a new referral partner."""
    from database.models.referral import ReferralPartner

    with get_db() as db:
        partner = ReferralPartner(
            name=name,
            business_name=company or "",
            contact_name=name,
            category=partner_type,
            type=partner_type,
            email=email,
            phone=phone,
            company=company,
            status="active",
            loyalty_tier="bronze",
        )
        db.add(partner)
        db.flush()

        data = {
            "id": partner.id,
            "name": partner.name,
            "type": partner.type,
            "email": partner.email,
            "phone": partner.phone,
            "company": partner.company,
            "status": partner.status,
            "created_at": datetime.now().isoformat(),
        }

    return ToolResult.success(
        data=data,
        message=f"Referral partner created: {name} ({partner_type})",
    )


@mortgage_tool(
    name="get_referral_stats",
    description="Get referral statistics per partner including lead counts and conversion rates",
    agent_roles=["referral_partner_manager", "reporting_engine", "profitability_analyst"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "partner_id": "Optional partner ID to filter to a single partner",
        "time_period": "Time period for stats: 30d, 60d, 90d, 180d, 365d (default 90d)",
    },
)
def get_referral_stats(
    partner_id: Optional[int] = None,
    time_period: str = "90d",
) -> ToolResult:
    """Get referral statistics per partner."""
    # Parse time period
    days = int(time_period.replace("d", "")) if time_period.endswith("d") else 90

    params: Dict[str, Any] = {"days": days}
    partner_filter = ""
    if partner_id:
        partner_filter = "AND rp.id = :partner_id"
        params["partner_id"] = partner_id

    results = execute_query(f"""
        SELECT
            rp.id,
            rp.name,
            rp.type,
            rp.company,
            rp.loyalty_tier,
            COUNT(l.id) as total_leads,
            COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded_leads,
            COUNT(CASE WHEN l.stage NOT IN ('Dead', 'Withdrawn', 'Does Not Qualify') THEN 1 END) as active_leads,
            COALESCE(SUM(CASE WHEN l.stage = 'Funded' THEN ln.loan_amount ELSE 0 END), 0) as funded_volume
        FROM referral_partners rp
        LEFT JOIN leads l ON l.referral_partner_id = rp.id
            AND l.created_at >= CURRENT_DATE - INTERVAL '{days} days'
        LEFT JOIN loans ln ON ln.lead_id = l.id AND ln.stage = 'Funded'
        WHERE rp.status = 'active'
            {partner_filter}
        GROUP BY rp.id, rp.name, rp.type, rp.company, rp.loyalty_tier
        ORDER BY COUNT(l.id) DESC
    """, params)

    if not results:
        return ToolResult.no_data("No referral partner stats found")

    stats = []
    for r in results:
        total = r.get("total_leads", 0) or 0
        funded = r.get("funded_leads", 0) or 0
        conversion_rate = round((funded / total) * 100, 1) if total > 0 else 0.0

        stats.append({
            "partner_id": r.get("id"),
            "name": r.get("name"),
            "type": r.get("type"),
            "company": r.get("company"),
            "loyalty_tier": r.get("loyalty_tier"),
            "total_leads": total,
            "active_leads": r.get("active_leads", 0) or 0,
            "funded_leads": funded,
            "conversion_rate": conversion_rate,
            "funded_volume": float(r.get("funded_volume", 0) or 0),
            "funded_volume_formatted": format_currency(r.get("funded_volume", 0) or 0),
        })

    return ToolResult.success(
        data={
            "stats": stats,
            "total_partners": len(stats),
            "time_period": time_period,
        },
        message=f"Referral stats for {len(stats)} partners over {time_period}",
    )


@mortgage_tool(
    name="log_referral",
    description="Link a lead to a referral partner by setting the lead's referral_partner_id",
    agent_roles=["referral_partner_manager", "lead_nurturer", "ai_receptionist"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "lead_id": "Lead ID to link (required)",
        "partner_id": "Referral partner ID (required)",
        "notes": "Optional notes about the referral",
    },
)
def log_referral(
    lead_id: int,
    partner_id: int,
    notes: Optional[str] = None,
) -> ToolResult:
    """Link a lead to a referral partner."""
    from database.models.lead_loan import Lead
    from database.models.referral import ReferralPartner

    with get_db() as db:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
        if not partner:
            return ToolResult.no_data(f"Referral partner {partner_id} not found")

        lead.referral_partner_id = partner_id

        # Increment referrals_in on the partner
        partner.referrals_in = (partner.referrals_in or 0) + 1
        partner.last_interaction = datetime.now()

        if notes:
            existing_notes = partner.notes or ""
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            partner.notes = f"{existing_notes}\n[{timestamp}] Referral: {notes}".strip()

        db.flush()

        lead_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or f"Lead #{lead_id}"

        data = {
            "lead_id": lead_id,
            "lead_name": lead_name,
            "partner_id": partner_id,
            "partner_name": partner.name,
            "partner_type": partner.type,
            "notes": notes,
            "logged_at": datetime.now().isoformat(),
        }

    return ToolResult.success(
        data=data,
        message=f"Lead '{lead_name}' linked to referral partner '{partner.name}'",
    )
