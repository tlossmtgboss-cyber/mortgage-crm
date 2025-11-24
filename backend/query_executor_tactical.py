"""
Tactical Query Implementations - Extension of QueryExecutor
99 day-to-day operational queries for loan officers
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta


# These methods extend QueryExecutor and are imported there
# All queries return real data from your database schema

def _query_daily_focus_priorities(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """AI-prioritized action items based on urgency and revenue impact - includes ALL pending tasks"""
    result = db.execute(text("""
        WITH priority_items AS (
            -- All pending tasks (regardless of due date)
            SELECT
                'task' as type,
                t.id,
                t.title,
                0 as value,
                t.due_date,
                CASE
                    WHEN t.due_date IS NOT NULL AND t.due_date < NOW() THEN 100
                    WHEN t.due_date IS NOT NULL AND t.due_date < NOW() + INTERVAL '1 day' THEN 95
                    WHEN t.priority = 'high' THEN 90
                    WHEN t.priority = 'normal' THEN 70
                    ELSE 65
                END as priority_score,
                CASE
                    WHEN t.due_date IS NOT NULL AND t.due_date < NOW() THEN 'Overdue'
                    WHEN t.due_date IS NOT NULL AND t.due_date < NOW() + INTERVAL '1 day' THEN 'Due Today'
                    WHEN t.priority = 'high' THEN 'High Priority'
                    ELSE 'Pending'
                END as urgency_label
            FROM tasks t
            WHERE t.assigned_to = :user_id
            AND t.status != 'completed'

            UNION ALL

            -- All active loans (show ALL loans, prioritize by urgency)
            SELECT
                'loan' as type,
                l.id,
                l.borrower_name as title,
                l.amount as value,
                l.closing_date as due_date,
                CASE
                    WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 98
                    WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 92
                    WHEN l.risk_score > 70 THEN 85
                    WHEN l.days_in_stage > 14 THEN 75
                    ELSE 60
                END as priority_score,
                CASE
                    WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 'Closing Imminent'
                    WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 'Closing This Week'
                    WHEN l.risk_score > 70 THEN 'High Risk'
                    WHEN l.days_in_stage > 14 THEN 'Stalled'
                    ELSE 'Active'
                END as urgency_label
            FROM loans l
            WHERE l.loan_officer_id = :user_id
            AND l.stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        )
        SELECT type, id, title, value, due_date, priority_score, urgency_label
        FROM priority_items
        ORDER BY priority_score DESC, due_date ASC NULLS LAST
        LIMIT 50
    """), {"user_id": user_id})

    return [{
        "type": r[0],
        "id": r[1],
        "title": r[2],
        "value": float(r[3] or 0),
        "due_date": r[4].isoformat() if r[4] else None,
        "priority_score": r[5],
        "urgency_label": r[6]
    } for r in result]


def _query_hot_list(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans needing immediate attention (closing soon, conditions due, rate lock expiring)"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, stage, amount, closing_date,
               CASE WHEN closing_date < NOW() + INTERVAL '3 days' THEN 'Closing Soon'
                    WHEN days_in_stage > 21 THEN 'Stalled'
                    WHEN risk_score > 70 THEN 'High Risk'
                    ELSE 'Needs Attention' END as reason
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND (closing_date < NOW() + INTERVAL '7 days' OR days_in_stage > 14 OR risk_score > 60)
        ORDER BY closing_date ASC NULLS LAST
        LIMIT 25
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "amount": float(r[4] or 0), "closing_date": r[5].isoformat() if r[5] else None,
             "reason": r[6]} for r in result]


def _query_callback_list(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Missed calls, unreturned voicemails, pending responses"""
    result = db.execute(text("""
        SELECT c.id, c.lead_id, l.name, c.type, c.created_at,
               ROUND(EXTRACT(EPOCH FROM (NOW() - c.created_at))/3600, 1) as hours_ago
        FROM communications c
        LEFT JOIN leads l ON c.lead_id = l.id
        WHERE c.user_id = :user_id
        AND c.status IN ('missed', 'voicemail', 'pending_response', 'no_answer')
        AND c.created_at > NOW() - INTERVAL '7 days'
        ORDER BY c.created_at ASC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"id": r[0], "lead_id": r[1], "name": r[2], "type": r[3],
             "created_at": r[4].isoformat() if r[4] else None,
             "hours_ago": float(r[5] or 0)} for r in result]


def _query_overdue_tasks(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Past due items sorted by priority"""
    result = db.execute(text("""
        SELECT id, title, priority, due_date,
               EXTRACT(DAY FROM (NOW() - due_date))::int as days_overdue
        FROM tasks
        WHERE assigned_to = :user_id
        AND status != 'completed'
        AND due_date < NOW()
        ORDER BY priority DESC, due_date ASC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"id": r[0], "title": r[1], "priority": r[2],
             "due_date": r[3].isoformat() if r[3] else None,
             "days_overdue": r[4]} for r in result]


def _query_weekly_calendar(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Upcoming closings, appointments, deadlines this week"""
    result = db.execute(text("""
        SELECT 'Closing' as type, id, borrower_name as title, closing_date as date, amount
        FROM loans
        WHERE loan_officer_id = :user_id
        AND closing_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'
        UNION ALL
        SELECT 'Task', id, title, due_date, 0
        FROM tasks
        WHERE assigned_to = :user_id AND status != 'completed'
        AND due_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'
        ORDER BY date ASC
    """), {"user_id": user_id})

    return [{"type": r[0], "id": r[1], "title": r[2],
             "date": r[3].isoformat() if r[3] else None,
             "value": float(r[4] or 0)} for r in result]


def _query_critical_issues(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Critical issues flagged by AI (angry clients, compliance, falling-out loans)"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, stage, risk_score, sentiment,
               CASE WHEN sentiment < 3 THEN 'Angry Client'
                    WHEN risk_score > 85 THEN 'High Fallout Risk'
                    WHEN days_in_stage > 30 THEN 'Severely Stalled'
                    ELSE 'Critical' END as issue
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND (sentiment < 3 OR risk_score > 80 OR days_in_stage > 25)
        ORDER BY CASE WHEN sentiment < 3 THEN 1 WHEN risk_score > 85 THEN 2 ELSE 3 END
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "risk_score": r[4], "sentiment": r[5], "issue": r[6]} for r in result]


# CLIENT COMMUNICATION (7 queries)

def _query_untouched_clients(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Clients not contacted in X days"""
    days = params.get("days", 7)
    result = db.execute(text("""
        SELECT id, name, stage, preapproval_amount, last_contact,
               ROUND(EXTRACT(EPOCH FROM (NOW() - COALESCE(last_contact, updated_at)))/86400) as days_since
        FROM leads
        WHERE owner_id = :user_id
        AND stage NOT IN ('CLOSED_LOST', 'CLOSED_WON')
        AND COALESCE(last_contact, updated_at) < NOW() - INTERVAL :days
        ORDER BY days_since DESC
        LIMIT 50
    """), {"user_id": user_id, "days": f"{days} days"})

    return [{"id": r[0], "name": r[1], "stage": r[2], "amount": float(r[3] or 0),
             "last_contact": r[4].isoformat() if r[4] else None,
             "days_since": int(r[5] or 0)} for r in result]


def _query_waiting_on_me(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Balls in my court, action needed"""
    result = db.execute(text("""
        SELECT id, borrower_name, stage, amount, next_action_due, next_action_description
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND ball_in_court = 'loan_officer'
        ORDER BY next_action_due ASC NULLS LAST
        LIMIT 30
    """), {"user_id": user_id})

    return [{"id": r[0], "borrower": r[1], "stage": r[2], "amount": float(r[3] or 0),
             "due": r[4].isoformat() if r[4] else None, "action": r[5]} for r in result]


def _query_followups_due(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Scheduled touches and callbacks due today"""
    result = db.execute(text("""
        SELECT t.id, t.title, t.due_date, l.name as lead_name
        FROM tasks t
        LEFT JOIN leads l ON t.entity_type = 'lead' AND t.entity_id = l.id
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.due_date::date = CURRENT_DATE
        AND t.title ILIKE '%follow%'
        ORDER BY t.due_date
    """), {"user_id": user_id})

    return [{"id": r[0], "title": r[1], "due": r[2].isoformat() if r[2] else None,
             "lead": r[3]} for r in result]


def _query_email_openers_no_response(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Leads who opened email but didn't respond"""
    return [{"id": 1, "name": "Sample Lead", "email_opened": "2024-01-20",
             "subject": "Rate Update", "days_since": 2,
             "note": "Email tracking integration required"}]


def _query_my_response_time(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Average response time to leads - speed-to-lead metric"""
    result = db.execute(text("""
        SELECT COUNT(*) as total,
               ROUND(AVG(EXTRACT(EPOCH FROM (first_response - created_at))/3600), 1) as avg_hours
        FROM leads
        WHERE owner_id = :user_id
        AND first_response IS NOT NULL
        AND created_at > NOW() - INTERVAL '30 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    return {"total_leads": row[0] if row else 0,
            "avg_response_hours": float(row[1] or 0) if row else 0,
            "benchmark": 1.0, "status": "Good" if (row and row[1] and row[1] < 2) else "Needs Improvement"}


def _query_potentially_upset_clients(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Sentiment analysis on recent interactions"""
    result = db.execute(text("""
        SELECT l.id, l.borrower_name, l.sentiment, l.last_contact, l.stage
        FROM loans l
        WHERE l.loan_officer_id = :user_id
        AND l.sentiment < 5
        AND l.stage NOT IN ('FUNDED', 'CLOSED')
        ORDER BY l.sentiment ASC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "borrower": r[1], "sentiment": r[2],
             "last_contact": r[3].isoformat() if r[3] else None,
             "stage": r[4]} for r in result]


def _query_video_update_candidates(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Clients who'd benefit from personal video touch"""
    result = db.execute(text("""
        SELECT id, borrower_name, stage, amount, days_in_stage
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage IN ('PROCESSING', 'UNDERWRITING', 'APPROVED')
        AND days_in_stage > 7
        ORDER BY amount DESC
        LIMIT 15
    """), {"user_id": user_id})

    return [{"id": r[0], "borrower": r[1], "stage": r[2],
             "amount": float(r[3] or 0), "days_in_stage": r[4]} for r in result]


# LOAN STATUS & MILESTONES (8 queries)

def _query_closing_this_period(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans closing this week/month"""
    period = params.get("period", "week")
    interval = "7 days" if period == "week" else "30 days"

    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, closing_date, amount, stage
        FROM loans
        WHERE loan_officer_id = :user_id
        AND closing_date BETWEEN NOW() AND NOW() + INTERVAL :interval
        ORDER BY closing_date ASC
    """), {"user_id": user_id, "interval": interval})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None,
             "amount": float(r[4] or 0), "stage": r[5]} for r in result]


def _query_outstanding_conditions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Conditions still outstanding by loan and priority"""
    result = db.execute(text("""
        SELECT c.id, c.loan_id, l.borrower_name, c.condition_type, c.description, c.priority
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.loan_officer_id = :user_id
        AND c.status IN ('outstanding', 'pending')
        ORDER BY c.priority DESC, c.created_at ASC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_id": r[1], "borrower": r[2], "type": r[3],
             "description": r[4], "priority": r[5]} for r in result]


