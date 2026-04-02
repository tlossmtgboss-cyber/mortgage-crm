"""
UVIP - Video Meeting Scheduling, Analytics, Intelligence & Settings Routes
Extracted from video_meeting_routes.py

Handles:
- AI analysis request and retrieval
- Conversation analytics (recording, user, team)
- Mortgage intelligence endpoints
- Manager dashboard / leaderboard
- Organization video settings
- Table setup / migration endpoints
- Calendar invite generation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
import logging

from video_meeting_shared import (
    get_db, get_current_user, get_models, _require_admin,
    verify_recording_access,
    run_ai_analysis, process_recording_analytics, process_mortgage_intelligence,
)
from video_meeting_schemas import (
    AIAnalysisRequest, OrgVideoSettingsUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# AI ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/ai-analysis")
async def request_ai_analysis(
    room_id: int,
    data: AIAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Request AI analysis for a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingAIAnalysis = _models.get('MeetingAIAnalysis')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.status not in ["ended", "completed"]:
        raise HTTPException(status_code=400, detail="Meeting must be ended before AI analysis")

    analyses_created = []
    for analysis_type in data.analysis_types:
        analysis = MeetingAIAnalysis(
            meeting_id=room_id,
            analysis_type=analysis_type,
            status="pending",
            created_by=current_user.id
        )
        db.add(analysis)
        analyses_created.append(analysis_type)

    db.commit()

    background_tasks.add_task(run_ai_analysis, room_id, data.analysis_types)

    return {"success": True, "analyses_requested": analyses_created}


@router.get("/rooms/{room_id}/ai-analysis")
async def get_ai_analysis(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get AI analysis results for a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingAIAnalysis = _models.get('MeetingAIAnalysis')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    analyses = []
    if MeetingAIAnalysis:
        analyses = db.query(MeetingAIAnalysis).filter(
            MeetingAIAnalysis.meeting_id == room_id
        ).all()

    return {
        "meeting_id": room_id,
        "summary": room.ai_summary,
        "action_items": room.ai_action_items,
        "key_topics": room.ai_key_topics,
        "follow_up_recommended": room.ai_follow_up_recommended,
        "analyses": [
            {
                "id": a.id,
                "analysis_type": a.analysis_type,
                "status": a.status,
                "content": a.content,
                "structured_content": a.structured_content,
                "confidence_score": a.confidence_score,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in analyses
        ]
    }


# ============================================================================
# CONVERSATION ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/analytics")
async def get_recording_analytics(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get analytics for all participants in a recording"""
    _models = get_models()

    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    ParticipantAnalytics = _models.get('ParticipantAnalytics')
    MeetingParticipant = _models.get('MeetingParticipant')
    CoachingRecommendation = _models.get('CoachingRecommendation')

    if not ParticipantAnalytics:
        raise HTTPException(status_code=500, detail="ParticipantAnalytics model not found")

    analytics_records = db.query(ParticipantAnalytics).filter(
        ParticipantAnalytics.recording_id == recording_id
    ).all()

    result = []
    for a in analytics_records:
        participant = None
        if MeetingParticipant:
            participant = db.query(MeetingParticipant).filter(
                MeetingParticipant.id == a.participant_id
            ).first()

        recommendations = []
        if CoachingRecommendation:
            recs = db.query(CoachingRecommendation).filter(
                CoachingRecommendation.analytics_id == a.id
            ).all()
            recommendations = [
                {
                    "category": rec.category,
                    "recommendation": rec.recommendation,
                    "priority": rec.priority,
                    "evidence": rec.evidence
                }
                for rec in recs
            ]

        result.append({
            "id": a.id,
            "participant_id": a.participant_id,
            "participant_name": participant.display_name if participant else None,
            "talk_time_seconds": a.talk_time_seconds,
            "listen_time_seconds": a.listen_time_seconds,
            "talk_listen_ratio": a.talk_listen_ratio,
            "longest_monologue_seconds": a.longest_monologue_seconds,
            "interruption_count": a.interruption_count,
            "question_count": a.question_count,
            "filler_word_count": a.filler_word_count,
            "speaking_pace_wpm": a.speaking_pace_wpm,
            "sentiment_positive_pct": a.sentiment_positive_pct,
            "sentiment_negative_pct": a.sentiment_negative_pct,
            "sentiment_neutral_pct": a.sentiment_neutral_pct,
            "engagement_score": a.engagement_score,
            "coaching_recommendations": recommendations
        })

    return {"analytics": result}


