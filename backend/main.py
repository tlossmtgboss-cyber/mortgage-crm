# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Increase recursion limit — FastAPI's merged_lifespan chains deeply with many routers
import sys
sys.setrecursionlimit(3000)

# Suppress warnings in production to avoid Railway rate limiting (500 logs/sec limit)
import warnings
import os as _os
if _os.getenv("RAILWAY_ENVIRONMENT") or _os.getenv("ENVIRONMENT") == "production":
    warnings.filterwarnings("ignore")
    # Also suppress SQLAlchemy deprecation warnings
    from sqlalchemy.exc import SAWarning
    warnings.filterwarnings("ignore", category=SAWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================================
# AGENTIC AI MORTGAGE CRM - App Setup & Configuration
# ============================================================================

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import uvicorn
import os
import logging
import hashlib
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import time
import signal as _signal_module

# Graceful shutdown and startup utilities
from utils.shutdown import GracefulShutdown, RequestTrackingMiddleware, install_signal_handlers
from utils.startup import startup_checks

# Import security middleware
from security_middleware import (
    IPAccessControlMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    IPBlockingMiddleware,
    RequestValidationMiddleware,
    SecurityLoggingMiddleware,
    security_stats,  # Shared security state for dashboard
)

# Import onboarding modules
from schemas.onboarding import Step1Data, OnboardingProgressResponse, VerifyCodeRequest, SendVerificationRequest
from crud import onboarding as onboarding_crud

# Import lead workflow automation engine
from workflows.lead_workflow_engine import LeadWorkflowEngine, TimeBasedWorkflowEngine, LeadStatusChange
from workflows.workflow_actions import WorkflowActionExecutor

# Import SLA tracking service for automatic milestone tracking
from services.sla_tracking_service import track_lead_created, track_lead_stage_change, track_loan_created, track_loan_stage_change

# Import capacity update for Master Manager integration
from services.capacity_service import update_capacity_on_assignment

# Import profitability models for AI financial context
from models.profitability import ProfitabilitySnapshot, ProfitabilityLoan, Expense, EmployeeCost

# Import financial intelligence models for table creation
from models.financial_intelligence import (
    LoanSale, HedgePosition, SecondaryMetrics, MSRPortfolio,
    WarehouseLine, WarehouseUsage, ProductProfitability,
    CashPosition, CashForecast, BurnRate, CompetitorRate,
    LostDeal, CapitalRequirement, ComplianceRisk
)

# Import rate sheet models for table creation
from models.rate_sheet import RateSheet, RateSheetRate, RefinanceOpportunity

# Setup structured logging - JSON in production, human-readable in development
# Installs RequestContextFilter so all loggers automatically get request_id,
# user_id, org_id injected from contextvars set by RequestContextMiddleware.
# Must be called before any logger.info() calls to install the correct formatter.
from utils.logging_config import configure_logging as _configure_logging
_configure_logging()
logger = logging.getLogger(__name__)

# Install PII redaction filter on root logger to prevent SSN/PII leakage in logs
# Enterprise Readiness Check 3.20 - must be installed before any PII processing
try:
    from middleware.pii_log_filter import install_pii_filter
    install_pii_filter()
except Exception as _pii_err:
    logger.warning(f"PII log filter not installed: {_pii_err}")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
# Use SQLite for local development if DATABASE_URL not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SECRET_KEY configuration - must be set in production
_SECRET_KEY = os.getenv("SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production" and not _SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is required in production. "
        "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# Require SECRET_KEY - no fallback for security
if not _SECRET_KEY:
    if ENVIRONMENT == "development":
        logger.warning("⚠️ SECRET_KEY not set - using generated key for development only")
        import secrets
        SECRET_KEY = secrets.token_hex(32)
    else:
        raise ValueError("SECRET_KEY environment variable is required in production")
else:
    SECRET_KEY = _SECRET_KEY

# JWT Configuration - Uses new auth module for RS256 support
# Keep these for backward compatibility, but auth module settings take precedence
ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")  # Can be overridden to RS256
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Reduced from 30 for security
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Import new auth module for secure token handling
try:
    from auth.tokens import (
        create_access_token as _create_secure_access_token,
        create_refresh_token as _create_secure_refresh_token,
        verify_token as _verify_secure_token,
        token_blacklist,
        TokenType,
        TokenData,
    )
    from auth.config import get_auth_settings
    _USE_SECURE_TOKENS = True

    # Initialize token blacklist with Redis if configured
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        token_blacklist.initialize(_redis_url)
        # Validate Redis connectivity at startup
        try:
            import redis
            _r = redis.from_url(_redis_url, socket_timeout=5)
            _r.ping()
            logger.info("Redis connection verified")
            _r.close()
        except Exception as e:
            logger.error(f"Redis connection FAILED: {e} — token revocation and rate limiting may not work")
        logger.info("Token blacklist initialized with Redis")
    else:
        _env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
        if _env in ("production", "staging"):
            logger.error("REDIS_URL not set — token revocation disabled in production")
        else:
            logger.warning("REDIS_URL not set — using in-memory token blacklist (dev only)")
except ImportError as e:
    logger.warning(f"⚠️ Secure auth module not available, using legacy JWT: {e}")
    _USE_SECURE_TOKENS = False

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ============================================================================
# IN-MEMORY CACHE FOR BLAZING FAST RETRIEVAL
# ============================================================================
# Simple TTL cache for expensive endpoints
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 30  # 30-second cache for dashboard data
MAX_CACHE_SIZE = 1000

def get_cached(key: str) -> Optional[Any]:
    """Get cached value if not expired"""
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry['timestamp'] < CACHE_TTL_SECONDS:
            return entry['data']
        del _cache[key]
    return None

def set_cached(key: str, data: Any) -> None:
    """Set cache entry with timestamp"""
    # Evict oldest entries if cache is full
    if len(_cache) >= MAX_CACHE_SIZE:
        # Remove expired entries first
        now = time.time()
        expired = [k for k, v in _cache.items() if now - v['timestamp'] > CACHE_TTL_SECONDS]
        for k in expired:
            del _cache[k]
        # If still full, remove oldest
        if len(_cache) >= MAX_CACHE_SIZE:
            oldest_key = min(_cache, key=lambda k: _cache[k]['timestamp'])
            del _cache[oldest_key]
    _cache[key] = {'data': data, 'timestamp': time.time()}

def clear_cache(prefix: str = None) -> None:
    """Clear cache entries, optionally by prefix"""
    global _cache
    if prefix:
        _cache = {k: v for k, v in _cache.items() if not k.startswith(prefix)}
    else:
        _cache = {}

# Database - Import shared engine and session from database.py to avoid duplicate pools
# This consolidates all DB connections to a single pool (Railway has ~20 connection limit)
from database import engine, SessionLocal, Base, get_db as _get_db_from_database

# Initialize background scheduler for auto-sync with job defaults
# misfire_grace_time: If a job is missed by up to 30 seconds, still run it
# coalesce: If multiple executions were missed, only run once
scheduler = AsyncIOScheduler(
    job_defaults={
        'coalesce': True,  # Combine missed executions into one
        'max_instances': 1,  # Only one instance of each job at a time
        'misfire_grace_time': 30  # 30 second grace period for missed jobs
    }
)

# Use RLS-aware get_db from database.py — ensures tenant isolation for ALL routes
get_db = _get_db_from_database

# ============================================================================
# ENUMS - imported from database.enums
# ============================================================================
from database.enums import (
    LeadStage, LoanStage, RateLockStatus, RateLockRecommendation,
    BuyingTimelineCategory, BorrowerRiskProfile, TaskType, ActivityType,
    EmailIntakeMatchStatus, AttachmentClassificationStatus, DocumentType,
    DocumentCategory, InviteStatus, PermissionLevel,
    DialerSessionStatus, DialerTaskStatus, CallOutcome,
    SocialProvider, ApplicationStatus, ApplicationStep, CoachMode,
)


# ============================================================================
# DATABASE MODELS - imported from database.models
# ============================================================================
from database.models import (
    # Core
    Organization, Branch, User, ApiKey, UserSettings, CalendarAssignment,
    EmailSignature, ImpersonationSession, OnboardingProgress, OnboardingError,
    VerificationToken,
    # Lead & Loan
    Lead, Loan,
    # Tasks
    AITask, Task,
    # Documents
    EmailIntake, AttachmentIntake, Document,
    # Communication
    Activity, StageHistory, Conversation, ConversationMemory,
    SMSMessage, SMSConversation, EmailMessage, Email, EmailDraft, EmailVerificationToken,
    TeamsMessage, VoicemailDrop, VoicemailTemplate, VoicemailCampaign, VoicemailEvent,
    CalendarEvent, IntegrationLog, IntegrationCredential,
    # AI
    AIDelegatedTask, AIFeedbackLog, AIAction, AILearningMetric,
    AIKnowledgeBase, AIAuditLog, AIColleagueAction, AIColleagueLearningMetric,
    AIPerformanceDaily, AIJourneyInsight, AIHealthScore, AIMetricsDaily,
    AIChangelogDaily, AITrainingEvent,
    # Referral
    ReferralPartner, LoanTeamMember, MUMClient,
    # Workflow
    ScheduledWorkflow, WorkflowExecution, Workflow, CalendarMapping,
    OnboardingStep, ProcessTemplate, ProcessRole, ProcessMilestone, ProcessTask,
    # Permission
    EmployeeInvite, CRMPage, RolePagePermission, UserPagePermission,
    UserPermission, PermissionRequest, AIQuickAction, AIQuickActionRole,
    Responsibility, RoleResponsibility, UserResponsibility,
    # Security
    AuditLog, UserSession, EmergencyRevocation, AccessCertification,
    SecuritySnapshotDaily, IntegrationStatusLog, SystemAlert, SystemJobsLog, Notification,
    # Subscription
    SubscriptionPlan, Subscription, PromoCode, TeamMember,
    # Microsoft
    MicrosoftToken, MicrosoftOAuthToken, MicrosoftAppConfig,
    # Data Reconciliation
    IncomingDataEvent, ExtractedData, BlockedSender, DuplicatePair,
    MergeTrainingEvent, MergeAIModel,
    # IT Helpdesk
    ITHelpdeskTicket, ITHelpdeskTool,
    # Client
    ClientProfile, TeamRole, ProcessFlowDocument, KPISnapshot,
    # HR Goals
    UserJobDescription, Skill, EmployeeResponsibility, ResponsibilitySkill,
    UserGoal, GoalKeyResult, GoalEmployeeAssessment, GoalManagerAssessment,
    GoalResponsibility, UserSkillAssessment,
    # Dialer
    AgentTelephonySettings, VerifiedCallerId, DialerSession, DialerSessionTask,
    CallLog, ActiveCall, ContactDNCStatus,
    # Borrower Application
    BorrowerProfile, BorrowerAuthEvent, BorrowerMagicLink, BorrowerApplication,
    ApplicationDocument, CoborrowerInvitation, ApplicationEvent,
    ApplicationNotification, ApplicationSession, VoiceApplicationSession,
    # Loan Estimates
    EstimateParseCache, EstimateParseFailure, EstimateComparison,
    # SSO
    SSOConfig,
)

# Configure mappers after all model imports
from sqlalchemy.orm import configure_mappers
try:
    configure_mappers()
except Exception as e:
    logger.warning(f"Mapper configuration warning (may be handled later): {e}")



# ============================================================================
# PYDANTIC SCHEMAS - imported from schemas.core
# ============================================================================
from schemas.core import (
    UserCreate, UserResponse, TeamMemberCreate, TeamMemberUpdate,
    ApiKeyCreate, ApiKeyResponse, ImpersonationStart, ImpersonationResponse,
    LeadCreate, LeadUpdate, LeadResponse,
    LoanCreate, LoanUpdate, LoanResponse,
    TaskCreate, TaskUpdate, TaskResponse,
    ReferralPartnerCreate, ReferralPartnerUpdate, ReferralPartnerResponse,
    LoanTeamMemberCreate, LoanTeamMemberUpdate, LoanTeamMemberResponse,
    MUMClientCreate, MUMClientUpdate, MUMClientResponse,
    BorrowerApplicationCreate, BorrowerApplicationUpdate, StepDataUpdate,
    CreditAuthCapture, PrequalificationRequest, PrequalificationResponse,
    DocumentUploadResponse, CoborrowerInvitationCreate, CoborrowerInvitationResponse,
    ApplicationEventCreate, BorrowerApplicationResponse, ApplicationPublicResponse,
    ApplicationAnalytics, ErrorFixRequest,
    UserProfileData, BrandingSettings, IntegrationSettings, AutomationSettings,
    ReconciliationSettings, PipelineSettings, KPITargets, PortfolioSettings,
    AdvancedSettings, ClientProfileCreate, ClientProfileUpdate, ClientProfileResponse,
    TeamRoleCreate, TeamRoleUpdate, TeamRoleResponse,
    ProcessFlowDocumentCreate, ProcessFlowDocumentResponse,
    ActivityCreate, ActivityResponse,
    ProcessTemplateCreate, ProcessTemplateUpdate, ProcessTemplateResponse,
    ProcessRoleCreate, ProcessRoleResponse,
    ProcessMilestoneCreate, ProcessMilestoneResponse,
    ProcessTaskCreate, ProcessTaskResponse,
    DocumentParseRequest, DocumentParseResponse,
    ConversationCreate, ChatStreamRequest, ConversationResponse,
    CoachRequest, CoachResponse,
    CalendarEventCreate, CalendarEventUpdate, CalendarEventResponse,
    CalendarAssignmentCreate, CalendarAssignmentUpdate, CalendarAssignmentResponse,
    CALENDAR_PURPOSES,
    IncomingDataEventCreate, ExtractedDataResponse,
    ReconciliationApproval, ReconciliationRejection, BlockSenderRequest,
    CreateLeadFromExtracted,
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    MicrosoftOAuthConnect, MicrosoftTokenResponse, MicrosoftSyncSettings,
    MicrosoftAppConfigRequest, MicrosoftAppConfigResponse,
    RevokeSessionRequest, RevokeAllSessionsRequest, EmergencyRevokeRequest,
    UpdateJobDescriptionRequest, JobDescriptionResponse,
    SkillCreate, SkillResponse,
    CreateResponsibilityRequest, UpdateResponsibilityRequest,
    ResponsibilityResponse, ReorderResponsibilitiesRequest,
)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Agentic AI Mortgage CRM",
    description="Complete mortgage CRM with AI automation - All features implemented",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False  # Prevent HTTP redirects that cause mixed content errors
)

# Graceful shutdown handler — tracks in-flight requests, coordinates shutdown sequence
graceful_shutdown = GracefulShutdown(drain_timeout=30.0)

# CORS - Dynamic custom domain support
# Custom domains are stored in the database and checked dynamically
# No code changes needed to add new user domains
from middleware.dynamic_cors import DynamicCORSMiddleware

# PHASE 3: Impersonation read-only enforcement middleware
from middleware.impersonation_middleware import ImpersonationEnforcementMiddleware

# Multi-Tenant: Tenant context middleware for organization isolation
from middleware.tenant_context_middleware import TenantContextMiddleware

# Request tracking for graceful shutdown (innermost middleware — added first)
# Tracks in-flight requests and returns 503 during shutdown to drain traffic
app.add_middleware(RequestTrackingMiddleware, shutdown_handler=graceful_shutdown)

# Add security middleware FIRST (order matters - last added = outermost = first to execute)
# Security middleware runs first, then CORS wraps everything including error responses
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestValidationMiddleware)

# Request Validator — Content-Type (415), Content-Length / size limit (413),
# path traversal, null-byte, SQL injection, and XSS checks.
try:
    from middleware.request_validator import RequestValidatorMiddleware
    app.add_middleware(RequestValidatorMiddleware)
    logger.info("✅ Request validator middleware enabled (Content-Type, size limit, injection checks)")
except Exception as e:
    logger.warning(f"⚠️ Request validator middleware not loaded: {e}")

app.add_middleware(IPBlockingMiddleware)
# Rate limiting - per-user for authenticated, per-IP for anonymous
# Supports role-based tiers (admin/power_user/standard/anonymous) and endpoint-specific limits
app.add_middleware(RateLimitMiddleware, requests_per_minute=5000, requests_per_hour=100000)
app.add_middleware(IPAccessControlMiddleware)  # Environment-aware IP access control
app.add_middleware(SecurityLoggingMiddleware)

# PHASE 3: Impersonation read-only enforcement
# Blocks POST/PUT/PATCH/DELETE when impersonation mode is 'read_only'
app.add_middleware(ImpersonationEnforcementMiddleware, db_session_factory=SessionLocal)

# CSRF Protection middleware - validates tokens on state-changing requests
# Must be added before CORS to ensure CSRF headers are allowed
try:
    from middleware.csrf_protection import CSRFProtectionMiddleware
    # Enable CSRF in production, disable in development for easier testing
    csrf_enabled = ENVIRONMENT == "production"
    app.add_middleware(
        CSRFProtectionMiddleware,
        enabled=csrf_enabled,
        cookie_secure=ENVIRONMENT == "production",
    )
    logger.info(f"✅ CSRF protection middleware {'enabled' if csrf_enabled else 'disabled (dev mode)'}")
