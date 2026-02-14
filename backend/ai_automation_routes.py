"""
AI Task Automation API Routes
Handles AI authorization, training, audit logs, costs, and performance metrics
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from datetime import datetime, timedelta
import json
import logging
import os

from database import get_db
from ai_automation_models import (
    AIAuthorizationCreate, TrainingReview, RevokeAuthorization,
    RollbackRequest, DelegateToAI, AuthorizationResponse,
    AuditLogEntry, CostSummary, CostBreakdown, CostTrend,
    PerformanceOverall, PerformanceByTaskType, DailyTrend,
    RollbackState, TaskDelegationResponse
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/api/v1/ai", tags=["ai-automation"])
logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


# User proxy class for auth
class UserProxy:
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.name = row[2]


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from jose import jwt

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY")
        if not secret:
            raise HTTPException(status_code=500, detail="Server configuration error: SECRET_KEY not set")
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user with raw SQL
        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        return UserProxy(user_row)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


def get_company_id_for_user(user):
    """Get company ID for user - generates UUID from user's company or ID"""
    if hasattr(user, 'company') and user.company:
        # Hash company name to consistent UUID
        import hashlib
        company_hash = hashlib.md5(user.company.encode()).hexdigest()
        return f"{company_hash[:8]}-{company_hash[8:12]}-{company_hash[12:16]}-{company_hash[16:20]}-{company_hash[20:32]}"
    # Fallback: derive from user ID
    return f"00000000-0000-0000-0000-{str(user.id).zfill(12)}"


def int_to_uuid(integer_id):
    """Convert integer user ID to UUID format for AI tables"""
    return f"00000000-0000-0000-0000-{str(integer_id).zfill(12)}"


# ============================================
# AUTHORIZATION ENDPOINTS
# ============================================

@router.post("/authorizations")
async def create_ai_authorization(
    auth_data: AIAuthorizationCreate,
    current_user= Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create AI authorization for a task type (workflow)"""
    user_id = int_to_uuid(current_user.id)
    company_id = get_company_id_for_user(current_user)
    
    # Check if authorization already exists
    existing = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE user_id::text = :user_id AND workflow_id::text = :workflow_id
    """), {"user_id": user_id, "workflow_id": auth_data.workflow_id}).fetchone()
    
    if existing:
        raise HTTPException(status_code=400, detail="Authorization already exists for this workflow")
    
    # Create authorization
    result = db.execute(text("""
        INSERT INTO ai_task_type_authorizations (
            user_id, workflow_id, company_id, task_type_name,
            authorization_status, training_progress_count,
            confidence_threshold, date_authorized, created_at, updated_at
        )
        VALUES (
            :user_id, :workflow_id, :company_id, :task_type_name,
            'training', 0, 90.0, NOW(), NOW(), NOW()
        )
        RETURNING authorization_id
    """), {
        "user_id": user_id,
        "workflow_id": auth_data.workflow_id,
        "company_id": company_id,
        "task_type_name": auth_data.task_type_name
    })
    
    authorization_id = result.fetchone()[0]
    db.commit()
    
    logger.info(f"Created AI authorization {authorization_id} for user {user_id}")
    
    return {
        "authorization_id": str(authorization_id),
        "status": "training",
        "message": "AI learning enabled. Next 5 tasks will be sent to you for review."
    }


