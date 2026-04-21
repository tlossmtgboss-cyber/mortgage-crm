"""
AI Workflow Routes - Autonomous Workflow Endpoints

This module contains endpoints for:
- Scheduled workflows (create, list, execute)
- Workflow executions history
- AI audit logs
- Workflow templates
- Compliance validation
- Event-triggered workflows
- Background scheduler operations
"""

import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Workflows"])


# =============================================================================
# Runtime Import Functions (to avoid circular imports)
# =============================================================================

def get_current_user_flexible_dep():
    """Get current user flexible dependency - imports from main at runtime"""
    import main
    return main.get_current_user_flexible


def get_scheduled_workflow_model():
    """Get ScheduledWorkflow model at runtime"""
    import main
    return main.ScheduledWorkflow


def get_workflow_execution_model():
    """Get WorkflowExecution model at runtime"""
    import main
    return main.WorkflowExecution


def get_ai_audit_log_model():
    """Get AIAuditLog model at runtime"""
    import main
    return main.AIAuditLog


def get_loan_model():
    """Get Loan model at runtime"""
    import main
    return main.Loan


def get_task_model():
    """Get Task model at runtime"""
    import main
    return main.Task


def get_lead_model():
    """Get Lead model at runtime"""
    import main
    return main.Lead


def get_user_model():
    """Get User model at runtime"""
    import main
    return main.User


# =============================================================================
# Workflow Templates
# =============================================================================

WORKFLOW_TEMPLATES = {
    "weekly_borrower_update": {
        "name": "Weekly Borrower Updates",
        "description": "Send personalized weekly status updates to all active loan borrowers",
        "schedule_interval": "weekly",
        "target_criteria": {"loan_status": ["in_progress", "processing", "underwriting"]},
        "config": {"include_next_steps": True, "include_timeline": True}
    },
    "daily_task_summary": {
        "name": "Daily Task Summary",
        "description": "Generate and send daily task digest",
        "schedule_interval": "daily",
        "config": {"include_overdue": True, "include_upcoming": True}
    },
    "follow_up_sequence": {
        "name": "Lead Follow-up Sequence",
        "description": "Auto-create follow-up tasks for leads in nurture stages",
        "schedule_interval": "daily",
        "target_criteria": {"lead_stage": ["NEW", "CONTACTED", "QUALIFIED"]},
        "config": {"follow_up_days": 2, "priority": "medium"}
    },
    "pipeline_report": {
        "name": "Weekly Pipeline Report",
        "description": "Generate and send weekly pipeline analytics report",
        "schedule_interval": "weekly",
        "config": {"include_conversion_rates": True, "include_projections": True}
    }
}


# =============================================================================
# Compliance Rules
# =============================================================================

COMPLIANCE_RULES = {
    "email_to_borrower": {
        "rules": [
            {"name": "rate_limit", "max_per_day": 3, "description": "Max 3 emails per borrower per day"},
            {"name": "business_hours", "start": 8, "end": 20, "description": "Only send during business hours"},
            {"name": "opt_out_check", "description": "Verify borrower hasn't opted out"},
            {"name": "content_review", "forbidden_words": ["guaranteed", "promise", "100%"], "description": "No misleading claims"}
        ],
        "risk_level": "medium"
    },
    "sms_to_borrower": {
        "rules": [
            {"name": "rate_limit", "max_per_day": 2, "description": "Max 2 SMS per borrower per day"},
            {"name": "tcpa_compliance", "description": "TCPA consent required"},
            {"name": "business_hours", "start": 9, "end": 21, "description": "Only send 9am-9pm local time"}
        ],
        "risk_level": "medium"
    },
    "lead_stage_update": {
        "rules": [
            {"name": "valid_transition", "description": "Stage transition must be valid"},
            {"name": "audit_required", "description": "All changes must be logged"}
        ],
        "risk_level": "low"
    },
    "loan_data_update": {
        "rules": [
            {"name": "hmda_fields", "protected": ["race", "ethnicity", "sex"], "description": "HMDA protected fields require special handling"},
            {"name": "audit_required", "description": "All changes must be logged"},
            {"name": "dual_control", "threshold": 50000, "description": "Changes over $50k need review"}
        ],
        "risk_level": "high"
    },
    "task_creation": {
        "rules": [
            {"name": "rate_limit", "max_per_hour": 20, "description": "Max 20 tasks per hour"},
        ],
        "risk_level": "low"
    }
}


