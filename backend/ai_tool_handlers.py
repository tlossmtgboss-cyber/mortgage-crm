"""
AI Tool Handlers
Actual implementations of tools that agents can use
"""

import os
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import openai

from ai_models import ToolContext

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")


# ============================================================================
# LEAD MANAGEMENT TOOLS
# ============================================================================

async def handle_search_leads(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Search and list leads with filtering options"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        # Filter parameters
        stage = input_data.get("stage")  # Filter by stage (New, Prospect, etc.)
        search_query = input_data.get("search_query", "")  # Search by name, email, phone
        limit = input_data.get("limit", 20)
        include_recent_activity = input_data.get("include_recent_activity", True)

        # Build query based on filters
        if stage:
            query = text("""
                SELECT
                    id, name, first_name, last_name, email, phone,
                    stage, source, credit_score, loan_amount,
                    created_at, updated_at, assigned_to
                FROM leads
                WHERE stage = :stage
                ORDER BY updated_at DESC
                LIMIT :limit
            """)
            results = db.execute(query, {"stage": stage, "limit": limit}).fetchall()
        elif search_query:
            query = text("""
                SELECT
                    id, name, first_name, last_name, email, phone,
                    stage, source, credit_score, loan_amount,
                    created_at, updated_at, assigned_to
                FROM leads
                WHERE
                    name ILIKE :search_pattern
                    OR first_name ILIKE :search_pattern
                    OR last_name ILIKE :search_pattern
                    OR email ILIKE :search_pattern
                    OR phone ILIKE :search_pattern
                ORDER BY updated_at DESC
                LIMIT :limit
            """)
            results = db.execute(query, {
                "search_pattern": f"%{search_query}%",
                "limit": limit
            }).fetchall()
        else:
            # Get all leads, most recent first
            query = text("""
                SELECT
                    id, name, first_name, last_name, email, phone,
                    stage, source, credit_score, loan_amount,
                    created_at, updated_at, assigned_to
                FROM leads
                ORDER BY updated_at DESC
                LIMIT :limit
            """)
            results = db.execute(query, {"limit": limit}).fetchall()

        leads = []
        for row in results:
            lead_name = row.name or f"{row.first_name or ''} {row.last_name or ''}".strip() or "Unknown"
            leads.append({
                "id": row.id,
                "name": lead_name,
                "email": row.email,
                "phone": row.phone,
                "stage": row.stage,
                "source": row.source,
                "credit_score": row.credit_score,
                "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None
            })

        # Get stage counts for summary
        stage_query = text("""
            SELECT stage, COUNT(*) as count
            FROM leads
            GROUP BY stage
        """)
        stage_results = db.execute(stage_query).fetchall()
        stage_counts = {row.stage: row.count for row in stage_results}

        return {
            "success": True,
            "leads": leads,
            "count": len(leads),
            "stage_counts": stage_counts,
            "filter_applied": {
                "stage": stage,
                "search_query": search_query if search_query else None
            }
        }
    finally:
        db.close()


async def handle_get_lead_by_id(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Get lead details by ID"""
    from database import SessionLocal

    lead_id = input_data["lead_id"]
    db = SessionLocal()

    try:
        query = text("SELECT * FROM leads WHERE id = :lead_id")
        result = db.execute(query, {"lead_id": lead_id}).fetchone()

        if not result:
            return {"success": False, "error": "Lead not found"}

        return {
            "success": True,
            "lead": dict(result._mapping)
        }
    finally:
        db.close()


async def handle_update_lead_stage(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Update lead stage/status"""
    from database import SessionLocal

    lead_id = input_data["lead_id"]
    stage = input_data["stage"]

    db = SessionLocal()

    try:
        query = text("""
            UPDATE leads
            SET stage = :stage,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :lead_id
            RETURNING id, first_name, last_name, stage
        """)

        result = db.execute(query, {"lead_id": lead_id, "stage": stage}).fetchone()
        db.commit()

        if not result:
            return {"success": False, "error": "Lead not found"}

        return {
            "success": True,
            "lead": dict(result._mapping),
            "message": f"Lead {lead_id} moved to {stage}"
        }
    finally:
        db.close()


async def handle_create_task(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Create a new task"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        query = text("""
            INSERT INTO tasks (
                title, description, assigned_to, due_date, priority,
                entity_type, entity_id, status, created_by
            ) VALUES (
                :title, :description, :assigned_to, :due_date, :priority,
                :entity_type, :entity_id, 'pending', :created_by
            )
            RETURNING id, title, assigned_to
        """)

        result = db.execute(query, {
            "title": input_data["title"],
            "description": input_data.get("description", ""),
            "assigned_to": input_data["assigned_to"],
            "due_date": input_data.get("due_date"),
            "priority": input_data.get("priority", "normal"),
            "entity_type": input_data.get("entity_type"),
            "entity_id": input_data.get("entity_id"),
            "created_by": context.user_id or 1  # System user
        }).fetchone()

        db.commit()

        return {
            "success": True,
            "task": dict(result._mapping),
            "message": f"Task '{input_data['title']}' created"
        }
    finally:
        db.close()


async def handle_assign_lead_to_user(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Assign lead to a user"""
    from database import SessionLocal

    lead_id = input_data["lead_id"]
    user_id = input_data["user_id"]

    db = SessionLocal()

    try:
        query = text("""
            UPDATE leads
            SET assigned_to = :user_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :lead_id
            RETURNING id, first_name, last_name, assigned_to
        """)

        result = db.execute(query, {"lead_id": lead_id, "user_id": user_id}).fetchone()
        db.commit()

        if not result:
            return {"success": False, "error": "Lead not found"}

        return {
            "success": True,
            "lead": dict(result._mapping),
            "message": f"Lead assigned to user {user_id}"
        }
    finally:
        db.close()


async def handle_score_lead_quality(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Score lead quality based on criteria"""
    lead_data = input_data.get("lead_data", {})

    score = 0
    factors = []

    # Credit score check
    credit_score = lead_data.get("credit_score", 0)
    if credit_score >= 740:
        score += 30
        factors.append("Excellent credit")
    elif credit_score >= 680:
        score += 20
        factors.append("Good credit")
    elif credit_score >= 620:
        score += 10
        factors.append("Fair credit")

    # DTI check
    dti = lead_data.get("dti", 100)
    if dti <= 36:
        score += 25
        factors.append("Strong DTI")
    elif dti <= 43:
        score += 15
        factors.append("Good DTI")

    # Down payment
    down_payment_percent = lead_data.get("down_payment_percent", 0)
    if down_payment_percent >= 20:
        score += 20
        factors.append("20%+ down payment")
    elif down_payment_percent >= 10:
        score += 10
        factors.append("10%+ down payment")

    # Contact info complete
    if lead_data.get("phone") and lead_data.get("email"):
        score += 15
        factors.append("Complete contact info")

    # Pre-approval
    if lead_data.get("has_pre_approval"):
        score += 10
        factors.append("Pre-approved")

    # Classify
    if score >= 70:
        quality = "hot"
    elif score >= 50:
        quality = "warm"
    elif score >= 30:
        quality = "cold"
    else:
        quality = "unqualified"

    return {
        "success": True,
        "score": score,
        "quality": quality,
        "factors": factors
    }


# ============================================================================
# COMMUNICATION TOOLS
# ============================================================================

async def handle_send_sms(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Send SMS message via Telnyx"""
    # Import SMS service
    try:
        from integrations.sms_service import get_sms_client

        to_number = input_data["to_number"]
        message = input_data["message"]
        lead_id = input_data.get("lead_id")

        sms_client = get_sms_client()

        # Check if SMS is enabled
        if not sms_client.enabled:
            return {
                "success": False,
                "error": "SMS service not configured"
            }

        # Send SMS
        provider_message_id = await sms_client.send_sms(to_number=to_number, message=message)

        # Log communication
        if lead_id:
            from database import SessionLocal
            db = SessionLocal()
            try:
                query = text("""
                    INSERT INTO communications (
                        lead_id, type, direction, content, status, created_by
                    ) VALUES (
                        :lead_id, 'sms', 'outbound', :content, 'sent', :created_by
                    )
                """)

                db.execute(query, {
                    "lead_id": lead_id,
                    "content": message,
                    "created_by": context.user_id or 1
                })
                db.commit()
            finally:
                db.close()

        return {
            "success": True,
            "provider_message_id": provider_message_id,
            "message": "SMS sent successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


async def handle_send_email(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Send email message using the configured email service"""
    from email_service import email_service
    from database import SessionLocal

    to_email = input_data["to_email"]
    subject = input_data["subject"]
    body = input_data["body"]
    lead_id = input_data.get("lead_id")
    is_html = input_data.get("is_html", False)

    # Send the actual email with correct FROM address (routes through Salesforce when connected)
    import os
    try:
        from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _fallback_email
    except ImportError:
        _fallback_email = "sarah@reply.perenniaai.com"
    ai_from_email = os.getenv("AI_FROM_EMAIL", _fallback_email)
    db = SessionLocal()
    try:
        if is_html:
            success = await email_service.send_html_email_sf(
                to_email=to_email,
                subject=subject,
                html_body=body,
                plain_text_body=input_data.get("plain_text_body"),
                from_email=ai_from_email,
                reply_to=ai_from_email,
                db=db,
                user_id=context.user_id,
            )
        else:
            # Convert plain text to simple HTML
            html_body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
            success = await email_service.send_html_email_sf(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=body,
                from_email=ai_from_email,
                reply_to=ai_from_email,
                db=db,
                user_id=context.user_id,
            )
    except Exception as e:
        db.close()
        return {
            "success": False,
            "message": "Failed to send email",
            "error": "Internal server error"
        }

    # Log the communication if associated with a lead
    if lead_id:
        try:
            query = text("""
                INSERT INTO communications (
                    lead_id, type, direction, content, status, created_by
                ) VALUES (
                    :lead_id, 'email', 'outbound', :content, :status, :created_by
                )
            """)

            db.execute(query, {
                "lead_id": lead_id,
                "content": f"{subject}\n\n{body}",
                "status": "sent" if success else "failed",
                "created_by": context.user_id or 1
            })
            db.commit()
        finally:
            db.close()
    else:
        db.close()

    return {
        "success": success,
        "message": "Email sent successfully" if success else "Email delivery failed",
        "to": to_email,
        "subject": subject
    }


async def handle_draft_sms(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Draft SMS message using AI"""
    lead_data = input_data.get("lead_data", {})
    purpose = input_data.get("purpose", "general")
    tone = input_data.get("tone", "professional")

    # Use OpenAI to draft message
    try:
        prompt = f"""Draft a brief SMS message for a mortgage lead:

Lead Name: {lead_data.get('first_name', '')} {lead_data.get('last_name', '')}
Purpose: {purpose}
Tone: {tone}

Keep it under 160 characters, friendly but professional.
"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a mortgage loan officer assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )

        draft = response.choices[0].message.content.strip()

        return {
            "success": True,
            "draft": draft,
            "requires_approval": True
        }

    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


async def handle_draft_email(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Draft email message using AI"""
    lead_data = input_data.get("lead_data", {})
    purpose = input_data.get("purpose", "general")
    tone = input_data.get("tone", "professional")

    # Use OpenAI to draft email
    try:
        prompt = f"""Draft an email for a mortgage lead:

Lead Name: {lead_data.get('first_name', '')} {lead_data.get('last_name', '')}
Purpose: {purpose}
Tone: {tone}

Include subject line and body. Keep it concise and professional.
"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a mortgage loan officer assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )

        draft = response.choices[0].message.content.strip()

        # Try to parse subject and body
        lines = draft.split('\n')
        subject = lines[0].replace("Subject:", "").strip()
        body = '\n'.join(lines[1:]).strip()

        return {
            "success": True,
            "subject": subject,
            "body": body,
            "requires_approval": True
        }

    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


# ============================================================================
# LOAN / PIPELINE TOOLS
# ============================================================================

async def handle_get_loan_by_id(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Get loan details by ID"""
    from database import SessionLocal

    loan_id = input_data["loan_id"]
    db = SessionLocal()

    try:
        query = text("SELECT * FROM loans WHERE id = :loan_id")
        result = db.execute(query, {"loan_id": loan_id}).fetchone()

        if not result:
            return {"success": False, "error": "Loan not found"}

        return {
            "success": True,
            "loan": dict(result._mapping)
        }
    finally:
        db.close()


async def handle_update_loan_stage(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Update loan stage"""
    from database import SessionLocal

    loan_id = input_data["loan_id"]
    stage = input_data["stage"]
    reason = input_data.get("reason", "AI agent update")

    db = SessionLocal()

    try:
        query = text("""
            UPDATE loans
            SET stage = :stage,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :loan_id
            RETURNING id, borrower_name, stage
        """)

        result = db.execute(query, {"loan_id": loan_id, "stage": stage}).fetchone()
        db.commit()

        if not result:
            return {"success": False, "error": "Loan not found"}

        # Log the stage change
        log_query = text("""
            INSERT INTO loan_stage_history (
                loan_id, old_stage, new_stage, changed_by, reason
            ) VALUES (
                :loan_id, NULL, :new_stage, :changed_by, :reason
            )
        """)

        db.execute(log_query, {
            "loan_id": loan_id,
            "new_stage": stage,
            "changed_by": context.user_id or 1,
            "reason": reason
        })
        db.commit()

        return {
            "success": True,
            "loan": dict(result._mapping),
            "message": f"Loan {loan_id} moved to {stage}"
        }
    finally:
        db.close()


async def handle_get_pipeline_snapshot(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Get current pipeline snapshot"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        # Get counts by stage
        query = text("""
            SELECT
                stage,
                COUNT(*) as count,
                SUM(loan_amount) as total_amount,
                AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 86400) as avg_days_in_stage
            FROM loans
            WHERE status = 'active'
            GROUP BY stage
            ORDER BY
                CASE stage
                    WHEN 'application' THEN 1
                    WHEN 'processing' THEN 2
                    WHEN 'underwriting' THEN 3
                    WHEN 'clear_to_close' THEN 4
                    WHEN 'closing' THEN 5
                    ELSE 6
                END
        """)

        results = db.execute(query).fetchall()

        stages = []
        total_count = 0
        total_amount = 0

        for row in results:
            stages.append({
                "stage": row.stage,
                "count": row.count,
                "total_amount": float(row.total_amount) if row.total_amount else 0,
                "avg_days": round(row.avg_days_in_stage, 1) if row.avg_days_in_stage else 0
            })
            total_count += row.count
            total_amount += float(row.total_amount) if row.total_amount else 0

        return {
            "success": True,
            "snapshot": {
                "stages": stages,
                "total_loans": total_count,
                "total_volume": total_amount,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    finally:
        db.close()


async def handle_find_stale_loans(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Find stale/stuck loans"""
    from database import SessionLocal

    threshold_days = input_data.get("threshold_days", 7)

    db = SessionLocal()

    try:
        query = text("""
            SELECT
                id, borrower_name, stage, loan_amount,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at)) / 86400 as days_stale
            FROM loans
            WHERE status = 'active'
            AND updated_at < CURRENT_TIMESTAMP - INTERVAL ':days days'
            ORDER BY updated_at ASC
            LIMIT 50
        """)

        results = db.execute(query, {"days": threshold_days}).fetchall()

        stale_loans = []
        for row in results:
            stale_loans.append({
                "loan_id": row.id,
                "borrower_name": row.borrower_name,
                "stage": row.stage,
                "loan_amount": float(row.loan_amount) if row.loan_amount else 0,
                "days_stale": round(row.days_stale, 1)
            })

        return {
            "success": True,
            "stale_loans": stale_loans,
            "count": len(stale_loans)
        }
    finally:
        db.close()


# ============================================================================
# DOCUMENT TOOLS
# ============================================================================

async def handle_classify_document(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Classify document type using Claude Vision AI"""
    from services.document_analysis_service import DocumentAnalysisService

    document_id = input_data["document_id"]
    file_path = input_data.get("file_path", "")
    claimed_type = input_data.get("claimed_type")
    borrower_name = input_data.get("borrower_name")

    if not file_path:
        return {
            "success": False,
            "document_id": document_id,
            "error": "No file path provided for document classification"
        }

    # Use the document analysis service
    service = DocumentAnalysisService()
    result = await service.analyze_document(
        file_path=file_path,
        claimed_type=claimed_type,
        borrower_name=borrower_name,
        additional_context=input_data.get("context")
    )

    return {
        "success": result.verified or result.confidence > 0,
        "document_id": document_id,
        "document_type": result.document_type,
        "confidence": result.confidence,
        "verified": result.verified,
        "extracted_data": result.extracted_data,
        "issues": result.issues,
        "suggestions": result.suggestions
    }


# ============================================================================
# PORTFOLIO TOOLS
# ============================================================================

async def handle_scan_refi_opportunities(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Scan portfolio for refi opportunities"""
    from database import SessionLocal

    min_rate_improvement_bps = input_data.get("min_rate_improvement_bps", 50)
    current_market_rate = input_data.get("current_market_rate", 6.5)

    db = SessionLocal()

    try:
        query = text("""
            SELECT
                id, borrower_name, original_rate, loan_amount,
                closed_date, property_value
            FROM loans
            WHERE status = 'closed'
            AND original_rate > :threshold_rate
            AND closed_date < CURRENT_TIMESTAMP - INTERVAL '6 months'
            ORDER BY (original_rate - :current_rate) DESC
            LIMIT 50
        """)

        threshold_rate = current_market_rate + (min_rate_improvement_bps / 100)

        results = db.execute(query, {
            "threshold_rate": threshold_rate,
            "current_rate": current_market_rate
        }).fetchall()

        opportunities = []
        for row in results:
            rate_improvement = round(row.original_rate - current_market_rate, 2)
            opportunities.append({
                "loan_id": row.id,
                "borrower_name": row.borrower_name,
                "current_rate": row.original_rate,
                "potential_new_rate": current_market_rate,
                "rate_improvement_bps": int(rate_improvement * 100),
                "loan_amount": float(row.loan_amount) if row.loan_amount else 0,
                "months_since_closing": int((datetime.utcnow() - row.closed_date).days / 30)
            })

        return {
            "success": True,
            "opportunities": opportunities,
            "count": len(opportunities),
            "estimated_value": len(opportunities) * 2000  # Estimated commission per refi
        }
    finally:
        db.close()


async def handle_get_portfolio_loans(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Get portfolio of closed/funded loans with filtering options"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        # Filter parameters
        min_loan_amount = input_data.get("min_loan_amount", 0)
        max_loan_amount = input_data.get("max_loan_amount", 10000000)
        min_rate = input_data.get("min_rate", 0)
        max_rate = input_data.get("max_rate", 20)
        loan_type = input_data.get("loan_type")  # conventional, fha, va, etc.
        months_since_closing = input_data.get("months_since_closing", 0)
        limit = input_data.get("limit", 100)

        query = text("""
            SELECT
                l.id,
                l.borrower_name,
                l.loan_amount,
                l.original_rate,
                l.loan_type,
                l.property_value,
                l.ltv,
                l.closed_date,
                l.status,
                l.property_address,
                l.has_pmi,
                l.pmi_monthly_amount,
                EXTRACT(MONTH FROM AGE(CURRENT_TIMESTAMP, l.closed_date)) as months_since_close
            FROM loans l
            WHERE l.status IN ('closed', 'funded')
            AND l.loan_amount >= :min_loan_amount
            AND l.loan_amount <= :max_loan_amount
            AND COALESCE(l.original_rate, 0) >= :min_rate
            AND COALESCE(l.original_rate, 0) <= :max_rate
            AND (l.closed_date IS NULL OR l.closed_date <= CURRENT_TIMESTAMP - INTERVAL '1 month' * :months_since_closing)
            AND (:loan_type IS NULL OR l.loan_type = :loan_type)
            ORDER BY l.closed_date DESC
            LIMIT :limit
        """)

        results = db.execute(query, {
            "min_loan_amount": min_loan_amount,
            "max_loan_amount": max_loan_amount,
            "min_rate": min_rate,
            "max_rate": max_rate,
            "loan_type": loan_type,
            "months_since_closing": months_since_closing,
            "limit": limit
        }).fetchall()

        loans = []
        total_portfolio_value = 0
        for row in results:
            loan_amount = float(row.loan_amount) if row.loan_amount else 0
            total_portfolio_value += loan_amount
            loans.append({
                "loan_id": row.id,
                "borrower_name": row.borrower_name,
                "loan_amount": loan_amount,
                "original_rate": float(row.original_rate) if row.original_rate else None,
                "loan_type": row.loan_type,
                "property_value": float(row.property_value) if row.property_value else None,
                "ltv": float(row.ltv) if row.ltv else None,
                "closed_date": row.closed_date.isoformat() if row.closed_date else None,
                "property_address": row.property_address,
                "has_pmi": row.has_pmi,
                "pmi_monthly_amount": float(row.pmi_monthly_amount) if row.pmi_monthly_amount else None,
                "months_since_close": int(row.months_since_close) if row.months_since_close else 0
            })

        # Get summary stats
        summary_query = text("""
            SELECT
                COUNT(*) as total_loans,
                SUM(loan_amount) as total_value,
                AVG(original_rate) as avg_rate,
                AVG(ltv) as avg_ltv
            FROM loans
            WHERE status IN ('closed', 'funded')
        """)
        summary = db.execute(summary_query).fetchone()

        return {
            "success": True,
            "loans": loans,
            "count": len(loans),
            "portfolio_summary": {
                "total_loans_in_portfolio": summary.total_loans or 0,
                "total_portfolio_value": float(summary.total_value) if summary.total_value else 0,
                "average_rate": round(float(summary.avg_rate), 3) if summary.avg_rate else None,
                "average_ltv": round(float(summary.avg_ltv), 1) if summary.avg_ltv else None,
                "returned_subset_value": total_portfolio_value
            }
        }
    finally:
        db.close()


async def handle_check_mi_drop_eligibility(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Check loans for MI (mortgage insurance) drop eligibility based on LTV"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        # Parameters
        target_ltv = input_data.get("target_ltv", 80)  # Standard MI drop threshold
        min_months_seasoning = input_data.get("min_months_seasoning", 24)  # Typical requirement
        appreciation_rate = input_data.get("assumed_appreciation_rate", 0.03)  # 3% annual default

        query = text("""
            SELECT
                l.id,
                l.borrower_name,
                l.loan_amount,
                l.original_rate,
                l.property_value,
                l.ltv,
                l.closed_date,
                l.has_pmi,
                l.pmi_monthly_amount,
                l.loan_type,
                EXTRACT(MONTH FROM AGE(CURRENT_TIMESTAMP, l.closed_date)) as months_since_close
            FROM loans l
            WHERE l.status IN ('closed', 'funded')
            AND l.has_pmi = true
            AND l.closed_date <= CURRENT_TIMESTAMP - INTERVAL '1 month' * :min_months
            ORDER BY l.pmi_monthly_amount DESC NULLS LAST
            LIMIT 100
        """)

        results = db.execute(query, {
            "min_months": min_months_seasoning
        }).fetchall()

        eligible_loans = []
        potential_monthly_savings = 0

        for row in results:
            if not row.property_value or not row.loan_amount:
                continue

            months = int(row.months_since_close) if row.months_since_close else 0
            years = months / 12

            # Estimate current property value with appreciation
            original_value = float(row.property_value)
            estimated_current_value = original_value * ((1 + appreciation_rate) ** years)

            # Estimate current loan balance (simplified - assumes 30yr amortization)
            original_loan = float(row.loan_amount)
            rate = float(row.original_rate) / 100 if row.original_rate else 0.065
            monthly_rate = rate / 12
            n_payments = 360
            if monthly_rate > 0:
                monthly_payment = original_loan * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)
                # Remaining balance after 'months' payments
                remaining_balance = original_loan * ((1 + monthly_rate)**n_payments - (1 + monthly_rate)**months) / ((1 + monthly_rate)**n_payments - 1)
            else:
                remaining_balance = original_loan - (original_loan / 360 * months)

            # Calculate current LTV
            current_ltv = (remaining_balance / estimated_current_value) * 100

            if current_ltv <= target_ltv:
                pmi_amount = float(row.pmi_monthly_amount) if row.pmi_monthly_amount else 100
                potential_monthly_savings += pmi_amount

                eligible_loans.append({
                    "loan_id": row.id,
                    "borrower_name": row.borrower_name,
                    "original_ltv": round(float(row.ltv), 1) if row.ltv else None,
                    "estimated_current_ltv": round(current_ltv, 1),
                    "original_property_value": original_value,
                    "estimated_current_value": round(estimated_current_value, 0),
                    "current_balance_estimate": round(remaining_balance, 0),
                    "months_seasoning": months,
                    "pmi_monthly_amount": pmi_amount,
                    "loan_type": row.loan_type,
                    "eligibility_reason": f"LTV now {current_ltv:.1f}% (below {target_ltv}%)"
                })

        return {
            "success": True,
            "eligible_loans": eligible_loans,
            "count": len(eligible_loans),
            "total_monthly_savings_potential": round(potential_monthly_savings, 2),
            "total_annual_savings_potential": round(potential_monthly_savings * 12, 2),
            "analysis_parameters": {
                "target_ltv_threshold": target_ltv,
                "min_months_seasoning": min_months_seasoning,
                "assumed_appreciation_rate": appreciation_rate
            }
        }
    finally:
        db.close()


async def handle_lookup_glossary_term(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Look up mortgage terminology from the glossary"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        search_term = input_data.get("term", "")
        category = input_data.get("category")
        include_related = input_data.get("include_related", True)
        limit = input_data.get("limit", 10)

        if search_term:
            # Search by term name, synonyms, or full-text search
            query = text("""
                SELECT
                    id, term, definition, category, subcategory,
                    synonyms, related_terms, ai_usage, workflow_usage, compliance_tags
                FROM mortgage_glossary
                WHERE
                    term ILIKE :search_pattern
                    OR :search_term = ANY(synonyms)
                    OR to_tsvector('english', term || ' ' || definition) @@ plainto_tsquery('english', :search_term)
                ORDER BY
                    CASE WHEN term ILIKE :search_pattern THEN 0 ELSE 1 END,
                    term
                LIMIT :limit
            """)

            results = db.execute(query, {
                "search_term": search_term,
                "search_pattern": f"%{search_term}%",
                "limit": limit
            }).fetchall()
        elif category:
            # Search by category
            query = text("""
                SELECT
                    id, term, definition, category, subcategory,
                    synonyms, related_terms, ai_usage, workflow_usage, compliance_tags
                FROM mortgage_glossary
                WHERE category ILIKE :category
                ORDER BY term
                LIMIT :limit
            """)

            results = db.execute(query, {
                "category": f"%{category}%",
                "limit": limit
            }).fetchall()
        else:
            return {
                "success": False,
                "error": "Either 'term' or 'category' must be provided"
            }

        terms = []
        for row in results:
            term_data = {
                "id": row.id,
                "term": row.term,
                "definition": row.definition,
                "category": row.category,
                "subcategory": row.subcategory,
                "synonyms": list(row.synonyms) if row.synonyms else [],
                "related_terms": list(row.related_terms) if row.related_terms else [],
                "ai_usage": row.ai_usage,
                "workflow_usage": row.workflow_usage,
                "compliance_tags": list(row.compliance_tags) if row.compliance_tags else []
            }
            terms.append(term_data)

        # Optionally fetch related terms
        related_definitions = []
        if include_related and terms:
            all_related = set()
            for t in terms:
                all_related.update(t.get("related_terms", []))

            if all_related:
                related_query = text("""
                    SELECT term, definition, category
                    FROM mortgage_glossary
                    WHERE term = ANY(:related_terms)
                    LIMIT 20
                """)
                related_results = db.execute(related_query, {
                    "related_terms": list(all_related)
                }).fetchall()

                for row in related_results:
                    related_definitions.append({
                        "term": row.term,
                        "definition": row.definition,
                        "category": row.category
                    })

        return {
            "success": True,
            "terms": terms,
            "count": len(terms),
            "related_definitions": related_definitions if include_related else []
        }
    finally:
        db.close()


# ============================================================================
# OPERATIONS TOOLS
# ============================================================================

async def handle_get_system_health(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Get current system health metrics"""
    from database import SessionLocal

    db = SessionLocal()

    try:
        # Get recent agent execution stats
        query = text("""
            SELECT
                COUNT(*) as total_executions,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                AVG(duration_ms) as avg_duration_ms
            FROM ai_agent_executions
            WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour'
        """)

        result = db.execute(query).fetchone()

        total = result.total_executions or 0
        successful = result.successful or 0
        success_rate = (successful / total * 100) if total > 0 else 100

        return {
            "success": True,
            "health": {
                "status": "healthy" if success_rate > 95 else "degraded",
                "total_executions_last_hour": total,
                "success_rate": round(success_rate, 2),
                "avg_response_time_ms": round(result.avg_duration_ms or 0, 0),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    finally:
        db.close()


# ============================================================================
# FORECASTING TOOLS
# ============================================================================

async def handle_forecast_volume(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Forecast loan volume"""
    weeks_ahead = input_data["weeks_ahead"]

    from database import SessionLocal

    db = SessionLocal()

    try:
        # Get historical data
        query = text("""
            SELECT
                DATE_TRUNC('week', created_at) as week,
                COUNT(*) as loan_count
            FROM loans
            WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '12 weeks'
            GROUP BY week
            ORDER BY week
        """)

        results = db.execute(query).fetchall()

        if not results:
            return {
                "success": True,
                "forecast": {
                    "weeks_ahead": weeks_ahead,
                    "predicted_volume": 0,
                    "confidence": "low"
                }
            }

        # Simple average-based forecast
        historical_avg = sum(row.loan_count for row in results) / len(results)

        return {
            "success": True,
            "forecast": {
                "weeks_ahead": weeks_ahead,
                "predicted_volume": int(historical_avg * weeks_ahead),
                "avg_weekly_volume": round(historical_avg, 1),
                "confidence": "medium",
                "based_on_weeks": len(results)
            }
        }
    finally:
        db.close()


# ============================================================================
# INTER-AGENT COMMUNICATION
# ============================================================================

async def handle_send_agent_message(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Send message to another agent"""
    from ai_services import MessageBus
    from ai_models import AgentMessage, MessageType, Priority
    from database import SessionLocal

    to_agent_id = input_data["to_agent_id"]
    subject = input_data["subject"]
    content = input_data["content"]
    priority = input_data.get("priority", "normal")

    db = SessionLocal()
    message_bus = MessageBus(db)

    try:
        import uuid

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent_id=context.agent_id,
            to_agent_id=to_agent_id,
            message_type=MessageType.REQUEST,
            subject=subject,
            content=content,
            priority=Priority(priority)
        )

        message_id = await message_bus.send_message(message)

        return {
            "success": True,
            "message_id": message_id,
            "message": f"Message sent to {to_agent_id}"
        }
    finally:
        db.close()


# ============================================================================
# TOOL HANDLER REGISTRY
# ============================================================================

TOOL_HANDLERS = {
    # Lead management
    "searchLeads": handle_search_leads,
    "getLeadById": handle_get_lead_by_id,
    "updateLeadStage": handle_update_lead_stage,
    "createTask": handle_create_task,
    "assignLeadToUser": handle_assign_lead_to_user,
    "scoreLeadQuality": handle_score_lead_quality,

    # Communication
    "sendSms": handle_send_sms,
    "sendEmail": handle_send_email,
    "draftSms": handle_draft_sms,
    "draftEmail": handle_draft_email,

    # Loan/Pipeline
    "getLoanById": handle_get_loan_by_id,
    "updateLoanStage": handle_update_loan_stage,
    "getPipelineSnapshot": handle_get_pipeline_snapshot,
    "findStaleLoans": handle_find_stale_loans,

    # Documents
    "classifyDocument": handle_classify_document,

    # Portfolio
    "scanForRefiOpportunities": handle_scan_refi_opportunities,
    "getPortfolioLoans": handle_get_portfolio_loans,
    "checkMIDropEligibility": handle_check_mi_drop_eligibility,

    # Knowledge
    "lookupGlossaryTerm": handle_lookup_glossary_term,

    # Operations
    "getSystemHealth": handle_get_system_health,

    # Forecasting
    "forecastVolume": handle_forecast_volume,

    # Inter-agent
    "sendMessage": handle_send_agent_message,
}
