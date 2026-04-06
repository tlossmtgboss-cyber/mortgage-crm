"""
Nurture & Retention Agents

Long-term relationship and retention autonomous agents:
1. refi_opportunity_scanner — Daily 9 AM, scan funded borrowers for refi savings
2. sphere_of_influence_nurture — Weekly Monday, nurture past borrowers by segment
3. review_solicitor — Daily 12 PM, multi-step review collection from closed borrowers
4. social_proof_collector — Daily 9 AM, identify closing stories for social content
5. document_expiration_tracker — Every 30 min, tiered doc expiration alerts
"""

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
)
_TERMINAL_SQL = "('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')"

# Refi constants
_DEFAULT_MARKET_RATE = 6.5
_REFI_CLOSING_COST_LOW = 3000.0
_REFI_CLOSING_COST_HIGH = 5000.0
_MIN_MONTHLY_SAVINGS = 100.0
_MAX_BREAKEVEN_MONTHS = 36
_REFI_DEDUP_DAYS = 90

# Stage-to-average-days mapping for close timeline estimation
_AVG_DAYS_TO_CLOSE_FROM_STAGE = {
    "APPLICATION": 45,
    "DISCLOSED": 40,
    "PROCESSING": 35,
    "SUBMITTED": 30,
    "UNDERWRITING": 25,
    "UW_RECEIVED": 20,
    "CONDITIONAL_APPROVAL": 15,
    "APPROVED": 12,
    "SUSPENDED": 30,
    "CTC": 7,
    "CLEAR_TO_CLOSE": 5,
    "CLOSING": 3,
    "DOCS": 3,
    "DOCS_OUT": 2,
}