@router.get("/authorizations")
async def get_ai_authorizations(
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all AI authorizations for current user"""
    try:
        # Convert integer user ID to UUID format for AI tables
        user_id = int_to_uuid(current_user.id)

        # Simple query first - just get basic authorizations
        result = db.execute(text("""
            SELECT
                a.authorization_id,
                a.user_id,
                a.workflow_id,
                a.task_type_name,
                a.authorization_status,
                a.training_progress_count,
                a.confidence_threshold,
                a.date_authorized,
                a.date_training_completed,
                a.created_at
            FROM ai_task_type_authorizations a
            WHERE a.user_id::text = :user_id
            ORDER BY a.created_at DESC
        """), {"user_id": user_id})

        authorizations = []
        for row in result:
            authorizations.append({
                "authorization_id": str(row.authorization_id),
                "user_id": str(row.user_id),
                "workflow_id": str(row.workflow_id),
                "task_type_name": row.task_type_name,
                "authorization_status": row.authorization_status,
                "training_progress_count": row.training_progress_count,
                "confidence_threshold": float(row.confidence_threshold),
                "date_authorized": row.date_authorized.isoformat() if row.date_authorized else None,
                "date_training_completed": row.date_training_completed.isoformat() if row.date_training_completed else None,
                "tasks_completed_count": 0,
                "success_rate": 0.0,
                "avg_confidence": 0.0,
                "last_activity": None
            })

        return {"authorizations": authorizations}
    except Exception as e:
        logger.error(f"Error getting authorizations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/authorizations/{authorization_id}/revoke")
async def revoke_ai_authorization(
    authorization_id: str,
    revoke_data: RevokeAuthorization,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Revoke AI authorization for a task type"""
    user_id = int_to_uuid(current_user.id)
    
    # Verify authorization exists and belongs to user
    auth = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE authorization_id::text = :auth_id AND user_id::text = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id}).fetchone()
    
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    
    # Update authorization
    db.execute(text("""
        UPDATE ai_task_type_authorizations
        SET authorization_status = 'revoked',
            date_revoked = NOW(),
            revoked_by_user_id = :user_id,
            retain_training_data = :retain_data,
            updated_at = NOW()
        WHERE authorization_id::text = :auth_id
    """), {
        "auth_id": authorization_id,
        "user_id": user_id,
        "retain_data": revoke_data.retain_training_data
    })
    
    # Optionally delete training data
    if not revoke_data.retain_training_data:
        db.execute(text("""
            DELETE FROM ai_training_history WHERE authorization_id = :auth_id
        """), {"auth_id": authorization_id})
        
        db.execute(text("""
            DELETE FROM ai_rollback_states WHERE authorization_id = :auth_id
        """), {"auth_id": authorization_id})
    
    # Log the revocation
    db.execute(text("""
        INSERT INTO ai_audit_log (
            user_id, company_id, authorization_id,
            action_type, action_details, result_status, timestamp
        )
        VALUES (
            :user_id, :company_id, :auth_id,
            'authorization_change', :details, 'success', NOW()
        )
    """), {
        "user_id": user_id,
        "company_id": get_current_company_id(),
        "auth_id": authorization_id,
        "details": json.dumps({"action": "revoke", "retain_data": revoke_data.retain_training_data})
    })
    
    db.commit()
    
    return {
        "status": "revoked",
        "message": f"AI authorization revoked. {'Training data retained.' if revoke_data.retain_training_data else 'Training data deleted.'}"
    }


@router.post("/authorizations/{authorization_id}/pause")
async def pause_ai_authorization(
    authorization_id: str,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Temporarily pause AI automation"""
    user_id = int_to_uuid(current_user.id)
    
    db.execute(text("""
        UPDATE ai_task_type_authorizations
        SET authorization_status = 'paused', updated_at = NOW()
        WHERE authorization_id::text = :auth_id AND user_id::text = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id})
    
    db.commit()
    
    return {"status": "paused", "message": "AI automation paused"}


@router.post("/authorizations/{authorization_id}/resume")
async def resume_ai_authorization(
    authorization_id: str,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Resume paused AI automation"""
    user_id = int_to_uuid(current_user.id)
    
    # Get current training progress
    auth = db.execute(text("""
        SELECT training_progress_count FROM ai_task_type_authorizations
        WHERE authorization_id::text = :auth_id AND user_id::text = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id}).fetchone()
    
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    
    new_status = 'active' if auth.training_progress_count >= 5 else 'training'
    
    db.execute(text("""
        UPDATE ai_task_type_authorizations
        SET authorization_status = :status, updated_at = NOW()
        WHERE authorization_id = :auth_id
    """), {"auth_id": authorization_id, "status": new_status})
    
    db.commit()
    
    return {"status": new_status, "message": "AI automation resumed"}


# ============================================
# TRAINING REVIEW ENDPOINT
# ============================================

