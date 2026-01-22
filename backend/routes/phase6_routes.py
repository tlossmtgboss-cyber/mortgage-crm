"""
Phase 6 Routes: Advanced AI Orchestration & Automation

Includes routes for:
- Advanced Workflow Orchestration
- Predictive AI & Proactive Recommendations
- AI Agent Coordination
- Self-Healing System
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Workflow Orchestration Routes
# =============================================================================

workflow_router = APIRouter(prefix="/api/v1/workflows")


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = []


class WorkflowStepCreate(BaseModel):
    step_id: str
    name: str
    step_type: str  # action, condition, parallel, wait, loop, subprocess, human_task, ai_decision
    config: Dict[str, Any] = {}
    next_steps: List[str] = []
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    retry_count: int = 0
    timeout_seconds: int = 300


class WorkflowTrigger(BaseModel):
    trigger_type: str  # manual, schedule, event, webhook, condition
    config: Dict[str, Any]


class WorkflowStartRequest(BaseModel):
    input_data: Dict[str, Any] = {}
    trigger_type: str = "manual"


@workflow_router.post("/")
async def create_workflow(workflow: WorkflowCreate):
    """Create a new workflow definition."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        wf = service.create_workflow(
            name=workflow.name,
            description=workflow.description,
            tags=workflow.tags
        )

        return {
            "success": True,
            "workflow": {
                "id": wf.id,
                "name": wf.name,
                "version": wf.version
            }
        }
    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.post("/{workflow_id}/steps")
