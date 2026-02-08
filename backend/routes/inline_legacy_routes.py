"""
Legacy Inline Routes

All inline @app route endpoints extracted from main.py.
This file is imported by main.py which calls register_inline_routes(app)
passing all necessary dependencies.

This is a transitional file - route groups should be further
decomposed into dedicated route files over time.
"""
from fastapi import (
    Depends, HTTPException, status, Request, Query,
    UploadFile, File, Form, WebSocket, WebSocketDisconnect,
    BackgroundTasks, Body, Header,
)
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Date, Text, ForeignKey, JSON, Enum as SQLEnum, func, text, or_, UniqueConstraint, Numeric, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any
import logging
import os
import json
import time
import asyncio
import secrets
import enum
import random
import io
import pytz
import requests
import anthropic
from openai import OpenAI
from passlib.context import CryptContext
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# Try to import SSE support
try:
    from sse_starlette.sse import EventSourceResponse
    SSE_AVAILABLE = True
except ImportError:
    EventSourceResponse = None
    SSE_AVAILABLE = False

# Import models from their source
from database.models import (
    Organization, Branch, User, ApiKey, EmailSignature,
    Lead, Loan, AITask, Task, Document, Activity, StageHistory,
    Conversation, SMSMessage, Email, EmailDraft, CalendarEvent,
    IntegrationCredential, AIKnowledgeBase, AIColleagueAction,
    ReferralPartner, LoanTeamMember, MUMClient, Workflow,
    Responsibility, UserResponsibility, Subscription,
    MicrosoftOAuthToken, IncomingDataEvent, ExtractedData,
    Skill, AgentTelephonySettings, VerifiedCallerId, CallLog,
    ImpersonationSession, UserSettings, OnboardingProgress, OnboardingError,
    VerificationToken, AIDelegatedTask, AIFeedbackLog,
    AIAction, AILearningMetric, AIAuditLog, AIPerformanceDaily,
    AIJourneyInsight, AIHealthScore, AIMetricsDaily, AIChangelogDaily,
    AITrainingEvent, VoicemailDrop, VoicemailTemplate,
    VoicemailCampaign, VoicemailEvent, ConversationMemory,
    EmailMessage, TeamsMessage, IntegrationLog,
    ScheduledWorkflow, WorkflowExecution,
    EmployeeInvite, CRMPage, RolePagePermission, UserPagePermission,
    UserPermission, PermissionRequest, AIQuickAction, AIQuickActionRole,
    RoleResponsibility,
    AuditLog, UserSession, EmergencyRevocation, AccessCertification,
    SecuritySnapshotDaily, IntegrationStatusLog, SystemAlert, SystemJobsLog,
    Notification, SubscriptionPlan, PromoCode, TeamMember,
    MicrosoftToken, MicrosoftAppConfig,
    BlockedSender, DuplicatePair, MergeTrainingEvent, MergeAIModel,
    ITHelpdeskTicket, ITHelpdeskTool,
    ClientProfile, TeamRole, ProcessFlowDocument, KPISnapshot,
    UserJobDescription, EmployeeResponsibility, ResponsibilitySkill,
    UserGoal, GoalKeyResult, GoalEmployeeAssessment, GoalManagerAssessment,
    GoalResponsibility, UserSkillAssessment,
    DialerSession, DialerSessionTask, ActiveCall, ContactDNCStatus,
    BorrowerProfile, BorrowerAuthEvent, BorrowerMagicLink, BorrowerApplication,
    ApplicationDocument, CoborrowerInvitation, ApplicationEvent,
    ApplicationNotification, ApplicationSession, VoiceApplicationSession,
    EstimateParseCache, EstimateParseFailure, EstimateComparison,
    CalendarMapping, OnboardingStep, ProcessTemplate, ProcessRole,
    ProcessMilestone, ProcessTask, EmailVerificationToken,
    AIColleagueLearningMetric,
)

# Import enums from their source
from database.enums import (
    LeadStage, LoanStage, TaskType, ActivityType,
    DialerSessionStatus, DialerTaskStatus, CallOutcome,
    SocialProvider, ApplicationStatus, ApplicationStep,
    DocumentType, DocumentCategory, InviteStatus, PermissionLevel,
    RateLockStatus, RateLockRecommendation, BuyingTimelineCategory,
    BorrowerRiskProfile, EmailIntakeMatchStatus, AttachmentClassificationStatus,
    CoachMode,
)

# Import schemas from their source
from schemas.core import (
    ApiKeyCreate, ApiKeyResponse,
    LeadCreate, LeadUpdate, LeadResponse,
    LoanCreate, LoanUpdate, LoanResponse,
    MUMClientCreate, MUMClientUpdate, MUMClientResponse,
    ErrorFixRequest, ActivityCreate, ActivityResponse,
    MicrosoftSyncSettings, MicrosoftOAuthConnect, MicrosoftTokenResponse,
    MicrosoftAppConfigRequest, MicrosoftAppConfigResponse,
    TaskCreate, TaskUpdate, TaskResponse,
    ReferralPartnerCreate, ReferralPartnerUpdate, ReferralPartnerResponse,
    LoanTeamMemberCreate, LoanTeamMemberUpdate, LoanTeamMemberResponse,
    ConversationCreate, ConversationResponse, ChatStreamRequest,
    CoachRequest, CoachResponse,
    CalendarEventCreate, CalendarEventUpdate, CalendarEventResponse,
    CalendarAssignmentCreate, CalendarAssignmentUpdate, CalendarAssignmentResponse,
    CALENDAR_PURPOSES,
    IncomingDataEventCreate, ExtractedDataResponse,
    ReconciliationApproval, ReconciliationRejection, BlockSenderRequest,
    CreateLeadFromExtracted,
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    ImpersonationStart, ImpersonationResponse,
    RevokeSessionRequest, RevokeAllSessionsRequest, EmergencyRevokeRequest,
    UserCreate, UserResponse, TeamMemberCreate, TeamMemberUpdate,
    UserProfileData, BrandingSettings, IntegrationSettings, AutomationSettings,
    ReconciliationSettings, PipelineSettings, KPITargets, PortfolioSettings,
    AdvancedSettings, ClientProfileCreate, ClientProfileUpdate, ClientProfileResponse,
    TeamRoleCreate, TeamRoleUpdate, TeamRoleResponse,
    ProcessFlowDocumentCreate, ProcessFlowDocumentResponse,
    ProcessTemplateCreate, ProcessTemplateUpdate, ProcessTemplateResponse,
    ProcessRoleCreate, ProcessRoleResponse,
    ProcessMilestoneCreate, ProcessMilestoneResponse,
    ProcessTaskCreate, ProcessTaskResponse,
    DocumentParseRequest, DocumentParseResponse,
    BorrowerApplicationCreate, BorrowerApplicationUpdate, StepDataUpdate,
    CreditAuthCapture, PrequalificationRequest, PrequalificationResponse,
    DocumentUploadResponse, CoborrowerInvitationCreate, CoborrowerInvitationResponse,
    ApplicationEventCreate, BorrowerApplicationResponse, ApplicationPublicResponse,
    ApplicationAnalytics,
    UpdateJobDescriptionRequest, JobDescriptionResponse,
    SkillCreate, SkillResponse,
    CreateResponsibilityRequest, UpdateResponsibilityRequest,
    ResponsibilityResponse, ReorderResponsibilitiesRequest,
)

# Import database infrastructure
from database import engine, SessionLocal, Base

# Import permission filter functions (extracted to permission_core_routes.py)
from routes.permission_core_routes import filter_leads_by_permissions


# Module-level dict for functions that need to be importable from outside
# Populated by register_inline_routes() at startup
_exported_functions = {}


def get_exported_function(name):
    """Get a function exported from register_inline_routes by name."""
    return _exported_functions.get(name)


