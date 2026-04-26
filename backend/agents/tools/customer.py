"""
Perennia AI - Customer Intelligence Tools
Tools for the Customer Intelligence agent to analyze customer data and relationships.
Provides 360-degree view of customers, LTV analysis, churn prediction, and opportunity finding.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from enum import Enum

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single,
    format_currency, format_percentage, days_between, calculate_percentage_change,
    LoanStatus, LoanType, PropertyType, OccupancyType,
)


class RelationshipStrength(Enum):
    """Customer relationship strength levels."""
    STRONG = "strong"         # Multiple loans, referrals, responsive
    GOOD = "good"            # Active loan, good communication
    AT_RISK = "at_risk"      # Low engagement, complaints
    NEW = "new"              # Recent acquisition
    DORMANT = "dormant"      # No activity in 12+ months


class ChurnRisk(Enum):
    """Customer churn risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@mortgage_tool(
    name="get_customer_360",
    description="Get comprehensive 360-degree view of a customer including all loans, communications, and relationship data",
    agent_roles=["customer_intelligence", "lead_nurturer"],
    risk_level="LOW",
    examples=[
        "get_customer_360(customer_id='CUST123')",
        "get_customer_360(email='john@example.com')",
    ],
)
def get_customer_360(
    customer_id: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> ToolResult:
    """
    Get complete 360-degree view of a customer.

    Includes:
    - WHO: Contact info, demographics
    - WHAT: All loans (current, past, inquiries)
    - WHEN: Timeline of all interactions
    - WHERE: Properties associated
    - WHY: Loan purposes, life events
    - OPPORTUNITY: Potential for new business
    """
    # Find customer
    if customer_id:
        customer_filter = "c.id = :customer_id"
        params = {"customer_id": customer_id}
    elif email:
        customer_filter = "c.email = :email"
        params = {"email": email}
    elif phone:
        customer_filter = "c.phone = :phone OR c.phone_secondary = :phone"
        params = {"phone": phone}
    else:
        raise ToolError("Must provide customer_id, email, or phone")

    # Get customer base info
    customer_query = f"""
        SELECT
            c.id,
            c.first_name,
            c.last_name,
            c.email,
            c.phone,
            c.phone_secondary,
            c.address,
            c.city,
            c.state,
            c.zip,
            c.date_of_birth,
            c.created_at as customer_since,
            c.source as acquisition_source,
            c.preferred_contact_method,
            c.preferred_contact_time,
            c.notes,
            c.tags
        FROM contacts c
        WHERE {customer_filter}
    """

    customer = execute_single(customer_query, params)
    if not customer:
        return ToolResult.no_data("Customer not found")

    params["customer_id"] = customer["id"]

    # Get all loans (current and past)
    loans_query = """
        SELECT
            l.id,
            l.loan_number,
            l.status,
            l.loan_type,
            l.loan_purpose,
            l.loan_amount,
            l.interest_rate,
            l.property_address,
            l.property_city,
            l.property_state,
            l.created_at,
            l.funded_at,
            l.expected_close_date,
            lo.name as loan_officer_name
        FROM loans l
        LEFT JOIN users lo ON lo.id = l.loan_officer_id
        WHERE l.borrower_id = :customer_id OR l.co_borrower_id = :customer_id
        ORDER BY l.created_at DESC
    """

    loans = execute_query(loans_query, params)

    # Calculate loan statistics
    total_funded = sum(float(l["loan_amount"]) for l in loans if l["status"] == "funded")
    active_loans = [l for l in loans if l["status"] not in ("funded", "cancelled", "denied")]
    funded_loans = [l for l in loans if l["status"] == "funded"]

    # Get communication history (last 50)
    comms_query = """
        SELECT
            ch.id,
            ch.type,
            ch.direction,
            ch.subject,
            ch.summary,
            ch.sentiment,
            ch.created_at,
            u.full_name as user_name
        FROM communication_history ch
        LEFT JOIN users u ON u.id = ch.user_id
        WHERE ch.contact_id = :customer_id
        ORDER BY ch.created_at DESC
        LIMIT 50
    """

    communications = execute_query(comms_query, params)

    # Get referrals made and received
    referrals_query = """
        SELECT
            r.id,
            r.type,
            r.status,
            r.created_at,
            CASE WHEN r.referrer_id = :customer_id THEN 'made' ELSE 'received' END as direction,
            CASE WHEN r.referrer_id = :customer_id
                THEN c2.first_name || ' ' || c2.last_name
                ELSE c1.first_name || ' ' || c1.last_name
            END as other_party
        FROM referrals r
        LEFT JOIN contacts c1 ON c1.id = r.referrer_id
        LEFT JOIN contacts c2 ON c2.id = r.referred_id
        WHERE r.referrer_id = :customer_id OR r.referred_id = :customer_id
        ORDER BY r.created_at DESC
    """

    referrals = execute_query(referrals_query, params)
    referrals_made = [r for r in referrals if r["direction"] == "made"]
    referrals_received = [r for r in referrals if r["direction"] == "received"]

    # Calculate engagement metrics
    last_contact = communications[0]["created_at"] if communications else None
    days_since_contact = days_between(last_contact, datetime.now()) if last_contact else 999

    contact_frequency = len(communications) / max(days_between(customer["customer_since"], datetime.now()) / 30, 1)

    # Determine relationship strength
    if len(funded_loans) >= 2 or len(referrals_made) >= 2:
        relationship = RelationshipStrength.STRONG.value
    elif funded_loans or active_loans:
        if days_since_contact <= 30:
            relationship = RelationshipStrength.GOOD.value
        elif days_since_contact > 180:
            relationship = RelationshipStrength.AT_RISK.value
        else:
            relationship = RelationshipStrength.GOOD.value
    elif days_between(customer["customer_since"], datetime.now()) < 90:
        relationship = RelationshipStrength.NEW.value
    else:
        relationship = RelationshipStrength.DORMANT.value

    # Sentiment analysis from communications
    positive_count = sum(1 for c in communications if c.get("sentiment") == "positive")
    negative_count = sum(1 for c in communications if c.get("sentiment") == "negative")
    sentiment_score = (positive_count - negative_count) / max(len(communications), 1)

    # Calculate lifetime value
    ltv = total_funded * 0.02  # Rough estimate: 2% of funded volume

    # Build customer profile
    data = {
        "who": {
            "id": customer["id"],
            "name": f"{customer['first_name']} {customer['last_name']}",
            "email": customer["email"],
            "phone": customer["phone"],
            "phone_secondary": customer["phone_secondary"],
            "address": f"{customer['address']}, {customer['city']}, {customer['state']} {customer['zip']}",
            "customer_since": customer["customer_since"].isoformat() if customer["customer_since"] else None,
            "acquisition_source": customer["acquisition_source"],
            "preferred_contact": {
                "method": customer["preferred_contact_method"],
                "time": customer["preferred_contact_time"],
            },
            "tags": customer["tags"] or [],
        },
        "what": {
            "total_loans": len(loans),
            "funded_loans": len(funded_loans),
            "active_loans": len(active_loans),
            "total_funded_volume": total_funded,
            "total_funded_formatted": format_currency(total_funded),
            "loans": [
                {
                    "id": l["id"],
                    "loan_number": l["loan_number"],
                    "status": l["status"],
                    "type": l["loan_type"],
                    "purpose": l["loan_purpose"],
                    "amount": float(l["loan_amount"]),
                    "amount_formatted": format_currency(l["loan_amount"]),
                    "rate": float(l["interest_rate"]) if l["interest_rate"] else None,
                    "property": f"{l['property_address']}, {l['property_city']}, {l['property_state']}" if l["property_address"] else None,
                    "date": l["created_at"].isoformat() if l["created_at"] else None,
                    "loan_officer": l["loan_officer_name"],
                }
                for l in loans
            ],
        },
        "when": {
            "customer_since_date": customer["customer_since"].isoformat() if customer["customer_since"] else None,
            "customer_tenure_days": days_between(customer["customer_since"], datetime.now()) if customer["customer_since"] else 0,
            "last_contact_date": last_contact.isoformat() if last_contact else None,
            "days_since_contact": days_since_contact,
            "total_interactions": len(communications),
            "avg_contacts_per_month": round(contact_frequency, 1),
            "recent_communications": [
                {
                    "type": c["type"],
                    "direction": c["direction"],
                    "subject": c["subject"],
                    "summary": c["summary"],
                    "date": c["created_at"].isoformat() if c["created_at"] else None,
                    "by": c["user_name"],
                }
                for c in communications[:10]
            ],
        },
        "relationships": {
            "referrals_made": len(referrals_made),
            "referrals_received": len(referrals_received),
            "referral_details": [
                {
                    "direction": r["direction"],
                    "other_party": r["other_party"],
                    "status": r["status"],
                    "date": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in referrals[:10]
            ],
            "relationship_strength": relationship,
            "sentiment_score": round(sentiment_score, 2),
        },
        "value": {
            "lifetime_value": ltv,
            "lifetime_value_formatted": format_currency(ltv),
            "avg_loan_size": total_funded / len(funded_loans) if funded_loans else 0,
            "avg_loan_size_formatted": format_currency(total_funded / len(funded_loans)) if funded_loans else "$0",
        },
        "notes": customer["notes"],
    }

    return ToolResult.success(
        data=data,
        message=f"Customer 360: {customer['first_name']} {customer['last_name']} - {relationship} relationship, {len(funded_loans)} funded loans, LTV {format_currency(ltv)}",
    )


@mortgage_tool(
    name="map_relationships",
    description="Map customer's network including family, referrals, and professional connections",
    agent_roles=["customer_intelligence"],
    risk_level="LOW",
    examples=[
        "map_relationships(customer_id='CUST123')",
        "map_relationships(customer_id='CUST123', depth=2)",
    ],
)
def map_relationships(
    customer_id: str,
    depth: int = 1,
) -> ToolResult:
    """
    Map the relationship network of a customer.

    Includes:
    - Family members (co-borrowers, related addresses)
    - Referrals (given and received)
    - Professional connections (same company/employer)
    - Property connections (same address history)
    """
    params = {"customer_id": customer_id, "depth": depth}

    # Get customer
    customer = execute_single(
        "SELECT id, first_name, last_name, email, employer FROM contacts WHERE id = :customer_id",
        params
    )
    if not customer:
        return ToolResult.no_data("Customer not found")

    relationships = []

    # Co-borrowers (direct loan connections)
    coborrower_query = """
        SELECT DISTINCT
            c.id,
            c.first_name,
            c.last_name,
            c.email,
            'co_borrower' as relationship_type,
            l.loan_number,
            l.status as loan_status
        FROM loans l
        JOIN contacts c ON c.id = l.co_borrower_id
        WHERE l.borrower_id = :customer_id AND l.co_borrower_id IS NOT NULL
        UNION
        SELECT DISTINCT
            c.id,
            c.first_name,
            c.last_name,
            c.email,
            'co_borrower' as relationship_type,
            l.loan_number,
            l.status as loan_status
        FROM loans l
        JOIN contacts c ON c.id = l.borrower_id
        WHERE l.co_borrower_id = :customer_id
    """

    coborrowers = execute_query(coborrower_query, params)
    for cb in coborrowers:
        relationships.append({
            "id": cb["id"],
            "name": f"{cb['first_name']} {cb['last_name']}",
            "email": cb["email"],
            "type": "co_borrower",
            "strength": "strong",
            "context": f"Co-borrower on loan {cb['loan_number']}",
        })

    # Referral connections
    referral_query = """
        SELECT
            c.id,
            c.first_name,
            c.last_name,
            c.email,
            CASE WHEN r.referrer_id = :customer_id THEN 'referred_out' ELSE 'referred_in' END as direction,
            r.status,
            r.created_at
        FROM referrals r
        JOIN contacts c ON c.id = CASE
            WHEN r.referrer_id = :customer_id THEN r.referred_id
            ELSE r.referrer_id
        END
        WHERE r.referrer_id = :customer_id OR r.referred_id = :customer_id
    """

    referrals = execute_query(referral_query, params)
    for ref in referrals:
        relationships.append({
            "id": ref["id"],
            "name": f"{ref['first_name']} {ref['last_name']}",
            "email": ref["email"],
            "type": "referral",
            "direction": ref["direction"],
            "strength": "strong" if ref["status"] == "funded" else "medium",
            "context": f"Referral ({ref['direction'].replace('_', ' ')})",
        })

    # Same employer connections
    if customer["employer"]:
        employer_query = """
            SELECT
                c.id,
                c.first_name,
                c.last_name,
                c.email,
                c.employer
            FROM contacts c
            WHERE c.employer = :employer
                AND c.id != :customer_id
            LIMIT 20
        """
        colleagues = execute_query(employer_query, {**params, "employer": customer["employer"]})
        for col in colleagues:
            relationships.append({
                "id": col["id"],
                "name": f"{col['first_name']} {col['last_name']}",
                "email": col["email"],
                "type": "colleague",
                "strength": "weak",
                "context": f"Same employer: {col['employer']}",
            })

    # Same address history (potential family)
    address_query = """
        SELECT DISTINCT
            c.id,
            c.first_name,
            c.last_name,
            c.email,
            l.property_address
        FROM loans l
        JOIN contacts c ON c.id = l.borrower_id OR c.id = l.co_borrower_id
        WHERE l.property_address IN (
            SELECT property_address FROM loans
            WHERE (borrower_id = :customer_id OR co_borrower_id = :customer_id)
                AND property_address IS NOT NULL
        )
        AND c.id != :customer_id
    """

    address_connections = execute_query(address_query, params)
    for ac in address_connections:
        if not any(r["id"] == ac["id"] for r in relationships):  # Avoid duplicates
            relationships.append({
                "id": ac["id"],
                "name": f"{ac['first_name']} {ac['last_name']}",
                "email": ac["email"],
                "type": "address_connection",
                "strength": "medium",
                "context": f"Same property: {ac['property_address']}",
            })

    # Group by type
    by_type = {}
    for rel in relationships:
        rel_type = rel["type"]
        if rel_type not in by_type:
            by_type[rel_type] = []
        by_type[rel_type].append(rel)

    # Calculate network score
    network_score = (
        len([r for r in relationships if r["strength"] == "strong"]) * 3 +
        len([r for r in relationships if r["strength"] == "medium"]) * 2 +
        len([r for r in relationships if r["strength"] == "weak"]) * 1
    )

    data = {
        "customer": {
            "id": customer["id"],
            "name": f"{customer['first_name']} {customer['last_name']}",
        },
        "network_size": len(relationships),
        "network_score": network_score,
        "relationships": relationships,
        "by_type": {k: len(v) for k, v in by_type.items()},
        "strong_connections": len([r for r in relationships if r["strength"] == "strong"]),
        "referral_potential": len([r for r in relationships if r["type"] == "colleague"]),
    }

    return ToolResult.success(
        data=data,
        message=f"Network: {len(relationships)} connections, {data['strong_connections']} strong. Referral potential: {data['referral_potential']} colleagues.",
    )


@mortgage_tool(
    name="calculate_ltv",
    description="Calculate customer lifetime value based on loan history and referral activity",
    agent_roles=["customer_intelligence", "profitability_analyst"],
    risk_level="LOW",
    examples=[
        "calculate_ltv(customer_id='CUST123')",
        "calculate_ltv(customer_id='CUST123', include_projections=True)",
    ],
)
def calculate_ltv(
    customer_id: str,
    include_projections: bool = True,
) -> ToolResult:
    """
    Calculate comprehensive customer lifetime value.

    Includes:
    - Direct loan revenue (origination, servicing)
    - Referral value
    - Repeat business probability
    - Projected future value
    """
    params = {"customer_id": customer_id}

    # Get loan history
    loans_query = """
        SELECT
            l.id,
            l.loan_amount,
            l.interest_rate,
            l.loan_type,
            l.status,
            l.funded_at,
            l.created_at
        FROM loans l
        WHERE l.borrower_id = :customer_id OR l.co_borrower_id = :customer_id
    """

    loans = execute_query(loans_query, params)

    if not loans:
        return ToolResult.no_data("No loan history found for customer")

    # Calculate historical value
    funded_loans = [l for l in loans if l["status"] == "funded"]
    total_funded = sum(float(l["loan_amount"]) for l in funded_loans)

    # Revenue estimates (industry averages)
    avg_margin_bps = 150  # 1.5% average margin
    origination_revenue = total_funded * (avg_margin_bps / 10000)

    # Servicing revenue estimate (if retained)
    annual_servicing_bps = 25  # 0.25% annual servicing
    avg_loan_life_years = 5
    servicing_revenue = total_funded * (annual_servicing_bps / 10000) * avg_loan_life_years

    # Referral value
    referral_query = """
        SELECT COUNT(*) as count,
               COALESCE(SUM(l.loan_amount), 0) as volume
        FROM referrals r
        JOIN loans l ON l.borrower_id = r.referred_id
        WHERE r.referrer_id = :customer_id
            AND l.stage = 'Funded'
    """

    referrals = execute_single(referral_query, params)
    referral_revenue = float(referrals["volume"] or 0) * (avg_margin_bps / 10000) * 0.5  # 50% attribution

    # Total historical LTV
    historical_ltv = origination_revenue + servicing_revenue + referral_revenue

    # Projections
    projected_ltv = 0
    projection_details = {}

    if include_projections:
        # Repeat business probability based on history
        years_as_customer = max(days_between(loans[0]["created_at"], datetime.now()) / 365, 1)
        loans_per_year = len(funded_loans) / years_as_customer

        # Industry average: 7 years between refinance/move
        expected_future_loans = max(3 - len(funded_loans), 0)  # Assume 3 lifetime loans
        avg_loan_size = total_funded / len(funded_loans) if funded_loans else 350000

        projected_origination = expected_future_loans * avg_loan_size * (avg_margin_bps / 10000)

        # Referral projections (based on historical rate)
        referral_rate = referrals["count"] / years_as_customer
        projected_referrals = referral_rate * 5  # 5 year projection
        projected_referral_value = projected_referrals * avg_loan_size * (avg_margin_bps / 10000) * 0.5

        projected_ltv = projected_origination + projected_referral_value

        projection_details = {
            "expected_future_loans": expected_future_loans,
            "projected_avg_loan_size": avg_loan_size,
            "projected_origination_revenue": round(projected_origination, 2),
            "projected_referrals": round(projected_referrals, 1),
            "projected_referral_revenue": round(projected_referral_value, 2),
            "projection_years": 5,
            "confidence": "medium" if len(funded_loans) >= 2 else "low",
        }

    # Customer tier
    total_ltv = historical_ltv + projected_ltv
    if total_ltv >= 50000:
        tier = "platinum"
    elif total_ltv >= 25000:
        tier = "gold"
    elif total_ltv >= 10000:
        tier = "silver"
    else:
        tier = "bronze"

    data = {
        "customer_id": customer_id,
        "historical": {
            "total_funded_volume": total_funded,
            "total_funded_formatted": format_currency(total_funded),
            "funded_loan_count": len(funded_loans),
            "origination_revenue": round(origination_revenue, 2),
            "servicing_revenue": round(servicing_revenue, 2),
            "referral_count": referrals["count"],
            "referral_revenue": round(referral_revenue, 2),
            "total_historical_ltv": round(historical_ltv, 2),
            "total_historical_ltv_formatted": format_currency(historical_ltv),
        },
        "projected": projection_details if include_projections else None,
        "total_ltv": round(total_ltv, 2),
        "total_ltv_formatted": format_currency(total_ltv),
        "customer_tier": tier,
        "revenue_per_loan": round(origination_revenue / len(funded_loans), 2) if funded_loans else 0,
    }

    return ToolResult.success(
        data=data,
        message=f"Customer LTV: {format_currency(total_ltv)} ({tier} tier). Historical: {format_currency(historical_ltv)}, Projected: {format_currency(projected_ltv)}",
    )


@mortgage_tool(
    name="assess_churn_risk",
    description="Assess customer churn risk based on engagement, satisfaction, and behavior patterns",
    agent_roles=["customer_intelligence", "lead_nurturer"],
    risk_level="LOW",
    examples=[
        "assess_churn_risk(customer_id='CUST123')",
    ],
)
def assess_churn_risk(
    customer_id: str,
) -> ToolResult:
    """
    Assess the risk of customer churn.

    Analyzes:
    - Communication frequency and recency
    - Sentiment from interactions
    - Service issue history
    - Competitive signals (rate inquiries elsewhere)
    - Loan performance
    """
    params = {"customer_id": customer_id}

    # Get communication metrics
    comms_query = """
        SELECT
            COUNT(*) as total_comms,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 90 THEN 1 END) as recent_comms,
            MAX(created_at) as last_contact,
            AVG(CASE WHEN sentiment = 'positive' THEN 1 WHEN sentiment = 'negative' THEN -1 ELSE 0 END) as sentiment_score,
            COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_count
        FROM communication_history
        WHERE contact_id = :customer_id
    """

    comms = execute_single(comms_query, params)

    # Get service issues
    issues_query = """
        SELECT
            COUNT(*) as total_issues,
            COUNT(CASE WHEN status = 'open' THEN 1 END) as open_issues,
            COUNT(CASE WHEN severity = 'high' THEN 1 END) as high_severity,
            AVG(EXTRACT(DAY FROM resolved_at - created_at)) as avg_resolution_days
        FROM service_issues
        WHERE contact_id = :customer_id
    """

    issues = execute_single(issues_query, params) or {"total_issues": 0, "open_issues": 0, "high_severity": 0}

    # Get loan status
    loan_query = """
        SELECT
            l.status,
            l.interest_rate,
            l.funded_at,
            COUNT(CASE WHEN lsh.to_status IN ('cancelled', 'denied') THEN 1 END) as failed_loans
        FROM loans l
        LEFT JOIN loan_status_history lsh ON lsh.loan_id = l.id
        WHERE l.borrower_id = :customer_id OR l.co_borrower_id = :customer_id
        GROUP BY l.id, l.status, l.interest_rate, l.funded_at
        ORDER BY l.created_at DESC
        LIMIT 1
    """

    loan = execute_single(loan_query, params)

    # Calculate risk factors
    risk_factors = []
    risk_score = 0

    # Communication factors
    days_since_contact = days_between(comms["last_contact"], datetime.now()) if comms and comms["last_contact"] else 999

    if days_since_contact > 180:
        risk_factors.append({"factor": "no_recent_contact", "impact": 25, "detail": f"{days_since_contact} days since last contact"})
        risk_score += 25
    elif days_since_contact > 90:
        risk_factors.append({"factor": "declining_engagement", "impact": 15, "detail": f"{days_since_contact} days since last contact"})
        risk_score += 15

    # Sentiment factors
    if comms and comms["sentiment_score"] is not None and comms["sentiment_score"] < -0.3:
        risk_factors.append({"factor": "negative_sentiment", "impact": 20, "detail": f"Sentiment score: {round(comms['sentiment_score'], 2)}"})
        risk_score += 20

    if comms and comms["negative_count"] and comms["negative_count"] >= 3:
        risk_factors.append({"factor": "multiple_complaints", "impact": 15, "detail": f"{comms['negative_count']} negative interactions"})
        risk_score += 15

    # Service issue factors
    if issues["open_issues"] and issues["open_issues"] > 0:
        risk_factors.append({"factor": "unresolved_issues", "impact": 20, "detail": f"{issues['open_issues']} open issues"})
        risk_score += 20

    if issues["high_severity"] and issues["high_severity"] >= 2:
        risk_factors.append({"factor": "severe_issues", "impact": 15, "detail": f"{issues['high_severity']} high-severity issues"})
        risk_score += 15

    # Loan factors
    if loan and loan.get("failed_loans", 0) > 0:
        risk_factors.append({"factor": "past_failed_loan", "impact": 15, "detail": f"{loan['failed_loans']} cancelled/denied loans"})
        risk_score += 15

    # Rate competitiveness (if current rate is high vs market)
    if loan and loan.get("interest_rate"):
        current_market_rate = 6.5  # Would come from rate service in production
        rate_diff = float(loan["interest_rate"]) - current_market_rate
        if rate_diff > 0.5:
            risk_factors.append({"factor": "uncompetitive_rate", "impact": 10, "detail": f"Rate {rate_diff:.2f}% above market"})
            risk_score += 10

    # Determine risk level
    if risk_score >= 50:
        risk_level = ChurnRisk.CRITICAL.value
    elif risk_score >= 35:
        risk_level = ChurnRisk.HIGH.value
    elif risk_score >= 20:
        risk_level = ChurnRisk.MEDIUM.value
    else:
        risk_level = ChurnRisk.LOW.value

    # Generate retention recommendations
    recommendations = []

    if days_since_contact > 90:
        recommendations.append({
            "action": "outreach",
            "priority": "high",
            "suggestion": "Schedule a check-in call to re-engage",
        })

    if issues["open_issues"] and issues["open_issues"] > 0:
        recommendations.append({
            "action": "issue_resolution",
            "priority": "high",
            "suggestion": f"Resolve {issues['open_issues']} open service issues immediately",
        })

    if any(f["factor"] == "uncompetitive_rate" for f in risk_factors):
        recommendations.append({
            "action": "rate_review",
            "priority": "medium",
            "suggestion": "Proactively offer refinance analysis with current market rates",
        })

    if comms and comms["sentiment_score"] is not None and comms["sentiment_score"] < 0:
        recommendations.append({
            "action": "service_recovery",
            "priority": "high",
            "suggestion": "Assign senior team member for relationship repair",
        })

    data = {
        "customer_id": customer_id,
        "risk_level": risk_level,
        "risk_score": min(risk_score, 100),
        "risk_factors": risk_factors,
        "metrics": {
            "days_since_contact": days_since_contact,
            "sentiment_score": round(float(comms["sentiment_score"] or 0), 2) if comms else None,
            "open_issues": issues["open_issues"] or 0,
            "total_issues": issues["total_issues"] or 0,
        },
        "recommendations": recommendations,
        "assessment_date": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Churn Risk: {risk_level.upper()} (score: {risk_score}/100). {len(risk_factors)} risk factors identified.",
    )


@mortgage_tool(
    name="find_opportunities",
    description="Find business opportunities for a customer based on their profile and market conditions",
    agent_roles=["customer_intelligence", "lead_nurturer", "rate_advisor"],
    risk_level="LOW",
    examples=[
        "find_opportunities(customer_id='CUST123')",
        "find_opportunities(customer_id='CUST123', opportunity_types=['refinance', 'heloc'])",
    ],
)
def find_opportunities(
    customer_id: str,
    opportunity_types: Optional[List[str]] = None,
) -> ToolResult:
    """
    Find potential business opportunities for a customer.

    Checks for:
    - Refinance opportunities (rate drop, cash-out equity)
    - HELOC opportunities (equity buildup)
    - Investment property opportunities
    - ARM adjustment notifications
    - Referral opportunities
    """
    params = {"customer_id": customer_id}

    # Get current loans
    loans_query = """
        SELECT
            l.id,
            l.loan_number,
            l.loan_type,
            l.loan_amount,
            l.interest_rate,
            l.funded_at,
            l.property_address,
            l.property_type,
            l.estimated_value,
            l.original_value,
            l.is_arm,
            l.arm_adjustment_date,
            l.current_balance
        FROM loans l
        WHERE (l.borrower_id = :customer_id OR l.co_borrower_id = :customer_id)
            AND l.stage = 'Funded'
    """

    loans = execute_query(loans_query, params)

    opportunities = []
    current_market_rate = 6.5  # Would come from rate service

    for loan in loans:
        loan_rate = float(loan["interest_rate"]) if loan["interest_rate"] else 0
        loan_amount = float(loan["loan_amount"])
        current_balance = float(loan["current_balance"] or loan_amount)
        estimated_value = float(loan["estimated_value"] or loan["original_value"] or loan_amount * 1.25)

        # Rate & Term Refinance
        if loan_rate and loan_rate > current_market_rate + 0.5:
            rate_savings = loan_rate - current_market_rate
            monthly_savings = (current_balance * (rate_savings / 100)) / 12
            annual_savings = monthly_savings * 12

            opportunities.append({
                "type": "rate_refinance",
                "loan_id": loan["id"],
                "loan_number": loan["loan_number"],
                "priority": "high" if rate_savings > 1.0 else "medium",
                "details": {
                    "current_rate": loan_rate,
                    "market_rate": current_market_rate,
                    "rate_reduction": round(rate_savings, 3),
                    "monthly_savings": round(monthly_savings, 2),
                    "annual_savings": round(annual_savings, 2),
                    "current_balance": current_balance,
                },
                "message": f"Refinance opportunity: Save ${monthly_savings:,.0f}/month by reducing rate from {loan_rate}% to {current_market_rate}%",
            })

        # Cash-out Refinance / HELOC
        current_ltv = (current_balance / estimated_value) * 100 if estimated_value else 100
        available_equity = estimated_value - current_balance
        max_cashout = estimated_value * 0.80 - current_balance  # 80% LTV max

        if max_cashout > 50000:
            opportunities.append({
                "type": "cash_out" if max_cashout > 100000 else "heloc",
                "loan_id": loan["id"],
                "loan_number": loan["loan_number"],
                "priority": "medium",
                "details": {
                    "estimated_value": estimated_value,
                    "current_balance": current_balance,
                    "current_ltv": round(current_ltv, 1),
                    "available_equity": round(available_equity, 2),
                    "max_cash_out": round(max_cashout, 2),
                },
                "message": f"Equity available: ${available_equity:,.0f} in home equity. Up to ${max_cashout:,.0f} cash-out possible.",
            })

        # ARM Adjustment Warning
        if loan["is_arm"] and loan["arm_adjustment_date"]:
            days_to_adjustment = days_between(datetime.now(), loan["arm_adjustment_date"])
            if 0 < days_to_adjustment <= 180:
                opportunities.append({
                    "type": "arm_adjustment",
                    "loan_id": loan["id"],
                    "loan_number": loan["loan_number"],
                    "priority": "high",
                    "details": {
                        "adjustment_date": loan["arm_adjustment_date"].isoformat(),
                        "days_until_adjustment": days_to_adjustment,
                        "current_rate": loan_rate,
                    },
                    "message": f"ARM adjusting in {days_to_adjustment} days. Recommend discussing fixed-rate refinance options.",
                })

    # Referral opportunities
    network_query = """
        SELECT COUNT(*) as colleague_count
        FROM contacts c
        WHERE c.employer = (
            SELECT employer FROM contacts WHERE id = :customer_id
        )
        AND c.id != :customer_id
        AND c.id NOT IN (
            SELECT borrower_id FROM loans WHERE stage = 'Funded'
        )
    """

    network = execute_single(network_query, params)
    if network and network["colleague_count"] and network["colleague_count"] > 5:
        opportunities.append({
            "type": "referral",
            "priority": "medium",
            "details": {
                "potential_referrals": network["colleague_count"],
            },
            "message": f"Referral opportunity: {network['colleague_count']} colleagues who haven't worked with us yet.",
        })

    # Investment property opportunity (if only primary residence)
    if len(loans) == 1 and loans[0]["property_type"] == "single_family":
        # Check if they have equity and income
        if available_equity > 100000:
            opportunities.append({
                "type": "investment_property",
                "priority": "low",
                "details": {
                    "equity_for_downpayment": round(available_equity * 0.25, 2),
                },
                "message": f"Investment property opportunity: Could use ${available_equity * 0.25:,.0f} from equity as down payment.",
            })

    # Filter by requested types
    if opportunity_types:
        opportunities = [o for o in opportunities if o["type"] in opportunity_types]

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda x: priority_order.get(x["priority"], 3))

    # Calculate total potential value
    total_value = sum(
        o["details"].get("annual_savings", 0) +
        o["details"].get("max_cash_out", 0) * 0.02  # 2% revenue on cashout
        for o in opportunities
    )

    data = {
        "customer_id": customer_id,
        "opportunity_count": len(opportunities),
        "opportunities": opportunities,
        "total_potential_value": round(total_value, 2),
        "high_priority_count": len([o for o in opportunities if o["priority"] == "high"]),
        "assessed_loans": len(loans),
        "current_market_rate": current_market_rate,
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(opportunities)} opportunities. {data['high_priority_count']} high-priority. Potential value: {format_currency(total_value)}",
    )