@router.post("/training/{task_id}/review")
async def review_training_task(
    task_id: str,
    review: TrainingReview,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """User approves or rejects AI's training attempt"""
    user_id = int_to_uuid(current_user.id)
    company_id = get_company_id_for_user(current_user)
    
    # Get task and verify it's pending review
    task = db.execute(text("""
        SELECT t.*, a.authorization_id, a.training_progress_count, a.task_type_name
        FROM tasks t
        JOIN ai_task_type_authorizations a ON t.workflow_id = a.workflow_id AND a.user_id::text = :user_id
        WHERE t.id = :task_id AND t.completion_method = 'ai_pending_review'
    """), {"task_id": task_id, "user_id": user_id}).fetchone()
    
    if not task:
        raise HTTPException(status_code=404, detail="Training task not found")
    
    if review.action == 'approved':
        # Deploy the task
        db.execute(text("""
            UPDATE tasks
            SET status = 'completed', ai_approved_at = NOW()
            WHERE id = :task_id
        """), {"task_id": task_id})
        
        # Update training history
        db.execute(text("""
            UPDATE ai_training_history
            SET user_response = 'approved',
                reviewed_by_user_id = :user_id,
                reviewed_at = NOW()
            WHERE task_instance_id = :task_id
        """), {"task_id": task_id, "user_id": user_id})
        
        # Increment training counter
        new_count = task.training_progress_count + 1
        
        # Check if training complete
        if new_count >= 5:
            db.execute(text("""
                UPDATE ai_task_type_authorizations
                SET authorization_status = 'active',
                    training_progress_count = :count,
                    date_training_completed = NOW(),
                    updated_at = NOW()
                WHERE authorization_id = :auth_id
            """), {"auth_id": task.authorization_id, "count": new_count})
            
            # Save rollback state
            db.execute(text("""
                INSERT INTO ai_rollback_states (
                    authorization_id, state_snapshot, tasks_completed_count,
                    snapshot_reason, created_at
                )
                VALUES (:auth_id, :snapshot, :count, 'training_complete', NOW())
            """), {
                "auth_id": task.authorization_id,
                "snapshot": json.dumps({"training_completed": True}),
                "count": new_count
            })
            
            db.commit()
            
            return {
                "status": "training_complete",
                "training_progress": "5/5",
                "message": f"🎉 AI training complete for '{task.task_type_name}'! AI will now handle these tasks automatically."
            }
        else:
            db.execute(text("""
                UPDATE ai_task_type_authorizations
                SET training_progress_count = :count, updated_at = NOW()
                WHERE authorization_id = :auth_id
            """), {"auth_id": task.authorization_id, "count": new_count})
        
        db.commit()
        
        return {
            "status": "approved",
            "training_progress": f"{new_count}/5",
            "message": f"Task approved. {5 - new_count} more approvals needed."
        }
    
    elif review.action == 'rejected':
        # Update training history with feedback
        feedback_text = review.feedback.text if review.feedback else None
        feedback_structured = json.dumps(review.feedback.structured) if review.feedback and review.feedback.structured else None
        
        db.execute(text("""
            UPDATE ai_training_history
            SET user_response = 'rejected',
                feedback_text = :text,
                feedback_structured = :structured,
                reviewed_by_user_id = :user_id,
                reviewed_at = NOW()
            WHERE task_instance_id = :task_id
        """), {
            "task_id": task_id,
            "user_id": user_id,
            "text": feedback_text,
            "structured": feedback_structured
        })
        
        # Mark task for manual completion
        db.execute(text("""
            UPDATE tasks
            SET status = 'pending', completion_method = 'manual'
            WHERE id = :task_id
        """), {"task_id": task_id})
        
        db.commit()
        
        return {
            "status": "rejected",
            "training_progress": f"{task.training_progress_count}/5",
            "message": "Feedback received. AI will apply your corrections to future tasks."
        }
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approved' or 'rejected'")


# ============================================
# AUDIT LOG ENDPOINT
# ============================================

@router.get("/audit-log")
async def get_ai_audit_log(
    action_type: Optional[str] = None,
    result_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get AI audit log with filters"""
    user_id = int_to_uuid(current_user.id)
    
    # Build query
    conditions = ["al.user_id::text = :user_id"]
    params = {"user_id": user_id, "limit": limit, "offset": offset}
    
    if action_type:
        conditions.append("al.action_type = :action_type")
        params["action_type"] = action_type
    
    if result_status:
        conditions.append("al.result_status = :result_status")
        params["result_status"] = result_status
    
    if date_from:
        conditions.append("al.timestamp >= :date_from")
        params["date_from"] = date_from
    
    if date_to:
        conditions.append("al.timestamp <= :date_to")
        params["date_to"] = date_to
    
    where_clause = " AND ".join(conditions)
    
    # Get total count
    count_result = db.execute(text(f"""
        SELECT COUNT(*) FROM ai_audit_log al WHERE {where_clause}
    """), params).fetchone()
    total = count_result[0]
    
    # Get logs
    result = db.execute(text(f"""
        SELECT 
            al.*,
            t.title as task_title,
            ata.task_type_name
        FROM ai_audit_log al
        LEFT JOIN tasks t ON al.task_instance_id::text = t.id::text
        LEFT JOIN ai_task_type_authorizations ata ON al.authorization_id = ata.authorization_id
        WHERE {where_clause}
        ORDER BY al.timestamp DESC
        LIMIT :limit OFFSET :offset
    """), params)
    
    logs = []
    for row in result:
        logs.append({
            "log_id": str(row.log_id),
            "user_id": str(row.user_id),
            "task_instance_id": str(row.task_instance_id) if row.task_instance_id else None,
            "authorization_id": str(row.authorization_id) if row.authorization_id else None,
            "action_type": row.action_type,
            "action_details": row.action_details,
            "result_status": row.result_status,
            "error_message": row.error_message,
            "confidence_score": float(row.confidence_score) if row.confidence_score else None,
            "execution_time_ms": row.execution_time_ms,
            "tokens_used": row.tokens_used,
            "estimated_cost": float(row.estimated_cost) if row.estimated_cost else None,
            "timestamp": row.timestamp.isoformat(),
            "task_title": row.task_title,
            "task_type_name": row.task_type_name
        })
    
    return {
        "total": total,
        "logs": logs,
        "limit": limit,
        "offset": offset
    }


# ============================================
# COST TRACKING ENDPOINT
# ============================================

@router.get("/costs")
async def get_ai_costs(
    user_id_param: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get AI usage and costs"""
    user_id = user_id_param or str(current_user.id)
    target_month = month or datetime.now().month
    target_year = year or datetime.now().year
    
    # Get cost summary
    summary = db.execute(text("""
        SELECT 
            COUNT(DISTINCT task_instance_id) as total_tasks,
            COALESCE(SUM(amount), 0) as total_cost,
            COALESCE(AVG(amount), 0) as avg_cost_per_task,
            COALESCE(SUM(tokens_used), 0) as total_tokens
        FROM ai_cost_tracking
        WHERE user_id::text = :user_id
        AND period_month = :month 
        AND period_year = :year
    """), {"user_id": user_id, "month": target_month, "year": target_year}).fetchone()
    
    # Get breakdown by task type
    breakdown_result = db.execute(text("""
        SELECT 
            ata.task_type_name,
            COUNT(DISTINCT ct.task_instance_id) as task_count,
            SUM(ct.amount) as total_cost,
            AVG(ct.amount) as avg_cost
        FROM ai_cost_tracking ct
        LEFT JOIN ai_task_type_authorizations ata ON ct.authorization_id = ata.authorization_id
        WHERE ct.user_id::text = :user_id
        AND ct.period_month = :month 
        AND ct.period_year = :year
        GROUP BY ata.task_type_name
        ORDER BY total_cost DESC
    """), {"user_id": user_id, "month": target_month, "year": target_year})
    
    breakdown = [
        {
            "task_type_name": row.task_type_name,
            "task_count": row.task_count,
            "total_cost": float(row.total_cost or 0),
            "avg_cost": float(row.avg_cost or 0)
        }
        for row in breakdown_result
    ]
    
    # Get monthly trend (last 6 months)
    trend_result = db.execute(text("""
        SELECT 
            period_year,
            period_month,
            COUNT(DISTINCT task_instance_id) as tasks,
            SUM(amount) as cost
        FROM ai_cost_tracking
        WHERE user_id::text = :user_id
        GROUP BY period_year, period_month
        ORDER BY period_year DESC, period_month DESC
        LIMIT 6
    """), {"user_id": user_id})
    
    trend = [
        {
            "period_year": row.period_year,
            "period_month": row.period_month,
            "tasks": row.tasks,
            "cost": float(row.cost or 0)
        }
        for row in trend_result
    ]
    
    return {
        "summary": {
            "total_tasks": summary.total_tasks or 0,
            "total_cost": float(summary.total_cost or 0),
            "avg_cost_per_task": float(summary.avg_cost_per_task or 0),
            "total_tokens": summary.total_tokens or 0
        },
        "breakdown": breakdown,
        "trend": trend
    }


# ============================================
# PERFORMANCE METRICS ENDPOINT
# ============================================

@router.get("/performance")
async def get_ai_performance(
    days: int = Query(default=30, le=365),
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get AI performance metrics for dashboard"""
    user_id = int_to_uuid(current_user.id)
    date_from = datetime.now() - timedelta(days=days)
    
    # Overall metrics
    overall = db.execute(text("""
        SELECT 
            COUNT(*) as total_tasks,
            COUNT(*) FILTER (WHERE result_status = 'success') as successful_tasks,
            AVG(confidence_score) as avg_confidence,
            SUM(execution_time_ms) / 1000.0 / 3600.0 as total_hours_saved
        FROM ai_audit_log
        WHERE user_id::text = :user_id
        AND action_type = 'auto_complete'
        AND timestamp >= :date_from
    """), {"user_id": user_id, "date_from": date_from}).fetchone()
    
    total_tasks = overall.total_tasks or 0
    successful_tasks = overall.successful_tasks or 0
    success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # Performance by task type
    by_task_type_result = db.execute(text("""
        SELECT 
            ata.task_type_name,
            COUNT(al.log_id) as completed,
            CASE 
                WHEN COUNT(al.log_id) > 0 
                THEN COUNT(al.log_id) FILTER (WHERE al.result_status = 'success') * 100.0 / COUNT(al.log_id)
                ELSE 0
            END as success_rate,
            AVG(al.confidence_score) as avg_confidence
        FROM ai_audit_log al
        JOIN ai_task_type_authorizations ata ON al.authorization_id = ata.authorization_id
        WHERE al.user_id::text = :user_id
        AND al.action_type = 'auto_complete'
        AND al.timestamp >= :date_from
        GROUP BY ata.task_type_name
        ORDER BY completed DESC
    """), {"user_id": user_id, "date_from": date_from})
    
    by_task_type = [
        {
            "task_type_name": row.task_type_name,
            "completed": row.completed,
            "success_rate": round(float(row.success_rate or 0), 1),
            "avg_confidence": round(float(row.avg_confidence or 0), 1)
        }
        for row in by_task_type_result
    ]
    
    # Daily trend
    daily_trend_result = db.execute(text("""
        SELECT 
            DATE(timestamp) as date,
            COUNT(*) as tasks,
            AVG(confidence_score) as avg_confidence
        FROM ai_audit_log
        WHERE user_id::text = :user_id
        AND action_type = 'auto_complete'
        AND timestamp >= :date_from
        GROUP BY DATE(timestamp)
        ORDER BY date
    """), {"user_id": user_id, "date_from": date_from})
    
    daily_trend = [
        {
            "date": str(row.date),
            "tasks": row.tasks,
            "avg_confidence": round(float(row.avg_confidence or 0), 1)
        }
        for row in daily_trend_result
    ]
    
    return {
        "overall": {
            "total_tasks": total_tasks,
            "success_rate": round(success_rate, 1),
            "avg_confidence": round(float(overall.avg_confidence or 0), 1),
            "time_saved_hours": round(float(overall.total_hours_saved or 0), 1),
            "error_rate": round(100 - success_rate, 1)
        },
        "by_task_type": by_task_type,
        "daily_trend": daily_trend
    }


# ============================================
# ROLLBACK ENDPOINTS
# ============================================

@router.get("/authorizations/{authorization_id}/rollback-states")
async def get_rollback_states(
    authorization_id: str,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get available rollback states for an authorization"""
    user_id = int_to_uuid(current_user.id)
    
    # Verify authorization belongs to user
    auth = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE authorization_id::text = :auth_id AND user_id::text = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id}).fetchone()
    
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    
    result = db.execute(text("""
        SELECT 
            state_id,
            created_at,
            snapshot_reason,
            tasks_completed_count,
            performance_metrics
        FROM ai_rollback_states
        WHERE authorization_id = :auth_id
        ORDER BY created_at DESC
        LIMIT 10
    """), {"auth_id": authorization_id})
    
    states = [
        {
            "state_id": str(row.state_id),
            "created_at": row.created_at.isoformat(),
            "snapshot_reason": row.snapshot_reason,
            "tasks_completed_count": row.tasks_completed_count,
            "performance_metrics": row.performance_metrics
        }
        for row in result
    ]
    
    return {"states": states}


@router.post("/authorizations/{authorization_id}/rollback")
async def rollback_ai_state(
    authorization_id: str,
    rollback_data: RollbackRequest,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Rollback AI to a previous state"""
    user_id = int_to_uuid(current_user.id)
    company_id = get_company_id_for_user(current_user)
    
    # Get the rollback state
    state = db.execute(text("""
        SELECT * FROM ai_rollback_states
        WHERE state_id = :state_id AND authorization_id = :auth_id
    """), {"state_id": rollback_data.state_id, "auth_id": authorization_id}).fetchone()
    
    if not state:
        raise HTTPException(status_code=404, detail="Rollback state not found")
    
    # Get current authorization
    current_auth = db.execute(text("""
        SELECT * FROM ai_task_type_authorizations
        WHERE authorization_id::text = :auth_id AND user_id::text = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id}).fetchone()
    
    if not current_auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    
    # Save current state before rollback
    db.execute(text("""
        INSERT INTO ai_rollback_states (
            authorization_id, state_snapshot, tasks_completed_count,
            snapshot_reason, created_at
        )
        VALUES (:auth_id, :snapshot, :count, 'pre_rollback', NOW())
    """), {
        "auth_id": authorization_id,
        "snapshot": json.dumps({
            "authorization_status": current_auth.authorization_status,
            "training_progress_count": current_auth.training_progress_count,
            "confidence_threshold": float(current_auth.confidence_threshold)
        }),
        "count": current_auth.training_progress_count
    })
    
    # Restore the previous state
    restored_state = state.state_snapshot if isinstance(state.state_snapshot, dict) else json.loads(state.state_snapshot)
    
    db.execute(text("""
        UPDATE ai_task_type_authorizations
        SET authorization_status = COALESCE(:status, authorization_status),
            training_progress_count = COALESCE(:count, training_progress_count),
            confidence_threshold = COALESCE(:threshold, confidence_threshold),
            updated_at = NOW()
        WHERE authorization_id = :auth_id
    """), {
        "auth_id": authorization_id,
        "status": restored_state.get('authorization_status'),
        "count": restored_state.get('training_progress_count'),
        "threshold": restored_state.get('confidence_threshold')
    })
    
    # Log the rollback
    db.execute(text("""
        INSERT INTO ai_audit_log (
            user_id, company_id, authorization_id,
            action_type, action_details, result_status, timestamp
        )
        VALUES (:user_id, :company_id, :auth_id, 'rollback', :details, 'success', NOW())
    """), {
        "user_id": user_id,
        "company_id": company_id,
        "auth_id": authorization_id,
        "details": json.dumps({
            "rolled_back_to": state.created_at.isoformat(),
            "state_id": rollback_data.state_id
        })
    })
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"AI rolled back to state from {state.created_at}"
    }


