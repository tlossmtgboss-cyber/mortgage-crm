# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Increase recursion limit — FastAPI's merged lifespan chaining with 72+ routers
# requires deep stack frames. Default 1000 is insufficient.
import sys
sys.setrecursionlimit(3000)

# Suppress warnings in production to avoid Railway rate limiting (500 logs/sec limit)
import warnings
import os as _os
if _os.getenv("RAILWAY_ENVIRONMENT") or _os.getenv("ENVIRONMENT") == "production":
    warnings.filterwarnings("ignore")
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
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
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

# Setup structured logging
from utils.logging_config import configure_logging as _configure_logging
_configure_logging()
logger = logging.getLogger(__name__)

# Install PII redaction filter on root logger
try:
    from middleware.pii_log_filter import install_pii_filter
    install_pii_filter()
except Exception as _pii_err:
    logger.warning(f"PII log filter not installed: {_pii_err}")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SECRET_KEY configuration
_SECRET_KEY = os.getenv("SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production" and not _SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is required in production. "
        "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

if not _SECRET_KEY:
    if ENVIRONMENT == "development":
        logger.warning("SECRET_KEY not set - using generated key for development only")
        import secrets
        SECRET_KEY = secrets.token_hex(32)
    else:
        raise ValueError("SECRET_KEY environment variable is required in production")
else:
    SECRET_KEY = _SECRET_KEY

# ADMIN_API_KEY validation
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
if ENVIRONMENT == "production" and (not _ADMIN_API_KEY or len(_ADMIN_API_KEY) < 32):
    raise ValueError(
        "ADMIN_API_KEY must be set and at least 32 characters in production. "
        "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
elif not _ADMIN_API_KEY:
    logger.warning("ADMIN_API_KEY not set — CSRF API-key bypass and admin endpoints disabled")

# REDIS_URL validation
_is_production = bool(os.getenv("RAILWAY_ENVIRONMENT") or ENVIRONMENT == "production")
_redis_url_check = os.getenv("REDIS_URL", "").strip()
if _is_production and not _redis_url_check:
    logger.critical(
        "REDIS_URL is not set in production. Token blacklisting, rate limiting, "
        "and Celery require Redis for correctness across replicas. "
        "Refusing to start — set REDIS_URL or downgrade ENVIRONMENT."
    )
    raise SystemExit(
        "FATAL: REDIS_URL environment variable is required in production. "
        "Token blacklisting, rate limiting, and Celery all require Redis."
    )

# JWT Configuration
ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 1

# Import auth module for secure token handling
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

    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        token_blacklist.initialize(_redis_url)
        try:
            import redis
            _r = redis.from_url(_redis_url, socket_timeout=5)
            _r.ping()
            logger.info("Redis connection verified")
            _r.close()
        except Exception as e:
            logger.error(f"Redis connection FAILED: {e} — token revocation and rate limiting may not work")
        logger.info("Token blacklist initialized with Redis")
        try:
            from services.redis_service import redis_service
            redis_service.initialize(_redis_url)
        except Exception as e:
            logger.warning(f"redis_service initialization failed: {e}")
    else:
        _env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
        if _env in ("production", "staging"):
            logger.critical(
                "SECURITY: Token blacklist running in-memory mode. "
                "Token revocation will not work across replicas (numReplicas=2). "
                "A revoked token on replica A remains valid on replica B. "
                "Set REDIS_URL to enable distributed blacklist."
            )
        else:
            logger.info("REDIS_URL not set — using in-memory token blacklist (dev mode)")
except ImportError as e:
    logger.warning(f"Secure auth module not available, using legacy JWT: {e}")
    _USE_SECURE_TOKENS = False

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ============================================================================
# IN-MEMORY CACHE
# ============================================================================
import asyncio as _asyncio
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = _asyncio.Lock()
CACHE_TTL_SECONDS = 30
MAX_CACHE_SIZE = 1000

def get_cached(key: str) -> Optional[Any]:
    """Get cached value if not expired (read path is lock-free for performance)"""
    entry = _cache.get(key)
    if entry is not None:
        if time.time() - entry['timestamp'] < CACHE_TTL_SECONDS:
            return entry['data']
    return None

async def set_cached(key: str, data: Any) -> None:
    """Set cache entry with timestamp (async-safe)"""
    async with _cache_lock:
        if len(_cache) >= MAX_CACHE_SIZE:
            now = time.time()
            expired = [k for k, v in _cache.items() if now - v['timestamp'] > CACHE_TTL_SECONDS]
            for k in expired:
                del _cache[k]
            if len(_cache) >= MAX_CACHE_SIZE:
                oldest_key = min(_cache, key=lambda k: _cache[k]['timestamp'])
                del _cache[oldest_key]
        _cache[key] = {'data': data, 'timestamp': time.time()}

def set_cached_sync(key: str, data: Any) -> None:
    """Sync version for non-async callers"""
    if len(_cache) >= MAX_CACHE_SIZE:
        now = time.time()
        keys_to_delete = [k for k, v in _cache.items() if now - v['timestamp'] > CACHE_TTL_SECONDS]
        for k in keys_to_delete:
            _cache.pop(k, None)
    _cache[key] = {'data': data, 'timestamp': time.time()}

def clear_cache(prefix: str = None) -> None:
    """Clear cache entries, optionally by prefix"""
    global _cache
    if prefix:
        _cache = {k: v for k, v in _cache.items() if not k.startswith(prefix)}
    else:
        _cache = {}

# ============================================================================
# DATABASE
# ============================================================================
from database import engine, SessionLocal, Base, get_db as _get_db_from_database

# Initialize background scheduler
scheduler = AsyncIOScheduler(
    job_defaults={
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 30
    }
)

# Use RLS-aware get_db from database.py
get_db = _get_db_from_database

# ============================================================================
# ENUMS
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
# DATABASE MODELS
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
    # Device Tokens (push notifications)
    DeviceToken, PushNotificationPreference,
)

# Register every model (direct + factory) on the single canonical Base before
# configuring mappers, so all cross-model relationships resolve at startup rather
# than relying on lazy resolution during the first request. Defensive: a failure
# here must never crash startup (mirrors the configure_mappers guard below).
try:
    from model_registry import register_all_models
    register_all_models()
except Exception as e:
    logger.warning(f"register_all_models warning (mappers may resolve lazily): {e}")

# Configure mappers after all model imports
from sqlalchemy.orm import configure_mappers
try:
    configure_mappers()
except Exception as e:
    logger.warning(f"Mapper configuration warning (may be handled later): {e}")

# Register audit immutability protection
try:
    from middleware.audit_immutability import register_audit_protection
    register_audit_protection()
except Exception as e:
    logger.warning(f"Failed to register audit immutability protection: {e}")

# ============================================================================
# PYDANTIC SCHEMAS
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
# AUTH FUNCTIONS — Must be defined before importing routes
# ============================================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Graceful shutdown handler
graceful_shutdown = GracefulShutdown(drain_timeout=30.0)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


class _BcryptCompat:
    """Drop-in replacement providing .hash()/.verify() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return get_password_hash(password)
    def verify(self, plain: str, hashed: str) -> bool:
        return verify_password(plain, hashed)

pwd_context = _BcryptCompat()


def create_access_token(data: dict, user_id: int = None, tenant_id: str = None):
    """Create a JWT access token with enhanced security."""
    if _USE_SECURE_TOKENS:
        token_data = data.copy()
        if user_id:
            token_data["user_id"] = user_id
        if tenant_id:
            token_data["tenant_id"] = tenant_id
        return _create_secure_access_token(token_data)
    else:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, user_id: int = None):
    """Create a JWT refresh token for session renewal."""
    if _USE_SECURE_TOKENS:
        token_data = data.copy()
        if user_id:
            token_data["user_id"] = user_id
        return _create_secure_refresh_token(token_data)
    else:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Back-compat re-exports: real bodies now live in auth/dependencies.py.
# All existing `from main import get_current_user` calls continue to work.
from auth.dependencies import (  # noqa: F401
    get_current_user,
    get_current_user_flexible,
)


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
    """Helper function to log AI actions to Mission Control for tracking."""
    try:
        import time
        action_id = f"{agent_name.lower().replace(' ', '_')}_{int(time.time() * 1000)}"
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
        logger.info(f"Mission Control: Logged {agent_name} action {action_id}")
        return action_id
    except Exception as e:
        logger.error(f"Failed to log AI action to Mission Control: {e}")
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
    """Update the outcome of a Mission Control action."""
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
            logger.info(f"Mission Control: Updated action {action_id} outcome to {outcome}")
            return True
        else:
            logger.warning(f"Mission Control: Action {action_id} not found")
            return False
    except Exception as e:
        logger.error(f"Failed to update AI action outcome: {e}")
        db.rollback()
        return False


# ============================================================================
# CREATE APPLICATION via App Factory
# ============================================================================

from app_factory import create_app

app = create_app(
    engine=engine,
    SessionLocal=SessionLocal,
    get_db=get_db,
    get_current_user=get_current_user,
    get_current_user_flexible=get_current_user_flexible,
    oauth2_scheme=oauth2_scheme,
    pwd_context=pwd_context,
    scheduler=scheduler,
    openai_client=openai_client,
    graceful_shutdown=graceful_shutdown,
    SECRET_KEY=SECRET_KEY,
    ENVIRONMENT=ENVIRONMENT,
    DATABASE_URL=DATABASE_URL,
    create_access_token=create_access_token,
    create_refresh_token=create_refresh_token,
    get_password_hash=get_password_hash,
    verify_password=verify_password,
    get_cached=get_cached,
    set_cached=set_cached,
    clear_cache=clear_cache,
    log_ai_action_to_mission_control=log_ai_action_to_mission_control,
    update_ai_action_outcome=update_ai_action_outcome,
    security_stats=security_stats,
    User=User,
)

# ============================================================================
# BACKWARD COMPATIBILITY RE-EXPORTS
# ============================================================================
# Many files do `from main import X`. These re-exports MUST remain.

# Re-export standalone utilities
from utils.lead_scoring import calculate_lead_score  # noqa: F811
from utils.email_signature import generate_email_signature_html  # noqa: F811

# Re-export encrypt/decrypt from calendly service
try:
    from services.calendly_service import encrypt_token, decrypt_token
except ImportError:
    pass

# ============================================================================
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
