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
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow-config", tags=["Workflow Configuration"])


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================

class DayConfigCreate(BaseModel):
    day_label: str
    day_value: int
    day_order: Optional[int] = None  # If not provided, will be auto-calculated
    phone_enabled: bool = False
    text_enabled: bool = False
    email_enabled: bool = False
    referral_partner_enabled: bool = False
    lo_responsible: bool = False
    jr_lo_responsible: bool = False
    production_asst_responsible: bool = False
    ai_responsible: bool = False
    task_description: Optional[str] = None


class DayConfigUpdate(BaseModel):
    day_label: Optional[str] = None
    day_value: Optional[int] = None
    phone_enabled: Optional[bool] = None
    text_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    referral_partner_enabled: Optional[bool] = None
    lo_responsible: Optional[bool] = None
    jr_lo_responsible: Optional[bool] = None
    production_asst_responsible: Optional[bool] = None
    ai_responsible: Optional[bool] = None
    is_active: Optional[bool] = None
    task_description: Optional[str] = None


class RoleAssignmentCreate(BaseModel):
    role: str  # loan_officer, junior_loan_officer, production_assistant, ai
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


def set_dependencies(db_dep, user_dep, models):
    """Set dependencies from main app"""
    global _get_db, _get_current_user, _models
    _get_db = db_dep
    _get_current_user = user_dep
    _models = models


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


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
        raise HTTPException(status_code=500, detail="Models not initialized")

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
            'text_enabled': day.text_enabled,
            'email_enabled': day.email_enabled,
            'referral_partner_enabled': day.referral_partner_enabled,
            'lo_responsible': day.lo_responsible,
            'jr_lo_responsible': day.jr_lo_responsible,
            'production_asst_responsible': day.production_asst_responsible,
            'ai_responsible': day.ai_responsible,
            'health_status': day.health_status.value if day.health_status else 'healthy',
            'health_message': day.health_message,
            'is_active': day.is_active,
            'task_description': day.task_description
        })

    # Build role assignments list
    role_assignments = []
    for ra in workflow.role_assignments or []:
        user_name = None
        if ra.user_id and ra.user:
            user_name = ra.user.full_name or ra.user.email
        role_assignments.append({
            'id': ra.id,
            'role': ra.role.value if hasattr(ra.role, 'value') else ra.role,
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
        lo_responsible=day_config.lo_responsible,
        jr_lo_responsible=day_config.jr_lo_responsible,
        production_asst_responsible=day_config.production_asst_responsible,
        ai_responsible=day_config.ai_responsible,
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
            'day_value': new_day.day_value
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
    update_data = day_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(day, field, value)

    day.updated_at = datetime.utcnow()
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
    """Add a new role assignment to a workflow"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    WorkflowConfiguration = _models['WorkflowConfiguration']
    WorkflowRoleAssignment = _models['WorkflowRoleAssignment']

    workflow = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.workflow_key == workflow_key
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_key}' not found")

    # Import TaskResponsibility enum
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

    assignment.updated_at = datetime.utcnow()
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
    if not any([day.lo_responsible, day.jr_lo_responsible, day.production_asst_responsible, day.ai_responsible]):
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

    day.last_health_check = datetime.utcnow()
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
    alert.resolved_at = datetime.utcnow()
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
                ai_responsible=day_data.get('ai', False),
                health_status=TaskHealthStatus.HEALTHY
            )
            db.add(day)

        created += 1

    db.commit()

    return {'success': True, 'workflows_created': created}


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
    from main import User

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