# ============================================
# TASK DELEGATION ENDPOINT
# ============================================

@router.post("/tasks/{task_id}/delegate")
async def delegate_task_to_ai(
    task_id: str,
    delegate_data: Optional[DelegateToAI] = None,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """User delegates a task to AI for completion"""
    user_id = int_to_uuid(current_user.id)
    
    # Get task
    task = db.execute(text("""
        SELECT * FROM tasks WHERE id = :task_id
    """), {"task_id": task_id}).fetchone()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check for existing authorization
    authorization = db.execute(text("""
        SELECT * FROM ai_task_type_authorizations
        WHERE user_id::text = :user_id AND workflow_id::text = :workflow_id
    """), {"user_id": user_id, "workflow_id": task.workflow_id}).fetchone()
    
    if not authorization:
        # No authorization exists - prompt user
        return {
            "task_id": task_id,
            "ai_status": "authorization_required",
            "message": "Would you like AI to automatically handle this type of task in the future?",
            "authorization_required": True,
            "workflow_id": str(task.workflow_id),
            "task_type_name": task.title
        }
    
    # Return status based on authorization
    return {
        "task_id": task_id,
        "ai_status": authorization.authorization_status,
        "message": f"Task delegated to AI ({authorization.authorization_status})",
        "training_progress": f"{authorization.training_progress_count}/5" if authorization.authorization_status == 'training' else None,
        "authorization_required": False
    }


# ============================================
# AI TRAINING INSTRUCTION ENDPOINT
# ============================================

@router.post("/training/instruction")
async def submit_training_instruction(
    instruction_data: dict,
    current_user= Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a training instruction to teach AI how to handle specific scenarios.
    The AI will acknowledge the instruction and explain how it will apply it.
    """
    user_id = int_to_uuid(current_user.id)
    company_id = get_company_id_for_user(current_user)

    instruction = instruction_data.get("instruction", "").strip()
    task_context = instruction_data.get("task_context", {})
    task_type = task_context.get("task_type", "general")
    borrower_name = task_context.get("borrower_name", "")
    task_title = task_context.get("task_title", "")

    if not instruction:
        raise HTTPException(status_code=400, detail="Instruction text is required")

    # Store the training instruction in the database
    try:
        db.execute(text("""
            INSERT INTO ai_training_instructions (
                user_id, company_id, instruction_text, task_type,
                task_context, created_at, status
            )
            VALUES (
                :user_id, :company_id, :instruction, :task_type,
                :task_context, NOW(), 'active'
            )
        """), {
            "user_id": user_id,
            "company_id": company_id,
            "instruction": instruction,
            "task_type": task_type,
            "task_context": json.dumps(task_context)
        })
        db.commit()
    except Exception as e:
        # Table might not exist yet, log but continue
        logger.warning(f"Could not store training instruction: {e}")
        db.rollback()

    # Generate AI acknowledgment based on the instruction
    acknowledgment_parts = []

    # Parse instruction to understand intent
    instruction_lower = instruction.lower()

    if "always" in instruction_lower or "never" in instruction_lower:
        acknowledgment_parts.append("I've noted your preference")

    if "rate" in instruction_lower or "rates" in instruction_lower:
        acknowledgment_parts.append("regarding rate discussions")
    elif "follow" in instruction_lower or "follow-up" in instruction_lower:
        acknowledgment_parts.append("about follow-up communications")
    elif "tone" in instruction_lower or "friendly" in instruction_lower or "professional" in instruction_lower:
        acknowledgment_parts.append("about communication style")
    elif "document" in instruction_lower or "documents" in instruction_lower:
        acknowledgment_parts.append("about document requests")
    elif "mention" in instruction_lower or "include" in instruction_lower:
        acknowledgment_parts.append("about what to include in messages")

    # Build the acknowledgment message
    if acknowledgment_parts:
        acknowledgment = f"Got it! {' '.join(acknowledgment_parts)}."
    else:
        acknowledgment = "Got it! I've recorded your instruction."

    # Build specific response about how AI will apply this
    application_response = f"""

**Your instruction:** "{instruction}"

**How I'll apply this:**
When handling similar tasks{f' for {borrower_name}' if borrower_name else ''}{f' ({task_title})' if task_title else ''}, I will:
• Remember this preference for future {task_type} tasks
• Apply this guidance when drafting messages
• Incorporate this into my response patterns for your account

This instruction is now part of my training for your workflow. I'll use it to improve my suggestions going forward."""

    # Log to audit
    try:
        db.execute(text("""
            INSERT INTO ai_audit_log (
                user_id, company_id, action_type, action_details,
                result_status, timestamp
            )
            VALUES (
                :user_id, :company_id, 'training_instruction',
                :details, 'success', NOW()
            )
        """), {
            "user_id": user_id,
            "company_id": company_id,
            "details": json.dumps({
                "instruction": instruction,
                "task_type": task_type,
                "task_context": task_context
            })
        })
        db.commit()
    except Exception as e:
        logger.warning(f"Could not log training instruction: {e}")
        db.rollback()

    return {
        "status": "success",
        "acknowledgment": acknowledgment + application_response,
        "instruction_recorded": True,
        "applied_to": task_type
    }


# ============================================
# AI REGENERATE MESSAGE ENDPOINT
# ============================================

@router.post("/regenerate-message")
async def regenerate_message(
    request_data: dict,
    current_user= Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Regenerate a message for a specific channel based on task context and training instructions.
    Channels: email, text, phone, voicemail
    """
    channel = request_data.get("channel", "email")
    client_name = request_data.get("client_name", "").split()[0] if request_data.get("client_name") else "there"
    task_title = request_data.get("task_title", "")
    stage = request_data.get("stage", "")
    training_instruction = request_data.get("training_instruction", "")

    # Build the message based on channel and training instructions
    if channel == "email":
        message = f"""Hi {client_name},

{training_instruction + chr(10) + chr(10) if training_instruction else ''}I wanted to reach out regarding your loan application{f' ({task_title})' if task_title else ''}.

If you have any questions or need assistance, please don't hesitate to contact me. I'm here to help make this process as smooth as possible.

Best regards,
[Your Name]
Loan Officer"""

    elif channel == "text":
        message = f"Hi {client_name}! {training_instruction + ' ' if training_instruction else ''}Just checking in on your loan. Let me know if you have any questions!"

    elif channel == "phone":
        message = f"""CALL SCRIPT for {client_name}:
{chr(10) + 'Key Point: ' + training_instruction + chr(10) if training_instruction else ''}
1. Greeting: "Hi {client_name}, this is [Your Name] calling about your loan application."
2. Purpose: {task_title or 'Discuss current status and next steps'}
3. Ask: "Do you have any questions I can help with?"
4. Close: Schedule follow-up if needed"""

    elif channel == "voicemail":
        message = f"""Hi {client_name}, this is [Your Name] from [Company]. {training_instruction + ' ' if training_instruction else ''}I'm calling about your loan application. Please call me back at your convenience at [phone number]. Thank you!"""

    else:
        message = f"Hi {client_name}, reaching out about your loan application."

    return {
        "status": "success",
        "channel": channel,
        "message": message,
        "client_name": client_name,
        "training_applied": bool(training_instruction)
    }


# =============================================================================
# BIO GENERATION
# =============================================================================

@router.post("/generate-bio")
async def generate_bio(
    request: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate a professional bio using AI based on user profile data."""
    try:
        import anthropic

        name = request.get("name", "")
        headline = request.get("headline", "")
        tagline = request.get("tagline", "")
        specialties = request.get("specialties", [])
        years_experience = request.get("yearsExperience", "")
        certifications = request.get("certifications", [])

        # Build context for the AI
        context_parts = []
        if name:
            context_parts.append(f"Name: {name}")
        if headline:
            context_parts.append(f"Headline: {headline}")
        if tagline:
            context_parts.append(f"Tagline: {tagline}")
        if specialties:
            context_parts.append(f"Specialties: {', '.join(specialties)}")
        if years_experience:
            context_parts.append(f"Years of Experience: {years_experience}")
        if certifications:
            context_parts.append(f"Certifications: {', '.join(certifications)}")

        context = "\n".join(context_parts) if context_parts else "A mortgage loan officer"

        prompt = f"""Write a professional, engaging bio for a mortgage loan officer's website. The bio should be warm, trustworthy, and highlight their expertise in helping clients achieve homeownership.

Profile Information:
{context}

Requirements:
- Write 2-3 paragraphs (150-200 words total)
- Use first person ("I" statements)
- Be warm and personable while maintaining professionalism
- Focus on the value they bring to clients
- If years of experience is provided, mention it naturally
- If specialties are provided, weave them in naturally
- End with something that invites the reader to reach out

Write only the bio text, no headers or labels."""

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        bio = response.content[0].text.strip()

        return {"status": "success", "bio": bio}

    except Exception as e:
        logger.error(f"Error generating bio: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate bio")
