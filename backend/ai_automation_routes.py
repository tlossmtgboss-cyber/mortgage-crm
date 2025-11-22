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

    # For testing without auth, return demo user
    if not credentials:
        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": "demo@example.com"}
        )
        user_row = result.fetchone()
        if user_row:
            return UserProxy(user_row)
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
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
    """Get company ID for user - placeholder for multi-tenant"""
    # TODO: Get actual company from user or context
    return "00000000-0000-0000-0000-000000000001"


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
    user_id = str(current_user.id)
    company_id = get_company_id_for_user(current_user)
    
    # Check if authorization already exists
    existing = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE user_id = :user_id AND workflow_id = :workflow_id
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
    user_id = str(current_user.id)
    
    result = db.execute(text("""
        SELECT 
            a.authorization_id,
            a.user_id,
            a.workflow_id,
            a.company_id,
            a.task_type_name,
            a.authorization_status,
            a.training_progress_count,
            a.confidence_threshold,
            a.date_authorized,
            a.date_training_completed,
            COUNT(DISTINCT th.task_instance_id) FILTER (
                WHERE th.user_response = 'approved'
            ) as tasks_completed_count,
            CASE 
                WHEN COUNT(DISTINCT th.task_instance_id) > 0 
                THEN COUNT(DISTINCT th.task_instance_id) FILTER (
                    WHERE th.user_response = 'approved'
                ) * 100.0 / COUNT(DISTINCT th.task_instance_id)
                ELSE 0
            END as success_rate,
            AVG(th.ai_confidence_score) FILTER (
                WHERE th.user_response = 'approved'
            ) as avg_confidence,
            MAX(al.timestamp) as last_activity
        FROM ai_task_type_authorizations a
        LEFT JOIN ai_training_history th ON a.authorization_id = th.authorization_id
        LEFT JOIN ai_audit_log al ON a.authorization_id = al.authorization_id
        WHERE a.user_id = :user_id
        GROUP BY a.authorization_id
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
            "tasks_completed_count": int(row.tasks_completed_count or 0),
            "success_rate": float(row.success_rate or 0),
            "avg_confidence": float(row.avg_confidence or 0),
            "last_activity": row.last_activity.isoformat() if row.last_activity else None
        })
    
    return {"authorizations": authorizations}


@router.post("/authorizations/{authorization_id}/revoke")
async def revoke_ai_authorization(
    authorization_id: str,
    revoke_data: RevokeAuthorization,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Revoke AI authorization for a task type"""
    user_id = str(current_user.id)
    
    # Verify authorization exists and belongs to user
    auth = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE authorization_id = :auth_id AND user_id = :user_id
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
        WHERE authorization_id = :auth_id
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
    user_id = str(current_user.id)
    
    db.execute(text("""
        UPDATE ai_task_type_authorizations
        SET authorization_status = 'paused', updated_at = NOW()
        WHERE authorization_id = :auth_id AND user_id = :user_id
    """), {"auth_id": authorization_id, "user_id": user_id})
    
    db.commit()
    
    return {"status": "paused", "message": "AI automation paused"}


@router.post("/authorizations/{authorization_id}/resume")
async def resume_ai_authorization(
    authorization_id: str,
    current_user= Depends(get_current_user), db: Session = Depends(get_db)
):
    """Resume paused AI automation"""
    user_id = str(current_user.id)
    
    # Get current training progress
    auth = db.execute(text("""
        SELECT training_progress_count FROM ai_task_type_authorizations
        WHERE authorization_id = :auth_id AND user_id = :user_id
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
    user_id = str(current_user.id)
    company_id = get_company_id_for_user(current_user)
    
    # Get task and verify it's pending review
    task = db.execute(text("""
        SELECT t.*, a.authorization_id, a.training_progress_count, a.task_type_name
        FROM tasks t
        JOIN ai_task_type_authorizations a ON t.workflow_id = a.workflow_id AND a.user_id = :user_id
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
    user_id = str(current_user.id)
    
    # Build query
    conditions = ["al.user_id = :user_id"]
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
        WHERE user_id = :user_id 
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
        WHERE ct.user_id = :user_id 
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
        WHERE user_id = :user_id
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
    user_id = str(current_user.id)
    date_from = datetime.now() - timedelta(days=days)
    
    # Overall metrics
    overall = db.execute(text("""
        SELECT 
            COUNT(*) as total_tasks,
            COUNT(*) FILTER (WHERE result_status = 'success') as successful_tasks,
            AVG(confidence_score) as avg_confidence,
            SUM(execution_time_ms) / 1000.0 / 3600.0 as total_hours_saved
        FROM ai_audit_log
        WHERE user_id = :user_id 
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
        WHERE al.user_id = :user_id
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
        WHERE user_id = :user_id
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
    user_id = str(current_user.id)
    
    # Verify authorization belongs to user
    auth = db.execute(text("""
        SELECT authorization_id FROM ai_task_type_authorizations
        WHERE authorization_id = :auth_id AND user_id = :user_id
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
    user_id = str(current_user.id)
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
        WHERE authorization_id = :auth_id AND user_id = :user_id
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
    user_id = str(current_user.id)
    
    # Get task
    task = db.execute(text("""
        SELECT * FROM tasks WHERE id = :task_id
    """), {"task_id": task_id}).fetchone()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check for existing authorization
    authorization = db.execute(text("""
        SELECT * FROM ai_task_type_authorizations
        WHERE user_id = :user_id AND workflow_id = :workflow_id
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