# =============================================================================
# Event Triggers
# =============================================================================

EVENT_TRIGGERS = {
    "lead_stage_changed": {
        "description": "Triggered when a lead's stage changes",
        "available_actions": ["send_email", "create_task", "send_sms", "notify_user"]
    },
    "loan_status_changed": {
        "description": "Triggered when a loan's status changes",
        "available_actions": ["send_borrower_update", "create_task", "notify_team"]
    },
    "task_overdue": {
        "description": "Triggered when a task becomes overdue",
        "available_actions": ["send_reminder", "escalate", "reassign"]
    },
    "document_uploaded": {
        "description": "Triggered when a document is uploaded",
        "available_actions": ["verify_document", "update_checklist", "notify_processor"]
    },
    "new_lead_created": {
        "description": "Triggered when a new lead is created",
        "available_actions": ["send_welcome", "create_tasks", "assign_lo"]
    }
}


# =============================================================================
# Helper Functions
# =============================================================================

async def validate_compliance(
    db: Session,
    user_id: int,
    action_type: str,
    target_id: int = None,
    action_data: dict = None
) -> dict:
    """
    Validate an action against compliance rules before execution
    Returns: {"passed": bool, "violations": [], "warnings": [], "risk_level": str}
    """
    AIAuditLog = get_ai_audit_log_model()

    result = {
        "passed": True,
        "violations": [],
        "warnings": [],
        "risk_level": "low",
        "checked_at": datetime.now().isoformat()
    }

    if action_type not in COMPLIANCE_RULES:
        return result

    rules = COMPLIANCE_RULES[action_type]
    result["risk_level"] = rules.get("risk_level", "low")

    for rule in rules.get("rules", []):
        rule_name = rule["name"]

        # Rate limit check
        if rule_name == "rate_limit":
            if "max_per_day" in rule:
                # Count actions in last 24 hours
                cutoff = datetime.now() - timedelta(days=1)
                count = db.query(AIAuditLog).filter(
                    AIAuditLog.user_id == user_id,
                    AIAuditLog.action_type == action_type,
                    AIAuditLog.target_id == target_id,
                    AIAuditLog.created_at >= cutoff
                ).count()

                if count >= rule["max_per_day"]:
                    result["passed"] = False
                    result["violations"].append({
                        "rule": rule_name,
                        "message": f"Rate limit exceeded: {count}/{rule['max_per_day']} per day",
                        "severity": "error"
                    })
                elif count >= rule["max_per_day"] - 1:
                    result["warnings"].append({
                        "rule": rule_name,
                        "message": f"Approaching rate limit: {count}/{rule['max_per_day']} per day"
                    })

            if "max_per_hour" in rule:
                cutoff = datetime.now() - timedelta(hours=1)
                count = db.query(AIAuditLog).filter(
                    AIAuditLog.user_id == user_id,
                    AIAuditLog.action_type == action_type,
                    AIAuditLog.created_at >= cutoff
                ).count()

                if count >= rule["max_per_hour"]:
                    result["passed"] = False
                    result["violations"].append({
                        "rule": rule_name,
                        "message": f"Hourly rate limit exceeded: {count}/{rule['max_per_hour']}",
                        "severity": "error"
                    })

        # Business hours check
        elif rule_name == "business_hours":
            current_hour = datetime.now().hour
            if current_hour < rule["start"] or current_hour >= rule["end"]:
                result["warnings"].append({
                    "rule": rule_name,
                    "message": f"Outside business hours ({rule['start']}:00-{rule['end']}:00)"
                })

        # Content review check
        elif rule_name == "content_review" and action_data:
            content = str(action_data.get("content", "") or action_data.get("message", "")).lower()
            for word in rule.get("forbidden_words", []):
                if word.lower() in content:
                    result["passed"] = False
                    result["violations"].append({
                        "rule": rule_name,
                        "message": f"Forbidden word detected: '{word}'",
                        "severity": "error"
                    })

        # HMDA protected fields
        elif rule_name == "hmda_fields" and action_data:
            for field in rule.get("protected", []):
                if field in action_data:
                    result["warnings"].append({
                        "rule": rule_name,
                        "message": f"HMDA protected field '{field}' being modified - ensure compliance"
                    })

        # Dual control for large amounts
        elif rule_name == "dual_control" and action_data:
            amount = action_data.get("loan_amount", 0) or action_data.get("amount", 0)
            if amount and float(amount) > rule.get("threshold", 50000):
                result["warnings"].append({
                    "rule": rule_name,
                    "message": f"Amount ${amount:,.2f} exceeds ${rule['threshold']:,} - consider review"
                })

    return result


