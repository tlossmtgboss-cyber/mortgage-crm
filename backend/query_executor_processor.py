"""
Processor Query Implementations - Extension of QueryExecutor
105 day-to-day operational queries for loan processors
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta


# These methods extend QueryExecutor for processor-specific queries
# All queries return real data from your database schema

# ============================================================================
# DAILY OPERATIONS & WORKLOAD MANAGEMENT (8 queries)
# ============================================================================

def _query_processor_workload_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What's my workload today - files assigned with priority order"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.amount,
               l.closing_date, l.processor,
               CASE WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 100
                    WHEN l.risk_score > 70 THEN 90
                    WHEN l.days_in_stage > 14 THEN 80
                    ELSE 60 END as priority_score
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        ORDER BY priority_score DESC, l.closing_date ASC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "amount": float(r[4] or 0), "closing_date": r[5].isoformat() if r[5] else None,
             "processor": r[6], "priority": r[7]} for r in result]


def _query_processor_deadlines_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What are my deadlines for today - all time-sensitive items due today"""
    result = db.execute(text("""
        SELECT 'task' as type, t.id, t.title, t.due_date, t.entity_type, t.entity_id,
               l.borrower_name
        FROM tasks t
        LEFT JOIN loans l ON t.entity_type = 'loan' AND t.entity_id = l.id
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.due_date::date = CURRENT_DATE

        UNION ALL

        SELECT 'closing' as type, l.id, CONCAT('Closing: ', l.borrower_name),
               l.closing_date, 'loan', l.id, l.borrower_name
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.closing_date::date = CURRENT_DATE

        ORDER BY due_date ASC
    """), {"user_id": user_id})

    return [{"type": r[0], "id": r[1], "title": r[2], "due_date": r[3].isoformat() if r[3] else None,
             "entity_type": r[4], "entity_id": r[5], "borrower": r[6]} for r in result]


def _query_processor_priority_queue(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need attention first - priority queue based on urgency"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.closing_date,
               CASE WHEN l.closing_date < NOW() + INTERVAL '2 days' THEN 'Critical - Closing Imminent'
                    WHEN l.stage = 'CTC' THEN 'High - Clear to Close'
                    WHEN l.days_in_stage > 21 THEN 'High - Stalled'
                    WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 'Medium - Closing Soon'
                    ELSE 'Normal' END as urgency,
               l.days_in_stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        ORDER BY
            CASE WHEN l.closing_date < NOW() + INTERVAL '2 days' THEN 1
                 WHEN l.stage = 'CTC' THEN 2
                 WHEN l.days_in_stage > 21 THEN 3
                 WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 4
                 ELSE 5 END,
            l.closing_date ASC NULLS LAST
        LIMIT 25
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "closing_date": r[4].isoformat() if r[4] else None, "urgency": r[5],
             "days_in_stage": r[6]} for r in result]


def _query_processor_current_capacity(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my current capacity - active files vs optimal workload"""
    result = db.execute(text("""
        WITH processor_stats AS (
            SELECT
                COUNT(*) as active_files,
                25 as optimal_capacity,
                COUNT(*) FILTER (WHERE stage IN ('PROCESSING', 'UNDERWRITING')) as files_in_process,
                COUNT(*) FILTER (WHERE closing_date < NOW() + INTERVAL '7 days') as closing_soon
            FROM loans
            WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
            AND stage NOT IN ('Funded')
        )
        SELECT active_files, optimal_capacity, files_in_process, closing_soon,
               ROUND(100.0 * active_files / optimal_capacity, 1) as utilization_pct,
               optimal_capacity - active_files as capacity_remaining,
               CASE WHEN active_files > optimal_capacity THEN 'Over Capacity'
                    WHEN active_files > optimal_capacity * 0.85 THEN 'At Capacity'
                    ELSE 'Available' END as status
        FROM processor_stats
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"status": "Available", "active_files": 0, "optimal_capacity": 25}

    return {
        "active_files": row[0],
        "optimal_capacity": row[1],
        "files_in_process": row[2],
        "closing_soon": row[3],
        "utilization_pct": float(row[4]) if row[4] else 0,
        "capacity_remaining": row[5],
        "status": row[6]
    }


def _query_processor_files_by_loan_officer(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which loan officers have files with me - breakdown by LO"""
    result = db.execute(text("""
        SELECT
            l.loan_officer_id,
            u.first_name || ' ' || u.last_name as loan_officer_name,
            COUNT(*) as file_count,
            COUNT(*) FILTER (WHERE l.stage = 'Processing') as in_processing,
            COUNT(*) FILTER (WHERE l.stage IN ('Underwriting', 'UW Received')) as in_underwriting,
            COUNT(*) FILTER (WHERE l.closing_date < NOW() + INTERVAL '7 days') as closing_soon
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.loan_officer_id, u.first_name, u.last_name
        ORDER BY file_count DESC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "file_count": r[2],
             "in_processing": r[3], "in_underwriting": r[4], "closing_soon": r[5]} for r in result]


def _query_processor_weekly_calendar(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What's on my calendar this week - closings, deadlines"""
    result = db.execute(text("""
        SELECT 'closing' as event_type, l.id, l.borrower_name as title,
               l.closing_date as event_date, l.amount as value
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.closing_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'

        UNION ALL

        SELECT 'task' as event_type, t.id, t.title, t.due_date as event_date, 0 as value
        FROM tasks t
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.due_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'

        ORDER BY event_date ASC
    """), {"user_id": user_id})

    return [{"event_type": r[0], "id": r[1], "title": r[2],
             "event_date": r[3].isoformat() if r[3] else None,
             "value": float(r[4] or 0)} for r in result]


def _query_processor_overdue_tasks(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What tasks are overdue - past-due items by file"""
    result = db.execute(text("""
        SELECT t.id, t.title, t.due_date, t.priority, t.entity_type, t.entity_id,
               EXTRACT(DAY FROM (NOW() - t.due_date))::int as days_overdue,
               l.borrower_name, l.loan_number
        FROM tasks t
        LEFT JOIN loans l ON t.entity_type = 'loan' AND t.entity_id = l.id
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.due_date < NOW()
        ORDER BY days_overdue DESC, t.priority DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"id": r[0], "title": r[1], "due_date": r[2].isoformat() if r[2] else None,
             "priority": r[3], "entity_type": r[4], "entity_id": r[5], "days_overdue": r[6],
             "borrower": r[7], "loan_number": r[8]} for r in result]