async def add_workflow_step(workflow_id: str, step: WorkflowStepCreate):
    """Add a step to a workflow."""
    try:
        from services.advanced_workflow_orchestration_service import (
            AdvancedWorkflowOrchestrationService, StepType
        )
        service = AdvancedWorkflowOrchestrationService()

        step_type = StepType(step.step_type)

        result = service.add_step(
            workflow_id=workflow_id,
            step_id=step.step_id,
            name=step.name,
            step_type=step_type,
            config=step.config,
            next_steps=step.next_steps,
            on_success=step.on_success,
            on_failure=step.on_failure,
            retry_count=step.retry_count,
            timeout_seconds=step.timeout_seconds
        )

        if not result:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return {"success": True, "step_id": step.step_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.post("/{workflow_id}/publish")
async def publish_workflow(workflow_id: str):
    """Publish a workflow, making it active."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        success = service.publish_workflow(workflow_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot publish workflow")

        return {"success": True, "workflow_id": workflow_id, "status": "published"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to publish workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.post("/{workflow_id}/start")
async def start_workflow(workflow_id: str, request: WorkflowStartRequest):
    """Start a workflow instance."""
    try:
        from services.advanced_workflow_orchestration_service import (
            AdvancedWorkflowOrchestrationService, TriggerType
        )
        service = AdvancedWorkflowOrchestrationService()

        trigger_type = TriggerType(request.trigger_type)

        instance = await service.start_workflow(
            workflow_id=workflow_id,
            input_data=request.input_data,
            trigger_type=trigger_type
        )

        if not instance:
            raise HTTPException(status_code=400, detail="Failed to start workflow")

        return {
            "success": True,
            "instance": {
                "id": instance.id,
                "workflow_id": instance.workflow_id,
                "status": instance.status.value
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.get("/instances/{instance_id}")
async def get_workflow_instance(instance_id: str):
    """Get workflow instance status."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        instance = service.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        return {
            "instance": {
                "id": instance.id,
                "workflow_id": instance.workflow_id,
                "status": instance.status.value,
                "current_step": instance.current_step_id,
                "started_at": instance.started_at.isoformat(),
                "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
                "steps_executed": len(instance.step_executions)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get instance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.post("/instances/{instance_id}/pause")
async def pause_workflow_instance(instance_id: str):
    """Pause a running workflow instance."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        success = await service.pause_workflow(instance_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot pause instance")

        return {"success": True, "instance_id": instance_id, "status": "paused"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause instance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.post("/instances/{instance_id}/resume")
async def resume_workflow_instance(instance_id: str):
    """Resume a paused workflow instance."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        success = await service.resume_workflow(instance_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot resume instance")

        return {"success": True, "instance_id": instance_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume instance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@workflow_router.get("/{workflow_id}/stats")
async def get_workflow_stats(workflow_id: str):
    """Get statistics for a workflow."""
    try:
        from services.advanced_workflow_orchestration_service import AdvancedWorkflowOrchestrationService
        service = AdvancedWorkflowOrchestrationService()

        return service.get_workflow_stats(workflow_id)
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Predictive AI Routes
# =============================================================================

predictive_router = APIRouter(prefix="/api/v1/predictions")


class PredictionRequest(BaseModel):
    entity_type: str  # lead, loan, customer
    entity_id: str
    entity_data: Dict[str, Any]


class RecommendationRequest(BaseModel):
    entity_type: str
    entity_id: str
    entity_data: Dict[str, Any]


class AlertRequest(BaseModel):
    user_id: int
    portfolio_data: Dict[str, Any]


@predictive_router.post("/conversion")
async def predict_conversion(request: PredictionRequest):
    """Predict lead conversion probability."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        prediction = service.predict_conversion(
            lead_id=request.entity_id,
            lead_data=request.entity_data
        )

        return {
            "prediction": {
                "id": prediction.id,
                "type": prediction.prediction_type.value,
                "value": prediction.predicted_value,
                "probability": prediction.probability,
                "confidence": prediction.confidence,
                "factors": prediction.contributing_factors,
                "explanation": prediction.explanation
            }
        }
    except Exception as e:
        logger.error(f"Failed to predict conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/churn")
async def predict_churn(request: PredictionRequest):
    """Predict customer churn risk."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        prediction = service.predict_churn_risk(
            customer_id=request.entity_id,
            customer_data=request.entity_data
        )

        return {
            "prediction": {
                "id": prediction.id,
                "risk_level": prediction.predicted_value,
                "probability": prediction.probability,
                "confidence": prediction.confidence,
                "factors": prediction.contributing_factors,
                "explanation": prediction.explanation
            }
        }
    except Exception as e:
        logger.error(f"Failed to predict churn: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/contact-time")
async def predict_contact_time(request: PredictionRequest):
    """Predict optimal contact time for a lead."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        prediction = service.predict_optimal_contact_time(
            lead_id=request.entity_id,
            lead_data=request.entity_data
        )

        return {
            "prediction": {
                "id": prediction.id,
                "optimal_time": prediction.predicted_value,
                "confidence": prediction.confidence,
                "explanation": prediction.explanation
            }
        }
    except Exception as e:
        logger.error(f"Failed to predict contact time: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/deal-velocity")
async def predict_deal_velocity(request: PredictionRequest):
    """Predict deal velocity and closing timeline."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        prediction = service.predict_deal_velocity(
            loan_id=request.entity_id,
            loan_data=request.entity_data
        )

        return {
            "prediction": {
                "id": prediction.id,
                "velocity_data": prediction.predicted_value,
                "confidence": prediction.confidence,
                "risk_factors": prediction.contributing_factors,
                "explanation": prediction.explanation
            }
        }
    except Exception as e:
        logger.error(f"Failed to predict velocity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/loan-approval")