# =============================================================================
# AUTONOMOUS WORKFLOW ENDPOINTS
# =============================================================================

@router.post("/workflows")
async def create_scheduled_workflow(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Create a new scheduled autonomous workflow
    """
    try:
        ScheduledWorkflow = get_scheduled_workflow_model()

        data = await request.json()

        # Calculate next run time
        schedule_interval = data.get("schedule_interval", "weekly")
        now = datetime.now()

        if schedule_interval == "daily":
            next_run = now + timedelta(days=1)
        elif schedule_interval == "weekly":
            next_run = now + timedelta(weeks=1)
        elif schedule_interval == "monthly":
            next_run = now + timedelta(days=30)
        else:
            next_run = now + timedelta(days=1)

        workflow = ScheduledWorkflow(
            user_id=current_user.id,
            name=data.get("name"),
            description=data.get("description"),
            workflow_type=data.get("workflow_type"),
            schedule_cron=data.get("schedule_cron"),
            schedule_interval=schedule_interval,
            next_run=next_run,
            is_active=data.get("is_active", True),
            config=data.get("config", {}),
            target_criteria=data.get("target_criteria", {}),
            template_id=data.get("template_id"),
            retry_on_failure=data.get("retry_on_failure", True),
            max_retries=data.get("max_retries", 3),
            notify_on_completion=data.get("notify_on_completion", False),
            notify_on_failure=data.get("notify_on_failure", True)
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        return {
            "id": workflow.id,
            "name": workflow.name,
            "workflow_type": workflow.workflow_type,
            "schedule_interval": workflow.schedule_interval,
            "next_run": workflow.next_run.isoformat() if workflow.next_run else None,
            "is_active": workflow.is_active,
            "success": True
        }

    except Exception as e:
        logger.error(f"Create workflow error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows")
async def list_scheduled_workflows(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    List all scheduled workflows for the user
    """
    ScheduledWorkflow = get_scheduled_workflow_model()

    workflows = db.query(ScheduledWorkflow).filter(
        ScheduledWorkflow.user_id == current_user.id
    ).order_by(ScheduledWorkflow.created_at.desc()).all()

    return {
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "workflow_type": w.workflow_type,
                "schedule_interval": w.schedule_interval,
                "next_run": w.next_run.isoformat() if w.next_run else None,
                "last_run": w.last_run.isoformat() if w.last_run else None,
                "is_active": w.is_active,
                "total_executions": w.total_executions,
                "successful_executions": w.successful_executions,
                "failed_executions": w.failed_executions
            }
            for w in workflows
        ],
        "total": len(workflows)
    }


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Manually trigger a workflow execution
    """
    try:
        from openai import OpenAI

        ScheduledWorkflow = get_scheduled_workflow_model()
        WorkflowExecution = get_workflow_execution_model()
        AIAuditLog = get_ai_audit_log_model()
        Loan = get_loan_model()
        Task = get_task_model()
        Lead = get_lead_model()

        workflow = db.query(ScheduledWorkflow).filter(
            ScheduledWorkflow.id == workflow_id,
            ScheduledWorkflow.user_id == current_user.id
        ).first()

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Create execution record
        execution = WorkflowExecution(
            workflow_id=workflow.id,
            user_id=current_user.id,
            status="running",
            trigger_type="manual"
        )
        db.add(execution)
        db.commit()

        actions_taken = []
        errors = []
        targets_processed = 0
        targets_succeeded = 0

        # Execute based on workflow type
        if workflow.workflow_type == "weekly_borrower_update":
            # Get active loans with borrower emails
            loans = db.query(Loan).filter(
                Loan.user_id == current_user.id,
                Loan.status.in_(["in_progress", "processing", "underwriting", "approved"])
            ).all()

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            for loan in loans:
                targets_processed += 1
                try:
                    # Generate personalized update
                    update_prompt = f"""Generate a brief, professional weekly loan status update email for:
Borrower: {loan.borrower_name}
Loan Type: {loan.loan_type}
Status: {loan.status}
Loan Amount: ${loan.loan_amount:,.2f if loan.loan_amount else 0}

Keep it under 150 words. Be encouraging and informative."""

                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a mortgage loan officer assistant."},
                            {"role": "user", "content": update_prompt}
                        ],
                        max_tokens=200
                    )

                    email_content = response.choices[0].message.content

                    # Log the action (in production, would actually send email)
                    actions_taken.append({
                        "action": "email_sent",
                        "target": loan.borrower_name,
                        "loan_id": loan.id,
                        "content_preview": email_content[:100]
                    })

                    # Create audit log
                    audit = AIAuditLog(
                        user_id=current_user.id,
                        agent_name="Workflow Engine",
                        action_type="borrower_update_email",
                        action_category="communication",
                        autonomy_level="autonomous",
                        target_type="loan",
                        target_id=loan.id,
                        input_data={"loan_status": loan.status, "borrower": loan.borrower_name},
                        output_data={"email_content": email_content},
                        status="completed",
                        model_used="gpt-4o"
                    )
                    db.add(audit)

                    targets_succeeded += 1

                except Exception as e:
                    errors.append({"loan_id": loan.id, "error": "Internal server error"})

        elif workflow.workflow_type == "daily_task_summary":
            # Get today's tasks
            today = datetime.now().date()
            tasks = db.query(Task).filter(
                Task.owner_id == current_user.id,
                Task.due_date != None
            ).all()

            today_tasks = [t for t in tasks if t.due_date.date() == today]
            overdue_tasks = [t for t in tasks if t.due_date.date() < today and t.status != "completed"]

            actions_taken.append({
                "action": "summary_generated",
                "today_tasks": len(today_tasks),
                "overdue_tasks": len(overdue_tasks)
            })
            targets_succeeded = 1
            targets_processed = 1

        elif workflow.workflow_type == "follow_up_sequence":
            # Get leads needing follow-up
            leads = db.query(Lead).filter(
                Lead.owner_id == current_user.id,
                Lead.stage.in_(["NEW", "CONTACTED", "QUALIFIED"])
            ).all()

            for lead in leads:
                targets_processed += 1
                # Create follow-up task
                task = Task(
                    title=f"Follow up with {lead.name}",
                    description=f"Automated follow-up for {lead.name}",
                    due_date=datetime.now() + timedelta(days=2),
                    priority="medium",
                    status="pending",
                    owner_id=current_user.id,
                    lead_id=lead.id
                )
                db.add(task)
                actions_taken.append({
                    "action": "task_created",
                    "lead": lead.name,
                    "task": task.title
                })
                targets_succeeded += 1

        # Update execution record
        execution.status = "completed" if not errors else "partial"
        execution.completed_at = datetime.now()
        execution.targets_processed = targets_processed
        execution.targets_succeeded = targets_succeeded
        execution.targets_failed = len(errors)
        execution.actions_taken = actions_taken
        execution.errors = errors if errors else None

        # Update workflow stats
        workflow.last_run = datetime.now()
        workflow.total_executions += 1
        if not errors:
            workflow.successful_executions += 1
        else:
            workflow.failed_executions += 1

        # Calculate next run
        if workflow.schedule_interval == "daily":
            workflow.next_run = datetime.now() + timedelta(days=1)
        elif workflow.schedule_interval == "weekly":
            workflow.next_run = datetime.now() + timedelta(weeks=1)
        elif workflow.schedule_interval == "monthly":
            workflow.next_run = datetime.now() + timedelta(days=30)

        db.commit()

        return {
            "execution_id": execution.id,
            "workflow_id": workflow.id,
            "status": execution.status,
            "targets_processed": targets_processed,
            "targets_succeeded": targets_succeeded,
            "actions_taken": actions_taken,
            "errors": errors,
            "next_run": workflow.next_run.isoformat() if workflow.next_run else None,
            "success": True
        }

    except Exception as e:
        logger.error(f"Workflow execution error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows/{workflow_id}/executions")
async def get_workflow_executions(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep()),
    limit: int = 20
):
    """
    Get execution history for a workflow
    """
    WorkflowExecution = get_workflow_execution_model()

    executions = db.query(WorkflowExecution).filter(
        WorkflowExecution.workflow_id == workflow_id,
        WorkflowExecution.user_id == current_user.id
    ).order_by(WorkflowExecution.created_at.desc()).limit(limit).all()

    return {
        "executions": [
            {
                "id": e.id,
                "status": e.status,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "targets_processed": e.targets_processed,
                "targets_succeeded": e.targets_succeeded,
                "targets_failed": e.targets_failed,
                "trigger_type": e.trigger_type,
                "actions_taken": e.actions_taken
            }
            for e in executions
        ]
    }


@router.get("/audit-logs")
async def get_audit_logs(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep()),
    limit: int = 50,
    action_type: Optional[str] = None,
    agent_name: Optional[str] = None
):
    """
    Get AI audit logs with optional filtering
    """
    AIAuditLog = get_ai_audit_log_model()

    query = db.query(AIAuditLog).filter(AIAuditLog.user_id == current_user.id)

    if action_type:
        query = query.filter(AIAuditLog.action_type == action_type)
    if agent_name:
        query = query.filter(AIAuditLog.agent_name == agent_name)

    logs = query.order_by(AIAuditLog.created_at.desc()).limit(limit).all()

    return {
        "logs": [
            {
                "id": l.id,
                "agent_name": l.agent_name,
                "action_type": l.action_type,
                "action_category": l.action_category,
                "autonomy_level": l.autonomy_level,
                "target_type": l.target_type,
                "target_id": l.target_id,
                "status": l.status,
                "compliance_passed": l.compliance_passed,
                "created_at": l.created_at.isoformat()
            }
            for l in logs
        ],
        "total": len(logs)
    }


@router.get("/audit-logs/summary")
async def get_audit_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep()),
    days: int = 7
):
    """
    Get summary of AI actions for reporting
    """
    AIAuditLog = get_ai_audit_log_model()

    cutoff = datetime.now() - timedelta(days=days)

    logs = db.query(AIAuditLog).filter(
        AIAuditLog.user_id == current_user.id,
        AIAuditLog.created_at >= cutoff
    ).all()

    # Aggregate by action type
    action_counts = {}
    agent_counts = {}
    autonomous_count = 0
    total_actions = len(logs)

    for log in logs:
        action_counts[log.action_type] = action_counts.get(log.action_type, 0) + 1
        agent_counts[log.agent_name] = agent_counts.get(log.agent_name, 0) + 1
        if log.autonomy_level == "autonomous":
            autonomous_count += 1

    return {
        "period_days": days,
        "total_actions": total_actions,
        "autonomous_actions": autonomous_count,
        "autonomous_percentage": round((autonomous_count / total_actions * 100) if total_actions > 0 else 0, 1),
        "by_action_type": action_counts,
        "by_agent": agent_counts
    }


@router.get("/workflow-templates")
async def get_workflow_templates(
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get available workflow templates
    """
    return {
        "templates": [
            {
                "id": key,
                **value
            }
            for key, value in WORKFLOW_TEMPLATES.items()
        ]
    }