def _query_processor_file_list(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me my file list - all active files with key status"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.amount,
               l.loan_type, l.closing_date, l.days_in_stage, l.risk_score,
               u.first_name || ' ' || u.last_name as loan_officer
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST, l.created_at DESC
        LIMIT 100
    """), {"user_id": user_id})

    return [{"id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "amount": float(r[4] or 0), "loan_type": r[5],
             "closing_date": r[6].isoformat() if r[6] else None,
             "days_in_stage": r[7], "risk_score": r[8], "loan_officer": r[9]} for r in result]


# ============================================================================
# DOCUMENT MANAGEMENT (12 queries)
# ============================================================================

def _query_processor_missing_documents(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What documents are missing across all my files"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               COUNT(d.id) FILTER (WHERE d.status = 'missing') as missing_count,
               STRING_AGG(CASE WHEN d.status = 'missing' THEN d.document_type END, ', ') as missing_docs
        FROM loans l
        LEFT JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.stage
        HAVING COUNT(d.id) FILTER (WHERE d.status = 'missing') > 0
        ORDER BY missing_count DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "missing_count": r[4], "missing_docs": r[5]} for r in result]


def _query_processor_unresponsive_borrowers_docs(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which borrowers haven't sent requested documents"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.email, l.phone,
               COUNT(d.id) as pending_docs,
               MIN(d.requested_date) as first_request_date,
               ROUND(EXTRACT(EPOCH FROM (NOW() - MIN(d.requested_date)))/86400) as days_waiting
        FROM loans l
        JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.status = 'requested'
        AND d.requested_date < NOW() - INTERVAL '3 days'
        AND l.stage NOT IN ('Funded')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.email, l.phone
        ORDER BY days_waiting DESC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "email": r[3],
             "phone": r[4], "pending_docs": r[5],
             "first_request": r[6].isoformat() if r[6] else None,
             "days_waiting": int(r[7] or 0)} for r in result]


def _query_processor_documents_uploaded_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What documents were uploaded today - recent document activity"""
    result = db.execute(text("""
        SELECT d.id, d.document_type, d.uploaded_at, d.loan_id,
               l.loan_number, l.borrower_name
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.uploaded_at >= CURRENT_DATE
        ORDER BY d.uploaded_at DESC
        LIMIT 100
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "document_type": r[1],
             "uploaded_at": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5]} for r in result]


def _query_processor_complete_documentation(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files have complete documentation - ready for next step"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               COUNT(d.id) as total_docs,
               COUNT(d.id) FILTER (WHERE d.status = 'received') as received_docs,
               ROUND(100.0 * COUNT(d.id) FILTER (WHERE d.status = 'received') /
                     NULLIF(COUNT(d.id), 0), 1) as completion_pct
        FROM loans l
        LEFT JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.stage
        HAVING COUNT(d.id) > 0
        AND COUNT(d.id) FILTER (WHERE d.status != 'received') = 0
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "total_docs": r[4], "received_docs": r[5], "completion_pct": float(r[6] or 0)} for r in result]


def _query_processor_overdue_doc_requests(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What document requests are overdue - borrower responsiveness issues"""
    result = db.execute(text("""
        SELECT d.id, d.document_type, d.requested_date, d.loan_id,
               l.loan_number, l.borrower_name, l.email, l.phone,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.requested_date))/86400) as days_overdue
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.status = 'requested'
        AND d.requested_date < NOW() - INTERVAL '5 days'
        ORDER BY days_overdue DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "document_type": r[1],
             "requested_date": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5],
             "email": r[6], "phone": r[7], "days_overdue": int(r[8] or 0)} for r in result]


def _query_processor_loan_stips(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me all stips for a loan - specific file's outstanding items"""
    loan_id = params.get("loan_id")
    if not loan_id:
        return [{"error": "loan_id required"}]

    result = db.execute(text("""
        SELECT d.id, d.document_type, d.status, d.requested_date, d.received_date,
               d.notes
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.id = :loan_id
        AND l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        ORDER BY
            CASE d.status
                WHEN 'missing' THEN 1
                WHEN 'requested' THEN 2
                WHEN 'pending_review' THEN 3
                ELSE 4
            END,
            d.requested_date ASC
    """), {"loan_id": loan_id, "user_id": user_id})

    return [{"doc_id": r[0], "document_type": r[1], "status": r[2],
             "requested_date": r[3].isoformat() if r[3] else None,
             "received_date": r[4].isoformat() if r[4] else None,
             "notes": r[5]} for r in result]


def _query_processor_initial_disclosures_needed(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need initial disclosures sent - TRID compliance"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.application_date,
               EXTRACT(DAY FROM (NOW() - l.application_date))::int as days_since_app
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('APPLICATION', 'PROCESSING')
        AND l.initial_disclosure_sent = false
        AND l.application_date IS NOT NULL
        ORDER BY l.application_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "application_date": r[4].isoformat() if r[4] else None,
             "days_since_app": r[5]} for r in result]


def _query_processor_pending_verifications(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What VOEs/VODs are pending - employment/deposit verifications"""
    result = db.execute(text("""
        SELECT d.id, d.document_type, d.requested_date, l.id as loan_id,
               l.loan_number, l.borrower_name,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.requested_date))/86400) as days_pending
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.document_type IN ('VOE', 'VOD', 'Verification of Employment', 'Verification of Deposit')
        AND d.status = 'requested'
        ORDER BY days_pending DESC
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "document_type": r[1],
             "requested_date": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5],
             "days_pending": int(r[6] or 0)} for r in result]


def _query_processor_credit_supplement_needed(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need credit supplement ordered - credit refresh needed"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.credit_report_date,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.credit_report_date))/86400) as credit_age_days
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.credit_report_date < NOW() - INTERVAL '90 days'
        ORDER BY credit_age_days DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "credit_report_date": r[3].isoformat() if r[3] else None,
             "credit_age_days": int(r[4] or 0)} for r in result]


def _query_processor_tax_return_requests(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What tax return requests are out - tax doc follow-ups"""
    result = db.execute(text("""
        SELECT d.id, d.requested_date, l.id as loan_id, l.loan_number, l.borrower_name,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.requested_date))/86400) as days_waiting
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.document_type ILIKE '%tax%'
        AND d.status = 'requested'
        ORDER BY days_waiting DESC
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "requested_date": r[1].isoformat() if r[1] else None,
             "loan_id": r[2], "loan_number": r[3], "borrower": r[4],
             "days_waiting": int(r[5] or 0)} for r in result]


def _query_processor_incomplete_income_docs(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files with incomplete income docs - income verification gaps"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.income,
               COUNT(d.id) FILTER (WHERE d.document_type ILIKE '%paystub%' AND d.status = 'received') as paystubs,
               COUNT(d.id) FILTER (WHERE d.document_type ILIKE '%w2%' AND d.status = 'received') as w2s,
               COUNT(d.id) FILTER (WHERE d.document_type ILIKE '%1099%' AND d.status = 'received') as form1099s
        FROM loans l
        LEFT JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.income
        HAVING COUNT(d.id) FILTER (WHERE d.document_type ILIKE '%paystub%' AND d.status = 'received') < 2
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "income": float(r[3] or 0),
             "paystubs_received": r[4], "w2s_received": r[5], "1099s_received": r[6]} for r in result]


def _query_processor_expired_documents(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files have expired documents - docs needing refresh"""
    result = db.execute(text("""
        SELECT d.id, d.document_type, d.received_date, l.id as loan_id,
               l.loan_number, l.borrower_name,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.received_date))/86400) as age_days
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.status = 'received'
        AND d.received_date < NOW() - INTERVAL '60 days'
        AND l.stage NOT IN ('Funded')
        ORDER BY age_days DESC
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "document_type": r[1],
             "received_date": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5],
             "age_days": int(r[6] or 0)} for r in result]


# ============================================================================
# THIRD-PARTY SERVICES & VENDORS (10 queries)
# ============================================================================

def _query_processor_appraisals_to_order(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What appraisals need to be ordered"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.property_address,
               l.property_city, l.property_state, l.property_zip, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('APPLICATION', 'PROCESSING')
        AND l.appraisal_ordered_date IS NULL
        AND l.property_address IS NOT NULL
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "property_address": r[3], "city": r[4], "state": r[5], "zip": r[6],
             "stage": r[7]} for r in result]


def _query_processor_appraisals_in_progress(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which appraisals are in progress - appraisal status tracking"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.property_address,
               l.appraisal_ordered_date, l.appraisal_due_date,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.appraisal_ordered_date))/86400) as days_since_ordered,
               CASE WHEN l.appraisal_due_date < NOW() THEN 'Overdue'
                    WHEN l.appraisal_due_date < NOW() + INTERVAL '3 days' THEN 'Due Soon'
                    ELSE 'On Track' END as status
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.appraisal_ordered_date IS NOT NULL
        AND l.appraisal_received_date IS NULL
        ORDER BY l.appraisal_due_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "property_address": r[3],
             "ordered_date": r[4].isoformat() if r[4] else None,
             "due_date": r[5].isoformat() if r[5] else None,
             "days_since_ordered": int(r[6] or 0), "status": r[7]} for r in result]


def _query_processor_overdue_appraisals(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What appraisals are overdue - late appraisals"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.appraisal_ordered_date,
               l.appraisal_due_date, l.appraiser,
               EXTRACT(DAY FROM (NOW() - l.appraisal_due_date))::int as days_overdue
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.appraisal_ordered_date IS NOT NULL
        AND l.appraisal_received_date IS NULL
        AND l.appraisal_due_date < NOW()
        ORDER BY days_overdue DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "ordered_date": r[3].isoformat() if r[3] else None,
             "due_date": r[4].isoformat() if r[4] else None,
             "appraiser": r[5], "days_overdue": r[6]} for r in result]


def _query_processor_appraisal_issues(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me appraisal issues - low values, condition issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.property_value,
               l.property_value - l.amount as value_gap,
               l.appraisal_conditions
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.appraisal_received_date IS NOT NULL
        AND (l.property_value < l.amount OR l.appraisal_conditions IS NOT NULL)
        AND l.stage NOT IN ('Funded')
        ORDER BY value_gap ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "loan_amount": float(r[3] or 0), "appraised_value": float(r[4] or 0),
             "value_gap": float(r[5] or 0), "conditions": r[6]} for r in result]


def _query_processor_title_work_pending(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What title work is pending - title order status"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.title_company,
               l.title_ordered_date, l.property_address,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.title_ordered_date))/86400) as days_pending
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.title_ordered_date IS NOT NULL
        AND l.title_received_date IS NULL
        ORDER BY days_pending DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "title_company": r[3],
             "ordered_date": r[4].isoformat() if r[4] else None,
             "property_address": r[5], "days_pending": int(r[6] or 0)} for r in result]