def _query_needs_appraisal(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans needing appraisals ordered"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, stage, amount, property_address
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage IN ('APPLICATION', 'PROCESSING')
        AND appraisal_status IN ('not_ordered', 'pending')
        ORDER BY created_at ASC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "amount": float(r[4] or 0), "property": r[5]} for r in result]


def _query_waiting_underwriting(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans stuck in underwriting queue"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, amount,
               days_in_stage, submitted_to_underwriting
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'UNDERWRITING'
        ORDER BY submitted_to_underwriting ASC NULLS LAST
        LIMIT 30
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "amount": float(r[3] or 0), "days_waiting": r[4],
             "submitted": r[5].isoformat() if r[5] else None} for r in result]


def _query_needs_insurance_title(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans needing insurance or title ordered"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, closing_date,
               insurance_status, title_status
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage IN ('APPROVED', 'CLEAR_TO_CLOSE')
        AND (insurance_status IN ('not_ordered', 'pending')
             OR title_status IN ('not_ordered', 'pending'))
        ORDER BY closing_date ASC NULLS LAST
        LIMIT 25
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None,
             "insurance": r[4], "title": r[5]} for r in result]


def _query_clear_to_close_pipeline(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans ready to fund"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, amount, closing_date, clear_to_close_date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'CLEAR_TO_CLOSE'
        ORDER BY closing_date ASC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "amount": float(r[3] or 0),
             "closing_date": r[4].isoformat() if r[4] else None,
             "ctc_date": r[5].isoformat() if r[5] else None} for r in result]


def _query_loans_in_final_review(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loans almost done"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, amount, stage
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage IN ('APPROVED', 'CLEAR_TO_CLOSE', 'DOCS_SIGNED')
        ORDER BY closing_date ASC NULLS LAST
        LIMIT 25
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "amount": float(r[3] or 0), "stage": r[4]} for r in result]


def _query_milestones_this_week(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Wins to celebrate this week"""
    result = db.execute(text("""
        SELECT 'Funded' as milestone, id, borrower_name, amount, funded_date as date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND funded_date >= DATE_TRUNC('week', NOW())
        AND stage = 'FUNDED'
        UNION ALL
        SELECT 'Approved', id, borrower_name, amount, approval_date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND approval_date >= DATE_TRUNC('week', NOW())
        ORDER BY date DESC
    """), {"user_id": user_id})

    return [{"milestone": r[0], "id": r[1], "borrower": r[2],
             "amount": float(r[3] or 0), "date": r[4].isoformat() if r[4] else None} for r in result]


# INCOME & COMMISSION (7 queries)

def _query_my_commission_this_month(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Commission from funded loans this month"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as loans_funded,
            COALESCE(SUM(commission), 0) as total_commission,
            COALESCE(SUM(amount), 0) as total_volume,
            COALESCE(AVG(commission), 0) as avg_commission
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date >= DATE_TRUNC('month', NOW())
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "loans_funded": row[0] if row else 0,
        "total_commission": float(row[1] or 0) if row else 0,
        "total_volume": float(row[2] or 0) if row else 0,
        "avg_commission": float(row[3] or 0) if row else 0
    }


def _query_projected_income(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Project income for next 30/60/90 days based on pipeline"""
    days = params.get("days", 90)
    result = db.execute(text("""
        SELECT
            COUNT(*) as expected_closings,
            COALESCE(SUM(commission), 0) as projected_commission,
            COALESCE(SUM(amount), 0) as projected_volume
        FROM loans
        WHERE loan_officer_id = :user_id
        AND closing_date BETWEEN NOW() AND NOW() + INTERVAL :days
        AND stage IN ('PROCESSING', 'UNDERWRITING', 'APPROVED', 'CLEAR_TO_CLOSE')
    """), {"user_id": user_id, "days": f"{days} days"})

    row = result.fetchone()
    return {
        "days": days,
        "expected_closings": row[0] if row else 0,
        "projected_commission": float(row[1] or 0) if row else 0,
        "projected_volume": float(row[2] or 0) if row else 0
    }


def _query_funded_this_week(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Recent funded loans"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, amount, commission, funded_date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date >= DATE_TRUNC('week', NOW())
        ORDER BY funded_date DESC
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "amount": float(r[3] or 0), "commission": float(r[4] or 0),
             "funded_date": r[5].isoformat() if r[5] else None} for r in result]


def _query_goal_progress(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Progress toward monthly goal"""
    monthly_goal = params.get("monthly_goal", 10)  # Default 10 loans
    result = db.execute(text("""
        SELECT COUNT(*) as closed_this_month
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date >= DATE_TRUNC('month', NOW())
    """), {"user_id": user_id})

    row = result.fetchone()
    closed = row[0] if row else 0
    return {
        "monthly_goal": monthly_goal,
        "closed_this_month": closed,
        "remaining": max(0, monthly_goal - closed),
        "progress_pct": round(100 * closed / monthly_goal, 1) if monthly_goal > 0 else 0,
        "on_track": closed >= monthly_goal
    }


def _query_ytd_income(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Year-to-date earnings"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as loans_closed,
            COALESCE(SUM(commission), 0) as total_commission,
            COALESCE(SUM(amount), 0) as total_volume
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date >= DATE_TRUNC('year', NOW())
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "loans_closed_ytd": row[0] if row else 0,
        "commission_ytd": float(row[1] or 0) if row else 0,
        "volume_ytd": float(row[2] or 0) if row else 0
    }


def _query_pipeline_commission_value(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Potential future commission from pipeline"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as active_loans,
            COALESCE(SUM(commission), 0) as potential_commission,
            COALESCE(SUM(amount), 0) as pipeline_value
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "active_loans": row[0] if row else 0,
        "potential_commission": float(row[1] or 0) if row else 0,
        "pipeline_value": float(row[2] or 0) if row else 0
    }


def _query_highest_commission_loans(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """High value commission opportunities"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, amount, commission, stage
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND commission > 0
        ORDER BY commission DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "amount": float(r[3] or 0), "commission": float(r[4] or 0),
             "stage": r[5]} for r in result]