except Exception as e:
    logger.warning(f"⚠️ CSRF protection middleware not loaded: {e}")

# NOTE: CORS middleware is added AFTER all other middleware (including production hardening)
# to ensure it is the absolute outermost middleware. See below after production hardening block.

# Performance Monitoring middleware - tracks endpoint response times and slow requests
try:
    from monitoring.performance_service import PerformanceMiddleware
    app.add_middleware(PerformanceMiddleware)
    logger.info("✅ Performance monitoring middleware enabled")
except Exception as e:
    logger.warning(f"⚠️ Performance monitoring middleware not loaded: {e}")

# Per-User/Per-IP API Rate Limiting — sliding window, Redis-backed with in-memory fallback
# Enforces hard per-identity ceilings with prefix-specific tuning (AI=30/min, pipeline=120/min, etc.)
# Must be added BEFORE TenantContextMiddleware (LIFO: Tenant sets user, then this reads it)
try:
    from middleware.api_rate_limit import APIRateLimitMiddleware
    app.add_middleware(APIRateLimitMiddleware)
    logger.info("API rate limiting middleware enabled (per-user/per-IP sliding window)")
except Exception as e:
    logger.warning(f"API rate limiting middleware not loaded: {e}")

# Mobile-Specific Rate Limiting — in-memory sliding window, no Redis required
# Applies only to requests from mobile apps (Capacitor/iOS/Android via User-Agent or X-Mobile-App header)
# Auth: 100 req/min, unauth: 20 req/min, with per-endpoint overrides for dashboard/sync/auth
# Must be added BEFORE TenantContextMiddleware (LIFO: inner = runs after Tenant sets user)
try:
    from middleware.mobile_rate_limit import MobileRateLimitMiddleware
    app.add_middleware(MobileRateLimitMiddleware)
    logger.info("Mobile rate limiting middleware enabled (per-user/per-IP, mobile UA only)")
except Exception as e:
    logger.warning(f"Mobile rate limiting middleware not loaded: {e}")

# Per-Tenant Rate Limiting — in-memory sliding window, no Redis required
# Must be added BEFORE TenantContextMiddleware (LIFO: Tenant Context added later
# = outermost = runs first, then this middleware reads request.state.organization_id)
try:
    from middleware.tenant_rate_limiter import TenantRateLimitMiddleware
    app.add_middleware(TenantRateLimitMiddleware)
    logger.info("Tenant rate limiting middleware enabled")
except Exception as e:
    logger.warning(f"Tenant rate limiting middleware not loaded: {e}")

# RBAC Enforcement — defense-in-depth role checks on admin/manager routes.
# Added BEFORE TenantContextMiddleware (LIFO: inner = runs after Tenant sets user).
try:
    from middleware.rbac_enforcement import RBACEnforcementMiddleware
    app.add_middleware(RBACEnforcementMiddleware)
    logger.info("RBAC enforcement middleware enabled")
except Exception as e:
    logger.warning(f"RBAC enforcement middleware not loaded: {e}")

# Multi-Tenant: Add tenant context middleware
# This sets request.state.user and request.state.tenant_context for authenticated requests
try:
    app.add_middleware(
        TenantContextMiddleware,
        secret_key=SECRET_KEY,
        get_db=get_db,
        user_model=User,
    )
    logger.info("✅ Tenant context middleware enabled")
except Exception as e:
    logger.warning(f"⚠️ Tenant context middleware not loaded: {e}")

# SOC 2 Type II Compliance — Audit trail middleware
try:
    from soc2_compliance.middleware.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
    logger.info("✅ SOC 2 audit trail middleware enabled")
except Exception as e:
    logger.error(f"⚠️ SOC 2 audit middleware not loaded: {e}")
    if ENVIRONMENT == "production":
        logger.critical("SOC 2 audit middleware failed in production — audit logging degraded")

# Breadcrumb audit middleware — defense-in-depth for mutating API calls
try:
    from middleware.audit_middleware import AuditMiddleware as BreadcrumbAuditMiddleware
    app.add_middleware(BreadcrumbAuditMiddleware)
    logger.info("✅ Breadcrumb audit middleware enabled (audit_events table)")
except Exception as e:
    logger.warning(f"⚠️ Breadcrumb audit middleware not loaded: {e}")

logger.info(f"✅ Security middleware enabled (ENVIRONMENT={os.getenv('ENVIRONMENT', 'development')}): "
            "IP access control, rate limiting, IP blocking, security headers, request validation, and logging")

# ============================================================================
# PRODUCTION HARDENING - Sentry, structured logging, request tracing
# ============================================================================
try:
    from production_hardening import (
        setup_production_hardening,
        structured_logger,
        health_checker,
        get_request_id,
        monitor_performance
    )

    # Initialize production hardening
    hardening_result = setup_production_hardening(app, engine)
    logger.info(f"✅ Production hardening initialized: {hardening_result}")

    # Register database health check
    async def check_database():
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    health_checker.register_check("database", check_database)

except Exception as e:
    logger.warning(f"⚠️ Production hardening not fully initialized: {e}")
    structured_logger = None
    health_checker = None

# ============================================================================
# DATADOG MONITORING - APM, Metrics, Dashboards
# ============================================================================
try:
    from datadog_monitoring import (
        setup_datadog_monitoring,
        business_metrics,
        metrics as dd_metrics,
        trace_function,
        track_metric
    )

    # Initialize DataDog monitoring
    dd_result = setup_datadog_monitoring(app)
    logger.info(f"✅ DataDog monitoring initialized: {dd_result}")

    # Register Redis health check with DataDog
    if health_checker:
        async def check_redis():
            try:
                from services.redis_cache import redis_cache
                return await redis_cache.health_check()
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                return False
        health_checker.register_check("redis", check_redis)

except Exception as e:
    logger.warning(f"⚠️ DataDog monitoring not fully initialized: {e}")
    business_metrics = None
    dd_metrics = None

# ============================================================================
# CACHE-CONTROL MIDDLEWARE — Sets Cache-Control headers for mobile API responses
# Dashboard/pipeline: private, max-age=60 | Config: public, max-age=300
# User data (leads/loans/tasks): private, no-cache | Health: no-store
# ============================================================================
try:
    from middleware.cache_control import CacheControlMiddleware
    app.add_middleware(CacheControlMiddleware)
    logger.info("✅ Cache-Control middleware enabled (path-based response caching)")
except Exception as e:
    logger.warning(f"⚠️ Cache-Control middleware not loaded: {e}")

# ============================================================================
# CORS MIDDLEWARE — MUST be added LAST to be the absolute outermost middleware
# In Starlette/FastAPI, middleware is LIFO: last added = outermost = first to execute.
# This ensures CORS headers are present on ALL responses, including errors from
# inner middleware (rate limiting, IP blocking, security headers, etc.)
# ============================================================================
try:
    app.add_middleware(
        DynamicCORSMiddleware,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Accept", "Accept-Language", "Authorization", "Content-Language",
            "Content-Type", "Origin", "X-Requested-With", "X-CSRF-Token",
            "X-Request-ID", "X-Visitor-ID", "X-API-Key", "X-Impersonation-Token",
            "X-Mask-PII",
        ],
        expose_headers=[
            "Content-Length", "Content-Type", "X-Request-ID", "X-Response-Time",
            "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
        ],
        max_age=3600,
    )
    logger.info("✅ CORS middleware enabled")
except Exception as e:
    logger.warning(f"⚠️ CORS middleware not loaded: {e}")

# ============================================================================
# PII RESPONSE FILTER — Safety-net scan for SSN / account-number leaks
# Registered after CORS (LIFO: outermost, so it is the last filter on
# outgoing response bodies).  Default mode is "mask" in production so any
# accidental SSN in a JSON response is redacted before it reaches the client.
# Override per-environment with PII_RESPONSE_MODE env var.
# ============================================================================
try:
    from middleware.pii_response_filter import PIIResponseFilterMiddleware
    app.add_middleware(
        PIIResponseFilterMiddleware,
        mode=os.environ.get("PII_RESPONSE_MODE", "mask"),
    )
    logger.info("✅ PII response filter middleware enabled (mode=%s)",
                os.environ.get("PII_RESPONSE_MODE", "mask"))
except Exception as e:
    logger.warning(f"⚠️ PII response filter middleware not loaded: {e}")

# ============================================================================
# REQUEST CONTEXT MIDDLEWARE — Correlation IDs and structured request logging
# Added AFTER CORS so it is the absolute outermost middleware (LIFO order).
# Every request gets a unique X-Request-ID (generated or propagated from
# incoming header) stored in contextvars for automatic injection into all
# log records via RequestContextFilter.
# ============================================================================
try:
    from middleware.request_context import RequestContextMiddleware
    app.add_middleware(RequestContextMiddleware)
    logger.info("✅ Request context middleware enabled (correlation IDs + structured request logging)")
except Exception as e:
    logger.warning(f"⚠️ Request context middleware not loaded: {e}")

# ============================================================================
# SIGNAL HANDLERS — Cooperative shutdown with uvicorn
# ============================================================================
# Sets the shutdown flag on SIGTERM/SIGINT so health checks return 503 immediately.
# The actual cleanup runs in the @app.on_event("shutdown") handler below.
install_signal_handlers(graceful_shutdown)

# ============================================================================
# SECURITY CONFIGURATION VALIDATION
# ============================================================================
try:
    from security_config import validate_security_config
    security_issues = validate_security_config()
    if security_issues:
        for issue in security_issues:
            if issue.startswith("CRITICAL"):
                logger.error(f"🔴 Security: {issue}")
            else:
                logger.warning(f"🟡 Security: {issue}")
        logger.warning(f"⚠️ Security validation: {len(security_issues)} issue(s) found")
    else:
        logger.info("✅ Security configuration validated — all checks passed")
except Exception as e:
    logger.warning(f"⚠️ Security validation could not run: {e}")

# Mount static files directory for voicemail audio files
from pathlib import Path as PathLib
static_dir = PathLib("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
logger.info(f"✅ Static files mounted at /static from {static_dir.absolute()}")

# Mount reports directory for shareable HTML reports (no auth required)
reports_dir = PathLib("static/reports")
reports_dir.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(reports_dir), html=True), name="reports")
logger.info(f"✅ Reports mounted at /reports from {reports_dir.absolute()}")

# Mount uploads directory for MMS media files (Telnyx fetches these on send)
uploads_sms_dir = PathLib("uploads/sms")
uploads_sms_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/sms", StaticFiles(directory=str(uploads_sms_dir)), name="uploads_sms")
logger.info(f"✅ SMS uploads mounted at /uploads/sms from {uploads_sms_dir.absolute()}")

# Register standardized exception handlers for consistent error responses
try:
    from utils.error_handling import register_exception_handlers
    register_exception_handlers(app)
    logger.info("✅ Standardized exception handlers registered")
except Exception as e:
    logger.warning(f"⚠️ Exception handlers not registered: {e}")

# Auth - Define BEFORE importing routes that use these functions
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, user_id: int = None, tenant_id: str = None):
    """
    Create a JWT access token with enhanced security.

    Uses the new auth module for RS256 support, proper claims, and blacklist support.
    Falls back to legacy HS256 if auth module is not available.
    """
    if _USE_SECURE_TOKENS:
        # Use enhanced token with proper claims
        token_data = data.copy()
        if user_id:
            token_data["user_id"] = user_id
        if tenant_id:
            token_data["tenant_id"] = tenant_id
        return _create_secure_access_token(token_data)
    else:
        # Legacy fallback
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, user_id: int = None):
    """
    Create a JWT refresh token for session renewal.

    Refresh tokens have longer expiry and are used to get new access tokens.
    """
    if _USE_SECURE_TOKENS:
        token_data = data.copy()
        if user_id:
            token_data["user_id"] = user_id
        return _create_secure_refresh_token(token_data)
    else:
        # Legacy fallback - create a longer-lived token
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    request: Request = None,
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user with impersonation support

    Returns the impersonated user if X-Impersonation-Token header is present,
    otherwise returns the authenticated user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # First, authenticate the actual user (manager)
    actual_user = None

    # Check if token is an API key (starts with 'sk_' or 'pk_live_')
    if token.startswith('sk_') or token.startswith('pk_live_'):
        # Look up by SHA-256 hash first (migrated keys)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == token_hash,
            ApiKey.is_active == True
        ).first()

        # Fallback to plaintext for unmigrated keys
        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == token,
                ApiKey.is_active == True
            ).first()
            if api_key:
                # Auto-migrate: hash the key and clear plaintext
                api_key.key_hash = token_hash
                api_key.key_prefix = token[:8]
                api_key.key = None
                db.commit()

        if api_key is None:
            raise credentials_exception

        # Check API key expiration (Enterprise Check 4.11)
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        # Get the user associated with this API key
        actual_user = db.query(User).filter(User.id == api_key.user_id).first()
        if actual_user is None:
            raise credentials_exception

        # API key scope enforcement (Enterprise Check 4.11)
        # Store API key on request state for scope checking in require_scope()
        if request:
            request.state._api_key_obj = api_key

        # Automatic scope enforcement based on endpoint pattern
        if request and api_key.scopes:
            try:
                from auth.scope_enforcement import check_endpoint_scopes
                if not check_endpoint_scopes(request, api_key.scopes):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key lacks required scope for this endpoint",
                    )
            except ImportError:
                pass  # Scope enforcement module not available
            except HTTPException:
                raise

    else:
        # Otherwise, treat it as a JWT token
        if _USE_SECURE_TOKENS:
            # Use secure token verification with blacklist check
            token_data = _verify_secure_token(token, expected_type=TokenType.ACCESS)
            if not token_data:
                raise credentials_exception
            email = token_data.sub
        else:
            # Legacy fallback
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_aud": False})
                email: str = payload.get("sub")
                if email is None:
                    raise credentials_exception
            except JWTError:
                raise credentials_exception

        actual_user = db.query(User).filter(User.email == email).first()
        if actual_user is None:
            raise credentials_exception

    # PHASE 2: Check for impersonation
    if request:
        impersonation_token = request.headers.get("X-Impersonation-Token")

        if impersonation_token:
            # Validate impersonation session
            session = db.query(ImpersonationSession).filter(
                ImpersonationSession.session_token == impersonation_token,
                ImpersonationSession.is_active == True,
                ImpersonationSession.expires_at > datetime.now(timezone.utc),
                ImpersonationSession.manager_id == actual_user.id
            ).first()

            if session:
                # Return the impersonated user instead of the manager
                impersonated_user = db.query(User).filter(
                    User.id == session.impersonated_user_id
                ).first()

                if impersonated_user:
                    logger.info(f"Impersonation active: user {actual_user.id} → user {impersonated_user.id} (mode: {session.mode})")
                    # PHASE 3: Store impersonation info on request state for middleware
                    request.state.impersonation_session = session
                    request.state.impersonation_mode = session.mode
                    request.state.actual_user = actual_user
                    return impersonated_user

    # No impersonation, return actual user
    # Update last_activity_at (throttled to every 5 minutes to avoid excessive DB writes)
    try:
        now = datetime.now(timezone.utc)
        if actual_user.last_activity_at is None or (now - actual_user.last_activity_at).total_seconds() > 300:
            actual_user.last_activity_at = now
            db.commit()
    except Exception as e:
        logger.debug(f"Failed to update last_activity_at: {e}")
        db.rollback()

    return actual_user