def _query_processor_title_commitments_review(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which title commitments need review - title issues to resolve"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.title_received_date,
               l.title_exceptions, l.title_company
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.title_received_date IS NOT NULL
        AND l.title_cleared_date IS NULL
        AND l.stage NOT IN ('Funded')
        ORDER BY l.title_received_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "received_date": r[3].isoformat() if r[3] else None,
             "exceptions": r[4], "title_company": r[5]} for r in result]


def _query_processor_hoa_docs_pending(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What HOA/condo questionnaires are out - HOA doc status"""
    result = db.execute(text("""
        SELECT d.id, l.id as loan_id, l.loan_number, l.borrower_name,
               d.requested_date, l.property_address,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.requested_date))/86400) as days_waiting
        FROM documents d
        JOIN loans l ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND d.document_type IN ('HOA Questionnaire', 'Condo Questionnaire', 'HOA Documents')
        AND d.status = 'requested'
        ORDER BY days_waiting DESC
    """), {"user_id": user_id})

    return [{"doc_id": r[0], "loan_id": r[1], "loan_number": r[2], "borrower": r[3],
             "requested_date": r[4].isoformat() if r[4] else None,
             "property_address": r[5], "days_waiting": int(r[6] or 0)} for r in result]


def _query_processor_vendor_turnaround_times(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me vendor turnaround times - which vendors are fast/slow"""
    result = db.execute(text("""
        SELECT
            title_company as vendor_name,
            'Title Company' as vendor_type,
            COUNT(*) as orders,
            ROUND(AVG(EXTRACT(EPOCH FROM (title_received_date - title_ordered_date))/86400), 1) as avg_days
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND title_ordered_date IS NOT NULL
        AND title_received_date IS NOT NULL
        AND title_ordered_date > NOW() - INTERVAL '90 days'
        GROUP BY title_company
        HAVING COUNT(*) >= 3

        UNION ALL

        SELECT
            appraiser as vendor_name,
            'Appraiser' as vendor_type,
            COUNT(*) as orders,
            ROUND(AVG(EXTRACT(EPOCH FROM (appraisal_received_date - appraisal_ordered_date))/86400), 1) as avg_days
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND appraisal_ordered_date IS NOT NULL
        AND appraisal_received_date IS NOT NULL
        AND appraisal_ordered_date > NOW() - INTERVAL '90 days'
        GROUP BY appraiser
        HAVING COUNT(*) >= 3

        ORDER BY avg_days ASC
    """), {"user_id": user_id})

    return [{"vendor_name": r[0], "vendor_type": r[1], "orders": r[2],
             "avg_turnaround_days": float(r[3] or 0)} for r in result]


def _query_processor_inspections_scheduled(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What inspections are scheduled - home inspection coordination"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.inspection_date,
               l.property_address, l.inspector
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.inspection_date IS NOT NULL
        AND l.inspection_completed = false
        ORDER BY l.inspection_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "inspection_date": r[3].isoformat() if r[3] else None,
             "property_address": r[4], "inspector": r[5]} for r in result]


def _query_processor_insurance_needed(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need insurance ordered - homeowners insurance"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.property_address,
               l.closing_date
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.insurance_binder_received = false
        AND l.stage IN ('UNDERWRITING', 'APPROVED', 'CLEAR_TO_CLOSE')
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "property_address": r[3],
             "closing_date": r[4].isoformat() if r[4] else None} for r in result]


# ============================================================================
# UNDERWRITING COORDINATION (10 queries)
# ============================================================================

def _query_processor_ready_for_underwriting(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files are ready to submit to underwriting - complete files"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_type, l.amount,
               COUNT(d.id) FILTER (WHERE d.status = 'received') as docs_received,
               COUNT(d.id) as total_docs
        FROM loans l
        LEFT JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage = 'Processing'
        AND l.appraisal_received_date IS NOT NULL
        GROUP BY l.id, l.loan_number, l.borrower_name, l.loan_type, l.amount
        HAVING COUNT(d.id) > 0 AND COUNT(d.id) FILTER (WHERE d.status != 'received') = 0
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "loan_type": r[3],
             "amount": float(r[4] or 0), "docs_received": r[5], "total_docs": r[6]} for r in result]


def _query_processor_files_with_underwriter(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files are with the underwriter - currently in underwriting"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.underwriter,
               l.submitted_to_uw_date, l.amount,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.submitted_to_uw_date))/86400) as days_in_uw
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('Underwriting', 'UW Received')
        ORDER BY days_in_uw DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "underwriter": r[3],
             "submitted_date": r[4].isoformat() if r[4] else None, "amount": float(r[5] or 0),
             "days_in_uw": int(r[6] or 0)} for r in result]


def _query_processor_conditions_received_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What conditions came back today - new underwriting conditions"""
    result = db.execute(text("""
        SELECT c.id, c.condition_text, c.created_at, l.id as loan_id,
               l.loan_number, l.borrower_name
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.created_at >= CURRENT_DATE
        ORDER BY c.created_at DESC
    """), {"user_id": user_id})

    return [{"condition_id": r[0], "condition_text": r[1],
             "created_at": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5]} for r in result]


def _query_processor_all_outstanding_conditions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me all outstanding conditions - all open stips across files"""
    result = db.execute(text("""
        SELECT c.id, c.condition_text, c.created_at, c.status, l.id as loan_id,
               l.loan_number, l.borrower_name,
               ROUND(EXTRACT(EPOCH FROM (NOW() - c.created_at))/86400) as age_days
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.status = 'open'
        ORDER BY age_days DESC, l.closing_date ASC NULLS LAST
        LIMIT 100
    """), {"user_id": user_id})

    return [{"condition_id": r[0], "condition_text": r[1],
             "created_at": r[2].isoformat() if r[2] else None, "status": r[3],
             "loan_id": r[4], "loan_number": r[5], "borrower": r[6],
             "age_days": int(r[7] or 0)} for r in result]


