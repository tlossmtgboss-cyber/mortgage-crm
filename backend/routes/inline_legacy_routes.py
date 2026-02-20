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
    SSOConfig,
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
        from routes.backup_routes import register_backup_routes
        register_backup_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Backup & DR routes loaded (enterprise readiness)")
    except Exception as e:
        logger.error(f"❌ Backup & DR routes failed: {e}")

    try:
        from routes.dr_routes import register_dr_routes
        register_dr_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ DR management routes loaded (failover, retention, degradation)")
    except Exception as e:
        logger.error(f"❌ DR management routes failed: {e}")

    try:
        from routes.gdpr_routes import register_gdpr_routes
        register_gdpr_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ GDPR/CCPA data deletion routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ GDPR routes failed: {e}")

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

    # Include MFA routes (TOTP setup, verify, disable, status)
    try:
        from routes.mfa_routes import router as mfa_router
        app.include_router(mfa_router, tags=["MFA - Multi-Factor Authentication"])
        logger.info("✅ MFA routes loaded (/api/v1/auth/mfa)")
    except Exception as e:
        logger.warning(f"⚠️ MFA routes not loaded: {e}")

    # Include SSO routes (SAML 2.0 + OIDC + admin config)
    try:
        from routes.sso_routes import router as sso_router
        app.include_router(sso_router, tags=["SSO - Single Sign-On"])
        # Create SSO tables if they don't exist
        try:
            from database.models.sso import SSOConfig
            SSOConfig.__table__.create(engine, checkfirst=True)
        except Exception as _tbl_err:
            logger.debug(f"SSO table creation skipped (may already exist): {_tbl_err}")
        logger.info("✅ SSO routes loaded (SAML + OIDC)")
    except Exception as e:
        logger.warning(f"⚠️ SSO routes not loaded: {e}")

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

    # Include MUM API routes (client list, metrics)
    try:
        from routes.mum_api_routes import router as mum_api_router
        app.include_router(mum_api_router, tags=["MUM API"])
        logger.info("✅ MUM API routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load MUM API routes: {e}")

    # Include MUM Valuation batch recalculation routes
    try:
        from routes.mum_valuation_routes import router as mum_valuation_router
        app.include_router(mum_valuation_router, tags=["MUM Valuation"])
        logger.info("✅ MUM Valuation routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load MUM Valuation routes: {e}")

    # Include Voice AI Receptionist sub-routes (webhooks, SMS, debug)
    # NOTE: The main voice_router is NOT included here — voice_routes.py (line ~492)
    # is the canonical /api/v1/voice router. Including both caused duplicate route conflicts.
    # Unique endpoints (drop-voicemail, amd-callback, voicemail-twiml) were migrated to voice_routes.py.
    try:
        from routes.voice_ai_receptionist_routes import webhook_router, sms_router, debug_router
        app.include_router(webhook_router, tags=["Voice Webhooks"])
        app.include_router(sms_router, tags=["SMS Messaging"])
        app.include_router(debug_router, tags=["Debug"])
        logger.info("✅ Voice AI Receptionist sub-routes loaded (webhooks, SMS, debug)")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Voice AI Receptionist sub-routes: {e}")

    # Power Dialer routes — DISABLED to resolve duplicate route conflict.
    # telephony/router.py (registered at line ~1568) is the canonical /api/v1/dialer router
    # with 1,506 lines, response models, TwiML webhooks, and better structure.
    # power_dialer_routes.py (882 lines) is a subset of that functionality.
    # try:
    #     from routes.power_dialer_routes import router as power_dialer_router
    #     app.include_router(power_dialer_router, tags=["Power Dialer"])
    #     logger.info("✅ Power Dialer routes loaded")
    # except Exception as e:
    #     logger.warning(f"⚠️ Could not load Power Dialer routes: {e}")
    logger.info("ℹ️ Power Dialer routes skipped (telephony/router.py is canonical)")

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

        # Ensure voicemail tables exist in production (Base.metadata.create_all is skipped)
        try:
            from database.models.communication import (
                VoicemailTemplate, VoicemailCampaign, VoicemailDrop, VoicemailEvent
            )
            from database.models.dialer import ContactDNCStatus
            from db import engine as _vm_engine
            from sqlalchemy import text as _vm_text

            # Create tables that don't exist yet (dependency order)
            for _vm_model in [VoicemailTemplate, VoicemailCampaign, VoicemailDrop, VoicemailEvent, ContactDNCStatus]:
                _vm_model.__table__.create(_vm_engine, checkfirst=True)

            # Add missing columns to pre-existing tables (old migration vs new model)
            _alter_stmts = [
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS organization_id INTEGER",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255)",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS delivery_method VARCHAR(50) DEFAULT 'vapi_ai'",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS vapi_assistant_id VARCHAR(255)",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20)",
                "ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS audio_url VARCHAR(500)",
                "ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS voice_provider VARCHAR(50) DEFAULT 'deepgram'",
                "ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS voice_id VARCHAR(100) DEFAULT 'asteria'",
                "ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS voice_speed NUMERIC(3,2) DEFAULT 1.0",
                "ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS delivery_method VARCHAR(50) DEFAULT 'vapi_ai'",
                # RVM (ringless voicemail) provider tracking columns
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS rvm_session_id VARCHAR(255)",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS rvm_provider VARCHAR(50)",
                "ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS rvm_dispo_code VARCHAR(50)",
                # Lead SLA milestone column
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS initial_consultation_date TIMESTAMP",
                # Multi-tenant column for API keys
                "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS organization_id INTEGER",
            ]
            with _vm_engine.connect() as _vm_conn:
                for _stmt in _alter_stmts:
                    try:
                        _vm_conn.execute(_vm_text(_stmt))
                        _vm_conn.commit()
                    except Exception:
                        _vm_conn.rollback()
                # Index for RVM session lookups (used by webhook)
                try:
                    _vm_conn.execute(_vm_text(
                        "CREATE INDEX IF NOT EXISTS ix_voicemail_drops_rvm_session_id "
                        "ON voicemail_drops (rvm_session_id)"
                    ))
                    _vm_conn.commit()
                except Exception:
                    _vm_conn.rollback()
                # Copy contact_phone -> phone_number for rows that used old column name
                try:
                    _vm_conn.execute(_vm_text(
                        "UPDATE voicemail_drops SET phone_number = contact_phone "
                        "WHERE phone_number IS NULL AND contact_phone IS NOT NULL"
                    ))
                    _vm_conn.commit()
                except Exception:
                    _vm_conn.rollback()

            logger.info("✅ Voicemail tables verified/created (columns synced)")

            # Seed default templates if table is empty
            from sqlalchemy.orm import Session as _VmSession
            _vm_sess = _VmSession(bind=_vm_engine)
            try:
                if _vm_sess.query(VoicemailTemplate).count() == 0:
                    _default_templates = [
                        VoicemailTemplate(name="Closing Disclosure Ready", category="closing", message_text="Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. Your closing disclosures are ready for review. They've been sent to your email. Please review and sign at your earliest convenience. If you have questions, call me back. Thanks!", variables=["contact_name", "loan_officer"], is_default=True, is_active=True),
                        VoicemailTemplate(name="Document Request", category="follow_up", message_text="Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. We need a few additional documents to move your loan forward. I've sent you an email with the list. Please upload them to your portal when you can. Call me if you need help. Thank you!", variables=["contact_name", "loan_officer"], is_default=True, is_active=True),
                        VoicemailTemplate(name="Rate Lock Expiration", category="urgent", message_text="Hi {{contact_name}}, this is {{loan_officer}}. Your rate lock expires soon. We need to take action to secure your current rate. Please call me back as soon as possible so we can discuss options. Thanks!", variables=["contact_name", "loan_officer"], is_default=True, is_active=True),
                        VoicemailTemplate(name="Application Status Update", category="status_update", message_text="Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. Quick update on your loan application — everything is moving along smoothly. I'll keep you posted. Feel free to reach out with questions. Have a great day!", variables=["contact_name", "loan_officer"], is_default=True, is_active=True),
                        VoicemailTemplate(name="Appointment Reminder", category="scheduling", message_text="Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. Just a friendly reminder about our appointment tomorrow. Looking forward to speaking with you. Call me if you need to reschedule. See you soon!", variables=["contact_name", "loan_officer"], is_default=True, is_active=True),
                    ]
                    _vm_sess.add_all(_default_templates)
                    _vm_sess.commit()
                    logger.info("✅ Seeded 5 default voicemail templates")
            except Exception as _seed_err:
                _vm_sess.rollback()
                logger.warning(f"⚠️ Could not seed voicemail templates: {_seed_err}")
            finally:
                _vm_sess.close()
        except Exception as _tbl_err:
            logger.warning(f"⚠️ Could not create voicemail tables: {_tbl_err}")

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

    # Include Permission Core routes (user permission endpoints)
    try:
        from routes.permission_core_routes import router as permission_core_router
        app.include_router(permission_core_router, tags=["Permission Core"])
        logger.info("✅ Permission Core routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Permission Core routes: {e}")

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

    # Include Loans CRUD routes (lead-to-loan conversion, loan pipeline)
    try:
        from routes.loans_crud_routes import router as loans_crud_router
        app.include_router(loans_crud_router, tags=["Loans CRUD"])
        logger.info("✅ Loans CRUD routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Loans CRUD routes: {e}")

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
        _video_meeting_error = f"{e}"
        logger.error(f"⚠️ Could not load Video Meeting routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint to check video meeting loading status
    @app.get("/api/v1/debug/video-meetings-status", tags=["Debug"])
    async def debug_video_meetings_status(current_user=Depends(get_current_user)):
        """Check if video meeting routes loaded successfully"""
        if _video_meeting_error:
            return {"status": "failed"}
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
        _video_clip_error = f"{e}"
        logger.error(f"⚠️ Could not load Video Clip routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint to check video clip loading status
    @app.get("/api/v1/debug/video-clips-status", tags=["Debug"])
    async def debug_video_clips_status(current_user=Depends(get_current_user)):
        """Check if video clip routes loaded successfully"""
        if _video_clip_error:
            return {"status": "failed"}
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
        from api.routes.call_recording import router as call_recording_router
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
        _carousel_routes_error = f"{e}"
        logger.warning(f"⚠️ Could not load Carousel Builder routes: {e}")
        logger.warning(f"Full traceback: {traceback.format_exc()}")


    @app.get("/api/v1/debug/carousel-routes-status", tags=["Debug"])
    async def debug_carousel_routes_status(current_user=Depends(get_current_user)):
        """Check if carousel builder routes loaded successfully"""
        if _carousel_routes_error:
            return {"status": "failed"}
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
        from routes.phase4_routes import ai_learning_router, meta_agent_router
        app.include_router(ai_learning_router, tags=["AI Learning"])
        app.include_router(meta_agent_router, tags=["Continuous Learning Meta-Agent"])
        logger.info("✅ Phase 4 AI Learning & Optimization routes loaded (AI Learning, Meta-Agent)")
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

    # Register Salesforce sync jobs with APScheduler
    if scheduler:
        try:
            from tasks.salesforce_sync_tasks import register_salesforce_sync_jobs
            register_salesforce_sync_jobs(scheduler)
            if not scheduler.running:
                scheduler.start()
            logger.info("✅ Salesforce sync jobs registered and scheduler started")
        except Exception as e:
            logger.warning(f"⚠️ Salesforce sync jobs not registered: {e}")

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
        from routes.user_profile_settings_routes import router as user_profile_settings_router, users_router as users_me_router, set_dependencies as set_user_profile_deps
        set_user_profile_deps(User, get_current_user, pwd_context)
        app.include_router(user_profile_settings_router, tags=["User Profile Settings"])
        app.include_router(users_me_router, tags=["Users"])
        logger.info("✅ User Profile Settings routes loaded")
    except Exception as e:
        logger.warning(f"User Profile Settings routes not loaded: {e}")

    # Dashboard routes
    try:
        from routes.dashboard_routes import router as dashboard_router
        app.include_router(dashboard_router, tags=["Dashboard"])
        logger.info("✅ Dashboard routes loaded")
    except Exception as e:
        logger.warning(f"Dashboard routes not loaded: {e}")

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

    # ============================================================================
    # DEBUG STATUS ROUTES (extracted to routes/debug_status_routes.py)
    # Endpoints: PURL debug, appointments, SMS test, cache, DataDog, CDN, roles
    # ============================================================================
    try:
        from routes.debug_status_routes import register_debug_status_routes
        register_debug_status_routes(
            app, get_db, get_current_user,
            route_errors={"purl": purl_routes_error},
            **kwargs
        )
        logger.info("✅ Debug status routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Debug status routes failed: {e}")


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
    async def debug_perennia_docs_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check Perennia Docs AI routes loading status"""
        return {
            "perennia_docs_loaded": perennia_docs_error is None
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
    async def debug_esign_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check E-Signature routes loading status"""
        return {
            "esign_loaded": esign_error is None
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
    async def debug_portal_integration_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check Portal AI and PURL Integration routes loading status"""
        return {
            "portal_ai_assistant_loaded": portal_ai_assistant_error is None,
            "purl_integration_loaded": purl_integration_error is None
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
    async def debug_portal_services_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check all portal-related routes loading status"""
        return {
            "portal_ai_assistant": {"loaded": portal_ai_assistant_error is None},
            "purl_integration": {"loaded": purl_integration_error is None},
            "portal_documents": {"loaded": portal_document_error is None},
            "portal_auth": {"loaded": portal_auth_error is None},
            "perennia_portal": {"loaded": perennia_portal_error is None}
        }

    @app.get("/api/v1/debug/intake-engine-status")
    async def debug_intake_engine_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check intake engine loading status"""
        status = {
            "loaded": intake_engine_error is None
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
            except Exception:
                status["engine_available"] = False

        return status

    # Debug endpoint for tools registry loading
    @app.get("/api/v1/debug/tools-registry-status")
    async def debug_tools_registry_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check tools registry loading status"""
        return {
            "tools_router_loaded": tools_router_error is None
        }


    # Cache stats monitoring endpoint
    # (Debug endpoints for cache-stats, datadog, CDN, add-missing-roles
    #  extracted to routes/debug_status_routes.py)


    # Extracted to routes/db_migration_routes.py
    # (add-purl-system, add-email-monitor, add-morning-checkin, add-rate-sheets)

    # ============================================================================
    # DRE HELPERS (extracted to services/dre_helpers.py)
    # ============================================================================
    from services.dre_helpers import (
        init_dre_helpers,
        generate_api_key,
        generate_ai_insights,
        calculate_lead_score,
        classify_email_content,
        extract_loan_fields,
        extract_borrower_from_subject,
        match_entity,
        classify_email_intent,
        get_entity_name,
        generate_recommended_action,
        detect_scheduling_intent,
        get_calendly_time_slots_for_user,
        generate_scheduling_email_draft,
        create_milestone_tasks,
        create_lead_milestone_tasks,
        apply_extracted_data,
        get_encryption_key,
        encrypt_token,
        decrypt_token,
        refresh_microsoft_token,
        fetch_microsoft_emails,
        delete_microsoft_email,
        process_microsoft_email_to_dre,
    )
    init_dre_helpers(openai_client=openai_client, secret_key=SECRET_KEY)

    # ============================================================================
    # (Legacy DRE helper definitions removed - now in services/dre_helpers.py)
    # Functions: generate_api_key, generate_ai_insights, calculate_lead_score,
    #   classify_email_content, extract_loan_fields, extract_borrower_from_subject,
    #   match_entity, classify_email_intent, get_entity_name,
    #   generate_recommended_action, detect_scheduling_intent,
    #   get_calendly_time_slots_for_user, generate_scheduling_email_draft,
    #   create_milestone_tasks, create_lead_milestone_tasks, apply_extracted_data,
    #   get_encryption_key, encrypt_token, decrypt_token,
    #   refresh_microsoft_token, fetch_microsoft_emails,
    #   delete_microsoft_email, process_microsoft_email_to_dre
    # ============================================================================

    # Extracted to routes/db_migration_routes.py
    # (add-external-message-id through fix-voicemail-drops-columns)
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

    # ============================================================================
    # LEADS DETAIL/CRUD ROUTES (extracted to routes/leads_detail_routes.py)
    # Routes: bulk-delete, bulk-update-status, leads/{id} CRUD, documents, claim-orphans
    # ============================================================================
    try:
        from routes.leads_detail_routes import register_leads_detail_routes
        register_leads_detail_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs)
        logger.info("✅ Leads detail/CRUD routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Leads detail routes failed: {e}")

    # ============================================================================
    # LOS INTEGRATION ROUTES (Domain 7 - Integration Health)
    # ============================================================================
    try:
        from routes.los_routes import register_los_routes
        register_los_routes(app, get_db, get_current_user, **kwargs)
        logger.info("LOS integration routes registered")
    except Exception as e:
        logger.warning(f"LOS routes not available: {e}")

    try:
        from routes.los_webhook_routes import register_los_webhook_routes
        register_los_webhook_routes(app, get_db, **kwargs)
        logger.info("LOS webhook routes registered")
    except Exception as e:
        logger.warning(f"LOS webhook routes not available: {e}")

    # ============================================================================
    # COMPLIANCE ROUTES (Domain 2 - Fair Lending, License, TCPA)
    # ============================================================================
    try:
        from routes.compliance_routes import register_compliance_routes
        register_compliance_routes(app, get_db, get_current_user, **kwargs)
        logger.info("Compliance routes registered (fair lending, license enforcement, TCPA)")
    except Exception as e:
        logger.warning(f"Compliance routes not available: {e}")

    # ============================================================================
    # DATABASE INITIALIZATION (extracted to database/init_db.py)
    # ============================================================================
    from database.init_db import init_module as init_db_module, init_db, create_sample_data
    init_db_module(engine=engine, Base=Base, database_url=DATABASE_URL, environment=ENVIRONMENT)

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
