"""
Perennia AI - Lead Nurturing Tools
Tools for the Lead Nurturer agent to manage and convert leads.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
)


# Lead scoring weights
SCORING_WEIGHTS = {
    "credit_score": 0.20,
    "income_stability": 0.15,
    "down_payment": 0.15,
    "engagement_level": 0.20,
    "timeline_urgency": 0.15,
    "property_identified": 0.15,
}

# Optimal contact times by day
OPTIMAL_CONTACT_TIMES = {
    "weekday": ["09:00-11:00", "14:00-16:00", "18:00-20:00"],
    "saturday": ["10:00-12:00", "14:00-16:00"],
    "sunday": ["12:00-14:00", "16:00-18:00"],
}


@mortgage_tool(
    name="get_lead_details",
    description="Get comprehensive details about a lead including contact info, status, and history",
    agent_roles=["lead_nurturer", "sales", "manager"],
    risk_level="low",
    examples=[
        "Tell me about this lead",
        "Get lead details",
        "Show lead information",
    ],
)
def get_lead_details(
    lead_id: int,
) -> ToolResult:
    """Get detailed information about a lead."""
    try:
        lead_query = """
            SELECT
                l.id, l.first_name, l.last_name, l.email, l.phone,
                l.status, l.source, l.created_at, l.updated_at,
                l.estimated_loan_amount, l.estimated_down_payment,
                l.credit_score_range, l.property_type_interest,
                l.timeline, l.notes, l.assigned_to,
                lo.name as assigned_lo_name,
                l.last_contact_date, l.next_followup_date,
                l.lead_score
            FROM leads l
            LEFT JOIN loan_officers lo ON l.assigned_to = lo.id
            WHERE l.id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Get activity history
        activity_query = """
            SELECT activity_type, description, created_at, created_by
            FROM lead_activities
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 10
        """
        activities = execute_query(activity_query, {"lead_id": lead_id})

        # Calculate days since last contact
        days_since_contact = None
        if lead["last_contact_date"]:
            days_since_contact = days_between(lead["last_contact_date"])

        # Calculate lead age
        lead_age = days_between(lead["created_at"]) if lead["created_at"] else 0

        return ToolResult.success({
            "lead": {
                "id": lead["id"],
                "name": f"{lead['first_name']} {lead['last_name']}",
                "email": lead["email"],
                "phone": lead["phone"],
                "status": lead["status"],
                "source": lead["source"],
                "lead_score": lead["lead_score"],
                "assigned_to": lead["assigned_lo_name"],
            },
            "financial_profile": {
                "estimated_loan_amount": float(lead["estimated_loan_amount"]) if lead["estimated_loan_amount"] else None,
                "estimated_loan_formatted": format_currency(lead["estimated_loan_amount"]),
                "estimated_down_payment": float(lead["estimated_down_payment"]) if lead["estimated_down_payment"] else None,
                "credit_score_range": lead["credit_score_range"],
                "property_interest": lead["property_type_interest"],
            },
            "engagement": {
                "timeline": lead["timeline"],
                "lead_age_days": lead_age,
                "days_since_contact": days_since_contact,
                "next_followup": format_date(lead["next_followup_date"]),
                "last_contact": format_date(lead["last_contact_date"]),
            },
            "notes": lead["notes"],
            "recent_activities": [{
                "type": a["activity_type"],
                "description": a["description"],
                "date": format_date(a["created_at"]),
            } for a in activities],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get lead details: {str(e)}")


@mortgage_tool(
    name="get_engagement_history",
    description="Get complete engagement history for a lead including all touchpoints",
    agent_roles=["lead_nurturer", "sales"],
    risk_level="low",
    examples=[
        "Show engagement history",
        "What interactions have we had?",
        "Lead touchpoint history",
    ],
)
def get_engagement_history(
    lead_id: int,
    limit: int = 50,
) -> ToolResult:
    """Get engagement history for a lead."""
    try:
        # Get all activities
        activities_query = """
            SELECT
                activity_type,
                description,
                outcome,
                created_at,
                created_by,
                duration_minutes,
                channel
            FROM lead_activities
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT :limit
        """
        activities = execute_query(activities_query, {"lead_id": lead_id, "limit": limit})

        if not activities:
            return ToolResult.no_data(f"No engagement history for lead {lead_id}")

        # Categorize by type
        by_type = {}
        for activity in activities:
            atype = activity["activity_type"]
            if atype not in by_type:
                by_type[atype] = []
            by_type[atype].append(activity)

        # Calculate engagement metrics
        total_activities = len(activities)
        calls = len(by_type.get("call", []))
        emails = len(by_type.get("email", []))
        meetings = len(by_type.get("meeting", []))

        # Get first and last contact
        first_activity = activities[-1] if activities else None
        last_activity = activities[0] if activities else None

        engagement_span = 0
        if first_activity and last_activity:
            engagement_span = days_between(first_activity["created_at"], last_activity["created_at"])

        return ToolResult.success({
            "lead_id": lead_id,
            "total_interactions": total_activities,
            "metrics": {
                "calls": calls,
                "emails": emails,
                "meetings": meetings,
                "other": total_activities - calls - emails - meetings,
                "engagement_span_days": engagement_span,
            },
            "first_contact": format_date(first_activity["created_at"]) if first_activity else None,
            "last_contact": format_date(last_activity["created_at"]) if last_activity else None,
            "history": [{
                "type": a["activity_type"],
                "description": a["description"],
                "outcome": a["outcome"],
                "channel": a["channel"],
                "date": format_date(a["created_at"]),
                "duration_minutes": a["duration_minutes"],
            } for a in activities],
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get engagement history: {str(e)}")


@mortgage_tool(
    name="score_lead",
    description="Calculate or recalculate lead score based on multiple factors",
    agent_roles=["lead_nurturer", "sales", "manager"],
    risk_level="low",
    examples=[
        "Score this lead",
        "What's the lead quality?",
        "Calculate lead score",
    ],
)
def score_lead(
    lead_id: int,
    update_record: bool = False,
) -> ToolResult:
    """Score a lead based on multiple factors."""
    try:
        # Get lead data
        lead_query = """
            SELECT
                l.id, l.first_name, l.last_name,
                l.credit_score_range, l.estimated_loan_amount,
                l.estimated_down_payment, l.timeline,
                l.property_type_interest, l.employment_status,
                l.created_at, l.last_contact_date
            FROM leads l
            WHERE l.id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Get engagement data
        engagement_query = """
            SELECT
                COUNT(*) as total_activities,
                COUNT(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 END) as recent_activities,
                COUNT(CASE WHEN outcome = 'positive' THEN 1 END) as positive_outcomes
            FROM lead_activities
            WHERE lead_id = :lead_id
        """
        engagement = execute_single(engagement_query, {"lead_id": lead_id})

        scores = {}
        recommendations = []

        # 1. Credit Score (0-100)
        credit_ranges = {
            "excellent": 100, "760+": 100,
            "good": 80, "700-759": 80,
            "fair": 60, "640-699": 60,
            "poor": 40, "580-639": 40,
            "unknown": 50, None: 50,
        }
        credit_range = lead.get("credit_score_range", "").lower() if lead.get("credit_score_range") else "unknown"
        scores["credit_score"] = credit_ranges.get(credit_range, 50)

        if scores["credit_score"] < 60:
            recommendations.append("Discuss credit improvement strategies")

        # 2. Income Stability (0-100)
        employment_scores = {
            "employed_w2": 100,
            "self_employed": 80,
            "retired": 85,
            "contract": 60,
            "unemployed": 20,
            None: 50,
        }
        scores["income_stability"] = employment_scores.get(lead.get("employment_status"), 50)

        # 3. Down Payment (0-100)
        loan_amt = float(lead["estimated_loan_amount"] or 0)
        down_pmt = float(lead["estimated_down_payment"] or 0)
        if loan_amt > 0 and down_pmt > 0:
            down_pct = down_pmt / (loan_amt + down_pmt) * 100
            if down_pct >= 20:
                scores["down_payment"] = 100
            elif down_pct >= 10:
                scores["down_payment"] = 80
            elif down_pct >= 5:
                scores["down_payment"] = 60
            else:
                scores["down_payment"] = 40
                recommendations.append("Discuss down payment assistance programs")
        else:
            scores["down_payment"] = 50

        # 4. Engagement Level (0-100)
        if engagement:
            total = engagement["total_activities"] or 0
            recent = engagement["recent_activities"] or 0
            positive = engagement["positive_outcomes"] or 0

            engagement_score = min(100, (total * 5) + (recent * 10) + (positive * 15))
            scores["engagement_level"] = engagement_score

            if recent == 0:
                recommendations.append("Re-engage with recent outreach")
        else:
            scores["engagement_level"] = 0
            recommendations.append("Initiate first contact")

        # 5. Timeline Urgency (0-100)
        timeline_scores = {
            "immediately": 100, "asap": 100,
            "1-3 months": 90, "1_3_months": 90,
            "3-6 months": 70, "3_6_months": 70,
            "6-12 months": 50, "6_12_months": 50,
            "just looking": 30, "just_looking": 30,
            None: 40,
        }
        timeline = lead.get("timeline", "").lower() if lead.get("timeline") else None
        scores["timeline_urgency"] = timeline_scores.get(timeline, 40)

        if scores["timeline_urgency"] >= 90:
            recommendations.append("Prioritize - hot lead with immediate timeline")

        # 6. Property Identified (0-100)
        if lead.get("property_type_interest"):
            scores["property_identified"] = 75
        else:
            scores["property_identified"] = 30
            recommendations.append("Help identify property criteria")

        # Calculate weighted total
        total_score = sum(
            scores[factor] * weight
            for factor, weight in SCORING_WEIGHTS.items()
        )
        total_score = round(total_score, 1)

        # Determine grade
        if total_score >= 80:
            grade = "A"
            priority = "high"
        elif total_score >= 60:
            grade = "B"
            priority = "medium"
        elif total_score >= 40:
            grade = "C"
            priority = "low"
        else:
            grade = "D"
            priority = "nurture"

        # Update record if requested
        if update_record:
            with get_db() as db:
                from sqlalchemy import text
                db.execute(
                    text("UPDATE leads SET lead_score = :score WHERE id = :lead_id"),
                    {"score": total_score, "lead_id": lead_id}
                )

        return ToolResult.success({
            "lead_id": lead_id,
            "lead_name": f"{lead['first_name']} {lead['last_name']}",
            "total_score": total_score,
            "grade": grade,
            "priority": priority,
            "factor_scores": scores,
            "scoring_weights": SCORING_WEIGHTS,
            "recommendations": recommendations,
            "record_updated": update_record,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to score lead: {str(e)}")


@mortgage_tool(
    name="suggest_followup",
    description="Suggest optimal follow-up action based on lead status and history",
    agent_roles=["lead_nurturer", "sales"],
    risk_level="low",
    examples=[
        "What should I do next with this lead?",
        "Suggest follow-up action",
        "Next steps for this lead",
    ],
)
def suggest_followup(
    lead_id: int,
) -> ToolResult:
    """Suggest next follow-up action for a lead."""
    try:
        # Get lead details
        lead_query = """
            SELECT
                l.id, l.first_name, l.last_name, l.status,
                l.timeline, l.last_contact_date, l.next_followup_date,
                l.lead_score, l.preferred_contact_method,
                l.email, l.phone
            FROM leads l
            WHERE l.id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Get recent activities
        recent_query = """
            SELECT activity_type, outcome, created_at
            FROM lead_activities
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 5
        """
        recent_activities = execute_query(recent_query, {"lead_id": lead_id})

        days_since_contact = days_between(lead["last_contact_date"]) if lead["last_contact_date"] else 999
        lead_score = lead["lead_score"] or 50
        status = lead["status"] or "new"

        suggestions = []
        primary_action = None
        urgency = "normal"

        # Determine suggestions based on status and engagement
        if status == "new":
            primary_action = {
                "action": "initial_contact",
                "method": lead["preferred_contact_method"] or "phone",
                "message": f"Welcome call/email to {lead['first_name']} - introduce services and understand needs",
                "timing": "within 24 hours",
            }
            urgency = "high"
            suggestions.append("Send welcome email with company introduction")
            suggestions.append("Schedule discovery call")

        elif status == "contacted":
            if days_since_contact > 3:
                primary_action = {
                    "action": "follow_up",
                    "method": "phone",
                    "message": f"Follow up with {lead['first_name']} - {days_since_contact} days since last contact",
                    "timing": "today",
                }
                urgency = "high"
            else:
                primary_action = {
                    "action": "nurture",
                    "method": "email",
                    "message": "Send relevant market update or educational content",
                    "timing": "within 48 hours",
                }

        elif status == "qualified":
            primary_action = {
                "action": "advance_conversation",
                "method": "call",
                "message": f"Discuss specific loan options with {lead['first_name']}",
                "timing": "within 24 hours",
            }
            urgency = "high"
            suggestions.append("Prepare personalized rate scenarios")
            suggestions.append("Send pre-qualification information")

        elif status == "application_started":
            primary_action = {
                "action": "application_assistance",
                "method": "call",
                "message": "Help complete application - check for missing documents",
                "timing": "today",
            }
            urgency = "high"
            suggestions.append("Review application for completeness")
            suggestions.append("Send document checklist")

        else:  # nurture or other
            if days_since_contact > 14:
                primary_action = {
                    "action": "re_engagement",
                    "method": "email",
                    "message": f"Re-engage {lead['first_name']} with value-add content",
                    "timing": "within 48 hours",
                }
            else:
                primary_action = {
                    "action": "continued_nurture",
                    "method": "email",
                    "message": "Continue nurture sequence with market updates",
                    "timing": "per nurture schedule",
                }

        # Score-based adjustments
        if lead_score >= 80:
            urgency = "high"
            suggestions.insert(0, "High-value lead - prioritize personal attention")
        elif lead_score < 40:
            suggestions.append("Consider automated nurture sequence")

        # Check for patterns in recent activities
        if recent_activities:
            no_answer_count = sum(1 for a in recent_activities if a["outcome"] == "no_answer")
            if no_answer_count >= 2:
                suggestions.append("Multiple no-answers - try different time or channel")
                primary_action["method"] = "email" if primary_action.get("method") == "phone" else "phone"

        return ToolResult.success({
            "lead_id": lead_id,
            "lead_name": f"{lead['first_name']} {lead['last_name']}",
            "current_status": status,
            "lead_score": lead_score,
            "days_since_contact": days_since_contact,
            "urgency": urgency,
            "primary_action": primary_action,
            "additional_suggestions": suggestions,
            "contact_info": {
                "email": lead["email"],
                "phone": lead["phone"],
                "preferred_method": lead["preferred_contact_method"],
            },
        })

    except Exception as e:
        return ToolResult.error(f"Failed to suggest followup: {str(e)}")


@mortgage_tool(
    name="draft_message",
    description="Draft a personalized message for lead outreach",
    agent_roles=["lead_nurturer", "sales"],
    risk_level="low",
    examples=[
        "Draft an email for this lead",
        "Write a follow-up message",
        "Create outreach message",
    ],
)
def draft_message(
    lead_id: int,
    message_type: str = "follow_up",
    channel: str = "email",
) -> ToolResult:
    """Draft a personalized message for a lead."""
    try:
        # Get lead details
        lead_query = """
            SELECT
                l.id, l.first_name, l.last_name, l.email,
                l.status, l.timeline, l.estimated_loan_amount,
                l.property_type_interest, l.source
            FROM leads l
            WHERE l.id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Get last interaction
        last_activity_query = """
            SELECT activity_type, description, created_at
            FROM lead_activities
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 1
        """
        last_activity = execute_single(last_activity_query, {"lead_id": lead_id})

        first_name = lead["first_name"]
        loan_amount = format_currency(lead["estimated_loan_amount"]) if lead["estimated_loan_amount"] else "your target loan amount"

        # Message templates
        templates = {
            "initial_contact": {
                "email": {
                    "subject": f"Welcome to [Company], {first_name}!",
                    "body": f"""Hi {first_name},

Thank you for your interest in getting a mortgage! I'm excited to help you on your homeownership journey.

I noticed you're looking at {lead['property_type_interest'] or 'purchasing a home'} with a timeline of {lead['timeline'] or 'the near future'}.

I'd love to schedule a quick 15-minute call to understand your goals and show you how we can help you secure the best rate possible.

What time works best for you this week?

Best regards,
[Your Name]
Mortgage Advisor""",
                },
                "sms": f"Hi {first_name}! Thanks for reaching out about a mortgage. I'm here to help you find the best rate. When's a good time for a quick chat?",
            },
            "follow_up": {
                "email": {
                    "subject": f"Following up on your mortgage inquiry, {first_name}",
                    "body": f"""Hi {first_name},

I wanted to follow up on our recent conversation about your mortgage needs.

Have you had a chance to gather the documents we discussed? I'm here to help make this process as smooth as possible.

If you have any questions or concerns, don't hesitate to reach out. I'm just a call or email away!

Looking forward to helping you move forward.

Best,
[Your Name]""",
                },
                "sms": f"Hi {first_name}, just checking in on your mortgage application. Any questions I can help with? - [Your Name]",
            },
            "rate_update": {
                "email": {
                    "subject": "Great news about mortgage rates!",
                    "body": f"""Hi {first_name},

I have some exciting news - rates have moved favorably this week, and I wanted to make sure you know about it!

Based on your target of {loan_amount}, this could mean significant savings over the life of your loan.

Would you like to see an updated quote? I can have personalized numbers for you within the hour.

Let me know!

Best,
[Your Name]""",
                },
                "sms": f"Hi {first_name}! Rates dropped this week. Want me to run updated numbers for you? Could save you money! - [Your Name]",
            },
            "re_engagement": {
                "email": {
                    "subject": f"Still thinking about homeownership, {first_name}?",
                    "body": f"""Hi {first_name},

It's been a little while since we last connected, and I wanted to check in.

Whether your plans have changed or you're still considering a home purchase, I'm here to help whenever you're ready.

The market is always evolving, and I'd be happy to give you an update on current rates and programs that might work for your situation.

No pressure - just want you to know I'm here when you need me!

Warmly,
[Your Name]""",
                },
                "sms": f"Hi {first_name}! Checking in to see if you're still thinking about a mortgage. Happy to help whenever you're ready! - [Your Name]",
            },
        }

        template = templates.get(message_type, templates["follow_up"])
        message = template.get(channel, template.get("email"))

        if isinstance(message, dict):
            result = {
                "lead_id": lead_id,
                "lead_name": f"{first_name} {lead['last_name']}",
                "message_type": message_type,
                "channel": channel,
                "subject": message.get("subject"),
                "body": message.get("body"),
                "personalization_used": {
                    "first_name": first_name,
                    "timeline": lead["timeline"],
                    "property_interest": lead["property_type_interest"],
                    "loan_amount": loan_amount,
                },
            }
        else:
            result = {
                "lead_id": lead_id,
                "lead_name": f"{first_name} {lead['last_name']}",
                "message_type": message_type,
                "channel": channel,
                "body": message,
            }

        return ToolResult.success(result)

    except Exception as e:
        return ToolResult.error(f"Failed to draft message: {str(e)}")


@mortgage_tool(
    name="schedule_outreach",
    description="Schedule follow-up outreach for a lead",
    agent_roles=["lead_nurturer", "sales"],
    risk_level="low",
    requires_confirmation=True,
    examples=[
        "Schedule a follow-up call",
        "Set up outreach for next week",
        "Book a callback",
    ],
)
def schedule_outreach(
    lead_id: int,
    outreach_type: str,
    scheduled_date: str,
    scheduled_time: Optional[str] = None,
    notes: Optional[str] = None,
) -> ToolResult:
    """Schedule outreach for a lead."""
    try:
        # Validate lead exists
        lead_query = """
            SELECT id, first_name, last_name, email, phone
            FROM leads
            WHERE id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Parse date
        try:
            schedule_dt = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
        except ValueError:
            return ToolResult.error("Invalid date format. Use YYYY-MM-DD")

        # Create scheduled task
        with get_db() as db:
            from sqlalchemy import text

            # Update lead's next followup date
            db.execute(
                text("UPDATE leads SET next_followup_date = :date WHERE id = :lead_id"),
                {"date": schedule_dt, "lead_id": lead_id}
            )

            # Create task
            db.execute(
                text("""
                    INSERT INTO tasks (
                        task_type, related_lead_id, title, description,
                        due_date, status, created_at
                    ) VALUES (
                        :task_type, :lead_id, :title, :description,
                        :due_date, 'pending', NOW()
                    )
                """),
                {
                    "task_type": outreach_type,
                    "lead_id": lead_id,
                    "title": f"{outreach_type.title()} with {lead['first_name']} {lead['last_name']}",
                    "description": notes or f"Scheduled {outreach_type} follow-up",
                    "due_date": schedule_dt,
                }
            )

        return ToolResult.success({
            "lead_id": lead_id,
            "lead_name": f"{lead['first_name']} {lead['last_name']}",
            "outreach_type": outreach_type,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "notes": notes,
            "status": "scheduled",
            "message": f"Outreach scheduled for {format_date(schedule_dt)}",
        })

    except Exception as e:
        return ToolResult.error(f"Failed to schedule outreach: {str(e)}")


@mortgage_tool(
    name="get_similar_converted_leads",
    description="Find similar leads that successfully converted to understand what worked",
    agent_roles=["lead_nurturer", "sales", "manager"],
    risk_level="low",
    examples=[
        "Show me similar leads that converted",
        "What worked for leads like this?",
        "Find successful similar prospects",
    ],
)
def get_similar_converted_leads(
    lead_id: int,
    limit: int = 5,
) -> ToolResult:
    """Find similar leads that converted successfully."""
    try:
        # Get current lead profile
        lead_query = """
            SELECT
                id, credit_score_range, estimated_loan_amount,
                timeline, property_type_interest, source
            FROM leads
            WHERE id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Find similar converted leads
        similar_query = """
            SELECT
                l.id, l.first_name, l.last_name,
                l.credit_score_range, l.estimated_loan_amount,
                l.timeline, l.source, l.created_at,
                l.converted_at,
                EXTRACT(EPOCH FROM (l.converted_at - l.created_at)) / 86400 as days_to_convert
            FROM leads l
            WHERE l.status = 'converted'
            AND l.id != :lead_id
            AND (
                l.credit_score_range = :credit_range
                OR l.source = :source
                OR ABS(l.estimated_loan_amount - :loan_amount) / NULLIF(:loan_amount, 0) < 0.2
            )
            ORDER BY l.converted_at DESC
            LIMIT :limit
        """
        similar = execute_query(similar_query, {
            "lead_id": lead_id,
            "credit_range": lead["credit_score_range"],
            "source": lead["source"],
            "loan_amount": lead["estimated_loan_amount"] or 0,
            "limit": limit,
        })

        if not similar:
            return ToolResult.no_data("No similar converted leads found")

        # Get engagement patterns for converted leads
        results = []
        for s in similar:
            engagement_query = """
                SELECT
                    activity_type,
                    COUNT(*) as count
                FROM lead_activities
                WHERE lead_id = :lead_id
                GROUP BY activity_type
            """
            engagement = execute_query(engagement_query, {"lead_id": s["id"]})

            results.append({
                "lead_id": s["id"],
                "profile": {
                    "credit_range": s["credit_score_range"],
                    "loan_amount": format_currency(s["estimated_loan_amount"]),
                    "timeline": s["timeline"],
                    "source": s["source"],
                },
                "conversion": {
                    "days_to_convert": round(s["days_to_convert"] or 0, 1),
                    "converted_date": format_date(s["converted_at"]),
                },
                "engagement_pattern": {
                    e["activity_type"]: e["count"] for e in engagement
                },
            })

        # Calculate aggregate insights
        avg_days = sum(r["conversion"]["days_to_convert"] for r in results) / len(results) if results else 0

        all_engagement = {}
        for r in results:
            for atype, count in r["engagement_pattern"].items():
                if atype not in all_engagement:
                    all_engagement[atype] = []
                all_engagement[atype].append(count)

        avg_engagement = {
            atype: round(sum(counts) / len(counts), 1)
            for atype, counts in all_engagement.items()
        }

        return ToolResult.success({
            "current_lead_id": lead_id,
            "similar_leads_found": len(results),
            "insights": {
                "avg_days_to_convert": round(avg_days, 1),
                "avg_engagement_by_type": avg_engagement,
                "most_common_source": lead["source"],
            },
            "similar_leads": results,
            "recommendations": _generate_conversion_recommendations(avg_engagement, avg_days),
        })

    except Exception as e:
        return ToolResult.error(f"Failed to find similar leads: {str(e)}")


def _generate_conversion_recommendations(avg_engagement: Dict, avg_days: float) -> List[str]:
    """Generate recommendations based on successful conversion patterns."""
    recommendations = []

    calls = avg_engagement.get("call", 0)
    emails = avg_engagement.get("email", 0)

    if calls >= 3:
        recommendations.append(f"Successful leads average {calls:.0f} calls - prioritize phone outreach")
    if emails >= 5:
        recommendations.append(f"Email nurturing important - average {emails:.0f} emails before conversion")

    if avg_days < 30:
        recommendations.append("Similar leads convert quickly - maintain frequent contact")
    elif avg_days > 60:
        recommendations.append("Longer nurture cycle expected - be patient and consistent")

    return recommendations


@mortgage_tool(
    name="get_optimal_contact_time",
    description="Determine the best time to contact a lead based on their history and patterns",
    agent_roles=["lead_nurturer", "sales", "voice_os", "ai_receptionist"],
    risk_level="low",
    examples=[
        "When should I call this lead?",
        "Best time to reach out",
        "Optimal contact time",
    ],
)
def get_optimal_contact_time(
    lead_id: int,
) -> ToolResult:
    """Determine optimal contact time for a lead."""
    try:
        # Get lead's successful contact history
        history_query = """
            SELECT
                EXTRACT(DOW FROM created_at) as day_of_week,
                EXTRACT(HOUR FROM created_at) as hour,
                outcome
            FROM lead_activities
            WHERE lead_id = :lead_id
            AND activity_type IN ('call', 'meeting')
        """
        history = execute_query(history_query, {"lead_id": lead_id})

        # Get lead's timezone preference (if available)
        lead_query = """
            SELECT timezone, preferred_contact_time
            FROM leads
            WHERE id = :lead_id
        """
        lead = execute_single(lead_query, {"lead_id": lead_id})

        if not lead:
            return ToolResult.no_data(f"Lead {lead_id} not found")

        # Analyze successful contacts
        successful_times = []
        for h in history:
            if h["outcome"] in ["answered", "positive", "completed"]:
                successful_times.append({
                    "day": int(h["day_of_week"]),
                    "hour": int(h["hour"]),
                })

        # Determine best times
        if successful_times:
            # Group by day/hour
            time_counts = {}
            for t in successful_times:
                key = (t["day"], t["hour"])
                time_counts[key] = time_counts.get(key, 0) + 1

            best_times = sorted(time_counts.items(), key=lambda x: x[1], reverse=True)[:3]

            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            recommendations = [
                {
                    "day": day_names[day],
                    "time": f"{hour:02d}:00",
                    "success_count": count,
                }
                for (day, hour), count in best_times
            ]
        else:
            # Use general best practices
            recommendations = [
                {"day": "Tuesday", "time": "10:00", "reason": "Industry best practice"},
                {"day": "Wednesday", "time": "14:00", "reason": "Industry best practice"},
                {"day": "Thursday", "time": "16:00", "reason": "Industry best practice"},
            ]

        # Check preferred time
        preferred = lead.get("preferred_contact_time")
        if preferred:
            recommendations.insert(0, {
                "day": "Any",
                "time": preferred,
                "reason": "Lead's stated preference",
            })

        return ToolResult.success({
            "lead_id": lead_id,
            "timezone": lead.get("timezone", "Unknown"),
            "preferred_time": preferred,
            "data_points": len(successful_times),
            "recommended_times": recommendations[:5],
            "general_guidelines": OPTIMAL_CONTACT_TIMES,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to determine optimal contact time: {str(e)}")


@mortgage_tool(
    name="get_stale_leads",
    description="Find leads that haven't been contacted in a specified number of days. Useful for re-engagement campaigns and preventing leads from going cold.",
    agent_roles=["lead_nurturer", "sales", "manager"],
    risk_level="low",
    examples=[
        "Find leads not contacted in 7 days",
        "Show me stale leads",
        "Get leads I haven't reached out to recently",
        "Which leads need follow-up?",
    ],
)
def get_stale_leads(
    days_since_contact: int = 7,
    limit: int = 50,
    include_never_contacted: bool = True,
) -> ToolResult:
    """
    Get leads that haven't been contacted in N days.

    Args:
        days_since_contact: Number of days since last contact (default 7)
        limit: Maximum number of leads to return (default 50)
        include_never_contacted: Include leads that have never been contacted (default True)

    Returns:
        List of stale leads with contact history and summary statistics
    """
    try:
        # Build the query based on parameters
        if include_never_contacted:
            stale_query = """
                SELECT
                    l.id,
                    l.first_name,
                    l.last_name,
                    l.phone,
                    l.email,
                    l.source as lead_source,
                    l.stage,
                    l.status,
                    l.created_at,
                    l.last_contact_date,
                    l.lead_score,
                    l.assigned_to,
                    lo.name as assigned_lo_name,
                    COALESCE(
                        EXTRACT(DAY FROM NOW() - l.last_contact_date),
                        EXTRACT(DAY FROM NOW() - l.created_at)
                    ) as days_stale,
                    CASE
                        WHEN l.last_contact_date IS NULL THEN true
                        ELSE false
                    END as never_contacted
                FROM leads l
                LEFT JOIN loan_officers lo ON l.assigned_to = lo.id
                WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify', 'Converted')
                    AND l.status NOT IN ('dead', 'unqualified', 'converted')
                    AND (
                        l.last_contact_date < NOW() - INTERVAL :days_interval
                        OR l.last_contact_date IS NULL
                    )
                ORDER BY
                    CASE WHEN l.last_contact_date IS NULL THEN 0 ELSE 1 END,
                    days_stale DESC
                LIMIT :limit
            """
        else:
            stale_query = """
                SELECT
                    l.id,
                    l.first_name,
                    l.last_name,
                    l.phone,
                    l.email,
                    l.source as lead_source,
                    l.stage,
                    l.status,
                    l.created_at,
                    l.last_contact_date,
                    l.lead_score,
                    l.assigned_to,
                    lo.name as assigned_lo_name,
                    EXTRACT(DAY FROM NOW() - l.last_contact_date) as days_stale,
                    false as never_contacted
                FROM leads l
                LEFT JOIN loan_officers lo ON l.assigned_to = lo.id
                WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify', 'Converted')
                    AND l.status NOT IN ('dead', 'unqualified', 'converted')
                    AND l.last_contact_date IS NOT NULL
                    AND l.last_contact_date < NOW() - INTERVAL :days_interval
                ORDER BY days_stale DESC
                LIMIT :limit
            """

        # Execute query with interval as string
        days_interval = f"{days_since_contact} days"
        stale_leads = execute_query(stale_query, {
            "days_interval": days_interval,
            "limit": limit
        })

        if not stale_leads:
            return ToolResult.no_data(f"No leads found that haven't been contacted in {days_since_contact}+ days")

        # Calculate summary statistics
        total_count = len(stale_leads)
        never_contacted_count = sum(1 for lead in stale_leads if lead.get("never_contacted"))

        # Find the oldest stale lead
        max_days = max((lead.get("days_stale") or 0) for lead in stale_leads)

        # Get count by stage for insights
        stage_counts = {}
        for lead in stale_leads:
            stage = lead.get("stage") or "Unknown"
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        # Format leads for response
        formatted_leads = []
        for lead in stale_leads:
            formatted_leads.append({
                "id": lead["id"],
                "name": f"{lead['first_name']} {lead['last_name']}",
                "phone": lead["phone"],
                "email": lead["email"],
                "lead_source": lead["lead_source"],
                "stage": lead["stage"] or lead["status"],
                "lead_score": lead["lead_score"],
                "assigned_to": lead["assigned_lo_name"],
                "created_at": format_date(lead["created_at"]),
                "last_contact_date": format_date(lead["last_contact_date"]) if lead["last_contact_date"] else "Never",
                "days_stale": int(lead["days_stale"] or 0),
                "never_contacted": lead["never_contacted"],
            })

        # Generate summary message
        if never_contacted_count > 0:
            summary = f"{total_count} leads need follow-up ({never_contacted_count} never contacted, oldest {int(max_days)} days)"
        else:
            summary = f"{total_count} leads need follow-up (oldest {int(max_days)} days since contact)"

        return ToolResult.success({
            "stale_leads": formatted_leads,
            "total_count": total_count,
            "never_contacted": never_contacted_count,
            "oldest_days": int(max_days),
            "days_threshold": days_since_contact,
            "by_stage": stage_counts,
            "summary": summary,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get stale leads: {str(e)}")