def _query_processor_cleared_conditions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which conditions are cleared - recently satisfied conditions"""
    result = db.execute(text("""
        SELECT c.id, c.condition_text, c.cleared_date, l.id as loan_id,
               l.loan_number, l.borrower_name
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.cleared_date >= NOW() - INTERVAL '7 days'
        ORDER BY c.cleared_date DESC
    """), {"user_id": user_id})

    return [{"condition_id": r[0], "condition_text": r[1],
             "cleared_date": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5]} for r in result]


def _query_processor_suspended_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files are in suspense - suspended files needing action"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.suspense_reason,
               l.suspended_date,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.suspended_date))/86400) as days_suspended
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage = 'Suspended'
        ORDER BY days_suspended DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "suspense_reason": r[3],
             "suspended_date": r[4].isoformat() if r[4] else None,
             "days_suspended": int(r[5] or 0)} for r in result]


def _query_processor_initial_approvals(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files got initial approval - conditionally approved today"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.approval_date,
               COUNT(c.id) FILTER (WHERE c.status = 'open') as open_conditions
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.approval_date >= CURRENT_DATE
        GROUP BY l.id, l.loan_number, l.borrower_name, l.approval_date
        ORDER BY l.approval_date DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "approval_date": r[3].isoformat() if r[3] else None,
             "open_conditions": r[4]} for r in result]


def _query_processor_clear_to_close_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files are clear to close - final approval status"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.closing_date, l.amount,
               l.clear_to_close_date
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage = 'CTC'
        ORDER BY l.closing_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None,
             "amount": float(r[4] or 0),
             "ctc_date": r[5].isoformat() if r[5] else None} for r in result]


def _query_processor_high_risk_underwriting(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me high-risk underwriting files - files with many conditions/issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.risk_score,
               COUNT(c.id) FILTER (WHERE c.status = 'open') as open_conditions,
               l.stage
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('UNDERWRITING', 'SUSPENDED')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.risk_score, l.stage
        HAVING COUNT(c.id) FILTER (WHERE c.status = 'open') > 5 OR l.risk_score > 70
        ORDER BY open_conditions DESC, l.risk_score DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "risk_score": r[3], "open_conditions": r[4], "stage": r[5]} for r in result]


def _query_processor_next_uw_call(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """When is my next underwriter call - scheduled UW discussions"""
    result = db.execute(text("""
        SELECT t.id, t.title, t.due_date, t.entity_id as loan_id,
               l.loan_number, l.borrower_name
        FROM tasks t
        LEFT JOIN loans l ON t.entity_type = 'loan' AND t.entity_id = l.id
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.title ILIKE '%underwriter%'
        AND t.due_date >= NOW()
        ORDER BY t.due_date ASC
        LIMIT 10
    """), {"user_id": user_id})

    return [{"task_id": r[0], "title": r[1],
             "due_date": r[2].isoformat() if r[2] else None,
             "loan_id": r[3], "loan_number": r[4], "borrower": r[5]} for r in result]


# ============================================================================
# TIMELINE & RATE LOCK MANAGEMENT (8 queries)
# ============================================================================

def _query_processor_closing_schedule(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What's my closing schedule - closings by date"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.closing_date, l.amount,
               l.stage, l.loan_type
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.closing_date BETWEEN NOW() AND NOW() + INTERVAL '30 days'
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None,
             "amount": float(r[4] or 0), "stage": r[5], "loan_type": r[6]} for r in result]


def _query_processor_at_risk_closings(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files might miss their closing date - at-risk closings"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.closing_date, l.stage,
               COUNT(c.id) FILTER (WHERE c.status = 'open') as open_conditions,
               CASE WHEN l.appraisal_received_date IS NULL THEN true ELSE false END as missing_appraisal,
               CASE WHEN l.title_received_date IS NULL THEN true ELSE false END as missing_title
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.closing_date < NOW() + INTERVAL '10 days'
        AND l.stage NOT IN ('CLEAR_TO_CLOSE', 'FUNDED', 'CLOSED', 'CANCELLED')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.closing_date, l.stage,
                 l.appraisal_received_date, l.title_received_date
        HAVING COUNT(c.id) FILTER (WHERE c.status = 'open') > 0
            OR l.appraisal_received_date IS NULL
            OR l.title_received_date IS NULL
        ORDER BY l.closing_date ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None, "stage": r[4],
             "open_conditions": r[5], "missing_appraisal": r[6], "missing_title": r[7]} for r in result]


def _query_processor_expiring_rate_locks(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What rate locks expire this week - rate lock expirations"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.lock_date, l.lock_expiration,
               l.rate, l.stage,
               EXTRACT(DAY FROM (l.lock_expiration - NOW()))::int as days_until_expiration
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.lock_expiration < NOW() + INTERVAL '7 days'
        AND l.stage NOT IN ('Funded')
        ORDER BY l.lock_expiration ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "lock_date": r[3].isoformat() if r[3] else None,
             "lock_expiration": r[4].isoformat() if r[4] else None,
             "rate": float(r[5] or 0), "stage": r[6], "days_until_expiration": r[7]} for r in result]


def _query_processor_tight_timeline_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files with tight timelines - time-sensitive files"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.closing_date, l.stage,
               EXTRACT(DAY FROM (l.closing_date - NOW()))::int as days_to_closing
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.closing_date BETWEEN NOW() AND NOW() + INTERVAL '14 days'
        AND l.stage NOT IN ('CLEAR_TO_CLOSE', 'FUNDED', 'CLOSED', 'CANCELLED')
        ORDER BY days_to_closing ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "closing_date": r[3].isoformat() if r[3] else None,
             "stage": r[4], "days_to_closing": r[5]} for r in result]


def _query_processor_disclosures_due(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What disclosures are due - TRID timing compliance"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name,
               l.initial_disclosure_sent, l.closing_disclosure_sent,
               l.closing_date,
               CASE WHEN NOT l.initial_disclosure_sent THEN 'Initial Disclosure'
                    WHEN NOT l.closing_disclosure_sent AND l.closing_date < NOW() + INTERVAL '4 days'
                    THEN 'Closing Disclosure' END as disclosure_type
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND (NOT l.initial_disclosure_sent
             OR (NOT l.closing_disclosure_sent AND l.closing_date < NOW() + INTERVAL '4 days'))
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "initial_sent": r[3], "closing_sent": r[4],
             "closing_date": r[5].isoformat() if r[5] else None,
             "disclosure_type": r[6]} for r in result]


def _query_processor_delayed_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files are delayed - behind schedule analysis"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.days_in_stage,
               l.closing_date,
               CASE WHEN l.days_in_stage > 21 THEN 'Severely Delayed'
                    WHEN l.days_in_stage > 14 THEN 'Delayed'
                    ELSE 'Slightly Delayed' END as delay_level
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.days_in_stage > 10
        ORDER BY l.days_in_stage DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "days_in_stage": r[4],
             "closing_date": r[5].isoformat() if r[5] else None,
             "delay_level": r[6]} for r in result]


def _query_processor_closing_success_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my closing success rate - % of files closing on time"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE stage = 'FUNDED') as total_closed,
            COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date <= closing_date) as on_time,
            COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date > closing_date) as delayed,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date <= closing_date) /
                  NULLIF(COUNT(*) FILTER (WHERE stage = 'FUNDED'), 0), 1) as on_time_pct
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND funded_date >= NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"on_time_pct": 0, "total_closed": 0}

    return {
        "total_closed": row[0],
        "closed_on_time": row[1],
        "closed_delayed": row[2],
        "on_time_pct": float(row[3]) if row[3] else 0
    }


def _query_processor_avg_days_to_close(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Show me average days to close - processing efficiency metric"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as closed_loans,
            ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - application_date))/86400), 1) as avg_days,
            MIN(EXTRACT(EPOCH FROM (funded_date - application_date))/86400)::int as fastest,
            MAX(EXTRACT(EPOCH FROM (funded_date - application_date))/86400)::int as slowest
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND stage = 'FUNDED'
        AND funded_date >= NOW() - INTERVAL '90 days'
        AND application_date IS NOT NULL
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"avg_days": 0, "closed_loans": 0}

    return {
        "closed_loans": row[0],
        "avg_days_to_close": float(row[1]) if row[1] else 0,
        "fastest_close": row[2],
        "slowest_close": row[3]
    }


# ============================================================================
# QUALITY CONTROL & COMPLIANCE (9 queries)
# ============================================================================

def _query_processor_files_needing_qc(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files need QC review - pre-submission quality check"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.qc_completed,
               l.closing_date
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('PROCESSING', 'UNDERWRITING')
        AND (l.qc_completed = false OR l.qc_completed IS NULL)
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "qc_completed": r[4],
             "closing_date": r[5].isoformat() if r[5] else None} for r in result]


def _query_processor_compliance_red_flags(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me compliance red flags - potential compliance issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.compliance_flags,
               l.stage, l.compliance_notes
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.compliance_flags > 0
        AND l.stage NOT IN ('Funded')
        ORDER BY l.compliance_flags DESC, l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "compliance_flags": r[3], "stage": r[4], "notes": r[5]} for r in result]


def _query_processor_trid_violations(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files have TRID violations - disclosure timing issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.application_date,
               l.initial_disclosure_sent, l.closing_date, l.closing_disclosure_sent,
               CASE WHEN NOT l.initial_disclosure_sent
                    AND l.application_date < NOW() - INTERVAL '3 days'
                    THEN 'Initial Disclosure Overdue'
                    WHEN NOT l.closing_disclosure_sent
                    AND l.closing_date < NOW() + INTERVAL '3 days'
                    THEN 'Closing Disclosure Too Late'
               END as violation_type
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND ((NOT l.initial_disclosure_sent AND l.application_date < NOW() - INTERVAL '3 days')
             OR (NOT l.closing_disclosure_sent AND l.closing_date < NOW() + INTERVAL '3 days'))
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "application_date": r[3].isoformat() if r[3] else None,
             "initial_sent": r[4],
             "closing_date": r[5].isoformat() if r[5] else None,
             "closing_sent": r[6], "violation_type": r[7]} for r in result]


def _query_processor_missing_disclosures(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files are missing required disclosures - compliance gaps"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name,
               l.initial_disclosure_sent, l.closing_disclosure_sent,
               l.le_sent, l.ecoa_sent,
               l.stage, l.closing_date
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND (NOT l.initial_disclosure_sent OR NOT l.le_sent OR NOT l.ecoa_sent)
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "initial_sent": r[3], "closing_sent": r[4], "le_sent": r[5],
             "ecoa_sent": r[6], "stage": r[7],
             "closing_date": r[8].isoformat() if r[8] else None} for r in result]


def _query_processor_data_errors(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files with data errors - 1003 accuracy issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.data_quality_score,
               l.stage, l.validation_errors
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.data_quality_score < 80
        AND l.stage NOT IN ('Funded')
        ORDER BY l.data_quality_score ASC, l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "data_quality_score": r[3], "stage": r[4], "errors": r[5]} for r in result]


def _query_processor_aus_rerun_needed(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need AUS re-run - DU/LP needs update"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.aus_run_date, l.aus_result,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.aus_run_date))/86400) as days_since_aus
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.aus_run_date < NOW() - INTERVAL '30 days'
        ORDER BY days_since_aus DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "aus_run_date": r[3].isoformat() if r[3] else None,
             "aus_result": r[4], "days_since_aus": int(r[5] or 0)} for r in result]


def _query_processor_appraisal_issues_qc(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files have appraisal issues - value/condition problems"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.amount,
               l.property_value, l.appraisal_conditions, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.appraisal_received_date IS NOT NULL
        AND (l.property_value < l.amount * 1.0 OR l.appraisal_conditions IS NOT NULL)
        AND l.stage NOT IN ('Funded')
        ORDER BY (l.property_value / NULLIF(l.amount, 0)) ASC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "loan_amount": float(r[3] or 0), "appraised_value": float(r[4] or 0),
             "conditions": r[5], "stage": r[6]} for r in result]


def _query_processor_credit_issues_qc(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files with credit issues - credit-related problems"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.credit_score,
               l.stage, l.credit_issues
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND (l.credit_score < 640 OR l.credit_issues IS NOT NULL)
        AND l.stage NOT IN ('Funded')
        ORDER BY l.credit_score ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "credit_score": r[3], "stage": r[4], "credit_issues": r[5]} for r in result]


def _query_processor_audit_ready(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files are audit-ready - file quality assessment"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.data_quality_score,
               l.qc_completed, l.compliance_flags, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.qc_completed = true
        AND l.compliance_flags = 0
        AND l.data_quality_score >= 90
        AND l.stage IN ('UNDERWRITING', 'APPROVED', 'CLEAR_TO_CLOSE')
        ORDER BY l.data_quality_score DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "quality_score": r[3], "qc_completed": r[4],
             "compliance_flags": r[5], "stage": r[6]} for r in result]


# ============================================================================
# BORROWER COMMUNICATION (7 queries)
# ============================================================================

def _query_processor_unresponsive_borrowers(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which borrowers are unresponsive - communication problems"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.email, l.phone,
               l.last_contact,
               ROUND(EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.updated_at)))/86400) as days_silent
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND COALESCE(l.last_contact, l.updated_at) < NOW() - INTERVAL '5 days'
        ORDER BY days_silent DESC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "email": r[3], "phone": r[4],
             "last_contact": r[5].isoformat() if r[5] else None,
             "days_silent": int(r[6] or 0)} for r in result]


def _query_processor_borrowers_to_call_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Who do I need to call today - borrower follow-up list"""
    result = db.execute(text("""
        SELECT t.id, l.id as loan_id, l.loan_number, l.borrower_name,
               l.phone, t.title, t.due_date
        FROM tasks t
        JOIN loans l ON t.entity_type = 'loan' AND t.entity_id = l.id
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'
        AND t.title ILIKE '%call%'
        AND t.due_date::date <= CURRENT_DATE
        ORDER BY t.due_date ASC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"task_id": r[0], "loan_id": r[1], "loan_number": r[2],
             "borrower": r[3], "phone": r[4], "task_title": r[5],
             "due_date": r[6].isoformat() if r[6] else None} for r in result]


def _query_processor_frustrated_borrowers(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What borrowers are frustrated - sentiment analysis"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.sentiment, l.stage,
               l.days_in_stage, l.email, l.phone
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.sentiment < 3
        AND l.stage NOT IN ('Funded')
        ORDER BY l.sentiment ASC, l.days_in_stage DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "sentiment": r[3], "stage": r[4], "days_in_stage": r[5],
             "email": r[6], "phone": r[7]} for r in result]


def _query_processor_borrower_response_times(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me borrower response times - how fast borrowers reply"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name,
               ROUND(AVG(EXTRACT(EPOCH FROM (c.created_at - LAG(c.created_at)
                   OVER (PARTITION BY l.id ORDER BY c.created_at)))/3600), 1) as avg_response_hours
        FROM loans l
        JOIN communications c ON c.lead_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.direction = 'inbound'
        AND c.created_at > NOW() - INTERVAL '30 days'
        GROUP BY l.id, l.loan_number, l.borrower_name
        HAVING COUNT(c.id) >= 3
        ORDER BY avg_response_hours DESC NULLS LAST
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "avg_response_hours": float(r[3] or 0)} for r in result]


def _query_processor_borrowers_need_updates(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which borrowers need status updates - communication cadence"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.last_status_update,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.last_status_update))/86400) as days_since_update
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.last_status_update < NOW() - INTERVAL '7 days'
        ORDER BY days_since_update DESC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3],
             "last_update": r[4].isoformat() if r[4] else None,
             "days_since_update": int(r[5] or 0)} for r in result]


def _query_processor_borrower_meetings_needed(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files need borrower meetings - in-person discussions needed"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.risk_score,
               COUNT(c.id) FILTER (WHERE c.status = 'open') as open_conditions
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('PROCESSING', 'UNDERWRITING')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.risk_score
        HAVING COUNT(c.id) FILTER (WHERE c.status = 'open') > 8 OR l.risk_score > 75
        ORDER BY open_conditions DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "risk_score": r[4], "open_conditions": r[5]} for r in result]


def _query_processor_borrower_satisfaction(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me borrower satisfaction scores - happy vs unhappy borrowers"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.sentiment, l.stage,
               CASE WHEN l.sentiment >= 4 THEN 'Satisfied'
                    WHEN l.sentiment = 3 THEN 'Neutral'
                    ELSE 'Dissatisfied' END as satisfaction_level
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.sentiment IS NOT NULL
        ORDER BY l.sentiment ASC, l.closing_date ASC NULLS LAST
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "sentiment": r[3], "stage": r[4], "satisfaction": r[5]} for r in result]


# ============================================================================
# LOAN OFFICER COORDINATION (7 queries)
# ============================================================================

def _query_processor_lo_action_items(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What do I need from each loan officer - LO action items"""
    result = db.execute(text("""
        SELECT l.loan_officer_id, u.first_name || ' ' || u.last_name as lo_name,
               COUNT(*) as total_files,
               COUNT(*) FILTER (WHERE l.ball_in_court = 'loan_officer') as waiting_on_lo
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.loan_officer_id, u.first_name, u.last_name
        HAVING COUNT(*) FILTER (WHERE l.ball_in_court = 'loan_officer') > 0
        ORDER BY waiting_on_lo DESC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "total_files": r[2],
             "waiting_on_lo": r[3]} for r in result]


def _query_processor_los_blocking_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which LOs have files waiting on them - ball in LO's court"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               u.first_name || ' ' || u.last_name as lo_name,
               l.next_action_description
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.ball_in_court = 'loan_officer'
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "lo_id": r[3], "lo_name": r[4], "next_action": r[5]} for r in result]


def _query_processor_lo_response_times(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me LO response times - how fast LOs respond to processor requests"""
    result = db.execute(text("""
        SELECT u.id as lo_id, u.first_name || ' ' || u.last_name as lo_name,
               COUNT(t.id) as requests,
               ROUND(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))/3600), 1) as avg_response_hours
        FROM tasks t
        JOIN loans l ON t.entity_type = 'loan' AND t.entity_id = l.id
        JOIN users u ON l.loan_officer_id = u.id
        WHERE t.assigned_to != :user_id
        AND l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND t.completed_at IS NOT NULL
        AND t.created_at > NOW() - INTERVAL '30 days'
        GROUP BY u.id, u.first_name, u.last_name
        HAVING COUNT(t.id) >= 5
        ORDER BY avg_response_hours ASC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "requests": r[2],
             "avg_response_hours": float(r[3] or 0)} for r in result]


def _query_processor_my_loan_officers(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which LOs am I processing for - active LO relationships"""
    result = db.execute(text("""
        SELECT l.loan_officer_id, u.first_name || ' ' || u.last_name as lo_name,
               COUNT(*) as active_files,
               COUNT(*) FILTER (WHERE l.stage = 'Processing') as in_processing,
               COUNT(*) FILTER (WHERE l.stage IN ('Underwriting', 'UW Received')) as in_underwriting,
               COUNT(*) FILTER (WHERE l.closing_date < NOW() + INTERVAL '14 days') as closing_soon
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.loan_officer_id, u.first_name, u.last_name
        ORDER BY active_files DESC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "active_files": r[2],
             "in_processing": r[3], "in_underwriting": r[4], "closing_soon": r[5]} for r in result]


def _query_processor_files_need_lo_approval(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files need LO approval - requires LO sign-off"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               u.first_name || ' ' || u.last_name as lo_name,
               l.pending_approval_type
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.pending_lo_approval = true
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "lo_id": r[3], "lo_name": r[4], "approval_type": r[5]} for r in result]


def _query_processor_problem_files_by_lo(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me problem files by LO - issue tracking by originator"""
    result = db.execute(text("""
        SELECT u.id as lo_id, u.first_name || ' ' || u.last_name as lo_name,
               COUNT(l.id) as total_files,
               COUNT(l.id) FILTER (WHERE l.risk_score > 70) as high_risk,
               COUNT(l.id) FILTER (WHERE l.days_in_stage > 21) as stalled
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY u.id, u.first_name, u.last_name
        HAVING COUNT(l.id) FILTER (WHERE l.risk_score > 70) > 0
            OR COUNT(l.id) FILTER (WHERE l.days_in_stage > 21) > 0
        ORDER BY high_risk DESC, stalled DESC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "total_files": r[2],
             "high_risk_files": r[3], "stalled_files": r[4]} for r in result]


def _query_processor_los_with_most_conditions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which LOs have the most conditions - LO quality patterns"""
    result = db.execute(text("""
        SELECT u.id as lo_id, u.first_name || ' ' || u.last_name as lo_name,
               COUNT(DISTINCT l.id) as files,
               COUNT(c.id) as total_conditions,
               ROUND(COUNT(c.id)::numeric / NULLIF(COUNT(DISTINCT l.id), 0), 1) as conditions_per_file
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.submitted_to_uw_date >= NOW() - INTERVAL '90 days'
        GROUP BY u.id, u.first_name, u.last_name
        HAVING COUNT(DISTINCT l.id) >= 3
        ORDER BY conditions_per_file DESC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "files": r[2],
             "total_conditions": r[3], "conditions_per_file": float(r[4] or 0)} for r in result]


# ============================================================================
# FILE STATUS & PROGRESS TRACKING (8 queries)
# ============================================================================

def _query_processor_files_by_stage(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files by stage - pipeline snapshot"""
    result = db.execute(text("""
        SELECT l.stage, COUNT(*) as file_count,
               COALESCE(SUM(l.amount), 0) as total_volume,
               ROUND(AVG(l.days_in_stage), 1) as avg_days_in_stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.stage
        ORDER BY file_count DESC
    """), {"user_id": user_id})

    return [{"stage": r[0], "file_count": r[1], "total_volume": float(r[2]),
             "avg_days_in_stage": float(r[3] or 0)} for r in result]


def _query_processor_files_moved_today(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files moved stages today - progress tracking"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               l.stage_updated_at, l.previous_stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage_updated_at >= CURRENT_DATE
        ORDER BY l.stage_updated_at DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "current_stage": r[3],
             "stage_updated_at": r[4].isoformat() if r[4] else None,
             "previous_stage": r[5]} for r in result]


def _query_processor_stalled_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files are stalled - no recent activity"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.days_in_stage,
               l.updated_at,
               ROUND(EXTRACT(EPOCH FROM (NOW() - l.updated_at))/86400) as days_no_activity
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND l.updated_at < NOW() - INTERVAL '7 days'
        ORDER BY days_no_activity DESC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "days_in_stage": r[4],
             "updated_at": r[5].isoformat() if r[5] else None,
             "days_no_activity": int(r[6] or 0)} for r in result]


def _query_processor_file_aging_report(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me file aging report - days in each stage"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.days_in_stage,
               l.closing_date,
               CASE WHEN l.days_in_stage > 21 THEN 'Red'
                    WHEN l.days_in_stage > 14 THEN 'Yellow'
                    ELSE 'Green' END as aging_status
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        ORDER BY l.days_in_stage DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "days_in_stage": r[4],
             "closing_date": r[5].isoformat() if r[5] else None,
             "aging_status": r[6]} for r in result]


def _query_processor_file_velocity(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my file velocity - how fast files move through pipeline"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total_files,
            ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - application_date))/86400), 1) as avg_days_app_to_fund,
            ROUND(AVG(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400), 1) as avg_days_app_to_uw,
            ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - submitted_to_uw_date))/86400), 1) as avg_days_uw_to_fund
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND stage = 'FUNDED'
        AND funded_date >= NOW() - INTERVAL '90 days'
        AND application_date IS NOT NULL
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"total_files": 0, "avg_days_app_to_fund": 0}

    return {
        "total_files": row[0],
        "avg_days_app_to_fund": float(row[1]) if row[1] else 0,
        "avg_days_app_to_uw": float(row[2]) if row[2] else 0,
        "avg_days_uw_to_fund": float(row[3]) if row[3] else 0
    }


