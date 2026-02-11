"""
Phase 5 Routes: Premium Features & White-Label

Includes routes for:
- Live Agent Escalation Network
- Call Quality Assurance
- Voice Biometrics
- White-Label & Multi-Tenant Management
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Header
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Live Agent Escalation Routes
# =============================================================================

escalation_router = APIRouter(prefix="/api/v1/escalation")


class AgentRegistration(BaseModel):
    agent_id: str
    name: str
    email: str
    phone: Optional[str] = None
    skills: List[str] = []
    languages: List[str] = ["en"]
    max_concurrent_calls: int = 3


class EscalationRequest(BaseModel):
    call_id: str
    caller_phone: str
    reason: str
    priority: Optional[str] = "normal"
    context: Optional[Dict[str, Any]] = None
    preferred_skills: Optional[List[str]] = None


class EscalationTriggerCheck(BaseModel):
    call_id: str
    message: str
    sentiment_score: Optional[float] = None
    time_elapsed_seconds: Optional[int] = None
    failure_count: Optional[int] = None


@escalation_router.post("/agents/register")
async def register_agent(registration: AgentRegistration):
    """Register a live agent in the escalation network."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        agent = service.register_agent(
            agent_id=registration.agent_id,
            name=registration.name,
            email=registration.email,
            phone=registration.phone,
            skills=registration.skills,
            languages=registration.languages,
            max_concurrent_calls=registration.max_concurrent_calls
        )

        return {
            "success": True,
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status.value,
                "skills": agent.skills
            }
        }
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.put("/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, status: str):
    """Update agent availability status."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        success = service.update_agent_status(agent_id, status)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {"success": True, "agent_id": agent_id, "new_status": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.post("/check-triggers")
async def check_escalation_triggers(check: EscalationTriggerCheck):
    """Check if escalation should be triggered."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        should_escalate, trigger = service.check_escalation_triggers(
            call_id=check.call_id,
            message=check.message,
            sentiment_score=check.sentiment_score,
            time_elapsed_seconds=check.time_elapsed_seconds,
            failure_count=check.failure_count
        )

        return {
            "should_escalate": should_escalate,
            "trigger": trigger
        }
    except Exception as e:
        logger.error(f"Failed to check triggers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.post("/request")
async def request_escalation(request: EscalationRequest):
    """Request escalation to a live agent."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        success, result = await service.request_escalation(
            call_id=request.call_id,
            caller_phone=request.caller_phone,
            reason=request.reason,
            priority=request.priority,
            context=request.context,
            preferred_skills=request.preferred_skills
        )

        return {
            "success": success,
            "escalation_id": result.id if hasattr(result, 'id') else None,
            "assigned_agent": result.assigned_agent_id if hasattr(result, 'assigned_agent_id') else None,
            "status": result.status.value if hasattr(result, 'status') else "error",
            "message": str(result) if not success else "Escalation requested"
        }
    except Exception as e:
        logger.error(f"Failed to request escalation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.post("/escalations/{escalation_id}/complete")
async def complete_escalation(
    escalation_id: str,
    resolution: str,
    notes: Optional[str] = None
):
    """Complete an escalation with resolution."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        success = service.complete_escalation(escalation_id, resolution, notes)
        if not success:
            raise HTTPException(status_code=404, detail="Escalation not found")

        return {"success": True, "escalation_id": escalation_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete escalation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.get("/dashboard")
async def get_escalation_dashboard():
    """Get escalation network dashboard."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        return service.get_agent_dashboard()
    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@escalation_router.get("/queue")
async def get_escalation_queue():
    """Get current escalation queue."""
    try:
        from services.live_agent_escalation_service import LiveAgentEscalationService
        service = LiveAgentEscalationService()

        return service.get_queue_status()
    except Exception as e:
        logger.error(f"Failed to get queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Call Quality Assurance Routes
# =============================================================================

qa_router = APIRouter(prefix="/api/v1/qa")


class QAReviewRequest(BaseModel):
    call_id: str
    call_date: str  # ISO format
    duration_seconds: int
    agent_id: Optional[str] = None
    priority: str = "normal"
    review_type: str = "standard"


class QAHumanReview(BaseModel):
    review_id: str
    reviewer_id: int
    scores: Dict[str, float]  # criterion -> score
    comments: Dict[str, str] = {}  # criterion -> comment
    overall_comment: Optional[str] = None
    coaching_notes: Optional[str] = None


class QATranscript(BaseModel):
    call_id: str
    transcript: List[Dict[str, Any]]  # [{speaker, text, timestamp}, ...]
    metadata: Optional[Dict[str, Any]] = None


@qa_router.post("/score/automated")
async def score_call_automated(data: QATranscript):
    """Score a call using automated AI analysis."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        scorecard = service.score_call_automated(
            call_id=data.call_id,
            transcript=data.transcript,
            metadata=data.metadata or {}
        )

        return {
            "success": True,
            "scorecard": {
                "id": scorecard.id,
                "call_id": scorecard.call_id,
                "overall_score": scorecard.overall_score,
                "grade": scorecard.grade,
                "scores": scorecard.scores,
                "recommendations": scorecard.recommendations,
                "strengths": scorecard.strengths,
                "improvements": scorecard.improvements
            }
        }
    except Exception as e:
        logger.error(f"Failed to score call: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.post("/reviews/create")
async def create_review_request(request: QAReviewRequest):
    """Create a human review request for a call."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        review = service.create_review_request(
            call_id=request.call_id,
            call_date=datetime.fromisoformat(request.call_date),
            duration_seconds=request.duration_seconds,
            agent_id=request.agent_id,
            priority=request.priority,
            review_type=request.review_type
        )

        return {
            "success": True,
            "review": {
                "id": review.id,
                "call_id": review.call_id,
                "status": review.status.value,
                "priority": review.priority
            }
        }
    except Exception as e:
        logger.error(f"Failed to create review: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.post("/reviews/submit")
async def submit_human_review(review: QAHumanReview):
    """Submit a human review for a call."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        success, scorecard = service.submit_human_review(
            review_id=review.review_id,
            reviewer_id=review.reviewer_id,
            scores=review.scores,
            comments=review.comments,
            overall_comment=review.overall_comment,
            coaching_notes=review.coaching_notes
        )

        if not success:
            raise HTTPException(status_code=404, detail="Review not found")

        return {
            "success": True,
            "scorecard": {
                "id": scorecard.id,
                "overall_score": scorecard.overall_score,
                "grade": scorecard.grade
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit review: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.get("/reviews/pending")
async def get_pending_reviews(
    limit: int = Query(default=20, le=100),
    priority: Optional[str] = None
):
    """Get pending human reviews."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        reviews = service.get_pending_reviews(limit=limit, priority=priority)

        return {
            "count": len(reviews),
            "reviews": [
                {
                    "id": r.id,
                    "call_id": r.call_id,
                    "call_date": r.call_date.isoformat(),
                    "priority": r.priority,
                    "review_type": r.review_type,
                    "created_at": r.created_at.isoformat()
                }
                for r in reviews
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get pending reviews: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.get("/scorecards/{call_id}")
async def get_call_scorecard(call_id: str):
    """Get scorecard for a specific call."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        scorecard = service.get_scorecard(call_id)
        if not scorecard:
            raise HTTPException(status_code=404, detail="Scorecard not found")

        return {
            "scorecard": {
                "id": scorecard.id,
                "call_id": scorecard.call_id,
                "overall_score": scorecard.overall_score,
                "grade": scorecard.grade,
                "scores": scorecard.scores,
                "recommendations": scorecard.recommendations,
                "reviewed_by": scorecard.reviewed_by,
                "review_date": scorecard.review_date.isoformat() if scorecard.review_date else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scorecard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.get("/calibration")
async def get_calibration_report():
    """Get AI vs Human scoring calibration report."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        return service.get_calibration_report()
    except Exception as e:
        logger.error(f"Failed to get calibration report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@qa_router.get("/agent/{agent_id}/performance")
async def get_agent_performance(agent_id: str, days: int = Query(default=30, le=90)):
    """Get QA performance metrics for an agent."""
    try:
        from services.call_quality_assurance_service import CallQualityAssuranceService
        service = CallQualityAssuranceService()

        return service.get_agent_performance(agent_id, days)
    except Exception as e:
        logger.error(f"Failed to get agent performance: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Voice Biometrics Routes
# =============================================================================

biometrics_router = APIRouter(prefix="/api/v1/biometrics")


class VoiceprintEnrollment(BaseModel):
    caller_id: str
    phone_number: str
    audio_data: str  # Base64 encoded audio
    caller_name: Optional[str] = None
    consent_given: bool = True


class VoiceprintVerification(BaseModel):
    voiceprint_id: str
    audio_data: str  # Base64 encoded audio


class CallerRecognition(BaseModel):
    phone_number: str
    audio_data: Optional[str] = None  # Base64 encoded audio


@biometrics_router.post("/enroll")
async def enroll_voiceprint(enrollment: VoiceprintEnrollment):
    """Enroll a new voiceprint for a caller."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        success, voiceprint = service.enroll_voiceprint(
            caller_id=enrollment.caller_id,
            phone_number=enrollment.phone_number,
            audio_data=enrollment.audio_data,
            caller_name=enrollment.caller_name,
            consent_given=enrollment.consent_given
        )

        return {
            "success": success,
            "voiceprint": {
                "id": voiceprint.id,
                "caller_id": voiceprint.caller_id,
                "status": voiceprint.status.value,
                "quality_score": voiceprint.quality_score
            } if voiceprint else None
        }
    except Exception as e:
        logger.error(f"Failed to enroll voiceprint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@biometrics_router.post("/verify")
async def verify_voiceprint(verification: VoiceprintVerification):
    """Verify a caller against their enrolled voiceprint."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        result, confidence = service.verify_caller(
            voiceprint_id=verification.voiceprint_id,
            audio_data=verification.audio_data
        )

        return {
            "result": result.value,
            "confidence": confidence,
            "verified": result.value in ["verified", "high_confidence"]
        }
    except Exception as e:
        logger.error(f"Failed to verify voiceprint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@biometrics_router.post("/recognize")
async def recognize_caller(recognition: CallerRecognition):
    """Recognize a caller by phone number and/or voice."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        result, profile, confidence = service.recognize_caller(
            phone_number=recognition.phone_number,
            audio_data=recognition.audio_data
        )

        return {
            "result": result.value,
            "confidence": confidence,
            "caller": {
                "id": profile.caller_id,
                "name": profile.name,
                "total_calls": profile.total_calls,
                "is_verified": profile.is_verified
            } if profile else None
        }
    except Exception as e:
        logger.error(f"Failed to recognize caller: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@biometrics_router.get("/voiceprint/{voiceprint_id}")
async def get_voiceprint(voiceprint_id: str):
    """Get voiceprint details."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        voiceprint = service.get_voiceprint(voiceprint_id)
        if not voiceprint:
            raise HTTPException(status_code=404, detail="Voiceprint not found")

        return {
            "voiceprint": {
                "id": voiceprint.id,
                "caller_id": voiceprint.caller_id,
                "status": voiceprint.status.value,
                "quality_score": voiceprint.quality_score,
                "created_at": voiceprint.created_at.isoformat(),
                "last_used_at": voiceprint.last_used_at.isoformat() if voiceprint.last_used_at else None,
                "verification_count": voiceprint.verification_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get voiceprint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@biometrics_router.delete("/voiceprint/{voiceprint_id}")
async def delete_voiceprint(voiceprint_id: str):
    """Delete a voiceprint (for GDPR compliance, etc.)."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        success = service.delete_voiceprint(voiceprint_id)
        if not success:
            raise HTTPException(status_code=404, detail="Voiceprint not found")

        return {"success": True, "deleted": voiceprint_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete voiceprint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@biometrics_router.get("/caller/{caller_id}/profile")
async def get_caller_profile(caller_id: str):
    """Get caller profile with all associated data."""
    try:
        from services.voice_biometrics_service import VoiceBiometricsService
        service = VoiceBiometricsService()

        profile = service.get_caller_profile(caller_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Caller not found")

        return {
            "profile": {
                "caller_id": profile.caller_id,
                "name": profile.name,
                "phone_numbers": profile.phone_numbers,
                "total_calls": profile.total_calls,
                "is_verified": profile.is_verified,
                "trust_level": profile.trust_level,
                "first_seen": profile.first_seen.isoformat(),
                "last_seen": profile.last_seen.isoformat() if profile.last_seen else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get caller profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# White-Label & Multi-Tenant Routes
# =============================================================================

tenant_router = APIRouter(prefix="/api/v1/tenants")


class TenantCreate(BaseModel):
    name: str
    tier: str = "starter"  # starter, professional, enterprise, custom
    primary_contact_email: str
    primary_contact_name: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    trial_days: int = 14
    custom_limits: Optional[Dict[str, int]] = None
    initial_branding: Optional[Dict[str, str]] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    billing_email: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class BrandingUpdate(BaseModel):
    branding_type: str  # voice, script, visual, email, sms
    config: Dict[str, Any]


class TierUpgrade(BaseModel):
    new_tier: str
    custom_limits: Optional[Dict[str, int]] = None


@tenant_router.post("/")
async def create_tenant(tenant: TenantCreate):
    """Create a new tenant."""
    try:
        from services.white_label_multi_tenant_service import (
            WhiteLabelMultiTenantService, TenantTier
        )
        service = WhiteLabelMultiTenantService()

        tier = TenantTier(tenant.tier)

        success, new_tenant = service.create_tenant(
            name=tenant.name,
            tier=tier,
            primary_contact_email=tenant.primary_contact_email,
            primary_contact_name=tenant.primary_contact_name or "",
            primary_contact_phone=tenant.primary_contact_phone or "",
            trial_days=tenant.trial_days,
            custom_limits=tenant.custom_limits,
            initial_branding=tenant.initial_branding
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to create tenant")

        return {
            "success": True,
            "tenant": {
                "id": new_tenant.id,
                "name": new_tenant.name,
                "slug": new_tenant.slug,
                "tier": new_tenant.tier.value,
                "status": new_tenant.status.value,
                "api_key": new_tenant.metadata.get("api_key")  # Only returned on creation
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Failed to create tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get tenant details."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        tenant = service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "tier": tenant.tier.value,
                "status": tenant.status.value,
                "created_at": tenant.created_at.isoformat(),
                "primary_contact_email": tenant.primary_contact_email,
                "sla_tier": tenant.sla_tier
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.put("/{tenant_id}")
async def update_tenant(tenant_id: str, updates: TenantUpdate):
    """Update tenant details."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        update_dict = {k: v for k, v in updates.dict().items() if v is not None}
        success, tenant = service.update_tenant(tenant_id, update_dict)

        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {"success": True, "tenant_id": tenant_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.post("/{tenant_id}/upgrade")
async def upgrade_tenant(tenant_id: str, upgrade: TierUpgrade):
    """Upgrade tenant to a higher tier."""
    try:
        from services.white_label_multi_tenant_service import (
            WhiteLabelMultiTenantService, TenantTier
        )
        service = WhiteLabelMultiTenantService()

        new_tier = TenantTier(upgrade.new_tier)
        success, tenant = service.upgrade_tenant_tier(
            tenant_id=tenant_id,
            new_tier=new_tier,
            custom_limits=upgrade.custom_limits
        )

        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {
            "success": True,
            "tenant_id": tenant_id,
            "new_tier": new_tier.value
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upgrade tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.post("/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, reason: str = ""):
    """Suspend a tenant account."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        success = service.suspend_tenant(tenant_id, reason)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {"success": True, "tenant_id": tenant_id, "status": "suspended"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to suspend tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.post("/{tenant_id}/reactivate")
async def reactivate_tenant(tenant_id: str):
    """Reactivate a suspended tenant."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        success = service.reactivate_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot reactivate tenant")

        return {"success": True, "tenant_id": tenant_id, "status": "active"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reactivate tenant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.put("/{tenant_id}/branding")
async def update_branding(tenant_id: str, branding: BrandingUpdate):
    """Update tenant branding configuration."""
    try:
        from services.white_label_multi_tenant_service import (
            WhiteLabelMultiTenantService, BrandingType
        )
        service = WhiteLabelMultiTenantService()

        branding_type = BrandingType(branding.branding_type)
        success, config = service.update_branding(
            tenant_id=tenant_id,
            branding_type=branding_type,
            config=branding.config
        )

        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {"success": True, "branding_type": branding_type.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update branding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/{tenant_id}/branding")
async def get_branding(tenant_id: str):
    """Get tenant branding configuration."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        branding = service.get_branding(tenant_id)
        if not branding:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {
            "branding": {
                "company_name": branding.company_name,
                "company_logo_url": branding.company_logo_url,
                "primary_color": branding.primary_color,
                "secondary_color": branding.secondary_color,
                "accent_color": branding.accent_color,
                "default_voice_id": branding.default_voice_id,
                "greeting_template": branding.greeting_template,
                "custom_domain": branding.custom_domain,
                "subdomain": branding.subdomain
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get branding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/{tenant_id}/features")
async def get_feature_matrix(tenant_id: str):
    """Get tenant feature access matrix."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        matrix = service.get_feature_matrix(tenant_id)
        if not matrix:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return matrix
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get features: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/{tenant_id}/usage")
async def get_usage_summary(tenant_id: str):
    """Get tenant usage summary."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        usage = service.get_usage_summary(tenant_id)
        if not usage:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return usage
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get usage: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/{tenant_id}/limits")
async def check_usage_limits(tenant_id: str):
    """Check tenant usage against limits."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        return service.check_usage_limits(tenant_id)
    except Exception as e:
        logger.error(f"Failed to check limits: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.post("/{tenant_id}/api-key/regenerate")
async def regenerate_api_key(tenant_id: str):
    """Regenerate API key for a tenant."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        new_key = service.regenerate_api_key(tenant_id)
        if not new_key:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return {
            "success": True,
            "api_key": new_key,
            "message": "Store this key securely. It won't be shown again."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate API key: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@tenant_router.get("/admin/dashboard")
async def get_admin_dashboard():
    """Get admin overview of all tenants."""
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        return service.get_admin_dashboard()
    except Exception as e:
        logger.error(f"Failed to get admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Tenant Context Middleware (for use in other routes)
# =============================================================================

async def get_tenant_context(
    x_tenant_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Dependency to get tenant context from request headers.
    Can be used in other routes to scope operations to a tenant.
    """
    try:
        from services.white_label_multi_tenant_service import WhiteLabelMultiTenantService
        service = WhiteLabelMultiTenantService()

        tenant_id = x_tenant_id

        # If no tenant ID, try to get from API key
        if not tenant_id and authorization:
            if authorization.startswith("Bearer "):
                api_key = authorization[7:]
                tenant_id = service.validate_api_key(api_key)

        if not tenant_id:
            raise HTTPException(
                status_code=401,
                detail="Tenant ID or valid API key required"
            )

        context = service.get_tenant_context(tenant_id)
        if not context:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if not context.get("is_active"):
            raise HTTPException(status_code=403, detail="Tenant is not active")

        return context

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant context: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
