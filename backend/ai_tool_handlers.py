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
    """Send SMS message via Twilio"""
    # Import Twilio service
    try:
        from integrations.twilio_service import sms_client

        to_number = input_data["to_number"]
        message = input_data["message"]
        lead_id = input_data.get("lead_id")

        # Check if SMS is enabled
        if not sms_client.enabled:
            return {
                "success": False,
                "error": "SMS service not configured"
            }

        # Send SMS
        twilio_sid = await sms_client.send_sms(to_number=to_number, message=message)

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
            "twilio_sid": twilio_sid,
            "message": "SMS sent successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def handle_send_email(input_data: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
    """Send email message"""
    # This would integrate with your email service
    to_email = input_data["to_email"]
    subject = input_data["subject"]
    body = input_data["body"]
    lead_id = input_data.get("lead_id")

    # TODO: Implement actual email sending
    # For now, just log it

    if lead_id:
        from database import SessionLocal
        db = SessionLocal()
        try:
            query = text("""
                INSERT INTO communications (
                    lead_id, type, direction, content, status, created_by
                ) VALUES (
                    :lead_id, 'email', 'outbound', :content, 'sent', :created_by
                )
            """)

            db.execute(query, {
                "lead_id": lead_id,
                "content": f"{subject}\n\n{body}",
                "created_by": context.user_id or 1
            })
            db.commit()
        finally:
            db.close()

    return {
        "success": True,
        "message": "Email sent (simulated)"
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
            "error": str(e)
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
            "error": str(e)
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
    """Classify document type using AI"""
    document_id = input_data["document_id"]
    file_path = input_data.get("file_path", "")

    # TODO: Implement actual document classification using OpenAI Vision
    # For now, return simulated result

    # In production, you would:
    # 1. Load the document
    # 2. Use OpenAI Vision API to analyze
    # 3. Return classification with confidence

    return {
        "success": True,
        "document_id": document_id,
        "document_type": "paystub",  # Simulated
        "confidence": 0.92,
        "extracted_data": {
            "employer": "ABC Company",
            "ytd_income": 45000,
            "pay_period": "2024-01-15 to 2024-01-31"
        }
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

    # Operations
    "getSystemHealth": handle_get_system_health,

    # Forecasting
    "forecastVolume": handle_forecast_volume,

    # Inter-agent
    "sendMessage": handle_send_agent_message,
}