def _query_processor_files_at_risk_fallout(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files are at risk of falling out - fallout prediction"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.risk_score,
               l.days_in_stage, l.sentiment
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        AND (l.risk_score > 75 OR l.sentiment < 3 OR l.days_in_stage > 28)
        ORDER BY l.risk_score DESC, l.sentiment ASC
        LIMIT 30
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "risk_score": r[4], "days_in_stage": r[5],
             "sentiment": r[6]} for r in result]


def _query_processor_funnel_health(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Show me my funnel health - files by stage distribution"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE stage IN ('APPLICATION', 'PROCESSING')) as top_funnel,
            COUNT(*) FILTER (WHERE stage = 'UNDERWRITING') as middle_funnel,
            COUNT(*) FILTER (WHERE stage IN ('APPROVED', 'CLEAR_TO_CLOSE')) as bottom_funnel,
            COUNT(*) as total_active
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND stage NOT IN ('Funded')
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"funnel_health": "No Data", "total_active": 0}

    top = row[0]
    middle = row[1]
    bottom = row[2]
    total = row[3]

    # Healthy funnel should have more files at top
    health = "Healthy" if top >= middle and middle >= bottom else "Needs Attention"

    return {
        "top_funnel": top,
        "middle_funnel": middle,
        "bottom_funnel": bottom,
        "total_active": total,
        "funnel_health": health
    }