async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Flexible authentication that supports both:
    1. Authorization: Bearer <token|api_key>
    2. X-API-Key: <api_key>

    This is useful for Zapier and other integrations.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None

    # Check X-API-Key header first (for Zapier and similar integrations)
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        # Look up by SHA-256 hash first (migrated keys)
        header_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == header_hash,
            ApiKey.is_active == True
        ).first()

        # Fallback to plaintext for unmigrated keys
        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == api_key_header,
                ApiKey.is_active == True
            ).first()
            if api_key:
                # Auto-migrate: hash the key and clear plaintext
                api_key.key_hash = header_hash
                api_key.key_prefix = api_key_header[:8]
                api_key.key = None
                db.commit()

        if api_key:
            # Check API key expiration
            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Update last used timestamp
            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

            # Store API key object for scope enforcement
            if hasattr(request, 'state'):
                request.state._api_key_obj = api_key

            # Enforce endpoint scopes if key has scopes assigned
            if api_key.scopes:
                try:
                    from auth.scope_enforcement import check_endpoint_scopes
                    if not check_endpoint_scopes(request, api_key.scopes):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="API key lacks required scope for this endpoint",
                        )
                except ImportError:
                    pass  # Scope enforcement module not available
                except HTTPException:
                    raise

            # Set tenant context for API key organization (CRITICAL for tenant isolation)
            if api_key.organization_id:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, api_key.organization_id)
                logger.info(f"API key tenant context set to org {api_key.organization_id}")

            # Get the user associated with this API key
            actual_user = db.query(User).filter(User.id == api_key.user_id).first()
            if actual_user:
                # Check for impersonation
                impersonation_token = request.headers.get("X-Impersonation-Token")
                if impersonation_token:
                    session = db.query(ImpersonationSession).filter(
                        ImpersonationSession.session_token == impersonation_token,
                        ImpersonationSession.is_active == True,
                        ImpersonationSession.expires_at > datetime.now(timezone.utc),
                        ImpersonationSession.manager_id == actual_user.id
                    ).first()

                    if session:
                        impersonated_user = db.query(User).filter(
                            User.id == session.impersonated_user_id
                        ).first()

                        if impersonated_user:
                            logger.info(f"Impersonation active (API key): user {actual_user.id} → user {impersonated_user.id} (mode: {session.mode})")
                            # PHASE 3: Store impersonation info on request state for middleware
                            request.state.impersonation_session = session
                            request.state.impersonation_mode = session.mode
                            request.state.actual_user = actual_user
                            return impersonated_user

                return actual_user

        # If we have X-API-Key header but it's invalid, raise exception
        raise credentials_exception

    # Check Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")

    if not token:
        raise credentials_exception

    # Check if token is an API key (starts with 'sk_' or 'pk_live_')
    if token.startswith('sk_') or token.startswith('pk_live_'):
        # Look up by SHA-256 hash first (migrated keys)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == token_hash,
            ApiKey.is_active == True
        ).first()

        # Fallback to plaintext for unmigrated keys
        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == token,
                ApiKey.is_active == True
            ).first()
            if api_key:
                # Auto-migrate: hash the key and clear plaintext
                api_key.key_hash = token_hash
                api_key.key_prefix = token[:8]
                api_key.key = None
                db.commit()

        if api_key is None:
            raise credentials_exception

        # Check API key expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        # Store API key object for scope enforcement
        if hasattr(request, 'state'):
            request.state._api_key_obj = api_key

        # Enforce endpoint scopes if key has scopes assigned
        if api_key.scopes:
            try:
                from auth.scope_enforcement import check_endpoint_scopes
                if not check_endpoint_scopes(request, api_key.scopes):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key lacks required scope for this endpoint",
                    )
            except ImportError:
                pass  # Scope enforcement module not available
            except HTTPException:
                raise

        # Get the user associated with this API key
        actual_user = db.query(User).filter(User.id == api_key.user_id).first()
        if actual_user is None:
            raise credentials_exception

        # Check for impersonation
        impersonation_token = request.headers.get("X-Impersonation-Token")
        if impersonation_token:
            session = db.query(ImpersonationSession).filter(
                ImpersonationSession.session_token == impersonation_token,
                ImpersonationSession.is_active == True,
                ImpersonationSession.expires_at > datetime.now(timezone.utc),
                ImpersonationSession.manager_id == actual_user.id
            ).first()

            if session:
                impersonated_user = db.query(User).filter(
                    User.id == session.impersonated_user_id
                ).first()

                if impersonated_user:
                    logger.info(f"Impersonation active (Bearer API key): user {actual_user.id} → user {impersonated_user.id} (mode: {session.mode})")
                    # PHASE 3: Store impersonation info on request state for middleware
                    request.state.impersonation_session = session
                    request.state.impersonation_mode = session.mode
                    request.state.actual_user = actual_user
                    return impersonated_user

        return actual_user

    # Otherwise, treat it as a JWT token
    if _USE_SECURE_TOKENS:
        # Use secure token verification with blacklist check (same as get_current_user)
        token_data = _verify_secure_token(token, expected_type=TokenType.ACCESS)
        if not token_data:
            raise credentials_exception
        email = token_data.sub
    else:
        # Legacy fallback
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_aud": False})
            email: str = payload.get("sub")
            if email is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

    actual_user = db.query(User).filter(User.email == email).first()
    if actual_user is None:
        raise credentials_exception

    # PHASE 3: Check for impersonation (same logic as get_current_user)
    impersonation_token = request.headers.get("X-Impersonation-Token")
    if impersonation_token:
        # Validate impersonation session
        session = db.query(ImpersonationSession).filter(
            ImpersonationSession.session_token == impersonation_token,
            ImpersonationSession.is_active == True,
            ImpersonationSession.expires_at > datetime.now(timezone.utc),
            ImpersonationSession.manager_id == actual_user.id
        ).first()

        if session:
            # Return the impersonated user instead of the manager
            impersonated_user = db.query(User).filter(
                User.id == session.impersonated_user_id
            ).first()

            if impersonated_user:
                logger.info(f"Impersonation active (flexible): user {actual_user.id} → user {impersonated_user.id} (mode: {session.mode})")
                # PHASE 3: Store impersonation info on request state for middleware
                request.state.impersonation_session = session
                request.state.impersonation_mode = session.mode
                request.state.actual_user = actual_user
                return impersonated_user

    # No impersonation, return actual user
    return actual_user

# ============================================================================
# MISSION CONTROL - AI ACTION LOGGING HELPER
# ============================================================================

