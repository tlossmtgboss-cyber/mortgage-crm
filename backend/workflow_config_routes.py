"""
Workflow Configuration API Routes
Provides endpoints for managing workflow configurations:
- CRUD operations for workflow configs
- Day management (add, edit, delete)
- Communication method toggling
- Role/user assignment
- Task health monitoring
- Broken task alert handling
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import Optional, List, Dict
from datetime import datetime, timezone
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow-config", tags=["Workflow Configuration"])
security = HTTPBearer(auto_error=False)


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================

class DayConfigCreate(BaseModel):
    day_label: str
    day_value: int
    day_order: Optional[int] = None  # If not provided, will be auto-calculated
    phone_enabled: bool = False
    phone_am_enabled: bool = False  # AM Phone (Lead Purchase workflow)
    phone_pm_enabled: bool = False  # PM Phone (Lead Purchase workflow)
    text_enabled: bool = False
    text_am_enabled: bool = False   # AM Text (Lead Purchase workflow)
    text_pm_enabled: bool = False   # PM Text (Lead Purchase workflow)
    email_enabled: bool = False
    referral_partner_enabled: bool = False
    # Legacy fields - kept for backwards compatibility
    lo_responsible: bool = False
    jr_lo_responsible: bool = False
    production_asst_responsible: bool = False
    concierge_responsible: bool = False
    ai_responsible: bool = False
    # Dynamic role responsibilities - format: {role_id: true/false}
    role_responsibilities: Optional[Dict[str, bool]] = None
    task_description: Optional[str] = None
    # Weekly recurring task settings
    repeat_weekly: bool = False
    repeat_day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    repeat_until_status: Optional[List[str]] = None  # e.g., ['closed', 'canceled', 'withdrawn', 'denied']


class DayConfigUpdate(BaseModel):
    day_label: Optional[str] = None
    day_value: Optional[int] = None
    phone_enabled: Optional[bool] = None
    phone_am_enabled: Optional[bool] = None  # AM Phone (Lead Purchase workflow)
    phone_pm_enabled: Optional[bool] = None  # PM Phone (Lead Purchase workflow)
    text_enabled: Optional[bool] = None
    text_am_enabled: Optional[bool] = None   # AM Text (Lead Purchase workflow)
    text_pm_enabled: Optional[bool] = None   # PM Text (Lead Purchase workflow)
    email_enabled: Optional[bool] = None
    referral_partner_enabled: Optional[bool] = None
    # Legacy fields - kept for backwards compatibility
    lo_responsible: Optional[bool] = None
    jr_lo_responsible: Optional[bool] = None
    production_asst_responsible: Optional[bool] = None
    concierge_responsible: Optional[bool] = None
    ai_responsible: Optional[bool] = None
    # Dynamic role responsibilities - format: {role_id: true/false}
    role_responsibilities: Optional[Dict[str, bool]] = None
    is_active: Optional[bool] = None
    task_description: Optional[str] = None
    # Weekly recurring task settings
    repeat_weekly: Optional[bool] = None
    repeat_day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    repeat_until_status: Optional[List[str]] = None  # e.g., ['closed', 'canceled', 'withdrawn', 'denied']


class RoleAssignmentCreate(BaseModel):
    # Legacy: use 'role' for enum-based role (backwards compat)
    role: Optional[str] = None  # loan_officer, junior_loan_officer, production_assistant, ai
    # New: use 'role_id' for dynamic role from Role table
    role_id: Optional[int] = None
    user_id: Optional[int] = None


class RoleAssignmentUpdate(BaseModel):
    user_id: Optional[int] = None
    is_active: Optional[bool] = None


class WorkflowConfigResponse(BaseModel):
    id: int
    workflow_key: str
    workflow_name: str
    description: Optional[str]
    objective: Optional[str]
    statuses_impacted: Optional[List[str]]
    color: Optional[str]
    is_active: bool
    days: List[dict]
    role_assignments: List[dict]
    task_count: int
    healthy_count: int
    broken_count: int


# =============================================================================
# Dependency Injection
# =============================================================================

_get_db = None
_get_current_user = None
_models = None


from db import get_db


def set_dependencies(db_dep, user_dep, models):
    """Set dependencies from main app"""
    global _get_db, _get_current_user, _models
    _get_db = db_dep
    _get_current_user = user_dep
    _models = models


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# Workflow Configuration Endpoints
# =============================================================================

@router.get("/workflows")
async def get_all_workflow_configs(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all workflow configurations with summary stats"""
    if _models is None:
        logger.warning("Workflow models not initialized - returning empty list")
        return {'workflows': []}

    try:
        WorkflowConfiguration = _models['WorkflowConfiguration']
        WorkflowDayConfig = _models['WorkflowDayConfig']

        workflows = db.query(WorkflowConfiguration).order_by(WorkflowConfiguration.workflow_key).all()

        result = []
        for wf in workflows:
            # Count tasks and health status
            day_count = len(wf.days) if wf.days else 0
            healthy = sum(1 for d in (wf.days or []) if d.health_status.value == 'healthy')
            broken = sum(1 for d in (wf.days or []) if d.health_status.value == 'broken')

            result.append({
                'id': wf.id,
                'workflow_key': wf.workflow_key,
                'workflow_name': wf.workflow_name,
                'description': wf.description,
                'objective': wf.objective,
                'statuses_impacted': wf.statuses_impacted or [],
                'color': wf.color,
                'is_active': wf.is_active,
                'day_count': day_count,
                'healthy_count': healthy,
                'broken_count': broken
            })

        return {'workflows': result}
    except Exception as e:
        logger.warning(f"Error fetching workflows (table may not exist): {e}")
        return {'workflows': []}