def _query_processor_files_closed_this_week(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files closed this week - recent successes"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.funded_date, l.amount,
               l.loan_type
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage = 'FUNDED'
        AND l.funded_date >= DATE_TRUNC('week', NOW())
        ORDER BY l.funded_date DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "funded_date": r[3].isoformat() if r[3] else None,
             "amount": float(r[4] or 0), "loan_type": r[5]} for r in result]


# ============================================================================
# PROBLEM RESOLUTION (8 queries)
# ============================================================================

def _query_processor_all_file_issues(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me all file issues - problems across all files"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               COUNT(c.id) FILTER (WHERE c.status = 'open') as open_conditions,
               l.risk_score, l.blocking_issue
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.risk_score, l.blocking_issue
        HAVING COUNT(c.id) FILTER (WHERE c.status = 'open') > 3 OR l.risk_score > 60 OR l.blocking_issue IS NOT NULL
        ORDER BY open_conditions DESC, l.risk_score DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "stage": r[3],
             "open_conditions": r[4], "risk_score": r[5], "blocking_issue": r[6]} for r in result]


def _query_processor_income_calc_problems(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files have income calculation problems - qualifying issues"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.income, l.dti,
               l.income_issues
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND (l.dti > 43 OR l.income_issues IS NOT NULL)
        AND l.stage NOT IN ('Funded')
        ORDER BY l.dti DESC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "income": float(r[3] or 0), "dti": float(r[4] or 0),
             "income_issues": r[5]} for r in result]


def _query_processor_credit_disputes(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files have credit disputes - credit-related obstacles"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.credit_score,
               l.credit_disputes, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.credit_disputes IS NOT NULL
        AND l.credit_disputes != ''
        AND l.stage NOT IN ('Funded')
        ORDER BY l.credit_score ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "credit_score": r[3], "credit_disputes": r[4], "stage": r[5]} for r in result]


def _query_processor_appraisal_gaps(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me appraisal gap issues - value shortfalls"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.amount, l.property_value,
               l.amount - l.property_value as shortage,
               ROUND(100.0 * (l.amount - l.property_value) / NULLIF(l.amount, 0), 1) as shortage_pct
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.appraisal_received_date IS NOT NULL
        AND l.property_value < l.amount
        AND l.stage NOT IN ('Funded')
        ORDER BY shortage DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "loan_amount": float(r[3] or 0), "appraised_value": float(r[4] or 0),
             "shortage": float(r[5] or 0), "shortage_pct": float(r[6] or 0)} for r in result]