def _safe_float(val, default: float = 0.0) -> float:
    """Safely coerce a DB value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Safely coerce a DB value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _task_exists(
    db: Session,
    organization_id: int,
    title_pattern: str,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    interval: str = "7 days",
) -> bool:
    """Check if a matching task already exists within the given interval."""
    clauses = ["organization_id = :org_id", "title LIKE :pattern"]
    params: Dict[str, Any] = {
        "org_id": organization_id,
        "pattern": title_pattern,
    }
    if loan_id is not None:
        clauses.append("loan_id = :loan_id")
        params["loan_id"] = str(loan_id)
    if lead_id is not None:
        clauses.append("lead_id = :lead_id")
        params["lead_id"] = str(lead_id)
    clauses.append(f"created_at > CURRENT_TIMESTAMP - INTERVAL '{interval}'")

    sql = f"SELECT id FROM tasks WHERE {' AND '.join(clauses)} LIMIT 1"
    return db.execute(text(sql), params).fetchone() is not None


def _insert_task(
    db: Session,
    organization_id: int,
    title: str,
    description: str,
    owner_id: int,
    priority: str = "medium",
    due_date_expr: str = "CURRENT_DATE + 7",
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    related_type: Optional[str] = None,
) -> None:
    """Insert a task with all required fields."""
    cols = ["title", "description", "owner_id", "priority", "status", "due_date", "created_at", "organization_id"]
    vals = [":title", ":desc", ":owner_id", ":priority", "'pending'", due_date_expr, "CURRENT_TIMESTAMP", ":org_id"]
    params: Dict[str, Any] = {
        "title": title[:255],
        "desc": description[:4000],
        "owner_id": str(owner_id),
        "priority": priority,
        "org_id": organization_id,
    }

    if loan_id is not None:
        cols.append("loan_id")
        vals.append(":loan_id")
        params["loan_id"] = str(loan_id)
    if lead_id is not None:
        cols.append("lead_id")
        vals.append(":lead_id")
        params["lead_id"] = str(lead_id)
    if related_type is not None:
        cols.append("related_type")
        vals.append(":related_type")
        params["related_type"] = related_type

    sql = f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(vals)})"
    db.execute(text(sql), params)


# ---------------------------------------------------------------------------
# 1. Refi Opportunity Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="refi_opportunity_scanner",
    description="Scan funded borrowers for refinance savings opportunities",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=120,
)
def refi_opportunity_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Comprehensive refi opportunity detection:
    - Compare funded loan rate vs configurable market benchmark
    - Calculate monthly savings, break-even months, lifetime savings
    - Segment by opportunity strength (strong/moderate/marginal)
    - Include specific talking points: current payment, estimated new payment
    - 90-day dedup on refi contact attempts
    - Track total refi opportunity volume in return metrics
    """
    actions = 0
    total_monthly_savings = 0.0
    total_opportunity_volume = 0.0
    by_segment: Dict[str, int] = {"strong": 0, "moderate": 0, "marginal": 0}

    # Configurable market rate from env or default
    market_rate = _safe_float(
        os.environ.get("CURRENT_MARKET_RATE"), _DEFAULT_MARKET_RATE,
    )

    # Funded loans with rates higher than market, funded 6+ months ago
    candidates = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.borrower_phone, l.loan_officer_id, l.rate, l.amount,
               l.funded_date, l.term, l.property_address, l.loan_type,
               l.loan_purpose, l.purchase_price,
               u.first_name AS lo_first, u.last_name AS lo_last
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.rate IS NOT NULL
          AND l.rate > :market_rate
          AND l.amount IS NOT NULL
          AND l.amount >= 100000
          AND l.funded_date IS NOT NULL
          AND l.funded_date < CURRENT_DATE - INTERVAL '6 months'
          AND l.loan_officer_id IS NOT NULL
        ORDER BY (l.rate - :market_rate) * l.amount DESC
    """), {"org_id": organization_id, "market_rate": market_rate}).fetchall()

    for loan in candidates:
        loan_id = loan[0]
        loan_number = loan[1] or "N/A"
        borrower = loan[2] or "Borrower"
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = loan[5]
        current_rate = _safe_float(loan[6])
        original_amount = _safe_float(loan[7])
        funded_date = loan[8]
        term_months = _safe_int(loan[9], 360)
        property_addr = loan[10] or "property on file"
        loan_type = loan[11] or "Conventional"
        loan_purpose = loan[12]
        purchase_price = _safe_float(loan[13])
        lo_name = f"{loan[14] or ''} {loan[15] or ''}".strip() or f"LO#{lo_id}"

        # Estimate remaining balance (simple amortization approximation)
        # Months since funding
        months_since_funded = db.execute(text("""
            SELECT EXTRACT(YEAR FROM age(CURRENT_DATE, :funded)) * 12
                 + EXTRACT(MONTH FROM age(CURRENT_DATE, :funded))
        """), {"funded": funded_date}).scalar()
        months_elapsed = _safe_int(months_since_funded, 0)

        if months_elapsed <= 0 or months_elapsed >= term_months:
            continue

        # Remaining balance approximation using amortization formula
        monthly_rate_current = current_rate / 100.0 / 12.0
        if monthly_rate_current > 0:
            # Standard amortization: B = P * [(1+r)^n - (1+r)^p] / [(1+r)^n - 1]
            factor_n = (1 + monthly_rate_current) ** term_months
            factor_p = (1 + monthly_rate_current) ** months_elapsed
            remaining_balance = original_amount * (factor_n - factor_p) / (factor_n - 1)
        else:
            remaining_balance = original_amount * (1 - months_elapsed / term_months)

        if remaining_balance < 75000:
            continue

        # Current monthly P&I
        if monthly_rate_current > 0:
            current_monthly_pi = original_amount * (monthly_rate_current * factor_n) / (factor_n - 1)
        else:
            current_monthly_pi = original_amount / term_months

        # New monthly P&I at market rate for remaining term
        remaining_months = term_months - months_elapsed
        monthly_rate_new = market_rate / 100.0 / 12.0
        if monthly_rate_new > 0:
            factor_new = (1 + monthly_rate_new) ** remaining_months
            new_monthly_pi = remaining_balance * (monthly_rate_new * factor_new) / (factor_new - 1)
        else:
            new_monthly_pi = remaining_balance / remaining_months

        monthly_savings = current_monthly_pi - new_monthly_pi

        if monthly_savings < _MIN_MONTHLY_SAVINGS:
            continue

        # Estimate closing costs based on loan amount
        closing_costs = max(
            _REFI_CLOSING_COST_LOW,
            min(_REFI_CLOSING_COST_HIGH, remaining_balance * 0.01),
        )

        # Break-even analysis
        breakeven_months = closing_costs / monthly_savings if monthly_savings > 0 else 999
        if breakeven_months > _MAX_BREAKEVEN_MONTHS:
            continue

        # Lifetime savings over remaining term
        lifetime_savings = (monthly_savings * remaining_months) - closing_costs

        # Segment by opportunity strength
        if monthly_savings > 300:
            segment = "strong"
            priority = "high"
        elif monthly_savings > 200:
            segment = "moderate"
            priority = "medium"
        else:
            segment = "marginal"
            priority = "low"

        # 90-day dedup: check if already contacted about refi
        if _task_exists(db, organization_id, "%refi opportunity%", loan_id=loan_id,
                        interval=f"{_REFI_DEDUP_DAYS} days"):
            continue

        # Also check activities for refi-related outreach
        recent_refi_activity = db.execute(text("""
            SELECT id FROM activities
            WHERE loan_id = :loan_id
              AND organization_id = :org_id
              AND content ILIKE '%refi%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '90 days'
            LIMIT 1
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchone()

        if recent_refi_activity:
            continue

        # Build talking points
        rate_drop = current_rate - market_rate
        contact_method = "call" if borrower_phone else ("email" if borrower_email else "mail")

        description = (
            f"REFI OPPORTUNITY ({segment.upper()})\n"
            f"Borrower: {borrower} | Loan: {loan_number}\n"
            f"Property: {property_addr}\n"
            f"Original: {loan_type} at {current_rate:.3f}% | ${original_amount:,.0f}\n"
            f"Current rate drop: {rate_drop:.3f}% (market: {market_rate:.2f}%)\n"
            f"---\n"
            f"Current P&I: ${current_monthly_pi:,.0f}/mo\n"
            f"New est. P&I: ${new_monthly_pi:,.0f}/mo\n"
            f"Monthly savings: ${monthly_savings:,.0f}/mo\n"
            f"Est. closing costs: ${closing_costs:,.0f}\n"
            f"Break-even: {breakeven_months:.0f} months\n"
            f"Lifetime savings: ${lifetime_savings:,.0f}\n"
            f"Remaining balance: ${remaining_balance:,.0f}\n"
            f"---\n"
            f"TALKING POINTS:\n"
            f"- 'Rates have dropped {rate_drop:.2f}% since your close — "
            f"that could save you ${monthly_savings:,.0f} every month.'\n"
            f"- 'You'd recoup closing costs in about {breakeven_months:.0f} months, "
            f"then save ${lifetime_savings:,.0f} over the life of the loan.'\n"
            f"- 'Your current payment is ~${current_monthly_pi:,.0f}; "
            f"a refi could bring it to ~${new_monthly_pi:,.0f}.'\n"
            f"Best contact method: {contact_method}"
        )

        _insert_task(
            db, organization_id,
            title=f"Refi opportunity ({segment}): {borrower} — save ${monthly_savings:,.0f}/mo",
            description=description,
            owner_id=lo_id,
            priority=priority,
            due_date_expr="CURRENT_DATE + 3",
            loan_id=loan_id,
            related_type="refi_opportunity",
        )
        actions += 1
        total_monthly_savings += monthly_savings
        total_opportunity_volume += remaining_balance
        by_segment[segment] = by_segment.get(segment, 0) + 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Refi scanner commit failed: {e}")

    return {
        "summary": (
            f"{actions} refi opportunities from {len(candidates)} funded loans "
            f"(strong={by_segment['strong']}, moderate={by_segment['moderate']}, "
            f"marginal={by_segment['marginal']})"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "candidates_scanned": len(candidates),
        "market_rate_used": market_rate,
        "total_monthly_savings": round(total_monthly_savings, 2),
        "total_opportunity_volume": round(total_opportunity_volume, 2),
        "by_segment": by_segment,
    }


# ---------------------------------------------------------------------------
# 2. Sphere of Influence Nurture
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="sphere_of_influence_nurture",
    description="Weekly nurture outreach to past borrowers segmented by recency",
    frequency=AgentFrequency.WEEKLY_MONDAY,
    max_runtime_seconds=120,
)
def sphere_of_influence_nurture(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Segmented past-borrower relationship maintenance:
    - 3-6 months: check-in call, satisfaction confirmation
    - 6-12 months: equity update + gentle referral ask
    - 1-2 years: market update + HELOC opportunity if equity > 20%
    - 2+ years: refi/HELOC check + appreciation report
    Includes estimated equity, referral network depth, realtor co-marketing.
    """
    actions = 0
    by_segment: Dict[str, int] = {
        "check_in": 0, "equity_update": 0,
        "market_update": 0, "long_term": 0,
    }
    referral_opportunities = 0

    # All funded borrowers segmented by time since funding
    past_borrowers = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.borrower_phone, l.loan_officer_id, l.funded_date,
               l.amount, l.purchase_price, l.property_address,
               l.property_city, l.property_state, l.loan_type,
               l.rate, l.realtor_agent, l.loan_purpose, l.term,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.funded_date)) AS days_since_funded,
               u.first_name AS lo_first, u.last_name AS lo_last
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.funded_date IS NOT NULL
          AND l.funded_date < CURRENT_DATE - INTERVAL '3 months'
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.funded_date DESC
    """), {"org_id": organization_id}).fetchall()

    for loan in past_borrowers:
        loan_id = loan[0]
        loan_number = loan[1] or "N/A"
        borrower = loan[2] or "Borrower"
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = loan[5]
        funded_date = loan[6]
        original_amount = _safe_float(loan[7])
        purchase_price = _safe_float(loan[8])
        property_addr = loan[9] or "property on file"
        property_city = loan[10] or ""
        property_state = loan[11] or ""
        loan_type = loan[12] or "Conventional"
        current_rate = _safe_float(loan[13])
        realtor = loan[14]
        loan_purpose = loan[15]
        term_months = _safe_int(loan[16], 360)
        days_since = _safe_int(loan[17], 0)
        lo_name = f"{loan[18] or ''} {loan[19] or ''}".strip() or f"LO#{lo_id}"

        # Determine segment
        if days_since < 180:  # 3-6 months
            segment = "check_in"
            dedup_interval = "30 days"
        elif days_since < 365:  # 6-12 months
            segment = "equity_update"
            dedup_interval = "60 days"
        elif days_since < 730:  # 1-2 years
            segment = "market_update"
            dedup_interval = "90 days"
        else:  # 2+ years
            segment = "long_term"
            dedup_interval = "90 days"

        # Dedup check
        if _task_exists(db, organization_id, "%sphere nurture%", loan_id=loan_id,
                        interval=dedup_interval):
            continue

        # Estimate current home value using ~3% annual appreciation
        years_owned = days_since / 365.0
        base_value = purchase_price if purchase_price > 0 else original_amount
        estimated_value = base_value * ((1 + 0.03) ** years_owned)
        estimated_equity = estimated_value - original_amount * 0.95  # rough remaining balance
        equity_pct = (estimated_equity / estimated_value * 100) if estimated_value > 0 else 0

        # HELOC opportunity: equity > 20%
        heloc_eligible = equity_pct > 20 and days_since >= 365

        # Referral network depth: count closed loans that reference this borrower
        referral_count = _safe_int(db.execute(text("""
            SELECT COUNT(*) FROM loans
            WHERE organization_id = :org_id
              AND stage = 'FUNDED'
              AND id != :loan_id
              AND (
                  user_metadata::text ILIKE :ref_pattern
                  OR borrower_name IN (
                      SELECT DISTINCT a.content FROM activities a
                      WHERE a.loan_id = :loan_id
                        AND a.type = 'Note'
                        AND a.content ILIKE '%referral%'
                        AND a.organization_id = :org_id
                  )
              )
        """), {
            "org_id": organization_id,
            "loan_id": str(loan_id),
            "ref_pattern": f"%{borrower}%referral%",
        }).scalar())

        # Build segment-specific content
        location = f"{property_city}, {property_state}" if property_city else property_addr

        if segment == "check_in":
            title = f"Sphere nurture (check-in): {borrower}"
            description = (
                f"3-6 MONTH CHECK-IN\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Property: {property_addr}\n"
                f"Funded: {funded_date} | {loan_type} at {current_rate:.3f}%\n"
                f"Original amount: ${original_amount:,.0f}\n"
                f"---\n"
                f"TALKING POINTS:\n"
                f"- 'How are you settling in at {location}?'\n"
                f"- Confirm autopay is set up, first payment went smoothly\n"
                f"- Ask about any homeowner questions (insurance, escrow, tax)'\n"
                f"- Mention: 'If any friends or family are looking, I'd love to help.'\n"
                f"Contact: {borrower_phone or borrower_email or 'see file'}"
            )
            priority = "medium"

        elif segment == "equity_update":
            title = f"Sphere nurture (equity update): {borrower}"
            description = (
                f"6-12 MONTH EQUITY UPDATE + REFERRAL ASK\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Property: {property_addr}\n"
                f"Original: ${original_amount:,.0f} at {current_rate:.3f}%\n"
                f"Estimated home value: ${estimated_value:,.0f} (~3% annual appreciation)\n"
                f"Estimated equity: ${estimated_equity:,.0f} ({equity_pct:.0f}%)\n"
                f"---\n"
                f"TALKING POINTS:\n"
                f"- 'Your home has likely appreciated ~${estimated_value - base_value:,.0f} "
                f"since closing.'\n"
                f"- 'Your equity position is strong at ~{equity_pct:.0f}%.'\n"
                f"- REFERRAL ASK: 'I helped you into {location} — "
                f"who else in your circle is thinking about buying or refinancing?'\n"
                f"Referrals from this borrower: {referral_count}\n"
                f"Contact: {borrower_phone or borrower_email or 'see file'}"
            )
            priority = "medium"
            referral_opportunities += 1

        elif segment == "market_update":
            heloc_line = ""
            if heloc_eligible:
                accessible_equity = max(0, estimated_equity - estimated_value * 0.20)
                heloc_line = (
                    f"\n- HELOC OPPORTUNITY: ~${accessible_equity:,.0f} accessible equity. "
                    f"Great for renovations, debt consolidation, or investment."
                )
            title = f"Sphere nurture (market update): {borrower}"
            description = (
                f"1-2 YEAR MARKET UPDATE\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Property: {property_addr}\n"
                f"Original: ${original_amount:,.0f} at {current_rate:.3f}%\n"
                f"Est. home value: ${estimated_value:,.0f} | Equity: ${estimated_equity:,.0f} ({equity_pct:.0f}%)\n"
                f"---\n"
                f"TALKING POINTS:\n"
                f"- Share local market update for {location}\n"
                f"- 'Your home has appreciated ~${estimated_value - base_value:,.0f} in "
                f"{years_owned:.1f} years.'{heloc_line}\n"
                f"- Referral ask: remind them you're still here for their network\n"
                f"Referrals from this borrower: {referral_count}\n"
                f"Contact: {borrower_phone or borrower_email or 'see file'}"
            )
            priority = "low"
            referral_opportunities += 1

        else:  # long_term (2+ years)
            heloc_line = ""
            if heloc_eligible:
                accessible_equity = max(0, estimated_equity - estimated_value * 0.20)
                heloc_line = (
                    f"\n- HELOC: ~${accessible_equity:,.0f} accessible equity — "
                    f"renovation, investment property down payment, debt consolidation"
                )
            # Check if refi might make sense
            market_rate = _safe_float(
                os.environ.get("CURRENT_MARKET_RATE"), _DEFAULT_MARKET_RATE,
            )
            refi_line = ""
            if current_rate > market_rate + 0.5:
                refi_line = (
                    f"\n- REFI CHECK: Currently at {current_rate:.3f}% vs market "
                    f"~{market_rate:.2f}%. Potential rate improvement."
                )

            title = f"Sphere nurture (long-term): {borrower}"
            description = (
                f"2+ YEAR BORROWER — REFI/HELOC CHECK\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Property: {property_addr}\n"
                f"Funded: {funded_date} ({years_owned:.1f} years ago)\n"
                f"Original: ${original_amount:,.0f} at {current_rate:.3f}%\n"
                f"Est. home value: ${estimated_value:,.0f} | Equity: ${estimated_equity:,.0f} ({equity_pct:.0f}%)\n"
                f"---\n"
                f"TALKING POINTS:\n"
                f"- 'It's been {years_owned:.0f} years since we closed — "
                f"let's review your mortgage position.'{refi_line}{heloc_line}\n"
                f"- Ask about life changes: kids, job, plans to move up\n"
                f"- Referral ask: 'I helped you {years_owned:.0f} years ago — "
                f"who's next in your circle?'\n"
                f"Referrals from this borrower: {referral_count}\n"
                f"Contact: {borrower_phone or borrower_email or 'see file'}"
            )
            priority = "low"
            referral_opportunities += 1

        # Realtor co-marketing opportunity
        if realtor:
            description += (
                f"\n---\n"
                f"REALTOR CO-MARKETING: Original agent was {realtor}. "
                f"Consider joint check-in, co-branded market update, or "
                f"home anniversary card."
            )

        _insert_task(
            db, organization_id,
            title=title,
            description=description,
            owner_id=lo_id,
            priority=priority,
            due_date_expr="CURRENT_DATE + 7",
            loan_id=loan_id,
            related_type="sphere_nurture",
        )
        actions += 1
        by_segment[segment] = by_segment.get(segment, 0) + 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Sphere nurture commit failed: {e}")

    return {
        "summary": (
            f"{actions} sphere nurture tasks from {len(past_borrowers)} past borrowers "
            f"(check-in={by_segment['check_in']}, equity={by_segment['equity_update']}, "
            f"market={by_segment['market_update']}, long-term={by_segment['long_term']})"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "borrowers_scanned": len(past_borrowers),
        "by_segment": by_segment,
        "referral_opportunities": referral_opportunities,
    }


# ---------------------------------------------------------------------------
# 3. Review Solicitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="review_solicitor",
    description="Multi-step online review collection from closed borrowers",
    frequency=AgentFrequency.DAILY_12PM,
    max_runtime_seconds=90,
)
def review_solicitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Multi-step review solicitation sequence:
    - Step 1 (Day 5-7): Email review request with personalized template
    - Step 2 (Day 10-14): SMS reminder if no review task completed
    - Step 3 (Day 21): Final ask via different channel
    Prioritizes by loan type: VA/FHA first-time = highest, large loans = high.
    Skips borrowers with complaint-related activities.
    Tracks review funnel metrics.
    """
    actions = 0
    step_counts: Dict[str, int] = {"email_request": 0, "sms_reminder": 0, "final_ask": 0}
    skipped_complaints = 0
    by_priority: Dict[str, int] = {"highest": 0, "high": 0, "medium": 0}

    # Recently funded loans within the review solicitation window (5-30 days)
    recent_closes = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.borrower_phone, l.loan_officer_id, l.loan_type,
               l.amount, l.property_address, l.property_city,
               l.property_state, l.stage_changed_at, l.loan_purpose,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) AS days_since_funded,
               u.first_name AS lo_first, u.last_name AS lo_last
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at IS NOT NULL
          AND l.stage_changed_at BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 5
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.stage_changed_at ASC
    """), {"org_id": organization_id}).fetchall()

    for loan in recent_closes:
        loan_id = loan[0]
        loan_number = loan[1] or "N/A"
        borrower = loan[2] or "Borrower"
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = loan[5]
        loan_type = loan[6] or "Conventional"
        amount = _safe_float(loan[7])
        property_addr = loan[8] or "your new home"
        property_city = loan[9] or ""
        property_state = loan[10] or ""
        funded_at = loan[11]
        loan_purpose = loan[12]
        days_since = _safe_int(loan[13], 0)
        lo_name = f"{loan[14] or ''} {loan[15] or ''}".strip() or "your loan officer"

        # Skip borrowers with complaint-related activities or tasks
        has_complaint = db.execute(text("""
            SELECT id FROM activities
            WHERE loan_id = :loan_id
              AND organization_id = :org_id
              AND (content ILIKE '%complaint%' OR content ILIKE '%escalat%'
                   OR content ILIKE '%dissatisf%' OR content ILIKE '%unhappy%'
                   OR content ILIKE '%dispute%')
            LIMIT 1
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchone()

        if has_complaint:
            skipped_complaints += 1
            continue

        has_complaint_task = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
              AND organization_id = :org_id
              AND (title ILIKE '%complaint%' OR title ILIKE '%escalat%'
                   OR title ILIKE '%issue%resolution%')
            LIMIT 1
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchone()

        if has_complaint_task:
            skipped_complaints += 1
            continue

        # Determine review priority
        is_first_time = loan_purpose and "purchase" in loan_purpose.lower()
        is_va_fha = loan_type.upper() in ("VA", "FHA")
        is_large = amount >= 500000

        if is_va_fha and is_first_time:
            review_priority = "highest"
            priority = "high"
        elif is_large or is_va_fha:
            review_priority = "high"
            priority = "high"
        else:
            review_priority = "medium"
            priority = "medium"

        # Determine which step this borrower is on
        existing_steps = db.execute(text("""
            SELECT title FROM tasks
            WHERE loan_id = :loan_id
              AND organization_id = :org_id
              AND title LIKE '%review request%'
            ORDER BY created_at ASC
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchall()

        step_titles = [row[0] for row in existing_steps]
        has_email_step = any("Step 1" in t for t in step_titles)
        has_sms_step = any("Step 2" in t for t in step_titles)
        has_final_step = any("Step 3" in t for t in step_titles)

        # Location for template
        location = f"{property_city}, {property_state}" if property_city else property_addr

        # Review platform links (placeholders — org configures actual URLs)
        review_links = (
            "REVIEW LINKS:\n"
            "- Google Business: [Configure in Settings > Review Links]\n"
            "- Zillow: [Configure in Settings > Review Links]\n"
            "- LendingTree: [Configure in Settings > Review Links]\n"
            "- Yelp: [Configure in Settings > Review Links]"
        )

        # Step 1: Email review request (Day 5-7)
        if 5 <= days_since <= 7 and not has_email_step:
            title = f"Review request (Step 1 — Email): {borrower}"
            description = (
                f"REVIEW REQUEST — EMAIL ({review_priority.upper()} priority)\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Property: {property_addr}\n"
                f"Funded: {funded_at} | {loan_type} ${amount:,.0f}\n"
                f"---\n"
                f"PERSONALIZED TEMPLATE:\n"
                f"Subject: How was your experience, {borrower.split()[0] if borrower.split() else borrower}?\n\n"
                f"Hi {borrower.split()[0] if borrower.split() else borrower},\n\n"
                f"Congratulations again on closing on {location}! "
                f"It was a pleasure working with you on your {loan_type.lower()} loan.\n\n"
                f"If you had a positive experience, I'd be incredibly grateful "
                f"if you could share a quick review. It helps other families "
                f"find the right loan officer.\n\n"
                f"Best,\n{lo_name}\n"
                f"---\n"
                f"{review_links}\n"
                f"Email to: {borrower_email or 'no email on file'}"
            )
            step_key = "email_request"

        # Step 2: SMS reminder (Day 10-14)
        elif 10 <= days_since <= 14 and has_email_step and not has_sms_step:
            title = f"Review request (Step 2 — SMS): {borrower}"
            description = (
                f"REVIEW FOLLOW-UP — SMS REMINDER\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Email sent ~{days_since - 7} days ago, no review yet.\n"
                f"---\n"
                f"SUGGESTED SMS:\n"
                f"'Hi {borrower.split()[0] if borrower.split() else borrower}! "
                f"Hope you're loving {location}. If you have 2 minutes, "
                f"a quick review would mean the world to me. [link]'\n"
                f"---\n"
                f"Phone: {borrower_phone or 'no phone on file'}\n"
                f"{review_links}"
            )
            step_key = "sms_reminder"

        # Step 3: Final ask (Day 21+)
        elif days_since >= 21 and has_email_step and not has_final_step:
            title = f"Review request (Step 3 — Final): {borrower}"
            description = (
                f"FINAL REVIEW ASK\n"
                f"Borrower: {borrower} | Loan: {loan_number}\n"
                f"Previous attempts: email + {'SMS' if has_sms_step else 'no SMS'}. "
                f"Last chance outreach.\n"
                f"---\n"
                f"APPROACH OPTIONS:\n"
                f"- Personal call: 'I hope the move went well! Would you be willing "
                f"to share a sentence or two about your experience?'\n"
                f"- Handwritten note with QR code to review page\n"
                f"- Thank-you gift with review card\n"
                f"---\n"
                f"Contact: {borrower_phone or borrower_email or 'see file'}\n"
                f"{review_links}"
            )
            step_key = "final_ask"
            priority = "low"  # Lower priority for final attempt
        else:
            continue

        _insert_task(
            db, organization_id,
            title=title,
            description=description,
            owner_id=lo_id,
            priority=priority,
            due_date_expr="CURRENT_DATE + 2",
            loan_id=loan_id,
            related_type="review_request",
        )
        actions += 1
        step_counts[step_key] = step_counts.get(step_key, 0) + 1
        by_priority[review_priority] = by_priority.get(review_priority, 0) + 1

    # Metrics: count completed review tasks (proxy for actual reviews)
    completed_reviews = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND title LIKE '%review request%'
          AND status = 'completed'
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id}).scalar())

    total_requests = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND title LIKE '%review request%'
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id}).scalar())

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Review solicitor commit failed: {e}")

    return {
        "summary": (
            f"{actions} review tasks created "
            f"(email={step_counts['email_request']}, sms={step_counts['sms_reminder']}, "
            f"final={step_counts['final_ask']}). "
            f"Skipped {skipped_complaints} with complaints."
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "borrowers_scanned": len(recent_closes),
        "step_counts": step_counts,
        "skipped_complaints": skipped_complaints,
        "by_priority": by_priority,
        "review_funnel_90d": {
            "total_requests": total_requests,
            "completed": completed_reviews,
            "completion_rate": (
                round(completed_reviews / total_requests * 100, 1)
                if total_requests > 0 else 0
            ),
        },
    }


# ---------------------------------------------------------------------------
# 4. Social Proof Collector
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="social_proof_collector",
    description="Identify closing stories for social media content",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=90,
)
def social_proof_collector(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Score and surface compelling closing stories for social content:
    - Content value scoring: first-time buyer, VA/military, FHA, large loans, unique properties
    - Detect compelling narratives: fast close, overcame suspension, referral chain
    - Create permission request task first, then content creation task
    - Include specific content angle and all details LO needs (no borrower name until permission)
    - Track social content pipeline metrics
    """
    actions = 0
    stories: List[Dict[str, Any]] = []
    total_content_value = 0

    # Recent funded loans (last 7 days for content freshness)
    recent_closings = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.loan_type, l.amount, l.property_address, l.property_city,
               l.property_state, l.loan_purpose, l.property_type,
               l.stage_changed_at, l.created_at, l.funded_date,
               EXTRACT(DAY FROM (l.stage_changed_at - l.created_at)) AS days_to_close,
               u.first_name AS lo_first, u.last_name AS lo_last
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at IS NOT NULL
          AND l.stage_changed_at >= CURRENT_DATE - 7
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.amount DESC NULLS LAST
    """), {"org_id": organization_id}).fetchall()

    for loan in recent_closings:
        loan_id = loan[0]
        loan_number = loan[1] or "N/A"
        borrower = loan[2] or "Borrower"
        lo_id = loan[3]
        loan_type = (loan[4] or "Conventional").upper()
        amount = _safe_float(loan[5])
        property_addr = loan[6] or "property"
        property_city = loan[7] or ""
        property_state = loan[8] or ""
        loan_purpose = loan[9] or ""
        property_type = loan[10] or ""
        funded_at = loan[11]
        created_at = loan[12]
        funded_date = loan[13]
        days_to_close = _safe_int(loan[14], 0)
        lo_name = f"{loan[15] or ''} {loan[16] or ''}".strip() or f"LO#{lo_id}"

        # Skip if already have social content task for this loan
        if _task_exists(db, organization_id, "%social content%", loan_id=loan_id,
                        interval="30 days"):
            continue

        # ── Score content value ──────────────────────────────────────────
        score = 0
        angles: List[str] = []
        hashtags: List[str] = []

        # First-time buyer (infer from purpose = purchase + loan type)
        is_purchase = "purchase" in loan_purpose.lower() if loan_purpose else False
        is_fha = loan_type in ("FHA",)
        is_va = loan_type in ("VA",)
        is_usda = loan_type in ("USDA",)

        # VA/military = 10 points
        if is_va:
            score += 10
            angles.append("Served & Housed: VA loan success story")
            hashtags.extend(["#VeteranHomeowner", "#VALoan", "#ThankYouForYourService"])

        # First-time buyer (FHA purchase as proxy) = 10 points
        if is_fha and is_purchase:
            score += 10
            angles.append("First Home! FHA buyer achieves the dream")
            hashtags.extend(["#FirstTimeHomeBuyer", "#FHALoan", "#DreamHome"])
        elif is_fha:
            score += 8
            angles.append("FHA success story")
            hashtags.append("#FHALoan")

        # USDA = 7 points
        if is_usda:
            score += 7
            angles.append("Rural homeownership: USDA loan")
            hashtags.extend(["#USDALoan", "#RuralLiving"])

        # Large loan = 8 points
        if amount >= 500000:
            score += 8
            if amount >= 1000000:
                angles.append("Dream Home: seven-figure closing")
                hashtags.append("#LuxuryRealEstate")
            else:
                angles.append("Major milestone: premium property")
                hashtags.append("#DreamHome")

        # Fast close = bonus
        if 0 < days_to_close <= 21:
            score += 5
            angles.append(f"Record Close: {days_to_close}-day turnaround")
            hashtags.append("#FastClose")

        # Overcame obstacles (was in SUSPENDED at some point)
        was_suspended = db.execute(text("""
            SELECT id FROM stage_history
            WHERE loan_id = :loan_id AND to_stage = 'SUSPENDED'
              AND organization_id = :org_id
            LIMIT 1
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchone()

        if was_suspended:
            score += 5
            angles.append("Against the Odds: overcame underwriting hurdles")
            hashtags.append("#NeverGiveUp")

        # Came from referral
        was_referral = db.execute(text("""
            SELECT id FROM leads
            WHERE loan_number = :loan_num
              AND organization_id = :org_id
              AND source ILIKE '%referral%'
            LIMIT 1
        """), {"loan_num": loan_number, "org_id": organization_id}).fetchone()

        if was_referral:
            score += 3
            angles.append("Referral success: trust that multiplies")
            hashtags.append("#Referral")

        # Unique property type bonus
        if property_type and property_type.lower() in ("condo", "multi-family", "townhouse", "manufactured"):
            score += 5
            angles.append(f"Unique property: {property_type}")

        # Minimum score threshold for content worthiness
        if score < 5:
            continue

        total_content_value += score

        # Select best content angle
        primary_angle = angles[0] if angles else "Another Happy Homeowner"
        all_angles = " | ".join(angles)
        location = f"{property_city}, {property_state}" if property_city else "local area"

        # ── Create permission request task (must complete before content) ─
        permission_title = f"Social content permission: {borrower}"
        permission_desc = (
            f"REQUEST BORROWER PERMISSION FOR SOCIAL POST\n"
            f"Borrower: {borrower} | Loan: {loan_number}\n"
            f"Content value score: {score}/30\n"
            f"---\n"
            f"Ask {borrower} for permission to feature their closing story on social media.\n"
            f"IMPORTANT: Do NOT post borrower name, photo, or identifiable details "
            f"without written consent.\n"
            f"---\n"
            f"Suggested ask: 'Congratulations again on your new home! "
            f"Would you be comfortable with me sharing a post celebrating your closing? "
            f"I won't use your name unless you'd like me to.'"
        )

        _insert_task(
            db, organization_id,
            title=permission_title,
            description=permission_desc,
            owner_id=lo_id,
            priority="medium",
            due_date_expr="CURRENT_DATE + 3",
            loan_id=loan_id,
            related_type="social_permission",
        )
        actions += 1

        # ── Create content creation task (with all details) ──────────────
        content_title = f"Social content: {primary_angle} — {location}"
        content_desc = (
            f"SOCIAL MEDIA CONTENT SUGGESTION (score: {score}/30)\n"
            f"BLOCKED: Complete permission task above before posting.\n"
            f"---\n"
            f"PRIMARY ANGLE: {primary_angle}\n"
            f"ALL ANGLES: {all_angles}\n"
            f"---\n"
            f"CONTENT DETAILS (for post creation):\n"
            f"- Location: {location}\n"
            f"- Loan type: {loan_type}\n"
            f"- Close date: {funded_at}\n"
            f"- Property type: {property_type or 'single-family'}\n"
            f"- Amount range: {'$500K+' if amount >= 500000 else '$250-500K' if amount >= 250000 else 'under $250K'}\n"
            f"{'- Days to close: ' + str(days_to_close) if days_to_close > 0 else ''}\n"
            f"---\n"
            f"DO NOT include until permission granted: borrower name, exact address, "
            f"exact loan amount, photos\n"
            f"---\n"
            f"SUGGESTED HASHTAGS: {' '.join(hashtags)}\n"
            f"PLATFORM TIPS:\n"
            f"- Instagram: Photo of house (exterior only) with story overlay\n"
            f"- Facebook: Longer story format, tag realtor if applicable\n"
            f"- LinkedIn: Professional angle, market insights"
        )

        _insert_task(
            db, organization_id,
            title=content_title,
            description=content_desc,
            owner_id=lo_id,
            priority="low",
            due_date_expr="CURRENT_DATE + 7",
            loan_id=loan_id,
            related_type="social_content",
        )
        actions += 1

        stories.append({
            "loan_id": loan_id,
            "angle": primary_angle,
            "score": score,
        })

    # Pipeline metrics: count existing social content tasks
    pending_permissions = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND related_type = 'social_permission'
          AND status = 'pending'
    """), {"org_id": organization_id}).scalar())

    completed_permissions = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND related_type = 'social_permission'
          AND status = 'completed'
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id}).scalar())

    content_in_queue = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND related_type = 'social_content'
          AND status = 'pending'
    """), {"org_id": organization_id}).scalar())

    content_completed = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE organization_id = :org_id
          AND related_type = 'social_content'
          AND status = 'completed'
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id}).scalar())

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Social proof commit failed: {e}")

    return {
        "summary": (
            f"{actions} social content tasks ({len(stories)} stories identified, "
            f"avg score {total_content_value / len(stories):.0f}/30)"
            if stories else f"{actions} social content tasks (no notable closings this week)"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "closings_scanned": len(recent_closings),
        "stories_identified": len(stories),
        "total_content_value": total_content_value,
        "top_stories": sorted(stories, key=lambda s: s["score"], reverse=True)[:5],
        "content_pipeline": {
            "pending_permissions": pending_permissions,
            "completed_permissions": completed_permissions,
            "content_in_queue": content_in_queue,
            "content_published": content_completed,
        },
    }


# ---------------------------------------------------------------------------
# 5. Document Expiration Tracker
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="document_expiration_tracker",
    description="Tiered alerts for expiring credit reports and appraisals",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=90,
)
def document_expiration_tracker(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Comprehensive document expiration management:
    - Tracks credit_docs_expire_date and appraisal_docs_expire_date
    - Tiered alerts at 30d, 14d, 7d, 3d with escalating priority
    - Window dedup: creates each tier alert only once per loan per doc type
    - Estimates whether loan can close before expiration based on current stage
    - Includes rush order instructions and cost impact when docs will expire
    - Groups alerts by LO in return metrics
    - Tracks total dollar exposure and refresh cost estimates
    """
    actions = 0
    total_dollar_exposure = 0.0
    total_refresh_cost_estimate = 0.0
    lo_alert_counts: Dict[int, int] = {}

    # Alert windows: (max_days, min_days, window_label, priority)
    alert_windows = [
        (30, 15, "30d", "low"),
        (14, 8, "14d", "medium"),
        (7, 4, "7d", "high"),
        (3, 0, "3d", "critical"),
    ]

    # Doc types to track: (column_name, doc_label, est_refresh_cost)
    doc_types = [
        ("credit_docs_expire_date", "Credit report", 50.0),
        ("appraisal_docs_expire_date", "Appraisal", 500.0),
    ]

    for expire_col, doc_label, refresh_cost in doc_types:
        for max_days, min_days, window_label, window_priority in alert_windows:

            # Find loans with this doc type expiring in this window
            expiring = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
                       l.{expire_col} AS expire_date,
                       (l.{expire_col}::date - CURRENT_DATE) AS days_left,
                       l.stage, l.amount, l.closing_date,
                       l.property_address, l.borrower_email
                FROM loans l
                WHERE l.organization_id = :org_id
                  AND l.{expire_col} IS NOT NULL
                  AND (l.{expire_col}::date - CURRENT_DATE) BETWEEN :min_days AND :max_days
                  AND l.stage NOT IN {_TERMINAL_SQL}
                  AND l.loan_officer_id IS NOT NULL
                ORDER BY l.{expire_col} ASC
            """), {
                "org_id": organization_id,
                "min_days": min_days,
                "max_days": max_days,
            }).fetchall()

            for loan in expiring:
                loan_id = loan[0]
                loan_number = loan[1] or "N/A"
                borrower = loan[2] or "Borrower"
                lo_id = loan[3]
                expire_date = loan[4]
                days_left = _safe_int(loan[5], 0)
                stage = loan[6] or "UNKNOWN"
                amount = _safe_float(loan[7])
                closing_date = loan[8]
                property_addr = loan[9] or "property on file"
                borrower_email = loan[10]

                # Window dedup: check if this specific window alert already exists
                # Pattern: "Credit report 7d alert" or "Appraisal 14d alert"
                dedup_pattern = f"%{doc_label}%{window_label} alert%"
                if _task_exists(db, organization_id, dedup_pattern,
                                loan_id=loan_id, interval="60 days"):
                    continue

                # Also skip if a more urgent alert already exists
                # (e.g., don't create 14d if 7d already sent)
                more_urgent_exists = False
                for check_max, check_min, check_label, _ in alert_windows:
                    if check_max < max_days:  # More urgent window
                        check_pattern = f"%{doc_label}%{check_label} alert%"
                        if _task_exists(db, organization_id, check_pattern,
                                        loan_id=loan_id, interval="60 days"):
                            more_urgent_exists = True
                            break

                # We DO want to create this alert even if less-urgent one exists,
                # but skip if more-urgent already covers it
                # Actually, the spec says: "don't create 14d alert if 30d alert
                # already exists, but DO create 7d". So we should still create
                # the alert if it's a MORE urgent window, even if less urgent exists.
                # The dedup_pattern above handles same-window dedup.
                # We should NOT skip if a more urgent alert exists — that's expected.

                # Calculate whether loan can close before expiration
                avg_days_to_close = _AVG_DAYS_TO_CLOSE_FROM_STAGE.get(stage, 30)
                can_close_before = days_left >= avg_days_to_close
                will_expire_before_close = not can_close_before

                # Build urgency-specific description
                urgency_header = {
                    "3d": "CRITICAL — EXPIRES IN 3 DAYS OR LESS",
                    "7d": "URGENT — EXPIRES WITHIN 1 WEEK",
                    "14d": "WARNING — EXPIRES WITHIN 2 WEEKS",
                    "30d": "HEADS UP — EXPIRES WITHIN 30 DAYS",
                }

                rush_instructions = ""
                if will_expire_before_close:
                    rush_instructions = (
                        f"\n---\n"
                        f"RUSH ORDER NEEDED\n"
                        f"Current stage: {stage} (avg {avg_days_to_close}d to close)\n"
                        f"Doc expires in {days_left}d — loan unlikely to close in time.\n"
                        f"Estimated refresh cost: ${refresh_cost:,.0f}\n"
                    )
                    if doc_label == "Appraisal":
                        rush_instructions += (
                            f"ACTION: Order appraisal update/recertification immediately. "
                            f"If expired, new appraisal required (~$500, 7-14 day turnaround). "
                            f"Contact AMC to rush. Notify borrower of potential delay and cost."
                        )
                    else:  # Credit
                        rush_instructions += (
                            f"ACTION: Order credit refresh/supplement immediately (~$50). "
                            f"Turnaround: 24-48 hours. New hard inquiry may affect score. "
                            f"Warn borrower: no new credit applications until close."
                        )
                    total_refresh_cost_estimate += refresh_cost

                closing_info = ""
                if closing_date:
                    closing_info = f"\nScheduled closing: {closing_date}"

                title = (
                    f"{doc_label} {window_label} alert: {borrower} ({loan_number}) "
                    f"— {days_left}d left"
                )
                description = (
                    f"{urgency_header.get(window_label, 'ALERT')}\n"
                    f"Borrower: {borrower} | Loan: {loan_number}\n"
                    f"Property: {property_addr}\n"
                    f"Loan amount: ${amount:,.0f} | Stage: {stage}\n"
                    f"{doc_label} expires: {expire_date} ({days_left} days){closing_info}\n"
                    f"Can close before expiration: {'YES' if can_close_before else 'NO — action required'}\n"
                    f"Estimated refresh cost: ${refresh_cost:,.0f}"
                    f"{rush_instructions}"
                )

                # Due date: sooner for more urgent windows
                if window_label == "3d":
                    due_expr = "CURRENT_DATE"
                elif window_label == "7d":
                    due_expr = "CURRENT_DATE + 1"
                elif window_label == "14d":
                    due_expr = "CURRENT_DATE + 3"
                else:
                    due_expr = "CURRENT_DATE + 7"

                _insert_task(
                    db, organization_id,
                    title=title,
                    description=description,
                    owner_id=lo_id,
                    priority=window_priority,
                    due_date_expr=due_expr,
                    loan_id=loan_id,
                    related_type="doc_expiration",
                )
                actions += 1
                total_dollar_exposure += amount
                lo_alert_counts[lo_id] = lo_alert_counts.get(lo_id, 0) + 1

    # Build LO-grouped summary for return metrics
    lo_summary: List[Dict[str, Any]] = []
    if lo_alert_counts:
        lo_names = db.execute(text("""
            SELECT id, first_name, last_name FROM users
            WHERE id = ANY(:ids) AND organization_id = :org_id
        """), {
            "ids": list(lo_alert_counts.keys()),
            "org_id": organization_id,
        }).fetchall()
        lo_name_map = {
            row[0]: f"{row[1] or ''} {row[2] or ''}".strip() or f"LO#{row[0]}"
            for row in lo_names
        }
        for lo_id, count in sorted(lo_alert_counts.items(), key=lambda x: -x[1]):
            lo_summary.append({
                "lo_id": lo_id,
                "lo_name": lo_name_map.get(lo_id, f"LO#{lo_id}"),
                "alert_count": count,
            })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Document expiration tracker commit failed: {e}")

    return {
        "summary": (
            f"{actions} document expiration alerts across {len(lo_alert_counts)} LOs. "
            f"${total_dollar_exposure:,.0f} in exposed loan volume."
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
        "total_dollar_exposure": round(total_dollar_exposure, 2),
        "estimated_refresh_costs": round(total_refresh_cost_estimate, 2),
        "alerts_by_lo": lo_summary,
    }
