"""
Perennia AI - MUM (Manage, Update, Market) Post-Closing Client Tools
Tools for managing post-closing client relationships, tracking anniversaries,
identifying refinance candidates, and logging outreach activities.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool, ToolResult, ToolError,
    get_db,
    format_currency, format_percentage, format_date, days_between,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool 1: Get MUM Clients
# =============================================================================

@mortgage_tool(
    name="get_mum_clients",
    description="List MUM (Mortgage Under Management) clients for the current user with optional search filtering by name or email",
    agent_roles=["customer_intelligence", "post_closing_care", "refinance_advisor", "lead_nurturer"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Show my MUM clients",
        "List post-closing clients",
        "Get my managed clients",
    ],
)
def get_mum_clients(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    **kwargs,
) -> ToolResult:
    """List MUM clients for the current user with optional search."""
    try:
        from database.models.referral import MUMClient

        db = kwargs.get("db")
        current_user = kwargs.get("current_user")
        if not db or not current_user:
            with get_db() as session:
                return _get_mum_clients_impl(session, current_user, limit, offset, search)

        return _get_mum_clients_impl(db, current_user, limit, offset, search)
    except Exception as e:
        return ToolResult.error(f"Failed to get MUM clients: {str(e)}")


def _get_mum_clients_impl(db, current_user, limit, offset, search):
    from database.models.referral import MUMClient
    from sqlalchemy import or_

    query = db.query(MUMClient).filter(MUMClient.user_id == current_user.id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                MUMClient.client_name.ilike(search_term),
                MUMClient.email.ilike(search_term),
            )
        )

    total = query.count()
    clients = query.order_by(MUMClient.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for c in clients:
        results.append({
            "id": c.id,
            "client_name": c.client_name,
            "email": c.email,
            "phone": c.phone,
            "loan_number": c.loan_number,
            "closing_date": c.closing_date.isoformat() if c.closing_date else None,
            "original_rate": float(c.original_rate) if c.original_rate else None,
            "original_loan_amount": float(c.original_loan_amount) if c.original_loan_amount else None,
            "status": c.status,
            "engagement_score": c.engagement_score,
            "last_contact": c.last_contact.isoformat() if c.last_contact else None,
        })

    return ToolResult.success({
        "clients": results,
        "total": total,
        "limit": limit,
        "offset": offset,
        "search": search,
    })


# =============================================================================
# Tool 2: Search MUM Clients
# =============================================================================

@mortgage_tool(
    name="search_mum_clients",
    description="Full-text search across MUM clients by name, email, phone, loan number, or property location",
    agent_roles=["customer_intelligence", "post_closing_care", "refinance_advisor", "ai_receptionist"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Search MUM clients for Johnson",
        "Find post-closing client by phone",
        "Look up client by loan number",
    ],
)
def search_mum_clients(
    query: str,
    **kwargs,
) -> ToolResult:
    """Full-text search across MUM clients."""
    try:
        from database.models.referral import MUMClient
        from sqlalchemy import or_

        if not query or len(query.strip()) < 2:
            return ToolResult.error("Search query must be at least 2 characters")

        current_user = kwargs.get("current_user")

        with get_db() as db:
            search_term = f"%{query.strip()}%"

            results = db.query(MUMClient).filter(
                MUMClient.user_id == current_user.id,
                or_(
                    MUMClient.client_name.ilike(search_term),
                    MUMClient.email.ilike(search_term),
                    MUMClient.phone.ilike(search_term),
                    MUMClient.loan_number.ilike(search_term),
                    MUMClient.property_state.ilike(search_term),
                    MUMClient.property_zip.ilike(search_term),
                )
            ).order_by(MUMClient.client_name).limit(50).all()

            if not results:
                return ToolResult.no_data(f"No MUM clients found matching '{query}'")

            clients = []
            for c in results:
                clients.append({
                    "id": c.id,
                    "client_name": c.client_name,
                    "email": c.email,
                    "phone": c.phone,
                    "loan_number": c.loan_number,
                    "closing_date": c.closing_date.isoformat() if c.closing_date else None,
                    "original_rate": float(c.original_rate) if c.original_rate else None,
                    "original_loan_amount": float(c.original_loan_amount) if c.original_loan_amount else None,
                    "property_state": c.property_state,
                    "property_zip": c.property_zip,
                    "status": c.status,
                })

            return ToolResult.success({
                "query": query,
                "results": clients,
                "count": len(clients),
            })

    except Exception as e:
        return ToolResult.error(f"Failed to search MUM clients: {str(e)}")


# =============================================================================
# Tool 3: Get MUM Client Details
# =============================================================================

@mortgage_tool(
    name="get_mum_client_details",
    description="Get full details of a single MUM client including loan info, team members, and engagement history",
    agent_roles=["customer_intelligence", "post_closing_care", "refinance_advisor"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Show MUM client details",
        "Get post-closing client info",
        "Full profile for this MUM client",
    ],
)
def get_mum_client_details(
    mum_client_id: int,
    **kwargs,
) -> ToolResult:
    """Get full details of one MUM client."""
    try:
        from database.models.referral import MUMClient

        current_user = kwargs.get("current_user")

        with get_db() as db:
            client = db.query(MUMClient).filter(
                MUMClient.id == mum_client_id,
                MUMClient.user_id == current_user.id,
            ).first()

            if not client:
                return ToolResult.no_data(f"MUM client {mum_client_id} not found")

            # Calculate days since closing
            days_since_closing = None
            if client.closing_date:
                days_since_closing = days_between(client.closing_date)

            return ToolResult.success({
                "id": client.id,
                "client_name": client.client_name,
                "email": client.email,
                "phone": client.phone,
                "loan_info": {
                    "loan_number": client.loan_number,
                    "closing_date": client.closing_date.isoformat() if client.closing_date else None,
                    "first_payment_date": client.first_payment_date.isoformat() if client.first_payment_date else None,
                    "original_loan_amount": format_currency(client.original_loan_amount),
                    "current_loan_amount": format_currency(client.current_loan_amount),
                    "interest_rate": format_percentage(client.interest_rate),
                    "original_rate": format_percentage(client.original_rate),
                    "current_rate": format_percentage(client.current_rate),
                    "term": client.term,
                    "maturity_date": client.maturity_date.isoformat() if client.maturity_date else None,
                },
                "property": {
                    "appraisal_value_at_closing": format_currency(client.appraisal_value_at_closing),
                    "current_property_value": format_currency(client.current_property_value),
                    "estimated_equity": format_currency(client.estimated_equity),
                    "current_ltv": format_percentage(client.current_ltv),
                    "property_state": client.property_state,
                    "property_zip": client.property_zip,
                },
                "team": {
                    "loan_officer": client.loan_officer,
                    "loan_officer_email": client.loan_officer_email,
                    "processor": client.processor,
                    "closer": client.closer,
                },
                "engagement": {
                    "engagement_score": client.engagement_score,
                    "last_contact": client.last_contact.isoformat() if client.last_contact else None,
                    "next_touchpoint": client.next_touchpoint.isoformat() if client.next_touchpoint else None,
                    "referrals_sent": client.referrals_sent,
                    "days_since_closing": days_since_closing,
                },
                "refinance": {
                    "refinance_opportunity": client.refinance_opportunity,
                    "estimated_savings": format_currency(client.estimated_savings),
                    "refi_score": client.refi_score,
                    "opportunity_notes": client.opportunity_notes,
                },
                "status": client.status,
                "notes": client.notes,
                "salesforce_id": client.salesforce_id,
            })

    except Exception as e:
        return ToolResult.error(f"Failed to get MUM client details: {str(e)}")


# =============================================================================
# Tool 4: Create MUM Activity
# =============================================================================

@mortgage_tool(
    name="create_mum_activity",
    description="Log an activity (call, email, meeting, or note) with a MUM client for post-closing relationship tracking",
    agent_roles=["post_closing_care", "customer_intelligence", "lead_nurturer"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Log a call with this MUM client",
        "Add a note to the post-closing client",
        "Record a meeting with the client",
    ],
)
def create_mum_activity(
    mum_client_id: int,
    activity_type: str,
    description: str,
    **kwargs,
) -> ToolResult:
    """Log an activity with a MUM client."""
    try:
        from database.models.referral import MUMClient

        valid_types = {"call", "email", "meeting", "note"}
        if activity_type not in valid_types:
            return ToolResult.error(
                f"Invalid activity_type '{activity_type}'. Must be one of: {', '.join(sorted(valid_types))}"
            )

        current_user = kwargs.get("current_user")

        with get_db() as db:
            client = db.query(MUMClient).filter(
                MUMClient.id == mum_client_id,
                MUMClient.user_id == current_user.id,
            ).first()

            if not client:
                return ToolResult.no_data(f"MUM client {mum_client_id} not found")

            # Append activity to notes with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            activity_entry = f"\n[{timestamp}] [{activity_type.upper()}] {description}"

            if client.notes:
                client.notes += activity_entry
            else:
                client.notes = activity_entry.lstrip("\n")

            # Update last_contact timestamp
            client.last_contact = datetime.now(timezone.utc)

            db.flush()

            return ToolResult.success({
                "mum_client_id": mum_client_id,
                "client_name": client.client_name,
                "activity_type": activity_type,
                "description": description,
                "logged_at": timestamp,
                "message": f"Activity logged for {client.client_name}",
            })

    except Exception as e:
        return ToolResult.error(f"Failed to create MUM activity: {str(e)}")


# =============================================================================
# Tool 5: Get MUM Anniversaries
# =============================================================================

@mortgage_tool(
    name="get_mum_anniversaries",
    description="Get MUM clients with upcoming closing anniversaries within a specified number of days",
    agent_roles=["post_closing_care", "customer_intelligence", "lead_nurturer"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Who has closing anniversaries this month?",
        "Upcoming client anniversaries",
        "Which clients have anniversaries in the next 30 days?",
    ],
)
def get_mum_anniversaries(
    days_ahead: int = 30,
    **kwargs,
) -> ToolResult:
    """Get MUM clients with upcoming closing anniversaries."""
    try:
        from database.models.referral import MUMClient
        from sqlalchemy import extract

        current_user = kwargs.get("current_user")

        with get_db() as db:
            clients = db.query(MUMClient).filter(
                MUMClient.user_id == current_user.id,
                MUMClient.closing_date.isnot(None),
            ).all()

            if not clients:
                return ToolResult.no_data("No MUM clients with closing dates found")

            today = datetime.now(timezone.utc).date()
            upcoming = []

            for c in clients:
                closing = c.closing_date
                if hasattr(closing, 'date'):
                    closing = closing.date()

                # Calculate this year's anniversary
                try:
                    anniversary_this_year = closing.replace(year=today.year)
                except ValueError:
                    # Handle Feb 29 in non-leap years
                    anniversary_this_year = closing.replace(year=today.year, day=28)

                # If anniversary already passed this year, check next year
                if anniversary_this_year < today:
                    try:
                        anniversary_this_year = closing.replace(year=today.year + 1)
                    except ValueError:
                        anniversary_this_year = closing.replace(year=today.year + 1, day=28)

                days_until = (anniversary_this_year - today).days
                if 0 <= days_until <= days_ahead:
                    years = anniversary_this_year.year - closing.year
                    upcoming.append({
                        "id": c.id,
                        "client_name": c.client_name,
                        "email": c.email,
                        "phone": c.phone,
                        "closing_date": closing.isoformat(),
                        "anniversary_date": anniversary_this_year.isoformat(),
                        "days_until": days_until,
                        "years": years,
                        "original_loan_amount": format_currency(c.original_loan_amount),
                    })

            # Sort by soonest anniversary first
            upcoming.sort(key=lambda x: x["days_until"])

            if not upcoming:
                return ToolResult.no_data(f"No closing anniversaries in the next {days_ahead} days")

            return ToolResult.success({
                "upcoming_anniversaries": upcoming,
                "count": len(upcoming),
                "days_ahead": days_ahead,
                "summary": f"{len(upcoming)} client(s) with closing anniversaries in the next {days_ahead} days",
            })

    except Exception as e:
        return ToolResult.error(f"Failed to get MUM anniversaries: {str(e)}")


# =============================================================================
# Tool 6: Get MUM Refinance Candidates
# =============================================================================

@mortgage_tool(
    name="get_mum_refinance_candidates",
    description="Find MUM clients who may benefit from refinancing based on rate differential against current market rates",
    agent_roles=["refinance_advisor", "post_closing_care", "rate_advisor"],
    risk_level="low",
    requires_confirmation=False,
    examples=[
        "Who are good refinance candidates?",
        "Find clients who could save by refinancing",
        "Show refi opportunities in my portfolio",
    ],
)
def get_mum_refinance_candidates(
    rate_threshold: float = 0.5,
    **kwargs,
) -> ToolResult:
    """Find MUM clients who may benefit from refinancing."""
    try:
        from database.models.referral import MUMClient
        from .base import execute_single

        current_user = kwargs.get("current_user")

        # Try to get current market rate from settings
        market_rate = 6.5  # default
        try:
            row = execute_single(
                "SELECT value FROM settings WHERE key = 'current_market_rate' LIMIT 1"
            )
            if row and row.get("value"):
                market_rate = float(row["value"])
        except Exception:
            pass

        with get_db() as db:
            clients = db.query(MUMClient).filter(
                MUMClient.user_id == current_user.id,
                MUMClient.interest_rate.isnot(None),
            ).all()

            if not clients:
                return ToolResult.no_data("No MUM clients with rate data found")

            candidates = []
            for c in clients:
                client_rate = float(c.interest_rate) if c.interest_rate else None
                if client_rate is None:
                    continue

                rate_diff = client_rate - market_rate
                if rate_diff >= rate_threshold:
                    # Estimate monthly savings
                    loan_amount = float(c.current_loan_amount) if c.current_loan_amount else 0
                    if loan_amount > 0:
                        old_monthly = loan_amount * (client_rate / 100 / 12)
                        new_monthly = loan_amount * (market_rate / 100 / 12)
                        monthly_savings = old_monthly - new_monthly
                    else:
                        monthly_savings = 0

                    candidates.append({
                        "id": c.id,
                        "client_name": c.client_name,
                        "email": c.email,
                        "phone": c.phone,
                        "current_rate": float(client_rate),
                        "market_rate": market_rate,
                        "rate_difference": round(rate_diff, 4),
                        "loan_number": c.loan_number,
                        "current_loan_amount": format_currency(c.current_loan_amount),
                        "estimated_monthly_savings": format_currency(monthly_savings),
                        "refi_score": c.refi_score,
                        "refinance_opportunity": c.refinance_opportunity,
                        "closing_date": c.closing_date.isoformat() if c.closing_date else None,
                    })

            # Sort by rate difference descending (biggest savings first)
            candidates.sort(key=lambda x: x["rate_difference"], reverse=True)

            if not candidates:
                return ToolResult.no_data(
                    f"No clients found with rate differential >= {rate_threshold}% "
                    f"(current market rate: {market_rate}%)"
                )

            return ToolResult.success({
                "candidates": candidates,
                "count": len(candidates),
                "market_rate": market_rate,
                "rate_threshold": rate_threshold,
                "summary": (
                    f"{len(candidates)} client(s) with rates at least "
                    f"{rate_threshold}% above the current market rate of {market_rate}%"
                ),
            })

    except Exception as e:
        return ToolResult.error(f"Failed to get refinance candidates: {str(e)}")


# =============================================================================
# Tool 7: Update MUM Client
# =============================================================================

@mortgage_tool(
    name="update_mum_client",
    description="Update MUM client contact information including email, phone, and notes",
    agent_roles=["post_closing_care", "customer_intelligence"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Update client email address",
        "Change MUM client phone number",
        "Add notes to post-closing client",
    ],
)
def update_mum_client(
    mum_client_id: int,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
    **kwargs,
) -> ToolResult:
    """Update MUM client contact info."""
    try:
        from database.models.referral import MUMClient

        current_user = kwargs.get("current_user")

        if email is None and phone is None and notes is None:
            return ToolResult.error("No fields provided to update. Specify email, phone, or notes.")

        with get_db() as db:
            client = db.query(MUMClient).filter(
                MUMClient.id == mum_client_id,
                MUMClient.user_id == current_user.id,
            ).first()

            if not client:
                return ToolResult.no_data(f"MUM client {mum_client_id} not found")

            updated_fields = []

            if email is not None:
                client.email = email
                updated_fields.append("email")

            if phone is not None:
                client.phone = phone
                updated_fields.append("phone")

            if notes is not None:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                note_entry = f"\n[{timestamp}] [UPDATE] {notes}"
                if client.notes:
                    client.notes += note_entry
                else:
                    client.notes = note_entry.lstrip("\n")
                updated_fields.append("notes")

            db.flush()

            return ToolResult.success({
                "mum_client_id": mum_client_id,
                "client_name": client.client_name,
                "updated_fields": updated_fields,
                "updated": True,
                "message": f"Updated {', '.join(updated_fields)} for {client.client_name}",
            })

    except Exception as e:
        return ToolResult.error(f"Failed to update MUM client: {str(e)}")