def _query_processor_title_issues(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What files have title issues - title clearance problems"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.title_exceptions,
               l.title_company, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.title_received_date IS NOT NULL
        AND l.title_exceptions IS NOT NULL
        AND l.title_cleared_date IS NULL
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "title_exceptions": r[3], "title_company": r[4], "stage": r[5]} for r in result]


def _query_processor_manual_underwriting_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files need manual underwriting - AUS refer/caution"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.aus_result, l.stage,
               l.credit_score, l.dti
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.aus_result IN ('Refer', 'Caution', 'Manual')
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "aus_result": r[3], "stage": r[4], "credit_score": r[5],
             "dti": float(r[6] or 0)} for r in result]


def _query_processor_eligibility_issues(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me files with eligibility issues - product fit problems"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_type,
               l.eligibility_issues, l.stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.eligibility_issues IS NOT NULL
        AND l.stage NOT IN ('Funded')
        ORDER BY l.closing_date ASC NULLS LAST
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "loan_type": r[3], "eligibility_issues": r[4], "stage": r[5]} for r in result]


def _query_processor_whats_blocking_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What's blocking each file - obstacle identification"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.blocking_issue,
               l.days_in_stage
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.blocking_issue IS NOT NULL
        AND l.stage NOT IN ('Funded')
        ORDER BY l.days_in_stage DESC
        LIMIT 50
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "stage": r[3], "blocking_issue": r[4], "days_in_stage": r[5]} for r in result]


# ============================================================================
# PERFORMANCE & ANALYTICS (7 queries)
# ============================================================================

def _query_processor_closing_ratio(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my closing ratio - files closed vs started"""
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date >= NOW() - INTERVAL '90 days') as closed,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '90 days') as started,
            ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date >= NOW() - INTERVAL '90 days') /
                  NULLIF(COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '90 days'), 0), 1) as closing_ratio_pct
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"closing_ratio_pct": 0, "closed": 0, "started": 0}

    return {
        "files_closed_90d": row[0],
        "files_started_90d": row[1],
        "closing_ratio_pct": float(row[2]) if row[2] else 0
    }


def _query_processor_avg_processing_time(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Show me my average processing time - efficiency metric"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as files_processed,
            ROUND(AVG(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400), 1) as avg_processing_days,
            MIN(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400)::int as fastest,
            MAX(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400)::int as slowest
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND submitted_to_uw_date IS NOT NULL
        AND submitted_to_uw_date >= NOW() - INTERVAL '90 days'
        AND application_date IS NOT NULL
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"avg_processing_days": 0, "files_processed": 0}

    return {
        "files_processed": row[0],
        "avg_processing_days": float(row[1]) if row[1] else 0,
        "fastest_file": row[2],
        "slowest_file": row[3]
    }


def _query_processor_peer_comparison(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """How do I compare to other processors - peer benchmarking"""
    result = db.execute(text("""
        WITH processor_stats AS (
            SELECT
                processor,
                COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date >= NOW() - INTERVAL '90 days') as closed,
                ROUND(AVG(CASE WHEN stage = 'FUNDED'
                          THEN EXTRACT(EPOCH FROM (funded_date - application_date))/86400 END), 1) as avg_days
            FROM loans
            WHERE processor IS NOT NULL
            AND application_date >= NOW() - INTERVAL '180 days'
            GROUP BY processor
        ),
        my_stats AS (
            SELECT closed, avg_days
            FROM processor_stats
            WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        ),
        avg_stats AS (
            SELECT ROUND(AVG(closed), 1) as avg_closed, ROUND(AVG(avg_days), 1) as avg_days
            FROM processor_stats
        )
        SELECT
            m.closed as my_closed,
            m.avg_days as my_avg_days,
            a.avg_closed as team_avg_closed,
            a.avg_days as team_avg_days
        FROM my_stats m CROSS JOIN avg_stats a
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"status": "No comparison data available"}

    return {
        "my_closed_90d": row[0],
        "my_avg_days": float(row[1]) if row[1] else 0,
        "team_avg_closed": float(row[2]) if row[2] else 0,
        "team_avg_days": float(row[3]) if row[3] else 0,
        "vs_team": "Above Average" if row[0] > row[2] else "Below Average"
    }


def _query_processor_condition_clear_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my condition clear rate - how fast I clear conditions"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as total_conditions,
            COUNT(*) FILTER (WHERE cleared_date IS NOT NULL) as cleared,
            ROUND(100.0 * COUNT(*) FILTER (WHERE cleared_date IS NOT NULL) / NULLIF(COUNT(*), 0), 1) as clear_rate_pct,
            ROUND(AVG(EXTRACT(EPOCH FROM (cleared_date - created_at))/86400), 1) as avg_days_to_clear
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.created_at >= NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"clear_rate_pct": 0, "total_conditions": 0}

    return {
        "total_conditions_90d": row[0],
        "cleared_conditions": row[1],
        "clear_rate_pct": float(row[2]) if row[2] else 0,
        "avg_days_to_clear": float(row[3]) if row[3] else 0
    }


def _query_processor_error_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Show me my error rate - quality metric"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as files_submitted,
            COUNT(*) FILTER (WHERE data_quality_score < 80) as files_with_errors,
            ROUND(100.0 * COUNT(*) FILTER (WHERE data_quality_score < 80) / NULLIF(COUNT(*), 0), 1) as error_rate_pct,
            ROUND(AVG(data_quality_score), 1) as avg_quality_score
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND submitted_to_uw_date >= NOW() - INTERVAL '90 days'
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"error_rate_pct": 0, "files_submitted": 0}

    return {
        "files_submitted_90d": row[0],
        "files_with_errors": row[1],
        "error_rate_pct": float(row[2]) if row[2] else 0,
        "avg_quality_score": float(row[3]) if row[3] else 0
    }