@router.get("/workflows/{workflow_key}")
async def get_workflow_config(
    workflow_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a specific workflow configuration with all days and role assignments"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Build days list
    days = []
    for day in sorted(workflow.days or [], key=lambda x: x.day_order):
        days.append({
            'id': day.id,
            'day_label': day.day_label,
            'day_order': day.day_order,
            'day_value': day.day_value,
            'phone_enabled': day.phone_enabled,
            'phone_am_enabled': getattr(day, 'phone_am_enabled', False),
            'phone_pm_enabled': getattr(day, 'phone_pm_enabled', False),
            'text_enabled': day.text_enabled,
            'text_am_enabled': getattr(day, 'text_am_enabled', False),
            'text_pm_enabled': getattr(day, 'text_pm_enabled', False),
            'email_enabled': day.email_enabled,
            'referral_partner_enabled': day.referral_partner_enabled,
            # Legacy fields
            'lo_responsible': day.lo_responsible,
            'jr_lo_responsible': day.jr_lo_responsible,
            'production_asst_responsible': day.production_asst_responsible,
            'concierge_responsible': getattr(day, 'concierge_responsible', False),
            'ai_responsible': day.ai_responsible,
            # Dynamic role responsibilities
            'role_responsibilities': getattr(day, 'role_responsibilities', {}) or {},
            'health_status': day.health_status.value if day.health_status else 'healthy',
            'health_message': day.health_message,
            'is_active': day.is_active,
            'task_description': day.task_description,
            # Weekly recurring task settings
            'repeat_weekly': getattr(day, 'repeat_weekly', False),
            'repeat_day_of_week': getattr(day, 'repeat_day_of_week', None),
            'repeat_until_status': getattr(day, 'repeat_until_status', None) or []
        })

    # Build role assignments list
    role_assignments = []
    for ra in workflow.role_assignments or []:
        user_name = None
        if ra.user_id and ra.user:
            user_name = ra.user.full_name or ra.user.email

        # Handle both legacy enum roles and new dynamic roles
        role_name = None
        role_id = None
        if hasattr(ra, 'role_id') and ra.role_id:
            role_id = ra.role_id
            # Get role name from dynamic_role relationship
            if hasattr(ra, 'dynamic_role') and ra.dynamic_role:
                role_name = ra.dynamic_role.name
        elif ra.role:
            # Legacy enum-based role
            role_name = ra.role.value if hasattr(ra.role, 'value') else str(ra.role)

        role_assignments.append({
            'id': ra.id,
            'role': role_name,  # Legacy field for backwards compatibility
            'role_id': role_id,  # New dynamic role ID
            'role_name': role_name,  # Display name
            'user_id': ra.user_id,
            'user_name': user_name,
            'is_active': ra.is_active
        })

    return {
        'id': workflow.id,
        'workflow_key': workflow.workflow_key,
        'workflow_name': workflow.workflow_name,
        'description': workflow.description,
        'objective': workflow.objective,
        'statuses_impacted': workflow.statuses_impacted or [],
        'color': workflow.color,
        'is_active': workflow.is_active,
        'days': days,
        'role_assignments': role_assignments,
        'task_count': len(days),
        'healthy_count': sum(1 for d in days if d['health_status'] == 'healthy'),
        'broken_count': sum(1 for d in days if d['health_status'] == 'broken')
    }


# =============================================================================
# Day Configuration Endpoints
# =============================================================================

@router.post("/workflows/{workflow_key}/days")
async def add_day_config(
    workflow_key: str,
    day_config: DayConfigCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a new day to a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Get max order
    max_order = db.query(func.max(WorkflowDayConfig.day_order)).filter(
        WorkflowDayConfig.workflow_id == workflow.id
    ).scalar() or 0

    new_day = WorkflowDayConfig(
        workflow_id=workflow.id,
        day_label=day_config.day_label,
        day_order=max_order + 1,
        day_value=day_config.day_value,
        phone_enabled=day_config.phone_enabled,
        text_enabled=day_config.text_enabled,
        email_enabled=day_config.email_enabled,
        referral_partner_enabled=day_config.referral_partner_enabled,
        # Legacy fields
        lo_responsible=day_config.lo_responsible,
        jr_lo_responsible=day_config.jr_lo_responsible,
        production_asst_responsible=day_config.production_asst_responsible,
        concierge_responsible=day_config.concierge_responsible,
        ai_responsible=day_config.ai_responsible,
        # Dynamic role responsibilities
        role_responsibilities=day_config.role_responsibilities or {},
        task_description=day_config.task_description
    )

    db.add(new_day)
    db.commit()
    db.refresh(new_day)

    return {
        'success': True,
        'day': {
            'id': new_day.id,
            'day_label': new_day.day_label,
            'day_order': new_day.day_order,
            'day_value': new_day.day_value,
            'phone_enabled': new_day.phone_enabled,
            'text_enabled': new_day.text_enabled,
            'email_enabled': new_day.email_enabled,
            'referral_partner_enabled': new_day.referral_partner_enabled,
            'lo_responsible': new_day.lo_responsible,
            'jr_lo_responsible': new_day.jr_lo_responsible,
            'production_asst_responsible': new_day.production_asst_responsible,
            'concierge_responsible': new_day.concierge_responsible,
            'ai_responsible': new_day.ai_responsible,
            'role_responsibilities': new_day.role_responsibilities or {},
            'health_status': 'healthy',
            'health_message': None,
            'task_description': new_day.task_description
        }
    }


@router.put("/workflows/{workflow_key}/days/{day_id}")
async def update_day_config(
    workflow_key: str,
    day_id: int,
    day_update: DayConfigUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a day configuration"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    day = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.id == day_id,
        WorkflowDayConfig.workflow_id == workflow.id
    ).first()

    if not day:
        raise HTTPException(status_code=404, detail=f"Day config {day_id} not found")

    # Update fields that were provided
    _protected = {'id', 'workflow_id', 'organization_id', 'created_at', 'updated_at'}
    update_data = day_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and field not in _protected:
            setattr(day, field, value)

    day.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {'success': True, 'message': 'Day configuration updated'}


@router.delete("/workflows/{workflow_key}/days/{day_id}")
async def delete_day_config(
    workflow_key: str,
    day_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a day from a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']
    BrokenTaskAlert = _models['BrokenTaskAlert']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    day = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.id == day_id,
        WorkflowDayConfig.workflow_id == workflow.id
    ).first()

    if not day:
        raise HTTPException(status_code=404, detail=f"Day config {day_id} not found")

    # Delete related alerts first (to avoid foreign key constraint)
    db.query(BrokenTaskAlert).filter(
        BrokenTaskAlert.day_config_id == day_id
    ).delete()

    db.delete(day)

    # Reorder remaining days
    remaining_days = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.workflow_id == workflow.id
    ).order_by(WorkflowDayConfig.day_order).all()

    for idx, d in enumerate(remaining_days, 1):
        d.day_order = idx

    db.commit()

    return {'success': True, 'message': 'Day deleted'}


@router.put("/workflows/{workflow_key}/days/reorder")
async def reorder_days(
    workflow_key: str,
    day_ids: List[int],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reorder days in a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    for order, day_id in enumerate(day_ids, 1):
        day = db.query(WorkflowDayConfig).filter(
            WorkflowDayConfig.id == day_id,
            WorkflowDayConfig.workflow_id == workflow.id
        ).first()
        if day:
            day.day_order = order

    db.commit()

    return {'success': True, 'message': 'Days reordered'}


# =============================================================================
# Role Assignment Endpoints
# =============================================================================

@router.get("/workflows/{workflow_key}/roles")
async def get_role_assignments(
    workflow_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get role assignments for a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    assignments = []
    for ra in workflow.role_assignments or []:
        user_name = None
        user_email = None
        if ra.user_id and ra.user:
            user_name = ra.user.full_name
            user_email = ra.user.email
        assignments.append({
            'id': ra.id,
            'role': ra.role.value if hasattr(ra.role, 'value') else ra.role,
            'user_id': ra.user_id,
            'user_name': user_name,
            'user_email': user_email,
            'is_active': ra.is_active
        })

    return {'role_assignments': assignments}


@router.post("/workflows/{workflow_key}/roles")
async def add_role_assignment(
    workflow_key: str,
    assignment: RoleAssignmentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a new role assignment to a workflow.

    Supports both legacy enum roles (via 'role' field) and dynamic roles (via 'role_id').
    When role_id is provided, it uses the dynamic Role table.
    When role is provided (without role_id), it falls back to the legacy enum.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Handle dynamic role (new approach)
    if assignment.role_id:
        # Verify role exists using raw SQL
        role_result = db.execute(text("""
            SELECT id, name FROM onboarding_roles
            WHERE id = :role_id AND is_active = true
        """), {'role_id': assignment.role_id}).first()

        if not role_result:
            raise HTTPException(status_code=404, detail=f"Role with ID {assignment.role_id} not found")

        role_name = role_result.name

        # Check if role already exists for this workflow
        existing = db.query(WorkflowRoleAssignment).filter(
            WorkflowRoleAssignment.workflow_id == workflow.id,
            WorkflowRoleAssignment.role_id == assignment.role_id
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail=f"Role '{role_name}' already exists for this workflow")

        new_assignment = WorkflowRoleAssignment(
            workflow_id=workflow.id,
            role_id=assignment.role_id,
            user_id=assignment.user_id
        )
    # Handle legacy enum role
    elif assignment.role:
        from workflow_config_models import TaskResponsibility

        try:
            role_enum = TaskResponsibility(assignment.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {assignment.role}")

        # Check if role already exists
        existing = db.query(WorkflowRoleAssignment).filter(
            WorkflowRoleAssignment.workflow_id == workflow.id,
            WorkflowRoleAssignment.role == role_enum
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail=f"Role {assignment.role} already exists for this workflow")

        new_assignment = WorkflowRoleAssignment(
            workflow_id=workflow.id,
            role=role_enum,
            user_id=assignment.user_id
        )
    else:
        raise HTTPException(status_code=400, detail="Either 'role' or 'role_id' must be provided")

    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    return {'success': True, 'assignment_id': new_assignment.id}


@router.put("/workflows/{workflow_key}/roles/{role_id}")
async def update_role_assignment(
    workflow_key: str,
    role_id: int,
    update: RoleAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a role assignment (assign/change user)"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    assignment = db.query(WorkflowRoleAssignment).filter(
        WorkflowRoleAssignment.id == role_id,
        WorkflowRoleAssignment.workflow_id == workflow.id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail=f"Role assignment {role_id} not found")

    if update.user_id is not None:
        assignment.user_id = update.user_id
    if update.is_active is not None:
        assignment.is_active = update.is_active

    assignment.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {'success': True, 'message': 'Role assignment updated'}


@router.delete("/workflows/{workflow_key}/roles/{role_id}")
async def delete_role_assignment(
    workflow_key: str,
    role_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a role assignment"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    assignment = db.query(WorkflowRoleAssignment).filter(
        WorkflowRoleAssignment.id == role_id,
        WorkflowRoleAssignment.workflow_id == workflow.id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail=f"Role assignment {role_id} not found")

    db.delete(assignment)
    db.commit()

    return {'success': True, 'message': 'Role assignment deleted'}


# =============================================================================
# Task Health Endpoints
# =============================================================================

@router.get("/workflows/{workflow_key}/health")
async def get_workflow_health(
    workflow_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get health status of all tasks in a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    health_summary = {
        'total': 0,
        'healthy': 0,
        'broken': 0,
        'disabled': 0,
        'issues': []
    }

    for day in workflow.days or []:
        health_summary['total'] += 1
        status = day.health_status.value if day.health_status else 'healthy'

        if status == 'healthy':
            health_summary['healthy'] += 1
        elif status == 'broken':
            health_summary['broken'] += 1
            health_summary['issues'].append({
                'day_id': day.id,
                'day_label': day.day_label,
                'message': day.health_message or 'Unknown issue'
            })
        elif status == 'disabled':
            health_summary['disabled'] += 1

    return health_summary


@router.post("/workflows/{workflow_key}/days/{day_id}/check-health")
async def check_day_health(
    workflow_key: str,
    day_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Run health check on a specific day configuration"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']
    BrokenTaskAlert = _models['BrokenTaskAlert']

    from workflow_config_models import TaskHealthStatus

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    day = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.id == day_id,
        WorkflowDayConfig.workflow_id == workflow.id
    ).first()

    if not day:
        raise HTTPException(status_code=404, detail=f"Day config {day_id} not found")

    # Run health checks
    issues = []

    # Check 1: At least one communication method enabled
    if not any([day.phone_enabled, day.text_enabled, day.email_enabled, day.referral_partner_enabled]):
        issues.append("No communication method enabled")

    # Check 2: At least one responsible party assigned
    concierge_resp = getattr(day, 'concierge_responsible', False)
    if not any([day.lo_responsible, day.jr_lo_responsible, day.production_asst_responsible, concierge_resp, day.ai_responsible]):
        issues.append("No responsible party assigned")

    # Check 3: If role is responsible, verify user is assigned
    role_assignments = {
        ra.role.value if hasattr(ra.role, 'value') else ra.role: ra
        for ra in (workflow.role_assignments or [])
    }

    if day.lo_responsible and 'loan_officer' not in role_assignments:
        issues.append("LO responsible but no user assigned to LO role")
    if day.jr_lo_responsible and 'junior_loan_officer' not in role_assignments:
        issues.append("Jr. LO responsible but no user assigned to Jr. LO role")
    if day.production_asst_responsible and 'production_assistant' not in role_assignments:
        issues.append("Production Asst. responsible but no user assigned")
    if concierge_resp and 'concierge' not in role_assignments:
        issues.append("Concierge responsible but no user assigned to Concierge role")

    # Update health status
    if issues:
        day.health_status = TaskHealthStatus.BROKEN
        day.health_message = "; ".join(issues)

        # Create alert record for broken task
        alert = BrokenTaskAlert(
            workflow_id=workflow.id,
            day_config_id=day.id,
            alert_type='config_error',
            alert_message="; ".join(issues),
            severity='high'
        )
        db.add(alert)
        logger.warning(f"Health check failed for {workflow.workflow_name} - {day.day_label}: {issues}")
    else:
        day.health_status = TaskHealthStatus.HEALTHY
        day.health_message = None

    day.last_health_check = datetime.now(timezone.utc)
    db.commit()

    return {
        'day_id': day_id,
        'health_status': day.health_status.value,
        'issues': issues,
        'checked_at': day.last_health_check.isoformat()
    }


# =============================================================================
# Broken Task Alerts Endpoints
# =============================================================================

@router.get("/alerts")
async def get_broken_task_alerts(
    resolved: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all broken task alerts"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    BrokenTaskAlert = _models['BrokenTaskAlert']

    query = db.query(BrokenTaskAlert)
    if not resolved:
        query = query.filter(BrokenTaskAlert.is_resolved == False)

    alerts = query.order_by(BrokenTaskAlert.created_at.desc()).all()

    result = []
    for alert in alerts:
        result.append({
            'id': alert.id,
            'workflow_id': alert.workflow_id,
            'workflow_name': alert.workflow.workflow_name if alert.workflow else None,
            'day_config_id': alert.day_config_id,
            'day_label': alert.day_config.day_label if alert.day_config else None,
            'alert_type': alert.alert_type,
            'alert_message': alert.alert_message,
            'severity': alert.severity,
            'admin_task_id': alert.admin_task_id,
            'is_resolved': alert.is_resolved,
            'created_at': alert.created_at.isoformat()
        })

    return {'alerts': result}


@router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark an alert as resolved"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    BrokenTaskAlert = _models['BrokenTaskAlert']

    alert = db.query(BrokenTaskAlert).filter(BrokenTaskAlert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by_id = current_user.id
    db.commit()

    return {'success': True, 'message': 'Alert resolved'}


# =============================================================================
# Seed/Initialize Default Workflows
# =============================================================================

@router.post("/seed")
async def seed_default_workflows(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Seed database with default workflow configurations"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    from workflow_config_models import DEFAULT_WORKFLOW_CONFIGS, TaskHealthStatus

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    created = 0
    for key, config in DEFAULT_WORKFLOW_CONFIGS.items():
        # Check if workflow already exists
        existing = db.query(WorkflowConfiguration).filter(
            WorkflowConfiguration.workflow_key == key
        ).first()

        if existing:
            continue

        # Create workflow
        workflow = WorkflowConfiguration(
            workflow_key=key,
            workflow_name=config['name'],
            description=config['description'],
            objective=config['objective'],
            statuses_impacted=config['statuses_impacted'],
            color=config['color']
        )
        db.add(workflow)
        db.flush()  # Get ID

        # Create day configs
        for day_data in config.get('days', []):
            day = WorkflowDayConfig(
                workflow_id=workflow.id,
                day_label=day_data['label'],
                day_order=day_data['order'],
                day_value=day_data['value'],
                phone_enabled=day_data.get('phone', False),
                text_enabled=day_data.get('text', False),
                email_enabled=day_data.get('email', False),
                referral_partner_enabled=day_data.get('partner', False),
                lo_responsible=day_data.get('lo', False),
                jr_lo_responsible=day_data.get('jr_lo', False),
                production_asst_responsible=day_data.get('pa', False),
                concierge_responsible=day_data.get('concierge', False),
                ai_responsible=day_data.get('ai', False),
                health_status=TaskHealthStatus.HEALTHY
            )
            db.add(day)

        created += 1

    db.commit()

    return {'success': True, 'workflows_created': created}


@router.post("/reseed/{workflow_key}")
async def reseed_workflow(
    workflow_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Delete and recreate a specific workflow from DEFAULT_WORKFLOW_CONFIGS.
    Useful for updating workflow configurations.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    from workflow_config_models import DEFAULT_WORKFLOW_CONFIGS, TaskHealthStatus

    if workflow_key not in DEFAULT_WORKFLOW_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found in defaults")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    # Delete existing workflow and its days (cascade delete should handle days)
    existing = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if existing:
        # Delete day configs first
        db.query(WorkflowDayConfig).filter(
            WorkflowDayConfig.workflow_id == existing.id
        ).delete()
        # Delete workflow
        db.delete(existing)
        db.flush()

    # Create fresh workflow from defaults
    config = DEFAULT_WORKFLOW_CONFIGS[workflow_key]
    workflow = WorkflowConfiguration(
        workflow_key=workflow_key,
        workflow_name=config['name'],
        description=config['description'],
        objective=config['objective'],
        statuses_impacted=config['statuses_impacted'],
        color=config['color']
    )
    db.add(workflow)
    db.flush()

    # Create day configs
    days_created = 0
    for day_data in config.get('days', []):
        day = WorkflowDayConfig(
            workflow_id=workflow.id,
            day_label=day_data['label'],
            day_order=day_data['order'],
            day_value=day_data['value'],
            phone_enabled=day_data.get('phone', False),
            text_enabled=day_data.get('text', False),
            email_enabled=day_data.get('email', False),
            referral_partner_enabled=day_data.get('partner', False),
            lo_responsible=day_data.get('lo', False),
            jr_lo_responsible=day_data.get('jr_lo', False),
            production_asst_responsible=day_data.get('pa', False),
            concierge_responsible=day_data.get('concierge', False),
            ai_responsible=day_data.get('ai', False),
            health_status=TaskHealthStatus.HEALTHY
        )
        db.add(day)
        days_created += 1

    db.commit()

    return {
        'success': True,
        'workflow_key': workflow_key,
        'workflow_id': workflow.id,
        'days_created': days_created,
        'message': f"Workflow '{workflow_key}' reseeded with {days_created} days"
    }


# =============================================================================
# User List for Role Assignment
# =============================================================================

@router.get("/users")
async def get_users_for_assignment(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get list of users that can be assigned to workflow roles"""
    from database.models import User

    query = db.query(User).filter(User.is_active == True)

    if role:
        # Filter by role if specified
        query = query.filter(User.role == role)

    users = query.order_by(User.full_name).all()

    return {
        'users': [
            {
                'id': u.id,
                'email': u.email,
                'full_name': u.full_name,
                'role': u.role
            }
            for u in users
        ]
    }


# =============================================================================
# Dynamic Roles Endpoints
# =============================================================================

@router.get("/available-roles")
async def get_available_roles(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all available roles from the onboarding_roles table for workflow configuration.

    These are the admin-created roles that can be assigned to workflows.
    Returns roles with their IDs and names.
    """
    # Use raw SQL to query onboarding_roles table to avoid model import issues
    # Note: Table is onboarding_roles (not roles) - do not change this
    table_name = "onboarding_roles"
    result = db.execute(text(f"""
        SELECT id, name, description
        FROM {table_name}
        WHERE is_active = true
        ORDER BY name
    """))

    roles = []
    for row in result:
        roles.append({
            'id': row.id,
            'name': row.name,
            'description': row.description
        })

    return {'roles': roles}


@router.post("/workflows/{workflow_key}/sync-roles")
async def sync_workflow_roles(
    workflow_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Sync workflow role assignments with available roles from onboarding_roles table.

    For each role in the Role table, creates a workflow role assignment if it doesn't exist.
    This allows admin-created roles to automatically appear in workflow configurations.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Get all active roles using raw SQL
    role_result = db.execute(text("""
        SELECT id FROM onboarding_roles WHERE is_active = true
    """))
    role_ids = [row.id for row in role_result]

    # Get existing role assignments for this workflow
    existing_role_ids = set()
    for ra in workflow.role_assignments or []:
        if hasattr(ra, 'role_id') and ra.role_id:
            existing_role_ids.add(ra.role_id)

    # Create assignments for any missing roles
    created = 0
    for role_id in role_ids:
        if role_id not in existing_role_ids:
            new_assignment = WorkflowRoleAssignment(
                workflow_id=workflow.id,
                role_id=role_id,
                user_id=None  # No user assigned yet
            )
            db.add(new_assignment)
            created += 1

    db.commit()

    return {
        'success': True,
        'message': f'Synced {created} new role assignments for workflow {workflow_key}',
        'created_count': created
    }


@router.post("/sync-all-workflow-roles")
async def sync_all_workflow_roles(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Sync all workflows with available roles from onboarding_roles table.

    Iterates through all workflows and ensures each has role assignments for all
    admin-created roles. This is useful after creating new roles to populate them
    across all workflows.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    # Get all active role IDs using raw SQL
    role_result = db.execute(text("""
        SELECT id FROM onboarding_roles WHERE is_active = true
    """))
    role_ids = [row.id for row in role_result]

    # Get all workflows
    workflows = db.query(WorkflowConfiguration).all()

    total_created = 0

    for workflow in workflows:
        # Get existing role assignments for this workflow
        existing_role_ids = set()
        for ra in workflow.role_assignments or []:
            if hasattr(ra, 'role_id') and ra.role_id:
                existing_role_ids.add(ra.role_id)

        # Create assignments for any missing roles
        for role_id in role_ids:
            if role_id not in existing_role_ids:
                new_assignment = WorkflowRoleAssignment(
                    workflow_id=workflow.id,
                    role_id=role_id,
                    user_id=None  # No user assigned yet
                )
                db.add(new_assignment)
                total_created += 1

    db.commit()

    return {
        'success': True,
        'message': f'Synced {total_created} role assignments across {len(workflows)} workflows',
        'created_count': total_created,
        'workflow_count': len(workflows)
    }


class RoleResponsibilityUpdate(BaseModel):
    """Request body for updating role responsibility"""
    role_id: int
    responsible: bool


@router.put("/workflows/{workflow_key}/days/{day_id}/role-responsibility")
async def update_day_role_responsibility(
    workflow_key: str,
    day_id: int,
    body: RoleResponsibilityUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a specific role's responsibility for a day.

    This is a convenience endpoint to toggle a single role's responsibility
    without having to update the entire day config.

    Request body:
    - role_id: The ID of the role from the Role table
    - responsible: Boolean indicating if this role is responsible for the day
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    day = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.id == day_id,
        WorkflowDayConfig.workflow_id == workflow.id
    ).first()

    if not day:
        raise HTTPException(status_code=404, detail=f"Day config {day_id} not found")

    # Get current responsibilities or initialize empty dict
    responsibilities = day.role_responsibilities or {}

    # Update the specific role
    responsibilities[str(body.role_id)] = body.responsible

    # Save back
    day.role_responsibilities = responsibilities
    day.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        'success': True,
        'day_id': day_id,
        'role_id': body.role_id,
        'is_responsible': body.responsible
    }


# =============================================================================
# Weekly Task Scheduler Endpoints
# =============================================================================

@router.post("/weekly-tasks/process")
async def process_weekly_tasks(
    workflow_key: str = Query(default='under_contract', description="Workflow key to process"),
    dry_run: bool = Query(default=False, description="If true, only simulate without creating tasks"),
    all_orgs: bool = Query(default=False, description="If true (admin only), process all organizations"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Process weekly recurring tasks for a workflow.

    When called with all_orgs=False (default), processes only the authenticated user's
    organization using the request-scoped tenant session.

    When called with all_orgs=True (platform admin only), iterates over ALL active
    organizations with per-org tenant-scoped sessions for proper RLS isolation.
    This mode is intended for cron/scheduled task triggers.

    Business Rules:
    - Monday Weekly Update: First update goes out on the Monday FOLLOWING the Disclosed date entry
    - Tasks repeat every week until loan is closed, canceled, withdrawn, or denied
    - Stakeholder emails exclude underwriter and closer

    Args:
        workflow_key: Which workflow to process (default: under_contract)
        dry_run: If true, only simulate and report what would be done
        all_orgs: If true, process all organizations (platform admin only)

    Returns:
        Summary of tasks processed, created, and any errors
    """
    try:
        if all_orgs:
            # Platform admin only: process all organizations with tenant isolation
            is_platform_admin = getattr(current_user, 'is_platform_admin', False)
            if not is_platform_admin:
                raise HTTPException(
                    status_code=403,
                    detail="Only platform admins can process weekly tasks for all organizations"
                )

            from weekly_task_scheduler import process_weekly_tasks_all_orgs
            results = process_weekly_tasks_all_orgs(
                models=_models,
                workflow_key=workflow_key,
                dry_run=dry_run
            )
        else:
            # Single-org mode: use the request-scoped session (already tenant-scoped)
            from weekly_task_scheduler import get_weekly_task_scheduler

            org_id = getattr(current_user, 'organization_id', None)
            scheduler = get_weekly_task_scheduler(db, _models, organization_id=org_id)
            results = scheduler.process_weekly_tasks(workflow_key=workflow_key, dry_run=dry_run)

        return results

    except ImportError as e:
        logger.error(f"Failed to import weekly_task_scheduler: {e}")
        raise HTTPException(status_code=500, detail="Weekly task scheduler not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing weekly tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/weekly-tasks/status")
async def get_weekly_task_status(
    workflow_key: str = Query(default='under_contract', description="Workflow key to check"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get status of weekly recurring task configurations for a workflow.

    Returns information about configured weekly tasks and recent execution.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowDayConfig = _models['WorkflowDayConfig']
    WorkflowTaskInstance = _models['WorkflowTaskInstance']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Get weekly task configurations
    weekly_configs = db.query(WorkflowDayConfig).filter(
        WorkflowDayConfig.workflow_id == workflow.id,
        WorkflowDayConfig.repeat_weekly == True
    ).all()

    # Get recent task instances
    from datetime import timedelta
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    recent_tasks = []
    for config in weekly_configs:
        tasks = db.query(WorkflowTaskInstance).filter(
            WorkflowTaskInstance.day_config_id == config.id,
            WorkflowTaskInstance.scheduled_date >= week_ago
        ).order_by(WorkflowTaskInstance.scheduled_date.desc()).limit(10).all()

        recent_tasks.extend([{
            'id': t.id,
            'loan_id': t.loan_id,
            'task_name': t.task_name,
            'scheduled_date': t.scheduled_date.isoformat() if t.scheduled_date else None,
            'status': t.status
        } for t in tasks])

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    return {
        'workflow_key': workflow_key,
        'workflow_name': workflow.workflow_name,
        'weekly_task_configs': [{
            'id': c.id,
            'day_label': c.day_label,
            'repeat_day_of_week': c.repeat_day_of_week,
            'repeat_day_name': day_names[c.repeat_day_of_week] if c.repeat_day_of_week is not None else None,
            'repeat_until_status': c.repeat_until_status or [],
            'is_active': c.is_active,
            'email_enabled': c.email_enabled,
            'stakeholders_enabled': c.referral_partner_enabled
        } for c in weekly_configs],
        'recent_tasks': recent_tasks,
        'total_weekly_configs': len(weekly_configs)
    }


@router.post("/weekly-tasks/test/{loan_id}")
async def test_weekly_task_for_loan(
    loan_id: int,
    day_config_id: int = Query(..., description="Day config ID to test"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Test weekly task generation for a specific loan (dry run).

    This is useful for debugging and verifying the scheduling logic
    before running the full weekly process.
    """
    try:
        from weekly_task_scheduler import get_weekly_task_scheduler

        if _models is None:
            raise HTTPException(status_code=500, detail="Models not initialized")

        Loan = _models['Loan']
        WorkflowDayConfig = _models['WorkflowDayConfig']

        # Get the loan
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        # Get the day config
        day_config = db.query(WorkflowDayConfig).filter(
            WorkflowDayConfig.id == day_config_id
        ).first()
        if not day_config:
            raise HTTPException(status_code=404, detail=f"Day config {day_config_id} not found")

        org_id = getattr(current_user, 'organization_id', None)
        scheduler = get_weekly_task_scheduler(db, _models, organization_id=org_id)

        # Check if task should be sent today
        should_send = scheduler.should_send_weekly_task(loan, day_config)

        # Get stakeholders
        stakeholders = scheduler.get_loan_stakeholders(loan_id)

        # Calculate next occurrence
        today = datetime.now(timezone.utc)
        target_day = getattr(day_config, 'repeat_day_of_week', 0)  # Default Monday
        trigger_date = getattr(loan, 'loan_estimate_sent_date', None) or loan.created_at

        next_send = scheduler.get_next_occurrence(target_day, trigger_date)

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        return {
            'loan_id': loan_id,
            'loan_borrower': loan.borrower_name,
            'loan_stage': loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage),
            'day_config_id': day_config_id,
            'day_label': day_config.day_label,
            'repeat_weekly': getattr(day_config, 'repeat_weekly', False),
            'repeat_day_of_week': target_day,
            'repeat_day_name': day_names[target_day],
            'trigger_date': trigger_date.isoformat() if trigger_date else None,
            'first_send_date': next_send.isoformat() if next_send else None,
            'today': today.isoformat(),
            'today_day_name': day_names[today.weekday()],
            'should_send_today': should_send,
            'stakeholders_count': len(stakeholders),
            'stakeholders': stakeholders
        }

    except ImportError as e:
        logger.error(f"Failed to import weekly_task_scheduler: {e}")
        raise HTTPException(status_code=500, detail="Weekly task scheduler not available")
    except Exception as e:
        logger.error(f"Error testing weekly task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Lead Workflow Tasks - Returns workflow tasks for a specific lead
# =============================================================================

@router.get("/leads/{lead_id}/workflow-tasks")
async def get_lead_workflow_tasks(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get workflow tasks for a specific lead based on their current stage.
    Returns all day configs with their completion status.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    # Import Lead model from main module
    from database.models import Lead

    try:
        # Get lead info using ORM
        lead = db.query(Lead).filter(Lead.id == lead_id).first()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_stage = lead.stage if lead.stage else "New"
        # Handle enum values
        if hasattr(lead_stage, 'value'):
            lead_stage = lead_stage.value

        # Map lead stages to workflow keys
        stage_to_workflow = {
            "New": "prospect",
            "Attempted Contact": "prospect",
            "Prospect": "prospect",
            "Application": "prequal",        # Application status uses prequal workflow
            "Pre-Qualified": "prequal",
            "Pre-Approved": "pre_approved",
            "Under Contract": "under_contract",
            "CTC": "last_mile",
            "Funded": "post_close",
            "Does Not Qualify": "credit_repair",
            "Long-Term Nurture": "nurture",
        }

        workflow_key = stage_to_workflow.get(lead_stage, "prospect")

        # Get workflow config using ORM
        workflow = db.query(WorkflowConfiguration).filter(
            WorkflowConfiguration.workflow_key == workflow_key,
            WorkflowConfiguration.is_active == True
        ).first()

        if not workflow:
            return {
                "lead_id": lead_id,
                "lead_name": lead.name,
                "lead_stage": lead_stage,
                "workflow": None,
                "tasks": [],
                "message": f"No active workflow found for stage: {lead_stage}"
            }

        # Calculate day in workflow
        # Use stage_changed_at if available, otherwise created_at
        stage_date = getattr(lead, 'stage_changed_at', None) or lead.created_at
        if stage_date:
            from datetime import datetime
            if hasattr(stage_date, 'replace'):
                days_in_stage = (datetime.now(timezone.utc) - stage_date.replace(tzinfo=None)).days + 1
            else:
                days_in_stage = 1
        else:
            days_in_stage = 1

        # Get all day configs for this workflow via relationship
        days = sorted([d for d in (workflow.days or []) if d.is_active], key=lambda x: (x.day_order or 0, x.day_value))

        # Build tasks list
        tasks = []
        for day in days:
            # Determine task status based on current day
            if day.day_value < days_in_stage:
                status = "completed"  # Past days are assumed completed
            elif day.day_value == days_in_stage:
                status = "due_today"
            elif day.day_value == days_in_stage + 1:
                status = "due_tomorrow"
            else:
                status = "upcoming"

            # Build communication methods list
            methods = []
            if day.phone_enabled:
                methods.append("phone")
            if day.text_enabled:
                methods.append("text")
            if day.email_enabled:
                methods.append("email")

            tasks.append({
                "id": day.id,
                "day_label": day.day_label,
                "day_value": day.day_value,
                "task_description": day.task_description,
                "communication_methods": methods,
                "status": status,
                "is_due": status in ["due_today", "due_tomorrow"],
            })

        return {
            "lead_id": lead_id,
            "lead_name": lead.name,
            "lead_stage": lead_stage,
            "days_in_stage": days_in_stage,
            "stage_changed_at": getattr(lead, 'stage_changed_at', None).isoformat() if getattr(lead, 'stage_changed_at', None) else None,
            "workflow": {
                "id": workflow.id,
                "key": workflow.workflow_key,
                "name": workflow.workflow_name,
                "color": workflow.color,
                "description": workflow.description,
            },
            "tasks": tasks,
            "summary": {
                "total_tasks": len(tasks),
                "completed": len([t for t in tasks if t["status"] == "completed"]),
                "due_today": len([t for t in tasks if t["status"] == "due_today"]),
                "due_tomorrow": len([t for t in tasks if t["status"] == "due_tomorrow"]),
                "upcoming": len([t for t in tasks if t["status"] == "upcoming"]),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lead workflow tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def get_all_workflow_tasks_logic(db: Session, current_user, days_ahead: int = 14) -> list:
    """
    Core logic to get aggregated workflow tasks for ALL leads and loans.
    This function can be called from other modules (e.g., telephony router).
    Returns a list of task dictionaries.
    """
    if _models is None:
        return []

    WorkflowConfiguration = _models['WorkflowConfiguration']
    from database.models import Lead, Loan
    from datetime import datetime, timedelta

    all_tasks = []

    # Stage to workflow mapping
    stage_to_workflow = {
        "New": "prospect",
        "Attempted Contact": "prospect",
        "Prospect": "prospect",
        "Application": "prequal",
        "Pre-Qualified": "prequal",
        "Pre-Approved": "pre_approved",
        "Under Contract": "under_contract",
        "CTC": "last_mile",
        "Funded": "post_close",
        "Does Not Qualify": "credit_repair",
        "Long-Term Nurture": "nurture",
    }

    # Cache workflows to avoid repeated queries
    workflows_cache = {}
    workflows = db.query(WorkflowConfiguration).filter(WorkflowConfiguration.is_active == True).all()
    for wf in workflows:
        workflows_cache[wf.workflow_key] = wf

    # Get all active leads (not withdrawn, closed, etc.)
    active_stages = ['New', 'Attempted Contact', 'Prospect', 'Application', 'Pre-Qualified',
                    'Pre-Approved', 'Under Contract', 'CTC', 'Does Not Qualify', 'Long-Term Nurture']
    leads = db.query(Lead).all()

    for lead in leads:
        lead_stage = lead.stage if lead.stage else "New"
        if hasattr(lead_stage, 'value'):
            lead_stage = lead_stage.value

        # Skip leads in inactive stages
        if lead_stage not in active_stages:
            continue

        workflow_key = stage_to_workflow.get(lead_stage, "prospect")
        workflow = workflows_cache.get(workflow_key)

        if not workflow:
            continue

        # Calculate days in stage
        stage_date = getattr(lead, 'stage_changed_at', None) or lead.created_at
        if stage_date:
            if hasattr(stage_date, 'replace'):
                days_in_stage = (datetime.now(timezone.utc) - stage_date.replace(tzinfo=None)).days + 1
            else:
                days_in_stage = 1
        else:
            days_in_stage = 1

        # Get tasks for this lead within the days_ahead window
        days = sorted([d for d in (workflow.days or []) if d.is_active], key=lambda x: (x.day_order or 0, x.day_value))

        for day in days:
            days_until_due = day.day_value - days_in_stage
            # Include overdue tasks (negative days_until_due) and upcoming tasks
            if days_until_due > days_ahead:
                continue

            # Calculate due date
            due_date = datetime.now(timezone.utc) + timedelta(days=days_until_due)

            # Determine status
            if days_until_due < 0:
                status = "overdue"
                urgency = "critical"
            elif days_until_due == 0:
                status = "due_today"
                urgency = "high"
            elif days_until_due == 1:
                status = "due_tomorrow"
                urgency = "medium"
            else:
                status = "upcoming"
                urgency = "low"

            # Build communication methods list
            methods = []
            if day.phone_enabled:
                methods.append("phone")
            if day.text_enabled:
                methods.append("text")
            if day.email_enabled:
                methods.append("email")

            all_tasks.append({
                "id": f"workflow-lead-{lead.id}-day-{day.id}",
                "title": day.day_label,
                "description": day.task_description or f"{day.day_label} - {workflow.workflow_name}",
                "client_name": lead.name,
                "client_type": "lead",
                "client_id": lead.id,
                "stage": lead_stage,
                "workflow_name": workflow.workflow_name,
                "workflow_key": workflow.workflow_key,
                "workflow_color": workflow.color,
                "day_value": day.day_value,
                "days_in_stage": days_in_stage,
                "days_until_due": days_until_due,
                "due_date": due_date.isoformat(),
                "status": status,
                "urgency": urgency,
                "communication_methods": methods,
                "source": "Workflow",
            })

    # Get all active loans
    # Loan stages are stored UPPERCASE in the DB — map both forms
    loan_stage_to_workflow = {
        "APPLICATION": "prequal",
        "DISCLOSED": "under_contract",
        "PROCESSING": "under_contract",
        "SUBMITTED": "under_contract",
        "UNDERWRITING": "under_contract",
        "UW_RECEIVED": "under_contract",
        "CONDITIONAL_APPROVAL": "under_contract",
        "APPROVED": "under_contract",
        "CTC": "last_mile",
        "CLEAR_TO_CLOSE": "last_mile",
        "CLOSING": "last_mile",
        "DOCS": "last_mile",
        "DOCS_OUT": "last_mile",
        "FUNDED": "post_close",
    }

    loans = db.query(Loan).all()
    for loan in loans:
        loan_stage = loan.stage if loan.stage else "APPLICATION"
        if hasattr(loan_stage, 'value'):
            loan_stage = loan_stage.value
        # Normalize to uppercase for matching
        loan_stage_upper = loan_stage.upper().replace(" ", "_") if loan_stage else "APPLICATION"

        workflow_key = loan_stage_to_workflow.get(loan_stage_upper)
        if not workflow_key:
            continue

        workflow = workflows_cache.get(workflow_key)
        if not workflow:
            continue

        # Calculate days in stage
        stage_date = getattr(loan, 'stage_changed_at', None) or loan.created_at
        if stage_date:
            if hasattr(stage_date, 'replace'):
                days_in_stage = (datetime.now(timezone.utc) - stage_date.replace(tzinfo=None)).days + 1
            else:
                days_in_stage = 1
        else:
            days_in_stage = 1

        # Get tasks for this loan within the days_ahead window
        days = sorted([d for d in (workflow.days or []) if d.is_active], key=lambda x: (x.day_order or 0, x.day_value))

        for day in days:
            days_until_due = day.day_value - days_in_stage
            # Include overdue tasks (negative days_until_due) and upcoming tasks
            if days_until_due > days_ahead:
                continue

            due_date = datetime.now(timezone.utc) + timedelta(days=days_until_due)

            if days_until_due < 0:
                status = "overdue"
                urgency = "critical"
            elif days_until_due == 0:
                status = "due_today"
                urgency = "high"
            elif days_until_due == 1:
                status = "due_tomorrow"
                urgency = "medium"
            else:
                status = "upcoming"
                urgency = "low"

            methods = []
            if day.phone_enabled:
                methods.append("phone")
            if day.text_enabled:
                methods.append("text")
            if day.email_enabled:
                methods.append("email")

            all_tasks.append({
                "id": f"workflow-loan-{loan.id}-day-{day.id}",
                "title": day.day_label,
                "description": day.task_description or f"{day.day_label} - {workflow.workflow_name}",
                "client_name": loan.borrower_name,
                "client_type": "loan",
                "client_id": loan.id,
                "stage": loan_stage,
                "workflow_name": workflow.workflow_name,
                "workflow_key": workflow.workflow_key,
                "workflow_color": workflow.color,
                "day_value": day.day_value,
                "days_in_stage": days_in_stage,
                "days_until_due": days_until_due,
                "due_date": due_date.isoformat(),
                "status": status,
                "urgency": urgency,
                "communication_methods": methods,
                "source": "Workflow",
            })

    # Also include tasks from the workflow_task_instances table (workflow-sla system)
    try:
        sla_tasks_query = db.execute(text("""
            SELECT
                wti.id as task_id,
                wti.task_type,
                wti.status as task_status,
                wti.scheduled_for,
                wti.created_at,
                wsi.lead_id,
                wsi.loan_id,
                wsi.workflow_type,
                wsi.started_at,
                wc.workflow_name,
                wc.color as workflow_color,
                l.name as lead_name,
                l.phone as lead_phone,
                l.email as lead_email,
                l.stage as lead_stage,
                loan.borrower_name as loan_borrower,
                loan.property_address as loan_property
            FROM workflow_task_instances wti
            JOIN workflow_sla_instances wsi ON wsi.id = wti.instance_id
            LEFT JOIN workflow_configurations wc ON wc.id = wsi.workflow_configuration_id
            LEFT JOIN leads l ON l.id = wsi.lead_id
            LEFT JOIN loans loan ON loan.id = wsi.loan_id
            WHERE wti.status IN ('pending', 'scheduled')
            ORDER BY wti.scheduled_for ASC NULLS LAST, wti.created_at DESC
        """))
        sla_task_rows = sla_tasks_query.fetchall()

        for row in sla_task_rows:
            # Determine client info
            if row[5]:  # lead_id
                client_name = row[12] or "Lead"
                client_type = "lead"
                client_id = row[5]
                stage = row[15] if row[15] else "Prospect"
            else:  # loan_id
                client_name = row[16] or "Borrower"
                client_type = "loan"
                client_id = row[6]
                stage = "Active Loan"

            # Determine urgency based on task type and age
            task_type = row[1]
            task_created = row[4]
            days_old = (datetime.now(timezone.utc) - task_created.replace(tzinfo=None)).days if task_created else 0

            if days_old > 2:
                urgency = "high"
                status = "overdue"
                days_until_due = -days_old
            elif days_old > 0:
                urgency = "medium"
                status = "due_today"
                days_until_due = 0
            else:
                urgency = "low"
                status = "due_today"
                days_until_due = 0

            # Build communication methods from task type
            methods = []
            if task_type == "phone":
                methods = ["phone"]
            elif task_type == "text":
                methods = ["text"]
            elif task_type == "email":
                methods = ["email"]
            elif task_type == "referral_partner":
                methods = ["email"]

            # Format task title
            type_labels = {
                "phone": "Phone Call",
                "text": "Send Text",
                "email": "Send Email",
                "referral_partner": "Partner Outreach"
            }
            title = f"{type_labels.get(task_type, task_type.title())} - {row[9] or 'Workflow'}"

            all_tasks.append({
                "id": f"sla-{row[0]}",
                "title": title,
                "description": f"Workflow task: {task_type} for {client_name}",
                "client_name": client_name,
                "client_type": client_type,
                "client_id": client_id,
                "stage": stage,
                "workflow_name": row[9] or "Workflow",
                "workflow_key": row[7],
                "workflow_color": row[10] or "#3b82f6",
                "day_value": days_old,
                "days_in_stage": days_old,
                "days_until_due": days_until_due,
                "due_date": (row[3] or row[4] or datetime.now(timezone.utc)).isoformat() if row[3] or row[4] else datetime.now(timezone.utc).isoformat(),
                "status": status,
                "urgency": urgency,
                "communication_methods": methods,
                "source": "Workflow SLA",
                "sla_task_id": row[0],
            })
    except Exception as sla_err:
        logger.warning(f"Could not fetch workflow SLA tasks: {sla_err}")

    # Sort tasks by due date (due_today first, then tomorrow, then upcoming)
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    all_tasks.sort(key=lambda t: (urgency_order.get(t["urgency"], 3), t.get("days_until_due", 0), t["client_name"]))

    return all_tasks


@router.get("/all-workflow-tasks")
async def get_all_workflow_tasks(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    days_ahead: int = Query(default=14, description="Number of days ahead to show tasks")
):
    """
    Get aggregated workflow tasks for ALL leads and loans.
    Returns tasks that are due today, tomorrow, or within the next N days.
    This is used by the global Tasks page to show all outstanding workflow tasks.
    """
    try:
        all_tasks = get_all_workflow_tasks_logic(db, current_user, days_ahead)

        return {
            "tasks": all_tasks,
            "summary": {
                "total": len(all_tasks),
                "due_today": len([t for t in all_tasks if t["status"] == "due_today"]),
                "due_tomorrow": len([t for t in all_tasks if t["status"] == "due_tomorrow"]),
                "upcoming": len([t for t in all_tasks if t["status"] == "upcoming"]),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error getting all workflow tasks (table may not exist): {e}")
        return {
            "tasks": [],
            "summary": {"total": 0, "due_today": 0, "due_tomorrow": 0, "upcoming": 0}
        }
