"""
Phase 4 API Routes
A/B Testing for Voice, AI Learning, and Continuous Improvement
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

# Import services
from services.voice_ab_testing_service import (
    voice_ab_testing_service,
    VoiceExperimentType,
    VoiceMetric
)
from services.conversation_ai_learning_service import (
    conversation_ai_learning_service,
    ConversationOutcome,
    LearningDataType
)
from services.continuous_learning_meta_agent import continuous_learning_meta_agent


# =============================================================================
# Voice A/B Testing Router
# =============================================================================
voice_ab_router = APIRouter(prefix="/api/v1/voice-ab")


class VoiceExperimentCreate(BaseModel):
    """Request to create a voice A/B experiment"""
    name: str
    description: str
    experiment_type: str = Field(..., description="greeting, script, voice_persona, call_flow")
    primary_metric: str = Field(..., description="call_success_rate, booking_conversion, etc.")
    variants: List[Dict[str, Any]]
    secondary_metrics: Optional[List[str]] = None
    target_percentage: float = 100.0
    min_calls: int = 100
    target_phone_patterns: Optional[List[str]] = None
    target_time_windows: Optional[List[Dict]] = None


class CallResultRecord(BaseModel):
    """Request to record a call result"""
    experiment_id: str
    variant_id: str
    call_id: str
    caller_phone: str
    call_success: bool = False
    booking_made: bool = False
    transferred: bool = False
    call_duration_seconds: int = 0
    satisfaction_score: Optional[float] = None
    voicemail_left: bool = False
    callback_requested: bool = False
    escalated: bool = False
    hang_up_early: bool = False
    caller_state: Optional[str] = None


@voice_ab_router.post("/experiments")
async def create_voice_experiment(request: VoiceExperimentCreate):
    """Create a new voice A/B test experiment"""
    try:
        experiment_type = VoiceExperimentType(request.experiment_type)
        primary_metric = VoiceMetric(request.primary_metric)
        secondary_metrics = [VoiceMetric(m) for m in (request.secondary_metrics or [])]

        experiment = voice_ab_testing_service.create_experiment(
            name=request.name,
            description=request.description,
            experiment_type=experiment_type,
            primary_metric=primary_metric,
            variants=request.variants,
            secondary_metrics=secondary_metrics,
            target_percentage=request.target_percentage,
            min_calls=request.min_calls,
            target_phone_patterns=request.target_phone_patterns,
            target_time_windows=request.target_time_windows
        )

        return {
            "status": "success",
            "experiment_id": experiment.id,
            "name": experiment.name,
            "variants_count": len(experiment.variants),
            "message": f"Experiment '{experiment.name}' created successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating voice experiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@voice_ab_router.post("/experiments/{experiment_id}/start")
async def start_voice_experiment(experiment_id: str):
    """Start a voice A/B test experiment"""
    success = voice_ab_testing_service.start_experiment(experiment_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start experiment")

    return {"status": "success", "message": f"Experiment {experiment_id} started"}


@voice_ab_router.post("/experiments/{experiment_id}/stop")
async def stop_voice_experiment(
    experiment_id: str,
    declare_winner: bool = True
):
    """Stop a voice A/B test experiment"""
    result = voice_ab_testing_service.stop_experiment(experiment_id, declare_winner)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return result


@voice_ab_router.get("/experiments/{experiment_id}")
async def get_voice_experiment(experiment_id: str):
    """Get voice experiment details and analysis"""
    analysis = voice_ab_testing_service.get_experiment_analysis(experiment_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return analysis


@voice_ab_router.get("/variant")
async def get_variant_for_call(
    caller_phone: str,
    experiment_type: Optional[str] = None,
    area_code: Optional[str] = None,
    state: Optional[str] = None
):
    """Get the active experiment variant for an incoming call"""
    exp_type = VoiceExperimentType(experiment_type) if experiment_type else None

    context = {}
    if area_code:
        context["area_code"] = area_code
    if state:
        context["state"] = state

    variant = voice_ab_testing_service.get_active_variant_for_call(
        caller_phone=caller_phone,
        experiment_type=exp_type,
        call_context=context if context else None
    )

    if not variant:
        return {"variant": None, "message": "No active experiment for this call"}

    return {"variant": variant}


@voice_ab_router.post("/results")
async def record_call_result(request: CallResultRecord):
    """Record the result of a call in an experiment"""
    success = voice_ab_testing_service.record_call_result(
        experiment_id=request.experiment_id,
        variant_id=request.variant_id,
        call_id=request.call_id,
        caller_phone=request.caller_phone,
        call_success=request.call_success,
        booking_made=request.booking_made,
        transferred=request.transferred,
        call_duration_seconds=request.call_duration_seconds,
        satisfaction_score=request.satisfaction_score,
        voicemail_left=request.voicemail_left,
        callback_requested=request.callback_requested,
        escalated=request.escalated,
        hang_up_early=request.hang_up_early,
        caller_state=request.caller_state
    )

    return {"status": "success" if success else "failed", "recorded": success}


@voice_ab_router.get("/templates/greetings")
async def get_greeting_templates():
    """Get sample greeting variants for A/B testing"""
    return {"greetings": voice_ab_testing_service.get_greeting_variants()}


@voice_ab_router.get("/templates/voices")
async def get_voice_persona_templates():
    """Get sample voice persona variants for A/B testing"""
    return {"voices": voice_ab_testing_service.get_voice_persona_variants()}


# =============================================================================
# AI Learning Router
# =============================================================================
ai_learning_router = APIRouter(prefix="/api/v1/ai-learning")


class ConversationAnalysisRequest(BaseModel):
    """Request to analyze a conversation"""
    conversation_id: str
    messages: List[Dict[str, str]]
    outcome: str = Field(..., description="success, partial_success, failure, escalated, abandoned")
    caller_satisfaction: Optional[float] = None
    metadata: Optional[Dict] = None


class CorrectionRequest(BaseModel):
    """Request to add a correction"""
    original_query: str
    incorrect_response: str
    correct_response: str
    explanation: Optional[str] = None
    source_conversation_id: Optional[str] = None


class KnowledgeGapResolution(BaseModel):
    """Request to resolve a knowledge gap"""
    gap_id: str
    resolution_content: str
    add_to_knowledge_base: bool = True


@ai_learning_router.post("/analyze")
async def analyze_conversation(request: ConversationAnalysisRequest):
    """Analyze a conversation for learning opportunities"""
    try:
        outcome = ConversationOutcome(request.outcome)

        analysis = conversation_ai_learning_service.analyze_conversation(
            conversation_id=request.conversation_id,
            messages=request.messages,
            outcome=outcome,
            caller_satisfaction=request.caller_satisfaction,
            metadata=request.metadata
        )

        return {
            "conversation_id": analysis.conversation_id,
            "outcome": analysis.outcome.value,
            "quality_score": round(analysis.quality_score, 3),
            "failure_reasons": [r.value for r in analysis.failure_reasons],
            "knowledge_gaps": analysis.knowledge_gaps_identified,
            "extracted_intents": analysis.extracted_intents,
            "recommendations": analysis.recommendations
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ai_learning_router.get("/training-data")
async def get_training_data(
    data_type: Optional[str] = None,
    min_quality: float = 0.8,
    approved_only: bool = True,
    limit: int = 100
):
    """Get training examples for fine-tuning"""
    dtype = LearningDataType(data_type) if data_type else None

    dataset = conversation_ai_learning_service.get_training_dataset(
        data_type=dtype,
        min_quality=min_quality,
        approved_only=approved_only,
        limit=limit
    )

    return {
        "count": len(dataset),
        "examples": dataset
    }


@ai_learning_router.get("/knowledge-gaps")
async def get_knowledge_gaps(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    min_frequency: int = 1
):
    """Get identified knowledge gaps"""
    gaps = conversation_ai_learning_service.get_knowledge_gaps(
        status=status,
        priority=priority,
        min_frequency=min_frequency
    )

    return {
        "count": len(gaps),
        "gaps": [
            {
                "id": g.id,
                "topic": g.topic,
                "description": g.description,
                "frequency": g.frequency,
                "priority": g.priority,
                "status": g.status,
                "example_queries": g.example_queries[:3]
            }
            for g in gaps
        ]
    }


@ai_learning_router.post("/knowledge-gaps/resolve")
async def resolve_knowledge_gap(request: KnowledgeGapResolution):
    """Resolve a knowledge gap with content"""
    success = conversation_ai_learning_service.resolve_knowledge_gap(
        gap_id=request.gap_id,
        resolution_content=request.resolution_content,
        add_to_knowledge_base=request.add_to_knowledge_base
    )

    if not success:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")

    return {"status": "success", "message": f"Knowledge gap {request.gap_id} resolved"}


@ai_learning_router.post("/corrections")
async def add_correction(request: CorrectionRequest):
    """Add a correction for an incorrect AI response"""
    example = conversation_ai_learning_service.add_correction(
        original_query=request.original_query,
        incorrect_response=request.incorrect_response,
        correct_response=request.correct_response,
        explanation=request.explanation,
        source_conversation_id=request.source_conversation_id
    )

    return {
        "status": "success",
        "correction_id": example.id,
        "message": "Correction added successfully"
    }


@ai_learning_router.get("/report")
async def get_improvement_report(days: int = 30):
    """Get AI improvement report"""
    report = conversation_ai_learning_service.get_improvement_report(days=days)
    return report


@ai_learning_router.post("/models")
async def create_model_version(
    version: str,
    base_model: str,
    notes: str = ""
):
    """Create a new model version for tracking"""
    model = conversation_ai_learning_service.create_model_version(
        version=version,
        base_model=base_model,
        notes=notes
    )

    return {
        "status": "success",
        "version": model.version,
        "base_model": model.base_model
    }


@ai_learning_router.post("/models/{version}/prepare-fine-tuning")
async def prepare_fine_tuning(version: str, min_examples: int = 100):
    """Prepare a fine-tuning job for a model version"""
    job = conversation_ai_learning_service.prepare_fine_tuning_job(
        model_version=version,
        min_examples=min_examples
    )

    if not job:
        raise HTTPException(
            status_code=400,
            detail="Insufficient training data or model version not found"
        )

    return job


# =============================================================================
# Continuous Learning Meta-Agent Router
# =============================================================================
meta_agent_router = APIRouter(prefix="/api/v1/meta-agent")


@meta_agent_router.post("/learning-cycle")
async def run_learning_cycle(period_hours: int = 24):
    """Run a complete learning cycle"""
    report = continuous_learning_meta_agent.run_learning_cycle(period_hours=period_hours)

    return {
        "cycle_id": report.cycle_id,
        "started_at": report.started_at.isoformat(),
        "completed_at": report.completed_at.isoformat(),
        "opportunities_identified": len(report.opportunities_identified),
        "actions_taken": len(report.actions_taken),
        "recommendations": report.recommendations,
        "next_cycle": report.next_cycle_scheduled.isoformat()
    }


@meta_agent_router.get("/dashboard")
async def get_performance_dashboard():
    """Get real-time performance dashboard"""
    return continuous_learning_meta_agent.get_performance_dashboard()


@meta_agent_router.post("/analyze-failures")
async def analyze_failed_conversations(conversations: List[Dict[str, Any]]):
    """Analyze a batch of failed conversations for patterns"""
    analysis = continuous_learning_meta_agent.analyze_failed_conversations(conversations)
    return analysis


@meta_agent_router.get("/opportunities")
async def get_improvement_opportunities(
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """Get identified improvement opportunities"""
    opportunities = list(continuous_learning_meta_agent._opportunities.values())

    if status:
        opportunities = [o for o in opportunities if o.status == status]
    if priority:
        opportunities = [o for o in opportunities if o.priority.value == priority]

    return {
        "count": len(opportunities),
        "opportunities": [
            {
                "id": o.id,
                "title": o.title,
                "description": o.description,
                "action_type": o.action_type.value,
                "priority": o.priority.value,
                "confidence": o.confidence,
                "status": o.status,
                "auto_executable": o.auto_executable,
                "impact_estimate": o.impact_estimate
            }
            for o in opportunities
        ]
    }


@meta_agent_router.post("/opportunities/{opportunity_id}/approve")
async def approve_opportunity(opportunity_id: str):
    """Approve an improvement opportunity"""
    success = continuous_learning_meta_agent.approve_opportunity(opportunity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {"status": "success", "message": f"Opportunity {opportunity_id} approved"}


@meta_agent_router.post("/opportunities/{opportunity_id}/reject")
async def reject_opportunity(opportunity_id: str, reason: str):
    """Reject an improvement opportunity"""
    success = continuous_learning_meta_agent.reject_opportunity(opportunity_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {"status": "success", "message": f"Opportunity {opportunity_id} rejected"}


@meta_agent_router.get("/suggest-ab-test")
async def suggest_ab_test(opportunity_id: Optional[str] = None):
    """Get A/B test suggestion based on opportunities"""
    suggestion = continuous_learning_meta_agent.suggest_ab_test(opportunity_id)

    if not suggestion:
        return {"suggestion": None, "message": "No suitable opportunities for A/B testing"}

    return {"suggestion": suggestion}


@meta_agent_router.get("/knowledge-base-suggestions")
async def get_knowledge_base_suggestions():
    """Get AI-generated knowledge base update suggestions"""
    suggestions = continuous_learning_meta_agent.get_knowledge_base_suggestions()
    return {"count": len(suggestions), "suggestions": suggestions}


@meta_agent_router.put("/thresholds/{metric}")
async def update_threshold(metric: str, value: float):
    """Update a performance threshold"""
    success = continuous_learning_meta_agent.set_threshold(metric, value)
    if not success:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")

    return {"status": "success", "message": f"Threshold {metric} set to {value}"}


@meta_agent_router.get("/thresholds")
async def get_thresholds():
    """Get all performance thresholds"""
    return {"thresholds": continuous_learning_meta_agent._thresholds}