@router.post("/workflows/from-template/{template_id}")
async def create_workflow_from_template(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Create a workflow from a predefined template
    """
    ScheduledWorkflow = get_scheduled_workflow_model()

    if template_id not in WORKFLOW_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")

    template = WORKFLOW_TEMPLATES[template_id]
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}

    # Calculate next run
    schedule_interval = template.get("schedule_interval", "weekly")

    if schedule_interval == "daily":
        next_run = datetime.now() + timedelta(days=1)
    elif schedule_interval == "weekly":
        next_run = datetime.now() + timedelta(weeks=1)
    else:
        next_run = datetime.now() + timedelta(days=1)

    workflow = ScheduledWorkflow(
        user_id=current_user.id,
        name=data.get("name", template["name"]),
        description=template["description"],
        workflow_type=template_id,
        schedule_interval=schedule_interval,
        next_run=next_run,
        is_active=True,
        config=template.get("config", {}),
        target_criteria=template.get("target_criteria", {})
    )

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    return {
        "id": workflow.id,
        "name": workflow.name,
        "workflow_type": workflow.workflow_type,
        "schedule_interval": workflow.schedule_interval,
        "next_run": workflow.next_run.isoformat(),
        "success": True
    }


# =============================================================================
# COMPLIANCE VALIDATION ENDPOINTS
# =============================================================================

@router.post("/compliance/validate")
async def validate_action_compliance(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Validate an action against compliance rules before execution
    """
    data = await request.json()

    result = await validate_compliance(
        db=db,
        user_id=current_user.id,
        action_type=data.get("action_type"),
        target_id=data.get("target_id"),
        action_data=data.get("action_data", {})
    )

    return result


@router.get("/compliance/rules")
async def get_compliance_rules(
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get all compliance rules
    """
    return {"rules": COMPLIANCE_RULES}


# =============================================================================
# EVENT-TRIGGERED WORKFLOW ENDPOINTS
# =============================================================================

@router.post("/events/trigger")
async def trigger_event_workflow(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Trigger event-based workflows
    Called by webhooks or internal events
    """
    try:
        from openai import OpenAI

        AIAuditLog = get_ai_audit_log_model()
        Lead = get_lead_model()
        Loan = get_loan_model()
        Task = get_task_model()

        data = await request.json()
        event_type = data.get("event_type")
        entity_type = data.get("entity_type")  # lead, loan, task
        entity_id = data.get("entity_id")
        old_value = data.get("old_value")
        new_value = data.get("new_value")
        metadata = data.get("metadata", {})

        actions_taken = []
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Handle different event types
        if event_type == "lead_stage_changed":
            lead = db.query(Lead).filter(Lead.id == entity_id).first()
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found")

            # Auto-actions based on new stage
            if new_value in ["QUALIFIED", "CONTACTED"]:
                # Create follow-up task
                task = Task(
                    title=f"Follow up with {lead.name} - Stage: {new_value}",
                    description=f"Lead moved to {new_value}. Schedule next contact.",
                    due_date=datetime.now() + timedelta(days=1),
                    priority="high",
                    status="pending",
                    owner_id=current_user.id,
                    lead_id=lead.id
                )
                db.add(task)
                actions_taken.append({"action": "task_created", "task": task.title})

            elif new_value == "APPLICATION":
                # Generate welcome to application email
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Generate a brief, professional welcome email for a mortgage applicant."},
                        {"role": "user", "content": f"Welcome {lead.name} who just started their mortgage application."}
                    ],
                    max_tokens=150
                )
                email_content = response.choices[0].message.content
                actions_taken.append({
                    "action": "email_generated",
                    "content_preview": email_content[:100]
                })

        elif event_type == "loan_status_changed":
            loan = db.query(Loan).filter(Loan.id == entity_id).first()
            if loan:
                # Auto-notify borrower of status change
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Generate a brief loan status update notification."},
                        {"role": "user", "content": f"Loan for {loan.borrower_name} moved from {old_value} to {new_value}."}
                    ],
                    max_tokens=100
                )
                notification = response.choices[0].message.content
                actions_taken.append({
                    "action": "notification_generated",
                    "status_change": f"{old_value} -> {new_value}",
                    "content": notification
                })

        elif event_type == "task_overdue":
            task = db.query(Task).filter(Task.id == entity_id).first()
            if task:
                # Escalate priority
                task.priority = "urgent"
                actions_taken.append({
                    "action": "task_escalated",
                    "task": task.title,
                    "new_priority": "urgent"
                })

        elif event_type == "new_lead_created":
            lead = db.query(Lead).filter(Lead.id == entity_id).first()
            if lead:
                # Create initial tasks
                initial_tasks = [
                    ("Initial contact call", 0, "high"),
                    ("Send intro email", 0, "medium"),
                    ("Qualify lead", 1, "high")
                ]
                for title, days, priority in initial_tasks:
                    task = Task(
                        title=f"{title} - {lead.name}",
                        due_date=datetime.now() + timedelta(days=days),
                        priority=priority,
                        status="pending",
                        owner_id=current_user.id,
                        lead_id=lead.id
                    )
                    db.add(task)
                    actions_taken.append({"action": "task_created", "task": task.title})

        # Log the event
        audit = AIAuditLog(
            user_id=current_user.id,
            agent_name="Event Trigger Engine",
            action_type=f"event_{event_type}",
            action_category="automation",
            autonomy_level="autonomous",
            target_type=entity_type,
            target_id=entity_id,
            input_data={"event": event_type, "old": old_value, "new": new_value},
            output_data={"actions": actions_taken},
            status="completed"
        )
        db.add(audit)
        db.commit()

        return {
            "event_type": event_type,
            "entity_id": entity_id,
            "actions_taken": actions_taken,
            "success": True
        }

    except Exception as e:
        logger.error(f"Event trigger error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/events/triggers")