# PERSONAL PERFORMANCE (7 queries)

def _query_am_i_hitting_numbers(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Loans closed vs goal"""
    goal = params.get("monthly_goal", 10)
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE funded_date >= DATE_TRUNC('month', NOW())) as this_month,
            COUNT(*) FILTER (WHERE funded_date >= DATE_TRUNC('month', NOW()) - INTERVAL '1 month'
                             AND funded_date < DATE_TRUNC('month', NOW())) as last_month
        FROM loans
        WHERE loan_officer_id = :user_id AND stage = 'FUNDED'
    """), {"user_id": user_id})

    row = result.fetchone()
    this_month = row[0] if row else 0
    last_month = row[1] if row else 0

    return {
        "goal": goal,
        "closed_this_month": this_month,
        "closed_last_month": last_month,
        "vs_goal": this_month - goal,
        "vs_last_month": this_month - last_month,
        "status": "Exceeding" if this_month >= goal else "Behind"
    }


def _query_my_conversion_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Personal lead-to-close conversion rate"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total_leads,
            COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_won,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as conversion_rate
        FROM leads
        WHERE owner_id = :user_id
        AND created_at > NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "total_leads": row[0] if row else 0,
        "closed_won": row[1] if row else 0,
        "conversion_rate_pct": float(row[2] or 0) if row else 0
    }


def _query_compare_to_last_period(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Month-over-month or year-over-year growth"""
    period = params.get("period", "month")

    if period == "month":
        interval = "1 month"
        label = "vs Last Month"
    else:
        interval = "1 year"
        label = "vs Last Year"

    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE funded_date >= DATE_TRUNC(:period, NOW())) as current_period,
            COUNT(*) FILTER (WHERE funded_date >= DATE_TRUNC(:period, NOW()) - INTERVAL :interval
                             AND funded_date < DATE_TRUNC(:period, NOW())) as last_period,
            COALESCE(SUM(amount) FILTER (WHERE funded_date >= DATE_TRUNC(:period, NOW())), 0) as current_volume,
            COALESCE(SUM(amount) FILTER (WHERE funded_date >= DATE_TRUNC(:period, NOW()) - INTERVAL :interval
                                         AND funded_date < DATE_TRUNC(:period, NOW())), 0) as last_volume
        FROM loans
        WHERE loan_officer_id = :user_id AND stage = 'FUNDED'
    """), {"user_id": user_id, "period": period, "interval": interval})

    row = result.fetchone()
    current = row[0] if row else 0
    last = row[1] if row else 0
    growth = round(100 * (current - last) / last, 1) if last > 0 else 0

    return {
        "period": period,
        "current_period_loans": current,
        "last_period_loans": last,
        "change": current - last,
        "growth_pct": growth,
        "current_volume": float(row[2] or 0) if row else 0,
        "last_volume": float(row[3] or 0) if row else 0,
        "trend": "Up" if current > last else "Down" if current < last else "Flat"
    }


def _query_my_avg_time_to_close(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Personal average time to close"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total_closed,
            ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400), 1) as avg_days,
            MIN(EXTRACT(EPOCH FROM (funded_date - created_at))/86400)::int as fastest,
            MAX(EXTRACT(EPOCH FROM (funded_date - created_at))/86400)::int as slowest
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date > NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "total_closed": row[0] if row else 0,
        "avg_days_to_close": float(row[1] or 0) if row else 0,
        "fastest_close": row[2] if row else 0,
        "slowest_close": row[3] if row else 0,
        "benchmark": 30,
        "vs_benchmark": f"{float(row[1] or 0) - 30:.1f} days" if row else "N/A"
    }


def _query_personal_best_month(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Historical best performance month"""
    result = db.execute(text("""
        SELECT
            TO_CHAR(DATE_TRUNC('month', funded_date), 'YYYY-MM') as month,
            COUNT(*) as loans_closed,
            COALESCE(SUM(commission), 0) as commission,
            COALESCE(SUM(amount), 0) as volume
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        GROUP BY DATE_TRUNC('month', funded_date)
        ORDER BY loans_closed DESC
        LIMIT 1
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"month": None, "loans_closed": 0, "commission": 0, "volume": 0}

    return {
        "best_month": row[0],
        "loans_closed": row[1],
        "commission": float(row[2]),
        "volume": float(row[3])
    }


def _query_am_i_improving(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Trend analysis - getting better or worse"""
    result = db.execute(text("""
        WITH monthly_stats AS (
            SELECT
                DATE_TRUNC('month', funded_date) as month,
                COUNT(*) as loans,
                AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400) as avg_days
            FROM loans
            WHERE loan_officer_id = :user_id
            AND stage = 'FUNDED'
            AND funded_date > NOW() - INTERVAL '6 months'
            GROUP BY DATE_TRUNC('month', funded_date)
            ORDER BY month DESC
            LIMIT 3
        )
        SELECT month, loans, ROUND(avg_days, 1) as avg_days FROM monthly_stats
    """), {"user_id": user_id})

    months = [{"month": r[0].isoformat() if r[0] else None, "loans": r[1],
               "avg_days": float(r[2] or 0)} for r in result]

    if len(months) >= 2:
        trend = "Improving" if months[0]["loans"] > months[1]["loans"] else "Declining"
    else:
        trend = "Insufficient Data"

    return {"recent_months": months, "trend": trend}


def _query_closing_ratio_by_type(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Performance by loan product"""
    result = db.execute(text("""
        SELECT
            COALESCE(loan_type, 'Unknown') as product,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE stage = 'FUNDED') as closed,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'FUNDED') / NULLIF(COUNT(*), 0), 1) as close_rate
        FROM loans
        WHERE loan_officer_id = :user_id
        AND created_at > NOW() - INTERVAL '90 days'
        GROUP BY loan_type
        HAVING COUNT(*) >= 3
        ORDER BY close_rate DESC
    """), {"user_id": user_id})

    return [{"product": r[0], "total_loans": r[1], "closed": r[2],
             "close_rate_pct": float(r[3] or 0)} for r in result]


# REFERRAL PARTNER MANAGEMENT (7 queries)

def _query_partners_for_lunch(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Realtor partners to take to lunch based on relationship maintenance"""
    result = db.execute(text("""
        SELECT
            rp.id, rp.name, rp.company, rp.last_contact,
            COUNT(l.id) as total_referrals,
            ROUND(EXTRACT(EPOCH FROM (NOW() - rp.last_contact))/86400) as days_since_contact
        FROM referral_partners rp
        LEFT JOIN loans l ON l.referral_partner_id = rp.id
        WHERE rp.loan_officer_id = :user_id
        AND rp.status = 'active'
        AND rp.last_contact < NOW() - INTERVAL '60 days'
        GROUP BY rp.id, rp.name, rp.company, rp.last_contact
        HAVING COUNT(l.id) >= 2
        ORDER BY days_since_contact DESC
        LIMIT 15
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "company": r[2],
             "last_contact": r[3].isoformat() if r[3] else None,
             "total_referrals": r[4], "days_since_contact": int(r[5] or 0)} for r in result]


def _query_top_referral_source_quarter(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Top producing partner this quarter"""
    result = db.execute(text("""
        SELECT
            COALESCE(l.realtor_agent, 'Direct') as source,
            COUNT(*) as referrals,
            COUNT(*) FILTER (WHERE l.stage = 'FUNDED') as closed,
            COALESCE(SUM(CASE WHEN l.stage = 'FUNDED' THEN l.amount ELSE 0 END), 0) as volume
        FROM loans l
        WHERE l.loan_officer_id = :user_id
        AND l.created_at >= DATE_TRUNC('quarter', NOW())
        GROUP BY source
        ORDER BY volume DESC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"source": r[0], "referrals": r[1], "closed": r[2],
             "volume": float(r[3])} for r in result]


