"""
Employee Impersonation Routes
Secure impersonation system for managers to access employee dashboards for training/troubleshooting

Features:
- Read-only and full-access modes
- Audit logging of all actions
- Session management with expiration
- Permission-based access control

Author: System
Date: 2025-11-16
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import secrets
import json

router = APIRouter(prefix="/api/v1/impersonation", tags=["impersonation"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class ImpersonationStartRequest(BaseModel):
    employee_id: int
    mode: str  # 'read_only' or 'full_access'
    reason_category: str  # 'training', 'troubleshooting', 'performance_review', etc.
    reason_notes: Optional[str] = None
    duration_minutes: Optional[int] = 60  # Default 1 hour
    notify_employee: bool = False


class ImpersonationSessionResponse(BaseModel):
    id: int
    session_token: str
    employee_id: int
    employee_name: str
    mode: str
    reason_category: str
    started_at: datetime
    scheduled_end_at: datetime
    actual_end_at: Optional[datetime]
    manager_name: str


class ActiveSessionResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    mode: str
    started_at: datetime
    scheduled_end_at: datetime
    manager_name: str
    time_remaining_minutes: int


class ImpersonationActionLog(BaseModel):
    action_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    action_details: Optional[dict] = {}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_impersonation_permission(manager_id: int, db: Session) -> bool:
    """Check if manager has permission to impersonate employees"""

    # First check if an employee record exists for this user
    employee_result = db.execute(text("""
        SELECT id FROM employees WHERE user_id = :user_id LIMIT 1
    """), {'user_id': manager_id}).fetchone()

    if not employee_result:
        return False

    employee_id = employee_result[0]

    # Then check permission
    result = db.execute(text("""
        SELECT granted
        FROM employee_permissions
        WHERE employee_id = :employee_id
        AND permission_key = 'team.impersonate'
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        LIMIT 1
    """), {'employee_id': employee_id}).fetchone()

    return result and result[0] if result else False


def get_employee_info(employee_id: int, db: Session) -> Optional[dict]:
    """Get employee basic information"""

    result = db.execute(text("""
        SELECT e.id, e.first_name, e.last_name, e.email, u.id as user_id
        FROM employees e
        LEFT JOIN users u ON e.user_id = u.id
        WHERE e.id = :employee_id
        LIMIT 1
    """), {'employee_id': employee_id}).fetchone()

    if not result:
        return None

    return {
        'id': result[0],
        'first_name': result[1],
        'last_name': result[2],
        'email': result[3],
        'user_id': result[4],
        'full_name': f"{result[1]} {result[2]}" if result[1] and result[2] else result[3]
    }


def get_manager_info(manager_id: int, db: Session) -> Optional[dict]:
    """Get manager basic information"""

    result = db.execute(text("""
        SELECT u.id, u.full_name, u.email
        FROM users u
        WHERE u.id = :user_id
        LIMIT 1
    """), {'user_id': manager_id}).fetchone()

    if not result:
        return None

    return {
        'id': result[0],
        'full_name': result[1] or result[2],
        'email': result[2]
    }


# Note: Dependencies will be passed from main.py when router is included
# Example usage in main.py:
#   from impersonation_routes import router as impersonation_router
#   app.include_router(impersonation_router)