def register_inline_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register all legacy inline routes on the FastAPI app.
    
    Called from main.py after all dependencies are defined.
    
    Args:
        app: FastAPI application instance
        get_db: Database session dependency
        get_current_user: Auth dependency (Bearer token)
        get_current_user_flexible: Auth dependency (Bearer + X-API-Key)
        **kwargs: Additional dependencies (scheduler, openai_client, etc.)
    """
    # Extract optional dependencies
    scheduler = kwargs.get('scheduler')
    openai_client = kwargs.get('openai_client')
    pwd_context = kwargs.get('pwd_context')
    SECRET_KEY = kwargs.get('SECRET_KEY', '')
    ENVIRONMENT = kwargs.get('ENVIRONMENT', 'development')
    create_access_token = kwargs.get('create_access_token')
    create_refresh_token = kwargs.get('create_refresh_token')
    get_password_hash = kwargs.get('get_password_hash')
    verify_password = kwargs.get('verify_password')
    get_cached = kwargs.get('get_cached')
    set_cached = kwargs.get('set_cached')
    clear_cache = kwargs.get('clear_cache')
    oauth2_scheme = kwargs.get('oauth2_scheme')
    log_ai_action_to_mission_control = kwargs.get('log_ai_action_to_mission_control')
    update_ai_action_outcome = kwargs.get('update_ai_action_outcome')
    DATABASE_URL = kwargs.get('DATABASE_URL', '')
    security_stats = kwargs.get('security_stats')

    # Re-import typing constructs and BaseModel as local vars so Python 3.14
    # PEP 649 deferred annotation evaluation can resolve them in nested functions.
    from typing import List, Optional, Dict, Any  # noqa: F811
    from pydantic import BaseModel  # noqa: F811

    # ---- Register extracted route modules ----
    try:
        from routes.health_routes import register_health_routes
        register_health_routes(app, get_db, health_checker=kwargs.get('health_checker'), SessionLocal=SessionLocal)
        logger.info("✅ Health routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Health routes failed: {e}")

    try:
        from routes.db_migration_routes import register_migration_routes
        register_migration_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Migration routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Migration routes failed: {e}")

    try:
        from routes.admin_ops_routes import register_admin_ops_routes
        register_admin_ops_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs)
        logger.info("✅ Admin ops routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Admin ops routes failed: {e}")

    try:
        from routes.email_management_routes import register_email_management_routes
        _email_exports = register_email_management_routes(app, get_db, get_current_user, **kwargs)
        if _email_exports:
            _exported_functions.update(_email_exports)
        logger.info("✅ Email management routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Email management routes failed: {e}")

    try:
        from routes.mum_activity_routes import register_mum_activity_routes
        register_mum_activity_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs)
        logger.info("✅ MUM/Activity routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ MUM/Activity routes failed: {e}")

    try:
        from routes.api_key_routes import register_api_key_routes
        register_api_key_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ API key routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ API key routes failed: {e}")

    try:
        from routes.cache_routes import register_cache_routes
        register_cache_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Cache routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Cache routes failed: {e}")

    try:
        from routes.calculator_settings_routes import register_calculator_settings_routes
        register_calculator_settings_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Calculator settings routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Calculator settings routes failed: {e}")

    try:
        from routes.scorecard_routes import register_scorecard_routes
        register_scorecard_routes(app, get_db, get_current_user, Lead=Lead, Loan=Loan, LoanStage=LoanStage, **kwargs)
        logger.info("✅ Scorecard routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Scorecard routes failed: {e}")

    try:
        from routes.search_routes import register_search_routes
        register_search_routes(app, get_db, get_current_user_flexible=get_current_user_flexible, Lead=Lead, Loan=Loan, LoanTeamMember=LoanTeamMember, ReferralPartner=ReferralPartner, MUMClient=MUMClient, filter_leads_by_permissions=filter_leads_by_permissions, **kwargs)
        logger.info("✅ Global search routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Global search routes failed: {e}")

    try:
        from routes.ai_underwriter_routes import router as ai_underwriter_router
        app.include_router(ai_underwriter_router, prefix="/api/v1/ai-underwriter", tags=["AI Underwriter"])
        logger.info("✅ AI Underwriter routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ AI Underwriter routes failed: {e}")

    # ---- All routes below are registered on `app` ----


    # Extracted to routes/ai_chat_routes.py
    # (POST /api/v1/ai/orchestrator-chat-stream - streaming AI chat with SSE
    #  POST /api/v1/ai/autonomous-task - multi-step autonomous AI execution)
    try:
        from routes.ai_chat_routes import register_ai_chat_routes
        register_ai_chat_routes(app, get_db, get_current_user_flexible, **kwargs)
        logger.info("✅ AI orchestrator chat routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ AI chat routes failed: {e}")


    # SECURITY: Include CSRF token routes
    try:
        from middleware.csrf_protection import create_csrf_routes
        csrf_router = create_csrf_routes()
        app.include_router(csrf_router, prefix="/api/v1", tags=["Security"])
        logger.info("✅ CSRF token routes loaded")
    except Exception as e:
        logger.warning(f"Could not load CSRF routes: {e}")

    # Include public routes - Import AFTER defining functions it needs
    from public_routes import router as public_router
    app.include_router(public_router, tags=["Public"])

    # Include organization (multi-tenant) management routes
    try:
        from routes.organization_routes import router as organization_router
        app.include_router(organization_router, prefix="/api/v1", tags=["Organizations"])
        logger.info("✅ Organization management routes loaded")
    except Exception as e:
        logger.warning(f"Could not load organization routes: {e}")

    # Include microsite routes (public LO profiles, lead capture)
    from microsite_routes import router as microsite_router
    app.include_router(microsite_router, tags=["Microsite"])

    # Include microsite theme marketplace routes
    try:
        from microsite_theme_routes import public_router as theme_public_router, auth_router as theme_auth_router
        app.include_router(theme_public_router, tags=["Microsite Themes (Public)"])
        app.include_router(theme_auth_router, tags=["Microsite Configuration"])
        logger.info("✅ Microsite Theme Marketplace routes loaded")
    except Exception as e:
        logger.warning(f"Could not load microsite theme routes: {e}")

    # Include microsite platform routes (template-based microsites with schema-driven content)
    try:
        from routes.microsite_routes import router as microsite_platform_router
        app.include_router(microsite_platform_router, tags=["Microsite Platform"])
        logger.info("✅ Microsite Platform routes loaded")
    except Exception as e:
        logger.warning(f"Could not load microsite platform routes: {e}")

    # Include borrower authentication routes (social login for applicants)
    from borrower_auth_routes import router as borrower_auth_router
    app.include_router(borrower_auth_router, tags=["Borrower Auth"])

    # Include secure auth routes (token refresh, logout, introspection)
    try:
        from auth import auth_router
        app.include_router(auth_router, prefix="/api/v1", tags=["Auth - Token Management"])
        logger.info("✅ Secure auth routes loaded (RS256 support)")
    except Exception as e:
        logger.warning(f"⚠️ Secure auth routes not loaded: {e}")

    # Include main authentication routes (/token, /token/refresh, password reset, registration)
    try:
        from routes.auth_routes import router as auth_routes_router, setup_auth_routes
        app.include_router(auth_routes_router, tags=["Authentication"])
        # Set up routes that need authentication dependencies (logout, admin routes, etc.)
        setup_auth_routes(app, oauth2_scheme, get_current_user)
        logger.info("✅ Authentication routes loaded (/token, password reset, registration)")
    except Exception as e:
        logger.warning(f"⚠️ Authentication routes not loaded: {e}")

    # Include borrower portal routes (applications, documents, scheduling)
    try:
        from routes.borrower_routes import router as borrower_portal_router
        app.include_router(borrower_portal_router, tags=["Borrower Portal"])
        logger.info("✅ Borrower Portal routes loaded")
    except Exception as e:
        logger.warning(f"Could not load borrower portal routes: {e}")

    # Include Decision Lab routes (Borrower Confidence Engine + Mortgage Decision Lab)
    try:
        from routes.decision_lab_routes import router as decision_lab_router
        app.include_router(decision_lab_router, tags=["Decision Lab"])
        logger.info("✅ Decision Lab routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Decision Lab routes: {e}")

    # Include MUM Portal routes (public client portal for post-close clients)
    try:
        from routes.mum_portal_routes import router as mum_portal_router
        app.include_router(mum_portal_router, tags=["MUM Portal (Public)"])
        logger.info("✅ MUM Portal routes loaded")
    except Exception as e:
        logger.warning(f"Could not load MUM Portal routes: {e}")

    # Include application analytics routes
    from analytics_routes import router as analytics_router
    app.include_router(analytics_router, tags=["Analytics"])

    # Include Visitor Tracking routes
    try:
        from routes.visitor_tracking_routes import router as visitor_tracking_router
        app.include_router(visitor_tracking_router, tags=["Visitor Tracking"])
        logger.info("✅ Visitor Tracking routes loaded")
    except Exception as e:
        logger.warning(f"Could not load visitor tracking routes: {e}")

    # Include AI API routes
    from ai_api_endpoints import router as ai_router
    app.include_router(ai_router, tags=["AI System"])

    # Include SSE Streaming Chat routes
    try:
        from routes.sse_streaming_chat_routes import router as sse_chat_router
        app.include_router(sse_chat_router, tags=["AI Streaming"])
        logger.info("✅ SSE Streaming Chat routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load SSE Streaming Chat routes: {e}")

    # Include Voice Integration routes
    try:
        from routes.voice_integration_routes import router as voice_integration_router
        app.include_router(voice_integration_router, tags=["Voice Integration"])
        logger.info("✅ Voice Integration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Voice Integration routes: {e}")

    # Include Chat and Screenshot Parsing routes
    try:
        from routes.chat_screenshot_routes import router as chat_screenshot_router
        app.include_router(chat_screenshot_router, tags=["Chat", "Screenshot Parsing"])
        logger.info("✅ Chat and Screenshot Parsing routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Chat and Screenshot Parsing routes: {e}")

    # Include User Settings routes
    try:
        from routes.user_settings_routes import router as user_settings_router
        app.include_router(user_settings_router, tags=["User Settings"])
        logger.info("✅ User Settings routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load User Settings routes: {e}")

    # Include AI Preferences routes
    try:
        from routes.ai_preferences_routes import router as ai_preferences_router
        app.include_router(ai_preferences_router, tags=["AI Preferences"])
        logger.info("✅ AI Preferences routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Preferences routes: {e}")

    # Include AI Memory and Smart Chat routes
    try:
        from routes.ai_memory_chat_routes import router as ai_memory_chat_router
        app.include_router(ai_memory_chat_router, tags=["AI Memory Chat"])
        logger.info("✅ AI Memory Chat routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Memory Chat routes: {e}")

    # Include Document Email Import routes
    try:
        from routes.document_email_import_routes import router as document_email_import_router
        app.include_router(document_email_import_router, tags=["Document Email Import"])
        logger.info("✅ Document Email Import routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Document Email Import routes: {e}")

    # Include AI Orchestrator Chat routes
    try:
        from routes.ai_orchestrator_routes import router as ai_orchestrator_router
        app.include_router(ai_orchestrator_router, tags=["AI Orchestrator"])
        logger.info("✅ AI Orchestrator Chat routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Orchestrator Chat routes: {e}")

    # Include Admin Migration routes
    try:
        from routes.admin_migration_routes import router as admin_migration_router
        app.include_router(admin_migration_router, tags=["Admin Migrations"])
        logger.info("✅ Admin Migration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Admin Migration routes: {e}")

    # Include Credit Report routes
    try:
        from routes.credit_routes import router as credit_router
        app.include_router(credit_router, tags=["Credit Reports"])
        logger.info("✅ Credit Report routes loaded")
    except Exception as e:
        logger.warning(f"Could not load credit report routes: {e}")

    # Include Mission Control routes
    from mission_control_routes import router as mission_control_router
    app.include_router(mission_control_router, tags=["Mission Control"])

    # Include A/B Testing routes
    from ab_testing_routes import router as ab_testing_router
    app.include_router(ab_testing_router, tags=["A/B Testing"])

    # Include AI Receptionist Dashboard routes
    from ai_receptionist_dashboard_routes import router as ai_receptionist_dashboard_router
    app.include_router(ai_receptionist_dashboard_router, tags=["AI Receptionist Dashboard"])

    # Include Voice AI Receptionist routes
    # ✅ FIXED: Circular import resolved by using lazy imports in voice_routes.py
    from voice_routes import router as voice_router
    app.include_router(voice_router, tags=["Voice AI"])

    # Include AMD Outbound Call routes (Twilio/Telnyx AMD for voicemail detection)
    try:
        from routes.amd_outbound_routes import router as amd_outbound_router
        app.include_router(amd_outbound_router, tags=["AMD Outbound Calls"])
        logger.info("✅ AMD Outbound Call routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AMD Outbound Call routes: {e}")

    # Include Telnyx Webhook routes (for Telnyx telephony provider)
    try:
        from routes.telnyx_webhook_routes import router as telnyx_webhook_router
        app.include_router(telnyx_webhook_router, tags=["Telnyx Webhooks"])
        logger.info("✅ Telnyx Webhook routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Telnyx Webhook routes: {e}")

    # Include Call Screening routes (blocklist/whitelist management, spam filtering)
    try:
        from routes.call_screening_routes import router as call_screening_router
        app.include_router(call_screening_router, tags=["Call Screening"])
        logger.info("✅ Call Screening routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Call Screening routes: {e}")

    # Include Twilio Status Callback routes (webhook handlers for call status + recordings)
    try:
        from routes.twilio_status_callback_routes import router as twilio_status_callback_router
        app.include_router(twilio_status_callback_router, tags=["Twilio Webhooks"])
        logger.info("✅ Twilio Status Callback routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Twilio Status Callback routes: {e}")

    # Include State Recording Rules routes (state-specific recording disclosure requirements)
    try:
        from routes.state_recording_rules_routes import router as state_recording_rules_router
        app.include_router(state_recording_rules_router, tags=["State Recording Rules"])
        logger.info("✅ State Recording Rules routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load State Recording Rules routes: {e}")

    # Include Quote Language Presets routes (compliant language management for AI calls)
    try:
        from routes.quote_language_routes import router as quote_language_router
        app.include_router(quote_language_router, tags=["Quote Language Presets"])
        logger.info("✅ Quote Language Presets routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Quote Language Presets routes: {e}")

    # Include Voice OS API routes (agents, phone numbers, call sessions, analytics)
    from voice_os_routes import router as voice_os_router, set_auth_dependency as set_voice_os_auth
    set_voice_os_auth(get_current_user)
    app.include_router(voice_os_router, tags=["Voice OS"])

    # Include Mobile Voice routes for real-time voice conversations
    from mobile_voice_routes import router as mobile_voice_router
    app.include_router(mobile_voice_router, tags=["Mobile Voice"])

    # Include Voice Workflow routes for conversational task completion
    try:
        from routes.voice_workflow_routes import router as voice_workflow_router, set_dependencies as set_voice_workflow_deps
        set_voice_workflow_deps(get_db)
        app.include_router(voice_workflow_router, tags=["Voice Workflow"])
        logger.info("✅ Voice Workflow routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Voice Workflow routes: {e}")

    # Include Advanced Telephony routes (Hold Music, Transfers, IVR, Queues, Conferences)
    try:
        from routes.hold_music_routes import router as hold_music_router
        app.include_router(hold_music_router, tags=["Hold Music"])
        logger.info("✅ Hold Music routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Hold Music routes: {e}")

    try:
        from routes.call_transfer_routes import router as call_transfer_router
        app.include_router(call_transfer_router, tags=["Call Transfers"])
        logger.info("✅ Call Transfer routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Call Transfer routes: {e}")

    try:
        from routes.ivr_routes import router as ivr_router
        app.include_router(ivr_router, tags=["IVR"])
        logger.info("✅ IVR routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load IVR routes: {e}")

    try:
        from routes.call_queue_routes import router as call_queue_router
        app.include_router(call_queue_router, tags=["Call Queues"])
        logger.info("✅ Call Queue routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Call Queue routes: {e}")

    try:
        from routes.conference_routes import router as conference_router
        app.include_router(conference_router, tags=["Conferences"])
        logger.info("✅ Conference routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Conference routes: {e}")

    # Include Deepgram Voice Agent routes (new all-in-one voice API)
    from deepgram_voice_agent import router as deepgram_voice_agent_router
    app.include_router(deepgram_voice_agent_router, tags=["Voice Agent"])

    # Include Vapi AI Receptionist routes
    from vapi_routes import router as vapi_router
    app.include_router(vapi_router, tags=["Vapi AI"])

    # Include Guideline Updates routes
    from guideline_updates_routes import router as guideline_updates_router
    app.include_router(guideline_updates_router, tags=["Guideline Updates"])

    # Include Escalation routes
    from escalation_routes import router as escalation_router
    app.include_router(escalation_router, tags=["Escalations"])

    # Include Migrations API routes
    from migrations_api import router as migrations_router
    app.include_router(migrations_router, tags=["Migrations"])

    # Include Circle of Cashflow routes
    from circle_of_cashflow_routes import router as circle_of_cashflow_router
    app.include_router(circle_of_cashflow_router, tags=["Circle of Cashflow"])

    # Include AI Command routes for Perennia AI Landing Page
    from ai_command_routes import router as ai_command_router
    app.include_router(ai_command_router, tags=["AI Commands"])

    # Include AI Smart File Analysis routes for loan file analysis
    try:
        from routes.ai_file_analysis_routes import router as ai_file_analysis_router, set_dependencies as set_ai_file_deps
        set_ai_file_deps(get_db, get_current_user)
        app.include_router(ai_file_analysis_router, tags=["AI File Analysis"])
        logger.info("✅ AI Smart File Analysis routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Smart File Analysis routes: {e}")

    # Include AI Underwriter chat routes for guideline Q&A
    try:
        from routes.ai_underwriter_routes import router as ai_underwriter_router, set_dependencies as set_ai_uw_deps
        set_ai_uw_deps(get_db, get_current_user)
        app.include_router(ai_underwriter_router, tags=["AI Underwriter"])
        logger.info("✅ AI Underwriter routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Underwriter routes: {e}")

    # Include AI Context routes for comprehensive AI data queries
    try:
        from routes.ai_context_routes import router as ai_context_router
        app.include_router(ai_context_router, tags=["AI Context"])
        logger.info("✅ AI Context routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Context routes: {e}")

    # Include AI Metrics Dashboard routes for AI performance tracking
    try:
        from routes.ai_metrics_dashboard_routes import router as ai_metrics_dashboard_router
        app.include_router(ai_metrics_dashboard_router, tags=["AI Metrics Dashboard"])
        logger.info("✅ AI Metrics Dashboard routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Metrics Dashboard routes: {e}")

    # Include AI Knowledge Base routes for document management
    try:
        from routes.ai_knowledge_base_routes import router as ai_knowledge_base_router
        app.include_router(ai_knowledge_base_router, tags=["AI Knowledge Base"])
        logger.info("✅ AI Knowledge Base routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Knowledge Base routes: {e}")

    # Include AI Underwriting Analysis routes for loan analysis
    try:
        from routes.ai_underwriting_analysis_routes import router as ai_underwriting_analysis_router
        app.include_router(ai_underwriting_analysis_router, tags=["AI Underwriting Analysis"])
        logger.info("✅ AI Underwriting Analysis routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Underwriting Analysis routes: {e}")

    # Include AI Workflow routes for autonomous workflow management
    try:
        from routes.ai_workflow_routes import router as ai_workflow_router
        app.include_router(ai_workflow_router, tags=["AI Workflows"])
        logger.info("✅ AI Workflow routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Workflow routes: {e}")

    # Include Data Reconciliation routes for email data extraction
    try:
        from routes.data_reconciliation_routes import router as data_reconciliation_router
        app.include_router(data_reconciliation_router, tags=["Data Reconciliation"])
        logger.info("✅ Data Reconciliation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Data Reconciliation routes: {e}")

    # Include Date Reconciliation routes for Salesforce date field tracking
    try:
        from routes.date_reconciliation_routes import router as date_reconciliation_router
        app.include_router(date_reconciliation_router, prefix="/api/date-reconciliation", tags=["Date Reconciliation"])
        logger.info("✅ Date Reconciliation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Date Reconciliation routes: {e}")

    # Include MUM Client Portal routes for portal management
    try:
        from routes.mum_client_portal_routes import router as mum_client_portal_router
        app.include_router(mum_client_portal_router, tags=["MUM Portal"])
        logger.info("✅ MUM Client Portal routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load MUM Client Portal routes: {e}")

    # Include Voice AI Receptionist routes
    try:
        from routes.voice_ai_receptionist_routes import router as voice_router, webhook_router, sms_router, debug_router
        app.include_router(voice_router, tags=["Voice AI Receptionist"])
        app.include_router(webhook_router, tags=["Voice Webhooks"])
        app.include_router(sms_router, tags=["SMS Messaging"])
        app.include_router(debug_router, tags=["Debug"])
        logger.info("✅ Voice AI Receptionist routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Voice AI Receptionist routes: {e}")

    # Include Power Dialer routes for telephony
    try:
        from routes.power_dialer_routes import router as power_dialer_router
        app.include_router(power_dialer_router, tags=["Power Dialer"])
        logger.info("✅ Power Dialer routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Power Dialer routes: {e}")

    # Include Client Profile routes for CMP API
    try:
        from routes.client_profile_routes import router as client_profile_router, set_dependencies as set_client_profile_deps
        set_client_profile_deps(User, get_current_user, get_db)
        app.include_router(client_profile_router, tags=["Client Profile"])
        logger.info("✅ Client Profile routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Client Profile routes: {e}")

    # Include Duplicate Detection routes
    try:
        from routes.duplicate_detection_routes import router as duplicate_detection_router
        app.include_router(duplicate_detection_router, tags=["Duplicate Detection"])
        logger.info("✅ Duplicate Detection routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Duplicate Detection routes: {e}")

    # Include Onboarding routes
    try:
        from routes.onboarding_routes import router as onboarding_router, team_router, impersonation_router
        app.include_router(onboarding_router, tags=["Onboarding"])
        app.include_router(team_router, tags=["Team"])
        app.include_router(impersonation_router, tags=["Impersonation"])
        logger.info("✅ Onboarding routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Onboarding routes: {e}")

    # Include Voicemail Drop routes
    try:
        from routes.voicemail_drop_routes import router as voicemail_drop_router
        app.include_router(voicemail_drop_router, tags=["Voicemail Drop"])
        logger.info("✅ Voicemail Drop routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Voicemail Drop routes: {e}")

    # Include Workflow Role routes
    try:
        from routes.workflow_role_routes import router as workflow_role_router
        app.include_router(workflow_role_router, tags=["Workflow Roles"])
        logger.info("✅ Workflow Role routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Workflow Role routes: {e}")

    # Include Permission System routes
    try:
        from routes.permission_system_routes import router as permission_system_router
        app.include_router(permission_system_router, tags=["Permission System"])
        logger.info("✅ Permission System routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Permission System routes: {e}")

    # Include HR Management routes
    try:
        from routes.hr_management_routes import router as hr_management_router
        app.include_router(hr_management_router, tags=["HR Management"])
        logger.info("✅ HR Management routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load HR Management routes: {e}")

    # Include IT Helpdesk routes
    try:
        from routes.it_helpdesk_routes import router as it_helpdesk_router
        app.include_router(it_helpdesk_router, prefix="/api/v1/it-helpdesk", tags=["IT Helpdesk"])
        logger.info("✅ IT Helpdesk routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load IT Helpdesk routes: {e}")

    # Include Workflow Test routes
    try:
        from routes.workflow_test_routes import router as workflow_test_router
        app.include_router(workflow_test_router, tags=["Workflow Operations"])
        logger.info("✅ Workflow Test routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Workflow Test routes: {e}")

    # Include AI Assistant routes
    try:
        from routes.ai_assistant_routes import router as ai_assistant_router
        app.include_router(ai_assistant_router, tags=["AI Assistant"])
        logger.info("✅ AI Assistant routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Assistant routes: {e}")

    # Include CRM Operations routes (Process Templates, Analytics, Portfolio)
    try:
        from routes.crm_operations_routes import router as crm_operations_router
        app.include_router(crm_operations_router, tags=["CRM Operations"])
        logger.info("✅ CRM Operations routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load CRM Operations routes: {e}")

    # Include Leads CRUD routes
    try:
        from routes.leads_crud_routes import router as leads_crud_router
        app.include_router(leads_crud_router, tags=["Leads CRUD"])
        logger.info("✅ Leads CRUD routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Leads CRUD routes: {e}")

    # Include Subscription routes for Perennia AI
    from subscription_routes import router as subscription_router
    app.include_router(subscription_router, tags=["Subscriptions"])

    # Include Module Subscription routes for modular a-la-carte pricing
    try:
        from routes.module_routes import router as module_router, set_dependencies as set_module_deps
        set_module_deps(get_db, get_current_user)
        app.include_router(module_router, tags=["Modules"])
        logger.info("Module Subscription routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Module Subscription routes: {e}")

    # Include Usage Intelligence routes for cost tracking (Owner-only)
    try:
        from routes.usage_intelligence_routes import router as usage_intelligence_router, set_dependencies as set_usage_deps
        set_usage_deps(get_db, get_current_user)
        app.include_router(usage_intelligence_router, tags=["Usage Intelligence"])
        logger.info("✅ Usage Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Usage Intelligence routes: {e}")

    # Include Custom Domain routes for multi-tenant domain support
    try:
        from routes.custom_domain_routes import router as custom_domain_router
        app.include_router(custom_domain_router, tags=["Custom Domains"])
        logger.info("Custom Domain routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Custom Domain routes: {e}")

    # Include SSL Certificate routes for custom domain SSL management
    try:
        from routes.ssl_routes import router as ssl_router
        app.include_router(ssl_router, tags=["SSL Certificates"])
        logger.info("SSL Certificate routes loaded")
    except Exception as e:
        logger.warning(f"Could not load SSL Certificate routes: {e}")

    # Include Conversation Intelligence routes (unified AI for email + SMS)
    try:
        from routes.conversation_intelligence_routes import router as conversation_intelligence_router
        app.include_router(conversation_intelligence_router, tags=["Conversation Intelligence"])
        logger.info("Conversation Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Conversation Intelligence routes: {e}")

    # Include Conversation Intelligence Voice routes (call analysis, QA scoring, real-time coaching)
    try:
        from routes.ci_voice_routes import router as ci_voice_router, set_dependencies as set_ci_voice_deps
        set_ci_voice_deps(get_current_user)
        app.include_router(ci_voice_router, tags=["Conversation Intelligence - Voice"])
        logger.info("✅ CI Voice routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load CI Voice routes: {e}")

    # Include Live Call Whisper routes (real-time AI coaching during calls)
    try:
        from routes.live_call_whisper_routes import router as live_call_whisper_router
        app.include_router(live_call_whisper_router, tags=["Live Call Whisper"])
        logger.info("✅ Live Call Whisper routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Live Call Whisper routes: {e}")

    # Include Call Monitoring routes (AI-powered call analysis with 3 agents)
    try:
        from routes.call_monitoring_routes import router as call_monitoring_router, set_dependencies as set_call_monitoring_deps
        set_call_monitoring_deps(get_current_user)
        app.include_router(call_monitoring_router, tags=["Call Monitoring"])
        logger.info("✅ Call Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Call Monitoring routes: {e}")

    # Include Underwriting Guidelines routes (upload and manage AI underwriter guidelines)
    try:
        from routes.underwriting_guidelines_routes import router as underwriting_guidelines_router
        app.include_router(underwriting_guidelines_router, tags=["Underwriting Guidelines"])
        logger.info("✅ Underwriting Guidelines routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Underwriting Guidelines routes: {e}")

    # Include AI Underwriting Engine routes (automated underwriting analysis)
    try:
        from routes.underwriting_engine_routes import router as underwriting_engine_router
        app.include_router(underwriting_engine_router, tags=["AI Underwriting Engine"])
        logger.info("✅ AI Underwriting Engine routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load AI Underwriting Engine routes: {e}")

    # Include Production Predictor routes (AI-powered production forecasting)
    try:
        from routes.production_predictor_routes import router as production_predictor_router
        app.include_router(production_predictor_router, tags=["Production Predictor"])
        logger.info("✅ Production Predictor routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Production Predictor routes: {e}")

    # Include Deal Alerts routes (proactive pipeline monitoring and alerting)
    try:
        from routes.deal_alerts_routes import router as deal_alerts_router
        app.include_router(deal_alerts_router, tags=["Deal Alerts"])
        logger.info("✅ Deal Alerts routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Deal Alerts routes: {e}")

    # Include Realtor Portal routes
    try:
        from routes.realtor_portal_routes import router as realtor_portal_router, set_dependencies as set_realtor_portal_deps
        set_realtor_portal_deps(get_db)
        app.include_router(realtor_portal_router, tags=["Realtor Portal"])
        logger.info("✅ Realtor Portal routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Realtor Portal routes: {e}")

    # Include Contract Portal Automation routes
    try:
        from routes.contract_automation_routes import router as contract_automation_router, set_dependencies as set_contract_automation_deps
        from services.notification_service import NotificationService
        notification_service = NotificationService()
        set_contract_automation_deps(get_db, notification_service)
        app.include_router(contract_automation_router, tags=["Contract Automation"])
        logger.info("✅ Contract Portal Automation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Contract Automation routes: {e}")

    # Include Workflow System routes
    from workflow_routes import router as workflow_router
    app.include_router(workflow_router, tags=["Workflow"])

    # Include Workflow Configuration routes (editable workflow definitions)
    try:
        from workflow_config_models import create_workflow_config_models
        from workflow_config_routes import router as workflow_config_router, set_dependencies as set_workflow_config_deps, get_all_workflow_tasks_logic

        # Create workflow config models using our Base
        workflow_config_models = create_workflow_config_models(Base)

        # Set dependencies for the routes
        set_workflow_config_deps(get_db, get_current_user, workflow_config_models)

        # Include the router
        app.include_router(workflow_config_router, tags=["Workflow Configuration"])
        logger.info("✅ Workflow Configuration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Workflow Configuration routes: {e}")

    # Include SLA Workflow System routes
    try:
        from routes.workflow_sla_routes import router as workflow_sla_router, set_dependencies as set_workflow_sla_deps

        # Set dependencies for workflow SLA routes to avoid circular imports
        set_workflow_sla_deps(get_db, get_current_user, User)

        app.include_router(workflow_sla_router, tags=["Workflow SLA"])
        logger.info("✅ Workflow SLA routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Workflow SLA routes: {e}")

    # Include Page Permissions routes
    try:
        from routes.page_permissions_routes import router as page_permissions_router, set_dependencies as set_page_permissions_deps

        # Set dependencies for page permissions routes to avoid circular imports
        set_page_permissions_deps(get_db, get_current_user, User)

        app.include_router(page_permissions_router, tags=["Page Permissions"])
        logger.info("✅ Page Permissions routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Page Permissions routes: {e}")

    # Include User Roles routes (Multi-role user system)
    try:
        from routes.user_roles_routes import router as user_roles_router
        app.include_router(user_roles_router, tags=["User Roles"])
        logger.info("✅ User Roles routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load User Roles routes: {e}")

    # Include Master Manager routes (Talent & Capacity OS)
    try:
        from routes.master_manager_routes import router as master_manager_router
        app.include_router(master_manager_router, tags=["Master Manager"])
        logger.info("✅ Master Manager routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Master Manager routes: {e}")

    # Include Smart Scheduler routes (AI-native appointment scheduling)
    try:
        from smart_scheduler_models import create_smart_scheduler_models
        from smart_scheduler_routes import router as smart_scheduler_router, set_dependencies as set_scheduler_deps

        # Create smart scheduler models using our Base
        smart_scheduler_models = create_smart_scheduler_models(Base)

        # Add User model so scheduler can lookup users by slug
        smart_scheduler_models['User'] = User

        # Set dependencies for the routes
        set_scheduler_deps(get_db, get_current_user, smart_scheduler_models)

        # Include the router
        app.include_router(smart_scheduler_router, tags=["Smart Scheduler"])
        logger.info("✅ Smart Scheduler routes loaded")
    except Exception as e:
        import traceback
        logger.error(f"⚠️ Could not load Smart Scheduler routes: {e}")
        logger.error(f"Smart Scheduler traceback: {traceback.format_exc()}")

        # Add fallback endpoint if main scheduler routes failed to load
        from pydantic import BaseModel
        from typing import Optional, List, Dict, Any
        # datetime and timedelta already imported at module level (line 22)
        import pytz

        class FallbackSlotsRequest(BaseModel):
            start_date: str
            end_date: str
            duration_minutes: int = 30
            appointment_type: str = "platform-demo"

        @app.post("/api/v1/scheduler/public/available-slots")
        async def fallback_available_slots(request: FallbackSlotsRequest, db: Session = Depends(get_db)):
            """Fallback endpoint for public available slots when main scheduler routes fail to load"""
            try:
                tz = pytz.timezone("America/Chicago")
                slots = []

                start = datetime.strptime(request.start_date, "%Y-%m-%d")
                end = datetime.strptime(request.end_date, "%Y-%m-%d")

                # Check for calendar assignment
                result = db.execute(text("""
                    SELECT ca.assigned_user_id, u.full_name as user_name
                    FROM calendar_assignments ca
                    LEFT JOIN users u ON u.id = ca.assigned_user_id
                    WHERE ca.purpose = 'website_demo' AND ca.is_active = true
                    LIMIT 1
                """)).fetchone()

                user_name = result.user_name if result else "Team Member"
                user_id = result.assigned_user_id if result else None

                current = start
                while current <= end:
                    if current.weekday() < 5:  # Monday-Friday
                        for hour in range(9, 17):  # 9 AM to 5 PM
                            for minute in [0, 30]:  # Every 30 minutes
                                slot_time = tz.localize(current.replace(hour=hour, minute=minute, second=0))
                                if slot_time > datetime.now(tz):
                                    slots.append({
                                        "start_time": slot_time.isoformat(),
                                        "end_time": (slot_time + timedelta(minutes=request.duration_minutes)).isoformat(),
                                        "user_id": user_id,
                                        "user_name": user_name,
                                        "available": True
                                    })
                    current += timedelta(days=1)

                return {
                    "available_slots": slots[:100],  # Limit to 100 slots
                    "message": "Generated default availability (fallback mode)",
                    "configured": bool(result),
                    "fallback": True
                }
            except Exception as fallback_error:
                logger.error(f"Fallback scheduler error: {fallback_error}")
                return {"available_slots": [], "error": str(fallback_error), "fallback": True}

        logger.info("✅ Fallback scheduler endpoint registered")

    # Include Pre-Qualification routes (embeddable form submission)
    try:
        from prequal_routes import router as prequal_router, set_dependencies as set_prequal_deps
        from services.notification_service import notification_service

        # Set dependencies
        set_prequal_deps(get_db, notification_service)

        # Include the router
        app.include_router(prequal_router, tags=["Pre-Qualification"])
        logger.info("✅ Pre-Qualification routes loaded")
    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Could not load Pre-Qualification routes: {e}")

    # Include AI Smart Scheduler Setup routes (LO assignment configuration)
    try:
        from routes.smart_scheduler_routes import router as ai_scheduler_setup_router
        app.include_router(ai_scheduler_setup_router, prefix="/api/v1/scheduler-setup", tags=["AI Scheduler Setup"])
        logger.info("✅ AI Scheduler Setup routes loaded (LO assignment, scheduling methods)")
    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Could not load AI Scheduler Setup routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Include Enhanced Scheduler routes (Advanced features)
    try:
        from scheduler_enhancements import create_scheduler_enhancement_models
        from scheduler_enhanced_routes import router as scheduler_enhanced_router, set_enhanced_dependencies

        # Create enhanced scheduler models using our Base
        scheduler_enhanced_models = create_scheduler_enhancement_models(Base)

        # Set dependencies for the enhanced routes
        set_enhanced_dependencies(get_db, get_current_user, smart_scheduler_models, scheduler_enhanced_models)

        # Include the enhanced router
        app.include_router(scheduler_enhanced_router, tags=["Smart Scheduler Enhanced"])
        logger.info("✅ Enhanced Scheduler routes loaded (Resources, SLA, Analytics, Group Sessions)")
    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Could not load Enhanced Scheduler routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Include Calendly Integration routes
    try:
        from routes.calendly_routes import router as calendly_router
        app.include_router(calendly_router, prefix="/api/v1/calendly", tags=["Calendly Integration"])
        logger.info("✅ Calendly Integration routes loaded")
    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Could not load Calendly routes: {e}")
        logger.warning(f"Traceback: {traceback.format_exc()}")

    # Include Microsoft Teams Integration routes
    try:
        from routes.teams_routes import router as teams_router
        app.include_router(teams_router, tags=["Teams Integration"])
        logger.info("✅ Microsoft Teams Integration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Teams routes: {e}")

    # Include Video Meeting routes (UVIP - Ultimate Video Intelligence Platform)
    _video_meeting_error = None
    try:
        from video_meeting_models import create_video_meeting_models
        from video_meeting_routes import router as video_meeting_router, set_dependencies as set_video_meeting_deps

        # Create video meeting models using our Base
        video_meeting_models = create_video_meeting_models(Base)

        # Set dependencies for the routes (including pwd_context for password hashing)
        set_video_meeting_deps(get_db, get_current_user, video_meeting_models, pwd_context=pwd_context)

        # Include the router
        app.include_router(video_meeting_router, tags=["Video Meetings"])
        logger.info("✅ Video Meeting (UVIP) routes loaded")

        # Load Video Meeting WebRTC Signaling
        from video_meeting_signaling import router as video_signaling_router
        app.include_router(video_signaling_router, tags=["Video Meeting Signaling"])
        logger.info("✅ Video Meeting Signaling (WebRTC) routes loaded")
    except Exception as e:
        import traceback
        _video_meeting_error = f"{e}\n{traceback.format_exc()}"
        logger.error(f"⚠️ Could not load Video Meeting routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint to check video meeting loading status
    @app.get("/api/v1/debug/video-meetings-status", tags=["Debug"])
    async def debug_video_meetings_status():
        """Check if video meeting routes loaded successfully"""
        if _video_meeting_error:
            return {"status": "failed", "error": _video_meeting_error}
        return {"status": "loaded"}

    # Include Video Clip routes (UVIP - Async Video Messages)
    _video_clip_error = None
    try:
        from video_clip_models import create_video_clip_models
        from video_clip_routes import router as video_clip_router, set_dependencies as set_video_clip_deps

        # Create video clip models using our Base
        video_clip_models = create_video_clip_models(Base)

        # Set dependencies for the routes
        set_video_clip_deps(get_db, get_current_user, video_clip_models)

        # Include the router
        app.include_router(video_clip_router, tags=["Video Clips"])
        logger.info("✅ Video Clip (UVIP Async) routes loaded")
    except Exception as e:
        import traceback
        _video_clip_error = f"{e}\n{traceback.format_exc()}"
        logger.error(f"⚠️ Could not load Video Clip routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint to check video clip loading status
    @app.get("/api/v1/debug/video-clips-status", tags=["Debug"])
    async def debug_video_clips_status():
        """Check if video clip routes loaded successfully"""
        if _video_clip_error:
            return {"status": "failed", "error": _video_clip_error}
        return {"status": "loaded"}

    # Include Market Chat routes
    from market_chat_routes import router as market_chat_router
    app.include_router(market_chat_router, tags=["Market Chat"])

    # Include Market Data routes (scrapers)
    from market_data_routes import router as market_data_router
    app.include_router(market_data_router, tags=["Market Data"])

    # Include Rate Lock Intelligence routes (integrated from external microservice)
    from routes.rate_lock_intelligence_routes import router as rate_lock_intelligence_router
    app.include_router(rate_lock_intelligence_router, tags=["Rate Lock Intelligence"])

    # Include Rate Monitor routes (MUM refinance opportunity tracking)
    try:
        from rate_monitor_routes import router as rate_monitor_router
        app.include_router(rate_monitor_router, tags=["Rate Monitor"])
    except Exception as e:
        logger.warning(f"Could not load rate monitor routes: {e}")

    # Include Rate Sheet Upload routes (rate sheet parsing and refinance opportunities)
    try:
        from rate_sheet_routes import router as rate_sheet_router
        app.include_router(rate_sheet_router, tags=["Rate Sheets"])
    except Exception as e:
        logger.warning(f"Could not load rate sheet routes: {e}")

    # Include Gmail Integration routes
    from gmail_routes import router as gmail_router
    app.include_router(gmail_router, tags=["Gmail Integration"])

    # Include Email Drop routes (drag-and-drop email processing)
    from email_drop_routes import router as email_drop_router
    app.include_router(email_drop_router, tags=["Email Drop"])

    # Include Document Drop routes (drag-and-drop document upload)
    from document_drop_routes import router as document_drop_router
    app.include_router(document_drop_router, tags=["Document Drop"])

    # Include Smart Documents routes (intelligent document collection)
    try:
        from routes.smart_docs_routes import router as smart_docs_router
        app.include_router(smart_docs_router, tags=["Smart Documents"])
    except Exception as e:
        logger.warning(f"Could not load smart docs routes: {e}")

    # Include Portal Smart Documents routes (borrower-facing document requirements)
    try:
        from routes.portal_smart_docs_routes import router as portal_smart_docs_router
        app.include_router(portal_smart_docs_router, tags=["Portal Smart Documents"])
        logger.info("✅ Portal Smart Documents routes loaded")
    except Exception as e:
        logger.warning(f"Could not load portal smart docs routes: {e}")

    # Include Platform Contracts routes (admin licensing agreements)
    try:
        from routes.platform_contracts_routes import router as platform_contracts_router
        app.include_router(platform_contracts_router, tags=["Platform Contracts"])

        # Auto-create platform_contracts table if it doesn't exist
        try:
            from database.models.platform_contract import PlatformContract
            PlatformContract.__table__.create(engine, checkfirst=True)
            logger.info("✅ Platform Contracts table verified/created")
        except Exception as table_err:
            logger.warning(f"Could not auto-create platform_contracts table: {table_err}")

        logger.info("✅ Platform Contracts routes loaded")
    except Exception as e:
        logger.warning(f"Could not load platform contracts routes: {e}")

    # Include Income routes (AI-powered income extraction and calculation)
    try:
        from routes.income_routes import router as income_router
        app.include_router(income_router, tags=["Income Management"])

        # Auto-create income tables if they don't exist
        try:
            from models.income_models import (
                IncomeSource, PaystubExtraction, Employment,
                SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory
            )
            for model in [IncomeSource, PaystubExtraction, Employment,
                          SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory]:
                model.__table__.create(engine, checkfirst=True)
            logger.info("✅ Income tables verified/created")
        except Exception as table_err:
            logger.warning(f"Could not auto-create income tables: {table_err}")

        logger.info("✅ Income Management routes loaded")
    except Exception as e:
        logger.warning(f"Could not load income routes: {e}")

    # Include Bank Statement routes (Non-QM bank statement worksheet extraction)
    try:
        from routes.bank_statement_routes import router as bank_statement_router
        app.include_router(bank_statement_router, tags=["Bank Statement Worksheets"])
        logger.info("✅ Bank Statement Worksheet routes loaded")
    except Exception as e:
        logger.warning(f"Could not load bank statement routes: {e}")

    # Include Income Engine routes (Automated Income Intelligence Engine)
    try:
        from income_engine import income_router as income_engine_router
        app.include_router(income_engine_router, tags=["Income Intelligence Engine"])
        logger.info("✅ Income Intelligence Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load income engine routes: {e}")

    # Include Application Engine routes (URLA audit + Call Intelligence)
    try:
        from routes.application_engine_routes import router as application_engine_router
        app.include_router(application_engine_router, tags=["Application Engine"])
        logger.info("✅ Application Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load application engine routes: {e}")

    # Include Unified Income Calculator routes (all 14 income types)
    try:
        from routes.unified_income_routes import router as unified_income_router
        app.include_router(unified_income_router, tags=["Unified Income Calculator"])
        logger.info("✅ Unified Income Calculator routes loaded")
    except Exception as e:
        logger.warning(f"Could not load unified income routes: {e}")

    # Include Morning Check-in routes
    from morning_checkin_routes import router as morning_checkin_router
    app.include_router(morning_checkin_router, tags=["Morning Check-in"])

    # Include Call Recording routes (mobile app call recording + AI summary)
    try:
        from backend.api.routes.call_recording import router as call_recording_router
        app.include_router(call_recording_router, tags=["Call Recording"])
    except Exception as e:
        logger.warning(f"Could not load call recording routes: {e}")

    # Include AI Task Automation routes
    from ai_automation_routes import router as ai_automation_router
    app.include_router(ai_automation_router, tags=["AI Task Automation"])

    # Include Task Workflow routes
    from task_workflow_routes import router as task_workflow_router
    app.include_router(task_workflow_router, tags=["Task Workflow"])

    # Include Integration routes (SMS, Email, Teams)
    from integration_routes import router as integration_router
    app.include_router(integration_router, tags=["Integrations"])

    # Include Profitability Intelligence routes
    from profitability_routes import router as profitability_router
    app.include_router(profitability_router, tags=["Profitability"])

    # Include Pipeline Probability routes (Advanced Analytics)
    try:
        from routes.pipeline_probability_routes import router as pipeline_probability_router
        app.include_router(pipeline_probability_router, tags=["Pipeline Probability"])
        logger.info("✅ Pipeline Probability routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Pipeline Probability routes: {e}")

    # Include AI Insights routes for profitability
    from ai_insights_routes import router as ai_insights_router
    app.include_router(ai_insights_router, tags=["AI Profitability Insights"])

    # Include Financial Intelligence routes (Phase 3)
    from financial_intelligence_routes import router as financial_intelligence_router
    app.include_router(financial_intelligence_router, tags=["Financial Intelligence"])

    # Include Accounting System routes (Full Double-Entry Accounting)
    try:
        from routes.accounting import (
            chart_of_accounts_router, journal_entry_router, period_router,
            ar_router, ap_router, reports_router, bank_router, budget_router
        )
        app.include_router(chart_of_accounts_router, tags=["Chart of Accounts"])
        app.include_router(journal_entry_router, tags=["Journal Entries"])
        app.include_router(period_router, tags=["Accounting Periods"])
        app.include_router(ar_router, tags=["Accounts Receivable"])
        app.include_router(ap_router, tags=["Accounts Payable"])
        app.include_router(reports_router, tags=["Financial Reports"])
        app.include_router(bank_router, tags=["Banking & Plaid"])
        app.include_router(budget_router, tags=["Budgeting"])
        logger.info("✅ Accounting System routes loaded (Full Suite: CoA, JE, AR, AP, Reports, Banking, Budgets)")
    except Exception as e:
        logger.warning(f"Could not load Accounting System routes: {e}")

    # Include Business Operations Dashboard routes
    from routes.business_operations_routes import router as business_ops_router
    app.include_router(business_ops_router, tags=["Business Operations"])

    # Note: Master Manager routes already loaded above (line ~5084)

    # Include Recruiting Engine routes (Phase 2)
    try:
        from routes.recruiting_routes import router as recruiting_router
        app.include_router(recruiting_router, tags=["Recruiting"])
        logger.info("✅ Recruiting Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting routes: {e}")

    # Include Candidate Grading routes (LO Assessment & Scoring)
    try:
        from routes.candidate_grading_routes import router as grading_router
        app.include_router(grading_router, tags=["Candidate Grading"])
        logger.info("✅ Candidate Grading routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Candidate Grading routes: {e}")

    # Include Recruit Assessment routes (Quiz System + Calculator)
    try:
        from routes.recruit_assessment_routes import router as recruit_assessment_router
        app.include_router(recruit_assessment_router, tags=["Recruit Assessment"])
        logger.info("✅ Recruit Assessment routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Assessment routes: {e}")

    # Include DISC + Motivators Assessment routes
    try:
        from routes.disc_assessment_routes import router as disc_assessment_router
        app.include_router(disc_assessment_router, tags=["DISC Assessment"])
        logger.info("✅ DISC Assessment routes loaded")
    except Exception as e:
        logger.warning(f"Could not load DISC Assessment routes: {e}")

    # Include Recruiting Workflow routes (Automated Tasks)
    try:
        from routes.recruiting_workflow_routes import router as recruiting_workflow_router
        app.include_router(recruiting_workflow_router, tags=["Recruiting Workflow"])
        logger.info("✅ Recruiting Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Workflow routes: {e}")

    # Include Recruiting Dialer routes (Click-to-Call)
    try:
        from routes.recruiting_dialer_routes import router as recruiting_dialer_router
        app.include_router(recruiting_dialer_router, tags=["Recruiting Dialer"])
        logger.info("✅ Recruiting Dialer routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Dialer routes: {e}")

    # Include Recruit Portal routes (public candidate portal)
    try:
        from routes.recruit_portal_routes import router as recruit_portal_router
        app.include_router(recruit_portal_router, tags=["Recruit Portal"])
        logger.info("✅ Recruit Portal routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Portal routes: {e}")

    # Include Recruit Social Media routes (LinkedIn, Facebook, Instagram)
    try:
        from routes.recruit_social_routes import router as recruit_social_router
        app.include_router(recruit_social_router, tags=["Recruit Social"])
        logger.info("✅ Recruit Social Media routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Social Media routes: {e}")

    # Include Recruiting Video routes (video recording for candidates)
    try:
        from routes.recruiting_video_routes import router as recruiting_video_router
        app.include_router(recruiting_video_router, tags=["Recruiting Video"])
        logger.info("✅ Recruiting Video routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Video routes: {e}")

    # Include Partner Recruiting routes (LO partner recruitment)
    try:
        from routes.partner_recruiting_routes import router as partner_recruiting_router
        app.include_router(partner_recruiting_router, tags=["Partner Recruiting"])
        logger.info("✅ Partner Recruiting routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Partner Recruiting routes: {e}")

    # Include Portal Video routes (video recording for client/realtor portals)
    try:
        from routes.portal_video_routes import router as portal_video_router
        app.include_router(portal_video_router, tags=["Portal Video"])
        logger.info("✅ Portal Video routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Portal Video routes: {e}")

    # Include Acquisition Engine routes (lead scoring, speed-to-lead)
    try:
        from routes.acquisition_engine_routes import router as acquisition_router
        app.include_router(acquisition_router, tags=["Acquisition Engine"])
        logger.info("✅ Acquisition Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Acquisition Engine routes: {e}")

    # Include AI Daily Blog + PDF Content Factory routes
    from blog_routes import router as blog_router
    app.include_router(blog_router, tags=["AI Daily Blog"])

    # Include Content Marketing Automation routes (Vocable.ai-style)
    try:
        from routes.content_marketing_routes import router as content_marketing_router
        app.include_router(content_marketing_router, tags=["Content Marketing"])
        logger.info("✅ Content Marketing routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Content Marketing routes: {e}")

    # Include Carousel Builder routes (AI-powered social media carousels)
    _carousel_routes_error = None
    try:
        from routes.carousel_builder_routes import router as carousel_builder_router, set_dependencies as set_carousel_deps
        set_carousel_deps(User, get_current_user)
        app.include_router(carousel_builder_router, tags=["Carousel Builder"])
        logger.info("✅ Carousel Builder routes loaded")
    except Exception as e:
        import traceback
        _carousel_routes_error = f"{e}\n{traceback.format_exc()}"
        logger.warning(f"⚠️ Could not load Carousel Builder routes: {e}")
        logger.warning(f"Full traceback: {traceback.format_exc()}")


    @app.get("/api/v1/debug/carousel-routes-status", tags=["Debug"])
    async def debug_carousel_routes_status():
        """Check if carousel builder routes loaded successfully"""
        if _carousel_routes_error:
            return {"status": "failed", "error": _carousel_routes_error}
        return {"status": "loaded"}


    # Include Email Monitor routes
    from email_monitor_routes import router as email_monitor_router
    app.include_router(email_monitor_router, tags=["Email Monitor"])

    # Include Data Import routes (CSV/Excel upload)
    from data_import_routes import router as data_import_router
    app.include_router(data_import_router, tags=["Data Import"])

    # Include Auto Import routes (intelligent field mapping)
    from auto_import_routes import router as auto_import_router
    app.include_router(auto_import_router, tags=["Auto Import"])

    # Include Disposition routes (voice notes + AI summarization)
    from telephony.disposition_router import router as disposition_router, set_dependencies as set_disposition_deps
    set_disposition_deps(get_db, get_current_user)
    app.include_router(disposition_router, prefix="/api/v1/dialer", tags=["Dialer Dispositions"])

    # Include Dialer Analytics routes
    from telephony.analytics_router import router as dialer_analytics_router, set_dependencies as set_analytics_deps
    set_analytics_deps(get_db, get_current_user)
    app.include_router(dialer_analytics_router, prefix="/api/v1/dialer", tags=["Dialer Analytics"])

    # Include Dialer Admin routes (caller ID management)
    from telephony.admin_router import router as dialer_admin_router, set_dependencies as set_admin_deps
    set_admin_deps(get_db, get_current_user)
    app.include_router(dialer_admin_router, prefix="/api/v1/dialer", tags=["Dialer Admin"])

    # Include main Dialer router (TwiML webhooks, click-to-dial, sessions)
    from telephony.router import router as dialer_main_router, set_dependencies as set_dialer_deps
    set_dialer_deps(get_db, get_current_user)
    app.include_router(dialer_main_router, tags=["Dialer"])  # Router already has /api/v1/dialer prefix

    # Include User Onboarding System routes
    try:
        from user_onboarding_integration import create_user_onboarding_models, seed_onboarding_data, create_onboarding_router
        # Create models using our Base
        user_onboarding_models = create_user_onboarding_models(Base)
        # Create the router with dependencies
        user_onboarding_router = create_onboarding_router(
            get_db=get_db,
            get_current_user=get_current_user,
            User=User,
            models=user_onboarding_models,
            pwd_context=pwd_context,
            create_access_token=create_access_token
        )
        app.include_router(user_onboarding_router, tags=["User Onboarding"])
        logger.info("✅ User Onboarding System loaded")
    except Exception as e:
        logger.warning(f"⚠️ User Onboarding System not loaded: {e}")

    # Include User Invitation routes
    try:
        from routes.user_invitation_routes import router as invitation_router_template, get_user_invitation_routes
        from email_service import email_service
        invitation_router = get_user_invitation_routes(
            get_db=get_db,
            get_current_user=get_current_user,
            User=User,
            get_password_hash=get_password_hash,
            create_access_token=create_access_token,
            email_service=email_service
        )
        app.include_router(invitation_router, tags=["User Invitations"])
        logger.info("✅ User Invitation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ User Invitation routes not loaded: {e}")

    # Include User Creation/Onboarding routes
    # NOTE: Table names now use "onboarding_" prefix to avoid conflicts with main app models
    try:
        from routes.user_creation_routes import router as user_creation_router_template, get_user_creation_routes
        from models.user_onboarding import (
            UserProfile, Role, Category, Responsibility, PermissionTemplate,
            UserPermissions, UserCategory, UserResponsibility,
            RoleDefaultCategory, RoleDefaultResponsibility,
            KPIScorecard, BulkUploadSession, BulkUserDraft,
            UserAuditLog, OnboardingSession
        )
        user_creation_router = get_user_creation_routes(
            get_db=get_db,
            get_current_user=get_current_user,
            User=User,
            UserProfile=UserProfile,
            Role=Role,
            Category=Category,
            Responsibility=Responsibility,
            PermissionTemplate=PermissionTemplate,
            UserPermissions=UserPermissions,
            UserCategory=UserCategory,
            UserResponsibility=UserResponsibility,
            RoleDefaultCategory=RoleDefaultCategory,
            RoleDefaultResponsibility=RoleDefaultResponsibility,
            KPIScorecard=KPIScorecard,
            BulkUploadSession=BulkUploadSession,
            BulkUserDraft=BulkUserDraft,
            UserAuditLog=UserAuditLog,
            OnboardingSession=OnboardingSession,
            pwd_context=pwd_context,
            create_access_token=create_access_token,
            email_service=email_service
        )
        app.include_router(user_creation_router, tags=["User Creation & Onboarding"])
        logger.info("✅ User Creation & Onboarding routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ User Creation routes not loaded: {e}")

    # Include Google Places API routes
    try:
        from routes.places_routes import router as places_router
        app.include_router(places_router, tags=["Places API"])
        logger.info("✅ Google Places API routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Google Places API routes not loaded: {e}")

    # Include Beta Application routes
    try:
        from routes.beta_routes import router as beta_router
        app.include_router(beta_router, tags=["Beta Program"])
        logger.info("✅ Beta Application routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Beta Application routes not loaded: {e}")

    # Include Analytics Tracking routes
    try:
        from routes.analytics_tracking_routes import router as analytics_tracking_router
        app.include_router(analytics_tracking_router, tags=["Analytics Tracking"])
        logger.info("✅ Analytics Tracking routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Analytics Tracking routes not loaded: {e}")

    # Include Feature Flags routes
    try:
        from feature_flags_routes import router as feature_flags_router
        app.include_router(feature_flags_router, tags=["Feature Flags"])
        logger.info("✅ Feature Flags routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Feature Flags routes not loaded: {e}")

    # Include Email Intelligence routes
    try:
        from routes.email_intelligence_routes import router as email_intelligence_router
        app.include_router(email_intelligence_router, tags=["Email Intelligence"])
        logger.info("✅ Email Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Email Intelligence routes not loaded: {e}")

    # Include SMS Intelligence routes
    try:
        from routes.sms_intelligence_routes import router as sms_intelligence_router
        app.include_router(sms_intelligence_router, tags=["SMS Intelligence"])
        logger.info("✅ SMS Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ SMS Intelligence routes not loaded: {e}")

    # Include SLA Tracking routes
    try:
        from routes.sla_tracking_routes import router as sla_tracking_router
        app.include_router(sla_tracking_router, tags=["SLA Tracking"])
        logger.info("✅ SLA Tracking routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ SLA Tracking routes not loaded: {e}")

    # Include AI Feedback routes
    try:
        from routes.ai_feedback_routes import router as ai_feedback_router
        from routes import ai_feedback_routes
        ai_feedback_routes.set_dependencies(get_db, get_current_user)
        ai_feedback_routes.ensure_tables_exist(engine)
        app.include_router(ai_feedback_router, prefix="/api/v1/ai-feedback", tags=["AI Feedback"])
        logger.info("✅ AI Feedback routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ AI Feedback routes not loaded: {e}")

    # Include AI Metrics routes (hallucination tracking, performance metrics)
    try:
        from routes.ai_metrics_routes import router as ai_metrics_router
        app.include_router(ai_metrics_router, prefix="/api/v1/ai-metrics", tags=["AI Metrics"])
        logger.info("✅ AI Metrics routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ AI Metrics routes not loaded: {e}")

    # AI Email Conversations (Two-Way AI Communication)
    try:
        from routes.ai_email_conversation_routes import router as ai_email_conv_router
        app.include_router(ai_email_conv_router, prefix="/api/v1/ai-email", tags=["AI Email Conversations"])
        logger.info("✅ AI Email Conversation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ AI Email Conversation routes not loaded: {e}")

    # AI Email Search Routes (for AI agents to search and analyze emails)
    try:
        from routes.ai_email_search_routes import router as ai_email_search_router
        app.include_router(ai_email_search_router, tags=["AI Email Search"])
        logger.info("✅ AI Email Search routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ AI Email Search routes not loaded: {e}")

    # AI Tools Registry & Unified Tool Endpoints
    tools_router_error = None
    try:
        from tools.router import router as tools_router
        app.include_router(tools_router, tags=["AI Tools"])
        logger.info("✅ AI Tools Registry routes loaded")
    except Exception as e:
        tools_router_error = str(e)
        import traceback
        full_error = traceback.format_exc()
        logger.warning(f"⚠️ AI Tools Registry routes not loaded: {e}")
        logger.warning(f"Full traceback: {full_error}")

    # Cache Management routes (for AI response caching)
    try:
        from api.cache_routes import router as cache_router
        app.include_router(cache_router, prefix="/api/v1", tags=["Cache Management"])
        logger.info("✅ Cache Management routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Cache Management routes not loaded: {e}")

    # Webhook routes (for cache invalidation from external systems)
    try:
        from api.webhooks import router as webhooks_router
        app.include_router(webhooks_router, prefix="/api/v1", tags=["Webhooks"])
        logger.info("✅ Webhook routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Webhook routes not loaded: {e}")

    # RETR Import Webhook routes (for importing realtors and loan officers)
    try:
        from routes.webhook_routes import router as retr_webhook_router
        app.include_router(retr_webhook_router, tags=["RETR Webhooks"])
        logger.info("✅ RETR webhook routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ RETR webhook routes not loaded: {e}")

    # Stripe Billing Webhook routes
    try:
        from routes.stripe_webhook_routes import router as stripe_webhook_router
        app.include_router(stripe_webhook_router, tags=["Stripe Billing"])
        logger.info("✅ Stripe webhook routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Stripe webhook routes not loaded: {e}")

    # Monitoring routes (cache health and performance metrics)
    try:
        from api.monitoring import router as monitoring_router
        app.include_router(monitoring_router, prefix="/api/v1", tags=["Monitoring"])
        logger.info("✅ Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Monitoring routes not loaded: {e}")

    # Performance Monitoring routes (slow queries, endpoint stats, alerts config)
    try:
        from routes.performance_routes import router as performance_router
        app.include_router(performance_router, tags=["Performance Monitoring"])
        logger.info("✅ Performance Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Performance Monitoring routes not loaded: {e}")

    # Phase 3 Advanced Features routes
    try:
        from routes.phase3_routes import bi_router, insights_router, compliance_router, webhook_router
        app.include_router(bi_router, tags=["AI Receptionist Analytics"])
        app.include_router(insights_router, tags=["Conversational Insights"])
        app.include_router(compliance_router, tags=["Call Compliance"])
        app.include_router(webhook_router, tags=["Webhook Automation"])
        logger.info("✅ Phase 3 Advanced Features routes loaded (Analytics, Insights, Compliance, Webhooks)")
    except Exception as e:
        logger.warning(f"⚠️ Phase 3 routes not loaded: {e}")

    # Phase 4 AI Learning & Optimization routes
    try:
        from routes.phase4_routes import voice_ab_router, ai_learning_router, meta_agent_router
        app.include_router(voice_ab_router, tags=["Voice A/B Testing"])
        app.include_router(ai_learning_router, tags=["AI Learning"])
        app.include_router(meta_agent_router, tags=["Continuous Learning Meta-Agent"])
        logger.info("✅ Phase 4 AI Learning & Optimization routes loaded (Voice A/B, AI Learning, Meta-Agent)")
    except Exception as e:
        logger.warning(f"⚠️ Phase 4 routes not loaded: {e}")

    # Phase 5 Premium Features & White-Label routes
    try:
        from routes.phase5_routes import escalation_router, qa_router, biometrics_router, tenant_router
        app.include_router(escalation_router, tags=["Live Agent Escalation"])
        app.include_router(qa_router, tags=["Call Quality Assurance"])
        app.include_router(biometrics_router, tags=["Voice Biometrics"])
        app.include_router(tenant_router, tags=["Multi-Tenant Management"])
        logger.info("✅ Phase 5 Premium Features routes loaded (Escalation, QA, Biometrics, Multi-Tenant)")
    except Exception as e:
        logger.warning(f"⚠️ Phase 5 routes not loaded: {e}")

    # Phase 6 Advanced AI Orchestration & Automation routes
    try:
        from routes.phase6_routes import workflow_router, predictive_router, agent_coordination_router, healing_router
        app.include_router(workflow_router, tags=["Advanced Workflow Orchestration"])
        app.include_router(predictive_router, tags=["Predictive AI & Recommendations"])
        app.include_router(agent_coordination_router, tags=["AI Agent Coordination"])
        app.include_router(healing_router, tags=["Self-Healing System"])
        logger.info("✅ Phase 6 Advanced AI Orchestration routes loaded (Workflows, Predictive AI, Agent Coordination, Self-Healing)")
    except Exception as e:
        logger.warning(f"⚠️ Phase 6 routes not loaded: {e}")

    # OAuth routes (Microsoft, Google integrations)
    try:
        from oauth_routes import router as oauth_router
        app.include_router(oauth_router, prefix="/api", tags=["OAuth"])
        logger.info("✅ OAuth routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ OAuth routes not loaded: {e}")

    # Salesforce Integration routes (OAuth, Webhooks, Sync)
    try:
        from routes.salesforce_routes import router as salesforce_router
        app.include_router(salesforce_router, prefix="/api/v1/salesforce", tags=["Salesforce Integration"])
        logger.info("✅ Salesforce routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Salesforce routes not loaded: {e}")

    # Salesforce Per-User Integration routes (OAuth, Schema Discovery, Field Mapping, Sync)
    try:
        from routes.salesforce_integration_routes import router as salesforce_integration_router
        app.include_router(salesforce_integration_router, tags=["Salesforce User Integration"])
        logger.info("✅ Salesforce user integration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Salesforce user integration routes not loaded: {e}")

    # Calendar Sync routes (CRM ↔ Salesforce ↔ Outlook calendar synchronization)
    try:
        from models.calendar_sync_models import CRMCalendarEvent, CalendarEventSyncMap, CalendarSyncLog, CalendarSyncSettings
        for model in [CRMCalendarEvent, CalendarEventSyncMap, CalendarSyncLog, CalendarSyncSettings]:
            try:
                model.__table__.create(engine, checkfirst=True)
            except Exception:
                pass
        from routes.calendar_sync_routes import router as calendar_sync_router
        app.include_router(calendar_sync_router, tags=["Calendar Sync"])
        logger.info("✅ Calendar sync routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Calendar sync routes not loaded: {e}")

    # Calendar Events routes (CRUD for user calendar events)
    try:
        from routes.calendar_routes import router as calendar_events_router
        app.include_router(calendar_events_router, tags=["Calendar Events"])
        logger.info("✅ Calendar events routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Calendar events routes not loaded: {e}")

    # Unified Calendar routes (merges calendar, scheduler, and CRM events)
    try:
        from routes.unified_calendar_routes import router as unified_calendar_router
        app.include_router(unified_calendar_router, tags=["Unified Calendar"])
        logger.info("✅ Unified calendar routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Unified calendar routes not loaded: {e}")

    # HubSpot Integration routes (OAuth, CRM Sync)
    try:
        from routes.hubspot_routes import router as hubspot_router, set_dependencies as set_hubspot_deps
        set_hubspot_deps(get_db, get_current_user)
        app.include_router(hubspot_router, tags=["HubSpot Integration"])
        logger.info("✅ HubSpot routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ HubSpot routes not loaded: {e}")

    # Follow Up Boss Integration routes (CRM Sync, Webhooks)
    try:
        from routes.followupboss_routes import router as followupboss_router, set_dependencies as set_fub_deps
        from routes.followupboss_webhook_routes import router as followupboss_webhook_router
        set_fub_deps(get_db, get_current_user)
        app.include_router(followupboss_router, prefix="/api/v1", tags=["Follow Up Boss Integration"])
        app.include_router(followupboss_webhook_router, prefix="/api", tags=["Follow Up Boss Webhooks"])
        logger.info("✅ Follow Up Boss routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Follow Up Boss routes not loaded: {e}")

    # Google Calendar Integration routes (OAuth, Calendar Sync)
    try:
        from routes.google_calendar_routes import router as google_calendar_router, set_dependencies as set_google_calendar_deps
        set_google_calendar_deps(get_db, get_current_user)
        app.include_router(google_calendar_router, tags=["Google Calendar Integration"])
        logger.info("✅ Google Calendar routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Google Calendar routes not loaded: {e}")

    # Zoom Integration routes (OAuth, Meetings)
    try:
        from routes.zoom_routes import router as zoom_router, set_dependencies as set_zoom_deps
        set_zoom_deps(get_db, get_current_user)
        app.include_router(zoom_router, tags=["Zoom Integration"])
        logger.info("✅ Zoom routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Zoom routes not loaded: {e}")

    # Slack Integration routes (OAuth, Messaging)
    try:
        from routes.slack_routes import router as slack_router, set_dependencies as set_slack_deps
        set_slack_deps(get_db, get_current_user)
        app.include_router(slack_router, tags=["Slack Integration"])
        logger.info("✅ Slack routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Slack routes not loaded: {e}")

    # DocuSign Integration routes (OAuth, E-Signatures)
    try:
        from routes.docusign_routes import router as docusign_router, set_dependencies as set_docusign_deps
        set_docusign_deps(get_db, get_current_user)
        app.include_router(docusign_router, tags=["DocuSign Integration"])
        logger.info("✅ DocuSign routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ DocuSign routes not loaded: {e}")

    # Microsoft Outlook Integration routes (OAuth, Calendar, Email)
    try:
        from routes.microsoft_routes import router as microsoft_router, set_dependencies as set_microsoft_deps
        set_microsoft_deps(get_db, get_current_user)
        app.include_router(microsoft_router, tags=["Microsoft Outlook Integration"])

        # Legacy OAuth callback path - redirect to new path
        from fastapi.responses import RedirectResponse
        @app.get("/oauth/microsoft/callback", tags=["Microsoft OAuth Legacy"])
        async def legacy_microsoft_callback(request: Request):
            """Legacy OAuth callback - redirects to new path with query params"""
            query_string = str(request.url.query)
            return RedirectResponse(url=f"/api/v1/microsoft/callback?{query_string}", status_code=307)

        logger.info("✅ Microsoft Outlook routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Microsoft Outlook routes not loaded: {e}")

    # Listing Agent Portal routes (Transaction updates for listing agents)
    try:
        from routes.listing_portal_routes import router as listing_portal_router, set_dependencies as set_listing_portal_deps
        set_listing_portal_deps(get_db, get_current_user)
        app.include_router(listing_portal_router, tags=["Listing Agent Portal"])
        logger.info("✅ Listing Agent Portal routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Listing Agent Portal routes not loaded: {e}")

    # Video OS routes (Internal video generation, hosting, and analytics)
    try:
        from routes.video_os_routes import router as video_os_router, set_dependencies as set_video_os_deps
        set_video_os_deps(get_db, get_current_user)
        app.include_router(video_os_router, tags=["Video OS"])
        logger.info("✅ Video OS routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Video OS routes not loaded: {e}")

    # Avatar routes (AI avatar profile management and video generation)
    try:
        from routes.avatar_routes import router as avatar_router, set_dependencies as set_avatar_deps
        set_avatar_deps(get_db, get_current_user)
        app.include_router(avatar_router, tags=["AI Avatars"])
        logger.info("✅ Avatar routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Avatar routes not loaded: {e}")

    # Vidyard routes (AI Avatar video generation via Vidyard API)
    try:
        from routes.vidyard_routes import router as vidyard_router
        app.include_router(vidyard_router, tags=["Vidyard"])
        logger.info("✅ Vidyard routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Vidyard routes not loaded: {e}")

    # Agent Governance routes (Agent Management & Monitoring)
    try:
        from routes.agent_governance_routes import router as agent_governance_router
        app.include_router(agent_governance_router, tags=["Agent Governance"])
        logger.info("✅ Agent Governance routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent Governance routes not loaded: {e}")

    # Agent Governance Settings routes (Proof-of-concept with comprehensive error handling)
    try:
        from routes.agent_governance_settings_routes import router as agent_governance_settings_router
        app.include_router(agent_governance_settings_router, tags=["Agent Governance Settings"])
        logger.info("✅ Agent Governance Settings routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent Governance Settings routes not loaded: {e}")

    # Page Permissions routes (Role-based page access control)
    # Note: Page Permissions routes already loaded above (line ~5068)

    # Smart Scheduler Settings routes (Comprehensive error handling pattern)
    try:
        from routes.smart_scheduler_settings_routes import router as smart_scheduler_settings_router, set_dependencies as set_scheduler_settings_deps
        set_scheduler_settings_deps(get_current_user)
        app.include_router(smart_scheduler_settings_router, tags=["Smart Scheduler Settings"])
        logger.info("✅ Smart Scheduler Settings routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Smart Scheduler Settings routes not loaded: {e}")

    # Email Integration Settings routes (Comprehensive error handling pattern)
    try:
        from routes.email_integration_settings_routes import router as email_integration_settings_router
        app.include_router(email_integration_settings_router, tags=["Email Integration Settings"])
        logger.info("Email Integration Settings routes loaded")
    except Exception as e:
        logger.warning(f"Email Integration Settings routes not loaded: {e}")

    # User Profile Settings routes (Comprehensive error handling pattern)
    try:
        from routes.user_profile_settings_routes import router as user_profile_settings_router, set_dependencies as set_user_profile_deps
        set_user_profile_deps(User, get_current_user, pwd_context)
        app.include_router(user_profile_settings_router, tags=["User Profile Settings"])
        logger.info("User Profile Settings routes loaded")
    except Exception as e:
        logger.warning(f"User Profile Settings routes not loaded: {e}")

    # Account Management routes (Master Administrator)
    try:
        from routes.account_management_routes import router as account_management_router, set_dependencies as set_account_mgmt_deps
        set_account_mgmt_deps(User, get_current_user)
        app.include_router(account_management_router, tags=["Account Management"])
        logger.info("Account Management routes loaded")
    except Exception as e:
        logger.warning(f"Account Management routes not loaded: {e}")

    # Admin Onboarding routes (Subscription signup wizard)
    try:
        from routes.admin_onboarding_routes import router as admin_onboarding_router
        app.include_router(admin_onboarding_router, tags=["Admin Onboarding"])
        logger.info("✅ Admin Onboarding routes loaded")
    except Exception as e:
        logger.warning(f"Admin Onboarding routes not loaded: {e}")

    # Security Monitoring routes (Admin Dashboard Security Tab)
    try:
        from routes.security_monitoring_routes import router as security_monitoring_router, set_dependencies as set_security_monitoring_deps
        set_security_monitoring_deps(get_current_user)
        app.include_router(security_monitoring_router, tags=["Security Monitoring"])
        logger.info("✅ Security Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Security Monitoring routes not loaded: {e}")

    # Document Upload Settings routes (Comprehensive error handling pattern)
    try:
        from routes.document_upload_settings_routes import router as document_upload_settings_router, set_dependencies as set_document_upload_deps
        set_document_upload_deps(User, get_current_user, get_db)
        app.include_router(document_upload_settings_router, tags=["Document Upload Settings"])
        logger.info("Document Upload Settings routes loaded")
    except Exception as e:
        logger.warning(f"Document Upload Settings routes not loaded: {e}")

    # Lead Capture Settings routes (Comprehensive error handling pattern)
    try:
        from routes.lead_capture_settings_routes import router as lead_capture_settings_router, set_dependencies as set_lead_capture_deps
        set_lead_capture_deps(User, get_current_user, get_db)
        app.include_router(lead_capture_settings_router, tags=["Lead Capture Settings"])
        logger.info("Lead Capture Settings routes loaded")
    except Exception as e:
        logger.warning(f"Lead Capture Settings routes not loaded: {e}")

    # Client Portal Settings routes (Comprehensive error handling pattern)
    try:
        from routes.client_portal_settings_routes import router as client_portal_settings_router, set_dependencies as set_client_portal_deps
        set_client_portal_deps(User, get_current_user, get_db)
        app.include_router(client_portal_settings_router, tags=["Client Portal Settings"])
        logger.info("Client Portal Settings routes loaded")
    except Exception as e:
        logger.warning(f"Client Portal Settings routes not loaded: {e}")

    # Communication Preferences routes (Comprehensive error handling pattern)
    try:
        from routes.communication_preferences_routes import router as communication_preferences_router, set_dependencies as set_communication_deps
        set_communication_deps(User, get_current_user, get_db)
        app.include_router(communication_preferences_router, tags=["Communication Preferences"])
        logger.info("Communication Preferences routes loaded")
    except Exception as e:
        logger.warning(f"Communication Preferences routes not loaded: {e}")

    # Integration Settings routes (Comprehensive error handling pattern)
    try:
        from routes.integration_settings_routes import router as integration_settings_router, set_dependencies as set_integration_deps
        set_integration_deps(User, get_current_user, get_db)
        app.include_router(integration_settings_router, tags=["Integration Settings"])
        logger.info("Integration Settings routes loaded")
    except Exception as e:
        logger.warning(f"Integration Settings routes not loaded: {e}")

    # ElevenLabs Voice AI routes
    try:
        from routes.elevenlabs_routes import router as elevenlabs_router, set_dependencies as set_elevenlabs_deps
        set_elevenlabs_deps(User, get_current_user, get_db)
        app.include_router(elevenlabs_router, tags=["ElevenLabs"])
        logger.info("ElevenLabs routes loaded")
    except Exception as e:
        logger.warning(f"ElevenLabs routes not loaded: {e}")

    # Twilio Self-Service Setup routes
    try:
        from routes.twilio_setup_routes import router as twilio_setup_router, set_dependencies as set_twilio_setup_deps
        set_twilio_setup_deps(User, get_current_user, get_db)
        app.include_router(twilio_setup_router, tags=["Twilio Setup"])
        logger.info("Twilio Setup routes loaded")
    except Exception as e:
        logger.warning(f"Twilio Setup routes not loaded: {e}")

    # Telnyx Self-Service Setup routes
    try:
        from routes.telnyx_setup_routes import router as telnyx_setup_router, set_dependencies as set_telnyx_setup_deps
        set_telnyx_setup_deps(User, get_current_user, get_db)
        app.include_router(telnyx_setup_router, tags=["Telnyx Setup"])
        logger.info("✅ Telnyx Setup routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Telnyx Setup routes not loaded: {e}")

    # Retell AI Voice Platform routes (replaces ElevenLabs + Twilio)
    try:
        from routes.retell_routes import router as retell_router, set_dependencies as set_retell_deps
        set_retell_deps(User, get_current_user, get_db)
        app.include_router(retell_router, tags=["Retell AI"])
        logger.info("Retell AI routes loaded")
    except Exception as e:
        logger.warning(f"Retell AI routes not loaded: {e}")

    # Telnyx-Retell Bridge routes (connect Telnyx numbers to Retell AI)
    try:
        from routes.telnyx_retell_routes import router as telnyx_retell_router, set_dependencies as set_telnyx_retell_deps
        set_telnyx_retell_deps(User, get_current_user, get_db)
        app.include_router(telnyx_retell_router, tags=["Telnyx-Retell Bridge"])
        logger.info("Telnyx-Retell Bridge routes loaded")
    except Exception as e:
        logger.warning(f"Telnyx-Retell Bridge routes not loaded: {e}")

    # API Keys Settings routes (Comprehensive error handling pattern)
    try:
        from routes.api_keys_settings_routes import router as api_keys_settings_router, set_dependencies as set_api_keys_deps
        set_api_keys_deps(User, get_current_user, get_db)
        app.include_router(api_keys_settings_router, tags=["API Keys Settings"])
        logger.info("API Keys Settings routes loaded")
    except Exception as e:
        logger.warning(f"API Keys Settings routes not loaded: {e}")

    # Company Branding Settings routes (Comprehensive error handling pattern)
    try:
        from routes.company_branding_routes import router as company_branding_router, set_dependencies as set_company_branding_deps
        set_company_branding_deps(User, get_current_user, get_db)
        app.include_router(company_branding_router, tags=["Company & Branding"])
        logger.info("Company Branding Settings routes loaded")
    except Exception as e:
        logger.warning(f"Company Branding Settings routes not loaded: {e}")

    # Application Slides Settings routes (Customize application flow)
    try:
        from routes.application_slides_settings_routes import router as application_slides_router, set_dependencies as set_app_slides_deps
        set_app_slides_deps(User, get_current_user, get_db)
        app.include_router(application_slides_router, tags=["Application Slides Settings"])
        logger.info("Application Slides Settings routes loaded")
    except Exception as e:
        logger.warning(f"Application Slides Settings routes not loaded: {e}")

    # Agent Gym routes (Agent Training & Simulation)
    try:
        from routes.agent_gym_routes import router as agent_gym_router
        app.include_router(agent_gym_router, tags=["Agent Gym"])
        logger.info("✅ Agent Gym routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent Gym routes not loaded: {e}")

    # Agent Chat routes (Interactive Agent Chat)
    try:
        from routes.agent_chat_routes import router as agent_chat_router
        app.include_router(agent_chat_router, tags=["Agent Chat"])
        logger.info("✅ Agent Chat routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent Chat routes not loaded: {e}")

    # Agent WebSocket routes (Real-time Agent Metrics & Updates)
    try:
        from routes.agent_websocket import router as agent_websocket_router
        app.include_router(agent_websocket_router, tags=["Agent WebSocket"])
        logger.info("✅ Agent WebSocket routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent WebSocket routes not loaded: {e}")

    # Agent Orchestration routes (Token-optimized AI Agent Execution)
    try:
        from api.v1.agents import router as agent_orchestration_router
        app.include_router(agent_orchestration_router, tags=["Agent Orchestration"])
        logger.info("✅ Agent Orchestration routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Agent Orchestration routes not loaded: {e}")

    # Pipeline Efficiency routes (Real-time pipeline analytics)
    try:
        from pipeline_efficiency_routes import router as pipeline_efficiency_router, set_dependencies as set_pipeline_deps
        # Pass models dict to avoid circular imports
        pipeline_models = {
            'Lead': Lead,
            'Loan': Loan,
            'LeadStage': LeadStage,
            'LoanStage': LoanStage,
            'User': User,
        }
        set_pipeline_deps(get_db, get_current_user, pipeline_models)
        app.include_router(pipeline_efficiency_router, tags=["Pipeline Efficiency"])
        logger.info("✅ Pipeline Efficiency routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Pipeline Efficiency routes not loaded: {e}")

    # PURL (Persistent URL) Borrower Portal routes
    purl_routes_error = None
    try:
        from routes.purl_routes import purl_router, purl_admin_router
        app.include_router(purl_router, tags=["PURL Portal"])
        app.include_router(purl_admin_router, tags=["PURL Administration"])
        logger.info("✅ PURL Portal routes loaded")
    except Exception as e:
        purl_routes_error = str(e)
        import traceback
        purl_routes_error = traceback.format_exc()
        logger.warning(f"⚠️ PURL Portal routes not loaded: {e}")

    # Workspace Documents routes (for DocumentsNeeded component)
    try:
        from routes.workspace_documents_routes import router as workspace_documents_router
        app.include_router(workspace_documents_router, tags=["Workspace Documents"])
        logger.info("✅ Workspace Documents routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Workspace Documents routes not loaded: {e}")

    # Estimate Parser routes (Loan Estimate comparison tool)
    try:
        from routes.estimate_parser_routes import router as estimate_parser_router
        app.include_router(estimate_parser_router, tags=["Estimate Parser"])
        logger.info("✅ Estimate Parser routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Estimate Parser routes not loaded: {e}")

    # Call Routing routes (Intelligent Vapi call routing based on CRM stage)
    try:
        from routes.call_routing_routes import router as call_routing_router
        app.include_router(call_routing_router, tags=["Call Routing"])
        logger.info("✅ Call Routing routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Call Routing routes not loaded: {e}")

    # Chat State Machine routes (Phase-based microsite chat)
    try:
        from chat_state_routes import router as chat_state_router
        app.include_router(chat_state_router, tags=["Chat State Machine"])
        logger.info("✅ Chat State Machine routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Chat State Machine routes not loaded: {e}")

    # Twilio Click-to-Call routes (for chat widget calling)
    try:
        from services.twilio_click_to_call import twilio_router
        app.include_router(twilio_router, tags=["Twilio Click-to-Call"])
        logger.info("✅ Twilio Click-to-Call routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Twilio Click-to-Call routes not loaded: {e}")

    # Surveying & Feedback routes (Customer satisfaction surveys, NPS, CSAT)
    try:
        from routes.survey_routes import router as survey_router
        app.include_router(survey_router, tags=["Surveys & Feedback"])
        logger.info("✅ Survey routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Survey routes not loaded: {e}")

    @app.get("/api/v1/debug/purl-routes-status")
    async def debug_purl_routes_status():
        """Debug endpoint to check PURL routes loading status"""
        return {
            "purl_routes_loaded": purl_routes_error is None,
            "error": purl_routes_error
        }

    @app.get("/api/v1/debug/purl-tables-status")
    async def debug_purl_tables_status(db: Session = Depends(get_db)):
        """Debug endpoint to check if PURL tables exist in database"""
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        all_tables = inspector.get_table_names()

        purl_tables_expected = [
            'purl_workspaces',
            'purl_contacts',
            'purl_workspace_members',
            'purl_access_tokens',
            'purl_applications',
            'purl_loans',
            'purl_documents',
            'purl_portal_modules',
            'purl_milestone_definitions',
            'purl_loan_milestones',
            'purl_tasks',
            'purl_messages',
            'purl_events_outbox',
            'purl_audit_log',
            'purl_document_requests'
        ]

        existing_purl_tables = [t for t in all_tables if t.startswith('purl_')]
        missing_purl_tables = [t for t in purl_tables_expected if t not in all_tables]

        return {
            "purl_tables_exist": len(missing_purl_tables) == 0,
            "existing_purl_tables": existing_purl_tables,
            "missing_purl_tables": missing_purl_tables,
            "all_table_count": len(all_tables)
        }

    @app.get("/api/v1/debug/user-delete-diagnosis")
    async def debug_user_delete_diagnosis(
        user_id: int,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to diagnose user deletion blockers (no actual deletion)"""
        # Check if user exists
        user = db.execute(text("SELECT id, email, full_name FROM users WHERE id = :uid"), {"uid": user_id}).fetchone()
        if not user:
            return {"error": "User not found", "user_id": user_id}

        # Get all FK constraints referencing users table
        fk_query = """
            SELECT tc.table_name, kcu.column_name, tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'users' AND tc.table_schema = 'public'
            ORDER BY tc.table_name
        """
        fks = db.execute(text(fk_query)).fetchall()

        # Check which tables reference this user
        blocking_tables = []
        for table_name, column_name, constraint_name in fks:
            if table_name == 'users':
                continue
            try:
                count = db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :uid"),
                    {"uid": user_id}
                ).scalar()
                if count > 0:
                    blocking_tables.append({
                        "table": table_name,
                        "column": column_name,
                        "references": count
                    })
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    blocking_tables.append({
                        "table": table_name,
                        "column": column_name,
                        "error": str(e)[:100]
                    })

        return {
            "user_id": user_id,
            "user_email": user[1],
            "user_name": user[2],
            "total_fk_constraints": len(fks),
            "blocking_references": blocking_tables,
            "can_delete": len(blocking_tables) == 0
        }

    @app.get("/api/v1/debug/list-test-users")
    async def debug_list_test_users(db: Session = Depends(get_db)):
        """List users available for testing (non-admin only)"""
        users = db.execute(text("""
            SELECT id, email, full_name, is_active, role
            FROM users
            WHERE email NOT LIKE '%admin%'
            ORDER BY id DESC
            LIMIT 10
        """)).fetchall()
        return {
            "users": [{"id": u[0], "email": u[1], "name": u[2], "active": u[3], "role": u[4]} for u in users],
            "note": "Use these IDs with /api/v1/debug/user-delete-diagnosis?user_id=X"
        }

    @app.get("/api/v1/debug/purl-token-verify")
    async def debug_purl_token_verify(
        token: str,
        workspace_slug: str,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to test PURL token verification"""
        import hashlib

        # Token format validation
        token_prefix = "purl_live_"
        is_valid_format = token.startswith(token_prefix) and len(token) == len(token_prefix) + 64

        # Compute hash
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Check workspace
        workspace = db.execute(text("""
            SELECT id, slug, organization_id, status
            FROM purl_workspaces
            WHERE slug = :slug
        """), {"slug": workspace_slug}).fetchone()

        workspace_info = None
        if workspace:
            workspace_info = {
                "id": workspace[0],
                "slug": workspace[1],
                "organization_id": workspace[2],
                "status": workspace[3]
            }

        # Check tokens for workspace
        tokens_info = []
        if workspace:
            tokens = db.execute(text("""
                SELECT id, token_hash, token_prefix, scope, status, expires_at, created_at
                FROM purl_access_tokens
                WHERE workspace_id = :workspace_id
            """), {"workspace_id": workspace[0]}).fetchall()

            for t in tokens:
                tokens_info.append({
                    "id": t[0],
                    "stored_hash": t[1],
                    "hash_matches": t[1] == token_hash,
                    "prefix": t[2],
                    "scope": t[3],
                    "status": t[4],
                    "expires_at": str(t[5]) if t[5] else None,
                    "created_at": str(t[6]) if t[6] else None
                })

        # Direct hash lookup
        token_by_hash = db.execute(text("""
            SELECT id, workspace_id, scope, status
            FROM purl_access_tokens
            WHERE token_hash = :hash
        """), {"hash": token_hash}).fetchone()

        hash_lookup = None
        if token_by_hash:
            hash_lookup = {
                "id": token_by_hash[0],
                "workspace_id": token_by_hash[1],
                "scope": token_by_hash[2],
                "status": token_by_hash[3]
            }

        return {
            "token_length": len(token),
            "expected_length": 74,
            "is_valid_format": is_valid_format,
            "computed_hash": token_hash,
            "workspace": workspace_info,
            "tokens_for_workspace": tokens_info,
            "token_found_by_hash": hash_lookup is not None,
            "hash_lookup_result": hash_lookup
        }

    @app.post("/api/v1/debug/purl-create-test-workspace")
    async def debug_create_test_workspace(
        test_name: str = "debug-test",
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to create a test PURL workspace with token"""
        import hashlib
        import secrets

        try:
            # Generate slug
            random_suffix = secrets.token_hex(4)
            slug = f"{test_name.lower().replace(' ', '-')}-{random_suffix}"

            # Create workspace
            workspace = db.execute(text("""
                INSERT INTO purl_workspaces (
                    organization_id, slug, display_name, status, created_at, updated_at
                ) VALUES (
                    1, :slug, :display_name, 'lead', NOW(), NOW()
                )
                RETURNING id, slug
            """), {"slug": slug, "display_name": test_name}).fetchone()
            db.commit()

            workspace_id = workspace[0]
            workspace_slug = workspace[1]

            # Generate token
            token_bytes = secrets.token_bytes(32)
            token_hex = token_bytes.hex()
            full_token = f"purl_live_{token_hex}"
            token_hash = hashlib.sha256(full_token.encode()).hexdigest()
            token_prefix = full_token[:16]

            # Create token
            from datetime import timezone, timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            token = db.execute(text("""
                INSERT INTO purl_access_tokens (
                    organization_id, workspace_id, token_hash, token_prefix,
                    scope, status, expires_at, created_at
                ) VALUES (
                    1, :workspace_id, :token_hash, :token_prefix,
                    'full', 'active', :expires_at, NOW()
                )
                RETURNING id
            """), {
                "workspace_id": workspace_id,
                "token_hash": token_hash,
                "token_prefix": token_prefix,
                "expires_at": expires_at
            }).fetchone()
            db.commit()

            return {
                "success": True,
                "workspace_id": workspace_id,
                "workspace_slug": workspace_slug,
                "token": full_token,
                "token_id": token[0],
                "expires_at": expires_at.isoformat(),
                "portal_url": f"https://perenniaai.com/portal/{workspace_slug}",
                "test_curl": f'curl -H "Authorization: Bearer {full_token}" "https://app.perenniaai.com/api/purl/workspace/{workspace_slug}"'
            }
        except Exception as e:
            db.rollback()
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }

    @app.get("/api/v1/debug/purl-auth-flow")
    async def debug_purl_auth_flow(
        token: str,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to test the full PURL auth flow"""
        import traceback

        result = {
            "token_received": token[:20] + "...",
            "token_length": len(token),
            "steps": {}
        }

        try:
            # Step 1: Format validation
            from models.purl import PURLTokenGenerator, TokenScope, TokenStatus
            is_valid = PURLTokenGenerator.is_valid_format(token)
            result["steps"]["1_format_valid"] = is_valid

            if not is_valid:
                result["error"] = "Token format invalid"
                return result

            # Step 2: Hash token
            token_hash = PURLTokenGenerator.hash_token(token)
            result["steps"]["2_token_hash"] = token_hash[:20] + "..."

            # Step 3: Query token
            from models.purl import PURLAccessToken
            token_record = db.query(PURLAccessToken).filter(
                PURLAccessToken.token_hash == token_hash
            ).first()

            result["steps"]["3_token_found"] = token_record is not None

            if not token_record:
                result["error"] = "Token not found in database"
                return result

            result["steps"]["3_token_id"] = token_record.id
            result["steps"]["3_token_status"] = token_record.status
            result["steps"]["3_token_scope"] = token_record.scope

            # Step 4: Check status
            result["steps"]["4_status_check"] = token_record.status == TokenStatus.ACTIVE.value

            if token_record.status != TokenStatus.ACTIVE.value:
                result["error"] = f"Token status is {token_record.status}, not active"
                return result

            # Step 5: Check expiration
            from datetime import datetime, timezone
            if token_record.expires_at:
                is_expired = token_record.expires_at < datetime.now(timezone.utc)
                result["steps"]["5_expiration_check"] = not is_expired
                result["steps"]["5_expires_at"] = str(token_record.expires_at)

                if is_expired:
                    result["error"] = "Token is expired"
                    return result
            else:
                result["steps"]["5_expiration_check"] = "No expiration"

            # Step 6: Get workspace
            from models.purl import PURLWorkspace
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == token_record.workspace_id
            ).first()

            result["steps"]["6_workspace_found"] = workspace is not None

            if not workspace:
                result["error"] = "Workspace not found"
                return result

            result["steps"]["6_workspace_id"] = workspace.id
            result["steps"]["6_workspace_slug"] = workspace.slug
            result["steps"]["6_workspace_status"] = workspace.status

            # Step 7: Try creating TokenScope enum
            try:
                scope = TokenScope(token_record.scope)
                result["steps"]["7_scope_enum_created"] = True
                result["steps"]["7_scope_value"] = scope.value
            except Exception as e:
                result["steps"]["7_scope_enum_created"] = False
                result["steps"]["7_scope_error"] = str(e)
                result["error"] = f"Failed to create TokenScope enum: {e}"
                return result

            # Step 8: Try full service verification
            try:
                from services.purl_token_service import PURLTokenService
                service = PURLTokenService(db)
                context_data = service.verify_token(token)
                result["steps"]["8_service_verify"] = context_data is not None
                if context_data:
                    result["steps"]["8_context_keys"] = list(context_data.keys())
                else:
                    result["error"] = "Service verification returned None"
            except Exception as e:
                result["steps"]["8_service_verify"] = False
                result["steps"]["8_service_error"] = str(e)
                result["steps"]["8_service_traceback"] = traceback.format_exc()
                result["error"] = f"Service verification failed: {e}"
                return result

            result["success"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            result["traceback"] = traceback.format_exc()
            return result


    @app.get("/api/v1/debug/appointments-status", tags=["Debug"])
    async def debug_appointments_status(db: Session = Depends(get_db)):
        """Debug endpoint to check recent appointments and reminder status"""
        result = {
            "scheduler_appointments": [],
            "legacy_appointments": [],
            "reminders_sent": [],
            "summary": {}
        }

        try:
            # Check smart scheduler appointments
            try:
                smart_appts = db.execute(text("""
                    SELECT
                        sa.id, sa.title, sa.scheduled_start, sa.status,
                        sa.attendee_name, sa.attendee_email, sa.attendee_phone,
                        sa.video_link, sa.created_at,
                        u.full_name as lo_name
                    FROM scheduler_appointments sa
                    LEFT JOIN users u ON u.id = sa.assigned_user_id
                    ORDER BY sa.created_at DESC
                    LIMIT 5
                """)).fetchall()

                for row in smart_appts:
                    result["scheduler_appointments"].append({
                        "id": row[0],
                        "title": row[1],
                        "scheduled_start": row[2].isoformat() if row[2] else None,
                        "status": row[3],
                        "attendee_name": row[4],
                        "attendee_email": row[5],
                        "attendee_phone": row[6],
                        "video_link": row[7],
                        "created_at": row[8].isoformat() if row[8] else None,
                        "lo_name": row[9] or ''
                    })
            except Exception as e:
                result["scheduler_appointments_error"] = str(e)

            # Check legacy appointments (may not exist in all deployments)
            try:
                # First check if appointments table exists
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'appointments'
                    )
                """)).scalar()

                if table_check:
                    legacy_appts = db.execute(text("""
                        SELECT
                            a.id, a.appointment_type, a.scheduled_at, a.status,
                            a.reminder_sent, a.meeting_link,
                            l.name as lead_name, l.email as lead_email, l.phone as lead_phone,
                            u.full_name as lo_name
                        FROM appointments a
                        LEFT JOIN leads l ON l.id = a.lead_id
                        LEFT JOIN users u ON u.id = a.assigned_to
                        ORDER BY a.created_at DESC
                        LIMIT 5
                    """)).fetchall()

                    for row in legacy_appts:
                        result["legacy_appointments"].append({
                            "id": row[0],
                            "type": row[1],
                            "scheduled_at": row[2].isoformat() if row[2] else None,
                            "status": row[3],
                            "reminder_sent": row[4],
                            "meeting_link": row[5],
                            "lead_name": row[6],
                            "lead_email": row[7],
                            "lead_phone": row[8],
                            "lo_name": row[9] or ''
                        })
                else:
                    result["legacy_appointments_note"] = "appointments table does not exist"
            except Exception as e:
                result["legacy_appointments_error"] = str(e)

            # Check chat widget appointments (scheduled_appointments table)
            result["chat_widget_appointments"] = []
            try:
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'scheduled_appointments'
                    )
                """)).scalar()

                if table_check:
                    chat_appts = db.execute(text("""
                        SELECT
                            sa.id, sa.appointment_id, sa.appointment_type, sa.start_time, sa.status,
                            sa.contact_name, sa.contact_email, sa.contact_phone,
                            sa.lo_name, sa.created_at
                        FROM scheduled_appointments sa
                        WHERE sa.status = 'scheduled'
                        ORDER BY sa.created_at DESC
                        LIMIT 10
                    """)).fetchall()

                    for row in chat_appts:
                        result["chat_widget_appointments"].append({
                            "id": row[0],
                            "appointment_id": row[1],
                            "type": row[2],
                            "start_time": row[3].isoformat() if row[3] else None,
                            "status": row[4],
                            "contact_name": row[5],
                            "contact_email": row[6],
                            "contact_phone": row[7],
                            "lo_name": row[8] or '',
                            "created_at": row[9].isoformat() if row[9] else None
                        })
                else:
                    result["chat_widget_appointments_note"] = "scheduled_appointments table does not exist"
            except Exception as e:
                result["chat_widget_appointments_error"] = str(e)

            # Check sent reminders
            try:
                reminders = db.execute(text("""
                    SELECT appointment_id, channel, hours_before, status, sent_at
                    FROM scheduler_reminders
                    ORDER BY created_at DESC
                    LIMIT 10
                """)).fetchall()

                for row in reminders:
                    result["reminders_sent"].append({
                        "appointment_id": row[0],
                        "channel": row[1],
                        "hours_before": row[2],
                        "status": row[3],
                        "sent_at": row[4].isoformat() if row[4] else None
                    })
            except Exception as e:
                result["reminders_error"] = str(e)

            # Check chat widget reminders
            result["chat_widget_reminders"] = []
            try:
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'chat_appointment_reminders'
                    )
                """)).scalar()

                if table_check:
                    chat_reminders = db.execute(text("""
                        SELECT appointment_id, channel, hours_before, status, sent_at
                        FROM chat_appointment_reminders
                        ORDER BY created_at DESC
                        LIMIT 10
                    """)).fetchall()

                    for row in chat_reminders:
                        result["chat_widget_reminders"].append({
                            "appointment_id": row[0],
                            "channel": row[1],
                            "hours_before": row[2],
                            "status": row[3],
                            "sent_at": row[4].isoformat() if row[4] else None
                        })
            except Exception as e:
                result["chat_widget_reminders_error"] = str(e)

            result["summary"] = {
                "scheduler_appointments_count": len(result["scheduler_appointments"]),
                "legacy_appointments_count": len(result["legacy_appointments"]),
                "chat_widget_appointments_count": len(result["chat_widget_appointments"]),
                "reminders_sent_count": len(result["reminders_sent"]),
                "chat_widget_reminders_count": len(result["chat_widget_reminders"])
            }

            return result

        except Exception as e:
            return {"error": str(e)}


    @app.post("/api/v1/debug/create-test-appointment", tags=["Debug"])
    async def create_test_appointment(
        attendee_email: str = "tloss@me.com",
        attendee_phone: str = "8438345251",
        attendee_name: str = "Test Reminder",
        hours_from_now: int = 24,
        db: Session = Depends(get_db)
    ):
        """Create a test appointment for notification testing"""
        from datetime import datetime, timedelta

        scheduled_start = datetime.utcnow() + timedelta(hours=hours_from_now)
        scheduled_end = scheduled_start + timedelta(minutes=30)

        try:
            # Get first user to assign
            user = db.execute(text("SELECT id, full_name FROM users LIMIT 1")).fetchone()
            user_id = user[0] if user else None
            user_name = user[1] if user else "Test LO"

            # Insert appointment (use uppercase enum values)
            result = db.execute(text("""
                INSERT INTO scheduler_appointments
                (title, scheduled_start, scheduled_end, duration_minutes, status,
                 attendee_name, attendee_email, attendee_phone, assigned_user_id,
                 meeting_type, timezone, created_at, updated_at)
                VALUES
                (:title, :start, :end, 30, 'BOOKED',
                 :name, :email, :phone, :user_id,
                 'DISCOVERY_CALL', 'America/New_York', NOW(), NOW())
                RETURNING id
            """), {
                "title": f"Test Call with {attendee_name}",
                "start": scheduled_start,
                "end": scheduled_end,
                "name": attendee_name,
                "email": attendee_email,
                "phone": attendee_phone,
                "user_id": user_id
            })

            appointment_id = result.fetchone()[0]
            db.commit()

            return {
                "success": True,
                "appointment_id": appointment_id,
                "scheduled_start": scheduled_start.isoformat(),
                "scheduled_end": scheduled_end.isoformat(),
                "attendee_email": attendee_email,
                "attendee_phone": attendee_phone,
                "assigned_to": user_name,
                "reminder_schedule": {
                    "24h_reminder": (scheduled_start - timedelta(hours=24)).isoformat() if hours_from_now > 24 else "Already passed",
                    "1h_reminder": (scheduled_start - timedelta(hours=1)).isoformat()
                },
                "note": f"Appointment created {hours_from_now} hours from now. Reminders will be sent automatically."
            }

        except Exception as e:
            db.rollback()
            return {"error": str(e)}


    @app.post("/api/v1/debug/send-test-sms", tags=["Debug"])
    async def send_test_sms(
        phone: str = "8438345251",
        message: str = "Test reminder from Perennia AI - your appointment is coming up!"
    ):
        """Send a test SMS to verify Twilio is working"""
        import os
        try:
            from twilio.rest import Client

            account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            auth_token = os.getenv("TWILIO_AUTH_TOKEN")
            from_number = os.getenv("TWILIO_PHONE_NUMBER")

            if not all([account_sid, auth_token, from_number]):
                return {
                    "success": False,
                    "error": "Twilio not configured",
                    "config": {
                        "account_sid": bool(account_sid),
                        "auth_token": bool(auth_token),
                        "from_number": from_number
                    }
                }

            # Format phone number
            if not phone.startswith("+"):
                phone = "+1" + phone.replace("-", "").replace(" ", "")

            client = Client(account_sid, auth_token)
            sms = client.messages.create(
                body=message,
                from_=from_number,
                to=phone
            )

            return {
                "success": True,
                "message_sid": sms.sid,
                "to": phone,
                "from": from_number,
                "status": sms.status
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


    @app.post("/api/v1/debug/trigger-appointment-reminders", tags=["Debug"])
    async def trigger_appointment_reminders():
        """Manually trigger the appointment reminder job"""
        try:
            from services.scheduler_service import scheduler_service
            scheduler_service.send_appointment_reminders()
            return {"success": True, "message": "Reminder job executed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


    # Perennia Docs AI Routes
    perennia_docs_error = None
    try:
        from routes.perennia_docs_routes import router as perennia_docs_router, set_dependencies as set_perennia_docs_deps
        from models.perennia_docs import create_perennia_docs_models

        # Create Perennia Docs models
        perennia_docs_models = create_perennia_docs_models(Base)

        # Set dependencies
        set_perennia_docs_deps(get_db, get_current_user, User, perennia_docs_models)

        app.include_router(perennia_docs_router, tags=["Perennia Docs AI"])
        logger.info("✅ Perennia Docs AI routes loaded")
    except Exception as e:
        perennia_docs_error = str(e)
        import traceback
        perennia_docs_error = traceback.format_exc()
        logger.warning(f"⚠️ Perennia Docs AI routes not loaded: {e}")

    @app.get("/api/v1/debug/perennia-docs-status")
    async def debug_perennia_docs_status():
        """Debug endpoint to check Perennia Docs AI routes loading status"""
        return {
            "perennia_docs_loaded": perennia_docs_error is None,
            "error": perennia_docs_error
        }

    # E-Signature Routes - initialized
    esign_error = None
    try:
        from routes.esign_routes import router as esign_router, set_dependencies as set_esign_deps
        from models.esign_models import create_esign_models

        # Create E-Sign models
        esign_models = create_esign_models(Base)

        # Set dependencies
        set_esign_deps(get_db, get_current_user, User, esign_models)

        app.include_router(esign_router, tags=["E-Signature"])
        logger.info("✅ E-Signature routes loaded")
    except Exception as e:
        esign_error = str(e)
        import traceback
        esign_error = traceback.format_exc()
        logger.warning(f"⚠️ E-Signature routes not loaded: {e}")

    @app.get("/api/v1/debug/esign-status")
    async def debug_esign_status():
        """Debug endpoint to check E-Signature routes loading status"""
        return {
            "esign_loaded": esign_error is None,
            "error": esign_error
        }

    # Portal AI Assistant Routes
    portal_ai_assistant_error = None
    try:
        from routes.portal_ai_assistant_routes import router as portal_ai_assistant_router, set_dependencies as set_portal_ai_deps

        # Set dependencies
        set_portal_ai_deps(get_db, get_current_user)

        app.include_router(portal_ai_assistant_router, tags=["Portal AI Assistant"])
        logger.info("✅ Portal AI Assistant routes loaded")
    except Exception as e:
        portal_ai_assistant_error = str(e)
        import traceback
        portal_ai_assistant_error = traceback.format_exc()
        logger.warning(f"⚠️ Portal AI Assistant routes not loaded: {e}")

    # PURL-Perennia Integration Routes
    purl_integration_error = None
    try:
        from routes.purl_perennia_integration_routes import router as purl_integration_router, set_dependencies as set_purl_integration_deps

        # Set dependencies
        set_purl_integration_deps(get_db, get_current_user)

        app.include_router(purl_integration_router, tags=["PURL Integration"])
        logger.info("✅ PURL-Perennia Integration routes loaded")
    except Exception as e:
        purl_integration_error = str(e)
        import traceback
        purl_integration_error = traceback.format_exc()
        logger.warning(f"⚠️ PURL-Perennia Integration routes not loaded: {e}")

    @app.get("/api/v1/debug/portal-integration-status")
    async def debug_portal_integration_status():
        """Debug endpoint to check Portal AI and PURL Integration routes loading status"""
        return {
            "portal_ai_assistant_loaded": portal_ai_assistant_error is None,
            "portal_ai_assistant_error": portal_ai_assistant_error,
            "purl_integration_loaded": purl_integration_error is None,
            "purl_integration_error": purl_integration_error
        }

    # Portal Document Routes (presigned URLs, upload, preview)
    portal_document_error = None
    try:
        from routes.portal_document_routes import router as portal_document_router, set_dependencies as set_portal_doc_deps

        # Set dependencies
        set_portal_doc_deps(get_db)

        app.include_router(portal_document_router, tags=["Portal Documents"])
        logger.info("✅ Portal Document routes loaded")
    except Exception as e:
        portal_document_error = str(e)
        import traceback
        portal_document_error = traceback.format_exc()
        logger.warning(f"⚠️ Portal Document routes not loaded: {e}")

    # NOTE: Smart Documents routes already loaded earlier in main.py (line ~19873)
    # Duplicate registration was removed to fix FastAPI duplicate operation_id warnings

    # Portal Authentication Routes (magic links, sessions)
    portal_auth_error = None
    try:
        from routes.portal_auth_routes import router as portal_auth_router, set_dependencies as set_portal_auth_deps

        # Set dependencies
        set_portal_auth_deps(get_db)

        app.include_router(portal_auth_router, tags=["Portal Authentication"])
        logger.info("✅ Portal Authentication routes loaded")
    except Exception as e:
        portal_auth_error = str(e)
        import traceback
        portal_auth_error = traceback.format_exc()
        logger.warning(f"⚠️ Portal Authentication routes not loaded: {e}")

    # Include Perennia Portal routes (Client Portal with lifecycle, milestones, close-on-time)
    perennia_portal_error = None
    try:
        from portal_routes import router as perennia_portal_router
        app.include_router(perennia_portal_router, tags=["Perennia Portal"])
        logger.info("✅ Perennia Portal routes loaded")
    except Exception as e:
        perennia_portal_error = str(e)
        import traceback
        perennia_portal_error = traceback.format_exc()
        logger.warning(f"⚠️ Perennia Portal routes not loaded: {e}")

    # Presentation Engine routes (equity scenarios and quote requests)
    presentation_error = None
    try:
        from presentation_routes import router as presentation_router
        app.include_router(presentation_router, tags=["Presentation Engine"])
        logger.info("✅ Presentation Engine routes loaded")
    except Exception as e:
        presentation_error = str(e)
        import traceback
        presentation_error = traceback.format_exc()
        logger.warning(f"⚠️ Presentation Engine routes not loaded: {e}")

    # CRM Webhooks routes (real-time CRM integration)
    crm_webhooks_error = None
    try:
        from routes.crm_webhooks import router as crm_webhooks_router
        app.include_router(crm_webhooks_router, tags=["CRM Webhooks"])
        logger.info("✅ CRM Webhooks routes loaded")
    except Exception as e:
        crm_webhooks_error = str(e)
        import traceback
        crm_webhooks_error = traceback.format_exc()
        logger.warning(f"⚠️ CRM Webhooks routes not loaded: {e}")

    # Portal WebSocket routes (real-time updates)
    portal_websocket_error = None
    try:
        from services.portal_websocket_service import router as portal_websocket_router
        app.include_router(portal_websocket_router, tags=["Portal WebSocket"])
        logger.info("✅ Portal WebSocket routes loaded")
    except Exception as e:
        portal_websocket_error = str(e)
        import traceback
        portal_websocket_error = traceback.format_exc()
        logger.warning(f"⚠️ Portal WebSocket routes not loaded: {e}")

    # Email Training routes (for reviewing and correcting AI responses)
    email_training_error = None
    try:
        from routes.email_training_routes import router as email_training_router
        app.include_router(email_training_router, prefix="/api/v1/email-training", tags=["Email Training"])
        logger.info("✅ Email Training routes loaded")
    except Exception as e:
        email_training_error = str(e)
        import traceback
        email_training_error = traceback.format_exc()
        logger.warning(f"⚠️ Email Training routes not loaded: {e}")

    # AI Email Settings routes (configure AI assistant email identity)
    ai_email_settings_error = None
    try:
        from routes.ai_email_settings_routes import router as ai_email_settings_router, AIEmailSettings
        app.include_router(ai_email_settings_router, tags=["AI Email Settings"])
        # Create table if not exists
        AIEmailSettings.__table__.create(bind=engine, checkfirst=True)
        logger.info("✅ AI Email Settings routes loaded")
    except Exception as e:
        ai_email_settings_error = str(e)
        import traceback
        ai_email_settings_error = traceback.format_exc()
        logger.warning(f"⚠️ AI Email Settings routes not loaded: {e}")

    # Pre-Approval Letter Settings routes (configure pre-approval letter content)
    pre_approval_letter_settings_error = None
    try:
        from routes.pre_approval_letter_settings_routes import router as pre_approval_letter_settings_router, PreApprovalLetterSettings
        app.include_router(pre_approval_letter_settings_router, tags=["Pre-Approval Letter Settings"])
        # Create table if not exists
        PreApprovalLetterSettings.__table__.create(bind=engine, checkfirst=True)
        logger.info("✅ Pre-Approval Letter Settings routes loaded")
    except Exception as e:
        pre_approval_letter_settings_error = str(e)
        import traceback
        pre_approval_letter_settings_error = traceback.format_exc()
        logger.warning(f"⚠️ Pre-Approval Letter Settings routes not loaded: {e}")

    # AI Outreach routes (send AI-powered emails/SMS to leads)
    ai_outreach_error = None
    try:
        from routes.ai_outreach_routes import router as ai_outreach_router, create_outreach_table
        app.include_router(ai_outreach_router, tags=["AI Outreach"])
        # Create outreach log table
        create_outreach_table(engine)
        logger.info("✅ AI Outreach routes loaded")
    except Exception as e:
        ai_outreach_error = str(e)
        import traceback
        ai_outreach_error = traceback.format_exc()
        logger.warning(f"⚠️ AI Outreach routes not loaded: {e}")

    # Automated Outreach routes (drip campaigns + triggers)
    automated_outreach_error = None
    try:
        from routes.automated_outreach_routes import router as automated_outreach_router, create_automated_outreach_tables
        app.include_router(automated_outreach_router, tags=["Automated Outreach"])
        create_automated_outreach_tables(engine)
        logger.info("✅ Automated Outreach routes loaded")
    except Exception as e:
        automated_outreach_error = str(e)
        import traceback
        automated_outreach_error = traceback.format_exc()
        logger.warning(f"⚠️ Automated Outreach routes not loaded: {e}")

    # Intake Engine routes (conversational loan intake)
    intake_engine_error = None
    try:
        from intake_engine.api.routes import router as intake_engine_router
        app.include_router(intake_engine_router, tags=["Intake Engine"])
        logger.info("✅ Intake Engine routes loaded")
    except Exception as e:
        intake_engine_error = str(e)
        import traceback
        intake_engine_error = traceback.format_exc()
        logger.warning(f"⚠️ Intake Engine routes not loaded: {e}")

    # Document Visibility routes
    try:
        from routes.document_visibility_routes import router as document_visibility_router, set_dependencies as set_doc_visibility_deps
        set_doc_visibility_deps(get_db)
        app.include_router(document_visibility_router, tags=["Document Visibility"])
        logger.info("✅ Document Visibility routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Document Visibility routes not loaded: {e}")

    # Support Tickets routes (IT ticket management for platform admin)
    try:
        from routes.support_tickets_routes import router as support_tickets_router, set_dependencies as set_support_deps
        set_support_deps(get_current_user)
        app.include_router(support_tickets_router, tags=["Support Tickets"])
        logger.info("✅ Support Tickets routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Support Tickets routes not loaded: {e}")

    @app.get("/api/v1/debug/portal-services-status")
    async def debug_portal_services_status():
        """Debug endpoint to check all portal-related routes loading status"""
        return {
            "portal_ai_assistant": {
                "loaded": portal_ai_assistant_error is None,
                "error": portal_ai_assistant_error
            },
            "purl_integration": {
                "loaded": purl_integration_error is None,
                "error": purl_integration_error
            },
            "portal_documents": {
                "loaded": portal_document_error is None,
                "error": portal_document_error
            },
            "portal_auth": {
                "loaded": portal_auth_error is None,
                "error": portal_auth_error
            },
            "perennia_portal": {
                "loaded": perennia_portal_error is None,
                "error": perennia_portal_error
            }
        }

    @app.get("/api/v1/debug/intake-engine-status")
    async def debug_intake_engine_status():
        """Debug endpoint to check intake engine loading status"""
        status = {
            "loaded": intake_engine_error is None,
            "error": intake_engine_error
        }

        # Try to get engine stats if loaded
        if intake_engine_error is None:
            try:
                from intake_engine.api.routes import get_engine
                engine = get_engine()
                status["engine_stats"] = {
                    "questions_loaded": len(engine.questions),
                    "sections": list(engine.section_order),
                }
            except Exception as e:
                status["engine_init_error"] = str(e)

        return status

    # Debug endpoint for tools registry loading
    @app.get("/api/v1/debug/tools-registry-status")
    async def debug_tools_registry_status():
        """Debug endpoint to check tools registry loading status"""
        return {
            "tools_router_loaded": tools_router_error is None,
            "error": tools_router_error
        }


    # Cache stats monitoring endpoint
    @app.get("/api/v1/debug/cache-stats", tags=["Debug"])
    async def debug_cache_stats():
        """
        Debug endpoint to monitor Redis LLM cache statistics.

        Returns cache hit/miss rates, estimated savings, and Redis connection status.
        Used to verify caching is working and measure cost savings.
        """
        try:
            from services.llm_cache_service import llm_cache

            if llm_cache and llm_cache._enabled:
                stats = llm_cache.get_stats()
                return {
                    "cache_enabled": True,
                    "redis_connected": True,
                    "stats": {
                        "hits": stats.get("hits", 0),
                        "misses": stats.get("misses", 0),
                        "errors": stats.get("errors", 0),
                        "hit_rate_percent": stats.get("hit_rate", 0),
                        "estimated_savings_usd": stats.get("estimated_savings", 0),
                    },
                    "message": "Cache is operational"
                }
            else:
                return {
                    "cache_enabled": False,
                    "redis_connected": False,
                    "stats": None,
                    "message": "LLM cache service not enabled or Redis not connected"
                }
        except ImportError:
            return {
                "cache_enabled": False,
                "redis_connected": False,
                "stats": None,
                "message": "LLM cache service not available"
            }
        except Exception as e:
            return {
                "cache_enabled": False,
                "redis_connected": False,
                "stats": None,
                "error": str(e),
                "message": f"Error checking cache: {str(e)}"
            }


    # DataDog monitoring status endpoint
    @app.get("/api/v1/debug/datadog-status", tags=["Debug"])
    async def debug_datadog_status():
        """
        Debug endpoint to check DataDog monitoring status.

        Returns APM tracing status, metrics collection status, and configuration.
        """
        try:
            from datadog_monitoring import (
                DD_SERVICE, DD_ENV, DD_TRACE_ENABLED,
                _tracer, _statsd, _initialized
            )

            return {
                "datadog_enabled": _initialized,
                "apm_tracing": {
                    "enabled": DD_TRACE_ENABLED,
                    "initialized": _tracer is not None,
                    "service": DD_SERVICE,
                    "environment": DD_ENV
                },
                "metrics": {
                    "statsd_initialized": _statsd is not None,
                    "prefix": "mortgage_crm"
                },
                "config": {
                    "DD_SERVICE": DD_SERVICE,
                    "DD_ENV": DD_ENV,
                    "DD_TRACE_ENABLED": DD_TRACE_ENABLED
                },
                "message": "DataDog monitoring is operational" if _initialized else "DataDog not fully initialized"
            }
        except ImportError:
            return {
                "datadog_enabled": False,
                "message": "DataDog monitoring module not available"
            }
        except Exception as e:
            return {
                "datadog_enabled": False,
                "error": str(e),
                "message": f"Error checking DataDog status: {str(e)}"
            }


    @app.get("/api/v1/debug/datadog-dashboard-config", tags=["Debug"])
    async def get_datadog_dashboard_config():
        """
        Get DataDog dashboard configuration JSON.

        Returns the dashboard configuration that can be imported into DataDog
        using their Dashboard API.
        """
        try:
            from datadog_monitoring import get_dashboard_config
            return get_dashboard_config()
        except ImportError:
            return {"error": "DataDog monitoring module not available"}
        except Exception as e:
            return {"error": str(e)}


    @app.post("/api/v1/debug/datadog-test-metrics", tags=["Debug"])
    async def test_datadog_metrics(current_user: User = Depends(get_current_user)):
        """
        Send test metrics to DataDog.

        Useful for verifying the DataDog agent connection and metrics pipeline.
        """
        try:
            from datadog_monitoring import metrics, business_metrics

            # Send test metrics
            metrics.increment("test.counter", tags=["source:api_test"])
            metrics.gauge("test.gauge", 42.0, tags=["source:api_test"])
            metrics.histogram("test.histogram", 100.5, tags=["source:api_test"])

            # Send test business metric
            business_metrics.metrics.event(
                title="DataDog Test Event",
                text=f"Test event triggered by user {current_user.email}",
                alert_type="info",
                tags=["source:api_test", f"user:{current_user.id}"]
            )

            return {
                "success": True,
                "message": "Test metrics sent to DataDog",
                "metrics_sent": ["test.counter", "test.gauge", "test.histogram"],
                "event_sent": True
            }
        except ImportError:
            return {"success": False, "error": "DataDog monitoring module not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}


    @app.get("/api/v1/debug/cdn-status", tags=["Debug"])
    async def get_cdn_status():
        """
        Get CloudFront CDN status and configuration.

        Returns information about CDN setup, distribution status,
        and whether CDN URLs are being used.
        """
        try:
            from services.cdn_service import get_cdn_service
            cdn = get_cdn_service()
            status = cdn.get_distribution_status()
            return {
                "cdn_enabled": cdn.enabled,
                "distribution_id": cdn.distribution_id,
                "domain_name": cdn.domain_name,
                "s3_bucket": cdn.s3_bucket,
                "signed_urls_available": bool(cdn._private_key and cdn.key_pair_id),
                "distribution_status": status
            }
        except ImportError:
            return {
                "cdn_enabled": False,
                "error": "CDN service module not available",
                "message": "Install cdn_service.py and configure CloudFront"
            }
        except Exception as e:
            return {
                "cdn_enabled": False,
                "error": str(e),
                "message": f"Error checking CDN status: {str(e)}"
            }


    @app.post("/api/v1/debug/cdn-invalidate", tags=["Debug"])
    async def invalidate_cdn_cache(
        paths: list[str] = Body(..., description="List of paths to invalidate"),
        current_user: User = Depends(get_current_user)
    ):
        """
        Invalidate CloudFront cache for specified paths.

        Requires admin or appropriate permissions.
        """
        try:
            from services.cdn_service import get_cdn_service
            cdn = get_cdn_service()

            if not cdn.enabled:
                return {"success": False, "error": "CDN not configured"}

            result = cdn.invalidate_cache(paths)
            return result
        except ImportError:
            return {"success": False, "error": "CDN service module not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}


    @app.post("/api/v1/debug/add-missing-roles", tags=["Debug"])
    async def add_missing_employee_roles(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Add missing employee roles to the onboarding_roles table.

        Adds: Admin, Site Admin, Executive Management, Management, Operations Manager,
              Branch Manager, Underwriter, Closer, Funder
        """
        if current_user.role != 'admin' and current_user.permission_role != 'admin':
            raise HTTPException(status_code=403, detail="Admin access required")

        try:
            from sqlalchemy import text as sql_text
            from datetime import datetime, timezone

            MISSING_ROLES = [
                {"name": "Admin", "description": "System administrator with full access"},
                {"name": "Site Admin", "description": "Site-level administrator"},
                {"name": "Executive Management", "description": "Executive management team"},
                {"name": "Management", "description": "Management role"},
                {"name": "Operations Manager", "description": "Operations manager overseeing daily operations"},
                {"name": "Branch Manager", "description": "Branch manager overseeing branch operations"},
                {"name": "Underwriter", "description": "Loan underwriter"},
                {"name": "Closer", "description": "Loan closer handling closing process"},
                {"name": "Funder", "description": "Loan funder handling funding process"},
            ]

            added = []
            skipped = []

            for role in MISSING_ROLES:
                # Check if role exists
                existing = db.execute(
                    sql_text("SELECT id FROM onboarding_roles WHERE name = :name"),
                    {"name": role["name"]}
                ).fetchone()

                if existing:
                    skipped.append(role["name"])
                else:
                    db.execute(
                        sql_text("""
                            INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
                            VALUES (:name, :description, true, :now, :now)
                        """),
                        {
                            "name": role["name"],
                            "description": role["description"],
                            "now": datetime.now(timezone.utc)
                        }
                    )
                    added.append(role["name"])

            db.commit()

            # Get all roles for display
            all_roles = db.execute(
                sql_text("SELECT id, name, is_active FROM onboarding_roles WHERE is_active = true ORDER BY name")
            ).fetchall()

            return {
                "success": True,
                "added": added,
                "skipped": skipped,
                "message": f"Added {len(added)} roles, skipped {len(skipped)} existing roles",
                "all_roles": [{"id": r[0], "name": r[1]} for r in all_roles]
            }

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}


    # Extracted to routes/db_migration_routes.py
    # (add-purl-system, add-email-monitor, add-morning-checkin, add-rate-sheets)

    # ============================================================================
    # API KEY HELPER FUNCTIONS
    # ============================================================================

    def generate_api_key() -> str:
        """Generate a secure API key with prefix 'sk_'"""
        import secrets
        random_part = secrets.token_urlsafe(32)
        return f"sk_{random_part}"

    # ============================================================================
    # AI HELPER FUNCTIONS
    # ============================================================================

    def generate_ai_insights(loan: Loan) -> str:
        """Generate AI insights for a loan (simple rule-based for now)"""
        insights = []

        if loan.days_in_stage and loan.days_in_stage > 10:
            stage_name = loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage) if loan.stage else 'unknown'
            insights.append(f"⚠️ Loan has been in {stage_name} stage for {loan.days_in_stage} days")

        if loan.closing_date:
            try:
                # Handle both date and datetime objects
                if hasattr(loan.closing_date, 'tzinfo'):
                    closing_dt = loan.closing_date if loan.closing_date.tzinfo else loan.closing_date.replace(tzinfo=timezone.utc)
                else:
                    # It's a date object, convert to datetime
                    closing_dt = datetime.combine(loan.closing_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                if (closing_dt - datetime.now(timezone.utc)).days < 7:
                    insights.append("🔥 Closing date approaching - prioritize tasks")
            except Exception:
                pass  # Skip closing date insight if there's any issue

        if loan.rate and loan.rate > 7.0:
            insights.append("💰 Higher rate loan - consider rate lock strategies")

        if not insights:
            insights.append("✅ Loan progressing normally")

        return " | ".join(insights)

    def calculate_lead_score(lead: Lead) -> int:
        """Calculate AI score for a lead"""
        score = 50

        if lead.credit_score:
            if lead.credit_score >= 740:
                score += 30
            elif lead.credit_score >= 680:
                score += 20
            elif lead.credit_score >= 620:
                score += 10
            else:
                score -= 10

        if lead.preapproval_amount and lead.preapproval_amount > 0:
            score += 15

        if lead.email:
            score += 5

        if lead.phone:
            score += 5

        if lead.debt_to_income:
            if lead.debt_to_income < 0.36:
                score += 10
            elif lead.debt_to_income > 0.50:
                score -= 15

        return min(max(score, 0), 100)

    # ============================================================================
    # DATA RECONCILIATION ENGINE (DRE) - AI EXTRACTION
    # ============================================================================

    def classify_email_content(content: str, subject: str) -> Dict[str, Any]:
        """Use AI to classify email content and determine category"""

        if not openai_client:
            logger.warning("OpenAI client not initialized - using fallback classification")
            # Fallback: Use keyword matching to classify
            content_lower = content.lower()
            subject_lower = subject.lower()

            if any(word in subject_lower or word in content_lower for word in ['loan', 'mortgage', 'borrower', 'closing', 'rate lock']):
                return {"category": "loan_update", "subcategory": "general", "confidence": 0.5}
            else:
                return {"category": "loan_update", "subcategory": "general", "confidence": 0.3}

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an email classification expert for mortgage loan processing.

    FIRST: Determine if this email is related to the mortgage/lending business.
    If the email is about ANY of these, classify as "unrelated":
    - Software updates, tech newsletters, product announcements
    - Marketing/promotional emails not about mortgage services
    - Personal emails, social media notifications
    - General news, politics, entertainment
    - Subscriptions, newsletters unrelated to mortgage industry
    - Internal company announcements not about loans

    ONLY classify as mortgage-related if the email contains:
    - Loan numbers, borrower names, property addresses
    - Loan status updates, milestone changes
    - Rate locks, appraisals, title, insurance
    - Closing documents, CDs, funding
    - Lead inquiries about getting a mortgage

    Categories (ONLY use if mortgage-related):
    - lead_update: New lead information or lead status changes
    - loan_update: Active loan milestone updates
    - rate_lock: Rate lock confirmations or expirations
    - appraisal: Appraisal scheduling or results
    - title: Title work, clear to close
    - insurance: HOI binders, insurance updates
    - closing: Closing date/time, CD delivery
    - document: Document receipt confirmations
    - portfolio: Servicing, escrow, tax updates
    - unrelated: NOT mortgage-related (use this liberally for anything that's not clearly about a mortgage transaction)

    Return JSON: {"category": "...", "subcategory": "...", "confidence": 0.0-1.0}"""
                    },
                    {
                        "role": "user",
                        "content": f"Subject: {subject}\n\nContent: {content[:1000]}"
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            logger.error(f"Email classification error: {e}")
            # Return loan_update with low confidence so email still gets processed
            return {"category": "loan_update", "subcategory": "error", "confidence": 0.3}

    def extract_loan_fields(content: str, category: str) -> Dict[str, Dict[str, Any]]:
        """Extract structured loan fields from email content"""

        if not openai_client:
            logger.warning("OpenAI client not initialized - cannot extract loan fields, returning empty")
            return {}

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""Extract mortgage loan fields from this {category} email.

    **CRITICAL - BORROWER NAME EXTRACTION:**
    You MUST extract the borrower name. Look for these patterns:
    1. "Borrower:  LastName" or "Borrower: FirstName LastName"
    2. "Borrower(s): Name1 and Name2"
    3. Subject line patterns like "Loan # XXX - LastName -" or "[LastName-LoanNumber]"
    4. Email signatures or references to "the borrower"
    If you see text like "Borrower:  Spink" - extract "Spink" as borrower_name!

    Extract any present fields:
    - loan_number: string (look for patterns like RCA#, Loan #, file #)
    - borrower_name: string (**REQUIRED** - extract from Borrower: field, subject line, or any reference)
    - coborrower_name: string (if present)
    - property_address: string
    - property_city: string
    - property_state: string
    - property_zip: string
    - loan_amount: float
    - program: string (e.g., "FHA 30 Yr Fixed", "VA 30 Yr Fixed", "Conv 30 Yr Fixed")
    - term: integer (loan term in years, e.g., 30)
    - rate: float (as decimal, e.g., 6.125)
    - rate_lock_date: ISO date
    - lock_expiration: ISO date
    - appraisal_ordered_date: ISO date
    - appraisal_scheduled_date: ISO date
    - appraisal_completed_date: ISO date
    - appraisal_value: float
    - closing_scheduled_date: ISO date
    - closing_date: ISO datetime
    - milestone: string (e.g., "RateLocked", "AppraisalOrdered", "ClearToClose", "InspectionCompleted")
    - documents_received: list of strings
    - lender: string
    - loan_officer_name: string
    - loan_officer_email: string
    - realtor_name: string
    - title_company: string

    For each field found, return:
    {{"field_name": {{"value": actual_value, "confidence": 0.0-1.0}}}}

    Return JSON object. Only include fields you found. Use null for missing."""
                    },
                    {
                        "role": "user",
                        "content": content[:3000]  # Increased to capture more content
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )

            fields = json.loads(response.choices[0].message.content)
            logger.info(f"Extracted fields: {list(fields.keys())}")
            return fields
        except Exception as e:
            logger.error(f"Field extraction error: {e}")
            return {}

    def extract_borrower_from_subject(subject: str) -> Optional[str]:
        """Extract borrower name from email subject line as fallback"""
        import re
        if not subject:
            return None

        # Pattern 1: "FirstName LastName RCA0000006026" - Full name before loan number
        # e.g., "Emma Spink RCA0000006026 - Accepted Electronic Consent"
        match = re.search(r'^([A-Za-z]+(?:\s+[A-Za-z]+)+)\s+[A-Z]{2,3}\d{7,}', subject)
        if match:
            return match.group(1).strip()

        # Pattern 2: "Closing Docs Downloaded, FirstName LastName, RCA..."
        # e.g., "Closing Docs Downloaded, Kelly M Capps, RCA0000010910"
        match = re.search(r',\s*([A-Za-z]+(?:\s+[A-Za-z]+)+)\s*,\s*[A-Z]{2,3}\d+', subject)
        if match:
            return match.group(1).strip()

        # Pattern 3: "LastName - RCA0000011023" format
        # e.g., "Davis - RCA0000011023 Signing Completed"
        match = re.search(r'([A-Za-z]+)\s*-\s*[A-Z]{2,3}\d{7,}', subject)
        if match:
            return match.group(1).strip()

        # Pattern 4: "Loan # XXX - LastName -" or "Loan # XXX - LastName - Status"
        match = re.search(r'Loan\s*#?\s*\w+\s*-\s*([A-Za-z]+)\s*-', subject, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 5: "[LastName-LoanNumber]" like "[Spink-RCA0000006026]"
        match = re.search(r'\[([A-Za-z]+)-\w+\]', subject)
        if match:
            return match.group(1).strip()

        # Pattern 6: "Disclosures for FirstName LastName, RCA..."
        # e.g., "CMG Mortgage... - Disclosures for John Whitten, RCA0000006456"
        match = re.search(r'Disclosures for\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)\s*,', subject, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 7: "Package Sent, RCA..." - check body instead
        # Pattern 8: "for FirstName LastName were" - generic
        match = re.search(r'for\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)\s+were', subject, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return None

    def match_entity(fields: Dict[str, Any], db: Session, user_id: int) -> Dict[str, Any]:
        """Match extracted fields to existing CRM entities

        Enhanced matching includes:
        - Loan number exact and partial matching
        - Borrower name matching (primary and co-borrower)
        - Last name matching for spouse/family identification
        - Email and phone matching for leads
        - Combined first_name + last_name support
        """

        match_results = {
            "entity_type": None,
            "entity_id": None,
            "confidence": 0.0,
            "candidates": []
        }

        def get_last_name(full_name: str) -> str:
            """Extract last name from full name"""
            if not full_name:
                return ""
            parts = full_name.strip().split()
            return parts[-1].lower() if parts else ""

        def names_match(name1: str, name2: str) -> tuple[bool, float]:
            """Check if names match - returns (is_match, confidence)

            Handles various name formats:
            - "First Last" vs "First Last" (exact)
            - "First Last" vs "Last, First" (reversed with comma)
            - Partial matches (one contains the other)
            - Last name only matches (family members)
            """
            if not name1 or not name2:
                return False, 0.0
            n1 = name1.lower().strip()
            n2 = name2.lower().strip()

            # Exact match
            if n1 == n2:
                return True, 0.95

            # One contains the other (partial name match)
            if n1 in n2 or n2 in n1:
                return True, 0.80

            # Handle "Last, First" vs "First Last" format
            # Normalize both names to "first last" format for comparison
            def normalize_name(name: str) -> set:
                """Extract name parts, handling 'Last, First' and 'First Last' formats"""
                # Remove common suffixes/prefixes
                name = name.lower().strip()
                # Split by comma first (handles "Last, First")
                if ',' in name:
                    parts = [p.strip() for p in name.split(',')]
                    # Reverse if comma format: "Last, First" -> ["First", "Last"]
                    parts = list(reversed(parts))
                else:
                    parts = name.split()
                # Return as set for comparison (ignores order)
                return set(p for p in parts if len(p) > 1)  # Ignore single letter initials

            parts1 = normalize_name(n1)
            parts2 = normalize_name(n2)

            # If at least 2 parts match (first and last name), consider it a match
            common_parts = parts1 & parts2
            if len(common_parts) >= 2:
                return True, 0.90  # High confidence for matching first AND last name

            # If just the last name matches (1 common part that's likely the last name)
            if len(common_parts) == 1:
                # Check if the common part is the last name
                ln1 = get_last_name(name1)
                ln2 = get_last_name(name2)
                if ln1 and ln2 and ln1 == ln2:
                    return True, 0.75  # Last name match (family member)

            # Last name match fallback (using original get_last_name)
            ln1, ln2 = get_last_name(name1), get_last_name(name2)
            if ln1 and ln2 and ln1 == ln2:
                return True, 0.75

            return False, 0.0

        def normalize_phone(phone: str) -> str:
            """Normalize phone number for comparison"""
            if not phone:
                return ""
            return ''.join(c for c in phone if c.isdigit())[-10:]  # Last 10 digits

        def normalize_email(email: str) -> str:
            """Normalize email for comparison"""
            if not email:
                return ""
            return email.lower().strip()

        # Build combined borrower name from first_name + last_name if not already present
        borrower_name = None
        if "borrower_name" in fields and fields["borrower_name"].get("value"):
            borrower_name = fields["borrower_name"]["value"]
        elif "first_name" in fields or "last_name" in fields:
            first = fields.get("first_name", {}).get("value", "") or ""
            last = fields.get("last_name", {}).get("value", "") or ""
            if first or last:
                borrower_name = f"{first} {last}".strip()
                logger.info(f"Built borrower_name from first_name + last_name: '{borrower_name}'")

        # Extract email and phone from fields
        extracted_email = None
        extracted_phone = None
        if "borrower_email" in fields and fields["borrower_email"].get("value"):
            extracted_email = normalize_email(fields["borrower_email"]["value"])
        if "borrower_phone" in fields and fields["borrower_phone"].get("value"):
            extracted_phone = normalize_phone(fields["borrower_phone"]["value"])

        logger.info(f"=" * 60)
        logger.info(f"MATCH_ENTITY DEBUG - Starting match process")
        logger.info(f"=" * 60)
        logger.info(f"Input fields: {list(fields.keys()) if fields else 'None'}")
        logger.info(f"Extracted borrower_name: '{borrower_name}'")
        logger.info(f"Extracted email: '{extracted_email}'")
        logger.info(f"Extracted phone: '{extracted_phone}'")

        # Collect all potential loan numbers from various fields
        loan_numbers_to_try = []
        if "loan_number" in fields and fields["loan_number"].get("value"):
            loan_numbers_to_try.append(str(fields["loan_number"]["value"]).strip())
        if "file_number" in fields and fields["file_number"].get("value"):
            loan_numbers_to_try.append(str(fields["file_number"]["value"]).strip())
        if "cmg_file_number" in fields and fields["cmg_file_number"].get("value"):
            loan_numbers_to_try.append(str(fields["cmg_file_number"]["value"]).strip())
        if "lender_loan_number" in fields and fields["lender_loan_number"].get("value"):
            loan_numbers_to_try.append(str(fields["lender_loan_number"]["value"]).strip())
        if "investor_loan_number" in fields and fields["investor_loan_number"].get("value"):
            loan_numbers_to_try.append(str(fields["investor_loan_number"]["value"]).strip())

        # Remove duplicates while preserving order
        loan_numbers_to_try = list(dict.fromkeys(loan_numbers_to_try))
        logger.info(f"Loan numbers to try: {loan_numbers_to_try}")
        logger.info(f"Total loan numbers to match: {len(loan_numbers_to_try)}")

        # Try to match by loan number first (highest confidence)
        # IMPORTANT: Check ALL tables and collect candidates, then pick the best match
        for loan_num in loan_numbers_to_try:
            loan_num_upper = loan_num.upper()  # For case-insensitive comparison
            logger.info(f"Attempting to match loan number: '{loan_num}'")

            # Helper to determine entity type based on loan stage
            def get_loan_entity_type(loan_obj):
                """Return 'portfolio' for funded loans, 'loan' for active loans"""
                if loan_obj and loan_obj.stage == LoanStage.FUNDED:
                    return "portfolio"
                return "loan"

            # ========== CHECK MUM CLIENTS FIRST (Portfolio) ==========
            # MUM clients are portfolio/past clients - check these BEFORE loans
            logger.info(f"[MUM] Searching MUM clients for loan_number='{loan_num}'")
            try:
                # Count total MUM clients for context
                total_mum = db.query(MUMClient).count()
                logger.info(f"[MUM] Total MUM clients in database: {total_mum}")

                # Exact match (case-insensitive)
                mum_client = db.query(MUMClient).filter(
                    func.upper(MUMClient.loan_number) == loan_num_upper
                ).first()

                if mum_client:
                    logger.info(f"[MUM] ✓ EXACT MATCH: {mum_client.name} (id={mum_client.id}, loan#={mum_client.loan_number})")
                    match_results["candidates"].append({
                        "type": "portfolio",
                        "id": mum_client.id,
                        "name": mum_client.name,
                        "loan_number": mum_client.loan_number,
                        "confidence": 0.98,  # Very high - exact loan number match
                        "match_type": "mum_loan_number_exact"
                    })
                else:
                    logger.info(f"[MUM] No exact match for loan_number='{loan_num}'")
                    # Try partial match (case-insensitive)
                    mum_clients = db.query(MUMClient).filter(
                        MUMClient.loan_number.ilike(f"%{loan_num}%")
                    ).all()
                    logger.info(f"[MUM] Partial match search found {len(mum_clients)} clients")
                    for client in mum_clients:
                        logger.info(f"[MUM] ✓ PARTIAL MATCH: {client.name} (loan#={client.loan_number})")
                        match_results["candidates"].append({
                            "type": "portfolio",
                            "id": client.id,
                            "name": client.name,
                            "loan_number": client.loan_number,
                            "confidence": 0.92,
                            "match_type": "mum_loan_number_partial"
                        })
            except Exception as e:
                logger.warning(f"MUM client loan number matching error: {e}")

            # ========== ACTIVE LOAN PROFILE MATCHING ==========
            # Check ActiveLoanProfile table (separate detailed loan profile table)
            try:
                from models.active_loan_profile import ActiveLoanProfile

                # Exact match on ActiveLoanProfile (case-insensitive)
                active_loan = db.query(ActiveLoanProfile).filter(
                    func.upper(ActiveLoanProfile.loan_number) == loan_num_upper,
                    ActiveLoanProfile.is_deleted == False
                ).first()

                if active_loan:
                    logger.info(f"Found match in ActiveLoanProfile: {active_loan.id}")
                    match_results["candidates"].append({
                        "type": "active_loan",
                        "id": str(active_loan.id),
                        "name": f"Active Loan {active_loan.loan_number}",
                        "loan_number": active_loan.loan_number,
                        "confidence": 0.99,
                        "match_type": "active_loan_exact"
                    })
                else:
                    # Try partial match on ActiveLoanProfile
                    active_loans = db.query(ActiveLoanProfile).filter(
                        ActiveLoanProfile.loan_number.ilike(f"%{loan_num}%"),
                        ActiveLoanProfile.is_deleted == False
                    ).all()

                    for al in active_loans:
                        logger.info(f"Found partial match in ActiveLoanProfile: {al.id}")
                        match_results["candidates"].append({
                            "type": "active_loan",
                            "id": str(al.id),
                            "name": f"Active Loan {al.loan_number}",
                            "loan_number": al.loan_number,
                            "confidence": 0.90,
                            "match_type": "active_loan_partial"
                        })

            except Exception as e:
                logger.debug(f"ActiveLoanProfile check skipped: {e}")

            # ========== REGULAR LOAN TABLE MATCHING ==========
            # Exact match with user's loans (highest confidence)
            try:
                loan = db.query(Loan).filter(
                    func.upper(Loan.loan_number) == loan_num_upper,
                    Loan.loan_officer_id == user_id
                ).first()

                if loan:
                    entity_type = get_loan_entity_type(loan)
                    logger.info(f"Found exact match with user's loan: {loan.id} (type: {entity_type})")
                    match_results["candidates"].append({
                        "type": entity_type,
                        "id": loan.id,
                        "name": loan.borrower_name,
                        "loan_number": loan.loan_number,
                        "confidence": 0.98,
                        "match_type": "loan_user_owned_exact"
                    })
                else:
                    # Try exact loan number match without user filter
                    loan = db.query(Loan).filter(
                        func.upper(Loan.loan_number) == loan_num_upper
                    ).first()
                    if loan:
                        entity_type = get_loan_entity_type(loan)
                        logger.info(f"Found exact match (any user): {loan.id} (type: {entity_type})")
                        match_results["candidates"].append({
                            "type": entity_type,
                            "id": loan.id,
                            "name": loan.borrower_name,
                            "loan_number": loan.loan_number,
                            "confidence": 0.95,
                            "match_type": "loan_exact"
                        })
                    else:
                        # Try partial loan number match (loan numbers may have prefixes/suffixes)
                        logger.info(f"Trying partial match for: {loan_num}")
                        loans = db.query(Loan).filter(
                            Loan.loan_number.ilike(f"%{loan_num}%")
                        ).all()
                        logger.info(f"Found {len(loans)} partial matches")
                        for l in loans:
                            entity_type = get_loan_entity_type(l)
                            conf = 0.90 if l.loan_officer_id == user_id else 0.85
                            match_results["candidates"].append({
                                "type": entity_type,
                                "id": l.id,
                                "name": l.borrower_name,
                                "loan_number": l.loan_number,
                                "confidence": conf,
                                "match_type": "loan_partial"
                            })
            except Exception as e:
                logger.warning(f"Loan table matching error: {e}")

            # If we have loan number candidates, pick the best one and return early
            # (loan number matches are most reliable)
            if match_results["candidates"]:
                best = max(match_results["candidates"], key=lambda x: x["confidence"])
                logger.info(f"Best loan number match: {best['type']} id={best['id']} conf={best['confidence']:.2f}")
                match_results["entity_type"] = best["type"]
                match_results["entity_id"] = best["id"]
                match_results["confidence"] = best["confidence"]
                return match_results

        # ========== LEAD MATCHING (Email, Phone, Name) ==========
        # Try email matching first (highest confidence for leads)
        if extracted_email:
            logger.info(f"Trying email match: '{extracted_email}'")
            # Search ALL leads by email (not just user-owned)
            email_leads = db.query(Lead).filter(
                Lead.email.ilike(extracted_email)
            ).all()
            for lead in email_leads:
                conf = 0.98 if lead.owner_id == user_id else 0.92
                match_results["candidates"].append({
                    "type": "lead",
                    "id": lead.id,
                    "name": lead.name,
                    "confidence": conf,
                    "match_type": "email_exact"
                })
                logger.info(f"Email match found: Lead {lead.id} - {lead.name}")

        # Try phone matching (high confidence)
        if extracted_phone and len(extracted_phone) >= 10:
            logger.info(f"Trying phone match: '{extracted_phone}'")
            # Search ALL leads by phone
            all_leads = db.query(Lead).all()
            for lead in all_leads:
                if lead.phone:
                    lead_phone = normalize_phone(lead.phone)
                    if lead_phone and lead_phone == extracted_phone:
                        # Avoid duplicates
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "lead" and c["id"] == lead.id), None)
                        if not existing:
                            conf = 0.95 if lead.owner_id == user_id else 0.88
                            match_results["candidates"].append({
                                "type": "lead",
                                "id": lead.id,
                                "name": lead.name,
                                "confidence": conf,
                                "match_type": "phone_exact"
                            })
                            logger.info(f"Phone match found: Lead {lead.id} - {lead.name}")

        # Try to match by borrower name - NOW SEARCH ALL LEADS GLOBALLY
        borrower_last_name = get_last_name(borrower_name) if borrower_name else ""
        if borrower_name:
            logger.info(f"Attempting to match borrower name: '{borrower_name}' (last name: '{borrower_last_name}')")

            # Search ALL leads by name (not just user-owned)
            all_leads = db.query(Lead).all()
            for lead in all_leads:
                if lead.name:
                    is_match, conf = names_match(borrower_name, lead.name)
                    if is_match:
                        # Avoid duplicates (might already have email/phone match)
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "lead" and c["id"] == lead.id), None)
                        if existing:
                            # Boost confidence if we have multiple match types
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.1)
                            existing["match_type"] += "+name"
                        else:
                            # Adjust confidence based on ownership
                            final_conf = conf if lead.owner_id == user_id else conf * 0.90
                            match_results["candidates"].append({
                                "type": "lead",
                                "id": lead.id,
                                "name": lead.name,
                                "confidence": final_conf,
                                "match_type": "lead_name"
                            })
                            logger.info(f"Name match found: Lead {lead.id} - {lead.name} (conf: {final_conf:.2f})")

        # ========== LOAN MATCHING (Name, Email, Phone) ==========
        # Run loan matching if we have ANY of: borrower_name, extracted_email, or extracted_phone
        if borrower_name or extracted_email or extracted_phone:
            # Try loans - check borrower_name, coborrower_name, borrower_email, borrower_phone
            # Use raw SQL to avoid enum deserialization issues with the stage column
            try:
                loan_results = db.execute(
                    text("""
                        SELECT id, borrower_name, coborrower_name, loan_officer_id,
                               borrower_email, borrower_phone, co_borrower_email, loan_number
                        FROM loans
                        WHERE loan_officer_id = :user_id
                    """),
                    {"user_id": user_id}
                ).fetchall()
                logger.info(f"Found {len(loan_results)} loans for user {user_id}")
            except Exception as e:
                logger.error(f"Error querying user loans: {e}")
                loan_results = []

            for loan_row in loan_results:
                loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

                # ===== EMAIL MATCHING (highest confidence for loans) =====
                if extracted_email and loan_borrower_email:
                    if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if existing:
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.15)
                            existing["match_type"] += "+email"
                        else:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": 0.96,  # Very high - email is unique
                                "match_type": "borrower_email"
                            })
                            logger.info(f"Loan email match: {loan_id} - {loan_borrower_name} (email: {loan_borrower_email})")

                # Check co-borrower email too
                if extracted_email and loan_coborrower_email:
                    if normalize_email(extracted_email) == normalize_email(loan_coborrower_email):
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if existing:
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                            existing["match_type"] += "+coborrower_email"
                        else:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": f"{loan_borrower_name} (co-borrower email match)",
                                "loan_number": loan_loan_number,
                                "confidence": 0.92,
                                "match_type": "coborrower_email"
                            })

                # ===== PHONE MATCHING =====
                if extracted_phone and loan_borrower_phone:
                    if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if existing:
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                            existing["match_type"] += "+phone"
                        else:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": 0.93,
                                "match_type": "borrower_phone"
                            })
                            logger.info(f"Loan phone match: {loan_id} - {loan_borrower_name}")

                # ===== NAME MATCHING =====
                # Match against primary borrower (only if we have a borrower_name to match)
                if borrower_name and loan_borrower_name:
                    is_match, conf = names_match(borrower_name, loan_borrower_name)
                    if is_match:
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if existing:
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.10)
                            existing["match_type"] += "+name"
                        else:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": conf,
                                "match_type": "borrower_name"
                            })
                            logger.info(f"Loan borrower match: {loan_id} - {loan_borrower_name} (conf: {conf:.2f})")

                # Match against co-borrower (spouse) - only if we have a borrower_name to match
                if borrower_name and loan_coborrower_name:
                    is_match, conf = names_match(borrower_name, loan_coborrower_name)
                    if is_match:
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if existing:
                            existing["confidence"] = min(0.99, existing["confidence"] + 0.08)
                            existing["match_type"] += "+coborrower_name"
                        else:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                                "loan_number": loan_loan_number,
                                "confidence": conf * 0.95,  # Slightly lower for co-borrower
                                "match_type": "coborrower_name"
                            })

                # Last name match - check if email name shares last name with borrower/coborrower
                if borrower_last_name:
                    borrower_ln = get_last_name(loan_borrower_name) if loan_borrower_name else ""
                    coborrower_ln = get_last_name(loan_coborrower_name) if loan_coborrower_name else ""

                    if borrower_last_name == borrower_ln or borrower_last_name == coborrower_ln:
                        # Avoid duplicates - check if we already have this loan
                        existing = next((c for c in match_results["candidates"]
                                       if c["type"] == "loan" and c["id"] == loan_id), None)
                        if not existing:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": 0.75,  # Last name only match
                                "match_type": "last_name_family"
                            })

            # If no matches found with user filter, try broader search for loans
            if not any(c["type"] == "loan" for c in match_results["candidates"]):
                logger.info("No loan matches with user filter, trying all loans...")
                try:
                    all_loan_results = db.execute(
                        text("""
                            SELECT id, borrower_name, coborrower_name, loan_officer_id,
                                   borrower_email, borrower_phone, co_borrower_email, loan_number
                            FROM loans
                        """)
                    ).fetchall()
                    logger.info(f"Found {len(all_loan_results)} total loans in database")
                except Exception as e:
                    logger.error(f"Error querying all loans: {e}")
                    all_loan_results = []

                for loan_row in all_loan_results:
                    loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

                    # Global email match (very high confidence even for non-owned)
                    if extracted_email and loan_borrower_email:
                        if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": 0.94,  # High even for non-owned (email is unique)
                                "match_type": "borrower_email_global"
                            })
                            logger.info(f"Global loan email match: {loan_id} - {loan_borrower_name}")
                            continue  # Email match is definitive

                    # Global phone match
                    if extracted_phone and loan_borrower_phone:
                        if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": 0.90,
                                "match_type": "borrower_phone_global"
                            })
                            logger.info(f"Global loan phone match: {loan_id} - {loan_borrower_name}")
                            continue

                    # Check borrower name
                    if loan_borrower_name:
                        is_match, conf = names_match(borrower_name, loan_borrower_name)
                        if is_match:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": loan_borrower_name,
                                "loan_number": loan_loan_number,
                                "confidence": conf * 0.85,  # Lower for non-owned loan
                                "match_type": "borrower_name_global"
                            })
                            logger.info(f"Global loan borrower match: {loan_id} - {loan_borrower_name}")

                    # Check co-borrower name
                    if loan_coborrower_name:
                        is_match, conf = names_match(borrower_name, loan_coborrower_name)
                        if is_match:
                            match_results["candidates"].append({
                                "type": "loan",
                                "id": loan_id,
                                "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                                "loan_number": loan_loan_number,
                                "confidence": conf * 0.80,
                                "match_type": "coborrower_name_global"
                            })

        # ========== PARTNER MATCHING (Referral Partners) ==========
        # Try to match against referral partners by name, email, phone, or company
        partner_name = fields.get("partner_name", {}).get("value") or fields.get("agent_name", {}).get("value") or fields.get("realtor_name", {}).get("value")
        partner_email = fields.get("partner_email", {}).get("value") or fields.get("agent_email", {}).get("value") or fields.get("realtor_email", {}).get("value")
        partner_phone = fields.get("partner_phone", {}).get("value") or fields.get("agent_phone", {}).get("value") or fields.get("realtor_phone", {}).get("value")
        partner_company = fields.get("partner_company", {}).get("value") or fields.get("brokerage", {}).get("value") or fields.get("company", {}).get("value")

        if partner_name or partner_email or partner_phone:
            logger.info(f"Trying partner match: name='{partner_name}', email='{partner_email}', phone='{partner_phone}'")
            all_partners = db.query(ReferralPartner).filter(ReferralPartner.status == "active").all()

            for partner in all_partners:
                partner_conf = 0.0
                match_reasons = []

                # Email match (highest confidence)
                if partner_email and partner.email:
                    if normalize_email(partner_email) == normalize_email(partner.email):
                        partner_conf = max(partner_conf, 0.95)
                        match_reasons.append("email")

                # Phone match
                if partner_phone and partner.phone:
                    if normalize_phone(partner_phone) == normalize_phone(partner.phone):
                        partner_conf = max(partner_conf, 0.90)
                        match_reasons.append("phone")

                # Name match
                if partner_name and partner.name:
                    is_match, conf = names_match(partner_name, partner.name)
                    if is_match:
                        partner_conf = max(partner_conf, conf * 0.90)
                        match_reasons.append("name")

                # Company match (lower confidence boost)
                if partner_company and partner.company:
                    if partner_company.lower().strip() in partner.company.lower() or partner.company.lower() in partner_company.lower().strip():
                        partner_conf = min(0.98, partner_conf + 0.10)
                        match_reasons.append("company")

                if partner_conf > 0.5:
                    match_results["candidates"].append({
                        "type": "partner",
                        "id": partner.id,
                        "name": partner.name,
                        "confidence": partner_conf,
                        "match_type": "+".join(match_reasons)
                    })
                    logger.info(f"Partner match found: {partner.name} ({partner_conf:.2f}) via {'+'.join(match_reasons)}")

        # ========== PORTFOLIO/MUM CLIENT MATCHING (by name, email, phone) ==========
        # Match against past clients (portfolio) for retention/referral opportunities
        # Note: Loan number matching for MUM clients is handled earlier in the code
        #       with case-insensitive matching and returns early if found

        # Check by name, email, phone
        if borrower_name or extracted_email or extracted_phone:
            logger.info(f"[MUM-NAME] Starting name/email/phone matching for borrower='{borrower_name}'")
            try:
                all_mum_clients = db.query(MUMClient).all()
                logger.info(f"[MUM-NAME] Checking {len(all_mum_clients)} MUM clients for name match")

                # Log first 5 client names for debugging
                sample_names = [c.name for c in all_mum_clients[:5]]
                logger.info(f"[MUM-NAME] Sample MUM client names: {sample_names}")

                for client in all_mum_clients:
                    # Skip if already matched by loan number
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "portfolio" and c["id"] == client.id), None)
                    if existing:
                        continue

                    client_conf = 0.0
                    match_reasons = []

                    # Email match
                    if extracted_email and client.email:
                        if normalize_email(extracted_email) == normalize_email(client.email):
                            client_conf = max(client_conf, 0.95)
                            match_reasons.append("email")

                    # Phone match
                    if extracted_phone and client.phone:
                        if normalize_phone(extracted_phone) == normalize_phone(client.phone):
                            client_conf = max(client_conf, 0.90)
                            match_reasons.append("phone")

                    # Name match
                    if borrower_name and client.name:
                        is_match, conf = names_match(borrower_name, client.name)
                        if is_match:
                            client_conf = max(client_conf, conf * 0.88)
                            match_reasons.append("name")

                    if client_conf > 0.5:
                        match_results["candidates"].append({
                            "type": "portfolio",
                            "id": client.id,
                            "name": client.name,
                            "loan_number": client.loan_number,
                            "confidence": client_conf,
                            "match_type": "+".join(match_reasons)
                        })
                        logger.info(f"Portfolio match found: {client.name} ({client_conf:.2f}) via {'+'.join(match_reasons)}")
            except Exception as e:
                logger.warning(f"Portfolio matching failed (table may not exist): {e}")

        # Loan matching now includes: loan_number, borrower_name, coborrower_name,
        # borrower_email, borrower_phone, and co_borrower_email (handled above)

        # Return best candidate if found
        logger.info(f"=" * 60)
        logger.info(f"MATCH_ENTITY DEBUG - Final Results")
        logger.info(f"=" * 60)
        logger.info(f"Total candidates found: {len(match_results['candidates'])}")

        if match_results["candidates"]:
            # Log all candidates
            for i, cand in enumerate(match_results["candidates"]):
                logger.info(f"  Candidate {i+1}: {cand['type']} - {cand.get('name', 'N/A')} (id={cand['id']}, conf={cand['confidence']:.2f}, via={cand.get('match_type', 'unknown')})")

            best = max(match_results["candidates"], key=lambda x: x["confidence"])
            logger.info(f"✓ BEST MATCH: {best['type']} - {best.get('name', 'N/A')} (id={best['id']}, conf={best['confidence']:.2f})")
            match_results["entity_type"] = best["type"]
            match_results["entity_id"] = best["id"]
            match_results["confidence"] = best["confidence"]
        else:
            logger.info("✗ NO MATCH FOUND - All matching strategies failed")
            logger.info(f"  Searched with: name='{borrower_name}', email='{extracted_email}', phone='{extracted_phone}'")
            logger.info(f"  Loan numbers tried: {loan_numbers_to_try}")

        logger.info(f"=" * 60)
        return match_results

    def classify_email_intent(subject: str, content: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Classify the intent/type of the email based on subject and content"""

        subject_lower = subject.lower() if subject else ""
        content_lower = content.lower() if content else ""

        # Clear to Close detection
        if any(keyword in subject_lower for keyword in ["clear to close", "cleartoclose", "ctc", "clear-to-close"]):
            return {
                "intent": "Clear to Close",
                "description": "Borrower has been cleared to close on their loan",
                "confidence": 0.95
            }

        # Appraisal detection
        if any(keyword in subject_lower for keyword in ["appraisal", "appraisal report", "home appraisal"]):
            return {
                "intent": "Appraisal Update",
                "description": "Appraisal report or update received",
                "confidence": 0.90
            }

        # Rate lock detection
        if any(keyword in subject_lower for keyword in ["rate lock", "lock confirmation", "locked rate"]):
            return {
                "intent": "Rate Lock",
                "description": "Interest rate has been locked for the loan",
                "confidence": 0.90
            }

        # Underwriting detection
        if any(keyword in subject_lower for keyword in ["underwriting", "underwriter", "uw approval", "conditionally approved"]):
            return {
                "intent": "Underwriting Update",
                "description": "Update from underwriting department",
                "confidence": 0.85
            }

        # Title/closing detection
        if any(keyword in subject_lower for keyword in ["title", "closing", "settlement"]):
            return {
                "intent": "Title/Closing Update",
                "description": "Update related to title or closing process",
                "confidence": 0.80
            }

        # Generic loan update
        if "loan_number" in fields or "borrower_name" in fields:
            return {
                "intent": "Loan Update",
                "description": "General loan status update",
                "confidence": 0.70
            }

        return {
            "intent": "General",
            "description": "General communication",
            "confidence": 0.50
        }

    def get_entity_name(entity_type: str, entity_id, db: Session) -> str:
        """Get the name of the matched entity"""
        try:
            if entity_type == "loan":
                loan = db.query(Loan).filter(Loan.id == entity_id).first()
                return loan.borrower_name if loan and loan.borrower_name else f"Loan #{entity_id}"
            elif entity_type == "lead":
                lead = db.query(Lead).filter(Lead.id == entity_id).first()
                return lead.name if lead and lead.name else f"Lead #{entity_id}"
            elif entity_type == "active_loan":
                # Query ActiveLoanProfile table for portfolio loans
                try:
                    from models.active_loan_profile import ActiveLoanProfile
                    from models.lead_profile import LeadProfile
                    import uuid

                    # Handle both UUID string and UUID object
                    if isinstance(entity_id, str):
                        try:
                            loan_uuid = uuid.UUID(entity_id)
                        except ValueError:
                            loan_uuid = entity_id
                    else:
                        loan_uuid = entity_id

                    active_loan = db.query(ActiveLoanProfile).filter(
                        ActiveLoanProfile.id == loan_uuid
                    ).first()

                    if active_loan:
                        # Try to get borrower name from linked lead profile
                        if active_loan.lead_profile_id:
                            lead_profile = db.query(LeadProfile).filter(
                                LeadProfile.id == active_loan.lead_profile_id
                            ).first()
                            if lead_profile:
                                name_parts = []
                                if lead_profile.first_name:
                                    name_parts.append(lead_profile.first_name)
                                if lead_profile.last_name:
                                    name_parts.append(lead_profile.last_name)
                                if name_parts:
                                    return " ".join(name_parts)
                        # Fallback to loan number
                        return f"Portfolio Loan {active_loan.loan_number}"
                except Exception as e:
                    logger.error(f"Error getting ActiveLoanProfile: {e}")
                return f"Portfolio Loan #{entity_id}"
            elif entity_type == "client":
                # Assuming client is a Lead
                client = db.query(Lead).filter(Lead.id == entity_id).first()
                return client.name if client and client.name else f"Client #{entity_id}"
            elif entity_type == "portfolio":
                # Portfolio can refer to either:
                # 1. A funded Loan (from Loan table with stage=FUNDED)
                # 2. A MUM client (from MUMClient table)
                # Try Loan first (more common case with integer IDs)
                try:
                    loan = db.query(Loan).filter(Loan.id == entity_id).first()
                    if loan:
                        return loan.borrower_name if loan.borrower_name else f"Portfolio Loan #{entity_id}"
                except Exception:
                    pass
                # Fall back to MUMClient
                mum_client = db.query(MUMClient).filter(MUMClient.id == entity_id).first()
                return mum_client.name if mum_client and mum_client.name else f"Portfolio Client #{entity_id}"
            elif entity_type == "partner":
                # Referral partner
                partner = db.query(ReferralPartner).filter(ReferralPartner.id == entity_id).first()
                return partner.name if partner and partner.name else f"Partner #{entity_id}"
        except Exception as e:
            logger.error(f"Error getting entity name: {e}")

        return f"{entity_type} #{entity_id}"

    def generate_recommended_action(email_intent: Dict[str, Any], entity_type: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Generate recommended action based on email intent and context"""

        intent = email_intent.get("intent", "General")

        # Clear to Close recommendation
        if intent == "Clear to Close":
            return {
                "title": "Update Status to Clear to Close",
                "description": "The AI recommends updating the loan status to 'Clear to Close' based on this email notification.",
                "action_type": "status_update",
                "action_value": "Clear to Close",
                "learning_status": "Learning from your approvals to auto-execute in the future"
            }

        # Appraisal recommendation
        if intent == "Appraisal Update":
            return {
                "title": "Update Appraisal Information",
                "description": "The AI recommends updating the appraisal value and date in the loan record.",
                "action_type": "field_update",
                "action_value": "appraisal_data",
                "learning_status": "Learning from your approvals to auto-execute in the future"
            }

        # Rate Lock recommendation
        if intent == "Rate Lock":
            return {
                "title": "Update Rate and Lock Date",
                "description": "The AI recommends updating the interest rate and lock expiration date.",
                "action_type": "field_update",
                "action_value": "rate_lock_data",
                "learning_status": "Learning from your approvals to auto-execute in the future"
            }

        # Underwriting recommendation
        if intent == "Underwriting Update":
            return {
                "title": "Update Status to Underwriting",
                "description": "The AI recommends updating the loan status based on underwriting progress.",
                "action_type": "status_update",
                "action_value": "In Underwriting",
                "learning_status": "Learning from your approvals to auto-execute in the future"
            }

        # Generic field update
        return {
            "title": "Update Loan Information",
            "description": "The AI recommends applying the extracted data to the matched loan record.",
            "action_type": "field_update",
            "action_value": "general",
            "learning_status": "Learning from your approvals to auto-execute in the future"
        }


    # ============================================================================
    # CALENDLY TIME SLOT SCHEDULING FOR TASKS
    # ============================================================================

    def detect_scheduling_intent(title: str, description: str = "") -> bool:
        """
        Detect if a task is about scheduling a meeting/call with someone.
        Returns True if scheduling intent is detected.
        """
        scheduling_keywords = [
            "schedule", "scheduling", "appointment", "meeting", "call",
            "pick a time", "pick time", "choose a time", "choose time",
            "set up a call", "set up call", "book", "booking",
            "calendar", "availability", "when to speak", "time to speak",
            "time to meet", "time to talk", "consultation", "consult"
        ]

        text = f"{title} {description}".lower()
        return any(keyword in text for keyword in scheduling_keywords)


    def get_calendly_time_slots_for_user(user_id: int, db: Session, num_slots: int = 5) -> dict:
        """
        Fetch available Calendly time slots for a user.
        Returns formatted time slots with booking links.
        """
        import requests
        from datetime import datetime, timedelta, timezone

        try:
            # First get user's Calendly credential
            cred = db.query(IntegrationCredential).filter(
                IntegrationCredential.user_id == user_id,
                IntegrationCredential.integration_type == "calendly",
                IntegrationCredential.is_active == True
            ).first()

            calendly_token = None
            if cred and cred.api_key:
                calendly_token = cred.api_key
            else:
                # Fallback to environment variable
                calendly_token = os.getenv("CALENDLY_API_TOKEN")

            if not calendly_token:
                logger.warning(f"No Calendly token found for user {user_id}")
                return {"success": False, "error": "Calendly not configured", "slots": []}

            headers = {
                "Authorization": f"Bearer {calendly_token}",
                "Content-Type": "application/json"
            }

            # Get user's Calendly URI
            user_response = requests.get(
                "https://api.calendly.com/users/me",
                headers=headers,
                timeout=10
            )

            if user_response.status_code != 200:
                logger.error(f"Calendly user API error: {user_response.status_code}")
                return {"success": False, "error": "Could not fetch Calendly user", "slots": []}

            user_uri = user_response.json().get("resource", {}).get("uri")

            # Get user's event types
            event_types_response = requests.get(
                "https://api.calendly.com/event_types",
                headers=headers,
                params={"user": user_uri, "active": "true"},
                timeout=10
            )

            if event_types_response.status_code != 200:
                logger.error(f"Calendly event types API error: {event_types_response.status_code}")
                return {"success": False, "error": "Could not fetch event types", "slots": []}

            event_types = event_types_response.json().get("collection", [])

            if not event_types:
                return {"success": False, "error": "No active Calendly event types", "slots": []}

            # Use the first active event type (typically the default meeting type)
            event_type = event_types[0]
            event_type_uuid = event_type.get("uri", "").split("/")[-1]
            event_type_name = event_type.get("name", "Meeting")
            scheduling_url = event_type.get("scheduling_url", "")
            duration_minutes = event_type.get("duration", 30)

            # Get availability for next 7 days
            start_time = datetime.now(timezone.utc).isoformat()
            end_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            availability_response = requests.get(
                "https://api.calendly.com/event_type_available_times",
                headers=headers,
                params={
                    "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                    "start_time": start_time,
                    "end_time": end_time
                },
                timeout=10
            )

            if availability_response.status_code != 200:
                logger.error(f"Calendly availability API error: {availability_response.status_code}")
                return {"success": False, "error": "Could not fetch availability", "slots": []}

            available_times = availability_response.json().get("collection", [])

            # Format the slots - take only the first num_slots
            formatted_slots = []
            for slot in available_times[:num_slots]:
                start_str = slot.get("start_time", "")
                if start_str:
                    # Parse the ISO timestamp
                    slot_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

                    # Format for display: "Monday, Dec 2 at 2:00 PM"
                    display_date = slot_dt.strftime("%A, %b %d at %-I:%M %p")

                    # Create a direct booking link with the time pre-selected
                    # Calendly supports ?month=YYYY-MM&date=YYYY-MM-DD format
                    booking_link = f"{scheduling_url}?month={slot_dt.strftime('%Y-%m')}&date={slot_dt.strftime('%Y-%m-%d')}"

                    formatted_slots.append({
                        "display": display_date,
                        "iso": start_str,
                        "booking_link": booking_link,
                        "duration_minutes": duration_minutes
                    })

            return {
                "success": True,
                "event_type_name": event_type_name,
                "scheduling_url": scheduling_url,
                "duration_minutes": duration_minutes,
                "slots": formatted_slots
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Calendly API request error: {e}")
            return {"success": False, "error": str(e), "slots": []}
        except Exception as e:
            logger.error(f"Error fetching Calendly slots: {e}")
            return {"success": False, "error": str(e), "slots": []}


    def generate_scheduling_email_draft(
        client_name: str,
        calendly_slots: dict,
        user_name: str = "Your Loan Officer"
    ) -> str:
        """
        Generate an AI-drafted email with embedded Calendly time slots.
        Returns HTML-formatted email body with clickable time slot links.
        """
        first_name = client_name.split()[0] if client_name else "there"

        if not calendly_slots.get("success") or not calendly_slots.get("slots"):
            # Fallback if Calendly is not configured or no slots available
            return f"""Hi {first_name},

    I'd like to schedule a call with you to discuss your loan. Please let me know what times work best for you this week.

    Looking forward to connecting!

    Best regards,
    {user_name}"""

        # Build the time slots HTML with clickable links
        slots = calendly_slots.get("slots", [])
        duration = calendly_slots.get("duration_minutes", 30)

        # Create clickable time slot buttons
        time_slots_html = ""
        for slot in slots:
            display = slot.get("display", "")
            link = slot.get("booking_link", "")
            time_slots_html += f"""
    <div style="margin: 8px 0;">
      <a href="{link}" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #218D8D 0%, #10b981 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">
        {display}
      </a>
    </div>"""

        # Build the full email
        email_body = f"""Hi {first_name},

    I'd like to schedule a {duration}-minute call to discuss your mortgage. Please click one of the available times below to book directly on my calendar:

    <div style="margin: 20px 0; padding: 16px; background: #f7fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
    <strong style="color: #1a202c; font-size: 14px;">📅 Available Time Slots:</strong>
    {time_slots_html}
    </div>

    If none of these times work, you can also <a href="{calendly_slots.get('scheduling_url', '#')}" style="color: #218D8D; font-weight: 600;">view all available times</a> on my calendar.

    Looking forward to speaking with you!

    Best regards,
    {user_name}"""

        return email_body


    def create_milestone_tasks(loan, updated_fields: list, db: Session) -> list:
        """
        Create tasks automatically when milestone dates are populated.
        This is triggered when reconciliation data is applied to a loan.
        """
        tasks_created = []

        # Define task triggers based on milestone dates
        # Format: (field_updated, task_title, task_description, days_offset, priority)
        milestone_task_triggers = [
            # Application milestones
            ("stage->PROCESSING", "Review Application Package", "Review newly submitted application for completeness", 0, "high"),
            ("stage->SUBMITTED", "Monitor UW Queue", "Application submitted - monitor underwriting queue", 1, "medium"),
            ("stage->UW_RECEIVED", "Follow Up on Underwriting", "File in underwriting - follow up for status", 2, "high"),
            ("stage->APPROVED", "Review Approval Conditions", "Loan approved - review and clear any conditions", 0, "high"),
            ("stage->CTC", "Schedule Closing", "Clear to Close received - coordinate closing date", 0, "urgent"),
            ("stage->FUNDED", "Send Thank You & Request Review", "Loan funded - send thank you and request review", 1, "medium"),

            # Appraisal milestones
            ("appraisal_ordered_date", "Follow Up on Appraisal", "Appraisal ordered - follow up in 3 days if not scheduled", 3, "medium"),
            ("appraisal_scheduled_date", "Confirm Appraisal Access", "Appraisal scheduled - confirm property access", 0, "medium"),
            ("appraisal_completed_date", "Review Appraisal Report", "Appraisal completed - review report for value/issues", 1, "high"),

            # Lock milestones
            ("lock_date", "Monitor Lock Expiration", "Rate locked - monitor expiration and closing timeline", 0, "high"),
            ("lock_expiration_date", "Lock Expiration Alert", "Rate lock expires soon - verify closing timeline", -3, "urgent"),

            # Closing milestones
            ("closing_date", "7-Day Closing Checklist", "Closing approaching - verify all items ready", -7, "high"),
            ("closing_date", "Final Closing Prep", "Closing in 3 days - final verification", -3, "urgent"),
        ]

        try:
            logger.info(f"🔍 create_milestone_tasks called for loan {loan.loan_number} with updated_fields: {updated_fields}")

            for trigger_field, task_title, task_desc, days_offset, priority in milestone_task_triggers:
                # Check if this field was just updated
                if trigger_field not in updated_fields:
                    continue

                logger.info(f"🎯 Trigger matched: {trigger_field} -> Creating task: {task_title}")

                # Determine the due date
                due_date = None
                if trigger_field.startswith("stage->"):
                    # Stage changes - task is due immediately or with offset from now
                    due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
                else:
                    # Date fields - task is due relative to the date value
                    date_value = getattr(loan, trigger_field, None)
                    if date_value:
                        if isinstance(date_value, datetime):
                            due_date = date_value + timedelta(days=days_offset)
                        else:
                            due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

                if not due_date:
                    due_date = datetime.now(timezone.utc) + timedelta(days=1)

                # Check if task already exists for this loan with same title
                existing_task = db.query(Task).filter(
                    Task.loan_id == loan.id,
                    Task.title == task_title,
                    Task.status != "completed"
                ).first()

                if existing_task:
                    logger.info(f"Task '{task_title}' already exists for loan {loan.loan_number}, skipping")
                    continue

                # Create the task
                new_task = Task(
                    title=task_title,
                    description=f"{task_desc}\n\nLoan: {loan.loan_number}\nBorrower: {loan.borrower_name or 'N/A'}",
                    status="pending",
                    priority=priority,
                    due_date=due_date,
                    loan_id=loan.id,
                    owner_id=loan.loan_officer_id,  # Use loan_officer_id, not owner_id (Loan model doesn't have owner_id)
                    related_contact_name=loan.borrower_name,  # Display borrower name in task list
                    related_type="loan",
                    created_at=datetime.now(timezone.utc)
                )

                db.add(new_task)
                tasks_created.append(task_title)
                logger.info(f"📋 Created task: '{task_title}' for loan {loan.loan_number}, due: {due_date}")

            if tasks_created:
                logger.info(f"💾 Committing {len(tasks_created)} tasks to database...")
                db.commit()
                logger.info(f"✅ Tasks committed successfully: {tasks_created}")
            else:
                logger.info(f"ℹ️ No matching triggers found for updated_fields: {updated_fields}")

        except Exception as e:
            import traceback
            logger.error(f"Error creating milestone tasks: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            db.rollback()

        return tasks_created


    def create_lead_milestone_tasks(lead, updated_fields: list, db: Session) -> list:
        """
        Create tasks automatically when lead milestone dates are populated.
        This is triggered when reconciliation data is applied to a lead.
        """
        tasks_created = []

        # Define task triggers for lead milestones
        lead_task_triggers = [
            # Application milestones
            ("application_started_date", "Review Started Application", "Application started - follow up to encourage completion", 1, "high"),
            ("application_completed_date", "Review Completed Application", "Application completed - review for completeness and pull credit", 0, "high"),
            ("stage->APPLICATION", "Process Application Package", "Application received - begin processing and verification", 0, "high"),
            ("credit_pulled_date", "Review Credit Report", "Credit pulled - review report and discuss with borrower", 0, "high"),
            ("preapproval_issued_date", "Send Preapproval Letter", "Preapproval issued - send letter to borrower and realtor", 0, "high"),
            ("stage->PRE_APPROVED", "Connect with Realtor", "Lead pre-approved - connect with realtor for home search", 1, "medium"),
        ]

        try:
            for trigger_field, task_title, task_desc, days_offset, priority in lead_task_triggers:
                # Check if this field was just updated
                if trigger_field not in updated_fields:
                    continue

                # Determine the due date
                due_date = None
                if trigger_field.startswith("stage->"):
                    due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
                else:
                    date_value = getattr(lead, trigger_field, None)
                    if date_value:
                        if isinstance(date_value, datetime):
                            due_date = date_value + timedelta(days=days_offset)
                        else:
                            due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

                if not due_date:
                    due_date = datetime.now(timezone.utc) + timedelta(days=1)

                # Check if task already exists
                existing_task = db.query(Task).filter(
                    Task.lead_id == lead.id,
                    Task.title == task_title,
                    Task.status != "completed"
                ).first()

                if existing_task:
                    logger.info(f"Task '{task_title}' already exists for lead {lead.name}, skipping")
                    continue

                # Create the task
                new_task = Task(
                    title=task_title,
                    description=f"{task_desc}\n\nLead: {lead.name}\nEmail: {lead.email or 'N/A'}",
                    status="pending",
                    priority=priority,
                    due_date=due_date,
                    lead_id=lead.id,
                    owner_id=lead.owner_id,
                    created_at=datetime.now(timezone.utc)
                )

                db.add(new_task)
                tasks_created.append(task_title)
                logger.info(f"📋 Created task: '{task_title}' for lead {lead.name}, due: {due_date}")

            if tasks_created:
                db.commit()

        except Exception as e:
            logger.error(f"Error creating lead milestone tasks: {e}")
            db.rollback()

        return tasks_created


    def apply_extracted_data(extracted_data: ExtractedData, db: Session) -> bool:
        """Apply extracted data to CRM entities - save all extracted fields to the borrower's profile"""

        def get_field_value(fields: dict, field_name: str, min_confidence: float = 0.70):
            """Helper to safely get field value if confidence is high enough"""
            if field_name in fields:
                field = fields[field_name]
                if isinstance(field, dict) and field.get("confidence", 0) >= min_confidence:
                    return field.get("value")
            return None

        def parse_date(date_str):
            """Parse various date formats to datetime"""
            if not date_str:
                return None
            try:
                if isinstance(date_str, datetime):
                    return date_str
                # Try ISO format first
                return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
            except (ValueError, TypeError):
                try:
                    # Try common formats
                    from dateutil import parser
                    return parser.parse(str(date_str))
                except (ValueError, TypeError):
                    return None

        try:
            fields = extracted_data.fields or {}
            updated_fields = []

            if extracted_data.match_entity_type == "loan" and extracted_data.match_entity_id:
                loan = db.query(Loan).filter(Loan.id == extracted_data.match_entity_id).first()
                if not loan:
                    logger.warning(f"Loan {extracted_data.match_entity_id} not found for data application - approving without applying data")
                    return True  # Allow approval even if loan doesn't exist

                logger.info(f"Applying extracted data to loan {loan.id} ({loan.loan_number})")

                # Borrower name - handle separate first/last name fields
                if value := get_field_value(fields, "borrower_name"):
                    loan.borrower_name = str(value)
                    updated_fields.append("borrower_name")
                elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                    first = get_field_value(fields, "first_name") or ""
                    last = get_field_value(fields, "last_name") or ""
                    full_name = f"{first} {last}".strip()
                    if full_name:
                        loan.borrower_name = full_name
                        updated_fields.append("borrower_name")

                # Borrower email
                if value := get_field_value(fields, "borrower_email"):
                    loan.borrower_email = str(value)
                    updated_fields.append("borrower_email")

                # Borrower phone
                if value := get_field_value(fields, "borrower_phone"):
                    loan.borrower_phone = str(value)
                    updated_fields.append("borrower_phone")

                # Co-borrower name
                if value := get_field_value(fields, "coborrower_name"):
                    loan.coborrower_name = str(value)
                    updated_fields.append("coborrower_name")

                # Amount / Loan Amount
                if value := get_field_value(fields, "amount"):
                    loan.amount = float(value)
                    updated_fields.append("amount")
                elif value := get_field_value(fields, "loan_amount"):
                    loan.amount = float(value)
                    updated_fields.append("amount")

                # Rate
                if value := get_field_value(fields, "rate"):
                    loan.rate = float(value)
                    updated_fields.append("rate")

                # Program
                if value := get_field_value(fields, "program"):
                    loan.program = str(value)
                    updated_fields.append("program")

                # Property Address
                if value := get_field_value(fields, "property_address"):
                    loan.property_address = str(value)
                    updated_fields.append("property_address")

                # Property City
                if value := get_field_value(fields, "property_city"):
                    loan.property_city = str(value)
                    updated_fields.append("property_city")

                # Property State
                if value := get_field_value(fields, "property_state"):
                    loan.property_state = str(value)
                    updated_fields.append("property_state")

                # Property Zip
                if value := get_field_value(fields, "property_zip"):
                    loan.property_zip = str(value)
                    updated_fields.append("property_zip")

                # Processor
                if value := get_field_value(fields, "processor"):
                    loan.processor = str(value)
                    updated_fields.append("processor")

                # Underwriter
                if value := get_field_value(fields, "underwriter"):
                    loan.underwriter = str(value)
                    updated_fields.append("underwriter")

                # Lender
                if value := get_field_value(fields, "lender"):
                    loan.lender = str(value)
                    updated_fields.append("lender")

                # Realtor
                if value := get_field_value(fields, "realtor_name"):
                    loan.realtor_agent = str(value)
                    updated_fields.append("realtor_agent")

                # Title Company
                if value := get_field_value(fields, "title_company"):
                    loan.title_company = str(value)
                    updated_fields.append("title_company")

                # Closing Date
                if value := get_field_value(fields, "closing_date"):
                    if parsed := parse_date(value):
                        loan.closing_date = parsed
                        updated_fields.append("closing_date")
                elif value := get_field_value(fields, "closing_scheduled_date"):
                    if parsed := parse_date(value):
                        loan.closing_date = parsed
                        updated_fields.append("closing_date")

                # Lock Date
                if value := get_field_value(fields, "rate_lock_date"):
                    if parsed := parse_date(value):
                        loan.lock_date = parsed
                        updated_fields.append("lock_date")

                # Lock Expiration
                if value := get_field_value(fields, "lock_expiration"):
                    if parsed := parse_date(value):
                        loan.lock_expiration_date = parsed
                        updated_fields.append("lock_expiration_date")

                # Appraisal Ordered Date
                if value := get_field_value(fields, "appraisal_ordered_date"):
                    if parsed := parse_date(value):
                        loan.appraisal_ordered_date = parsed
                        updated_fields.append("appraisal_ordered_date")

                # Appraisal Scheduled Date
                if value := get_field_value(fields, "appraisal_scheduled_date"):
                    if parsed := parse_date(value):
                        loan.appraisal_scheduled_date = parsed
                        updated_fields.append("appraisal_scheduled_date")

                # Appraisal Completed Date
                if value := get_field_value(fields, "appraisal_completed_date"):
                    if parsed := parse_date(value):
                        loan.appraisal_completed_date = parsed
                        updated_fields.append("appraisal_completed_date")

                # Appraisal Value
                if value := get_field_value(fields, "appraisal_value"):
                    loan.appraisal_value = float(value)
                    updated_fields.append("appraisal_value")

                # Initial Disclosures Sent Date
                if value := get_field_value(fields, "initial_disclosures_sent_date"):
                    if parsed := parse_date(value):
                        loan.initial_disclosures_sent_date = parsed
                        updated_fields.append("initial_disclosures_sent_date")

                # Initial Disclosures Signed Date
                if value := get_field_value(fields, "initial_disclosures_signed_date"):
                    if parsed := parse_date(value):
                        loan.initial_disclosures_signed_date = parsed
                        updated_fields.append("initial_disclosures_signed_date")

                # CD Received/Signed Date
                if value := get_field_value(fields, "cd_received_signed_date"):
                    if parsed := parse_date(value):
                        loan.cd_received_signed_date = parsed
                        updated_fields.append("cd_received_signed_date")

                # Final Closing Package Sent Date - AUTO TRIGGERS STAGE TO CTC
                if value := get_field_value(fields, "final_closing_package_sent_date"):
                    if parsed := parse_date(value):
                        loan.final_closing_package_sent_date = parsed
                        updated_fields.append("final_closing_package_sent_date")
                        # Auto-update stage to CTC when closing docs are sent
                        if loan.stage != LoanStage.FUNDED:
                            loan.stage = LoanStage.CTC
                            updated_fields.append("stage->CTC")

                # Borrower Name (from extracted data)
                if value := get_field_value(fields, "borrower_name"):
                    if not loan.borrower_name or loan.borrower_name.strip() == "":
                        loan.borrower_name = str(value)
                        updated_fields.append("borrower_name")

                # Milestone - update stage based on milestone
                if value := get_field_value(fields, "milestone", min_confidence=0.85):
                    milestone = str(value).lower()
                    if "clearto" in milestone or "ctc" in milestone:
                        loan.stage = LoanStage.CTC
                        updated_fields.append("stage->CTC")
                    elif "approved" in milestone:
                        loan.stage = LoanStage.APPROVED
                        updated_fields.append("stage->APPROVED")
                    elif "processing" in milestone:
                        loan.stage = LoanStage.PROCESSING
                        updated_fields.append("stage->PROCESSING")
                    elif "u/w" in milestone or "underwriting" in milestone or "received" in milestone:
                        loan.stage = LoanStage.UW_RECEIVED
                        updated_fields.append("stage->UW_RECEIVED")
                    elif "submitted" in milestone:
                        loan.stage = LoanStage.SUBMITTED
                        updated_fields.append("stage->SUBMITTED")
                    elif "funded" in milestone:
                        loan.stage = LoanStage.FUNDED
                        loan.funded_date = datetime.now(timezone.utc)
                        updated_fields.append("stage->FUNDED")

                # Update the updated_at timestamp
                loan.updated_at = datetime.now(timezone.utc)

                db.commit()
                logger.info(f"✅ Applied {len(updated_fields)} fields to loan {loan.loan_number}: {', '.join(updated_fields)}")

                # TRIGGER TASK CREATION based on updated milestone dates
                tasks_created = create_milestone_tasks(loan, updated_fields, db)
                if tasks_created:
                    logger.info(f"📋 Created {len(tasks_created)} tasks for loan {loan.loan_number}: {tasks_created}")
                return True

            elif extracted_data.match_entity_type == "lead" and extracted_data.match_entity_id:
                lead = db.query(Lead).filter(Lead.id == extracted_data.match_entity_id).first()
                if not lead:
                    logger.warning(f"Lead {extracted_data.match_entity_id} not found for data application - approving without applying data")
                    return True  # Allow approval even if lead doesn't exist

                logger.info(f"Applying extracted data to lead {lead.id} ({lead.name})")

                # Update lead fields - handle various field name formats from AI extraction
                # Name - check for combined or separate first/last name fields
                if value := get_field_value(fields, "borrower_name"):
                    lead.name = str(value)
                    updated_fields.append("name")
                elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                    first = get_field_value(fields, "first_name") or ""
                    last = get_field_value(fields, "last_name") or ""
                    full_name = f"{first} {last}".strip()
                    if full_name:
                        lead.name = full_name
                        updated_fields.append("name")

                # Email - check multiple possible field names
                if value := get_field_value(fields, "email"):
                    lead.email = str(value)
                    updated_fields.append("email")
                elif value := get_field_value(fields, "borrower_email"):
                    lead.email = str(value)
                    updated_fields.append("email")

                # Phone - check multiple possible field names
                if value := get_field_value(fields, "phone"):
                    lead.phone = str(value)
                    updated_fields.append("phone")
                elif value := get_field_value(fields, "borrower_phone"):
                    lead.phone = str(value)
                    updated_fields.append("phone")

                if value := get_field_value(fields, "credit_score"):
                    lead.credit_score = int(value)
                    updated_fields.append("credit_score")

                if value := get_field_value(fields, "loan_amount"):
                    lead.loan_amount = float(value)
                    updated_fields.append("loan_amount")
                elif value := get_field_value(fields, "amount"):
                    lead.loan_amount = float(value)
                    updated_fields.append("loan_amount")

                if value := get_field_value(fields, "property_address"):
                    lead.property_address = str(value)
                    updated_fields.append("property_address")

                if value := get_field_value(fields, "program"):
                    lead.loan_type = str(value)
                    updated_fields.append("loan_type")

                # Milestone dates for leads
                if value := get_field_value(fields, "application_started_date"):
                    if parsed := parse_date(value):
                        lead.application_started_date = parsed
                        updated_fields.append("application_started_date")

                if value := get_field_value(fields, "application_completed_date"):
                    if parsed := parse_date(value):
                        lead.application_completed_date = parsed
                        updated_fields.append("application_completed_date")
                        # Also update stage to APPLICATION using raw SQL
                        db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                                   {"stage": LeadStage.APPLICATION.name, "id": lead.id})
                        updated_fields.append("stage->APPLICATION")

                if value := get_field_value(fields, "credit_pulled_date"):
                    if parsed := parse_date(value):
                        lead.credit_pulled_date = parsed
                        updated_fields.append("credit_pulled_date")

                if value := get_field_value(fields, "preapproval_issued_date"):
                    if parsed := parse_date(value):
                        lead.preapproval_issued_date = parsed
                        updated_fields.append("preapproval_issued_date")
                        # Also update stage to PRE_APPROVED using raw SQL
                        db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                                   {"stage": LeadStage.PRE_APPROVED.name, "id": lead.id})
                        updated_fields.append("stage->PRE_APPROVED")

                # Update timestamp
                lead.updated_at = datetime.now(timezone.utc)

                db.commit()
                logger.info(f"✅ Applied {len(updated_fields)} fields to lead {lead.name}: {', '.join(updated_fields)}")

                # TRIGGER TASK CREATION based on updated milestone dates for leads
                tasks_created = create_lead_milestone_tasks(lead, updated_fields, db)
                if tasks_created:
                    logger.info(f"📋 Created {len(tasks_created)} tasks for lead {lead.name}: {tasks_created}")
                return True

            elif extracted_data.match_entity_type == "partner" and extracted_data.match_entity_id:
                partner = db.query(ReferralPartner).filter(ReferralPartner.id == extracted_data.match_entity_id).first()
                if not partner:
                    logger.warning(f"Partner {extracted_data.match_entity_id} not found for data application")
                    return True

                logger.info(f"Applying extracted data to partner {partner.id} ({partner.name})")

                # Update partner fields
                if value := get_field_value(fields, "partner_name"):
                    partner.name = str(value)
                    updated_fields.append("name")
                elif value := get_field_value(fields, "agent_name"):
                    partner.name = str(value)
                    updated_fields.append("name")
                elif value := get_field_value(fields, "realtor_name"):
                    partner.name = str(value)
                    updated_fields.append("name")

                if value := get_field_value(fields, "partner_email"):
                    partner.email = str(value)
                    updated_fields.append("email")
                elif value := get_field_value(fields, "agent_email"):
                    partner.email = str(value)
                    updated_fields.append("email")

                if value := get_field_value(fields, "partner_phone"):
                    partner.phone = str(value)
                    updated_fields.append("phone")
                elif value := get_field_value(fields, "agent_phone"):
                    partner.phone = str(value)
                    updated_fields.append("phone")

                if value := get_field_value(fields, "partner_company"):
                    partner.company = str(value)
                    updated_fields.append("company")
                elif value := get_field_value(fields, "brokerage"):
                    partner.company = str(value)
                    updated_fields.append("company")

                # Update last interaction timestamp
                partner.last_interaction = datetime.now(timezone.utc)
                updated_fields.append("last_interaction")

                db.commit()
                logger.info(f"✅ Applied {len(updated_fields)} fields to partner {partner.name}: {', '.join(updated_fields)}")
                return True

            elif extracted_data.match_entity_type == "portfolio" and extracted_data.match_entity_id:
                # Portfolio clients (MUM clients) - past borrowers
                try:
                    client = db.query(MUMClient).filter(MUMClient.id == extracted_data.match_entity_id).first()
                    if not client:
                        logger.warning(f"Portfolio client {extracted_data.match_entity_id} not found")
                        return True

                    logger.info(f"Applying extracted data to portfolio client {client.id} ({client.name})")

                    # Update portfolio client fields
                    if value := get_field_value(fields, "borrower_name"):
                        client.name = str(value)
                        updated_fields.append("name")

                    if value := get_field_value(fields, "borrower_email"):
                        client.email = str(value)
                        updated_fields.append("email")
                    elif value := get_field_value(fields, "email"):
                        client.email = str(value)
                        updated_fields.append("email")

                    if value := get_field_value(fields, "borrower_phone"):
                        client.phone = str(value)
                        updated_fields.append("phone")
                    elif value := get_field_value(fields, "phone"):
                        client.phone = str(value)
                        updated_fields.append("phone")

                    db.commit()
                    logger.info(f"✅ Applied {len(updated_fields)} fields to portfolio client {client.name}: {', '.join(updated_fields)}")
                except Exception as e:
                    logger.warning(f"Portfolio client update failed: {e}")
                return True

            # No match - return True anyway since data was extracted, just nowhere to apply
            logger.info("No matched entity to apply data to")
            return True

        except Exception as e:
            logger.error(f"Apply extracted data error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't rollback here - let the calling function handle transactions
            return False

    # ============================================================================
    # MICROSOFT OAUTH & EMAIL SYNC FUNCTIONS
    # ============================================================================

    # Simple token encryption (use Fernet for production)
    from cryptography.fernet import Fernet
    import base64

    # Generate encryption key from SECRET_KEY (in production, use dedicated key)
    def get_encryption_key():
        # Use first 32 bytes of SECRET_KEY, base64 encoded
        key_material = SECRET_KEY.encode()[:32].ljust(32, b'0')
        return base64.urlsafe_b64encode(key_material)

    def encrypt_token(token: str) -> str:
        """Encrypt a token for secure storage"""
        f = Fernet(get_encryption_key())
        return f.encrypt(token.encode()).decode()

    def decrypt_token(encrypted_token: str) -> str:
        """Decrypt a stored token"""
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_token.encode()).decode()

    async def refresh_microsoft_token(oauth_record: MicrosoftOAuthToken, db: Session) -> dict:
        """Refresh an expired Microsoft access token.

        Returns:
            dict with 'success' (bool) and optionally 'error' (str) and 'needs_reauth' (bool)
        """
        try:
            refresh_token = decrypt_token(oauth_record.refresh_token)

            # Microsoft token endpoint
            token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

            # Get client credentials from environment
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

            if not client_id or not client_secret:
                logger.error("Microsoft OAuth credentials not configured")
                return {"success": False, "error": "Microsoft OAuth credentials not configured"}

            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.Read offline_access"
            }

            response = requests.post(token_url, data=data)

            if response.status_code == 200:
                token_data = response.json()

                # Update tokens
                oauth_record.access_token = encrypt_token(token_data["access_token"])
                oauth_record.refresh_token = encrypt_token(token_data["refresh_token"])
                oauth_record.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
                oauth_record.updated_at = datetime.now(timezone.utc)

                db.commit()
                logger.info(f"Refreshed Microsoft token for user {oauth_record.user_id}")
                return {"success": True}
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_code = error_data.get("error", "")
                error_desc = error_data.get("error_description", response.text)

                # Check if refresh token is invalid/expired (requires re-authentication)
                needs_reauth = error_code in ["invalid_grant", "interaction_required", "consent_required"]

                logger.error(f"Failed to refresh Microsoft token: {error_code} - {error_desc}")
                return {
                    "success": False,
                    "error": error_desc,
                    "needs_reauth": needs_reauth,
                    "error_code": error_code
                }

        except Exception as e:
            logger.error(f"Error refreshing Microsoft token: {e}")
            return {"success": False, "error": str(e)}

    async def fetch_microsoft_emails(oauth_record: MicrosoftOAuthToken, db: Session, limit: int = 50):
        """Fetch emails from Microsoft Graph API"""
        try:
            # Check if token needs refresh (proactively refresh if expiring within 5 mins)
            needs_refresh = False
            if oauth_record.token_expires_at:
                token_expiry = oauth_record.token_expires_at
                if token_expiry.tzinfo is None:
                    token_expiry = token_expiry.replace(tzinfo=timezone.utc)
                needs_refresh = token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5)

            if needs_refresh:
                logger.info("Token expiring soon, refreshing proactively...")
                refresh_result = await refresh_microsoft_token(oauth_record, db)
                if not refresh_result.get("success"):
                    return {
                        "error": refresh_result.get("error", "Failed to refresh token"),
                        "needs_reauth": refresh_result.get("needs_reauth", False)
                    }
                # Refresh ORM object to get updated token
                db.refresh(oauth_record)

            access_token = decrypt_token(oauth_record.access_token)

            # Microsoft Graph API endpoint
            folder = oauth_record.sync_folder or "Inbox"
            graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages?$top={limit}&$orderby=receivedDateTime desc"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            response = requests.get(graph_url, headers=headers)

            # If we get a 401, try refreshing token and retry ONCE
            if response.status_code == 401:
                logger.info("Got 401 from Microsoft API, attempting token refresh...")
                refresh_result = await refresh_microsoft_token(oauth_record, db)
                if not refresh_result.get("success"):
                    return {
                        "error": refresh_result.get("error", "Failed to refresh token"),
                        "needs_reauth": refresh_result.get("needs_reauth", True)
                    }
                # Refresh the ORM object to get updated token from DB
                db.refresh(oauth_record)
                # Retry with new token
                access_token = decrypt_token(oauth_record.access_token)
                headers["Authorization"] = f"Bearer {access_token}"
                response = requests.get(graph_url, headers=headers)

            if response.status_code == 200:
                emails_data = response.json()
                emails = emails_data.get("value", [])

                logger.info(f"Fetched {len(emails)} emails from Microsoft for user {oauth_record.user_id} (folder: {folder})")
                if len(emails) == 0:
                    logger.warning(f"Microsoft API returned 0 emails for folder '{folder}'. API response keys: {list(emails_data.keys())}")

                # Update last sync time
                oauth_record.last_sync_at = datetime.now(timezone.utc)
                db.commit()

                return {"emails": emails, "count": len(emails)}
            else:
                error_detail = response.text
                logger.error(f"Failed to fetch Microsoft emails: {response.status_code} - {error_detail}")
                # Check if it's still auth-related
                if response.status_code == 401 or response.status_code == 403:
                    return {"error": "Authentication failed", "needs_reauth": True}
                return {"error": f"Microsoft API error: {response.status_code} - {error_detail[:200]}"}

        except Exception as e:
            logger.error(f"Error fetching Microsoft emails: {e}")
            return {"error": str(e)}


    async def delete_microsoft_email(oauth_record: MicrosoftOAuthToken, message_id: str, db: Session):
        """Move an email to trash in Microsoft 365/Outlook"""
        try:
            # Check if token needs refresh (proactively)
            needs_refresh = False
            if oauth_record.token_expires_at:
                token_expiry = oauth_record.token_expires_at
                if token_expiry.tzinfo is None:
                    token_expiry = token_expiry.replace(tzinfo=timezone.utc)
                needs_refresh = token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5)

            if needs_refresh:
                logger.info("Token expiring soon, refreshing before delete...")
                refresh_result = await refresh_microsoft_token(oauth_record, db)
                if not refresh_result.get("success"):
                    return {
                        "success": False,
                        "error": refresh_result.get("error", "Failed to refresh token"),
                        "needs_reauth": refresh_result.get("needs_reauth", False)
                    }
                # Refresh ORM object to get updated token
                db.refresh(oauth_record)

            access_token = decrypt_token(oauth_record.access_token)

            # Microsoft Graph API endpoint to move email to trash (deletedItems folder)
            graph_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            body = {"destinationId": "deleteditems"}

            response = requests.post(graph_url, headers=headers, json=body)

            # If we get a 401, try refreshing token and retry ONCE
            if response.status_code == 401:
                logger.info("Got 401 from Microsoft API on delete, attempting token refresh...")
                refresh_result = await refresh_microsoft_token(oauth_record, db)
                if not refresh_result.get("success"):
                    return {
                        "success": False,
                        "error": refresh_result.get("error", "Failed to refresh token"),
                        "needs_reauth": refresh_result.get("needs_reauth", True)
                    }
                # Refresh ORM object to get updated token from DB
                db.refresh(oauth_record)
                # Retry with new token
                access_token = decrypt_token(oauth_record.access_token)
                headers["Authorization"] = f"Bearer {access_token}"
                response = requests.post(graph_url, headers=headers, json=body)

            if response.status_code == 200 or response.status_code == 201:
                logger.info(f"Successfully moved email {message_id} to trash for user {oauth_record.user_id}")
                return {"success": True, "message_id": message_id}
            elif response.status_code == 404:
                # Email might have already been deleted
                logger.warning(f"Email {message_id} not found - may have already been deleted")
                return {"success": True, "message_id": message_id, "note": "already_deleted"}
            else:
                error_detail = response.text
                logger.error(f"Failed to delete Microsoft email: {response.status_code} - {error_detail}")
                if response.status_code == 401 or response.status_code == 403:
                    return {"success": False, "error": "Authentication failed", "needs_reauth": True}
                return {"success": False, "error": f"Microsoft API error: {response.status_code}"}

        except Exception as e:
            logger.error(f"Error deleting Microsoft email: {e}")
            return {"success": False, "error": str(e)}


    async def process_microsoft_email_to_dre(email_data: dict, user_id: int, db: Session):
        """Process a Microsoft Graph email and ingest into DRE"""
        try:
            # Extract email data
            message_id = email_data.get("id", "")  # Microsoft Graph message ID
            subject = email_data.get("subject", "")
            sender = email_data.get("from", {}).get("emailAddress", {}).get("address", "")
            recipients = [r.get("emailAddress", {}).get("address", "") for r in email_data.get("toRecipients", [])]
            received_at = email_data.get("receivedDateTime", "")

            # Check if this email was already processed (deduplication)
            if message_id:
                existing_event = db.query(IncomingDataEvent).filter(
                    IncomingDataEvent.external_message_id == message_id,
                    IncomingDataEvent.user_id == user_id
                ).first()

                if existing_event:
                    logger.debug(f"Email {message_id} already processed (event {existing_event.id}), skipping")
                    return {"status": "skipped", "reason": "already_processed", "event_id": existing_event.id}

            # Get body content - always try to get both HTML and text
            body = email_data.get("body", {})
            body_content = body.get("content", "")
            content_type = body.get("contentType", "text")

            if content_type == "html":
                raw_html = body_content
                # Convert HTML to plain text for display
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(body_content, 'html.parser')
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    raw_text = soup.get_text(separator='\n', strip=True)
                except Exception:
                    # Fallback: simple HTML tag removal
                    import re
                    raw_text = re.sub(r'<[^>]+>', '', body_content)
                    raw_text = raw_text.replace('&nbsp;', ' ').replace('&amp;', '&')
            else:
                raw_text = body_content
                raw_html = None

            # Parse received_at - handle both ISO format (Microsoft) and RFC 2822 (Gmail)
            parsed_received_at = datetime.now(timezone.utc)
            if received_at:
                try:
                    # Try ISO format first (Microsoft Graph)
                    parsed_received_at = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        # Try RFC 2822 format (Gmail)
                        from email.utils import parsedate_to_datetime
                        parsed_received_at = parsedate_to_datetime(received_at)
                    except Exception:
                        logger.warning(f"Could not parse date: {received_at}")
                        parsed_received_at = datetime.now(timezone.utc)

            # Create incoming data event
            db_event = IncomingDataEvent(
                source="microsoft365",
                external_message_id=message_id,
                raw_text=raw_text,
                raw_html=raw_html,
                subject=subject,
                sender=sender,
                recipients=recipients,
                received_at=parsed_received_at,
                user_id=user_id,
                processed=False
            )
            db.add(db_event)
            db.commit()
            db.refresh(db_event)

            logger.info(f"Ingested NEW Microsoft email {db_event.id} from {sender} (msg_id: {message_id[:20]}...)")

            # Also queue to Email Intelligence system for intelligent disposition
            try:
                from routes.email_intelligence_routes import queue_email_for_intelligence
                intel_email_data = {
                    "email_provider": "microsoft365",
                    "provider_message_id": message_id,
                    "thread_id": email_data.get("conversationId"),
                    "from_email": sender,
                    "from_name": email_data.get("from", {}).get("emailAddress", {}).get("name", ""),
                    "to_emails": recipients,
                    "cc_emails": [r.get("emailAddress", {}).get("address", "") for r in email_data.get("ccRecipients", [])],
                    "subject": subject,
                    "body_preview": raw_text[:500] if raw_text else "",
                    "body_full": raw_text,
                    "body_html": raw_html,
                    "sent_date": email_data.get("sentDateTime"),
                    "received_date": received_at,
                    "has_attachments": email_data.get("hasAttachments", False),
                    "direction": "inbound"
                }
                await queue_email_for_intelligence(
                    db=db,
                    user_id=user_id,
                    email_data=intel_email_data,
                    auto_analyze=True,  # Auto-analyze to identify borrower, create tasks, log conversations
                    source="microsoft365"
                )
                logger.debug(f"Queued email {message_id[:20]}... to Email Intelligence")
            except Exception as intel_error:
                logger.warning(f"Email Intelligence queue error: {intel_error}")

            # Check AI provider setting
            ai_provider = os.getenv("AI_PROVIDER", "openai").lower()

            # Trigger extraction with Claude or legacy OpenAI
            content = raw_text or raw_html or ""

            if ai_provider == "claude":
                # Use Claude for superior extraction (97-99% accuracy)
                from ai_providers.claude_parser import get_claude_parser

                logger.info(f"🤖 Using Claude parser for email {db_event.id}")

                # Format email for Claude parser
                claude_email_data = {
                    "id": message_id,
                    "subject": subject,
                    "from_email": sender,
                    "body_text": raw_text,
                    "body_html": raw_html,
                    "received_at": received_at
                }

                # Get Claude parser and classify
                parser = get_claude_parser()
                profile_type = parser.classify_email(claude_email_data)

                logger.info(f"📧 Email classified as: {profile_type}")

                # Skip unrelated emails BEFORE trying to parse
                if profile_type == "unrelated":
                    db_event.processed = True
                    db.commit()
                    logger.info(f"Skipped unrelated email (Claude): {subject[:50]}")
                    return {"status": "skipped", "reason": "Email classified as unrelated to mortgage business"}

                # Parse with Claude
                parsed_result = await parser.parse_email(
                    claude_email_data,
                    profile_type,
                    current_profile=None
                )

                # Map Claude result to DRE format
                extracted_fields = parsed_result.get('extracted_fields', {})
                confidence_scores = parsed_result.get('confidence_scores', {})

                # Convert Claude format to legacy format
                # Claude: {"field_name": "value"}
                # Legacy: {"field_name": {"value": "value", "confidence": 0.95}}
                fields = {}
                for field_name, field_value in extracted_fields.items():
                    # Get confidence score (convert from 0-100 to 0-1)
                    confidence = confidence_scores.get(field_name, 95) / 100.0

                    # Wrap in legacy format
                    fields[field_name] = {
                        "value": field_value,
                        "confidence": confidence
                    }

                avg_confidence = parsed_result.get('overall_confidence', 0) / 100.0  # Convert to 0-1
                classification = {
                    "category": profile_type,
                    "subcategory": parsed_result.get('email_summary', ''),
                    "confidence": avg_confidence
                }

                logger.info(f"✅ Claude extracted {len(fields)} fields with {avg_confidence*100:.1f}% confidence")
            else:
                # Legacy OpenAI extraction
                logger.info(f"⚙️  Using legacy OpenAI parser for email {db_event.id}")
                classification = classify_email_content(content, subject)
                fields = extract_loan_fields(content, classification["category"]) if classification["category"] != "unrelated" and classification["confidence"] >= 0.3 else {}
                avg_confidence = classification["confidence"]

            # Skip unrelated emails - don't clutter the reconciliation queue
            if classification["category"] == "unrelated":
                db_event.processed = True
                db.commit()
                logger.info(f"Skipped unrelated email: {subject[:50]}")
                return {"status": "skipped", "reason": "Email classified as unrelated to mortgage business"}

            # Extract fields if not already done (OpenAI path)
            if not fields:
                fields = extract_loan_fields(content, classification["category"])

            # Handle different confidence formats (Claude vs OpenAI)
            if ai_provider == "claude":
                # Claude already calculated avg_confidence
                pass
            else:
                # Legacy OpenAI format - fields contain {"confidence": ...} dicts
                confidences = [field.get("confidence", 0.0) for field in fields.values()] if fields else []
                avg_confidence = sum(confidences) / len(confidences) if confidences else classification["confidence"]

            entity_match = match_entity(fields, db, user_id) if fields else {"entity_type": None, "entity_id": None, "confidence": 0.0}

            # Check for learned patterns - if user has approved similar emails before, auto-complete
            learned_pattern = None
            sender_domain = sender.split("@")[1] if "@" in sender else ""
            email_intent = classification.get("category", "")

            try:
                pattern_result = db.execute(text("""
                    SELECT id, pattern_type, pattern_value, response_type, response_config,
                           confidence_score, auto_execute_threshold, approval_count
                    FROM email_response_patterns
                    WHERE user_id = :user_id
                      AND is_active = true
                      AND (
                          (pattern_type = 'sender_domain' AND pattern_value = :domain)
                          OR (pattern_type = 'sender_email' AND pattern_value = :email)
                          OR (pattern_type = 'email_intent' AND pattern_value = :intent)
                      )
                    ORDER BY confidence_score DESC, approval_count DESC
                    LIMIT 1
                """), {
                    "user_id": user_id,
                    "domain": sender_domain,
                    "email": sender.lower(),
                    "intent": email_intent,
                })
                row = pattern_result.fetchone()
                if row and row.confidence_score and float(row.confidence_score) >= 0.90 and row.approval_count >= 3:
                    learned_pattern = {
                        "id": row.id,
                        "pattern_type": row.pattern_type,
                        "response_type": row.response_type,
                        "confidence_score": float(row.confidence_score),
                        "approval_count": row.approval_count
                    }
                    logger.info(f"Found learned pattern {row.id} ({row.pattern_type}={row.pattern_value}) with {row.approval_count} approvals")
            except Exception as pattern_error:
                logger.warning(f"Could not check learned patterns: {pattern_error}")

            # Determine status based on confidence, category, AND learned patterns
            status = "needs_review"  # Default to needs_review for safety
            auto_complete_reason = None

            # Check if we have a learned pattern that should auto-complete
            if learned_pattern:
                status = "auto_approved"
                auto_complete_reason = f"Learned pattern: {learned_pattern['pattern_type']} ({learned_pattern['approval_count']} prior approvals)"
                logger.info(f"Auto-completing email based on learned pattern: {auto_complete_reason}")
            elif fields and avg_confidence > 0.85 and entity_match["confidence"] > 0.90:
                status = "auto_approved"
                auto_complete_reason = "High AI confidence with entity match"
            elif fields and avg_confidence >= 0.60 and entity_match["confidence"] >= 0.50:
                status = "pending_review"
            # Everything else stays as needs_review

            extracted = ExtractedData(
                event_id=db_event.id,
                category=classification["category"],
                subcategory=classification.get("subcategory"),
                fields=fields or {},  # Use empty dict if no fields
                match_entity_type=entity_match["entity_type"],
                match_entity_id=entity_match["entity_id"],
                match_confidence=entity_match["confidence"],
                ai_confidence=avg_confidence,
                status=status
            )
            db.add(extracted)
            db_event.processed = True
            db.commit()

            # Auto-apply if high confidence
            if status == "auto_approved":
                if apply_extracted_data(extracted, db):
                    extracted.status = "applied"
                    db.commit()
                    logger.info(f"Auto-applied extraction from email {db_event.id} - Reason: {auto_complete_reason or 'High confidence'}")

                    # Update pattern statistics if we used a learned pattern
                    if learned_pattern:
                        try:
                            db.execute(text("""
                                UPDATE email_response_patterns
                                SET last_matched_at = NOW(),
                                    last_approved_at = NOW()
                                WHERE id = :pattern_id
                            """), {"pattern_id": learned_pattern["id"]})
                            db.commit()
                        except Exception as update_error:
                            logger.warning(f"Could not update pattern stats: {update_error}")

            return {"status": "success", "event_id": db_event.id}

        except Exception as e:
            logger.error(f"Error processing Microsoft email: {e}")
            db.rollback()
            return {"status": "error", "error": str(e)}

    # Extracted to routes/db_migration_routes.py
    # (add-external-message-id through fix-voicemail-drops-columns)


    # Extracted to routes/debug_data_routes.py
    # (email-sync-status, create-sample-tasks, auto-fix-error, microsoft/sync-now,
    #  reconciliation/*, debug/all-loans, debug/dashboard-diagnosis, microsoft/*,
    #  debug/test-task-creation, admin/create-salesforce-tables, debug/complete-onboarding,
    #  admin/run-salesforce-migration, debug/test-two-way-email, debug/send-real-email,
    #  webhook/sendgrid-inbound, debug/simulate-email-reply, debug/start-ai-conversation,
    #  debug/test-email-delivery, debug/test-appointment-confirmation-email, debug/test-import)
    try:
        from routes.debug_data_routes import register_debug_data_routes
        register_debug_data_routes(
            app, get_db, get_current_user, get_current_user_flexible,
            process_microsoft_email_to_dre=process_microsoft_email_to_dre,
            fetch_microsoft_emails=fetch_microsoft_emails,
            match_entity=match_entity,
            decrypt_token=decrypt_token,
            refresh_microsoft_token=refresh_microsoft_token,
            **kwargs
        )
        logger.info("✅ Debug data & email routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Debug data routes failed: {e}")

    # Extracted to routes/scorecard_routes.py
    # (GET /api/v1/scorecard - conversion metrics, funding totals, referral breakdown)

    # Extracted to routes/search_routes.py
    # (GET /api/v1/search/global - cross-entity search)

    # IMPORTANT: This route MUST be defined BEFORE /leads/{lead_id} to avoid route conflicts
    @app.delete("/api/v1/leads/bulk-delete")
    @app.post("/api/v1/leads/bulk-delete")
    async def bulk_delete_leads_v2(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Bulk delete multiple leads. Admin users, master user (id=1), or users with leads.delete_all permission can use this.
        """
        # Parse lead_ids from request body
        try:
            body = await request.json()
            # Handle both array format [1,2,3] and object format {"lead_ids": [1,2,3]}
            if isinstance(body, list):
                lead_ids = body
            elif isinstance(body, dict):
                lead_ids = body.get('lead_ids', body.get('ids', []))
            else:
                lead_ids = []
            lead_ids = [int(id) for id in lead_ids]  # Ensure integers
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid request body: {str(e)}")

        # PHASE 3: Check delete permission (delete or delete_all)
        is_master = current_user.id == 1 or current_user.email == 'admin@perenniaai.com'
        has_delete_permission = has_permission(current_user.id, 'leads.delete', db) or has_permission(current_user.id, 'leads.delete_all', db)

        if not (is_master or has_delete_permission):
            raise HTTPException(status_code=403, detail="Permission denied: leads.delete")

        if not lead_ids:
            raise HTTPException(status_code=400, detail="No lead IDs provided")

        deleted_count = 0
        errors = []

        # Get table list once
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        existing_tables = set(inspector.get_table_names())

        tables_to_clean = [
            ("activities", "lead_id"),
            ("tasks", "lead_id"),
            ("ai_tasks", "lead_id"),
            ("notes", "lead_id"),
            ("communications", "lead_id"),
            ("email_reconciliation_queue", "lead_id"),
            ("workflow_executions", "lead_id"),
            ("workflow_sla_instances", "lead_id"),
            ("workflow_sla_tasks", "lead_id"),
            ("lead_profiles", "lead_id"),
            ("circle_contacts", "lead_id"),
            ("notifications", "lead_id"),
            ("stage_history", "lead_id"),
            ("conversation_messages", "lead_id"),
            ("ai_conversation_messages", "lead_id"),
            ("incoming_data_events", "lead_id"),
            ("lead_source_tracking", "lead_id"),
            ("purl_events", "lead_id"),
            ("purl_workspaces", "lead_id"),
        ]

        for lead_id in lead_ids:
            # Use savepoint for each lead so failures don't cascade
            savepoint = db.begin_nested()
            try:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if not lead:
                    errors.append(f"Lead {lead_id} not found")
                    savepoint.rollback()
                    continue

                # Delete related records using raw SQL
                for table, column in tables_to_clean:
                    if table in existing_tables:
                        try:
                            db.execute(text(f"DELETE FROM {table} WHERE {column} = :lead_id"), {"lead_id": lead_id})
                        except Exception as te:
                            logger.warning(f"Error cleaning {table} for lead {lead_id}: {te}")

                # Unlink from loans instead of deleting
                if "loans" in existing_tables:
                    db.execute(text("UPDATE loans SET lead_id = NULL WHERE lead_id = :lead_id"), {"lead_id": lead_id})

                # Delete the lead
                db.delete(lead)
                savepoint.commit()  # Commit the savepoint
                deleted_count += 1

            except Exception as e:
                savepoint.rollback()  # Rollback only this lead's savepoint
                errors.append(f"Failed to delete lead {lead_id}: {str(e)}")

        # Final commit
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Final commit failed: {e}")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "errors": errors,
            "message": f"Successfully deleted {deleted_count} leads" + (f" with {len(errors)} errors" if errors else "")
        }


    @app.post("/api/v1/leads/bulk-update-status")
    async def bulk_update_lead_status(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Bulk update status/stage for multiple leads.
        Body: { "lead_ids": [1, 2, 3], "status": "Withdraw" }
        """
        logger.info(f"[bulk-update-status] Request received from user {current_user.id} ({current_user.email})")
        try:
            body = await request.json()
            logger.info(f"[bulk-update-status] Request body: {body}")
            lead_ids = body.get('lead_ids', body.get('ids', []))
            new_status = body.get('status', body.get('stage'))

            if isinstance(lead_ids, list) == False:
                lead_ids = [lead_ids]
            lead_ids = [int(id) for id in lead_ids]
            logger.info(f"[bulk-update-status] Parsed {len(lead_ids)} lead IDs, new_status={new_status}")
        except Exception as e:
            logger.error(f"[bulk-update-status] Failed to parse request: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid request body: {str(e)}")

        if not lead_ids:
            raise HTTPException(status_code=400, detail="No lead IDs provided")

        if not new_status:
            raise HTTPException(status_code=400, detail="No status provided")

        # PHASE 3: Check update permission (master users bypass)
        is_master = current_user.id == 1 or current_user.email == 'admin@perenniaai.com'
        if not is_master:
            has_update_permission = has_permission(current_user.id, 'leads.update', db) or has_permission(current_user.id, 'leads.update_all', db)
            if not has_update_permission:
                raise HTTPException(status_code=403, detail="Permission denied: leads.update")

        updated_count = 0
        errors = []

        for lead_id in lead_ids:
            try:
                # Apply permission filtering
                query = db.query(Lead).filter(Lead.id == lead_id)
                if not is_master:
                    query = filter_leads_by_permissions(query, current_user, db)
                lead = query.first()

                if not lead:
                    errors.append(f"Lead {lead_id} not found or access denied")
                    continue

                # Update the stage
                lead.stage = new_status
                lead.updated_at = datetime.utcnow()
                updated_count += 1

            except Exception as e:
                errors.append(f"Failed to update lead {lead_id}: {str(e)}")

        try:
            db.commit()
            logger.info(f"[bulk-update-status] Successfully committed. Updated {updated_count}, errors: {len(errors)}")
        except Exception as e:
            db.rollback()
            logger.error(f"[bulk-update-status] Failed to commit: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save changes: {str(e)}")

        result = {
            "success": True,
            "updated_count": updated_count,
            "new_status": new_status,
            "errors": errors,
            "message": f"Successfully updated {updated_count} leads to '{new_status}'" + (f" with {len(errors)} errors" if errors else "")
        }
        logger.info(f"[bulk-update-status] Returning result: {result}")
        return result


    @app.get("/api/v1/leads/{lead_id}")
    async def get_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        # Use the same permission filtering as the list endpoint
        query = db.query(Lead).filter(Lead.id == lead_id)
        query = filter_leads_by_permissions(query, current_user, db)
        lead = query.first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Handle stage value - it might be an enum or a string depending on DB content
        stage_value = None
        if lead.stage:
            stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

        # Return dict to avoid Pydantic validation issues with enum
        return {
            "id": lead.id,
            "name": lead.name,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "phone": lead.phone,
            "co_applicant_name": lead.co_applicant_name,
            "co_applicant_email": lead.co_applicant_email,
            "co_applicant_phone": lead.co_applicant_phone,
            "preferred_communication": lead.preferred_communication,
            "stage": stage_value,
            "source": lead.source,
            "ai_score": lead.ai_score,
            "sentiment": lead.sentiment,
            "next_action": lead.next_action,
            "preapproval_amount": lead.preapproval_amount,
            "credit_score": lead.credit_score,
            "loan_type": lead.loan_type,
            "notes": lead.notes,
            "owner_id": lead.owner_id,
            # Property Information
            "address": lead.address,
            "city": lead.city,
            "state": lead.state,
            "zip_code": lead.zip_code,
            "property_type": lead.property_type,
            "property_value": lead.property_value,
            "down_payment": lead.down_payment,
            # Financial Information
            "employment_status": lead.employment_status,
            "employer_name": getattr(lead, 'employer_name', None),
            "annual_income": lead.annual_income,
            "monthly_debts": lead.monthly_debts,
            "first_time_buyer": lead.first_time_buyer,
            # Metadata
            "user_metadata": getattr(lead, 'user_metadata', None),
            # Loan Details
            "loan_number": lead.loan_number,
            "loan_amount": lead.loan_amount,
            "interest_rate": lead.interest_rate,
            "loan_term": lead.loan_term,
            "apr": lead.apr,
            "points": lead.points,
            "lock_date": lead.lock_date.isoformat() if lead.lock_date else None,
            "lock_expiration": lead.lock_expiration.isoformat() if lead.lock_expiration else None,
            "closing_date": lead.closing_date.isoformat() if lead.closing_date else None,
            "lender": lead.lender,
            "loan_officer": lead.loan_officer,
            "processor": lead.processor,
            "underwriter": lead.underwriter,
            "appraisal_value": lead.appraisal_value,
            "ltv": lead.ltv,
            "dti": lead.dti,
            "cltv": lead.cltv,
            # Salesforce Sync Fields - Property Details
            "occupancy_type": lead.occupancy_type,
            "property_county": lead.property_county,
            "property_ownership_type": lead.property_ownership_type,
            "property_units": lead.property_units,
            # Salesforce Sync Fields - 1st Loan Financial Details
            "rate_type": lead.rate_type,
            "monthly_payment": lead.monthly_payment,
            "property_tax": lead.property_tax,
            "hazard_insurance": lead.hazard_insurance,
            "mortgage_insurance": lead.mortgage_insurance,
            "hoa_amount": lead.hoa_amount,
            "origination_fee": lead.origination_fee,
            "estimated_prepaid_interest": lead.estimated_prepaid_interest,
            "index_rate": lead.index_rate,
            "margin": lead.margin,
            # Salesforce Sync Fields - LTV/CLTV and Purpose
            "loan_purpose": lead.loan_purpose,
            "file_state": lead.file_state,
            # Salesforce Sync Fields - 2nd Loan Details
            "second_loan_amount": lead.second_loan_amount,
            "second_loan_rate": lead.second_loan_rate,
            "second_loan_payment": lead.second_loan_payment,
            # Salesforce Sync Fields - Present vs Proposed Housing
            "present_housing_expense": lead.present_housing_expense,
            "proposed_housing_expense": lead.proposed_housing_expense,
            "present_monthly_payment": lead.present_monthly_payment,
            "proposed_monthly_payment": lead.proposed_monthly_payment,
            # Timestamps
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            "stage_changed_at": lead.stage_changed_at.isoformat() if lead.stage_changed_at else None,
            # SLA Milestone Dates
            "lead_received_date": lead.lead_received_date.isoformat() if lead.lead_received_date else None,
            "first_contact_attempt_date": lead.first_contact_attempt_date.isoformat() if lead.first_contact_attempt_date else None,
            "first_contact_successful_date": lead.first_contact_successful_date.isoformat() if lead.first_contact_successful_date else None,
            "application_started_date": lead.application_started_date.isoformat() if lead.application_started_date else None,
            "application_completed_date": lead.application_completed_date.isoformat() if lead.application_completed_date else None,
            "preapproval_issued_date": lead.preapproval_issued_date.isoformat() if lead.preapproval_issued_date else None,
        }


    @app.get("/api/v1/leads/{lead_id}/documents")
    async def get_lead_documents(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """Get all documents associated with a lead"""
        # Check lead exists and user has access
        query = db.query(Lead).filter(Lead.id == lead_id)
        query = filter_leads_by_permissions(query, current_user, db)
        lead = query.first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Fetch documents for this lead
        documents = db.query(Document).filter(Document.borrower_id == lead_id, Document.status == "active").all()

        # Organize documents by category
        categorized = {
            "income_verification": [],
            "credit_reports": [],
            "property_documents": [],
            "disclosures_forms": [],
            "bank_statements": [],
            "other": [],
        }

        category_mapping = {
            "Income": "income_verification",
            "Credit": "credit_reports",
            "Property": "property_documents",
            "Disclosures": "disclosures_forms",
            "Assets": "bank_statements",
            "Miscellaneous": "other",
        }

        for doc in documents:
            doc_data = {
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "doc_type": doc.doc_type.value if hasattr(doc.doc_type, 'value') else str(doc.doc_type),
                "doc_category": doc.doc_category.value if doc.doc_category and hasattr(doc.doc_category, 'value') else str(doc.doc_category) if doc.doc_category else None,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "source": doc.source,
            }

            # Determine category
            cat_key = "other"
            if doc.doc_category:
                cat_value = doc.doc_category.value if hasattr(doc.doc_category, 'value') else str(doc.doc_category)
                cat_key = category_mapping.get(cat_value, "other")

            categorized[cat_key].append(doc_data)

        return {
            "lead_id": lead_id,
            "total_documents": len(documents),
            "documents": categorized,
        }


    @app.patch("/api/v1/leads/{lead_id}")
    async def update_lead(lead_id: int, lead_update: LeadUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        # Use the same permission filtering as the list endpoint
        query = db.query(Lead).filter(Lead.id == lead_id)
        query = filter_leads_by_permissions(query, current_user, db)
        lead = query.first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # PHASE 3: Check edit permission (edit_all or edit_own + ownership)
        check_resource_access(
            current_user.id,
            lead.owner_id,
            'leads.edit_all',
            'leads.edit_own',
            db
        )

        # Capture old status for workflow trigger
        old_status = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None

        for key, value in lead_update.dict(exclude_unset=True).items():
            setattr(lead, key, value)

        # Recalculate AI score
        lead.ai_score = calculate_lead_score(lead)
        lead.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(lead)
        logger.info(f"Lead updated: {lead.name}")

        # Trigger workflow if status changed
        new_status = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None
        if old_status != new_status and new_status:
            # Calculate duration in previous stage
            duration_days = None
            if lead.stage_changed_at:
                duration_days = (datetime.now(timezone.utc) - lead.stage_changed_at.replace(tzinfo=timezone.utc)).days

            # Track when stage changed for workflow day calculations
            lead.stage_changed_at = datetime.now(timezone.utc)
            lead.workflow_day = 0  # Reset workflow day counter

            # Record stage change in history
            stage_history = StageHistory(
                entity_type='lead',
                entity_id=lead.id,
                lead_id=lead.id,
                from_stage=old_status,
                to_stage=new_status,
                changed_at=datetime.now(timezone.utc),
                changed_by_id=current_user.id,
                duration_in_previous_stage=duration_days
            )
            db.add(stage_history)

            db.commit()
            db.refresh(lead)
            logger.info(f"Stage changed for lead {lead.id}: {old_status} → {new_status}, stage_changed_at updated, history recorded")

            try:
                # Create status change event
                status_change = LeadStatusChange(
                    lead_id=lead.id,
                    lead_name=lead.name,
                    lead_email=lead.email,
                    lead_phone=lead.phone,
                    old_status=old_status or "None",
                    new_status=new_status,
                    loan_officer_id=current_user.id,
                    loan_officer_name=current_user.full_name or current_user.email,
                    loan_officer_email=current_user.email,
                    loan_type=lead.loan_type if hasattr(lead, 'loan_type') else None,
                    loan_amount=lead.loan_amount if hasattr(lead, 'loan_amount') else None,
                    changed_at=datetime.now(timezone.utc)
                )

                # Process workflow
                workflow_engine = LeadWorkflowEngine(db)
                workflow_result = await workflow_engine.process_status_change(status_change)

                # Execute actions
                if workflow_result.get("actions"):
                    action_executor = WorkflowActionExecutor(db)
                    await action_executor.execute_actions(workflow_result["actions"])

                logger.info(f"✅ Workflow triggered for {lead.name}: {old_status} → {new_status} ({workflow_result.get('action_count', 0)} actions)")
            except Exception as e:
                logger.error(f"⚠️ Workflow error for lead {lead.id}: {e}")
                # Don't fail the update if workflow fails

            # Track SLA milestone for stage change
            try:
                track_lead_stage_change(db, lead.id, old_status, new_status, current_user.id)
                logger.info(f"SLA milestone tracked for lead {lead.id} stage change: {old_status} → {new_status}")
            except Exception as e:
                logger.warning(f"Failed to track SLA milestone for lead {lead.id}: {e}")

            # Fire lead status change triggers for automated outreach (nurture, etc.)
            try:
                from routes.automated_outreach_routes import execute_trigger, TriggerType
                asyncio.create_task(execute_trigger(
                    trigger_type=TriggerType.LEAD_STATUS_CHANGE,
                    lead_id=lead.id,
                    context={"old_status": old_status, "new_status": new_status},
                    db=db
                ))
                logger.info(f"Lead status change trigger fired for lead {lead.id}: {old_status} → {new_status}")
            except Exception as trigger_error:
                logger.error(f"Error firing lead status trigger: {trigger_error}")

        # Handle stage value - it might be an enum or a string depending on DB content
        stage_value = None
        if lead.stage:
            stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

        # Return dict to avoid Pydantic validation issues with enum
        return {
            "id": lead.id,
            "name": lead.name,
            "email": lead.email,
            "phone": lead.phone,
            "stage": stage_value,
            "source": lead.source,
            "ai_score": lead.ai_score,
            "sentiment": lead.sentiment,
            "next_action": lead.next_action,
            "preapproval_amount": lead.preapproval_amount,
            "credit_score": lead.credit_score,
            "loan_type": lead.loan_type,
            "notes": lead.notes,
            "owner_id": lead.owner_id,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        }

    @app.delete("/api/v1/leads/{lead_id}", status_code=204)
    async def delete_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        # PHASE 3: Check delete permission (master users bypass)
        is_master = current_user.id == 1 or current_user.email == 'admin@perenniaai.com'
        if not is_master:
            require_permission_or_403(current_user.id, 'leads.delete', db)

        # Use the same permission filtering as the list endpoint
        query = db.query(Lead).filter(Lead.id == lead_id)
        query = filter_leads_by_permissions(query, current_user, db)
        lead = query.first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_name = lead.name

        try:
            # Delete related records first using raw SQL connection
            # This avoids SQLAlchemy transaction issues
            from sqlalchemy import inspect

            # Get list of existing tables
            inspector = inspect(db.bind)
            existing_tables = set(inspector.get_table_names())

            # Define tables and their foreign key columns to lead
            tables_to_clean = [
                ("activities", "lead_id"),
                ("tasks", "lead_id"),
                ("ai_tasks", "lead_id"),
                ("notes", "lead_id"),
                ("communications", "lead_id"),
                ("email_reconciliation_queue", "lead_id"),
                ("workflow_executions", "lead_id"),
                ("lead_profiles", "lead_id"),
                ("circle_contacts", "lead_id"),
                ("notifications", "lead_id"),
                ("stage_history", "lead_id"),
                ("conversation_messages", "lead_id"),
                ("ai_conversation_messages", "lead_id"),
                ("incoming_data_events", "lead_id"),
            ]

            # Build a single SQL statement that deletes from all existing tables
            delete_sqls = []
            for table, column in tables_to_clean:
                if table in existing_tables:
                    delete_sqls.append(f"DELETE FROM {table} WHERE {column} = {lead_id}")

            # Nullify loan references if loans table exists
            if "loans" in existing_tables:
                delete_sqls.append(f"UPDATE loans SET lead_id = NULL WHERE lead_id = {lead_id}")

            # Add the final lead delete
            delete_sqls.append(f"DELETE FROM leads WHERE id = {lead_id}")

            # Execute all as a single raw SQL transaction
            raw_conn = db.bind.raw_connection()
            try:
                cursor = raw_conn.cursor()
                for sql in delete_sqls:
                    try:
                        cursor.execute(sql)
                    except Exception as e:
                        logger.debug(f"Delete statement skipped: {sql[:50]}... - {e}")
                        # Continue with next statement
                raw_conn.commit()
            finally:
                raw_conn.close()

            logger.info(f"Lead deleted: {lead_name}")
            return None

        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to delete lead: {str(e)}")


    @app.post("/api/v1/leads/claim-orphans")
    async def claim_orphan_leads(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Claim all orphan leads (leads with no owner) and assign them to the current user.
        This fixes the AI chat issue where leads aren't visible because they have no owner.
        Also claims loans that don't belong to any valid user.
        """
        try:
            # Update leads with NULL owner_id to current user
            result = db.execute(
                text("UPDATE leads SET owner_id = :user_id WHERE owner_id IS NULL"),
                {"user_id": current_user.id}
            )
            leads_claimed = result.rowcount

            # Update loans with NULL loan_officer_id OR loan_officer_id not matching any user
            # This catches loans with invalid/orphaned loan_officer_ids
            result = db.execute(
                text("""
                    UPDATE loans
                    SET loan_officer_id = :user_id
                    WHERE loan_officer_id IS NULL
                       OR loan_officer_id NOT IN (SELECT id FROM users)
                       OR loan_officer_id != :user_id
                """),
                {"user_id": current_user.id}
            )
            loans_claimed = result.rowcount

            db.commit()

            # Get totals
            result = db.execute(
                text("""
                    SELECT
                        (SELECT COUNT(*) FROM leads WHERE owner_id = :user_id) as leads,
                        (SELECT COUNT(*) FROM loans WHERE loan_officer_id = :user_id) as loans
                """),
                {"user_id": current_user.id}
            )
            totals = result.fetchone()

            logger.info(f"User {current_user.email} claimed {leads_claimed} leads, {loans_claimed} loans")

            return {
                "success": True,
                "message": f"Successfully claimed {leads_claimed} leads and {loans_claimed} loans",
                "claimed": {
                    "leads": leads_claimed,
                    "loans": loans_claimed
                },
                "totals": {
                    "leads": totals[0],
                    "loans": totals[1]
                }
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error claiming orphan leads: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to claim orphan leads: {str(e)}")


    # Extracted to routes/mum_activity_routes.py
    # (calculate-referral-scores, convert-to-mum, mum-clients CRUD, activities CRUD)

    # ============================================================================
    # DATABASE INITIALIZATION
    # ============================================================================

    # Configuration: Skip auto-create tables in production
    # Tables should be managed via Alembic migrations in production
    AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true"


    def init_db():
        """
        Initialize database tables.

        In production (ENVIRONMENT=production), this skips Base.metadata.create_all()
        to prevent accidental schema changes. Use Alembic migrations instead.

        Set AUTO_CREATE_TABLES=true to force table creation (development only).
        """
        try:
            # Import models to register them with Base before create_all
            import salesforce_integration_models  # Salesforce integration tables

            # Skip auto-create in production unless explicitly enabled
            if ENVIRONMENT == "production" and not AUTO_CREATE_TABLES:
                logger.info("ℹ️ Skipping Base.metadata.create_all() in production - use Alembic migrations")
            else:
                Base.metadata.create_all(bind=engine)
                logger.info("✅ Database tables created successfully")

            # Explicitly create Salesforce integration tables if they don't exist
            # Use individual transactions for each table to ensure partial success
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS integration_profiles (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                            status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                            access_token_encrypted TEXT,
                            refresh_token_encrypted TEXT,
                            instance_url TEXT,
                            sf_org_id VARCHAR(100),
                            sf_user_id VARCHAR(100),
                            sf_username VARCHAR(255),
                            connected_at TIMESTAMP,
                            last_sync_at TIMESTAMP,
                            last_error TEXT,
                            field_map_version INTEGER DEFAULT 1,
                            sync_enabled BOOLEAN DEFAULT TRUE,
                            sync_interval_minutes INTEGER DEFAULT 15,
                            sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, provider)
                        )
                    """))
                    conn.commit()
                    logger.info("✅ integration_profiles table created/verified")
            except Exception as e:
                logger.warning(f"integration_profiles table creation: {e}")

            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS oauth_states (
                            id SERIAL PRIMARY KEY,
                            state_token VARCHAR(255) UNIQUE NOT NULL,
                            user_id INTEGER NOT NULL,
                            provider VARCHAR(50) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP NOT NULL,
                            used BOOLEAN DEFAULT FALSE,
                            return_url TEXT,
                            state_metadata JSONB
                        )
                    """))
                    conn.commit()
                    logger.info("✅ oauth_states table created/verified")
            except Exception as e:
                logger.warning(f"oauth_states table creation: {e}")

            # Create oauth_pkce_store table for PKCE verifier storage
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS oauth_pkce_store (
                            id SERIAL PRIMARY KEY,
                            state VARCHAR(255) UNIQUE NOT NULL,
                            code_verifier TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("✅ oauth_pkce_store table created/verified")
            except Exception as e:
                logger.warning(f"oauth_pkce_store table creation: {e}")

            # Run schema migrations for existing tables (PostgreSQL only)
            # Note: SQLite tables are already created with all columns via Base.metadata.create_all()
            try:
                # Only run PostgreSQL-specific migrations if using PostgreSQL
                if not DATABASE_URL.startswith("sqlite"):
                    with engine.connect() as conn:
                        # Add email_verified column if it doesn't exist
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='users' AND column_name='email_verified'
                                ) THEN
                                    ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
                                END IF;
                            END $$;
                        """))

                        # Add title column to users table if it doesn't exist (for job title/position)
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='users' AND column_name='title'
                                ) THEN
                                    ALTER TABLE users ADD COLUMN title TEXT;
                                END IF;
                            END $$;
                        """))

                        # Add company_logo_url column to users table if it doesn't exist
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='users' AND column_name='company_logo_url'
                                ) THEN
                                    ALTER TABLE users ADD COLUMN company_logo_url TEXT;
                                END IF;
                            END $$;
                        """))

                        # Add headshot_url column to users table if it doesn't exist
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='users' AND column_name='headshot_url'
                                ) THEN
                                    ALTER TABLE users ADD COLUMN headshot_url TEXT;
                                END IF;
                            END $$;
                        """))

                        # Add team_name column to users table if it doesn't exist
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='users' AND column_name='team_name'
                                ) THEN
                                    ALTER TABLE users ADD COLUMN team_name TEXT;
                                END IF;
                            END $$;
                        """))

                        conn.commit()
                        logger.info("✅ User profile columns added/verified")

                        # Add new Lead columns if they don't exist
                        conn.execute(text("""
                            DO $$
                        BEGIN
                            -- Property Information
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address') THEN
                                ALTER TABLE leads ADD COLUMN address VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='city') THEN
                                ALTER TABLE leads ADD COLUMN city VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='state') THEN
                                ALTER TABLE leads ADD COLUMN state VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='zip_code') THEN
                                ALTER TABLE leads ADD COLUMN zip_code VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_type') THEN
                                ALTER TABLE leads ADD COLUMN property_type VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_value') THEN
                                ALTER TABLE leads ADD COLUMN property_value FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='down_payment') THEN
                                ALTER TABLE leads ADD COLUMN down_payment FLOAT;
                            END IF;
                            -- Financial Information
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_status') THEN
                                ALTER TABLE leads ADD COLUMN employment_status VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='annual_income') THEN
                                ALTER TABLE leads ADD COLUMN annual_income FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='monthly_debts') THEN
                                ALTER TABLE leads ADD COLUMN monthly_debts FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='first_time_buyer') THEN
                                ALTER TABLE leads ADD COLUMN first_time_buyer BOOLEAN DEFAULT FALSE;
                            END IF;
                            -- Loan Information
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_number') THEN
                                ALTER TABLE leads ADD COLUMN loan_number VARCHAR;
                            END IF;
                            -- Loan Details
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_amount') THEN
                                ALTER TABLE leads ADD COLUMN loan_amount FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='interest_rate') THEN
                                ALTER TABLE leads ADD COLUMN interest_rate FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_term') THEN
                                ALTER TABLE leads ADD COLUMN loan_term INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='apr') THEN
                                ALTER TABLE leads ADD COLUMN apr FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='points') THEN
                                ALTER TABLE leads ADD COLUMN points FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_date') THEN
                                ALTER TABLE leads ADD COLUMN lock_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_expiration') THEN
                                ALTER TABLE leads ADD COLUMN lock_expiration TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='closing_date') THEN
                                ALTER TABLE leads ADD COLUMN closing_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lender') THEN
                                ALTER TABLE leads ADD COLUMN lender VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_officer') THEN
                                ALTER TABLE leads ADD COLUMN loan_officer VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='processor') THEN
                                ALTER TABLE leads ADD COLUMN processor VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='underwriter') THEN
                                ALTER TABLE leads ADD COLUMN underwriter VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='appraisal_value') THEN
                                ALTER TABLE leads ADD COLUMN appraisal_value FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='ltv') THEN
                                ALTER TABLE leads ADD COLUMN ltv FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='dti') THEN
                                ALTER TABLE leads ADD COLUMN dti FLOAT;
                            END IF;
                            -- Lead tracking date columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='application_started_date') THEN
                                ALTER TABLE leads ADD COLUMN application_started_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='application_completed_date') THEN
                                ALTER TABLE leads ADD COLUMN application_completed_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='credit_pulled_date') THEN
                                ALTER TABLE leads ADD COLUMN credit_pulled_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='preapproval_issued_date') THEN
                                ALTER TABLE leads ADD COLUMN preapproval_issued_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_address') THEN
                                ALTER TABLE leads ADD COLUMN property_address VARCHAR;
                            END IF;
                            -- Buying timeline and risk profile (enum as VARCHAR for flexibility)
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='buying_timeline_category') THEN
                                ALTER TABLE leads ADD COLUMN buying_timeline_category VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='borrower_risk_profile') THEN
                                ALTER TABLE leads ADD COLUMN borrower_risk_profile VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='target_payment') THEN
                                ALTER TABLE leads ADD COLUMN target_payment FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='expected_purchase_date') THEN
                                ALTER TABLE leads ADD COLUMN expected_purchase_date TIMESTAMP;
                            END IF;
                            -- Referral scoring columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_score') THEN
                                ALTER TABLE leads ADD COLUMN referral_score INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_source_score') THEN
                                ALTER TABLE leads ADD COLUMN referral_source_score INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_referral_flag') THEN
                                ALTER TABLE leads ADD COLUMN employment_referral_flag BOOLEAN DEFAULT FALSE;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='manager_flag') THEN
                                ALTER TABLE leads ADD COLUMN manager_flag BOOLEAN DEFAULT FALSE;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employees_managed') THEN
                                ALTER TABLE leads ADD COLUMN employees_managed INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='leadership_level') THEN
                                ALTER TABLE leads ADD COLUMN leadership_level VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='company_size') THEN
                                ALTER TABLE leads ADD COLUMN company_size VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employer_name') THEN
                                ALTER TABLE leads ADD COLUMN employer_name VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='industry') THEN
                                ALTER TABLE leads ADD COLUMN industry VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='circle_of_cash_flow_map') THEN
                                ALTER TABLE leads ADD COLUMN circle_of_cash_flow_map JSON;
                            END IF;
                            -- Workflow columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='current_workflow_id') THEN
                                ALTER TABLE leads ADD COLUMN current_workflow_id INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='workflow_day') THEN
                                ALTER TABLE leads ADD COLUMN workflow_day INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='last_workflow_action') THEN
                                ALTER TABLE leads ADD COLUMN last_workflow_action TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='nurture_month') THEN
                                ALTER TABLE leads ADD COLUMN nurture_month INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='user_metadata') THEN
                                ALTER TABLE leads ADD COLUMN user_metadata JSON;
                            END IF;
                        END $$;
                        """))

                        # Add email_intake_id to tasks table for document intake
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='email_intake_id') THEN
                                    ALTER TABLE tasks ADD COLUMN email_intake_id INTEGER;
                                END IF;
                            END $$;
                        """))

                        # Create email_intakes table for document intake
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS email_intakes (
                                id SERIAL PRIMARY KEY,
                                message_id VARCHAR UNIQUE,
                                from_address VARCHAR NOT NULL,
                                from_name VARCHAR,
                                subject VARCHAR,
                                body_preview TEXT,
                                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                matched_loan_id INTEGER REFERENCES loans(id),
                                matched_lead_id INTEGER REFERENCES leads(id),
                                match_status VARCHAR DEFAULT 'pending',
                                match_confidence FLOAT,
                                match_method VARCHAR,
                                matched_by_user_id INTEGER REFERENCES users(id),
                                matched_at TIMESTAMP,
                                processing_status VARCHAR DEFAULT 'pending',
                                processing_started_at TIMESTAMP,
                                processing_completed_at TIMESTAMP,
                                processing_error TEXT,
                                raw_email_data JSON,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_email_intakes_match_status ON email_intakes(match_status);
                            CREATE INDEX IF NOT EXISTS ix_email_intakes_received_at ON email_intakes(received_at);
                        """))

                        # Create attachment_intakes table
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS attachment_intakes (
                                id SERIAL PRIMARY KEY,
                                email_intake_id INTEGER NOT NULL REFERENCES email_intakes(id),
                                filename VARCHAR NOT NULL,
                                content_type VARCHAR,
                                file_size INTEGER,
                                storage_path VARCHAR,
                                storage_url VARCHAR,
                                classification VARCHAR,
                                classification_confidence FLOAT,
                                extracted_data JSON,
                                processing_status VARCHAR DEFAULT 'pending',
                                processing_error TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_attachment_intakes_email_intake_id ON attachment_intakes(email_intake_id);
                        """))

                        # Create classified_documents table
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS classified_documents (
                                id SERIAL PRIMARY KEY,
                                loan_id INTEGER REFERENCES loans(id),
                                lead_id INTEGER REFERENCES leads(id),
                                category VARCHAR NOT NULL,
                                sub_category VARCHAR,
                                document_name VARCHAR NOT NULL,
                                file_path VARCHAR,
                                file_url VARCHAR,
                                file_size INTEGER,
                                mime_type VARCHAR,
                                upload_source VARCHAR DEFAULT 'manual',
                                source_email_intake_id INTEGER REFERENCES email_intakes(id),
                                source_attachment_id INTEGER REFERENCES attachment_intakes(id),
                                extracted_data JSON,
                                ai_classification_confidence FLOAT,
                                verified_by_user_id INTEGER REFERENCES users(id),
                                verified_at TIMESTAMP,
                                expiration_date DATE,
                                notes TEXT,
                                version INTEGER DEFAULT 1,
                                is_current BOOLEAN DEFAULT TRUE,
                                created_by_id INTEGER REFERENCES users(id),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_classified_documents_loan_id ON classified_documents(loan_id);
                            CREATE INDEX IF NOT EXISTS ix_classified_documents_category ON classified_documents(category);
                        """))

                        # Add new Loan columns for rate lock intelligence, appraisal, etc.
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                -- Appraisal tracking columns
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_ordered_date') THEN
                                    ALTER TABLE loans ADD COLUMN appraisal_ordered_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_scheduled_date') THEN
                                    ALTER TABLE loans ADD COLUMN appraisal_scheduled_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_completed_date') THEN
                                    ALTER TABLE loans ADD COLUMN appraisal_completed_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_value') THEN
                                    ALTER TABLE loans ADD COLUMN appraisal_value FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_expiration_date') THEN
                                    ALTER TABLE loans ADD COLUMN lock_expiration_date TIMESTAMP;
                                END IF;
                                -- Rate Lock Intelligence columns
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_status') THEN
                                    ALTER TABLE loans ADD COLUMN rate_lock_status VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_recommendation') THEN
                                    ALTER TABLE loans ADD COLUMN rate_lock_recommendation VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_term_days') THEN
                                    ALTER TABLE loans ADD COLUMN lock_term_days INTEGER;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='float_down_available') THEN
                                    ALTER TABLE loans ADD COLUMN float_down_available BOOLEAN DEFAULT FALSE;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='float_down_terms') THEN
                                    ALTER TABLE loans ADD COLUMN float_down_terms VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='extension_cost_estimate') THEN
                                    ALTER TABLE loans ADD COLUMN extension_cost_estimate FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='volatility_score') THEN
                                    ALTER TABLE loans ADD COLUMN volatility_score INTEGER DEFAULT 50;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='borrower_risk_profile') THEN
                                    ALTER TABLE loans ADD COLUMN borrower_risk_profile VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_score') THEN
                                    ALTER TABLE loans ADD COLUMN lock_score INTEGER;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_decision_date') THEN
                                    ALTER TABLE loans ADD COLUMN lock_decision_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_decision_notes') THEN
                                    ALTER TABLE loans ADD COLUMN lock_decision_notes TEXT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_rate_check') THEN
                                    ALTER TABLE loans ADD COLUMN last_rate_check TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_history') THEN
                                    ALTER TABLE loans ADD COLUMN rate_lock_history JSON;
                                END IF;
                                -- Property and workflow columns
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_city') THEN
                                    ALTER TABLE loans ADD COLUMN property_city VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_state') THEN
                                    ALTER TABLE loans ADD COLUMN property_state VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_zip') THEN
                                    ALTER TABLE loans ADD COLUMN property_zip VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lender') THEN
                                    ALTER TABLE loans ADD COLUMN lender VARCHAR;
                                END IF;
                                -- Milestone dates
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='initial_disclosures_sent_date') THEN
                                    ALTER TABLE loans ADD COLUMN initial_disclosures_sent_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='initial_disclosures_signed_date') THEN
                                    ALTER TABLE loans ADD COLUMN initial_disclosures_signed_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='cd_received_signed_date') THEN
                                    ALTER TABLE loans ADD COLUMN cd_received_signed_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='final_closing_package_sent_date') THEN
                                    ALTER TABLE loans ADD COLUMN final_closing_package_sent_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='contract_received_date') THEN
                                    ALTER TABLE loans ADD COLUMN contract_received_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_estimate_sent_date') THEN
                                    ALTER TABLE loans ADD COLUMN loan_estimate_sent_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='conditional_approval_date') THEN
                                    ALTER TABLE loans ADD COLUMN conditional_approval_date TIMESTAMP;
                                END IF;
                                -- AMR tracking
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_amr_date') THEN
                                    ALTER TABLE loans ADD COLUMN last_amr_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='next_amr_date') THEN
                                    ALTER TABLE loans ADD COLUMN next_amr_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='refi_opportunity_score') THEN
                                    ALTER TABLE loans ADD COLUMN refi_opportunity_score INTEGER;
                                END IF;
                                -- Workflow columns
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='current_workflow_id') THEN
                                    ALTER TABLE loans ADD COLUMN current_workflow_id INTEGER;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_workflow_action') THEN
                                    ALTER TABLE loans ADD COLUMN last_workflow_action TIMESTAMP;
                                END IF;
                                -- Team member fields
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_officer_name') THEN
                                    ALTER TABLE loans ADD COLUMN loan_officer_name VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_officer_email') THEN
                                    ALTER TABLE loans ADD COLUMN loan_officer_email VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='processor_email') THEN
                                    ALTER TABLE loans ADD COLUMN processor_email VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='underwriter_email') THEN
                                    ALTER TABLE loans ADD COLUMN underwriter_email VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='closer') THEN
                                    ALTER TABLE loans ADD COLUMN closer VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='closer_email') THEN
                                    ALTER TABLE loans ADD COLUMN closer_email VARCHAR;
                                END IF;
                            END $$;
                        """))

                        # Create api_keys table if it doesn't exist
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS api_keys (
                                id SERIAL PRIMARY KEY,
                                key VARCHAR UNIQUE NOT NULL,
                                name VARCHAR NOT NULL,
                                user_id INTEGER NOT NULL REFERENCES users(id),
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                last_used_at TIMESTAMP
                            );
                        """))
                        conn.execute(text("""
                            CREATE INDEX IF NOT EXISTS ix_api_keys_key ON api_keys(key);
                        """))

                        # Add missing columns to referral_partners table
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='name') THEN
                                    ALTER TABLE referral_partners ADD COLUMN name VARCHAR NOT NULL DEFAULT 'Unknown';
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='company') THEN
                                    ALTER TABLE referral_partners ADD COLUMN company VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='type') THEN
                                    ALTER TABLE referral_partners ADD COLUMN type VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='phone') THEN
                                    ALTER TABLE referral_partners ADD COLUMN phone VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='email') THEN
                                    ALTER TABLE referral_partners ADD COLUMN email VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='referrals_in') THEN
                                    ALTER TABLE referral_partners ADD COLUMN referrals_in INTEGER DEFAULT 0;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='referrals_out') THEN
                                    ALTER TABLE referral_partners ADD COLUMN referrals_out INTEGER DEFAULT 0;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='closed_loans') THEN
                                    ALTER TABLE referral_partners ADD COLUMN closed_loans INTEGER DEFAULT 0;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='volume') THEN
                                    ALTER TABLE referral_partners ADD COLUMN volume FLOAT DEFAULT 0.0;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='reciprocity_score') THEN
                                    ALTER TABLE referral_partners ADD COLUMN reciprocity_score FLOAT DEFAULT 0.0;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='status') THEN
                                    ALTER TABLE referral_partners ADD COLUMN status VARCHAR DEFAULT 'active';
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='loyalty_tier') THEN
                                    ALTER TABLE referral_partners ADD COLUMN loyalty_tier VARCHAR DEFAULT 'bronze';
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='last_interaction') THEN
                                    ALTER TABLE referral_partners ADD COLUMN last_interaction TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='notes') THEN
                                    ALTER TABLE referral_partners ADD COLUMN notes TEXT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='created_at') THEN
                                    ALTER TABLE referral_partners ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                                END IF;
                            END $$;
                        """))

                        # Add missing columns to leads table
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_name') THEN
                                    ALTER TABLE leads ADD COLUMN co_applicant_name VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_email') THEN
                                    ALTER TABLE leads ADD COLUMN co_applicant_email VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_phone') THEN
                                    ALTER TABLE leads ADD COLUMN co_applicant_phone VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_officer') THEN
                                    ALTER TABLE leads ADD COLUMN loan_officer VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='processor') THEN
                                    ALTER TABLE leads ADD COLUMN processor VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='underwriter') THEN
                                    ALTER TABLE leads ADD COLUMN underwriter VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_number') THEN
                                    ALTER TABLE leads ADD COLUMN loan_number VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lender') THEN
                                    ALTER TABLE leads ADD COLUMN lender VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_date') THEN
                                    ALTER TABLE leads ADD COLUMN lock_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_expiration') THEN
                                    ALTER TABLE leads ADD COLUMN lock_expiration TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='closing_date') THEN
                                    ALTER TABLE leads ADD COLUMN closing_date TIMESTAMP;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='apr') THEN
                                    ALTER TABLE leads ADD COLUMN apr FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='points') THEN
                                    ALTER TABLE leads ADD COLUMN points FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='user_metadata') THEN
                                    ALTER TABLE leads ADD COLUMN user_metadata JSON;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address') THEN
                                    ALTER TABLE leads ADD COLUMN address VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='city') THEN
                                    ALTER TABLE leads ADD COLUMN city VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='state') THEN
                                    ALTER TABLE leads ADD COLUMN state VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='zip_code') THEN
                                    ALTER TABLE leads ADD COLUMN zip_code VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_type') THEN
                                    ALTER TABLE leads ADD COLUMN property_type VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_value') THEN
                                    ALTER TABLE leads ADD COLUMN property_value FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='down_payment') THEN
                                    ALTER TABLE leads ADD COLUMN down_payment FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_status') THEN
                                    ALTER TABLE leads ADD COLUMN employment_status VARCHAR;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='annual_income') THEN
                                    ALTER TABLE leads ADD COLUMN annual_income FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='monthly_debts') THEN
                                    ALTER TABLE leads ADD COLUMN monthly_debts FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='first_time_buyer') THEN
                                    ALTER TABLE leads ADD COLUMN first_time_buyer BOOLEAN DEFAULT FALSE;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_amount') THEN
                                    ALTER TABLE leads ADD COLUMN loan_amount FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='interest_rate') THEN
                                    ALTER TABLE leads ADD COLUMN interest_rate FLOAT;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_term') THEN
                                    ALTER TABLE leads ADD COLUMN loan_term INTEGER;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_partner_id') THEN
                                    ALTER TABLE leads ADD COLUMN referral_partner_id INTEGER;
                                END IF;
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='updated_at') THEN
                                    ALTER TABLE leads ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                                END IF;
                            END $$;
                        """))

                        # Create user_permissions table if it doesn't exist
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS user_permissions (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                                permission_key VARCHAR(255) NOT NULL,
                                granted BOOLEAN DEFAULT TRUE,
                                granted_by INTEGER REFERENCES users(id),
                                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                expires_at TIMESTAMP,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
                            );
                            CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id);
                            CREATE INDEX IF NOT EXISTS idx_user_permissions_composite ON user_permissions(user_id, permission_key, granted);
                        """))

                        # Add all missing enum values to loanstage type
                        # Must use raw connection with autocommit - ALTER TYPE ADD VALUE cannot run in a transaction
                        try:
                            raw_conn = engine.raw_connection()
                            raw_conn.set_isolation_level(0)  # AUTOCOMMIT
                            raw_cursor = raw_conn.cursor()
                            for loanstage_val in [
                                "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
                                "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
                                "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
                                "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
                                "CANCELLED", "DENIED", "DEAD", "NURTURE",
                                "WITHDRAWN", "DOES_NOT_QUALIFY", "Docs Out",
                            ]:
                                try:
                                    raw_cursor.execute(f"ALTER TYPE loanstage ADD VALUE IF NOT EXISTS '{loanstage_val}'")
                                except Exception:
                                    pass
                            raw_cursor.close()
                            raw_conn.close()
                            logger.info("✅ Ensured all loanstage enum values exist")
                        except Exception as enum_e:
                            logger.warning(f"⚠️ loanstage enum migration: {enum_e}")

                        # Add role_responsibilities column for dynamic workflow roles
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_day_configs' AND column_name='role_responsibilities'
                                ) THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN role_responsibilities JSONB DEFAULT '{}'::jsonb;
                                END IF;
                            END $$;
                        """))

                        # Add role_id column to workflow_role_assignments for dynamic roles
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_role_assignments' AND column_name='role_id'
                                ) THEN
                                    ALTER TABLE workflow_role_assignments ADD COLUMN role_id INTEGER REFERENCES onboarding_roles(id);
                                END IF;
                            END $$;
                        """))

                        # Make the legacy 'role' column nullable for dynamic role support
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                ALTER TABLE workflow_role_assignments ALTER COLUMN role DROP NOT NULL;
                            EXCEPTION
                                WHEN others THEN NULL;
                            END $$;
                        """))

                        # Add AM/PM communication method columns for Lead Purchase workflow
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                -- Add phone_am_enabled column
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_day_configs' AND column_name='phone_am_enabled'
                                ) THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN phone_am_enabled BOOLEAN DEFAULT FALSE;
                                END IF;
                                -- Add phone_pm_enabled column
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_day_configs' AND column_name='phone_pm_enabled'
                                ) THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN phone_pm_enabled BOOLEAN DEFAULT FALSE;
                                END IF;
                                -- Add text_am_enabled column
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_day_configs' AND column_name='text_am_enabled'
                                ) THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN text_am_enabled BOOLEAN DEFAULT FALSE;
                                END IF;
                                -- Add text_pm_enabled column
                                IF NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_name='workflow_day_configs' AND column_name='text_pm_enabled'
                                ) THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN text_pm_enabled BOOLEAN DEFAULT FALSE;
                                END IF;
                            END $$;
                        """))

                        conn.commit()
                        logger.info("✅ Schema migrations applied (PostgreSQL)")

                        # Create telephony tables if they don't exist
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS agent_telephony_settings (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                                cell_phone VARCHAR,
                                business_caller_id VARCHAR,
                                dialer_enabled BOOLEAN DEFAULT TRUE,
                                max_calls_per_day INTEGER DEFAULT 200,
                                max_concurrent_sessions INTEGER DEFAULT 1,
                                auto_advance BOOLEAN DEFAULT TRUE,
                                pause_between_calls INTEGER DEFAULT 3,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );

                            CREATE TABLE IF NOT EXISTS verified_caller_ids (
                                id SERIAL PRIMARY KEY,
                                phone_number VARCHAR UNIQUE NOT NULL,
                                friendly_name VARCHAR,
                                verification_status VARCHAR DEFAULT 'pending',
                                twilio_sid VARCHAR,
                                user_id INTEGER REFERENCES users(id),
                                verified_at TIMESTAMP,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );

                            CREATE TABLE IF NOT EXISTS contact_dnc_status (
                                id SERIAL PRIMARY KEY,
                                phone_number VARCHAR UNIQUE NOT NULL,
                                reason VARCHAR,
                                added_by_id INTEGER REFERENCES users(id),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_dnc_phone ON contact_dnc_status(phone_number);

                            DROP TABLE IF EXISTS active_calls;
                            CREATE TABLE IF NOT EXISTS active_calls (
                                id SERIAL PRIMARY KEY,
                                contact_phone VARCHAR NOT NULL,
                                agent_id INTEGER REFERENCES users(id),
                                call_sid VARCHAR,
                                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                expires_at TIMESTAMP NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS idx_active_calls_phone ON active_calls(contact_phone);

                            CREATE TABLE IF NOT EXISTS call_logs (
                                id SERIAL PRIMARY KEY,
                                agent_id INTEGER REFERENCES users(id),
                                contact_phone VARCHAR NOT NULL,
                                contact_name VARCHAR,
                                lead_id INTEGER,
                                loan_id INTEGER,
                                referral_partner_id INTEGER,
                                mum_client_id INTEGER,
                                session_id INTEGER,
                                session_task_id INTEGER,
                                call_sid VARCHAR,
                                caller_id_used VARCHAR,
                                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                end_time TIMESTAMP,
                                duration_seconds INTEGER,
                                outcome VARCHAR,
                                failure_reason VARCHAR,
                                disposition VARCHAR,
                                notes TEXT,
                                ai_note_summary TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );

                            -- Add missing columns to existing call_logs table
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS referral_partner_id INTEGER;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS mum_client_id INTEGER;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_id INTEGER;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_task_id INTEGER;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS caller_id_used VARCHAR;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS failure_reason VARCHAR;
                            ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                            -- Migrate old column data if they exist
                            UPDATE call_logs SET start_time = started_at WHERE start_time IS NULL AND started_at IS NOT NULL;
                            UPDATE call_logs SET end_time = ended_at WHERE end_time IS NULL AND ended_at IS NOT NULL;
                        """))
                        conn.commit()
                        logger.info("✅ Telephony tables created/verified")

                        # Add concierge_responsible column to workflow_day_configs
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='concierge_responsible') THEN
                                        ALTER TABLE workflow_day_configs ADD COLUMN concierge_responsible BOOLEAN DEFAULT FALSE;
                                    END IF;
                                END IF;
                            END $$;
                        """))
                        conn.commit()
                        logger.info("✅ Workflow concierge_responsible column added")

                        # Add weekly task scheduling columns to workflow_day_configs
                        # These support recurring tasks like Monday Weekly Updates
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                                    -- repeat_weekly: Flag to mark task as weekly recurring
                                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_weekly') THEN
                                        ALTER TABLE workflow_day_configs ADD COLUMN repeat_weekly BOOLEAN DEFAULT FALSE;
                                    END IF;
                                    -- repeat_day_of_week: Which day to repeat (0=Monday, 6=Sunday)
                                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_day_of_week') THEN
                                        ALTER TABLE workflow_day_configs ADD COLUMN repeat_day_of_week INTEGER;
                                    END IF;
                                    -- repeat_until_status: JSON array of statuses that stop the recurrence
                                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_until_status') THEN
                                        ALTER TABLE workflow_day_configs ADD COLUMN repeat_until_status JSONB DEFAULT '[]'::jsonb;
                                    END IF;
                                END IF;
                            END $$;
                        """))
                        conn.commit()
                        logger.info("✅ Weekly task scheduling columns added to workflow_day_configs")

                        # Add concierge to TaskResponsibility enum type
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                -- Check if taskresponsibility enum type exists and add concierge value
                                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskresponsibility') THEN
                                    IF NOT EXISTS (
                                        SELECT 1 FROM pg_enum WHERE enumlabel = 'concierge'
                                        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'taskresponsibility')
                                    ) THEN
                                        ALTER TYPE taskresponsibility ADD VALUE IF NOT EXISTS 'concierge';
                                    END IF;
                                END IF;
                            EXCEPTION
                                WHEN duplicate_object THEN NULL;
                            END $$;
                        """))
                        conn.commit()
                        logger.info("✅ TaskResponsibility enum updated with concierge")

                        # Fix invalid Application stage values
                        result = conn.execute(text("""
                            UPDATE leads
                            SET stage = 'Application'
                            WHERE stage = 'Application'
                        """))
                        if result.rowcount > 0:
                            logger.info(f"✅ Fixed {result.rowcount} leads with invalid Application stage")

                        # Fix null stages - set to New
                        result2 = conn.execute(text("""
                            UPDATE leads
                            SET stage = 'New'
                            WHERE stage IS NULL
                        """))
                        if result2.rowcount > 0:
                            logger.info(f"✅ Fixed {result2.rowcount} leads with null stage")

                        conn.commit()
            except Exception as e:
                logger.warning(f"⚠️ Schema migration note: {e}")

            # Run comprehensive column migration for all missing columns
            try:
                from migrations.add_all_missing_columns import run_migration
                run_migration()
                logger.info("✅ Comprehensive column migration completed")
            except Exception as e:
                logger.warning(f"⚠️ Comprehensive migration note: {e}")

            return True
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False

    def create_sample_data(db: Session):
        """Create sample data for testing"""
        try:
            # Check if data already exists - check for both demo and admin users
            existing_demo = db.query(User).filter(User.email == "admin@perenniaai.com").first()
            existing_admin = db.query(User).filter(User.email == "admin@perenniaai.com").first()

            if existing_demo or existing_admin:
                logger.info("Sample data already exists")
                return

            # Create demo branch
            branch = Branch(
                name="Main Office",
                company="Demo Mortgage Company",
                nmls_id="123456"
            )
            db.add(branch)
            db.commit()

            # Create demo user
            demo_user = User(
                email="admin@perenniaai.com",
                hashed_password=get_password_hash("demo123"),
                full_name="Demo User",
                role="loan_officer",
                branch_id=branch.id
            )
            db.add(demo_user)
            db.commit()

            # Create sample leads
            sample_leads = [
                Lead(
                    name="John Smith",
                    email="john.smith@email.com",
                    phone="555-0101",
                    stage=LeadStage.NEW,
                    source="Website",
                    loan_type="Purchase",
                    preapproval_amount=450000,
                    credit_score=750,
                    debt_to_income=0.35,
                    owner_id=demo_user.id,
                    ai_score=85,
                    sentiment="positive",
                    next_action="Schedule initial consultation"
                ),
                Lead(
                    name="Sarah Johnson",
                    email="sarah.j@email.com",
                    phone="555-0102",
                    stage=LeadStage.PROSPECT,
                    source="Referral",
                    loan_type="Refinance",
                    preapproval_amount=350000,
                    credit_score=720,
                    debt_to_income=0.40,
                    owner_id=demo_user.id,
                    ai_score=78,
                    sentiment="positive",
                    next_action="Send pre-qualification letter"
                ),
                Lead(
                    name="Mike Williams",
                    email="mike.w@email.com",
                    phone="555-0103",
                    stage=LeadStage.Application,
                    source="Zillow",
                    loan_type="Purchase",
                    preapproval_amount=525000,
                    credit_score=680,
                    debt_to_income=0.42,
                    owner_id=demo_user.id,
                    ai_score=65,
                    sentiment="neutral",
                    next_action="Collect additional documentation"
                )
            ]

            for lead in sample_leads:
                db.add(lead)
            db.commit()

            # Create sample loans
            sample_loans = [
                Loan(
                    loan_number="L2024-001",
                    borrower_name="Emily Davis",
                    amount=400000,
                    stage=LoanStage.PROCESSING,
                    program="Conventional",
                    loan_type="Purchase",
                    rate=6.875,
                    term=360,
                    property_address="123 Main St, Anytown, CA",
                    closing_date=datetime.now(timezone.utc) + timedelta(days=25),
                    loan_officer_id=demo_user.id,
                    processor="Jane Processor",
                    days_in_stage=5,
                    sla_status="on-track"
                ),
                Loan(
                    loan_number="L2024-002",
                    borrower_name="Robert Brown",
                    amount=550000,
                    stage=LoanStage.UW_RECEIVED,
                    program="FHA",
                    loan_type="Purchase",
                    rate=7.125,
                    term=360,
                    property_address="456 Oak Ave, Somewhere, CA",
                    closing_date=datetime.now(timezone.utc) + timedelta(days=18),
                    loan_officer_id=demo_user.id,
                    processor="John Processor",
                    underwriter="Sarah UW",
                    days_in_stage=3,
                    sla_status="on-track"
                )
            ]

            for loan in sample_loans:
                loan.ai_insights = generate_ai_insights(loan)
                db.add(loan)
            db.commit()

            # Create sample tasks
            sample_tasks = [
                AITask(
                    title="Review appraisal for L2024-001",
                    description="Appraisal came in at $395,000 - need to discuss with borrower",
                    type=TaskType.HUMAN_NEEDED,
                    category="Documentation",
                    priority="high",
                    ai_confidence=85,
                    borrower_name="Emily Davis",
                    loan_id=sample_loans[0].id,
                    assigned_to_id=demo_user.id,
                    due_date=datetime.now(timezone.utc) + timedelta(days=1)
                ),
                AITask(
                    title="Follow up on income verification",
                    description="Waiting on 2023 W2 from borrower",
                    type=TaskType.IN_PROGRESS,
                    category="Documentation",
                    priority="medium",
                    ai_confidence=92,
                    borrower_name="Robert Brown",
                    loan_id=sample_loans[1].id,
                    assigned_to_id=demo_user.id,
                    due_date=datetime.now(timezone.utc) + timedelta(days=3)
                )
            ]

            for task in sample_tasks:
                db.add(task)
            db.commit()

            # Create sample referral partners
            sample_partners = [
                ReferralPartner(
                    name="Jane Realtor",
                    company="Premier Realty",
                    type="Real Estate Agent",
                    phone="555-0200",
                    email="jane@premierrealty.com",
                    referrals_in=15,
                    closed_loans=8,
                    volume=3200000,
                    loyalty_tier="gold",
                    status="active"
                ),
                ReferralPartner(
                    name="Bob Builder",
                    company="Custom Homes Inc",
                    type="Builder",
                    phone="555-0201",
                    email="bob@customhomes.com",
                    referrals_in=8,
                    closed_loans=5,
                    volume=2100000,
                    loyalty_tier="silver",
                    status="active"
                )
            ]

            for partner in sample_partners:
                db.add(partner)
            db.commit()

            # Create sample MUM clients
            sample_mum = [
                MUMClient(
                    name="Previous Borrower 1",
                    loan_number="L2023-045",
                    original_close_date=datetime.now(timezone.utc) - timedelta(days=365),
                    days_since_funding=365,
                    original_rate=7.5,
                    current_rate=6.875,
                    loan_balance=380000,
                    refinance_opportunity=True,
                    estimated_savings=2375,
                    status="opportunity"
                )
            ]

            for mum in sample_mum:
                db.add(mum)
            db.commit()

            logger.info("✅ Sample data created successfully")
            logger.info(f"   Admin user: admin@perenniaai.com")
            logger.info(f"   Created {len(sample_leads)} leads, {len(sample_loans)} loans, {len(sample_tasks)} tasks")

        except Exception as e:
            logger.error(f"❌ Sample data creation failed: {e}")
            db.rollback()

    # Extracted to routes/ai_underwriter_routes.py
    # (POST /api/v1/ai-underwriter/ask - AI mortgage Q&A)

    # Extracted to routes/db_migration_routes.py
    # (add-purl-system, add-email-monitor, add-morning-checkin, add-rate-sheets)


    # Duplicate helper block removed (was copy of lines 7723-10268)
    # Functions: generate_api_key, generate_ai_insights, calculate_lead_score,
    # classify_email_content, extract_loan_fields, match_entity, detect_scheduling_intent,
    # Microsoft OAuth helpers, process_microsoft_email_to_dre, init_db, create_sample_data


    # Duplicate route block removed (was copy of lines 10269-14860)
    # Routes: debug, reconciliation, leads CRUD, init_db, sample data
    # AI underwriter extracted to routes/ai_underwriter_routes.py


    # Extracted to routes/db_migration_routes.py and routes/admin_ops_routes.py
    # (admin/run-migration, followupboss-tables, add-loans-organization-column,
    #  fix-loan-associations, fix-task-assignments, loan-check, debug-data,
    #  task-check, clear-imported-loans, import-loans)

    # Export key functions for backward compatibility (from main import X)
    _exported_functions.update({
        'process_microsoft_email_to_dre': process_microsoft_email_to_dre,
        'fetch_microsoft_emails': fetch_microsoft_emails,
        # generate_email_signature_html is now exported via email_management_routes
        'calculate_lead_score': calculate_lead_score,
        'get_entity_name': get_entity_name,
        'classify_email_intent': classify_email_intent,
        'generate_recommended_action': generate_recommended_action,
        'classify_email_content': classify_email_content,
        'extract_loan_fields': extract_loan_fields,
        'extract_borrower_from_subject': extract_borrower_from_subject,
        'match_entity': match_entity,
        'apply_extracted_data': apply_extracted_data,
        'delete_microsoft_email': delete_microsoft_email,
    })