async def log_ai_action_to_mission_control(
    db: Session,
    agent_name: str,
    action_type: str,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    user_id: Optional[int] = None,
    context: Optional[dict] = None,
    reasoning: Optional[str] = None,
    confidence_score: Optional[float] = None,
    autonomy_level: str = "assisted",
    required_approval: bool = False,
    status: str = "pending",
    outcome: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Optional[str]:
    """
    Helper function to log AI actions to Mission Control for tracking
    Returns the action_id if successful, None if failed
    """
    try:
        import time

        # Generate unique action ID
        action_id = f"{agent_name.lower().replace(' ', '_')}_{int(time.time() * 1000)}"

        # Create action record
        action = AIColleagueAction(
            action_id=action_id,
            agent_name=agent_name,
            action_type=action_type,
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=user_id,
            context=context,
            trigger_type="user_request",
            confidence_score=confidence_score,
            reasoning=reasoning,
            autonomy_level=autonomy_level,
            required_approval=required_approval,
            status=status,
            outcome=outcome,
            executed_at=datetime.now(timezone.utc) if status == "completed" else None,
            completed_at=datetime.now(timezone.utc) if outcome else None,
            action_metadata=metadata
        )

        db.add(action)
        db.commit()

        logger.info(f"✅ Mission Control: Logged {agent_name} action {action_id}")
        return action_id

    except Exception as e:
        logger.error(f"❌ Failed to log AI action to Mission Control: {e}")
        db.rollback()
        return None

async def update_ai_action_outcome(
    db: Session,
    action_id: str,
    outcome: str,
    impact_score: Optional[float] = None,
    customer_response: Optional[str] = None,
    metadata: Optional[dict] = None
) -> bool:
    """
    Update the outcome of a Mission Control action
    """
    try:
        action = db.query(AIColleagueAction).filter(
            AIColleagueAction.action_id == action_id
        ).first()

        if action:
            action.outcome = outcome
            action.completed_at = datetime.now(timezone.utc)
            action.status = "completed"

            if impact_score is not None:
                action.impact_score = impact_score
            if customer_response:
                action.customer_response = customer_response
            if metadata:
                action.action_metadata = {**(action.action_metadata or {}), **metadata}

            db.commit()
            logger.info(f"✅ Mission Control: Updated action {action_id} outcome to {outcome}")
            return True
        else:
            logger.warning(f"⚠️  Mission Control: Action {action_id} not found")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to update AI action outcome: {e}")
        db.rollback()
        return False

# ============================================================================
# APP VERSION CHECK ROUTES - Mobile forced update & maintenance mode
# ============================================================================
try:
    from routes.app_version_routes import register_app_version_routes
    register_app_version_routes(app=app)
    logger.info("✅ App version check routes loaded (no-auth version gate)")
except Exception as e:
    logger.error(f"❌ App version check routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# API GATEWAY ROUTES - Enterprise Domain 11
# ============================================================================
try:
    from routes.api_gateway_routes import register_api_gateway_routes
    register_api_gateway_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ API Gateway routes loaded (Domain 11: API Key CRUD, Webhooks, Rate Limiting)")
except Exception as e:
    logger.error(f"❌ API Gateway routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TENANT LIFECYCLE ROUTES - Provisioning & Lifecycle (D3)
# ============================================================================
try:
    from routes.tenant_lifecycle_routes import register_tenant_lifecycle_routes
    register_tenant_lifecycle_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Tenant lifecycle routes loaded (signup, provision, export, suspend, hard-delete)")
except Exception as e:
    logger.error(f"❌ Tenant lifecycle routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# BILLING ADMIN ROUTES - Licensing & Subscription (D2)
# ============================================================================
try:
    from routes.billing_admin_routes import register_billing_admin_routes
    register_billing_admin_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Billing admin routes loaded (Stripe, subscriptions, invoices)")
except Exception as e:
    logger.error(f"❌ Billing admin routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# EMAIL TEMPLATE ROUTES - White-Label (WL-003)
# ============================================================================
try:
    from routes.email_template_routes import register_email_template_routes
    register_email_template_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Email template routes loaded (per-tenant template editor)")
except Exception as e:
    logger.error(f"❌ Email template routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# LEGAL DOCUMENT ROUTES - White-Label (WL-007)
# ============================================================================
try:
    from routes.legal_document_routes import register_legal_document_routes
    register_legal_document_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Legal document routes loaded (T&C, Privacy Policy management)")
except Exception as e:
    logger.error(f"❌ Legal document routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# REGULATORY REPORT ROUTES - Compliance (CMP-008)
# ============================================================================
try:
    from routes.regulatory_report_routes import register_regulatory_report_routes
    register_regulatory_report_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Regulatory report routes loaded (HMDA LAR, state filings)")
except Exception as e:
    logger.error(f"❌ Regulatory report routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# REPORT EXPORT & PERFORMANCE MONITORING ROUTES (Enterprise Readiness Domain 6 + 9)
# ============================================================================
try:
    from routes.report_export_routes import register_report_export_routes
    register_report_export_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Report export & performance monitoring routes loaded (PDF, Excel, SLA compliance, scheduled delivery)")
except Exception as e:
    logger.error(f"❌ Report export routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# AUDIT REPORT SHARE ROUTES (Public HTML audit report pages)
# ============================================================================
try:
    from routes.audit_report_routes import register_audit_report_routes
    register_audit_report_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Audit report share routes loaded (public HTML report pages)")
except Exception as e:
    logger.error(f"❌ Audit report share routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# API DEVELOPER EXPERIENCE ROUTES (Enterprise Readiness Domain 11)
# ============================================================================
try:
    from routes.api_developer_routes import register_api_developer_routes
    register_api_developer_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ API developer routes loaded (changelog, SDK, Postman, sandbox, webhooks)")
except Exception as e:
    logger.error(f"❌ API developer routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# ENTERPRISE READINESS ROUTES (Domains 3, 4, 5, 7, 9, 10, 12)
# ============================================================================
try:
    from routes.enterprise_readiness_routes import register_enterprise_readiness_routes
    register_enterprise_readiness_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Enterprise readiness routes loaded (data quality, security, onboarding, white-label, import templates)")
except Exception as e:
    logger.error(f"❌ Enterprise readiness routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# OPS MANAGER ROUTES - Pipeline Sweep & Impediment Detection
# ============================================================================
try:
    from routes.ops_manager_routes import register_ops_manager_routes
    register_ops_manager_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user_flexible
    )
    logger.info("✅ Ops Manager routes loaded (sweep, summary, history)")
except Exception as e:
    logger.error(f"❌ Ops Manager routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# ENCOMPASS LOS INTEGRATION ROUTES
# ============================================================================
try:
    from routes.encompass_integration_routes import register_encompass_integration_routes
    register_encompass_integration_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("Encompass LOS integration routes loaded (connect, sync, search, import)")
except Exception as e:
    logger.error(f"Encompass integration routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# GDPR / CCPA DATA PRIVACY ROUTES (Export, Deletion, DSAR)
# ============================================================================
try:
    from routes.gdpr_routes import register_gdpr_routes
    register_gdpr_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("GDPR/CCPA data privacy routes loaded (export, deletion, DSAR)")
except Exception as e:
    logger.error(f"GDPR routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# SMART DOCS V2 ROUTES (Intelligence, Income, Review, Follow-up, Security,
#                        Bank Analysis, Analytics, Portal, E-Signature)
# ============================================================================
try:
    from routes.smart_docs_v2_registration import register_smart_docs_v2_routes
    register_smart_docs_v2_routes(app=app)
    logger.info("✅ Smart Docs V2 routes loaded (intelligence, income, review, followup, security, bank-analysis, analytics, portal, esign)")
except Exception as e:
    logger.error(f"❌ Smart Docs V2 routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# ENTERPRISE DOCUMENTATION PORTAL ROUTES
# ============================================================================
try:
    from routes.enterprise_documentation_routes import register_enterprise_documentation_routes
    register_enterprise_documentation_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Enterprise Documentation Portal routes loaded (content, search, analytics)")
except Exception as e:
    logger.error(f"❌ Enterprise Documentation Portal routes failed to load: {e}")
    import traceback
    traceback.print_exc()

try:
    from routes.enterprise_documentation_admin_routes import register_content_management_routes
    register_content_management_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Enterprise Documentation Admin routes loaded (content management)")
except Exception as e:
    logger.error(f"❌ Enterprise Documentation Admin routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# SOC 2 TYPE II COMPLIANCE ROUTES
# ============================================================================
try:
    from soc2_compliance.api.router import soc2_router
    app.include_router(soc2_router, prefix="/api/v1/compliance", tags=["SOC 2 Compliance"])
    logger.info("✅ SOC 2 compliance routes loaded (audit, incidents, dashboard)")
except Exception as e:
    logger.error(f"SOC 2 compliance routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# VOICE AI RECEPTIONIST ROUTES
# ============================================================================
try:
    from routes.voice_ai_receptionist_routes import webhook_router, sms_router, debug_router
    app.include_router(webhook_router, tags=["Voice Webhooks"])
    app.include_router(sms_router, tags=["SMS Messaging"])
    app.include_router(debug_router, tags=["Debug"])
    logger.info("✅ Voice AI Receptionist sub-routes loaded (webhooks, SMS, debug)")
except Exception as e:
    logger.error(f"❌ Voice AI Receptionist routes failed to load: {e}")
    import traceback
    traceback.print_exc()

try:
    from ai_receptionist_dashboard_routes import router as ai_receptionist_dashboard_router
    app.include_router(ai_receptionist_dashboard_router, tags=["AI Receptionist Dashboard"])
    logger.info("✅ AI Receptionist Dashboard routes loaded")
except Exception as e:
    logger.error(f"❌ AI Receptionist Dashboard routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# CALL QUEUE ROUTES
# ============================================================================
try:
    from routes.call_queue_routes import router as call_queue_router
    app.include_router(call_queue_router, tags=["Call Queues"])
    logger.info("✅ Call Queue routes loaded")
except Exception as e:
    logger.error(f"❌ Call Queue routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# BORROWER APPLICATION ROUTES
# ============================================================================
try:
    from routes.borrower_application_routes import router as borrower_application_router
    app.include_router(borrower_application_router, tags=["Borrower Applications"])
    logger.info("Borrower Application routes loaded")
except Exception as e:
    logger.error(f"Borrower Application routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# AI PROSPECT RE-ENGAGEMENT ROUTES
# ============================================================================
try:
    from routes.prospect_reengagement_routes import router as prospect_reengagement_router
    app.include_router(prospect_reengagement_router, tags=["Prospect Re-Engagement"])
    logger.info("AI Prospect Re-Engagement routes loaded")

    # Create tables if needed
    try:
        from database.models.ai_prospect_conversation import create_tables_if_needed
        from db import engine
        create_tables_if_needed(engine)
    except Exception as e:
        logger.warning(f"AI Re-Engagement table creation skipped: {e}")
except Exception as e:
    logger.error(f"AI Prospect Re-Engagement routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# BOOKING BRANDING ROUTES (public org-branded booking pages)
# ============================================================================
try:
    from routes.booking_branding_routes import register_booking_branding_routes
    register_booking_branding_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("Booking branding routes loaded (public org pages, admin branding)")
except Exception as e:
    logger.warning(f"Booking branding routes skipped: {e}")

# ============================================================================
# ENTERPRISE HARDENING ROUTES (March 2026 sprint)
# ============================================================================

# TCPA Consent Management
try:
    from routes.tcpa_consent_routes import router as tcpa_consent_router
    app.include_router(tcpa_consent_router, tags=["TCPA Compliance"])
    logger.info("TCPA Consent routes loaded")
except Exception as e:
    logger.warning(f"TCPA Consent routes skipped: {e}")

# Credit Bureau Monitoring & Recapture Intelligence
try:
    from routes.credit_monitoring_routes import router as credit_monitoring_router
    app.include_router(credit_monitoring_router, tags=["Credit Monitoring"])
    logger.info("Credit Monitoring routes loaded")
except Exception as e:
    logger.warning(f"Credit Monitoring routes skipped: {e}")

# Content Governance (marketing compliance approval workflows)
try:
    from routes.content_governance_routes import router as content_governance_router
    app.include_router(content_governance_router, tags=["Content Governance"])
    logger.info("Content Governance routes loaded")
except Exception as e:
    logger.warning(f"Content Governance routes skipped: {e}")

# Scheduling Intelligence — Continuous Learning System
try:
    from routes.scheduling_intelligence_routes import router as scheduling_intelligence_router
    app.include_router(scheduling_intelligence_router, tags=["Scheduling Intelligence"])
    logger.info("Scheduling Intelligence routes loaded")
except Exception as e:
    logger.warning(f"Scheduling Intelligence routes skipped: {e}")

# SOC 2 Compliance Admin Dashboard
try:
    from routes.soc2_compliance_routes import router as soc2_admin_router
    app.include_router(soc2_admin_router, tags=["SOC 2 Admin"])
    logger.info("SOC 2 Compliance admin routes loaded")
except Exception as e:
    logger.warning(f"SOC 2 Compliance admin routes skipped: {e}")

# SOC 2 Security Training Tracking (CC1.4 evidence)
try:
    from routes.security_training_routes import router as security_training_router
    app.include_router(security_training_router, tags=["SOC 2 Training"])
    logger.info("Security training routes loaded")
except Exception as e:
    logger.warning(f"Security training routes skipped: {e}")

# ============================================================================
# PIPELINE APPOINTMENT TRIGGER ROUTES — Auto-schedule from stage changes
# ============================================================================
try:
    from routes.pipeline_appointment_routes import register_pipeline_appointment_routes
    register_pipeline_appointment_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("Pipeline appointment trigger routes loaded")
except Exception as e:
    logger.warning(f"Pipeline appointment trigger routes skipped: {e}")

# ============================================================================
# PIPELINE ALERTS ROUTES — Mobile dashboard urgent alerts
# ============================================================================
try:
    from routes.pipeline_alerts_routes import router as pipeline_alerts_router
    app.include_router(pipeline_alerts_router, tags=["Pipeline Alerts"])
    logger.info("Pipeline alerts routes loaded")
except Exception as e:
    logger.warning(f"Pipeline alerts routes skipped: {e}")

# ============================================================================
# MOBILE TASKS ROUTES — Real tasks table for mobile dashboard
# ============================================================================
try:
    from routes.mobile_tasks_routes import router as mobile_tasks_router
    app.include_router(mobile_tasks_router, tags=["Mobile Tasks"])
    logger.info("Mobile tasks routes loaded")
except Exception as e:
    logger.warning(f"Mobile tasks routes not loaded: {e}")

# ============================================================================
# TASK SNOOZE ROUTES — PATCH /api/v1/tasks/{task_id}/snooze for iOS push actions
# ============================================================================
try:
    from routes.task_snooze_routes import router as task_snooze_router
    app.include_router(task_snooze_router, tags=["Tasks"])
    logger.info("Task snooze routes loaded")
except Exception as e:
    logger.warning(f"Task snooze routes not loaded: {e}")

# ============================================================================
# MOBILE ANALYTICS ROUTES — Log-sink for frontend mobileAnalytics.js
# ============================================================================
try:
    from routes.mobile_analytics_routes import router as mobile_analytics_router
    app.include_router(mobile_analytics_router, tags=["Mobile Analytics"])
    logger.info("Mobile analytics routes loaded")
except Exception as e:
    logger.warning(f"Mobile analytics routes not loaded: {e}")

# ============================================================================
# MOBILE DASHBOARD ROUTES — Proxy endpoints for iOS PerenniaWidget
# ============================================================================
try:
    from routes.mobile_dashboard_routes import router as mobile_dashboard_router
    app.include_router(mobile_dashboard_router, tags=["Mobile Dashboard"])
    logger.info("Mobile dashboard routes loaded")
except Exception as e:
    logger.warning(f"Mobile dashboard routes not loaded: {e}")

# ============================================================================
# MOBILE NOTIFICATION ROUTES — Notifications for iOS VisionPro + mobile app
# ============================================================================
try:
    from routes.mobile_notification_routes import router as mobile_notification_router
    app.include_router(mobile_notification_router, tags=["Mobile Notifications"])
    logger.info("Mobile notification routes loaded")
except Exception as e:
    logger.warning(f"Mobile notification routes not loaded: {e}")

# ============================================================================
# MOBILE SYNC ROUTES — Offline sync queue for mobile clients
# ============================================================================
try:
    from routes.mobile_sync_routes import router as mobile_sync_router
    app.include_router(mobile_sync_router, tags=["Mobile Sync"])
    logger.info("Mobile sync routes loaded")
except Exception as e:
    logger.warning(f"Mobile sync routes not loaded: {e}")

# ============================================================================
# VOICE PROFILE ROUTES — Aria voice enrollment, verification, GDPR delete
# ============================================================================
try:
    from routes.voice_profile_routes import router as voice_profile_router
    app.include_router(voice_profile_router, tags=["Voice Profile"])
    logger.info("Voice profile routes loaded")
except Exception as e:
    logger.warning(f"Voice profile routes not loaded: {e}")

try:
    from mobile_voice_routes import router as mobile_voice_router
    app.include_router(mobile_voice_router, tags=["Mobile Voice"])
    logger.info("Mobile voice routes loaded (ElevenLabs TTS)")
except Exception as e:
    logger.warning(f"Mobile voice routes not loaded: {e}")

# ============================================================================
# LIVEKIT VOICE ROUTES — LiveKit WebRTC token provisioning for Aria voice
# ============================================================================
try:
    from routes.livekit_routes import router as livekit_router
    app.include_router(livekit_router, tags=["LiveKit Voice"])
    logger.info("LiveKit voice routes loaded")
except Exception as e:
    logger.warning(f"LiveKit voice routes not loaded: {e}")

# ============================================================================
# ARIA CHAT ROUTES — Conversational intelligence (WebSocket + REST)
# ============================================================================
try:
    from routes.aria_chat_routes import router as aria_chat_router
    app.include_router(aria_chat_router, tags=["Aria Chat"])
    logger.info("Aria chat routes loaded")
except Exception as e:
    logger.warning(f"Aria chat routes not loaded: {e}")

# ============================================================================
# SCHEDULER ENHANCEMENT ROUTES (March 2026 sprint)
# ============================================================================

# Audit trail routes (scheduler compliance logging)
try:
    from routes.audit_routes import router as audit_router, set_dependencies as audit_set_deps
    audit_set_deps(get_db, get_current_user, {})
    app.include_router(audit_router, prefix="/api/v1/scheduler", tags=["Scheduler Audit"])
    logger.info("Scheduler audit routes loaded")
except Exception as e:
    logger.warning(f"Scheduler audit routes skipped: {e}")

# Scheduling rules engine routes
try:
    from routes.scheduler_rules_routes import router as rules_router, set_dependencies as rules_set_deps
    rules_set_deps(get_db, get_current_user, {})
    app.include_router(rules_router, prefix="/api/v1/scheduler", tags=["Scheduling Rules"])
    logger.info("Scheduling rules routes loaded")
except Exception as e:
    logger.warning(f"Scheduling rules routes skipped: {e}")

# Slot hold routes (TTL-based reservation during AI conversations)
try:
    from routes.slot_hold_routes import router as slot_hold_router, set_dependencies as hold_set_deps
    hold_set_deps(get_db, get_current_user, {})
    app.include_router(slot_hold_router, prefix="/api/v1/scheduler", tags=["Slot Holds"])
    logger.info("Slot hold routes loaded")
except Exception as e:
    logger.warning(f"Slot hold routes skipped: {e}")

# Scheduling optimizer routes (AI-powered slot ranking)
try:
    from routes.scheduling_optimizer_routes import router as optimizer_router, set_dependencies as opt_set_deps
    opt_set_deps(get_db, get_current_user)
    app.include_router(optimizer_router, prefix="/api/v1/scheduler", tags=["Scheduling Optimizer"])
    logger.info("Scheduling optimizer routes loaded")
except Exception as e:
    logger.warning(f"Scheduling optimizer routes skipped: {e}")

# AI outbound calling routes
try:
    from routes.ai_outbound_routes import router as ai_outbound_router
    app.include_router(ai_outbound_router, tags=["AI Outbound Calling"])
    logger.info("AI outbound calling routes loaded")
except Exception as e:
    logger.warning(f"AI outbound calling routes skipped: {e}")

# SMS scheduler webhook routes
try:
    from routes.sms_scheduler_webhook import router as sms_sched_router, set_dependencies as sms_set_deps
    sms_set_deps(get_db, {})
    app.include_router(sms_sched_router, prefix="/api/v1/scheduler", tags=["Scheduler SMS"])
    logger.info("SMS scheduler webhook routes loaded")
except Exception as e:
    logger.warning(f"SMS scheduler webhook routes skipped: {e}")

# No-show recovery opt-out routes
try:
    from routes.recovery_opt_out_routes import router as recovery_router, set_dependencies as recovery_set_deps
    recovery_set_deps(get_current_user_func=get_current_user)
    app.include_router(recovery_router, prefix="/api/v1/scheduler", tags=["No-Show Recovery"])
    logger.info("Recovery opt-out routes loaded")
except Exception as e:
    logger.warning(f"Recovery opt-out routes skipped: {e}")

# Scheduler analytics routes (conversion funnel, source performance)
try:
    from routes.scheduler_analytics_routes import router as sched_analytics_router
    app.include_router(sched_analytics_router, tags=["Scheduler Analytics"])
    logger.info("Scheduler analytics routes loaded")
except Exception as e:
    logger.warning(f"Scheduler analytics routes skipped: {e}")

# Capacity dashboard routes (team scheduling load)
try:
    from routes.capacity_dashboard_routes import register_capacity_dashboard_routes
    register_capacity_dashboard_routes(app, get_current_user, {})
    logger.info("Capacity dashboard routes loaded")
except Exception as e:
    logger.warning(f"Capacity dashboard routes skipped: {e}")

# API V2 routes (cursor pagination, RFC 7807 errors)
try:
    from routes.api_v2 import v2_router
    app.include_router(v2_router, tags=["API V2"])
    logger.info("API V2 routes loaded")
except Exception as e:
    logger.warning(f"API V2 routes skipped: {e}")

# ============================================================================
# APP BRANDING ROUTES (per-org white-label config for the main React app)
# ============================================================================
try:
    from routes.branding_routes import register_branding_routes
    register_branding_routes(
        app=app,
        get_db_func=get_db,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("App branding routes loaded")
except Exception as e:
    logger.warning(f"App branding routes skipped: {e}")

# ============================================================================
# CUSTOM DOMAIN MANAGEMENT ROUTES
# ============================================================================
try:
    from routes.custom_domain_routes import register_custom_domain_routes
    register_custom_domain_routes(
        app=app,
        get_db_func=get_db,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("Custom domain routes loaded")
except Exception as e:
    logger.warning(f"Custom domain routes skipped: {e}")

# ============================================================================
# DB MIGRATION ROUTES
# DISABLED: Schema mutations must not be exposed via HTTP (security audit March 2026)
# ============================================================================
# try:
#     from routes.db_migration_routes import register_db_migration_routes
#     register_db_migration_routes(
#         app=app,
#         get_db=get_db,
#         get_current_user=get_current_user
#     )
#     logger.info("✅ DB migration routes loaded")
# except Exception as e:
#     logger.error(f"❌ DB migration routes failed to load: {e}")
#     import traceback
#     traceback.print_exc()

# ============================================================================
# EXPERIMENTAL MODULE ROUTES
# ARCHIVED: Experimental modules frozen - no SLA (March 2026)
# ============================================================================
# DEPRECATED: Experimental feature deregistered
# try:
#     from routes.decision_lab_routes import register_decision_lab_routes
#     register_decision_lab_routes(app=app, get_db=get_db, get_current_user=get_current_user)
#     logger.info("✅ Decision Lab routes loaded")
# except Exception as e:
#     logger.error(f"❌ Decision Lab routes failed to load: {e}")
#
# DEPRECATED: Experimental feature deregistered
# try:
#     from routes.circle_of_cashflow_routes import register_circle_of_cashflow_routes
#     register_circle_of_cashflow_routes(app=app, get_db=get_db, get_current_user=get_current_user)
#     logger.info("✅ Circle of Cashflow routes loaded")
# except Exception as e:
#     logger.error(f"❌ Circle of Cashflow routes failed to load: {e}")
#
# DEPRECATED: Premium feature deregistered — not yet launched
# try:
#     from routes.hr_management_routes import register_hr_management_routes
#     register_hr_management_routes(app=app, get_db=get_db, get_current_user=get_current_user)
#     logger.info("✅ HR Management routes loaded")
# except Exception as e:
#     logger.error(f"❌ HR Management routes failed to load: {e}")
#
# try:
#     from routes.it_helpdesk_routes import register_it_helpdesk_routes
#     register_it_helpdesk_routes(app=app, get_db=get_db, get_current_user=get_current_user)
#     logger.info("✅ IT Helpdesk routes loaded")
# except Exception as e:
#     logger.error(f"❌ IT Helpdesk routes failed to load: {e}")
#
# DEPRECATED: Experimental feature deregistered
# try:
#     from routes.avatar_studio_routes import register_avatar_studio_routes
#     register_avatar_studio_routes(app=app, get_db=get_db, get_current_user=get_current_user)
#     logger.info("✅ Avatar Studio routes loaded")
# except Exception as e:
#     logger.error(f"❌ Avatar Studio routes failed to load: {e}")

# Lead Assignment Configuration routes
try:
    from routes.lead_assignment_routes import router as lead_assignment_router, set_dependencies as set_lead_assign_deps
    from database.models import User as _UserModel
    set_lead_assign_deps(_UserModel, get_current_user, get_db)
    app.include_router(lead_assignment_router, tags=["Lead Assignment"])
    logger.info("✅ Lead Assignment routes loaded")
except Exception as e:
    logger.warning(f"⚠️ Lead Assignment routes not loaded: {e}")

# Morning Briefing routes
try:
    from routes.briefing_routes import router as briefing_router, set_dependencies as set_briefing_deps
    set_briefing_deps(get_db, get_current_user)
    app.include_router(briefing_router, tags=["Morning Briefing"])
    logger.info("✅ Morning Briefing routes loaded")
except Exception as e:
    logger.warning(f"⚠️ Morning Briefing routes not loaded: {e}")

# Voice Workflow Monitoring routes
try:
    from routes.voice_workflow_monitoring_routes import router as voice_workflow_router
    app.include_router(voice_workflow_router)
    logger.info("✅ Voice Workflow Monitoring routes loaded")
except Exception as e:
    logger.warning(f"⚠️ Voice Workflow Monitoring routes not loaded: {e}")

# ============================================================================
# BULK SMS CAMPAIGN ROUTES
# ============================================================================
try:
    from routes.bulk_sms_routes import router as bulk_sms_router
    app.include_router(bulk_sms_router, tags=["Bulk SMS"])
    logger.info("Bulk SMS campaign routes loaded")
except Exception as e:
    logger.warning(f"Bulk SMS campaign routes skipped: {e}")

# ============================================================================
# SMS CONVERSATION ROUTES (two-way SMS panel)
# ============================================================================
try:
    from routes.sms_conversation_routes import router as sms_conv_router, ws_router as sms_ws_router
    app.include_router(sms_conv_router, tags=["SMS Conversations"])
    app.include_router(sms_ws_router, tags=["SMS WebSocket"])
    logger.info("✅ SMS conversation routes loaded (REST + WebSocket)")
except Exception as e:
    logger.warning(f"SMS conversation routes skipped: {e}")

# ============================================================================
# APP VERSION COMPATIBILITY ROUTES (unauthenticated — mobile pre-login)
# ============================================================================
try:
    from routes.app_compatibility_routes import router as app_compatibility_router
    app.include_router(app_compatibility_router, tags=["App Compatibility"])
    logger.info("✅ App Compatibility routes loaded")
except Exception as e:
    logger.warning(f"⚠️ App Compatibility routes not loaded: {e}")

# ============================================================================
# AI AGENT FEEDBACK ROUTES
# ============================================================================
try:
    from routes.agent_feedback_routes import register_agent_feedback_routes
    register_agent_feedback_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Agent feedback routes loaded")
except Exception as e:
    logger.warning(f"Agent feedback routes skipped: {e}")

# ============================================================================
# AUTONOMOUS AI AGENT TASK ROUTES
# ============================================================================
try:
    from routes.autonomous_task_routes import register_autonomous_task_routes
    register_autonomous_task_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Autonomous task routes loaded")
except Exception as e:
    logger.warning(f"Autonomous task routes skipped: {e}")

# ============================================================================
# AGGREGATE ROUTE REGISTRATIONS — Auth, Security, Settings, Telephony, etc.
# These _register_*.py files are aggregators that load many sub-route modules.
# ============================================================================

# --- Auth & Security (CSRF, SSO, MFA, org routes, public routes) ---
try:
    from routes._register_auth_security import register_auth_security_routes
    register_auth_security_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        oauth2_scheme=oauth2_scheme,
    )
    logger.info("Auth & security routes loaded")
except Exception as e:
    logger.warning(f"Auth & security routes failed to load: {e}")

# --- Settings & Configuration (user settings, profile, lead capture, branding) ---
try:
    from routes._register_settings import register_settings_routes
    register_settings_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        pwd_context=pwd_context,
    )
    logger.info("Settings routes loaded")
except Exception as e:
    logger.warning(f"Settings routes failed to load: {e}")

# --- Telephony & Voice (Telnyx, Vapi, AMD, IVR, dialer, voice workflows) ---
try:
    from routes._register_telephony import register_telephony_routes
    register_telephony_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("Telephony routes loaded")
except Exception as e:
    logger.warning(f"Telephony routes failed to load: {e}")

# --- Video & Media (meetings, clips, carousel, content marketing) ---
try:
    from routes._register_video_media import register_video_media_routes
    register_video_media_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        pwd_context=pwd_context,
    )
    logger.info("Video & media routes loaded")
except Exception as e:
    logger.warning(f"Video & media routes failed to load: {e}")

# --- Documents & Income (smart docs, income extraction, bank statements) ---
try:
    from routes._register_documents_income import register_documents_income_routes
    register_documents_income_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("Documents & income routes loaded")
except Exception as e:
    logger.warning(f"Documents & income routes failed to load: {e}")

# --- AI & ML (orchestrator chat, underwriter, streaming, knowledge base) ---
try:
    from routes._register_ai_routes import register_ai_routes
    register_ai_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        log_ai_action_to_mission_control=log_ai_action_to_mission_control,
        update_ai_action_outcome=update_ai_action_outcome,
    )
    logger.info("AI & ML routes loaded")
except Exception as e:
    logger.warning(f"AI & ML routes failed to load: {e}")

# --- Third-Party Integrations (Salesforce, Microsoft, Google, Zoom, Slack) ---
try:
    from routes._register_integrations import register_integration_routes
    register_integration_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        scheduler=scheduler,
    )
    logger.info("Integration routes loaded")
except Exception as e:
    logger.warning(f"Integration routes failed to load: {e}")

# --- Recruiting (engine, grading, DISC, workflow, dialer, portal) ---
try:
    from routes._register_recruiting import register_recruiting_routes
    register_recruiting_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("Recruiting routes loaded")
except Exception as e:
    logger.warning(f"Recruiting routes failed to load: {e}")

# ============================================================================
# CORE CRM ROUTES — Leads, Search, MUM, Email, Compliance
# ============================================================================

# --- Health & system status ---
try:
    from routes.health_routes import register_health_routes
    register_health_routes(app=app, get_db=get_db, SessionLocal=SessionLocal)
    logger.info("Health routes loaded")
except Exception as e:
    logger.warning(f"Health routes failed to load: {e}")

# --- Leads detail (bulk ops, individual CRUD by ID, claim-orphans) ---
try:
    from routes.leads_detail_routes import register_leads_detail_routes
    register_leads_detail_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("Leads detail routes loaded")
except Exception as e:
    logger.warning(f"Leads detail routes failed to load: {e}")

# --- Global search (cross-entity: leads, loans, contacts, partners) ---
try:
    from routes.search_routes import register_search_routes
    from routes.permission_core_routes import filter_leads_by_permissions
    register_search_routes(
        app=app,
        get_db=get_db,
        get_current_user_flexible=get_current_user_flexible,
        Lead=Lead,
        Loan=Loan,
        LoanTeamMember=LoanTeamMember,
        ReferralPartner=ReferralPartner,
        MUMClient=MUMClient,
        filter_leads_by_permissions=filter_leads_by_permissions,
    )
    logger.info("Search routes loaded")
except Exception as e:
    logger.warning(f"Search routes failed to load: {e}")

# --- MUM client & activity (referral scores, funded conversion, CRUD) ---
try:
    from routes.mum_activity_routes import register_mum_activity_routes
    register_mum_activity_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
    )
    logger.info("MUM activity routes loaded")
except Exception as e:
    logger.warning(f"MUM activity routes failed to load: {e}")

# --- Email management (signatures, drafts, send via Microsoft 365) ---
try:
    from routes.email_management_routes import register_email_management_routes
    register_email_management_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Email management routes loaded")
except Exception as e:
    logger.warning(f"Email management routes failed to load: {e}")

# --- Escalation (SLA escalation, team alerts) ---
try:
    from routes.escalation_routes import register_escalation_routes
    register_escalation_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Escalation routes loaded")
except Exception as e:
    logger.warning(f"Escalation routes failed to load: {e}")

# --- Compliance (fair lending, license enforcement, TCPA) ---
try:
    from routes.compliance_routes import register_compliance_routes
    register_compliance_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Compliance routes loaded")
except Exception as e:
    logger.warning(f"Compliance routes failed to load: {e}")

# --- Data import (CSV/Excel lead import, field mapping, rollback) ---
try:
    from routes.data_import_routes import register_data_import_routes
    register_data_import_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Data import routes loaded")
except Exception as e:
    logger.warning(f"Data import routes failed to load: {e}")

# ============================================================================
# ENTERPRISE & ADMIN ROUTES — LOS, SCIM, Scorecard, DR, Quality
# ============================================================================

# --- LOS integration API (push/pull, config, field mappings, health) ---
try:
    from routes.los_routes import register_los_routes
    register_los_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("LOS integration routes loaded")
except Exception as e:
    logger.warning(f"LOS integration routes failed to load: {e}")

# --- LOS webhook routes (inbound webhooks from Encompass/LOS) ---
try:
    from routes.los_webhook_routes import register_los_webhook_routes
    register_los_webhook_routes(app=app, get_db=get_db)
    logger.info("LOS webhook routes loaded")
except Exception as e:
    logger.warning(f"LOS webhook routes failed to load: {e}")

# --- SCIM provisioning (enterprise user provisioning via SCIM 2.0) ---
try:
    from routes.scim_provisioning_routes import register_scim_provisioning_routes
    register_scim_provisioning_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("SCIM provisioning routes loaded")
except Exception as e:
    logger.warning(f"SCIM provisioning routes failed to load: {e}")

# --- Scorecard (loan scorecard metrics, conversion, funding, referral breakdown) ---
try:
    from routes.scorecard_routes import register_scorecard_routes
    register_scorecard_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        Lead=Lead,
        Loan=Loan,
        LoanStage=LoanStage,
    )
    logger.info("Scorecard routes loaded")
except Exception as e:
    logger.warning(f"Scorecard routes failed to load: {e}")

# --- State disclosure (admin: state-specific disclosure requirements) ---
try:
    from routes.state_disclosure_routes import register_state_disclosure_routes
    register_state_disclosure_routes(app=app, get_db=get_db)
    logger.info("State disclosure routes loaded")
except Exception as e:
    logger.warning(f"State disclosure routes failed to load: {e}")

# --- Data quality (validation, dedup, integrity checks) ---
try:
    from routes.data_quality_routes import register_data_quality_routes
    register_data_quality_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Data quality routes loaded")
except Exception as e:
    logger.warning(f"Data quality routes failed to load: {e}")

# --- Disaster recovery (failover, RTO benchmarking, retention policy) ---
try:
    from routes.dr_routes import register_dr_routes
    register_dr_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("DR routes loaded")
except Exception as e:
    logger.warning(f"DR routes failed to load: {e}")

# --- Team calendar (shared calendar views, team scheduling) ---
try:
    from routes.team_calendar_routes import register_team_calendar_routes
    register_team_calendar_routes(app=app, get_current_user=get_current_user)
    logger.info("Team calendar routes loaded")
except Exception as e:
    logger.warning(f"Team calendar routes failed to load: {e}")

# ============================================================================
# MOBILE, NOTIFICATIONS & CONFIGURATION ROUTES
# ============================================================================

# --- SSE notifications (server-sent events for real-time updates) ---
try:
    from routes.sse_notification_routes import register_sse_notification_routes
    register_sse_notification_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("SSE notification routes loaded")
except Exception as e:
    logger.warning(f"SSE notification routes failed to load: {e}")

# --- Remote config (mobile feature flags, A/B config) ---
try:
    from routes.remote_config_routes import register_remote_config_routes
    register_remote_config_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Remote config routes loaded")
except Exception as e:
    logger.warning(f"Remote config routes failed to load: {e}")

# --- Calculator settings (mortgage calculator configuration) ---
try:
    from routes.calculator_settings_routes import register_calculator_settings_routes
    register_calculator_settings_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Calculator settings routes loaded")
except Exception as e:
    logger.warning(f"Calculator settings routes failed to load: {e}")

# ============================================================================
# INFRASTRUCTURE ROUTES — Backup, Cache, API Keys, Agents, Debug
# ============================================================================

# --- Backup (data backup, restore, export) ---
try:
    from routes.backup_routes import register_backup_routes
    register_backup_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Backup routes loaded")
except Exception as e:
    logger.warning(f"Backup routes failed to load: {e}")

# --- Cache management (cache stats, clear, warm) ---
try:
    from routes.cache_routes import register_cache_routes
    register_cache_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Cache routes loaded")
except Exception as e:
    logger.warning(f"Cache routes failed to load: {e}")

# --- API key management (CRUD for API keys) ---
try:
    from routes.api_key_routes import register_api_key_routes
    register_api_key_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("API key routes loaded")
except Exception as e:
    logger.warning(f"API key routes failed to load: {e}")

# --- Agent metrics (AI agent performance metrics, dashboards) ---
try:
    from routes.agent_metrics_routes import register_agent_metrics_routes
    register_agent_metrics_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Agent metrics routes loaded")
except Exception as e:
    logger.warning(f"Agent metrics routes failed to load: {e}")

# --- Application completion orchestrator (completeness scoring, gap detection) ---
try:
    from routes.app_completion_registration import register_app_completion_routes
    register_app_completion_routes(app=app)
    logger.info("App completion routes loaded")
except Exception as e:
    logger.warning(f"App completion routes failed to load: {e}")

# --- Smart Docs enterprise (Wave 3 enterprise document routes) ---
try:
    from routes.smart_docs_enterprise_registration import register_smart_docs_enterprise_routes
    register_smart_docs_enterprise_routes(app=app)
    logger.info("Smart Docs enterprise routes loaded")
except Exception as e:
    logger.warning(f"Smart Docs enterprise routes failed to load: {e}")

# --- Debug status & diagnostics (PURL testing, cache stats, admin tools) ---
try:
    from routes.debug_status_routes import register_debug_status_routes
    register_debug_status_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Debug status routes loaded")
except Exception as e:
    logger.warning(f"Debug status routes failed to load: {e}")

# ============================================================================
# INLINE ROUTES - extracted to routes/inline_legacy_routes.py
# ============================================================================
try:
    from routes.inline_legacy_routes import register_inline_routes
    register_inline_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        scheduler=scheduler,
        openai_client=openai_client,
        pwd_context=pwd_context,
        SECRET_KEY=SECRET_KEY,
        ENVIRONMENT=ENVIRONMENT,
        create_access_token=create_access_token,
        create_refresh_token=create_refresh_token,
        get_password_hash=get_password_hash,
        verify_password=verify_password,
        get_cached=get_cached,
        set_cached=set_cached,
        clear_cache=clear_cache,
        oauth2_scheme=oauth2_scheme,
        log_ai_action_to_mission_control=log_ai_action_to_mission_control,
        update_ai_action_outcome=update_ai_action_outcome,
        DATABASE_URL=DATABASE_URL,
        security_stats=security_stats,
    )
    logger.info("✅ Legacy inline routes loaded")

    # Re-export key functions for backward compatibility (from main import X)
    from routes.inline_legacy_routes import get_exported_function as _gef
    import types
    _mod = types.ModuleType.__dict__  # noqa - just checking availability
    import sys as _sys
    _this = _sys.modules[__name__]
    for _fname in ('process_microsoft_email_to_dre', 'fetch_microsoft_emails',
                    'generate_email_signature_html', 'calculate_lead_score',
                    'get_entity_name', 'classify_email_intent', 'generate_recommended_action',
                    'classify_email_content', 'extract_loan_fields', 'extract_borrower_from_subject',
                    'match_entity', 'apply_extracted_data', 'delete_microsoft_email'):
        _fn = _gef(_fname)
        if _fn:
            setattr(_this, _fname, _fn)

except Exception as e:
    logger.error(f"❌ Legacy inline routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# Re-export standalone utilities for backward compatibility
from utils.lead_scoring import calculate_lead_score  # noqa: F811
from utils.email_signature import generate_email_signature_html  # noqa: F811

# Re-export encrypt/decrypt from calendly service for backward compatibility
try:
    from services.calendly_service import encrypt_token, decrypt_token
except ImportError:
    pass

# ── Enterprise Challenge Routes ──────────────────────────────────────
try:
    from routes.file_collaborator_routes import register_file_collaborator_routes
    register_file_collaborator_routes(app)
    logger.info("✓ File collaborator routes registered")
except Exception as e:
    logger.warning(f"File collaborator routes skipped: {e}")

try:
    from routes.unified_timeline_routes import register_unified_timeline_routes
    register_unified_timeline_routes(app)
    logger.info("✓ Unified timeline routes registered")
except Exception as e:
    logger.warning(f"Unified timeline routes skipped: {e}")

try:
    from routes.vendor_management_routes import register_vendor_management_routes
    register_vendor_management_routes(app)
    logger.info("✓ Vendor management routes registered")
except Exception as e:
    logger.warning(f"Vendor management routes skipped: {e}")

try:
    from routes.marketing_campaign_routes import register_marketing_campaign_routes
    register_marketing_campaign_routes(app)
    logger.info("✓ Marketing campaign routes registered")
except Exception as e:
    logger.warning(f"Marketing campaign routes skipped: {e}")

try:
    from routes.learning_routes import register_learning_routes
    register_learning_routes(app)
    logger.info("✓ Learning routes registered")
except Exception as e:
    logger.warning(f"Learning routes skipped: {e}")

try:
    from routes.ai_activity_routes import register_ai_activity_routes
    register_ai_activity_routes(app)
    logger.info("✓ AI activity routes registered")
except Exception as e:
    logger.warning(f"AI activity routes not loaded: {e}")

try:
    from routes.aria_test_routes import register_aria_test_routes
    register_aria_test_routes(app=app)
    logger.info("✓ Aria test page registered at /aria-test")
except Exception as e:
    logger.warning(f"Aria test page not loaded: {e}")

# ============================================================================
# POST-LEGACY ROUTES — Depend on functions exported from inline_legacy_routes
# ============================================================================

# --- Admin ops (pool status, migrations, user mgmt, data endpoints) ---
try:
    from routes.admin_ops_routes import register_admin_ops_routes
    register_admin_ops_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        pwd_context=pwd_context,
        get_password_hash=get_password_hash,
        create_access_token=create_access_token,
        DATABASE_URL=DATABASE_URL,
    )
    logger.info("Admin ops routes loaded")
except Exception as e:
    logger.warning(f"Admin ops routes failed to load: {e}")

# --- Debug data & email (email sync, reconciliation, Microsoft integration) ---
try:
    from routes.debug_data_routes import register_debug_data_routes
    from services.dre_helpers import (
        process_microsoft_email_to_dre as _dre_process,
        fetch_microsoft_emails as _dre_fetch,
        match_entity as _dre_match,
        refresh_microsoft_token as _dre_refresh,
    )
    register_debug_data_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        process_microsoft_email_to_dre=_dre_process,
        fetch_microsoft_emails=_dre_fetch,
        match_entity=_dre_match,
        refresh_microsoft_token=_dre_refresh,
    )
    logger.info("Debug data routes loaded")
except Exception as e:
    logger.warning(f"Debug data routes failed to load: {e}")

# ============================================================================
# NEW ROUTE REGISTRATIONS — Security, Dashboard, CRM, Telephony, Compliance
# ============================================================================

# --- Security Audit (penetration test logging, vulnerability tracking) ---
try:
    from routes.security_audit_routes import router as security_audit_router
    app.include_router(security_audit_router, tags=["Security Audit"])
    logger.info("Security audit routes loaded")
except Exception as e:
    logger.warning(f"Security audit routes skipped: {e}")

# --- Security Certificate Pinning (SPKI hash serving, pin failure reporting) ---
try:
    from routes.security_certificate_routes import router as security_certificate_router
    app.include_router(security_certificate_router, tags=["Security Certificates"])
    logger.info("Security certificate routes loaded")
except Exception as e:
    logger.warning(f"Security certificate routes skipped: {e}")

# --- Security Dashboard (admin security overview, IP blocking) ---
try:
    from routes.security_dashboard_routes import router as security_dashboard_router
    app.include_router(security_dashboard_router, tags=["Security Dashboard"])
    logger.info("Security dashboard routes loaded")
except Exception as e:
    logger.warning(f"Security dashboard routes skipped: {e}")

# --- Dashboard Summary (pipeline, lead, loan summary stats) ---
try:
    from routes.dashboard_summary_routes import router as dashboard_summary_router
    app.include_router(dashboard_summary_router, tags=["Dashboard"])
    logger.info("Dashboard summary routes loaded")
except Exception as e:
    logger.warning(f"Dashboard summary routes skipped: {e}")

# --- Engagement Health (engagement subsystem health checks) ---
try:
    from routes.engagement_health_routes import router as engagement_health_router
    app.include_router(engagement_health_router, tags=["Engagement Health"])
    logger.info("Engagement health routes loaded")
except Exception as e:
    logger.warning(f"Engagement health routes skipped: {e}")

# --- Form 1084 (Fannie Mae Cash Flow Analysis generation) ---
try:
    from routes.form_1084_routes import router as form_1084_router
    app.include_router(form_1084_router, tags=["Form 1084"])
    logger.info("Form 1084 routes loaded")
except Exception as e:
    logger.warning(f"Form 1084 routes skipped: {e}")

# --- LO Availability (real-time presence, transfer readiness) ---
try:
    from routes.lo_availability_routes import router as lo_availability_router
    app.include_router(lo_availability_router, tags=["LO Availability"])
    logger.info("LO availability routes loaded")
except Exception as e:
    logger.warning(f"LO availability routes skipped: {e}")

# --- Email Response Queue (AI-assisted email handling with approval workflow) ---
try:
    from routes.email_response_queue_routes import router as email_response_queue_router
    from routes.email_response_queue_routes import set_dependencies as set_email_queue_deps
    from database.models import User as _UserModelEQ
    set_email_queue_deps(_UserModelEQ, get_current_user, get_db)
    app.include_router(email_response_queue_router, tags=["Email Response Queue"])
    logger.info("Email response queue routes loaded")
except Exception as e:
    logger.warning(f"Email response queue routes skipped: {e}")

# --- Live Transfer (warm/cold call transfer with LO whisper audio) ---
try:
    from routes.live_transfer_routes import router as live_transfer_router
    app.include_router(live_transfer_router, tags=["Live Transfer"])
    logger.info("Live transfer routes loaded")
except Exception as e:
    logger.warning(f"Live transfer routes skipped: {e}")

# --- AMD Voicemail (answering machine detection → auto voicemail drop) ---
try:
    from routes.amd_voicemail_routes import router as amd_voicemail_router
    app.include_router(amd_voicemail_router, tags=["AMD Voicemail"])
    logger.info("AMD voicemail routes loaded")
except Exception as e:
    logger.warning(f"AMD voicemail routes skipped: {e}")

# --- Speed to Lead (instant lead response triggers) ---
try:
    from routes.speed_to_lead_routes import router as speed_to_lead_router
    app.include_router(speed_to_lead_router, tags=["Speed to Lead"])
    logger.info("Speed to Lead routes loaded")
except Exception as e:
    logger.warning(f"Speed to Lead routes skipped: {e}")

# --- Speed to Lead Calls (auto-dial new leads for fastest contact) ---
try:
    from routes.speed_to_lead_call_routes import router as speed_to_lead_call_router
    app.include_router(speed_to_lead_call_router, tags=["Speed to Lead"])
    logger.info("Speed to Lead call routes loaded")
except Exception as e:
    logger.warning(f"Speed to Lead call routes skipped: {e}")

# --- SMS Compliance (opt-out handling, DNC enforcement) ---
try:
    from routes.sms_compliance_routes import router as sms_compliance_router
    app.include_router(sms_compliance_router, tags=["SMS Compliance"])
    logger.info("SMS compliance routes loaded")
except Exception as e:
    logger.warning(f"SMS compliance routes skipped: {e}")

# --- SMS AI Task routes (auto-response task queue) ---
try:
    from routes.sms_task_routes import router as sms_task_router
    app.include_router(sms_task_router, tags=["SMS Tasks"])
    logger.info("SMS task routes loaded")
except Exception as e:
    logger.warning(f"SMS task routes skipped: {e}")

# --- Lead Routing (round-robin, rules-based lead distribution) ---
try:
    from routes.lead_routing_routes import router as lead_routing_router
    app.include_router(lead_routing_router, tags=["Lead Routing"])
    logger.info("Lead routing routes loaded")
except Exception as e:
    logger.warning(f"Lead routing routes skipped: {e}")

# --- Compliance Validation (TRID, ECOA, HMDA, stage-transition checks) ---
try:
    from routes.compliance_validation_routes import register_compliance_validation_routes
    register_compliance_validation_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user,
    )
    logger.info("Compliance validation routes loaded")
except Exception as e:
    logger.warning(f"Compliance validation routes skipped: {e}")

# --- Command Center (unified action items dashboard) ---
try:
    from routes.command_center_routes import router as command_center_router
    from routes.command_center_routes import set_dependencies as set_command_center_deps
    from database.models import User as _UserModelCC, Lead as _LeadModelCC, Loan as _LoanModelCC
    from database.models.task import Task as _TaskModelCC
    from database.models.ai import AIAction as _AIActionModelCC
    set_command_center_deps(
        _UserModelCC, _TaskModelCC, _LeadModelCC, _LoanModelCC, _AIActionModelCC,
        get_current_user_flexible, get_db
    )
    app.include_router(command_center_router, tags=["Command Center"])
    logger.info("Command center routes loaded")
except Exception as e:
    logger.warning(f"Command center routes skipped: {e}")

# --- Meeting Routes (meeting link generation, room endpoints) ---
try:
    from routes.meeting_routes import router as meeting_router
    from routes.meeting_routes import set_dependencies as set_meeting_deps
    set_meeting_deps(get_db, get_current_user, {})
    app.include_router(meeting_router, tags=["Meetings"])
    logger.info("Meeting routes loaded")
except Exception as e:
    logger.warning(f"Meeting routes skipped: {e}")

# --- Call Intelligence Review Queue ---
try:
    from routes.call_intelligence_review_routes import router as ci_review_router
    app.include_router(ci_review_router, tags=["Call Intelligence Reviews"])
    logger.info("Call intelligence review routes loaded")
except Exception as e:
    logger.warning(f"Call intelligence review routes skipped: {e}")

# --- Rate Monitor (iOS-compatible alerts) ---
try:
    from routes.rate_monitor_routes import router as rate_monitor_ios_router
    app.include_router(rate_monitor_ios_router, tags=["Rate Monitor"])
    logger.info("Rate monitor iOS routes loaded")
except Exception as e:
    logger.warning(f"Rate monitor iOS routes skipped: {e}")

# --- Rate Alerts (unified /rate-monitor/alerts + /rate-alerts with empty-state handling) ---
try:
    from routes.rate_alerts_routes import router as rate_alerts_router
    app.include_router(rate_alerts_router, tags=["Rate Monitor"])
    logger.info("Rate alerts routes loaded")
except Exception as e:
    logger.warning(f"Rate alerts routes skipped: {e}")

# ============================================================================
# STARTUP EVENT — Initialize scheduler for workflow task generation
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """Initialize the scheduler on app startup and run critical schema migrations."""
    # Skip DB-dependent startup when running under pytest (TestClient triggers this
    # before dependency overrides are in effect, causing connections to unavailable DB)
    # Note: use _os (module-level alias) since `import os` appears later in this function
    # body, which makes Python treat `os` as a local variable throughout.
    if _os.environ.get("TESTING") == "1":
        logger.info("⏭️ Skipping startup DB operations (TESTING=1)")
        return

    # Initialize migration tracker (records which migrations have run, prevents duplicates)
    try:
        from migrations.migration_tracker import ensure_tracker_table, run_tracked
        ensure_tracker_table(engine)
        logger.info("Migration tracker initialized")
    except Exception as e:
        logger.warning(f"Migration tracker init failed, migrations will run untracked: {e}")
        run_tracked = None

    # Run API key hash migration (adds key_hash/key_prefix columns, migrates plaintext keys)
    try:
        from migrations.hash_api_keys import run_migration as _run_api_key_hash_migration
        if run_tracked:
            run_tracked(engine, "hash_api_keys", _run_api_key_hash_migration)
        else:
            _run_api_key_hash_migration(engine)
    except Exception as e:
        logger.error(f"API key hash migration FAILED: {e}", exc_info=True)

    # Ensure tcpa_consents table exists (needed for SMS opt-in form)
    try:
        from migrations.add_tcpa_consents_table import run_migration as _run_tcpa_migration
        _run_tcpa_migration()
    except Exception as e:
        logger.error(f"TCPA consents table migration FAILED: {e}", exc_info=True)

    # Create enterprise challenge tables (file collaborator, timeline, vendor, campaigns, learning)
    try:
        from migrations.enterprise_challenge_tables import run_migration as _run_enterprise_migration
        if run_tracked:
            run_tracked(engine, "enterprise_challenge_tables", _run_enterprise_migration)
        else:
            _run_enterprise_migration(engine)
    except Exception as e:
        logger.error(f"Enterprise migration FAILED: {e}", exc_info=True)

    # Run critical schema migrations (missing columns that break page loads)
    try:
        _run_critical_schema_migrations()
    except Exception as e:
        logger.error(f"❌ Critical schema migrations failed: {e}")

    try:
        from services.scheduler_service import init_scheduler
        init_scheduler()
        logger.info("✅ Scheduler initialized and started (workflow tasks, SLA tracking, appointment reminders)")
    except Exception as e:
        logger.error(f"❌ Scheduler failed to start: {e}")
        import traceback
        traceback.print_exc()

    # Register scheduler error handler (SchedulerError hierarchy → JSON responses)
    try:
        from middleware.scheduler_error_handler import register_scheduler_error_handlers
        register_scheduler_error_handlers(app)
        logger.info("✅ Scheduler exception handler registered")
    except Exception as e:
        logger.warning(f"⚠️ Scheduler error handler skipped: {e}")

    # Register event bus subscribers (appointment lifecycle events)
    try:
        from services.event_subscribers import register_all_subscribers
        register_all_subscribers()
        logger.info("✅ Event bus subscribers registered")
    except Exception as e:
        logger.warning(f"⚠️ Event bus subscribers skipped: {e}")

    # Register agent-specific event subscribers (inter-agent messaging via EventBus)
    try:
        from services.agent_event_subscribers import register_agent_subscribers
        register_agent_subscribers()
        logger.info("✅ Agent event subscribers registered")
    except Exception as e:
        logger.warning(f"⚠️ Agent event subscribers skipped: {e}")

    # Register agent message processor background job (polls ai_agent_messages every 5 min)
    try:
        from services.agent_message_processor import register_message_processor_job
        from services.scheduler_service import scheduler_service
        register_message_processor_job(scheduler_service.scheduler)
        logger.info("✅ Agent message processor job registered")
    except Exception as e:
        logger.warning(f"⚠️ Agent message processor skipped: {e}")

    # Register autonomous AI agents (morning briefing, pipeline monitor, compliance watchdog, etc.)
    try:
        from migrations.add_autonomous_agent_runs import run_migration as _run_agent_runs_migration
        if run_tracked:
            run_tracked(engine, "add_autonomous_agent_runs", _run_agent_runs_migration)
        else:
            _run_agent_runs_migration(engine)
        from agents.autonomous.loop import register_all_autonomous_agents
        from services.scheduler_service import scheduler_service
        agent_count = register_all_autonomous_agents(scheduler_service.scheduler)
        logger.info(f"✅ {agent_count} autonomous agents registered with scheduler")
    except Exception as e:
        logger.warning(f"⚠️ Autonomous agents registration skipped: {e}")

    # Start autonomous AI task executor (proactive agents: nurturing, compliance, pipeline, etc.)
    try:
        from services.autonomous.task_executor import get_executor
        _task_executor = get_executor()
        import asyncio
        asyncio.create_task(_task_executor.start())
        logger.info("Autonomous AI task executor started")
    except Exception as e:
        logger.warning(f"Autonomous task executor skipped: {e}")

    # Create all AI autonomy tables (autonomous_tasks, agent_feedback, learning,
    # agent_memory, agent_metrics, webhook_idempotency)
    try:
        from migrations.add_ai_autonomy_tables import run_migration as _run_ai_autonomy_migration
        if run_tracked:
            run_tracked(engine, "add_ai_autonomy_tables", _run_ai_autonomy_migration)
        else:
            _run_ai_autonomy_migration(engine)
    except Exception as e:
        logger.error(f"AI autonomy table creation FAILED: {e}", exc_info=True)
    # Webhook idempotency table (separate from AI autonomy)
    try:
        from database.models.webhook_idempotency import create_tables_if_needed as _create_webhook_tables
        _create_webhook_tables(engine)
        logger.info("Webhook idempotency table verified")
    except Exception as e:
        logger.error(f"Webhook idempotency table creation FAILED: {e}", exc_info=True)

    # Consolidate OAuth tokens into unified table
    try:
        from migrations.consolidate_oauth_tokens import run_migration as _run_oauth_migration
        if run_tracked:
            run_tracked(engine, "consolidate_oauth_tokens", _run_oauth_migration)
        else:
            _run_oauth_migration(engine)
    except Exception as e:
        logger.error(f"OAuth token consolidation FAILED: {e}", exc_info=True)

    # Ensure call intelligence columns and tables exist
    try:
        from migrations.add_call_intelligence_columns import run_migration as _run_ci_migration
        if run_tracked:
            run_tracked(engine, "add_call_intelligence_columns", _run_ci_migration)
        else:
            _run_ci_migration(engine)
    except Exception as e:
        logger.error(f"Call intelligence migration FAILED: {e}", exc_info=True)

    # ========================================================================
    # CRITICAL TABLE MIGRATIONS — Tables required by active SQLAlchemy models
    # Without these, any query touching these models raises ProgrammingError.
    # All use CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS (idempotent).
    # ========================================================================

    # --- Voice & Telephony ---
    try:
        from migrations.add_voice_workflows_table import run_migration as _run_voice_wf
        if run_tracked:
            run_tracked(engine, "add_voice_workflows_table", _run_voice_wf)
        else:
            _run_voice_wf(engine)
    except Exception as e:
        logger.warning(f"Voice workflows migration: {e}")

    try:
        from migrations.add_vapi_tables import run_migration as _run_vapi
        _run_vapi()
    except Exception as e:
        logger.warning(f"Vapi tables migration: {e}")

    try:
        from migrations.add_engagement_tables import run_migration as _run_engagement
        _run_engagement()
    except Exception as e:
        logger.warning(f"Engagement tables migration: {e}")

    try:
        from migrations.add_call_monitoring_system import run_migration as _run_call_monitor
        _run_call_monitor()
    except Exception as e:
        logger.warning(f"Call monitoring system migration: {e}")

    try:
        from migrations.add_call_intelligence_expansion import run_migration as _run_ci_expand
        _run_ci_expand()
    except Exception as e:
        logger.warning(f"Call intelligence expansion migration: {e}")

    try:
        from migrations.add_ci_enhancement_columns import run_migration as _run_ci_enhance
        if run_tracked:
            run_tracked(engine, "add_ci_enhancement_columns", _run_ci_enhance)
        else:
            _run_ci_enhance(engine)
    except Exception as e:
        logger.warning(f"CI enhancement columns migration: {e}")

    # --- SMS & Notifications ---
    try:
        from migrations.add_sms_persistence_tables import run_migration as _run_sms_persist
        _run_sms_persist()
    except Exception as e:
        logger.warning(f"SMS persistence tables migration: {e}")

    try:
        from migrations.add_sms_compliance_tables import run_migration as _run_sms_compliance
        _run_sms_compliance()
    except Exception as e:
        logger.warning(f"SMS compliance tables migration: {e}")

    try:
        from migrations.add_sms_consent_proof_columns import run_migration as _run_consent_proof
        _run_consent_proof()
    except Exception as e:
        logger.warning(f"SMS consent proof columns migration: {e}")

    try:
        from migrations.add_sms_delivery_tracking import run_migration as _run_delivery_tracking
        _run_delivery_tracking()
    except Exception as e:
        logger.warning(f"SMS delivery tracking migration: {e}")

    try:
        from migrations.add_sms_ai_conversations import run_migration as _run_sms_ai_conv
        _run_sms_ai_conv()
    except Exception as e:
        logger.warning(f"SMS AI conversations migration: {e}")

    try:
        from migrations.add_sms_task_tables import run_migration as _run_sms_task
        _run_sms_task(engine)
    except Exception as e:
        logger.warning(f"SMS task tables migration: {e}")

    try:
        from migrations.add_voicemail_sms_followup_columns import run_migration as _run_vm_followup
        _run_vm_followup()
    except Exception as e:
        logger.warning(f"Voicemail SMS followup columns migration: {e}")

    try:
        from migrations.add_media_s3_keys_columns import run_migration as _run_media_s3_keys
        _run_media_s3_keys()
    except Exception as e:
        logger.warning(f"Media S3 keys columns migration: {e}")

    try:
        from migrations.add_device_tokens_table import run_migration as _run_device_tokens
        _run_device_tokens()
    except Exception as e:
        logger.warning(f"Device tokens migration: {e}")

    try:
        from migrations.add_push_notification_preferences import run_migration as _run_push_prefs
        _run_push_prefs()
    except Exception as e:
        logger.warning(f"Push notification preferences migration: {e}")

    # --- AI Agents & Orchestration ---
    try:
        from migrations.add_agent_memory_tables import run_migration as _run_agent_mem
        _run_agent_mem()
    except Exception as e:
        logger.warning(f"Agent memory tables migration: {e}")

    try:
        from migrations.add_morning_briefings import run_migration as _run_briefings
        _run_briefings()
    except Exception as e:
        logger.warning(f"Morning briefings migration: {e}")

    try:
        from migrations.add_ai_benchmark_tables import run_migration as _run_ai_bench
        if run_tracked:
            run_tracked(engine, "add_ai_benchmark_tables", _run_ai_bench)
        else:
            _run_ai_bench(engine)
    except Exception as e:
        logger.warning(f"AI benchmark tables migration: {e}")

    # --- Lead & Loan Pipeline ---
    try:
        from migrations.add_stage_history_table import run_migration as _run_stage_hist
        _run_stage_hist()
    except Exception as e:
        logger.warning(f"Stage history table migration: {e}")

    try:
        from migrations.add_lead_assignment_tables import run_migration as _run_lead_assign
        _run_lead_assign()
    except Exception as e:
        logger.warning(f"Lead assignment tables migration: {e}")

    try:
        from migrations.add_app_completion_tables import run_migration as _run_app_complete
        if run_tracked:
            run_tracked(engine, "add_app_completion_tables", _run_app_complete)
        else:
            _run_app_complete(engine)
    except Exception as e:
        logger.warning(f"App completion tables migration: {e}")

    try:
        from migrations.add_post_closing_workflow import run_migration as _run_post_close
        _run_post_close()
    except Exception as e:
        logger.warning(f"Post-closing workflow migration: {e}")

    try:
        from migrations.add_business_rules_table import run_migration as _run_biz_rules
        _run_biz_rules()
    except Exception as e:
        logger.warning(f"Business rules table migration: {e}")

    # --- Compliance & Audit ---
    try:
        from migrations.add_compliance_decision_log import run_migration as _run_compliance_log
        _run_compliance_log()
    except Exception as e:
        logger.warning(f"Compliance decision log migration: {e}")

    try:
        from migrations.add_decision_audit_tables import run_migration as _run_decision_audit
        _run_decision_audit()
    except Exception as e:
        logger.warning(f"Decision audit tables migration: {e}")

    try:
        from migrations.add_pii_audit_log_table import run_migration as _run_pii_audit
        _run_pii_audit()
    except Exception as e:
        logger.warning(f"PII audit log migration: {e}")

    try:
        from migrations.add_security_training_table import run_migration as _run_sec_training
        _run_sec_training()
    except Exception as e:
        logger.warning(f"Security training table migration: {e}")

    # --- Smart Docs ---
    try:
        from migrations.add_document_cache_table import run_migration as _run_doc_cache
        _run_doc_cache()
    except Exception as e:
        logger.warning(f"Document cache table migration: {e}")

    try:
        from migrations.add_document_extraction_tables import run_migration as _run_doc_extract
        if run_tracked:
            run_tracked(engine, "add_document_extraction_tables", _run_doc_extract)
        else:
            _run_doc_extract(engine)
    except Exception as e:
        logger.warning(f"Document extraction tables migration: {e}")

    try:
        from migrations.add_smart_docs_sla import run_migration as _run_smart_sla
        _run_smart_sla()
    except Exception as e:
        logger.warning(f"Smart docs SLA migration: {e}")

    try:
        from migrations.add_smart_docs_missing_columns import run_migration as _run_smart_cols
        _run_smart_cols()
    except Exception as e:
        logger.warning(f"Smart docs missing columns migration: {e}")

    # --- E-Signature & E-Closing ---
    try:
        from migrations.add_esign_tables import run_migration as _run_esign
        _run_esign()
    except Exception as e:
        logger.warning(f"E-signature tables migration: {e}")

    try:
        from migrations.add_eclosing_table import run_migration as _run_eclose
        if run_tracked:
            run_tracked(engine, "add_eclosing_table", _run_eclose)
        else:
            _run_eclose(engine)
    except Exception as e:
        logger.warning(f"E-closing table migration: {e}")

    # --- Underwriting & Income ---
    try:
        from migrations.add_aus_submission_table import run_migration as _run_aus
        if run_tracked:
            run_tracked(engine, "add_aus_submission_table", _run_aus)
        else:
            _run_aus(engine)
    except Exception as e:
        logger.warning(f"AUS submission table migration: {e}")

    try:
        from migrations.add_guideline_updates_tables import run_migration as _run_guidelines
        _run_guidelines()
    except Exception as e:
        logger.warning(f"Guideline updates tables migration: {e}")

    # --- Billing & Subscriptions ---
    try:
        from migrations.add_accounting_tables import run_migration as _run_accounting
        _run_accounting()
    except Exception as e:
        logger.warning(f"Accounting tables migration: {e}")

    try:
        from migrations.add_subscription_modules import run_migration as _run_sub_modules
        if run_tracked:
            run_tracked(engine, "add_subscription_modules", _run_sub_modules)
        else:
            _run_sub_modules(engine)
    except Exception as e:
        logger.warning(f"Subscription modules migration: {e}")

    # --- Encompass LOS Integration ---
    try:
        from migrations.add_encompass_columns import run_migration as _run_encompass
        _run_encompass()
    except Exception as e:
        logger.warning(f"Encompass columns migration: {e}")

    # --- Content Marketing ---
    try:
        from migrations.add_content_marketing_tables import run_migration as _run_content_mktg
        _run_content_mktg()
    except Exception as e:
        logger.warning(f"Content marketing tables migration: {e}")

    # --- Performance Indexes (HIGH priority) ---
    try:
        from migrations.add_performance_indexes import run_migration as _run_perf_idx
        if run_tracked:
            run_tracked(engine, "add_performance_indexes", _run_perf_idx)
        else:
            _run_perf_idx(engine)
    except Exception as e:
        logger.warning(f"Performance indexes migration: {e}")

    try:
        from migrations.add_scheduler_indexes import run_migration as _run_sched_idx
        if run_tracked:
            run_tracked(engine, "add_scheduler_indexes", _run_sched_idx)
        else:
            _run_sched_idx(engine)
    except Exception as e:
        logger.warning(f"Scheduler indexes migration: {e}")

    logger.info("✅ Critical table migrations complete")

    # Register SOC 2 compliance scheduled jobs
    try:
        from soc2_compliance.scheduler import register_soc2_jobs
        register_soc2_jobs(scheduler)
        logger.info("✅ SOC 2 compliance jobs registered")
    except Exception as e:
        logger.warning(f"⚠️ SOC 2 scheduler registration skipped: {e}")

    # Record deployment event for SOC 2 change management (CC8)
    try:
        from db import SessionLocal
        from soc2_compliance.services.change_management_service import ChangeManagementService
        import os
        cms_session = SessionLocal()
        cms = ChangeManagementService(cms_session)
        cms.record_deployment(
            title=f"Application startup — {os.getenv('RAILWAY_DEPLOYMENT_ID', 'local')[:12]}",
            description="Automated deployment event recorded at application startup",
            git_commit=os.getenv("RAILWAY_GIT_COMMIT_SHA"),
            git_branch=os.getenv("RAILWAY_GIT_BRANCH"),
            deployment_id=os.getenv("RAILWAY_DEPLOYMENT_ID"),
        )
        cms_session.close()
    except Exception as e:
        logger.debug(f"SOC 2 deployment record skipped: {e}")

    # Start DB connection pool monitor (background thread, logs every 60s)
    try:
        from services.db_monitor import start_pool_monitor
        start_pool_monitor()
        logger.info("DB connection pool monitor started")
    except Exception as e:
        logger.warning(f"DB pool monitor failed to start: {e}")

    # Post-startup route health check
    critical_paths = ["/api/v1/leads", "/api/v1/loans", "/api/v1/pipeline", "/api/v1/auth", "/api/v1/ai"]
    registered_paths = [route.path for route in app.routes if hasattr(route, 'path')]
    missing = [p for p in critical_paths if not any(p in rp for rp in registered_paths)]
    if missing:
        logger.error(f"CRITICAL: Missing route registrations: {missing}")
    else:
        logger.info(f"✅ All {len(critical_paths)} critical route groups verified")

    # Verify certificate pins against live TLS chains (non-blocking background task)
    try:
        from routes.security_certificate_routes import _run_startup_pin_check
        import asyncio
        asyncio.create_task(_run_startup_pin_check())
        logger.info("Certificate pin verification scheduled (background)")
    except Exception as e:
        logger.warning(f"Certificate pin verification skipped: {e}")

    # Dedicated executor for LangGraph workflows — keeps them off the main event loop
    from concurrent.futures import ThreadPoolExecutor
    langgraph_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph")
    app.state.langgraph_executor = langgraph_executor
    logger.info("✅ LangGraph thread pool executor started (4 workers)")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown handler — clean up resources."""
    if hasattr(app.state, "langgraph_executor"):
        app.state.langgraph_executor.shutdown(wait=False)
        logger.info("LangGraph thread pool executor shut down")


def _run_critical_schema_migrations():
    """Run critical schema migrations at startup.

    These fix missing columns or type mismatches that cause 500 errors on page loads.
    All operations use IF NOT EXISTS / IF EXISTS to be idempotent.
    """
    from sqlalchemy import text as sa_text
    from db import SessionLocal

    success_count = 0
    skip_count = 0
    fail_count = 0

    db = SessionLocal()
    try:
        # Fix 1: Add ALL missing columns to loans table
        # Model defines columns that may not exist in production DB
        # (init_db.py handles some, but not all — especially Salesforce sync columns)
        loan_columns = [
            # Encompass LOS integration
            ("encompass_loan_id", "VARCHAR"),
            ("encompass_last_synced_at", "TIMESTAMP"),
            ("encompass_sync_status", "VARCHAR(50)"),
            # Salesforce Sync - Property
            ("property_type", "VARCHAR"),
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            ("file_state", "VARCHAR"),
            ("loan_purpose", "VARCHAR"),
            ("rate_type", "VARCHAR"),
            # Salesforce Sync - Financials
            ("monthly_payment", "NUMERIC(18,2)"),
            ("property_tax", "NUMERIC(18,2)"),
            ("hazard_insurance", "NUMERIC(18,2)"),
            ("mortgage_insurance", "NUMERIC(18,2)"),
            ("hoa_amount", "NUMERIC(18,2)"),
            ("origination_fee", "NUMERIC(18,2)"),
            ("estimated_prepaid_interest", "NUMERIC(18,2)"),
            ("points", "NUMERIC(8,4)"),
            ("index_rate", "NUMERIC(8,4)"),
            ("margin", "NUMERIC(8,4)"),
            ("ltv", "NUMERIC(8,4)"),
            ("cltv", "NUMERIC(8,4)"),
            # Salesforce Sync - 2nd Loan
            ("second_loan_amount", "NUMERIC(18,2)"),
            ("second_loan_rate", "NUMERIC(8,4)"),
            ("second_loan_payment", "NUMERIC(18,2)"),
            # Salesforce Sync - Housing Expenses
            ("present_housing_expense", "NUMERIC(18,2)"),
            ("proposed_housing_expense", "NUMERIC(18,2)"),
            ("present_monthly_payment", "NUMERIC(18,2)"),
            ("proposed_monthly_payment", "NUMERIC(18,2)"),
            # Missing date columns
            ("appraisal_received_date", "TIMESTAMP"),
            ("appraisal_docs_expire_date", "TIMESTAMP"),
            ("credit_docs_expire_date", "TIMESTAMP"),
            ("cd_sent_to_borrower_date", "TIMESTAMP"),
            ("cd_acknowledged_date", "TIMESTAMP"),
            # Borrower info
            ("coborrower_name", "VARCHAR"),
            ("co_borrower_email", "VARCHAR"),
            ("preferred_communication", "VARCHAR"),
            # SLA tracking
            ("days_in_stage", "INTEGER DEFAULT 0"),
            ("sla_status", "VARCHAR DEFAULT 'on-track'"),
            ("milestones", "JSONB"),
            ("ai_insights", "TEXT"),
            ("predicted_close_date", "TIMESTAMP"),
            ("risk_score", "INTEGER DEFAULT 0"),
            ("user_metadata", "JSONB"),
            # Stage tracking
            ("stage_changed_at", "TIMESTAMP"),
            # COMP-001: AI modification tracking
            ("last_modified_by_ai", "BOOLEAN DEFAULT FALSE"),
        ]
        added = 0
        for col_name, col_type in loan_columns:
            try:
                alter_sql = "ALTER TABLE loans ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"loans.{col_name} migration FAILED: {e}", exc_info=True)
        if added:
            logger.info(f"Ensured {added} loan columns exist")

        # Create index on encompass_loan_id if it doesn't exist
        try:
            db.execute(sa_text("""
                CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id
                ON loans (encompass_loan_id)
            """))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"encompass_loan_id index creation FAILED: {e}", exc_info=True)

        # Fix 2: Add missing columns to leads table
        lead_columns = [
            # Co-applicant
            ("co_applicant_name", "VARCHAR"),
            ("co_applicant_email", "VARCHAR"),
            ("co_applicant_phone", "VARCHAR"),
            ("preferred_communication", "VARCHAR"),
            ("organization_code", "VARCHAR"),
            # Financial
            ("debt_to_income", "NUMERIC(8,4)"),
            ("property_value", "NUMERIC(18,2)"),
            ("down_payment", "NUMERIC(18,2)"),
            ("employment_status", "VARCHAR"),
            ("annual_income", "NUMERIC(18,2)"),
            ("monthly_debts", "NUMERIC(18,2)"),
            ("first_time_buyer", "BOOLEAN DEFAULT FALSE"),
            # Loan Details
            ("loan_amount", "NUMERIC(18,2)"),
            ("interest_rate", "NUMERIC(8,4)"),
            ("loan_term", "INTEGER"),
            ("apr", "NUMERIC(8,4)"),
            ("points", "NUMERIC(8,4)"),
            ("lock_date", "TIMESTAMP"),
            ("lock_expiration", "TIMESTAMP"),
            ("closing_date", "TIMESTAMP"),
            ("lender", "VARCHAR"),
            ("loan_officer", "VARCHAR"),
            ("processor", "VARCHAR"),
            ("underwriter", "VARCHAR"),
            ("appraisal_value", "NUMERIC(18,2)"),
            ("ltv", "NUMERIC(8,4)"),
            ("cltv", "NUMERIC(8,4)"),
            ("dti", "NUMERIC(8,4)"),
            ("dti_front", "NUMERIC(8,4)"),
            ("dti_back", "NUMERIC(8,4)"),
            ("program", "VARCHAR"),
            ("status_date", "TIMESTAMP"),
            # SLA Milestone Dates
            ("lead_received_date", "TIMESTAMP"),
            ("first_contact_attempt_date", "TIMESTAMP"),
            ("first_contact_successful_date", "TIMESTAMP"),
            ("lead_qualification_date", "TIMESTAMP"),
            ("application_link_sent_date", "TIMESTAMP"),
            ("application_started_date", "TIMESTAMP"),
            ("application_completed_date", "TIMESTAMP"),
            ("credit_pulled_date", "TIMESTAMP"),
            ("preapproval_submission_date", "TIMESTAMP"),
            ("preapproval_issued_date", "TIMESTAMP"),
            ("preapproval_expiration_date", "TIMESTAMP"),
            ("realtor_referral_date", "TIMESTAMP"),
            ("rate_watch_enrollment_date", "TIMESTAMP"),
            ("initial_consultation_date", "TIMESTAMP"),
            ("property_address", "VARCHAR"),
            ("expected_purchase_date", "TIMESTAMP"),
            ("target_payment", "NUMERIC(18,2)"),
            # Referral fields
            ("referral_score", "INTEGER DEFAULT 0"),
            ("referral_source_score", "INTEGER DEFAULT 0"),
            ("employment_referral_flag", "BOOLEAN DEFAULT FALSE"),
            ("manager_flag", "BOOLEAN DEFAULT FALSE"),
            ("employees_managed", "INTEGER DEFAULT 0"),
            ("leadership_level", "VARCHAR"),
            ("company_size", "INTEGER"),
            ("employer_name", "VARCHAR"),
            ("industry", "VARCHAR"),
            ("circle_of_cash_flow_map", "JSONB"),
            # Workflow tracking
            ("current_workflow_id", "VARCHAR"),
            ("workflow_day", "INTEGER DEFAULT 0"),
            ("last_workflow_action", "TIMESTAMP"),
            ("nurture_month", "INTEGER DEFAULT 0"),
            ("stage_changed_at", "TIMESTAMP"),
            ("current_milestone_status", "VARCHAR(50)"),
            ("current_milestone_entered_at", "TIMESTAMP"),
            # Salesforce Sync - Property
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            # Salesforce Sync - Financial
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "NUMERIC(18,2)"),
            ("property_tax", "NUMERIC(18,2)"),
            ("hazard_insurance", "NUMERIC(18,2)"),
            ("mortgage_insurance", "NUMERIC(18,2)"),
            ("hoa_amount", "NUMERIC(18,2)"),
            ("origination_fee", "NUMERIC(18,2)"),
            ("estimated_prepaid_interest", "NUMERIC(18,2)"),
            ("index_rate", "NUMERIC(8,4)"),
            ("margin", "NUMERIC(8,4)"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            # Salesforce Sync - 2nd Loan
            ("second_loan_amount", "NUMERIC(18,2)"),
            ("second_loan_rate", "NUMERIC(8,4)"),
            ("second_loan_payment", "NUMERIC(18,2)"),
            # Salesforce Sync - Housing Expenses
            ("present_housing_expense", "NUMERIC(18,2)"),
            ("proposed_housing_expense", "NUMERIC(18,2)"),
            ("present_monthly_payment", "NUMERIC(18,2)"),
            ("proposed_monthly_payment", "NUMERIC(18,2)"),
            # Metadata
            ("salesforce_id", "VARCHAR"),
            ("meta_data", "JSONB"),
            ("user_metadata", "JSONB"),
            # COMP-001: AI modification tracking
            ("last_modified_by_ai", "BOOLEAN DEFAULT FALSE"),
            # COMP-004: GDPR PII retention with automated expiry
            ("data_retention_expires_at", "TIMESTAMP"),
        ]
        leads_added = 0
        for col_name, col_type in lead_columns:
            try:
                alter_sql = "ALTER TABLE leads ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                leads_added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"leads.{col_name} migration FAILED: {e}", exc_info=True)
        if leads_added:
            logger.info(f"Ensured {leads_added} lead columns exist")

        # Fix 3a: Convert leads.stage from PostgreSQL ENUM to VARCHAR if needed
        # The model defines Column(String) but the DB may have a leadstage enum type
        try:
            result = db.execute(sa_text("""
                SELECT data_type, udt_name FROM information_schema.columns
                WHERE table_name = 'leads' AND column_name = 'stage'
            """)).fetchone()
            if result and result[1] == 'leadstage':
                logger.info("Converting leads.stage from enum to varchar...")
                db.execute(sa_text("ALTER TABLE leads ALTER COLUMN stage TYPE VARCHAR USING stage::text"))
                db.commit()
                logger.info("leads.stage converted from enum to varchar")
                success_count += 1
            else:
                skip_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"leads.stage type migration FAILED: {e}", exc_info=True)

        # Fix 3b: Convert loans.stage from PostgreSQL ENUM to VARCHAR if needed
        try:
            result = db.execute(sa_text("""
                SELECT data_type, udt_name FROM information_schema.columns
                WHERE table_name = 'loans' AND column_name = 'stage'
            """)).fetchone()
            if result and result[1] == 'loanstage':
                logger.info("Converting loans.stage from enum to varchar...")
                db.execute(sa_text("ALTER TABLE loans ALTER COLUMN stage TYPE VARCHAR USING stage::text"))
                db.commit()
                logger.info("loans.stage converted from enum to varchar")
                success_count += 1
            else:
                skip_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"loans.stage type migration FAILED: {e}", exc_info=True)

        # Fix 4: Backfill MUM client names from leads (replace "Client - XXX" with real names)
        try:
            result = db.execute(sa_text("""
                UPDATE mum_clients m
                SET client_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')),
                    updated_at = CURRENT_TIMESTAMP
                FROM leads le
                WHERE m.client_name LIKE 'Client - %'
                  AND (
                      (le.loan_number = m.loan_number AND le.loan_number IS NOT NULL)
                      OR (le.email = m.email AND le.email IS NOT NULL)
                  )
                  AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            """))
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Backfilled {result.rowcount} MUM client names from leads")
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"MUM name backfill FAILED: {e}", exc_info=True)

        # Chime SDK migration: add columns for video meeting Chime integration
        chime_columns = {
            "video_meeting_rooms": [
                ("chime_meeting_id", "VARCHAR(255)"),
                ("chime_media_region", "VARCHAR(50) DEFAULT 'us-east-1'"),
            ],
            "meeting_recordings": [
                ("chime_pipeline_id", "VARCHAR(255)"),
                ("s3_key", "VARCHAR(1000)"),
            ],
        }
        for table, cols in chime_columns.items():
            for col_name, col_type in cols:
                try:
                    alter_sql = "ALTER TABLE " + table + " ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                    db.execute(sa_text(alter_sql))
                    db.commit()
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    fail_count += 1
                    logger.error(f"{table}.{col_name} migration FAILED: {e}", exc_info=True)
        try:
            db.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_video_meeting_rooms_chime_meeting_id ON video_meeting_rooms (chime_meeting_id)"))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"chime_meeting_id index creation FAILED: {e}", exc_info=True)
        try:
            db.execute(sa_text("ALTER TABLE meeting_recordings ALTER COLUMN retention_days SET DEFAULT 1825"))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"retention_days default migration FAILED: {e}", exc_info=True)
        try:
            result = db.execute(sa_text("UPDATE meeting_recordings SET retention_days = 1825 WHERE retention_days = 90"))
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Updated {result.rowcount} recording retention periods to 5 years")
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"retention_days update FAILED: {e}", exc_info=True)

        # Fix N: Add missing columns to users table
        # The User model defines columns that may not exist in the production table,
        # causing ProgrammingError on any query that SELECTs all User columns.
        users_columns = [
            ("manager_id", "INTEGER"),
            ("briefing_enabled", "BOOLEAN DEFAULT TRUE"),
            ("briefing_hour", "INTEGER DEFAULT 7"),
            ("briefing_preferences", "JSONB"),
            ("email_verified", "BOOLEAN DEFAULT FALSE"),
            ("onboarding_completed", "BOOLEAN DEFAULT FALSE"),
            ("user_metadata", "JSON"),
            ("phone", "VARCHAR(50)"),
            ("nmls_number", "VARCHAR(50)"),
            ("business_address", "VARCHAR(500)"),
            ("current_role", "VARCHAR(100)"),
            ("business_hours", "JSON"),
            ("email_verified_at", "TIMESTAMP"),
            ("phone_verified_at", "TIMESTAMP"),
            ("slug", "VARCHAR(255)"),
            ("company_logo_url", "TEXT"),
            ("headshot_url", "TEXT"),
            ("title", "TEXT"),
            ("team_name", "TEXT"),
            ("nmls_id", "VARCHAR(50)"),
            ("timezone", "VARCHAR(100) DEFAULT 'America/Chicago'"),
            ("last_activity_at", "TIMESTAMP"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "TIMESTAMP"),
            ("last_failed_login_at", "TIMESTAMP"),
            ("mfa_secret", "VARCHAR(255)"),
            ("mfa_enabled", "BOOLEAN DEFAULT FALSE"),
            ("mfa_backup_codes", "JSON"),
            ("mfa_enabled_at", "TIMESTAMP"),
            ("sso_provider", "VARCHAR(50)"),
            ("sso_subject_id", "VARCHAR(255)"),
        ]
        u_added = 0
        for col_name, col_type in users_columns:
            try:
                alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                u_added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"users.{col_name} migration FAILED: {e}", exc_info=True)
        if u_added:
            logger.info(f"Ensured {u_added} users columns exist")

        # Fix N+1: Add missing columns to scheduler tables
        # The BookingLink model defines columns (organization_id, etc.) that may not
        # exist in the production table, causing 503 on public booking endpoints.
        scheduler_table_migrations = {
            "scheduler_booking_links": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("single_appointment_type_id", "INTEGER"),
                ("requires_authentication", "BOOLEAN DEFAULT FALSE"),
                ("password_protected", "BOOLEAN DEFAULT FALSE"),
                ("password_hash", "VARCHAR(255)"),
                ("custom_title", "VARCHAR(255)"),
                ("custom_description", "TEXT"),
                ("custom_logo_url", "VARCHAR(500)"),
                ("custom_color", "VARCHAR(20)"),
                ("max_bookings", "INTEGER"),
                ("current_bookings", "INTEGER DEFAULT 0"),
                ("max_per_person", "INTEGER"),
                ("available_from", "TIMESTAMP"),
                ("available_until", "TIMESTAMP"),
                ("routing_strategy", "VARCHAR(50) DEFAULT 'relationship'"),
                ("assigned_users", "JSONB"),
                ("view_count", "INTEGER DEFAULT 0"),
                ("booking_count", "INTEGER DEFAULT 0"),
                ("last_booked_at", "TIMESTAMP"),
                ("default_utm_source", "VARCHAR(100)"),
                ("default_utm_medium", "VARCHAR(100)"),
                ("default_utm_campaign", "VARCHAR(100)"),
                ("expires_at", "TIMESTAMP"),
            ],
            "scheduler_configs": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("working_hours", "JSONB"),
                ("min_notice_hours", "INTEGER DEFAULT 2"),
                ("max_advance_days", "INTEGER DEFAULT 30"),
                ("buffer_before_minutes", "INTEGER DEFAULT 5"),
                ("buffer_after_minutes", "INTEGER DEFAULT 5"),
                ("max_meetings_per_day", "INTEGER DEFAULT 8"),
                ("ai_scheduling_config", "JSON"),
                ("notification_settings", "JSON"),
                ("setup_completed", "BOOLEAN DEFAULT FALSE"),
                ("setup_progress", "JSON"),
                ("feature_toggles", "JSON"),
            ],
            "appointment_types": [
                ("organization_id", "INTEGER"),
                ("config_id", "INTEGER"),
                ("type_key", "VARCHAR(100)"),
                ("allowed_durations", "JSONB"),
                ("meeting_type", "VARCHAR(50)"),
                ("default_mode", "VARCHAR(20)"),
                ("color", "VARCHAR(20)"),
                ("icon", "VARCHAR(50)"),
                ("intake_questions", "JSONB"),
                ("requires_confirmation", "BOOLEAN DEFAULT FALSE"),
                ("buffer_before_minutes", "INTEGER DEFAULT 5"),
                ("buffer_after_minutes", "INTEGER DEFAULT 5"),
            ],
            "scheduler_blocked_times": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("title", "VARCHAR(255)"),
                ("description", "TEXT"),
                ("block_type", "VARCHAR(50) DEFAULT 'custom'"),
                ("start_datetime", "TIMESTAMP"),
                ("end_datetime", "TIMESTAMP"),
                ("all_day", "BOOLEAN DEFAULT FALSE"),
                ("is_recurring", "BOOLEAN DEFAULT FALSE"),
                ("recurrence_pattern", "JSON"),
                ("recurrence_end_date", "DATE"),
                ("applies_to_all_users", "BOOLEAN DEFAULT FALSE"),
                ("applies_to_teams", "JSON"),
                ("is_active", "BOOLEAN DEFAULT TRUE"),
                ("created_at", "TIMESTAMP DEFAULT NOW()"),
                ("updated_at", "TIMESTAMP DEFAULT NOW()"),
                ("created_by_id", "INTEGER"),
            ],
            "scheduler_appointments": [
                ("organization_id", "INTEGER"),
                ("appointment_type_id", "INTEGER"),
                ("assigned_user_id", "INTEGER"),
                ("created_by_user_id", "INTEGER"),
                ("lead_id", "INTEGER"),
                ("loan_id", "INTEGER"),
                ("contact_id", "INTEGER"),
                ("idempotency_key", "VARCHAR(64)"),
                ("external_id", "VARCHAR(100)"),
                ("external_source", "VARCHAR(50)"),
                ("title", "VARCHAR(255)"),
                ("description", "TEXT"),
                ("meeting_type", "VARCHAR(50)"),
                ("meeting_mode", "VARCHAR(50)"),
                ("scheduled_start", "TIMESTAMP"),
                ("scheduled_end", "TIMESTAMP"),
                ("duration_minutes", "INTEGER"),
                ("timezone", "VARCHAR(50) DEFAULT 'America/Chicago'"),
                ("location", "VARCHAR(255)"),
                ("video_link", "VARCHAR(500)"),
                ("phone_number", "VARCHAR(20)"),
                ("dial_in_info", "TEXT"),
                ("attendee_name", "VARCHAR(255)"),
                ("attendee_email", "VARCHAR(255)"),
                ("attendee_phone", "VARCHAR(20)"),
                ("attendee_notes", "TEXT"),
                ("intake_responses", "JSON"),
                ("status", "VARCHAR(50) DEFAULT 'booked'"),
                ("status_changed_at", "TIMESTAMP"),
                ("status_changed_by", "INTEGER"),
                ("completed_at", "TIMESTAMP"),
                ("no_show_at", "TIMESTAMP"),
                ("cancelled_at", "TIMESTAMP"),
                ("cancellation_reason", "TEXT"),
                ("rescheduled_from_id", "INTEGER"),
                ("reschedule_count", "INTEGER DEFAULT 0"),
                ("booked_by_ai", "BOOLEAN DEFAULT FALSE"),
                ("ai_booking_context", "JSON"),
                ("auto_confirmed", "BOOLEAN DEFAULT FALSE"),
                ("google_calendar_event_id", "VARCHAR(255)"),
                ("outlook_event_id", "VARCHAR(255)"),
                ("last_synced_at", "TIMESTAMP"),
                ("internal_notes", "TEXT"),
                ("meeting_notes", "TEXT"),
                ("version", "INTEGER DEFAULT 1"),
                ("recovery_step", "INTEGER DEFAULT 0"),
                ("recovery_started_at", "TIMESTAMP"),
                ("recovery_completed_at", "TIMESTAMP"),
                ("recovery_opted_out", "BOOLEAN DEFAULT FALSE"),
                ("communication_consent_at", "TIMESTAMP"),
                ("communication_consent_source", "VARCHAR(50)"),
                ("booking_attribution", "JSON"),
                ("created_at", "TIMESTAMP DEFAULT NOW()"),
                ("updated_at", "TIMESTAMP DEFAULT NOW()"),
            ],
        }
        for table_name, columns in scheduler_table_migrations.items():
            tbl_added = 0
            for col_name, col_type in columns:
                try:
                    alter_sql = "ALTER TABLE " + table_name + " ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                    db.execute(sa_text(alter_sql))
                    db.commit()
                    tbl_added += 1
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    fail_count += 1
                    logger.error(f"{table_name}.{col_name} migration FAILED: {e}", exc_info=True)
            if tbl_added:
                logger.info(f"Ensured {tbl_added} {table_name} columns exist")

        # Fix N+2: Convert scheduler ENUM columns to VARCHAR
        # Same pattern as Lead.stage and Loan.stage — the production DB has a
        # PostgreSQL ENUM type that doesn't include newer status values (CONFIRMED,
        # REMINDED, CHECKED_IN). Converting to VARCHAR lets any string value work.
        enum_to_varchar_conversions = [
            ("scheduler_appointments", "status", "appointmentstatus"),
            ("scheduler_appointments", "meeting_type", "meetingtype"),
            ("scheduler_appointments", "meeting_mode", "meetingmode"),
        ]
        for table, col, enum_type in enum_to_varchar_conversions:
            try:
                # Check if column is currently an enum type
                col_info = db.execute(sa_text(
                    "SELECT data_type, udt_name FROM information_schema.columns "
                    "WHERE table_name = :tbl AND column_name = :col"
                ), {"tbl": table, "col": col}).fetchone()
                if col_info and col_info[0] == 'USER-DEFINED':
                    alter_col_sql = "ALTER TABLE " + table + " ALTER COLUMN " + col + " TYPE VARCHAR(50) USING " + col + "::text"
                    db.execute(sa_text(alter_col_sql))
                    db.commit()
                    logger.info(f"Converted {table}.{col} from enum to VARCHAR")
                    success_count += 1
                    # Drop the old enum type if it's no longer used
                    try:
                        drop_type_sql = "DROP TYPE IF EXISTS " + enum_type
                        db.execute(sa_text(drop_type_sql))
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Failed to drop enum type {enum_type}: {e}", exc_info=True)
                else:
                    skip_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"Enum conversion {table}.{col} FAILED: {e}", exc_info=True)

        # Fix N+3: Create missing scheduler tables if they don't exist
        missing_tables_sql = [
            """CREATE TABLE IF NOT EXISTS scheduler_slot_holds (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                appointment_type_id INTEGER,
                user_id INTEGER,
                slot_start TIMESTAMP NOT NULL,
                slot_end TIMESTAMP NOT NULL,
                hold_token VARCHAR(64) UNIQUE,
                held_by_email VARCHAR(255),
                held_by_session VARCHAR(255),
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                converted_to_appointment_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS recurring_availability (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                user_id INTEGER,
                day_of_week INTEGER NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS availability_exceptions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                user_id INTEGER,
                exception_date DATE NOT NULL,
                start_time TIME,
                end_time TIME,
                is_available BOOLEAN DEFAULT FALSE,
                reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )""",
        ]
        for create_sql in missing_tables_sql:
            try:
                db.execute(sa_text(create_sql))
                db.commit()
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"Table creation FAILED: {e}", exc_info=True)

        logger.info(f"Schema migrations: {success_count} applied, {skip_count} skipped, {fail_count} FAILED")
        if fail_count > 0:
            logger.error(f"Schema migrations completed with {fail_count} FAILURES — check logs above for details")
    finally:
        db.close()

# ============================================================================
# MOBILE API ROUTES - Lightweight endpoints for mobile clients
# ============================================================================
try:
    from routes.mobile_api_routes import register_mobile_api_routes
    register_mobile_api_routes(
        app=app,
        get_db=get_db,
        get_current_user=get_current_user
    )
    logger.info("✅ Mobile API routes loaded (dashboard, pipeline, leads, notifications, quick-lead, rate-lock-alerts)")
except Exception as e:
    logger.error(f"❌ Mobile API routes failed to load: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEMPORARY: One-time seed endpoint for App Store demo account
# Remove after demo account is created
# Gated to non-production environments only.
# ============================================================================

@app.post("/api/v1/management/seed-demo")
async def seed_demo_account(request: Request):
    """One-time endpoint to create App Store review demo account. Protected by SECRET_KEY."""
    import secrets as _secrets_mod
    _env_name = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")).lower()
    if _env_name == "production":
        raise HTTPException(status_code=404, detail="Not found")

    body = await request.json()
    auth = (body.get("key", "") or "").strip()
    expected = SECRET_KEY.strip()
    # Constant-time comparison to prevent timing attacks
    if not auth or not _secrets_mod.compare_digest(auth, expected):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        import importlib
        import scripts.seed_demo_account as seed_mod
        importlib.reload(seed_mod)  # ensure fresh run
        seed_mod.main()
        return {"status": "success", "message": "Demo account seeded successfully"}
    except SystemExit:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Seed script exited (DATABASE_URL missing?)"})
    except Exception as e:
        logger.exception("Demo seed failed")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# MAIN
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