def _query_processor_fastest_loan_types(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What types of files do I process fastest - loan type efficiency"""
    result = db.execute(text("""
        SELECT
            l.loan_type,
            COUNT(*) as files,
            ROUND(AVG(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400), 1) as avg_days_to_submit
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.submitted_to_uw_date IS NOT NULL
        AND l.submitted_to_uw_date >= NOW() - INTERVAL '90 days'
        GROUP BY l.loan_type
        HAVING COUNT(*) >= 3
        ORDER BY avg_days_to_submit ASC
    """), {"user_id": user_id})

    return [{"loan_type": r[0], "files": r[1], "avg_days_to_submit": float(r[2] or 0)} for r in result]


def _query_processor_slowest_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which files took the longest to process - bottleneck analysis"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_type,
               l.application_date, l.submitted_to_uw_date,
               ROUND(EXTRACT(EPOCH FROM (submitted_to_uw_date - application_date))/86400) as processing_days
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.submitted_to_uw_date IS NOT NULL
        AND l.submitted_to_uw_date >= NOW() - INTERVAL '90 days'
        ORDER BY processing_days DESC
        LIMIT 20
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "loan_type": r[3],
             "application_date": r[4].isoformat() if r[4] else None,
             "submitted_date": r[5].isoformat() if r[5] else None,
             "processing_days": int(r[6] or 0)} for r in result]


# ============================================================================
# CAPACITY & WORKLOAD PLANNING (5 queries)
# ============================================================================

def _query_processor_at_capacity_check(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Am I at capacity - workload assessment"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as current_files,
            25 as optimal_capacity,
            COUNT(*) FILTER (WHERE closing_date < NOW() + INTERVAL '30 days') as closing_next_month,
            ROUND(100.0 * COUNT(*) / 25, 1) as utilization_pct,
            CASE WHEN COUNT(*) > 30 THEN 'Over Capacity'
                 WHEN COUNT(*) > 25 THEN 'At Capacity'
                 WHEN COUNT(*) > 20 THEN 'Near Capacity'
                 ELSE 'Available' END as capacity_status
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND stage NOT IN ('Funded')
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"capacity_status": "Available", "current_files": 0}

    return {
        "current_files": row[0],
        "optimal_capacity": row[1],
        "closing_next_month": row[2],
        "utilization_pct": float(row[3]) if row[3] else 0,
        "capacity_status": row[4],
        "can_take_new_files": row[0] < 25
    }


def _query_processor_incoming_files(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What new files are coming to me - upcoming assignments"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_type, l.amount,
               l.application_date, l.loan_officer_id,
               u.first_name || ' ' || u.last_name as lo_name
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage IN ('APPLICATION', 'NEW')
        AND l.application_date >= NOW() - INTERVAL '7 days'
        ORDER BY l.application_date DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2], "loan_type": r[3],
             "amount": float(r[4] or 0), "application_date": r[5].isoformat() if r[5] else None,
             "lo_id": r[6], "lo_name": r[7]} for r in result]


def _query_processor_can_take_another(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Can I take another file - bandwidth check"""
    result = db.execute(text("""
        SELECT
            COUNT(*) as current_files,
            COUNT(*) FILTER (WHERE closing_date < NOW() + INTERVAL '14 days') as urgent_files,
            25 as max_capacity
        FROM loans
        WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND stage NOT IN ('Funded')
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"can_take_file": True, "current_files": 0, "reason": "Available"}

    current = row[0]
    urgent = row[1]
    max_cap = row[2]

    can_take = current < max_cap and urgent < 10
    reason = "Available" if can_take else "At capacity or too many urgent files"

    return {
        "can_take_file": can_take,
        "current_files": current,
        "urgent_files": urgent,
        "max_capacity": max_cap,
        "reason": reason
    }


def _query_processor_workload_trend(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me my workload trend - volume over time"""
    result = db.execute(text("""
        SELECT
            DATE_TRUNC('week', l.application_date) as week,
            COUNT(*) as files_received,
            COUNT(*) FILTER (WHERE l.submitted_to_uw_date IS NOT NULL) as files_submitted
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.application_date >= NOW() - INTERVAL '12 weeks'
        GROUP BY DATE_TRUNC('week', l.application_date)
        ORDER BY week DESC
    """), {"user_id": user_id})

    return [{"week": r[0].isoformat() if r[0] else None,
             "files_received": r[1], "files_submitted": r[2]} for r in result]


def _query_processor_file_distribution(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What's my file distribution by loan type - portfolio mix"""
    result = db.execute(text("""
        SELECT
            l.loan_type,
            COUNT(*) as file_count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM loans
                                      WHERE processor = (SELECT CONCAT(first_name, ' ', last_name)
                                                        FROM users WHERE id = :user_id)
                                      AND stage NOT IN ('Funded')), 1) as pct_of_pipeline
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY l.loan_type
        ORDER BY file_count DESC
    """), {"user_id": user_id})

    return [{"loan_type": r[0], "file_count": r[1], "pct_of_pipeline": float(r[2] or 0)} for r in result]


# ============================================================================
# REPORTING & INSIGHTS (6 queries)
# ============================================================================

def _query_processor_weekly_summary(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """Show me my weekly summary - week-over-week performance"""
    result = db.execute(text("""
        WITH this_week AS (
            SELECT
                COUNT(*) FILTER (WHERE stage = 'FUNDED') as closed,
                COUNT(*) FILTER (WHERE application_date >= DATE_TRUNC('week', NOW())) as new_files,
                COUNT(*) FILTER (WHERE submitted_to_uw_date >= DATE_TRUNC('week', NOW())) as submitted
            FROM loans
            WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        ),
        last_week AS (
            SELECT
                COUNT(*) FILTER (WHERE stage = 'FUNDED') as closed,
                COUNT(*) FILTER (WHERE application_date >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week'
                                 AND application_date < DATE_TRUNC('week', NOW())) as new_files
            FROM loans
            WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        )
        SELECT tw.closed, tw.new_files, tw.submitted, lw.closed, lw.new_files
        FROM this_week tw CROSS JOIN last_week lw
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"this_week_closed": 0, "this_week_new": 0}

    return {
        "this_week_closed": row[0],
        "this_week_new_files": row[1],
        "this_week_submitted": row[2],
        "last_week_closed": row[3],
        "last_week_new_files": row[4],
        "closed_change": row[0] - row[3]
    }


def _query_processor_weekly_wins(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """What were my wins this week - successfully closed files"""
    result = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.funded_date, l.amount,
               l.loan_type,
               ROUND(EXTRACT(EPOCH FROM (l.funded_date - l.application_date))/86400) as days_to_close
        FROM loans l
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage = 'FUNDED'
        AND l.funded_date >= DATE_TRUNC('week', NOW())
        ORDER BY l.funded_date DESC
    """), {"user_id": user_id})

    return [{"loan_id": r[0], "loan_number": r[1], "borrower": r[2],
             "funded_date": r[3].isoformat() if r[3] else None,
             "amount": float(r[4] or 0), "loan_type": r[5],
             "days_to_close": int(r[6] or 0)} for r in result]


def _query_processor_time_allocation(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Where am I spending the most time - time allocation analysis"""
    result = db.execute(text("""
        SELECT
            'Document Collection' as activity,
            COUNT(DISTINCT l.id) as files,
            SUM(CASE WHEN d.status IN ('missing', 'requested') THEN 1 ELSE 0 END) as open_items
        FROM loans l
        LEFT JOIN documents d ON d.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY activity

        UNION ALL

        SELECT
            'Condition Management' as activity,
            COUNT(DISTINCT l.id) as files,
            SUM(CASE WHEN c.status = 'open' THEN 1 ELSE 0 END) as open_items
        FROM loans l
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.stage NOT IN ('Funded')
        GROUP BY activity

        ORDER BY open_items DESC
    """), {"user_id": user_id})

    return [{"activity": r[0], "files_involved": r[1], "open_items": r[2]} for r in result]


def _query_processor_biggest_bottleneck(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
    """What's my biggest bottleneck - process improvement opportunity"""
    result = db.execute(text("""
        WITH stage_times AS (
            SELECT
                stage,
                COUNT(*) as files,
                ROUND(AVG(days_in_stage), 1) as avg_days
            FROM loans
            WHERE processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
            AND stage NOT IN ('Funded')
            GROUP BY stage
        )
        SELECT stage, files, avg_days
        FROM stage_times
        ORDER BY avg_days DESC
        LIMIT 1
    """), {"user_id": user_id})

    row = result.fetchone()
    if not row:
        return {"bottleneck": "No bottlenecks identified"}

    return {
        "bottleneck_stage": row[0],
        "files_in_stage": row[1],
        "avg_days_in_stage": float(row[2]) if row[2] else 0,
        "recommendation": f"Focus on improving {row[0]} stage efficiency"
    }


def _query_processor_common_conditions(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Show me my most common conditions - pattern recognition"""
    result = db.execute(text("""
        SELECT
            c.condition_type,
            COUNT(*) as occurrence_count,
            ROUND(AVG(EXTRACT(EPOCH FROM (c.cleared_date - c.created_at))/86400), 1) as avg_days_to_clear
        FROM conditions c
        JOIN loans l ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND c.created_at >= NOW() - INTERVAL '90 days'
        GROUP BY c.condition_type
        HAVING COUNT(*) >= 3
        ORDER BY occurrence_count DESC
        LIMIT 15
    """), {"user_id": user_id})

    return [{"condition_type": r[0], "count": r[1], "avg_days_to_clear": float(r[2] or 0)} for r in result]


def _query_processor_lo_quality_ranking(db: Session, params: Dict, user_id: int) -> List[Dict]:
    """Which loan officers send me the cleanest files - LO quality ranking"""
    result = db.execute(text("""
        SELECT
            u.id as lo_id,
            u.first_name || ' ' || u.last_name as lo_name,
            COUNT(l.id) as files,
            ROUND(AVG(l.data_quality_score), 1) as avg_quality_score,
            ROUND(AVG(l.days_in_stage) FILTER (WHERE l.stage = 'Processing'), 1) as avg_processing_time,
            COUNT(c.id)::numeric / NULLIF(COUNT(DISTINCT l.id), 0) as conditions_per_file
        FROM loans l
        LEFT JOIN users u ON l.loan_officer_id = u.id
        LEFT JOIN conditions c ON c.loan_id = l.id
        WHERE l.processor = (SELECT CONCAT(first_name, ' ', last_name) FROM users WHERE id = :user_id)
        AND l.application_date >= NOW() - INTERVAL '90 days'
        GROUP BY u.id, u.first_name, u.last_name
        HAVING COUNT(l.id) >= 5
        ORDER BY avg_quality_score DESC, conditions_per_file ASC
    """), {"user_id": user_id})

    return [{"lo_id": r[0], "lo_name": r[1], "files": r[2],
             "avg_quality_score": float(r[3] or 0),
             "avg_processing_days": float(r[4] or 0),
             "conditions_per_file": float(r[5] or 0)} for r in result]
