# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

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
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import time

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

# Setup logging - reduce verbosity in production to avoid Railway rate limits
_is_production = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") == "production"
_log_level = logging.WARNING if _is_production else logging.INFO
logging.basicConfig(
    level=_log_level,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

# Install PII redaction filter on root logger to prevent SSN/PII leakage in logs
# Enterprise Readiness Check 3.20 - must be installed before any PII processing
try:
    from middleware.pii_log_filter import install_pii_filter
    install_pii_filter()
except Exception as _pii_err:
    logger.warning(f"PII log filter not installed: {_pii_err}")

# Suppress noisy loggers in production
if _log_level == logging.WARNING:
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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
        logger.info("✅ Token blacklist initialized with Redis")
    else:
        logger.warning("⚠️ Token blacklist disabled (no REDIS_URL)")
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

# CORS - Dynamic custom domain support
# Custom domains are stored in the database and checked dynamically
# No code changes needed to add new user domains
from middleware.dynamic_cors import DynamicCORSMiddleware

# PHASE 3: Impersonation read-only enforcement middleware
from middleware.impersonation_middleware import ImpersonationEnforcementMiddleware

# Multi-Tenant: Tenant context middleware for organization isolation
from middleware.tenant_context_middleware import TenantContextMiddleware

# Add security middleware FIRST (order matters - last added = outermost = first to execute)
# Security middleware runs first, then CORS wraps everything including error responses
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestValidationMiddleware)
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
    logger.warning(f"⚠️ SOC 2 audit middleware not loaded: {e}")

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
            "X-Request-ID", "X-Visitor-ID", "X-Impersonation-Token",
        ],
        expose_headers=[
            "Content-Length", "Content-Type", "X-Request-ID",
            "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
        ],
        max_age=3600,
    )
    logger.info("✅ CORS middleware enabled (outermost — added last for correct ordering)")
except Exception as e:
    logger.warning(f"⚠️ CORS middleware not loaded: {e}")

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

    # Check if token is an API key (starts with 'sk_')
    if token.startswith('sk_'):
        api_key = db.query(ApiKey).filter(
            ApiKey.key == token,
            ApiKey.is_active == True
        ).first()

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
        # Try to find API key in database
        api_key = db.query(ApiKey).filter(
            ApiKey.key == api_key_header,
            ApiKey.is_active == True
        ).first()

        if api_key:
            # Update last used timestamp
            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

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

    # Check if token is an API key (starts with 'sk_')
    if token.startswith('sk_'):
        api_key = db.query(ApiKey).filter(
            ApiKey.key == token,
            ApiKey.is_active == True
        ).first()

        if api_key is None:
            raise credentials_exception

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

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

# ============================================================================
# STARTUP EVENT — Initialize scheduler for workflow task generation
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """Initialize the scheduler on app startup and run critical schema migrations."""
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


def _run_critical_schema_migrations():
    """Run critical schema migrations at startup.

    These fix missing columns or type mismatches that cause 500 errors on page loads.
    All operations use IF NOT EXISTS / IF EXISTS to be idempotent.
    """
    from sqlalchemy import text as sa_text
    from db import SessionLocal

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
        ]
        added = 0
        for col_name, col_type in loan_columns:
            try:
                db.execute(sa_text(f"ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                db.commit()
                added += 1
            except Exception as e:
                db.rollback()
                logger.debug(f"loans.{col_name} migration: {e}")
        if added:
            logger.info(f"✅ Ensured {added} loan columns exist")

        # Create index on encompass_loan_id if it doesn't exist
        try:
            db.execute(sa_text("""
                CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id
                ON loans (encompass_loan_id)
            """))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug(f"encompass_loan_id index: {e}")

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
        ]
        leads_added = 0
        for col_name, col_type in lead_columns:
            try:
                db.execute(sa_text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                db.commit()
                leads_added += 1
            except Exception as e:
                db.rollback()
                logger.debug(f"leads.{col_name} migration: {e}")
        if leads_added:
            logger.info(f"✅ Ensured {leads_added} lead columns exist")

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
                logger.info("✅ leads.stage converted from enum to varchar")
        except Exception as e:
            db.rollback()
            logger.warning(f"leads.stage type migration: {e}")

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
                logger.info("✅ loans.stage converted from enum to varchar")
        except Exception as e:
            db.rollback()
            logger.warning(f"loans.stage type migration: {e}")

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
                logger.info(f"✅ Backfilled {result.rowcount} MUM client names from leads")
        except Exception as e:
            db.rollback()
            logger.debug(f"MUM name backfill: {e}")

        logger.info("✅ Critical schema migrations complete")
    finally:
        db.close()

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