@router.post("/recordings/{recording_id}/analyze")
async def analyze_recording(
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Trigger analytics processing for a recording"""
    _models = get_models()
    MeetingRecording = _models.get('MeetingRecording')
    RecordingTranscript = _models.get('RecordingTranscript')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id,
        RecordingTranscript.status == "completed"
    ).first()

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not ready. Please wait for transcription to complete.")

    background_tasks.add_task(
        process_recording_analytics,
        recording_id,
        recording.meeting_id
    )

    return {"success": True, "message": "Analytics processing started", "recording_id": recording_id}


@router.get("/analytics/user/{user_id}")
async def get_user_analytics(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get aggregate analytics for a user across all meetings"""
    _models = get_models()

    try:
        from uvip.coaching_service import get_coaching_service
        coaching_service = get_coaching_service()

        result = await coaching_service.get_user_coaching_summary(
            user_id=user_id,
            db=db,
            models=_models,
            days=days
        )

        return result

    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/me")
async def get_my_analytics(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get aggregate analytics for the current user"""
    return await get_user_analytics(
        user_id=current_user.id,
        days=days,
        db=db,
        current_user=current_user
    )


@router.get("/analytics/team")
async def get_team_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get team-wide analytics for managers"""
    _models = get_models()
    ParticipantAnalytics = _models.get('ParticipantAnalytics')
    MeetingParticipant = _models.get('MeetingParticipant')

    if not all([ParticipantAnalytics, MeetingParticipant]):
        raise HTTPException(status_code=500, detail="Required models not available")

    team_id = getattr(current_user, 'team_id', None)
    organization_id = getattr(current_user, 'organization_id', None)

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

    analytics_records = db.query(ParticipantAnalytics).filter(
        ParticipantAnalytics.created_at >= cutoff_date
    ).all()

    if not analytics_records:
        return {
            "total_meetings": 0,
            "team_size": 0,
            "avg_engagement_score": 0,
            "top_performers": [],
            "coaching_priorities": []
        }

    user_analytics = {}
    for a in analytics_records:
        participant = db.query(MeetingParticipant).filter(
            MeetingParticipant.id == a.participant_id
        ).first()

        if participant and participant.user_id:
            if participant.user_id not in user_analytics:
                user_analytics[participant.user_id] = {
                    "name": participant.display_name,
                    "meetings": [],
                    "total_engagement": 0
                }
            user_analytics[participant.user_id]["meetings"].append(a)
            user_analytics[participant.user_id]["total_engagement"] += (a.engagement_score or 0)

    user_metrics = []
    for uid, data in user_analytics.items():
        meeting_count = len(data["meetings"])
        if meeting_count > 0:
            avg_engagement = data["total_engagement"] / meeting_count
            avg_talk_ratio = sum(m.talk_listen_ratio or 0 for m in data["meetings"]) / meeting_count
            avg_questions = sum(m.question_count or 0 for m in data["meetings"]) / meeting_count

            user_metrics.append({
                "user_id": uid,
                "name": data["name"],
                "meetings": meeting_count,
                "avg_engagement": round(avg_engagement, 2),
                "avg_talk_ratio": round(avg_talk_ratio, 2),
                "avg_questions": round(avg_questions, 1)
            })

    top_performers = sorted(user_metrics, key=lambda x: x["avg_engagement"], reverse=True)[:5]

    return {
        "total_meetings": len(set(a.recording_id for a in analytics_records)),
        "team_size": len(user_analytics),
        "avg_engagement_score": round(
            sum(a.engagement_score or 0 for a in analytics_records) / len(analytics_records), 2
        ) if analytics_records else 0,
        "top_performers": top_performers,
        "period_days": 30
    }


# ============================================================================
# MORTGAGE INTELLIGENCE ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/intelligence")
async def get_mortgage_intelligence(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get mortgage-specific intelligence from a recording"""
    _models = get_models()

    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    MortgageIntelligence = _models.get('MortgageIntelligence')
    if not MortgageIntelligence:
        raise HTTPException(status_code=500, detail="MortgageIntelligence model not found")

    intelligence = db.query(MortgageIntelligence).filter(
        MortgageIntelligence.recording_id == recording_id
    ).first()

    if not intelligence:
        raise HTTPException(status_code=404, detail="Intelligence not available for this recording")

    return {
        "id": intelligence.id,
        "recording_id": intelligence.recording_id,
        "borrower_concerns": intelligence.borrower_concerns or [],
        "compliance_risks": intelligence.compliance_risks or [],
        "competitor_mentions": intelligence.competitor_mentions or {},
        "objections": intelligence.objections or [],
        "explanation_effectiveness": intelligence.explanation_effectiveness or {},
        "loan_details": intelligence.loan_details or {},
        "next_steps_clarity": intelligence.next_steps_clarity or {},
        "overall_risk_score": intelligence.overall_risk_score,
        "priority_flags": intelligence.priority_flags or [],
        "created_at": intelligence.created_at.isoformat() if intelligence.created_at else None
    }


@router.post("/recordings/{recording_id}/intelligence/analyze")
async def analyze_mortgage_intelligence(
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Trigger mortgage intelligence analysis for a recording"""
    _models = get_models()
    MeetingRecording = _models.get('MeetingRecording')
    RecordingTranscript = _models.get('RecordingTranscript')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id,
        RecordingTranscript.status == "completed"
    ).first()

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not ready. Please wait for transcription to complete.")

    background_tasks.add_task(
        process_mortgage_intelligence,
        recording_id
    )

    return {"success": True, "message": "Mortgage intelligence analysis started", "recording_id": recording_id}


@router.get("/intelligence/summary")
async def get_intelligence_summary(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get summary of mortgage intelligence across all recordings for a user"""
    _models = get_models()
    MortgageIntelligence = _models.get('MortgageIntelligence')
    MeetingRecording = _models.get('MeetingRecording')
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    if not all([MortgageIntelligence, MeetingRecording, VideoMeetingRoom]):
        raise HTTPException(status_code=500, detail="Required models not available")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    recordings = db.query(MeetingRecording).join(
        VideoMeetingRoom,
        MeetingRecording.meeting_id == VideoMeetingRoom.id
    ).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        MeetingRecording.created_at >= cutoff_date
    ).all()

    recording_ids = [r.id for r in recordings]

    if not recording_ids:
        return {
            "meetings_analyzed": 0,
            "period_days": days,
            "message": "No recordings found for this period"
        }

    intel_records = db.query(MortgageIntelligence).filter(
        MortgageIntelligence.recording_id.in_(recording_ids)
    ).all()

    if not intel_records:
        return {
            "meetings_analyzed": len(recordings),
            "intelligence_processed": 0,
            "period_days": days,
            "message": "No intelligence analysis available yet"
        }

    # Aggregate statistics
    total_concerns = 0
    concern_types = {}
    total_compliance_risks = 0
    compliance_types = {}
    total_competitor_mentions = 0
    competitors_mentioned = {}
    avg_risk_score = 0
    total_objections = 0
    objections_handled_well = 0

    for intel in intel_records:
        concerns = intel.borrower_concerns or []
        total_concerns += len(concerns)
        for concern in concerns:
            ctype = concern.get("concern_type", "unknown")
            concern_types[ctype] = concern_types.get(ctype, 0) + 1

        risks = intel.compliance_risks or []
        total_compliance_risks += len(risks)
        for risk in risks:
            rtype = risk.get("risk_type", "unknown")
            compliance_types[rtype] = compliance_types.get(rtype, 0) + 1

        comp_data = intel.competitor_mentions or {}
        summary = comp_data.get("summary", {})
        for comp, data in summary.items():
            total_competitor_mentions += data.get("count", 0)
            competitors_mentioned[comp] = competitors_mentioned.get(comp, 0) + data.get("count", 0)

        avg_risk_score += (intel.overall_risk_score or 0)

        objections = intel.objections or []
        total_objections += len(objections)
        objections_handled_well += sum(1 for o in objections if o.get("handled_well"))

    num_records = len(intel_records)
    avg_risk_score = avg_risk_score / num_records if num_records > 0 else 0

    return {
        "meetings_analyzed": len(recordings),
        "intelligence_processed": num_records,
        "period_days": days,
        "summary": {
            "total_borrower_concerns": total_concerns,
            "concern_breakdown": concern_types,
            "total_compliance_flags": total_compliance_risks,
            "compliance_breakdown": compliance_types,
            "total_competitor_mentions": total_competitor_mentions,
            "competitors_mentioned": competitors_mentioned,
            "avg_risk_score": round(avg_risk_score, 2),
            "total_objections": total_objections,
            "objections_handled_well_pct": round(
                (objections_handled_well / total_objections * 100) if total_objections > 0 else 100, 1
            )
        },
        "recommendations": _generate_summary_recommendations(
            concern_types, compliance_types, avg_risk_score, total_objections, objections_handled_well
        )
    }


def _generate_summary_recommendations(
    concern_types: Dict,
    compliance_types: Dict,
    avg_risk_score: float,
    total_objections: int,
    objections_handled_well: int
) -> List[Dict]:
    """Generate recommendations based on aggregated intelligence"""
    recommendations = []

    if concern_types.get("rate_anxiety", 0) > 3:
        recommendations.append({
            "category": "rate_discussion",
            "priority": "high",
            "recommendation": "Rate anxiety is common in your calls. Proactively explain rate lock options and market context early in conversations."
        })

    if concern_types.get("competing_offers", 0) > 2:
        recommendations.append({
            "category": "competitive",
            "priority": "high",
            "recommendation": "Borrowers frequently mention other lenders. Focus on relationship value and service quality, not just rates."
        })

    if len(compliance_types) > 0:
        recommendations.append({
            "category": "compliance",
            "priority": "critical",
            "recommendation": f"Compliance flags detected. Review recordings for potential steering or pressure issues."
        })

    if total_objections > 0:
        handling_rate = objections_handled_well / total_objections
        if handling_rate < 0.7:
            recommendations.append({
                "category": "objection_handling",
                "priority": "medium",
                "recommendation": "Objection handling could improve. Practice empathetic listening and the 'Feel, Felt, Found' technique."
            })

    if avg_risk_score > 0.3:
        recommendations.append({
            "category": "general",
            "priority": "high",
            "recommendation": "Your average call risk score is elevated. Review recent recordings and focus on clear communication and compliance."
        })

    return recommendations


# ============================================================================
# MANAGER DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/analytics/manager/dashboard")
async def get_manager_dashboard(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get comprehensive manager dashboard with team performance metrics"""
    _models = get_models()

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            team_member_ids = [current_user.id]

        dashboard_service = get_manager_dashboard_service(db, _models)

        result = await dashboard_service.get_team_overview(
            team_member_ids=team_member_ids,
            days=days
        )

        return result

    except Exception as e:
        logger.error(f"Error getting manager dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/manager/compare/{user_id}")
async def compare_user_to_team(
    user_id: int,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Compare individual user performance against team averages"""
    _models = get_models()

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            team_member_ids = [current_user.id]

        if user_id not in team_member_ids:
            raise HTTPException(status_code=403, detail="User not in your team")

        dashboard_service = get_manager_dashboard_service(db, _models)

        result = await dashboard_service.get_individual_comparison(
            user_id=user_id,
            team_member_ids=team_member_ids,
            days=days
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing user to team: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/manager/leaderboard")
async def get_team_leaderboard(
    metric: str = Query("engagement_score", regex="^(engagement_score|question_count|positive_sentiment|talk_listen_ratio)$"),
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get team leaderboard for specific metrics"""
    _models = get_models()

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            team_member_ids = [current_user.id]

        dashboard_service = get_manager_dashboard_service(db, _models)

        leaderboard = await dashboard_service.get_leaderboard(
            team_member_ids=team_member_ids,
            days=days,
            metric=metric
        )

        return {
            "metric": metric,
            "period_days": days,
            "leaderboard": leaderboard
        }

    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TABLE SETUP / MIGRATION ENDPOINTS
# ============================================================================

@router.post("/setup-consent-fields")
async def setup_consent_fields(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Add recording consent columns to meeting_recordings and meeting_participants tables."""
    _require_admin(current_user)
    try:
        alter_statements = [
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_obtained BOOLEAN DEFAULT FALSE",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_type VARCHAR(20)",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_state_code VARCHAR(2)",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS disclosure_script_shown TEXT",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_obtained_at TIMESTAMP",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_given BOOLEAN DEFAULT FALSE",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_at TIMESTAMP",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_method VARCHAR(20)",
        ]

        from sqlalchemy import text
        for stmt in alter_statements:
            try:
                db.execute(text(stmt))
            except Exception as e:
                logger.warning(f"Migration statement skipped: {e}")

        db.commit()
        return {"success": True, "message": "Consent fields migration completed"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error setting up consent fields: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/org-settings/setup")
async def setup_org_video_settings_table(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create the organization_video_settings table."""
    _require_admin(current_user)
    try:
        from sqlalchemy import text
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS organization_video_settings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER UNIQUE NOT NULL,
                recording_allowed BOOLEAN DEFAULT TRUE,
                recording_consent_required BOOLEAN DEFAULT TRUE,
                default_consent_type VARCHAR(20) DEFAULT 'one_party',
                default_waiting_room BOOLEAN DEFAULT TRUE,
                max_participants INTEGER DEFAULT 50,
                allowed_providers JSON DEFAULT '["internal", "zoom", "teams"]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.commit()
        return {"success": True, "message": "organization_video_settings table created"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating org video settings table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# ORGANIZATION VIDEO SETTINGS ENDPOINTS
# ============================================================================

@router.get("/org-settings")
async def get_org_video_settings(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get organization video meeting settings."""
    _models = get_models()
    OrganizationVideoSettings = _models.get('OrganizationVideoSettings')
    if not OrganizationVideoSettings:
        raise HTTPException(status_code=500, detail="OrganizationVideoSettings model not found")

    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        return {
            "settings": None,
            "message": "No organization associated with user"
        }

    settings = db.query(OrganizationVideoSettings).filter(
        OrganizationVideoSettings.organization_id == org_id
    ).first()

    if not settings:
        return {
            "settings": {
                "recording_allowed": True,
                "recording_consent_required": True,
                "default_consent_type": "one_party",
                "default_waiting_room": True,
                "max_participants": 50,
                "allowed_providers": ["internal", "zoom", "teams"]
            },
            "is_default": True
        }

    return {
        "settings": {
            "recording_allowed": settings.recording_allowed,
            "recording_consent_required": settings.recording_consent_required,
            "default_consent_type": settings.default_consent_type,
            "default_waiting_room": settings.default_waiting_room,
            "max_participants": settings.max_participants,
            "allowed_providers": settings.allowed_providers or ["internal", "zoom", "teams"]
        },
        "is_default": False
    }


@router.put("/org-settings")
async def update_org_video_settings(
    data: OrgVideoSettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update organization video meeting settings."""
    _require_admin(current_user)
    _models = get_models()
    OrganizationVideoSettings = _models.get('OrganizationVideoSettings')
    if not OrganizationVideoSettings:
        raise HTTPException(status_code=500, detail="OrganizationVideoSettings model not found")

    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")

    settings = db.query(OrganizationVideoSettings).filter(
        OrganizationVideoSettings.organization_id == org_id
    ).first()

    if not settings:
        settings = OrganizationVideoSettings(organization_id=org_id)
        db.add(settings)

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and field not in _protected:
            setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    return {
        "success": True,
        "settings": {
            "recording_allowed": settings.recording_allowed,
            "recording_consent_required": settings.recording_consent_required,
            "default_consent_type": settings.default_consent_type,
            "default_waiting_room": settings.default_waiting_room,
            "max_participants": settings.max_participants,
            "allowed_providers": settings.allowed_providers
        }
    }


@router.post("/breakout-rooms/setup")
async def setup_breakout_rooms_table(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create the breakout_rooms table if it doesn't exist."""
    _require_admin(current_user)
    _models = get_models()
    BreakoutRoom = _models.get('BreakoutRoom')
    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    try:
        from database import engine
        BreakoutRoom.__table__.create(engine, checkfirst=True)
        return {"success": True, "message": "breakout_rooms table ready"}
    except Exception as e:
        logger.error(f"Error creating breakout_rooms table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CALENDAR INVITE ENDPOINT
# ============================================================================

@router.post("/rooms/{room_id}/calendar-invite")
async def generate_calendar_invite(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Generate an ICS calendar invite for a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        from services.calendar_invite_service import calendar_invite_service

        participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id
        ).all()

        attendees = [
            {"email": p.email or "", "name": p.display_name or ""}
            for p in participants if p.email
        ]

        ics_content = calendar_invite_service.create_meeting_invite(
            room=room,
            host_user=current_user,
            attendee_list=attendees,
            base_url="https://app.perenniaai.com"
        )

        from fastapi.responses import Response
        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="meeting-{room.room_code}.ics"'
            }
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Calendar invite service not available")