async def predict_loan_approval(request: PredictionRequest):
    """Predict loan approval probability."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        prediction = service.predict_loan_approval(
            loan_id=request.entity_id,
            loan_data=request.entity_data
        )

        return {
            "prediction": {
                "id": prediction.id,
                "likelihood": prediction.predicted_value,
                "probability": prediction.probability,
                "confidence": prediction.confidence,
                "factors": prediction.contributing_factors,
                "explanation": prediction.explanation
            }
        }
    except Exception as e:
        logger.error(f"Failed to predict approval: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/recommendations")
async def get_recommendations(request: RecommendationRequest):
    """Get next best action recommendations."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        recommendations = service.get_next_best_action(
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            entity_data=request.entity_data
        )

        return {
            "recommendations": [
                {
                    "id": r.id,
                    "type": r.recommendation_type.value,
                    "action": r.action,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority.value,
                    "impact_score": r.impact_score,
                    "expected_impact": r.expected_impact
                }
                for r in recommendations
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.post("/alerts/generate")
async def generate_proactive_alerts(request: AlertRequest):
    """Generate proactive alerts for a user."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        alerts = service.generate_proactive_alerts(
            user_id=request.user_id,
            portfolio_data=request.portfolio_data
        )

        return {
            "alerts": [
                {
                    "id": a.id,
                    "type": a.alert_type,
                    "title": a.title,
                    "message": a.message,
                    "priority": a.priority.value,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id
                }
                for a in alerts
            ]
        }
    except Exception as e:
        logger.error(f"Failed to generate alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictive_router.get("/alerts/{user_id}")
async def get_alerts(user_id: int):
    """Get alerts for a user."""
    try:
        from services.predictive_ai_service import PredictiveAIService
        service = PredictiveAIService()

        alerts = service.get_alerts(user_id)

        return {
            "alerts": [
                {
                    "id": a.id,
                    "type": a.alert_type,
                    "title": a.title,
                    "message": a.message,
                    "priority": a.priority.value,
                    "is_read": a.is_read
                }
                for a in alerts
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AI Agent Coordination Routes
# =============================================================================

agent_coordination_router = APIRouter(prefix="/api/v1/agents")


class AgentRegister(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    max_load: int = 10
    specializations: List[str] = []


class TaskSubmit(BaseModel):
    task_type: str
    input_data: Dict[str, Any]
    priority: str = "medium"  # critical, high, medium, low, background
    required_capabilities: List[str] = []
    preferred_agent_type: Optional[str] = None


class AgentMessage(BaseModel):
    from_agent_id: str
    to_agent_id: str
    message_type: str  # request, response, notification
    subject: str
    payload: Dict[str, Any]


class CollaborationStart(BaseModel):
    name: str
    goal: str
    agent_ids: List[str]
    lead_agent_id: Optional[str] = None


@agent_coordination_router.post("/register")
async def register_agent(agent: AgentRegister):
    """Register a new AI agent."""
    try:
        from services.ai_agent_coordination_service import (
            AIAgentCoordinationService, AgentType
        )
        service = AIAgentCoordinationService()

        agent_type = AgentType(agent.agent_type)

        result = service.register_agent(
            agent_id=agent.agent_id,
            name=agent.name,
            agent_type=agent_type,
            max_load=agent.max_load,
            specializations=agent.specializations
        )

        return {
            "success": True,
            "agent": {
                "id": result.id,
                "name": result.name,
                "type": result.agent_type.value
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.put("/{agent_id}/status")
async def update_agent_status(agent_id: str, status: str):
    """Update agent status."""
    try:
        from services.ai_agent_coordination_service import (
            AIAgentCoordinationService, AgentStatus
        )
        service = AIAgentCoordinationService()

        agent_status = AgentStatus(status)
        success = service.update_agent_status(agent_id, agent_status)

        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {"success": True, "agent_id": agent_id, "status": status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.post("/tasks")
async def submit_task(task: TaskSubmit):
    """Submit a task for agent execution."""
    try:
        from services.ai_agent_coordination_service import (
            AIAgentCoordinationService, TaskPriority, AgentType
        )
        service = AIAgentCoordinationService()

        priority_map = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
            "background": TaskPriority.BACKGROUND
        }
        priority = priority_map.get(task.priority, TaskPriority.MEDIUM)

        preferred_type = AgentType(task.preferred_agent_type) if task.preferred_agent_type else None

        result = await service.submit_task(
            task_type=task.task_type,
            input_data=task.input_data,
            priority=priority,
            required_capabilities=task.required_capabilities,
            preferred_agent_type=preferred_type
        )

        return {
            "success": True,
            "task": {
                "id": result.id,
                "type": result.task_type,
                "status": result.status.value,
                "assigned_to": result.assigned_agent_id
            }
        }
    except Exception as e:
        logger.error(f"Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status."""
    try:
        from services.ai_agent_coordination_service import AIAgentCoordinationService
        service = AIAgentCoordinationService()

        task = service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return {
            "task": {
                "id": task.id,
                "type": task.task_type,
                "status": task.status.value,
                "assigned_to": task.assigned_agent_id,
                "output": task.output_data if task.status.value == "completed" else None,
                "error": task.error
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.post("/messages")
async def send_agent_message(message: AgentMessage):
    """Send a message between agents."""
    try:
        from services.ai_agent_coordination_service import (
            AIAgentCoordinationService, CommunicationType
        )
        service = AIAgentCoordinationService()

        msg_type = CommunicationType(message.message_type)

        result = service.send_message(
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            message_type=msg_type,
            subject=message.subject,
            payload=message.payload
        )

        return {
            "success": True,
            "message_id": result.id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.post("/collaborations")
async def start_collaboration(collab: CollaborationStart):
    """Start a collaboration session between agents."""
    try:
        from services.ai_agent_coordination_service import AIAgentCoordinationService
        service = AIAgentCoordinationService()

        session = service.start_collaboration(
            name=collab.name,
            goal=collab.goal,
            agent_ids=collab.agent_ids,
            lead_agent_id=collab.lead_agent_id
        )

        return {
            "success": True,
            "collaboration": {
                "id": session.id,
                "name": session.name,
                "participants": session.participating_agents,
                "lead": session.lead_agent_id
            }
        }
    except Exception as e:
        logger.error(f"Failed to start collaboration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.get("/status")
async def get_system_status():
    """Get overall agent system status."""
    try:
        from services.ai_agent_coordination_service import AIAgentCoordinationService
        service = AIAgentCoordinationService()

        return service.get_system_status()
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_coordination_router.get("/performance")
async def get_all_agent_performance():
    """Get performance metrics for all agents."""
    try:
        from services.ai_agent_coordination_service import AIAgentCoordinationService
        service = AIAgentCoordinationService()

        return {"agents": service.get_all_agents_summary()}
    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Self-Healing System Routes
# =============================================================================

healing_router = APIRouter(prefix="/api/v1/healing")


class ComponentRegister(BaseModel):
    component_id: str
    component_type: str  # api, database, cache, queue, external_api, ai_service, storage
    name: str
    critical: bool = False
    dependencies: List[str] = []


class ErrorReport(BaseModel):
    component_id: str
    error_type: str
    error_message: str
    stack_trace: str = ""
    details: Dict[str, Any] = {}
    severity: Optional[str] = None


class IncidentResolve(BaseModel):
    resolution: str
    root_cause: str = ""


class PlaybookCreate(BaseModel):
    id: str
    name: str
    description: str
    trigger_error_types: List[str] = []
    trigger_component_types: List[str] = []
    actions: List[Dict[str, Any]] = []
    max_retries: int = 3
    escalate_on_failure: bool = True


@healing_router.post("/components/register")
async def register_component(component: ComponentRegister):
    """Register a component for health monitoring."""
    try:
        from services.self_healing_system_service import (
            SelfHealingSystemService, ComponentType
        )
        service = SelfHealingSystemService()

        comp_type = ComponentType(component.component_type)

        service.register_component(
            component_id=component.component_id,
            component_type=comp_type,
            name=component.name,
            critical=component.critical,
            dependencies=component.dependencies
        )

        return {
            "success": True,
            "component_id": component.component_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to register component: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/health")
async def get_system_health():
    """Get overall system health status."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        return service.get_system_health()
    except Exception as e:
        logger.error(f"Failed to get health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/health/check")
async def run_health_check(component_id: Optional[str] = None):
    """Run health check for component(s)."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        results = await service.check_health(component_id)

        return {
            "results": {
                cid: {
                    "status": h.status.value,
                    "message": h.message,
                    "response_time_ms": h.response_time_ms
                }
                for cid, h in results.items()
            }
        }
    except Exception as e:
        logger.error(f"Failed to run health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/errors/report")
async def report_error(error: ErrorReport):
    """Report an error and trigger incident handling."""
    try:
        from services.self_healing_system_service import (
            SelfHealingSystemService, IncidentSeverity
        )
        service = SelfHealingSystemService()

        severity = IncidentSeverity(error.severity) if error.severity else None

        incident = await service.report_error(
            component_id=error.component_id,
            error_type=error.error_type,
            error_message=error.error_message,
            stack_trace=error.stack_trace,
            details=error.details,
            severity=severity
        )

        return {
            "success": True,
            "incident": {
                "id": incident.id,
                "severity": incident.severity.value,
                "status": incident.status.value
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/incidents")
async def get_active_incidents():
    """Get all active incidents."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        incidents = service.get_active_incidents()

        return {
            "incidents": [
                {
                    "id": i.id,
                    "title": i.title,
                    "severity": i.severity.value,
                    "status": i.status.value,
                    "affected_components": i.affected_components,
                    "detected_at": i.detected_at.isoformat(),
                    "healing_attempts": i.healing_attempts,
                    "auto_healed": i.auto_healed
                }
                for i in incidents
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        incident = service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "incident": {
                "id": incident.id,
                "title": incident.title,
                "description": incident.description,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "error_type": incident.error_type,
                "error_message": incident.error_message,
                "affected_components": incident.affected_components,
                "detected_at": incident.detected_at.isoformat(),
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "healing_actions": incident.healing_actions_taken,
                "auto_healed": incident.auto_healed,
                "resolution": incident.resolution,
                "root_cause": incident.root_cause
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str):
    """Acknowledge an incident."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        success = service.acknowledge_incident(incident_id)
        if not success:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {"success": True, "incident_id": incident_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, resolution: IncidentResolve):
    """Manually resolve an incident."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        success = service.resolve_incident(
            incident_id,
            resolution.resolution,
            resolution.root_cause
        )

        if not success:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {"success": True, "incident_id": incident_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/circuit-breakers/{component_id}")
async def get_circuit_breaker(component_id: str):
    """Get circuit breaker status for a component."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        status = service.get_circuit_breaker_status(component_id)
        if not status:
            raise HTTPException(status_code=404, detail="Component not found")

        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get circuit breaker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/circuit-breakers/{component_id}/reset")
async def reset_circuit_breaker(component_id: str):
    """Reset a circuit breaker."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        success = service.reset_circuit_breaker(component_id)
        if not success:
            raise HTTPException(status_code=404, detail="Component not found")

        return {"success": True, "component_id": component_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/playbooks")
async def list_playbooks():
    """List all healing playbooks."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        return {"playbooks": service.list_playbooks()}
    except Exception as e:
        logger.error(f"Failed to list playbooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.post("/playbooks")
async def create_playbook(playbook: PlaybookCreate):
    """Create a healing playbook."""
    try:
        from services.self_healing_system_service import (
            SelfHealingSystemService, HealingPlaybook, ComponentType
        )
        service = SelfHealingSystemService()

        comp_types = [ComponentType(t) for t in playbook.trigger_component_types]

        pb = HealingPlaybook(
            id=playbook.id,
            name=playbook.name,
            description=playbook.description,
            trigger_error_types=playbook.trigger_error_types,
            trigger_component_types=comp_types,
            actions=playbook.actions,
            max_retries=playbook.max_retries,
            escalate_on_failure=playbook.escalate_on_failure
        )

        service.add_playbook(pb)

        return {"success": True, "playbook_id": playbook.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/metrics")
async def get_healing_metrics():
    """Get self-healing metrics."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        return service.get_healing_metrics()
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@healing_router.get("/summary")
async def get_incident_summary(days: int = Query(default=7, le=30)):
    """Get incident summary for past N days."""
    try:
        from services.self_healing_system_service import SelfHealingSystemService
        service = SelfHealingSystemService()

        return service.get_incident_summary(days)
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