@mortgage_tool(
    name="get_interaction_history",
    description="Get detailed interaction history for a customer across all channels",
    agent_roles=["customer_intelligence", "lead_nurturer"],
    risk_level="LOW",
    examples=[
        "get_interaction_history(customer_id='CUST123')",
        "get_interaction_history(customer_id='CUST123', channel='phone', days=90)",
    ],
)
def get_interaction_history(
    customer_id: str,
    channel: Optional[str] = None,
    days: int = 365,
    limit: int = 100,
) -> ToolResult:
    """
    Get comprehensive interaction history for a customer.

    Includes all touchpoints:
    - Phone calls
    - Emails
    - SMS
    - Meetings
    - Portal activity
    - Document submissions
    """
    params = {
        "customer_id": customer_id,
        "days": days,
        "limit": limit,
    }

    channel_filter = ""
    if channel:
        channel_filter = "AND ch.type = :channel"
        params["channel"] = channel

    query = f"""
        SELECT
            ch.id,
            ch.type as channel,
            ch.direction,
            ch.subject,
            ch.summary,
            ch.duration_seconds,
            ch.sentiment,
            ch.outcome,
            ch.created_at,
            u.full_name as user_name,
            l.loan_number
        FROM communication_history ch
        LEFT JOIN users u ON u.id = ch.user_id
        LEFT JOIN loans l ON l.id = ch.loan_id
        WHERE ch.contact_id = :customer_id
            AND ch.created_at >= CURRENT_DATE - :days
            {channel_filter}
        ORDER BY ch.created_at DESC
        LIMIT :limit
    """

    interactions = execute_query(query, params)

    if not interactions:
        return ToolResult.no_data(f"No interactions found in last {days} days")

    # Calculate statistics
    total = len(interactions)
    by_channel = {}
    by_direction = {"inbound": 0, "outbound": 0}
    by_sentiment = {"positive": 0, "neutral": 0, "negative": 0}
    total_duration = 0

    for i in interactions:
        # By channel
        ch = i["channel"]
        if ch not in by_channel:
            by_channel[ch] = 0
        by_channel[ch] += 1

        # By direction
        if i["direction"] in by_direction:
            by_direction[i["direction"]] += 1

        # By sentiment
        if i["sentiment"] in by_sentiment:
            by_sentiment[i["sentiment"]] += 1

        # Total duration (for calls)
        if i["duration_seconds"]:
            total_duration += i["duration_seconds"]

    # Format interactions
    formatted = []
    for i in interactions:
        formatted.append({
            "id": i["id"],
            "channel": i["channel"],
            "direction": i["direction"],
            "subject": i["subject"],
            "summary": i["summary"],
            "duration_minutes": round(i["duration_seconds"] / 60, 1) if i["duration_seconds"] else None,
            "sentiment": i["sentiment"],
            "outcome": i["outcome"],
            "date": i["created_at"].isoformat() if i["created_at"] else None,
            "user": i["user_name"],
            "loan_number": i["loan_number"],
        })

    # Calculate engagement score
    recency_score = 100 - min(days_between(interactions[0]["created_at"], datetime.now()), 100) if interactions else 0
    frequency_score = min(total * 2, 100)
    sentiment_score = (by_sentiment["positive"] - by_sentiment["negative"]) / total * 50 + 50 if total else 50
    engagement_score = (recency_score + frequency_score + sentiment_score) / 3

    data = {
        "customer_id": customer_id,
        "period_days": days,
        "total_interactions": total,
        "interactions": formatted,
        "statistics": {
            "by_channel": by_channel,
            "by_direction": by_direction,
            "by_sentiment": by_sentiment,
            "total_call_minutes": round(total_duration / 60, 1),
            "avg_interactions_per_month": round(total / (days / 30), 1),
        },
        "engagement_score": round(engagement_score, 1),
        "last_interaction_date": interactions[0]["created_at"].isoformat() if interactions else None,
    }

    return ToolResult.success(
        data=data,
        message=f"{total} interactions in last {days} days. Engagement score: {engagement_score:.0f}/100. Sentiment: {by_sentiment['positive']} positive, {by_sentiment['negative']} negative.",
    )