async def get_event_triggers(
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get available event triggers
    """
    return {"triggers": EVENT_TRIGGERS}


# =============================================================================
# BACKGROUND SCHEDULER ENDPOINTS
# =============================================================================

@router.post("/scheduler/run-due-workflows")
async def run_due_workflows(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Execute all workflows that are due to run
    Called by external cron job or scheduler service
    """
    try:
        ScheduledWorkflow = get_scheduled_workflow_model()
        WorkflowExecution = get_workflow_execution_model()
        Loan = get_loan_model()
        Task = get_task_model()
        Lead = get_lead_model()

        # Get API key from header for scheduler authentication
        api_key = request.headers.get("X-Scheduler-Key") or ""
        expected_key = os.getenv("SCHEDULER_API_KEY", "")

        if not expected_key:
            raise HTTPException(status_code=503, detail="Scheduler API key not configured")
        if not secrets.compare_digest(api_key, expected_key):
            raise HTTPException(status_code=401, detail="Invalid scheduler key")

        now = datetime.now()

        # Find all due workflows
        due_workflows = db.query(ScheduledWorkflow).filter(
            ScheduledWorkflow.is_active == True,
            ScheduledWorkflow.next_run <= now
        ).all()

        results = []

        for workflow in due_workflows:
            try:
                # Create execution record
                execution = WorkflowExecution(
                    workflow_id=workflow.id,
                    user_id=workflow.user_id,
                    status="running",
                    trigger_type="scheduled"
                )
                db.add(execution)
                db.commit()

                # Execute the workflow (simplified - would call execute_workflow internally)
                actions_taken = []
                errors = []

                if workflow.workflow_type == "weekly_borrower_update":
                    loans = db.query(Loan).filter(
                        Loan.user_id == workflow.user_id,
                        Loan.status.in_(["in_progress", "processing", "underwriting"])
                    ).all()

                    for loan in loans:
                        actions_taken.append({
                            "action": "borrower_update_queued",
                            "loan_id": loan.id,
                            "borrower": loan.borrower_name
                        })

                elif workflow.workflow_type == "daily_task_summary":
                    tasks = db.query(Task).filter(
                        Task.owner_id == workflow.user_id,
                        Task.status != "completed"
                    ).count()
                    actions_taken.append({
                        "action": "summary_generated",
                        "pending_tasks": tasks
                    })

                elif workflow.workflow_type == "follow_up_sequence":
                    leads = db.query(Lead).filter(
                        Lead.owner_id == workflow.user_id,
                        Lead.stage.in_(["NEW", "CONTACTED"])
                    ).all()
                    for lead in leads:
                        actions_taken.append({
                            "action": "follow_up_queued",
                            "lead": lead.name
                        })

                # Update execution
                execution.status = "completed"
                execution.completed_at = datetime.now()
                execution.targets_processed = len(actions_taken)
                execution.targets_succeeded = len(actions_taken)
                execution.actions_taken = actions_taken

                # Update workflow
                workflow.last_run = now
                workflow.total_executions += 1
                workflow.successful_executions += 1

                # Calculate next run
                if workflow.schedule_interval == "daily":
                    workflow.next_run = now + timedelta(days=1)
                elif workflow.schedule_interval == "weekly":
                    workflow.next_run = now + timedelta(weeks=1)
                elif workflow.schedule_interval == "monthly":
                    workflow.next_run = now + timedelta(days=30)

                results.append({
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "status": "completed",
                    "actions": len(actions_taken)
                })

            except Exception as e:
                workflow.failed_executions += 1
                results.append({
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "status": "failed",
                    "error": "Internal server error"
                })

        db.commit()

        return {
            "executed": len(results),
            "results": results,
            "next_check": "Call this endpoint periodically (e.g., every 5 minutes)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scheduler/status")
async def get_scheduler_status(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get scheduler status and upcoming workflows
    """
    ScheduledWorkflow = get_scheduled_workflow_model()

    now = datetime.now()

    # Get user's workflows
    workflows = db.query(ScheduledWorkflow).filter(
        ScheduledWorkflow.user_id == current_user.id,
        ScheduledWorkflow.is_active == True
    ).all()

    upcoming = []
    overdue = []

    for w in workflows:
        info = {
            "id": w.id,
            "name": w.name,
            "workflow_type": w.workflow_type,
            "next_run": w.next_run.isoformat() if w.next_run else None,
            "last_run": w.last_run.isoformat() if w.last_run else None
        }

        if w.next_run:
            if w.next_run <= now:
                overdue.append(info)
            elif w.next_run <= now + timedelta(days=1):
                upcoming.append(info)

    return {
        "total_active_workflows": len(workflows),
        "overdue_count": len(overdue),
        "upcoming_24h": upcoming,
        "overdue": overdue,
        "scheduler_endpoint": "/api/v1/ai/scheduler/run-due-workflows",
        "recommended_interval": "5 minutes"
    }


@router.post("/scheduler/pause/{workflow_id}")
async def pause_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Pause a scheduled workflow
    """
    ScheduledWorkflow = get_scheduled_workflow_model()

    workflow = db.query(ScheduledWorkflow).filter(
        ScheduledWorkflow.id == workflow_id,
        ScheduledWorkflow.user_id == current_user.id
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow.is_active = False
    db.commit()

    return {"id": workflow_id, "is_active": False, "message": "Workflow paused"}


@router.post("/scheduler/resume/{workflow_id}")
async def resume_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Resume a paused workflow
    """
    ScheduledWorkflow = get_scheduled_workflow_model()

    workflow = db.query(ScheduledWorkflow).filter(
        ScheduledWorkflow.id == workflow_id,
        ScheduledWorkflow.user_id == current_user.id
    ).first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow.is_active = True

    # Reset next_run if it's in the past
    if workflow.next_run and workflow.next_run < datetime.now():
        if workflow.schedule_interval == "daily":
            workflow.next_run = datetime.now() + timedelta(days=1)
        elif workflow.schedule_interval == "weekly":
            workflow.next_run = datetime.now() + timedelta(weeks=1)
        else:
            workflow.next_run = datetime.now() + timedelta(days=1)

    db.commit()

    return {
        "id": workflow_id,
        "is_active": True,
        "next_run": workflow.next_run.isoformat() if workflow.next_run else None,
        "message": "Workflow resumed"
    }