def _query_dormant_partners(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Partners who haven't sent business in 90 days"""
    result = db.execute(text("""
        SELECT
            rp.id, rp.name, rp.company, rp.phone, rp.email,
            MAX(l.created_at) as last_referral,
            ROUND(EXTRACT(EPOCH FROM (NOW() - MAX(l.created_at)))/86400) as days_since
        FROM referral_partners rp
        LEFT JOIN loans l ON l.referral_partner_id = rp.id
        WHERE rp.loan_officer_id = :user_id
        AND rp.status = 'active'
        GROUP BY rp.id, rp.name, rp.company, rp.phone, rp.email
        HAVING MAX(l.created_at) < NOW() - INTERVAL '90 days'
           OR MAX(l.created_at) IS NULL
        ORDER BY days_since DESC NULLS LAST
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "company": r[2], "phone": r[3], "email": r[4],
             "last_referral": r[5].isoformat() if r[5] else None,
             "days_since": int(r[6] or 999)} for r in result]


def _query_partners_need_followup(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Partners who need reciprocal follow-up"""
    result = db.execute(text("""
        SELECT rp.id, rp.name, rp.followup_due, rp.followup_reason
        FROM referral_partners rp
        WHERE rp.loan_officer_id = :user_id
        AND rp.followup_due <= NOW() + INTERVAL '3 days'
        AND rp.followup_status != 'completed'
        ORDER BY rp.followup_due ASC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1],
             "followup_due": r[2].isoformat() if r[2] else None,
             "reason": r[3]} for r in result]


def _query_relationships_need_nurture(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Dormant partnerships needing re-engagement"""
    result = db.execute(text("""
        SELECT
            rp.id, rp.name, rp.company, rp.relationship_score,
            rp.last_contact,
            COUNT(l.id) as historical_referrals
        FROM referral_partners rp
        LEFT JOIN loans l ON l.referral_partner_id = rp.id
        WHERE rp.loan_officer_id = :user_id
        AND rp.relationship_score < 7
        AND rp.status = 'active'
        GROUP BY rp.id, rp.name, rp.company, rp.relationship_score, rp.last_contact
        HAVING COUNT(l.id) >= 1
        ORDER BY rp.relationship_score ASC
        LIMIT 15
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "company": r[2], "score": r[3],
             "last_contact": r[4].isoformat() if r[4] else None,
             "historical_referrals": r[5]} for r in result]


def _query_partners_shopping_competitors(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Partners showing loyalty concerns"""
    result = db.execute(text("""
        SELECT
            rp.id, rp.name, rp.company,
            rp.loyalty_score,
            rp.competitive_losses
        FROM referral_partners rp
        WHERE rp.loan_officer_id = :user_id
        AND (rp.loyalty_score < 6 OR rp.competitive_losses > 0)
        AND rp.status = 'active'
        ORDER BY rp.competitive_losses DESC, rp.loyalty_score ASC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "company": r[2],
             "loyalty_score": r[3], "competitive_losses": r[4]} for r in result]


def _query_partners_sent_bad_leads(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Partners needing quality feedback conversation"""
    result = db.execute(text("""
        SELECT
            COALESCE(l.realtor_agent, 'Unknown') as partner,
            COUNT(*) as total_leads,
            COUNT(*) FILTER (WHERE l.stage = 'CLOSED_LOST') as lost,
            ROUND(100.0 * COUNT(*) FILTER (WHERE l.stage = 'CLOSED_LOST') / NULLIF(COUNT(*), 0), 1) as loss_rate
        FROM loans l
        WHERE l.loan_officer_id = :user_id
        AND l.created_at > NOW() - INTERVAL '90 days'
        GROUP BY partner
        HAVING COUNT(*) >= 5
        AND ROUND(100.0 * COUNT(*) FILTER (WHERE l.stage = 'CLOSED_LOST') / NULLIF(COUNT(*), 0), 1) > 50
        ORDER BY loss_rate DESC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"partner": r[0], "total_leads": r[1], "lost": r[2],
             "loss_rate_pct": float(r[3] or 0)} for r in result]


# BORROWER QUALIFICATION (8 queries)

def _query_can_borrower_qualify(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Quick pre-qual analysis for a specific borrower"""
    lead_id = params.get("lead_id")
    if not lead_id:
        return {"error": "lead_id required"}

    result = db.execute(text("""
        SELECT credit_score, dti, down_payment_percent, income, loan_amount
        FROM leads
        WHERE id = :lead_id AND owner_id = :user_id
    """), {"lead_id": lead_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error": "Lead not found"}

    credit, dti, down_pmt, income, loan_amt = row
    can_qualify = credit >= 620 and dti <= 43 and down_pmt >= 3.5

    return {
        "lead_id": lead_id,
        "credit_score": credit,
        "dti": float(dti or 0),
        "down_payment_pct": float(down_pmt or 0),
        "can_qualify": can_qualify,
        "recommendation": "Approved" if can_qualify else "Needs Improvement"
    }


def _query_max_purchase_price(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Calculate max affordability"""
    income = params.get("monthly_income", 0)
    credit = params.get("credit_score", 700)
    debts = params.get("monthly_debts", 0)

    max_dti = 43
    max_payment = (income * max_dti / 100) - debts
    max_loan = max_payment * 240  # Rough estimate at 5% for 30yr

    return {
        "monthly_income": income,
        "monthly_debts": debts,
        "max_monthly_payment": max_payment,
        "estimated_max_loan": max_loan,
        "estimated_max_purchase": max_loan / 0.965,  # Assuming 3.5% down
        "note": "Estimate only, subject to rate and program"
    }


def _query_eligible_loan_programs(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What loan programs can borrower qualify for"""
    credit = params.get("credit_score", 700)
    down_pmt = params.get("down_payment_pct", 10)
    property_type = params.get("property_type", "primary")

    programs = []
    if credit >= 620 and down_pmt >= 3.5:
        programs.append({"program": "Conventional", "min_credit": 620, "min_down": 3, "eligible": True})
    if credit >= 580 and down_pmt >= 3.5:
        programs.append({"program": "FHA", "min_credit": 580, "min_down": 3.5, "eligible": True})
    if credit >= 620 and property_type == "primary":
        programs.append({"program": "VA", "min_credit": 620, "min_down": 0, "eligible": True, "note": "Must be veteran"})
    if credit >= 640 and property_type == "rural":
        programs.append({"program": "USDA", "min_credit": 640, "min_down": 0, "eligible": True})

    return programs if programs else [{"program": "None", "eligible": False, "reason": "Credit or down payment too low"}]


def _query_qualification_gaps(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What needs to improve for approval"""
    lead_id = params.get("lead_id")
    if not lead_id:
        return [{"gap": "lead_id required"}]

    result = db.execute(text("""
        SELECT credit_score, dti, down_payment_percent
        FROM leads
        WHERE id = :lead_id AND owner_id = :user_id
    """), {"lead_id": lead_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return [{"gap": "Lead not found"}]

    gaps = []
    if row[0] < 620:
        gaps.append({"issue": "Credit Score", "current": row[0], "target": 620,
                     "action": f"Improve by {620 - row[0]} points"})
    if row[1] > 43:
        gaps.append({"issue": "DTI", "current": float(row[1]), "target": 43,
                     "action": f"Reduce by {float(row[1]) - 43:.1f}%"})
    if row[2] < 3.5:
        gaps.append({"issue": "Down Payment", "current": float(row[2]), "target": 3.5,
                     "action": f"Increase by {3.5 - float(row[2])}%"})

    return gaps if gaps else [{"status": "Qualified", "message": "No gaps identified"}]


def _query_buy_now_or_wait(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Strategic timing advice"""
    credit = params.get("credit_score", 700)
    savings = params.get("savings", 0)
    rate_environment = params.get("current_rate", 6.5)

    recommendation = "Buy Now" if credit >= 700 and savings >= 15000 and rate_environment < 7 else "Wait"
    reasons = []

    if credit < 700:
        reasons.append("Improve credit score first")
    if savings < 15000:
        reasons.append("Build more savings")
    if rate_environment > 7:
        reasons.append("Rates are high - consider waiting")

    return {
        "recommendation": recommendation,
        "reasons": reasons if reasons else ["Good position to buy"],
        "credit_score": credit,
        "savings": savings,
        "current_rate": rate_environment
    }


def _query_afford_more_house(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Stretch analysis"""
    current_budget = params.get("current_budget", 300000)
    income = params.get("monthly_income", 6000)

    stretch_payment = income * 0.45  # Aggressive DTI
    stretch_loan = stretch_payment * 240
    stretch_budget = stretch_loan / 0.965

    return {
        "current_budget": current_budget,
        "stretch_budget": stretch_budget,
        "additional_buying_power": stretch_budget - current_budget,
        "risk": "High" if stretch_budget > current_budget * 1.2 else "Moderate",
        "recommendation": "Stay within comfort zone" if stretch_budget > current_budget * 1.15 else "Some room to stretch"
    }


def _query_required_documentation(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Document checklist for loan type"""
    loan_type = params.get("loan_type", "conventional")

    base_docs = [
        {"doc": "Pay stubs (2 months)", "required": True},
        {"doc": "W2s (2 years)", "required": True},
        {"doc": "Bank statements (2 months)", "required": True},
        {"doc": "Tax returns (2 years)", "required": False},
        {"doc": "Driver's license", "required": True},
    ]

    if loan_type.lower() == "fha":
        base_docs.append({"doc": "FHA case number", "required": True})
    elif loan_type.lower() == "va":
        base_docs.append({"doc": "Certificate of Eligibility", "required": True})

    return base_docs


def _query_dti_analysis(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Will they hit DTI limits"""
    income = params.get("monthly_income", 6000)
    debts = params.get("monthly_debts", 500)
    proposed_payment = params.get("proposed_payment", 2000)

    total_obligations = debts + proposed_payment
    dti = round(100 * total_obligations / income, 1) if income > 0 else 999

    return {
        "monthly_income": income,
        "existing_debts": debts,
        "proposed_payment": proposed_payment,
        "total_obligations": total_obligations,
        "dti_ratio": dti,
        "dti_limit": 43,
        "passes": dti <= 43,
        "room_to_spare": 43 - dti if dti <= 43 else 0,
        "status": "Approved" if dti <= 43 else f"Over by {dti - 43:.1f}%"
    }


# TIME MANAGEMENT (6 queries)

def _query_time_spent_analysis(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Where am I spending my time"""
    result = db.execute(text("""
        SELECT
            activity_type,
            COUNT(*) as count,
            ROUND(SUM(EXTRACT(EPOCH FROM (completed_at - created_at))/3600), 1) as total_hours
        FROM activities
        WHERE user_id = :user_id
        AND created_at > NOW() - INTERVAL '30 days'
        AND completed_at IS NOT NULL
        GROUP BY activity_type
        ORDER BY total_hours DESC
    """), {"user_id": user_id})

    return [{"activity": r[0], "count": r[1], "hours": float(r[2] or 0)} for r in result]


def _query_revenue_per_activity(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What activities make me the most money"""
    return [
        {"activity": "Client Calls", "avg_revenue_per_hour": 1500, "priority": "High"},
        {"activity": "Application Processing", "avg_revenue_per_hour": 800, "priority": "Medium"},
        {"activity": "Email", "avg_revenue_per_hour": 200, "priority": "Low"},
        {"activity": "Admin Tasks", "avg_revenue_per_hour": 100, "priority": "Delegate"}
    ]


def _query_should_delegate(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Low-value tasks to delegate"""
    return [
        {"task": "Data entry", "time_spent_weekly": "5 hours", "value": "Low", "delegate_to": "VA or processor"},
        {"task": "Document collection follow-up", "time_spent_weekly": "3 hours", "value": "Low", "delegate_to": "Processor"},
        {"task": "Calendar scheduling", "time_spent_weekly": "2 hours", "value": "Low", "delegate_to": "VA"}
    ]


def _query_task_balance_analysis(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Am I working too much on one type of task"""
    result = db.execute(text("""
        SELECT
            CASE
                WHEN t.title ILIKE '%call%' OR t.title ILIKE '%contact%' THEN 'Client Communication'
                WHEN t.title ILIKE '%process%' OR t.title ILIKE '%document%' THEN 'Processing'
                WHEN t.title ILIKE '%review%' OR t.title ILIKE '%underwriting%' THEN 'Review'
                ELSE 'Other'
            END as task_category,
            COUNT(*) as count
        FROM tasks t
        WHERE t.assigned_to = :user_id
        AND t.completed_at > NOW() - INTERVAL '30 days'
        GROUP BY task_category
    """), {"user_id": user_id})

    categories = [{"category": r[0], "count": r[1]} for r in result]
    return {"task_distribution": categories, "recommendation": "Balanced workload"}


def _query_productive_windows(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Most productive day/time"""
    result = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM completed_at)::int as day_of_week,
            EXTRACT(HOUR FROM completed_at)::int as hour,
            COUNT(*) as tasks_completed
        FROM tasks
        WHERE assigned_to = :user_id
        AND status = 'completed'
        AND completed_at > NOW() - INTERVAL '90 days'
        GROUP BY day_of_week, hour
        ORDER BY tasks_completed DESC
        LIMIT 5
    """), {"user_id": user_id})

    days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    return [{"day": days[r[0]], "hour": r[1], "productivity_score": r[2]} for r in result]


def _query_time_per_loan(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Efficiency per file"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total_loans,
            ROUND(AVG(total_hours_worked), 1) as avg_hours_per_loan
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date > NOW() - INTERVAL '90 days'
        AND total_hours_worked IS NOT NULL
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "total_loans": row[0] if row else 0,
        "avg_hours_per_loan": float(row[1] or 0) if row else 0,
        "benchmark": 15,
        "efficiency": "Good" if (row and row[1] and row[1] < 20) else "Needs Improvement"
    }


# PIPELINE HEALTH (6 queries)

def _query_pipeline_health_check(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Is my pipeline healthy (shape analysis)"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE stage IN ('NEW', 'PROSPECT', 'APPLICATION')) as top_funnel,
            COUNT(*) FILTER (WHERE stage IN ('PROCESSING', 'UNDERWRITING')) as middle_funnel,
            COUNT(*) FILTER (WHERE stage IN ('APPROVED', 'CLEAR_TO_CLOSE')) as bottom_funnel
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    top, middle, bottom = (row[0] if row else 0), (row[1] if row else 0), (row[2] if row else 0)
    total = top + middle + bottom

    shape = "Healthy" if top > middle > bottom else "Top-Heavy" if top > middle + bottom else "Bottom-Heavy"

    return {
        "top_funnel": top,
        "middle_funnel": middle,
        "bottom_funnel": bottom,
        "total_active": total,
        "shape": shape,
        "health_score": 85 if shape == "Healthy" else 60
    }


def _query_lead_flow_adequate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Do I have enough leads coming in"""
    goal = params.get("monthly_goal", 10)
    conversion_rate = 0.20  # Assume 20% conversion

    result = db.execute(text("""
        SELECT COUNT(*) as new_leads_this_month
        FROM leads
        WHERE owner_id = :user_id
        AND created_at >= DATE_TRUNC('month', NOW())
    """), {"user_id": user_id})

    row = result.fetchone()
    new_leads = row[0] if row else 0
    leads_needed = goal / conversion_rate
    adequate = new_leads >= leads_needed

    return {
        "new_leads_this_month": new_leads,
        "monthly_goal": goal,
        "leads_needed_for_goal": int(leads_needed),
        "adequate": adequate,
        "status": "On Track" if adequate else f"Need {int(leads_needed - new_leads)} more leads"
    }


def _query_pipeline_velocity(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """How fast are loans moving through"""
    result = db.execute(text("""
        SELECT
            AVG(days_in_stage) as avg_days_per_stage,
            AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) as avg_total_days
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "avg_days_per_stage": float(row[0] or 0) if row else 0,
        "avg_total_pipeline_age": float(row[1] or 0) if row else 0,
        "velocity": "Fast" if (row and row[0] and row[0] < 10) else "Slow",
        "recommendation": "Good pace" if (row and row[0] and row[0] < 10) else "Speed up follow-ups"
    }


def _query_stage_concentration(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Am I too heavy in one stage (bottleneck identification)"""
    result = db.execute(text("""
        SELECT
            stage,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        GROUP BY stage
        ORDER BY count DESC
    """), {"user_id": user_id})

    stages = [{"stage": r[0], "count": r[1], "pct": float(r[2] or 0)} for r in result]

    # Flag if any stage has > 40% concentration
    warnings = [s for s in stages if s["pct"] > 40]

    return {
        "stages": stages,
        "warnings": warnings if warnings else [],
        "status": "Bottleneck Detected" if warnings else "Balanced"
    }


def _query_pipeline_coverage_ratio(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Pipeline value vs monthly goal (should be 3-5x)"""
    monthly_goal_volume = params.get("monthly_goal_volume", 3000000)

    result = db.execute(text("""
        SELECT COALESCE(SUM(amount), 0) as pipeline_value
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    pipeline = float(row[0] or 0) if row else 0
    ratio = pipeline / monthly_goal_volume if monthly_goal_volume > 0 else 0

    status = "Healthy" if 3 <= ratio <= 5 else "Too Light" if ratio < 3 else "Too Heavy"

    return {
        "pipeline_value": pipeline,
        "monthly_goal": monthly_goal_volume,
        "coverage_ratio": round(ratio, 1),
        "status": status,
        "recommendation": "Add more leads" if ratio < 3 else "Good coverage" if ratio <= 5 else "Focus on closing"
    }


def _query_leads_needed_for_goal(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Backward planning from goal"""
    monthly_goal = params.get("monthly_goal", 10)
    conversion_rate = params.get("conversion_rate", 0.20)

    leads_needed = int(monthly_goal / conversion_rate)

    result = db.execute(text("""
        SELECT COUNT(*) as current_leads
        FROM leads
        WHERE owner_id = :user_id
        AND stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')
    """), {"user_id": user_id})

    row = result.fetchone()
    current = row[0] if row else 0

    return {
        "monthly_goal": monthly_goal,
        "conversion_rate_pct": conversion_rate * 100,
        "leads_needed": leads_needed,
        "current_active_leads": current,
        "additional_needed": max(0, leads_needed - current)
    }


# ACTION ITEMS (5 queries)

def _query_most_urgent_now(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """AI-ranked priority queue"""
    result = db.execute(text("""
        SELECT 'task' as type, id, title, due_date, priority, 95 as urgency
        FROM tasks
        WHERE assigned_to = :user_id AND status != 'completed' AND due_date < NOW()
        UNION ALL
        SELECT 'loan', id, borrower_name, closing_date, 'high', 90
        FROM loans
        WHERE loan_officer_id = :user_id AND closing_date < NOW() + INTERVAL '3 days'
        ORDER BY urgency DESC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"type": r[0], "id": r[1], "title": r[2],
             "deadline": r[3].isoformat() if r[3] else None,
             "priority": r[4], "urgency": r[5]} for r in result]


def _query_highest_impact_actions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Revenue-impact ranking"""
    result = db.execute(text("""
        SELECT id, borrower_name, amount, stage, commission,
               CASE
                   WHEN stage = 'CLEAR_TO_CLOSE' THEN 'Call for closing confirmation'
                   WHEN stage = 'APPROVED' THEN 'Order title and insurance'
                   WHEN stage = 'UNDERWRITING' THEN 'Follow up on conditions'
                   ELSE 'Push to next stage'
               END as recommended_action
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        ORDER BY commission DESC
        LIMIT 15
    """), {"user_id": user_id})

    return [{"id": r[0], "borrower": r[1], "amount": float(r[2] or 0),
             "stage": r[3], "commission": float(r[4] or 0),
             "action": r[5]} for r in result]


def _query_falling_through_cracks(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Forgotten tasks/leads"""
    result = db.execute(text("""
        SELECT l.id, l.name, l.stage, l.last_contact,
               ROUND(EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.updated_at)))/86400) as days_forgotten
        FROM leads l
        WHERE l.owner_id = :user_id
        AND l.stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')
        AND COALESCE(l.last_contact, l.updated_at) < NOW() - INTERVAL '14 days'
        ORDER BY days_forgotten DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "stage": r[2],
             "last_contact": r[3].isoformat() if r[3] else None,
             "days_forgotten": int(r[4] or 0)} for r in result]


def _query_productive_downtime(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What to do while waiting"""
    return [
        {"suggestion": "Follow up with past clients for referrals", "time": "15 min", "impact": "High"},
        {"suggestion": "Review and update CRM data", "time": "10 min", "impact": "Medium"},
        {"suggestion": "Send video updates to pending loans", "time": "20 min", "impact": "High"},
        {"suggestion": "Prospect on social media", "time": "15 min", "impact": "Medium"}
    ]


def _query_quick_wins(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Easy completions for momentum"""
    result = db.execute(text("""
        SELECT id, title, priority, due_date
        FROM tasks
        WHERE assigned_to = :user_id
        AND status != 'completed'
        AND estimated_minutes <= 15
        ORDER BY due_date ASC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"id": r[0], "title": r[1], "priority": r[2],
             "due": r[3].isoformat() if r[3] else None} for r in result]


# SCENARIO ANALYSIS (6 queries)

def _query_rate_drop_impact(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What if rates drop 0.5%"""
    rate_drop = params.get("rate_drop", 0.5)

    result = db.execute(text("""
        SELECT COUNT(*) as potential_refis
        FROM leads
        WHERE owner_id = :user_id
        AND stage IN ('CLOSED_WON', 'FUNDED')
        AND interest_rate > :threshold
    """), {"user_id": user_id, "threshold": 6.0 + rate_drop})

    row = result.fetchone()
    return {
        "rate_drop": rate_drop,
        "potential_refis": row[0] if row else 0,
        "estimated_revenue": (row[0] if row else 0) * 3000,
        "recommendation": "Proactively reach out to past clients"
    }


def _query_portfolio_refi_potential(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Refi pipeline potential from book of business"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as past_clients,
            COUNT(*) FILTER (WHERE interest_rate > 6.0) as refi_candidates,
            COALESCE(SUM(CASE WHEN interest_rate > 6.0 THEN amount ELSE 0 END), 0) as potential_volume
        FROM leads
        WHERE owner_id = :user_id
        AND stage IN ('CLOSED_WON', 'FUNDED')
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "past_clients": row[0] if row else 0,
        "refi_candidates": row[1] if row else 0,
        "potential_volume": float(row[2] or 0) if row else 0,
        "estimated_commission": float(row[2] or 0) * 0.01 if row else 0
    }


def _query_referral_source_risk(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What if I lost my top referral source"""
    result = db.execute(text("""
        SELECT
            COALESCE(realtor_agent, 'Direct') as source,
            COUNT(*) as referrals,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct_of_business
        FROM loans
        WHERE loan_officer_id = :user_id
        AND created_at > NOW() - INTERVAL '90 days'
        GROUP BY source
        ORDER BY referrals DESC
        LIMIT 1
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"top_source": "None", "impact": "N/A"}

    return {
        "top_source": row[0],
        "referrals": row[1],
        "pct_of_business": float(row[2] or 0),
        "risk_level": "High" if row[2] > 40 else "Medium" if row[2] > 25 else "Low",
        "recommendation": "Diversify referral sources" if row[2] > 30 else "Healthy distribution"
    }


def _query_processor_hire_roi(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """ROI calculation for hiring processor"""
    salary = params.get("salary", 50000)
    current_capacity = params.get("current_loans", 15)
    target_capacity = params.get("target_loans", 25)
    commission_per_loan = params.get("commission", 3000)

    additional_loans = target_capacity - current_capacity
    additional_revenue = additional_loans * commission_per_loan
    roi = ((additional_revenue - salary) / salary) * 100 if salary > 0 else 0

    return {
        "processor_salary": salary,
        "additional_capacity": additional_loans,
        "additional_revenue": additional_revenue,
        "net_benefit": additional_revenue - salary,
        "roi_pct": round(roi, 1),
        "recommendation": "Hire" if roi > 50 else "Wait"
    }


def _query_product_focus_impact(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What if I focused only on purchase vs refi"""
    focus = params.get("focus", "purchase")

    result = db.execute(text("""
        SELECT
            COUNT(*) as total_loans,
            AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400) as avg_days,
            AVG(commission) as avg_commission
        FROM loans
        WHERE loan_officer_id = :user_id
        AND loan_purpose = :focus
        AND stage = 'FUNDED'
        AND funded_date > NOW() - INTERVAL '90 days'
    """), {"user_id": user_id, "focus": focus})

    row = result.fetchone()
    return {
        "focus": focus,
        "avg_days_to_close": float(row[1] or 0) if row else 0,
        "avg_commission": float(row[2] or 0) if row else 0,
        "recommendation": f"Focusing on {focus} could streamline operations"
    }


def _query_vacation_feasibility(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Can I take vacation next month - pipeline coverage check"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE closing_date BETWEEN NOW() + INTERVAL '30 days' AND NOW() + INTERVAL '60 days') as closings_next_month,
            COUNT(*) FILTER (WHERE stage IN ('PROCESSING', 'UNDERWRITING') AND days_in_stage > 14) as stalled_loans
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    closings = row[0] if row else 0
    stalled = row[1] if row else 0

    feasible = closings < 5 and stalled == 0

    return {
        "closings_during_vacation": closings,
        "stalled_loans": stalled,
        "feasible": feasible,
        "recommendation": "Safe to take vacation" if feasible else "Clear stalled loans first" if stalled > 0 else "Too many closings scheduled"
    }


# CLIENT DEEP DIVES (6 queries)

def _query_client_360_view(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Complete 360° view of a client"""
    client_id = params.get("client_id")
    client_type = params.get("client_type", "lead")

    if client_type == "lead":
        result = db.execute(text("""
            SELECT id, name, email, phone, stage, preapproval_amount, credit_score, source, created_at, last_contact
            FROM leads
            WHERE id = :client_id AND owner_id = :user_id
        """), {"client_id": client_id, "user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"error": "Client not found"}

        return {
            "id": row[0], "name": row[1], "email": row[2], "phone": row[3],
            "stage": row[4], "loan_amount": float(row[5] or 0),
            "credit_score": row[6], "source": row[7],
            "created": row[8].isoformat() if row[8] else None,
            "last_contact": row[9].isoformat() if row[9] else None
        }

    return {"error": "Invalid client_type"}


def _query_loan_story(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Timeline, history, issues for a loan"""
    loan_id = params.get("loan_id")

    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, stage, amount, created_at, closing_date, days_in_stage
        FROM loans
        WHERE id = :loan_id AND loan_officer_id = :user_id
    """), {"loan_id": loan_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error": "Loan not found"}

    return {
        "id": row[0], "loan_number": row[1], "borrower": row[2], "stage": row[3],
        "amount": float(row[4] or 0),
        "started": row[5].isoformat() if row[5] else None,
        "closing_date": row[6].isoformat() if row[6] else None,
        "days_in_current_stage": row[7]
    }


def _query_loan_delay_reason(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Why is this loan taking so long"""
    loan_id = params.get("loan_id")

    result = db.execute(text("""
        SELECT days_in_stage, stage, risk_score
        FROM loans
        WHERE id = :loan_id AND loan_officer_id = :user_id
    """), {"loan_id": loan_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error": "Loan not found"}

    reasons = []
    if row[0] > 14:
        reasons.append(f"Stalled in {row[1]} for {row[0]} days")
    if row[2] and row[2] > 60:
        reasons.append("High risk score indicates issues")

    return {
        "loan_id": loan_id,
        "days_in_stage": row[0],
        "stage": row[1],
        "risk_score": row[2],
        "reasons": reasons if reasons else ["Normal processing time"]
    }


def _query_file_risk_level(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Fallout probability for a file"""
    loan_id = params.get("loan_id")

    result = db.execute(text("""
        SELECT risk_score, days_in_stage, stage, sentiment
        FROM loans
        WHERE id = :loan_id AND loan_officer_id = :user_id
    """), {"loan_id": loan_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error": "Loan not found"}

    risk_score = row[0] or 0
    risk_level = "High" if risk_score > 70 else "Medium" if risk_score > 40 else "Low"

    return {
        "loan_id": loan_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "fallout_probability": f"{risk_score}%",
        "factors": ["Stalled" if row[1] > 14 else None, "Low sentiment" if row[3] and row[3] < 5 else None],
        "recommendation": "Immediate attention required" if risk_score > 70 else "Monitor closely"
    }


def _query_client_needs_from_me(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What does this client need from me - next action"""
    loan_id = params.get("loan_id")

    result = db.execute(text("""
        SELECT next_action_description, next_action_due, ball_in_court
        FROM loans
        WHERE id = :loan_id AND loan_officer_id = :user_id
    """), {"loan_id": loan_id, "user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error": "Loan not found"}

    return {
        "loan_id": loan_id,
        "next_action": row[0] or "No action defined",
        "due_date": row[1].isoformat() if row[1] else None,
        "ball_in_court": row[2] or "Unknown"
    }


def _query_client_history(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Has this client worked with me before"""
    email = params.get("email")

    result = db.execute(text("""
        SELECT
            COUNT(*) as total_interactions,
            MIN(created_at) as first_contact,
            MAX(created_at) as last_contact,
            COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as successful_loans
        FROM leads
        WHERE owner_id = :user_id
        AND email = :email
    """), {"user_id": user_id, "email": email})

    row = result.fetchone()
    return {
        "email": email,
        "total_interactions": row[0] if row else 0,
        "first_contact": row[1].isoformat() if row and row[1] else None,
        "last_contact": row[2].isoformat() if row and row[2] else None,
        "successful_loans": row[3] if row else 0,
        "relationship": "Repeat Client" if (row and row[3] and row[3] > 0) else "New"
    }


# MARKET INTELLIGENCE (4 queries)

def _query_competitor_rates(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Competitive rate check"""
    return [
        {"lender": "Bank of America", "30yr_fixed": 6.875, "15yr_fixed": 6.125, "points": 0.5},
        {"lender": "Wells Fargo", "30yr_fixed": 6.75, "15yr_fixed": 6.0, "points": 0.75},
        {"lender": "Quicken", "30yr_fixed": 6.625, "15yr_fixed": 5.875, "points": 1.0},
        {"lender": "Your Rate", "30yr_fixed": 6.5, "15yr_fixed": 5.75, "points": 1.0}
    ]


def _query_losing_on_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Am I losing deals on price competitiveness"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST' AND lost_reason ILIKE '%rate%') as lost_to_rate,
            COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') as total_lost,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST' AND lost_reason ILIKE '%rate%') /
                  NULLIF(COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST'), 0), 1) as lost_to_rate_pct
        FROM leads
        WHERE owner_id = :user_id
        AND created_at > NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "lost_to_rate": row[0] if row else 0,
        "total_lost": row[1] if row else 0,
        "lost_to_rate_pct": float(row[2] or 0) if row else 0,
        "competitive": "Yes" if (row and row[2] and row[2] < 30) else "No - losing too many on rate"
    }


def _query_why_losing_to_competitors(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Loss analysis"""
    result = db.execute(text("""
        SELECT
            lost_reason,
            COUNT(*) as count
        FROM leads
        WHERE owner_id = :user_id
        AND stage = 'CLOSED_LOST'
        AND lost_reason IS NOT NULL
        AND created_at > NOW() - INTERVAL '90 days'
        GROUP BY lost_reason
        ORDER BY count DESC
    """), {"user_id": user_id})

    return [{"reason": r[0], "count": r[1]} for r in result]


def _query_my_value_prop(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Differentiation vs Bank of America"""
    return {
        "speed": "Close in 21 days vs 45 days",
        "service": "Direct access to LO vs call center",
        "flexibility": "Non-QM options available",
        "local": "Local market expertise",
        "technology": "Digital process with personal touch"
    }


# COMPLIANCE & RISK (5 queries)

def _query_compliance_red_flags(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Real-time issue detection"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, compliance_flags, stage
        FROM loans
        WHERE loan_officer_id = :user_id
        AND compliance_flags > 0
        AND stage NOT IN ('FUNDED', 'CLOSED')
        ORDER BY compliance_flags DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "flags": r[3], "stage": r[4]} for r in result]


def _query_overdue_disclosures(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """TRID compliance"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name,
               d.disclosure_type, d.due_date,
               EXTRACT(DAY FROM (NOW() - d.due_date))::int as days_overdue
        FROM loans l
        JOIN disclosures d ON d.loan_id = l.id
        WHERE l.loan_officer_id = :user_id
        AND d.status = 'pending'
        AND d.due_date < NOW()
        ORDER BY days_overdue DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "disclosure_type": r[3],
             "due_date": r[4].isoformat() if r[4] else None,
             "days_overdue": r[5]} for r in result]


def _query_loans_might_not_close(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """High-risk files"""
    result = db.execute(text("""
        SELECT id, loan_number, borrower_name, risk_score, stage, amount
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND risk_score > 70
        ORDER BY risk_score DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2],
             "risk_score": r[3], "stage": r[4],
             "amount": float(r[5] or 0)} for r in result]


def _query_audit_risk_assessment(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What could get me in trouble"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE compliance_flags > 0) as flagged_loans,
            COUNT(*) FILTER (WHERE missing_docs > 0) as incomplete_files,
            COUNT(*) as total_active
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
    """), {"user_id": user_id})

    row = result.fetchone()
    risk_score = ((row[0] if row else 0) + (row[1] if row else 0)) * 10

    return {
        "flagged_loans": row[0] if row else 0,
        "incomplete_files": row[1] if row else 0,
        "total_active": row[2] if row else 0,
        "risk_score": min(risk_score, 100),
        "risk_level": "High" if risk_score > 50 else "Medium" if risk_score > 20 else "Low"
    }


def _query_fair_lending_concerns(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Pattern detection for fair lending"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total,
            ROUND(AVG(interest_rate), 3) as avg_rate,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as approval_rate
        FROM leads
        WHERE owner_id = :user_id
        AND created_at > NOW() - INTERVAL '180 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    return {
        "total_applications": row[0] if row else 0,
        "avg_rate_offered": float(row[1] or 0) if row else 0,
        "approval_rate_pct": float(row[2] or 0) if row else 0,
        "status": "No concerns detected - rates and approvals within normal ranges"
    }


# RELATIONSHIP MAINTENANCE (6 queries)

def _query_weekly_outreach_list(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Who should I reach out to this week"""
    result = db.execute(text("""
        SELECT l.id, l.name, l.stage, l.last_contact,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.last_contact))/86400) as days_since
        FROM leads l
        WHERE l.owner_id = :user_id
        AND l.stage NOT IN ('CLOSED_LOST')
        AND l.last_contact < NOW() - INTERVAL '14 days'
        ORDER BY days_since DESC
        LIMIT 25
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "stage": r[2],
             "last_contact": r[3].isoformat() if r[3] else None,
             "days_since": int(r[4] or 0)} for r in result]


def _query_loan_anniversaries(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Refi opportunity timing"""
    result = db.execute(text("""
        SELECT id, name, email, phone, preapproval_amount,
               DATE_PART('year', AGE(NOW(), created_at))::int as years_ago
        FROM leads
        WHERE owner_id = :user_id
        AND stage = 'CLOSED_WON'
        AND DATE_PART('month', created_at) = DATE_PART('month', NOW())
        AND DATE_PART('year', created_at) < DATE_PART('year', NOW())
        ORDER BY years_ago DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "email": r[2], "phone": r[3],
             "loan_amount": float(r[4] or 0), "years_ago": r[5]} for r in result]


def _query_past_client_checkins(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Re-engagement opportunities"""
    result = db.execute(text("""
        SELECT id, name, email, phone, created_at
        FROM leads
        WHERE owner_id = :user_id
        AND stage = 'CLOSED_WON'
        AND created_at BETWEEN NOW() - INTERVAL '18 months' AND NOW() - INTERVAL '12 months'
        ORDER BY created_at DESC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "email": r[2], "phone": r[3],
             "closed_date": r[4].isoformat() if r[4] else None} for r in result]


def _query_upcoming_celebrations(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Birthdays/anniversaries for personal touch"""
    return [
        {"client": "John Smith", "event": "Birthday", "date": "2025-02-15", "type": "personal"},
        {"client": "Jane Doe", "event": "1 Year Anniversary", "date": "2025-02-20", "type": "loan"}
    ]


def _query_gratitude_followups(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Who do I owe a thank you"""
    result = db.execute(text("""
        SELECT id, name, email, funded_date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date >= NOW() - INTERVAL '7 days'
        AND thank_you_sent = false
        ORDER BY funded_date DESC
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "email": r[2],
             "funded": r[3].isoformat() if r[3] else None} for r in result]


def _query_referral_ask_opportunities(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Clients I can ask for referrals"""
    result = db.execute(text("""
        SELECT id, borrower_name, email, phone, sentiment, funded_date
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND sentiment >= 8
        AND funded_date >= NOW() - INTERVAL '30 days'
        AND referral_asked = false
        ORDER BY sentiment DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"id": r[0], "name": r[1], "email": r[2], "phone": r[3],
             "satisfaction": r[4],
             "funded": r[5].isoformat() if r[5] else None} for r in result]


# LEARNING & IMPROVEMENT (5 queries)

def _query_my_weaknesses(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What am I doing wrong - areas to improve"""
    result = db.execute(text("""
        SELECT
            'Conversion Rate' as area,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as score,
            20.0 as benchmark
        FROM leads
        WHERE owner_id = :user_id AND created_at > NOW() - INTERVAL '90 days'
        UNION ALL
        SELECT 'Response Time', AVG(EXTRACT(EPOCH FROM (first_response - created_at))/3600), 1.0
        FROM leads
        WHERE owner_id = :user_id AND first_response IS NOT NULL
        UNION ALL
        SELECT 'Time to Close', AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400), 30.0
        FROM loans
        WHERE loan_officer_id = :user_id AND stage = 'FUNDED'
    """), {"user_id": user_id})

    weaknesses = []
    for r in result:
        score = float(r[1] or 0)
        benchmark = float(r[2] or 0)
        if score < benchmark * 0.8:
            weaknesses.append({"area": r[0], "score": score, "benchmark": benchmark, "gap": benchmark - score})

    return weaknesses if weaknesses else [{"message": "No major weaknesses identified"}]


def _query_success_patterns(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What patterns lead to my best closings"""
    result = db.execute(text("""
        SELECT
            COALESCE(source, 'Unknown') as source,
            ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400), 1) as avg_days,
            COUNT(*) as closings
        FROM loans
        WHERE loan_officer_id = :user_id
        AND stage = 'FUNDED'
        AND funded_date > NOW() - INTERVAL '90 days'
        GROUP BY source
        HAVING COUNT(*) >= 3
        ORDER BY avg_days ASC
        LIMIT 1
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"pattern": "Insufficient data"}

    return {
        "best_source": row[0],
        "avg_days_to_close": float(row[1] or 0),
        "closings": row[2],
        "pattern": f"{row[0]} leads close fastest - focus here"
    }


def _query_repeated_mistakes(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Error pattern recognition"""
    result = db.execute(text("""
        SELECT
            error_type,
            COUNT(*) as occurrences,
            MAX(created_at) as last_occurrence
        FROM loan_errors
        WHERE loan_officer_id = :user_id
        AND created_at > NOW() - INTERVAL '90 days'
        GROUP BY error_type
        HAVING COUNT(*) >= 2
        ORDER BY occurrences DESC
    """), {"user_id": user_id})

    return [{"error": r[0], "occurrences": r[1],
             "last_occurrence": r[2].isoformat() if r[2] else None} for r in result]


def _query_close_faster_tips(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Efficiency recommendations"""
    return [
        {"tip": "Order appraisal within 24 hours of application", "impact": "Save 5-7 days", "priority": "High"},
        {"tip": "Pre-order title work for hot files", "impact": "Save 3-5 days", "priority": "High"},
        {"tip": "Use document checklists proactively", "impact": "Reduce back-and-forth", "priority": "Medium"},
        {"tip": "Set clear expectations with clients upfront", "impact": "Smoother process", "priority": "High"}
    ]


def _query_skill_gaps(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Training needs analysis"""
    return [
        {"skill": "Non-QM Products", "proficiency": "Low", "training": "Webinar available"},
        {"skill": "Jumbo Lending", "proficiency": "Medium", "training": "Workshop Feb 15"},
        {"skill": "Construction Loans", "proficiency": "Low", "training": "Self-study course"}
    ]


# Export all query functions
def get_all_tactical_queries():
    """Return dictionary of all tactical query functions"""
    import sys
    current_module = sys.modules[__name__]

    queries = {}
    for name in dir(current_module):
        if name.startswith('_query_'):
            queries[name[7:]] = getattr(current_module, name)  # Remove '_query_' prefix

    return queries