@mortgage_tool(
    name="get_referral_network",
    description="Analyze customer's referral network and identify potential new referrers",
    agent_roles=["customer_intelligence"],
    risk_level="LOW",
    examples=[
        "get_referral_network(customer_id='CUST123')",
    ],
)
def get_referral_network(
    customer_id: str,
) -> ToolResult:
    """
    Analyze the referral network of a customer.

    Returns:
    - Referrals made by customer
    - Referrals received
    - Network expansion opportunities
    - Referral quality metrics
    """
    params = {"customer_id": customer_id}

    # Referrals made by customer
    made_query = """
        SELECT
            r.id,
            r.status,
            r.created_at,
            c.first_name || ' ' || c.last_name as referred_name,
            l.loan_amount,
            l.status as loan_status,
            l.funded_at
        FROM referrals r
        JOIN contacts c ON c.id = r.referred_id
        LEFT JOIN loans l ON l.borrower_id = r.referred_id AND l.stage IN ('Funded', 'Disclosed', 'Processing', 'Submitted', 'UW Received')
        WHERE r.referrer_id = :customer_id
        ORDER BY r.created_at DESC
    """

    made = execute_query(made_query, params)

    # Referrals received
    received_query = """
        SELECT
            r.id,
            r.created_at,
            c.first_name || ' ' || c.last_name as referrer_name,
            l.loan_amount,
            l.funded_at
        FROM referrals r
        JOIN contacts c ON c.id = r.referrer_id
        LEFT JOIN loans l ON l.borrower_id = :customer_id AND l.stage = 'Funded'
        WHERE r.referred_id = :customer_id
        ORDER BY r.created_at DESC
    """

    received = execute_query(received_query, params)

    # Calculate metrics
    made_funded = [r for r in made if r["loan_status"] == "funded"]
    made_pending = [r for r in made if r["loan_status"] in ("application", "processing", "underwriting")]
    made_total_volume = sum(float(r["loan_amount"] or 0) for r in made_funded)

    conversion_rate = len(made_funded) / len(made) if made else 0
    avg_referral_value = made_total_volume / len(made_funded) if made_funded else 0

    # Identify expansion opportunities (second-degree referrals)
    expansion_query = """
        SELECT
            c.id,
            c.first_name || ' ' || c.last_name as name,
            c.email,
            r1.referred_name as connected_through
        FROM referrals r1
        JOIN referrals r2 ON r2.referrer_id = r1.referred_id
        JOIN contacts c ON c.id = r2.referred_id
        WHERE r1.referrer_id = :customer_id
            AND c.id NOT IN (
                SELECT referred_id FROM referrals WHERE referrer_id = :customer_id
            )
        LIMIT 10
    """

    # This query would need adjustment based on actual schema
    # expansion = execute_query(expansion_query, params)
    expansion = []  # Simplified for now

    # Format referrals made
    made_formatted = []
    for r in made:
        revenue = float(r["loan_amount"] or 0) * 0.015  # Est 1.5% revenue
        made_formatted.append({
            "id": r["id"],
            "name": r["referred_name"],
            "status": r["status"],
            "loan_status": r["loan_status"],
            "loan_amount": float(r["loan_amount"]) if r["loan_amount"] else None,
            "loan_amount_formatted": format_currency(r["loan_amount"]) if r["loan_amount"] else None,
            "funded_date": r["funded_at"].isoformat() if r["funded_at"] else None,
            "estimated_revenue": round(revenue, 2) if r["loan_status"] == "funded" else None,
            "referral_date": r["created_at"].isoformat() if r["created_at"] else None,
        })

    # Referrer tier based on activity
    if len(made_funded) >= 5:
        referrer_tier = "champion"
    elif len(made_funded) >= 2:
        referrer_tier = "active"
    elif made:
        referrer_tier = "engaged"
    else:
        referrer_tier = "potential"

    # Revenue from referrals
    total_revenue = made_total_volume * 0.015

    data = {
        "customer_id": customer_id,
        "referrals_made": {
            "total": len(made),
            "funded": len(made_funded),
            "pending": len(made_pending),
            "conversion_rate": round(conversion_rate * 100, 1),
            "total_volume": made_total_volume,
            "total_volume_formatted": format_currency(made_total_volume),
            "total_revenue": round(total_revenue, 2),
            "total_revenue_formatted": format_currency(total_revenue),
            "avg_referral_value": round(avg_referral_value, 2),
            "details": made_formatted,
        },
        "referrals_received": {
            "total": len(received),
            "details": [
                {
                    "referrer": r["referrer_name"],
                    "date": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in received
            ],
        },
        "referrer_tier": referrer_tier,
        "expansion_opportunities": expansion,
    }

    return ToolResult.success(
        data=data,
        message=f"Referral network: {len(made)} made ({len(made_funded)} funded, {format_currency(made_total_volume)}). Tier: {referrer_tier.upper()}",
    )


@mortgage_tool(
    name="get_market_comparison",
    description="Compare customer's loan terms against current market conditions",
    agent_roles=["customer_intelligence", "rate_advisor"],
    risk_level="LOW",
    examples=[
        "get_market_comparison(customer_id='CUST123')",
    ],
)
def get_market_comparison(
    customer_id: str,
) -> ToolResult:
    """
    Compare customer's current loan terms against market conditions.

    Analyzes:
    - Rate vs current market
    - Property value changes
    - Equity position
    - Refinance break-even analysis
    """
    params = {"customer_id": customer_id}

    # Get funded loans
    loans_query = """
        SELECT
            l.id,
            l.loan_number,
            l.loan_type,
            l.loan_amount,
            l.current_balance,
            l.interest_rate,
            l.funded_at,
            l.property_address,
            l.property_city,
            l.property_state,
            l.property_zip,
            l.property_type,
            l.original_value,
            l.estimated_value
        FROM loans l
        WHERE (l.borrower_id = :customer_id OR l.co_borrower_id = :customer_id)
            AND l.stage = 'Funded'
    """

    loans = execute_query(loans_query, params)

    if not loans:
        return ToolResult.no_data("No funded loans found for customer")

    # Market rates (would come from rate service in production)
    market_rates = {
        "conventional_30": 6.50,
        "conventional_15": 5.75,
        "fha_30": 6.25,
        "va_30": 6.00,
        "jumbo_30": 6.75,
    }

    comparisons = []

    for loan in loans:
        loan_rate = float(loan["interest_rate"]) if loan["interest_rate"] else 0
        loan_amount = float(loan["loan_amount"])
        current_balance = float(loan["current_balance"] or loan_amount)
        original_value = float(loan["original_value"] or loan_amount / 0.8)
        estimated_value = float(loan["estimated_value"] or original_value)

        # Determine market rate for this loan type
        loan_type = loan["loan_type"] or "conventional"
        market_rate = market_rates.get(f"{loan_type}_30", 6.50)

        # Rate comparison
        rate_diff = loan_rate - market_rate
        monthly_savings = 0
        breakeven_months = 0

        if rate_diff > 0:
            # Calculate savings from refinancing
            old_monthly = (current_balance * (loan_rate / 100 / 12))  # Simplified interest only
            new_monthly = (current_balance * (market_rate / 100 / 12))
            monthly_savings = old_monthly - new_monthly

            # Estimate closing costs (2.5% of loan amount)
            closing_costs = current_balance * 0.025

            if monthly_savings > 0:
                breakeven_months = int(closing_costs / monthly_savings)

        # Property value analysis
        value_change = estimated_value - original_value
        value_change_pct = (value_change / original_value) * 100 if original_value else 0

        # Equity position
        current_ltv = (current_balance / estimated_value) * 100 if estimated_value else 100
        original_ltv = (loan_amount / original_value) * 100 if original_value else 80
        equity = estimated_value - current_balance
        equity_pct = 100 - current_ltv

        # Recommendation
        recommendation = None
        if rate_diff >= 1.0 and breakeven_months <= 24:
            recommendation = "strong_refi"
        elif rate_diff >= 0.5 and breakeven_months <= 36:
            recommendation = "consider_refi"
        elif equity >= 100000 and current_ltv <= 70:
            recommendation = "equity_options"
        else:
            recommendation = "maintain"

        comparisons.append({
            "loan_id": loan["id"],
            "loan_number": loan["loan_number"],
            "loan_type": loan["loan_type"],
            "property": f"{loan['property_address']}, {loan['property_city']}, {loan['property_state']}",
            "rate_analysis": {
                "current_rate": loan_rate,
                "market_rate": market_rate,
                "rate_difference": round(rate_diff, 3),
                "status": "above_market" if rate_diff > 0.25 else "at_market" if rate_diff >= -0.25 else "below_market",
                "monthly_savings_potential": round(monthly_savings, 2),
                "annual_savings_potential": round(monthly_savings * 12, 2),
                "breakeven_months": breakeven_months if rate_diff > 0 else None,
            },
            "value_analysis": {
                "original_value": original_value,
                "estimated_current_value": estimated_value,
                "value_change": round(value_change, 2),
                "value_change_pct": round(value_change_pct, 1),
                "appreciation_status": "appreciated" if value_change_pct > 5 else "stable" if value_change_pct >= -5 else "depreciated",
            },
            "equity_analysis": {
                "current_balance": current_balance,
                "equity": round(equity, 2),
                "equity_pct": round(equity_pct, 1),
                "current_ltv": round(current_ltv, 1),
                "original_ltv": round(original_ltv, 1),
                "ltv_status": "excellent" if current_ltv <= 60 else "good" if current_ltv <= 80 else "limited",
            },
            "recommendation": recommendation,
            "funded_date": loan["funded_at"].isoformat() if loan["funded_at"] else None,
        })

    # Summary
    total_potential_savings = sum(c["rate_analysis"]["annual_savings_potential"] for c in comparisons)
    total_equity = sum(c["equity_analysis"]["equity"] for c in comparisons)
    refi_candidates = len([c for c in comparisons if c["recommendation"] in ("strong_refi", "consider_refi")])

    data = {
        "customer_id": customer_id,
        "loan_count": len(loans),
        "comparisons": comparisons,
        "summary": {
            "total_potential_annual_savings": round(total_potential_savings, 2),
            "total_potential_annual_savings_formatted": format_currency(total_potential_savings),
            "total_equity": round(total_equity, 2),
            "total_equity_formatted": format_currency(total_equity),
            "refi_candidates": refi_candidates,
            "primary_recommendation": "refinance" if refi_candidates > 0 else "maintain",
        },
        "market_rates_used": market_rates,
        "analysis_date": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Market comparison: {refi_candidates}/{len(loans)} loans are refi candidates. Potential annual savings: {format_currency(total_potential_savings)}. Total equity: {format_currency(total_equity)}",
    )


@mortgage_tool(
    name="create_referral_partner",
    description="Create or add a referral partner to the CRM. Use when user wants to add a realtor, attorney, "
                "financial advisor, or other professional as a referral partner.",
    agent_roles=["customer_intelligence", "lead_nurturer", "voice_os", "ai_receptionist", "all"],
    risk_level="MEDIUM",
    parameters={
        "name": "Full name of the referral partner",
        "email": "Email address (optional if phone provided)",
        "phone": "Phone number (optional if email provided)",
        "company": "Company/firm name (optional)",
        "partner_type": "Type: realtor, attorney, financial_advisor, builder, insurance, other",
        "notes": "Notes about the partner (optional)",
        "user_id": "User ID adding this partner",
    },
)
def create_referral_partner(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    partner_type: str = "realtor",
    notes: Optional[str] = None,
    user_id: Optional[int] = None,
) -> ToolResult:
    """
    Create a new referral partner in the CRM.

    Referral partners are professionals (realtors, attorneys, etc.)
    who refer business to the loan officer.
    """
    import uuid

    if not name:
        raise ToolError("Name is required for creating a referral partner")
    if not email and not phone:
        raise ToolError("At least one of email or phone is required")

    # Validate email format if provided
    import re
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise ToolError(f"Invalid email format: {email}")

    # Validate partner type
    valid_types = ["realtor", "attorney", "financial_advisor", "builder", "insurance", "cpa", "other"]
    if partner_type.lower() not in valid_types:
        partner_type = "other"

    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Check if partner already exists (by email or phone)
            existing = None
            if email:
                existing = db.execute(text("""
                    SELECT id, name, email, phone, type, category
                    FROM referral_partners
                    WHERE LOWER(email) = LOWER(:email)
                    LIMIT 1
                """), {"email": email}).fetchone()
            if not existing and phone:
                clean_phone = re.sub(r"[^\d]", "", phone)
                if len(clean_phone) >= 10:
                    existing = db.execute(text("""
                        SELECT id, name, email, phone, type, category
                        FROM referral_partners
                        WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', ''), ')', '') LIKE :phone
                        LIMIT 1
                    """), {"phone": f"%{clean_phone[-10:]}"}).fetchone()

            if existing:
                return ToolResult.success(
                    data={
                        "partner_id": existing.id,
                        "name": existing.name,
                        "email": existing.email,
                        "partner_type": existing.type or existing.category,
                        "already_exists": True,
                    },
                    message=f"Referral partner '{existing.name}' already exists in the system"
                )

            # Create new partner - use schema from main.py ReferralPartner model
            # Columns: name, business_name, contact_name, category, company, type, phone, email, status, loyalty_tier, notes
            db.execute(text("""
                INSERT INTO referral_partners (
                    name, business_name, contact_name, category, company, type,
                    phone, email, status, loyalty_tier, notes, created_at
                ) VALUES (
                    :name, :business_name, :contact_name, :category, :company, :type,
                    :phone, :email, 'active', 'bronze', :notes, CURRENT_TIMESTAMP
                )
                RETURNING id
            """), {
                "name": name,
                "business_name": company or "",
                "contact_name": name,
                "category": partner_type.lower(),
                "company": company,
                "type": partner_type.lower(),
                "phone": phone,
                "email": email,
                "notes": notes,
            })
            db.commit()

            # Get the created ID
            if email:
                result = db.execute(text("""
                    SELECT id FROM referral_partners WHERE LOWER(email) = LOWER(:email) ORDER BY created_at DESC LIMIT 1
                """), {"email": email}).fetchone()
            else:
                result = db.execute(text("""
                    SELECT id FROM referral_partners WHERE name = :name ORDER BY created_at DESC LIMIT 1
                """), {"name": name}).fetchone()

            partner_id = result.id if result else None

            return ToolResult.success(
                data={
                    "partner_id": partner_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "company": company,
                    "partner_type": partner_type,
                    "notes": notes,
                    "created": True,
                },
                message=f"Created referral partner: {name} ({partner_type})"
            )

        finally:
            db.close()

    except Exception as e:
        # If the table doesn't exist, create it first
        if "referral_partners" in str(e).lower() and "does not exist" in str(e).lower():
            return ToolResult.error(
                "Referral partners feature is not yet set up. Please contact support.",
                [str(e)]
            )
        raise ToolError(f"Failed to create referral partner: {str(e)}")
