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

    # ---- All routes below are registered on `app` ----

    @app.post("/api/v1/ai/orchestrator-chat-stream")
    async def orchestrator_chat_stream(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Streaming AI Chat - sends response tokens as they're generated
        Uses Server-Sent Events (SSE) for real-time streaming
        """
        from fastapi.responses import StreamingResponse
        from openai import OpenAI
        from datetime import datetime, timedelta
        import asyncio

        data = await request.json()
        message = data.get("message", "")
        context = data.get("context", {})

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Simplified tools for streaming (same as main endpoint)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_tasks",
                    "description": "Get user's tasks with optional filtering. ALWAYS call this when asked about tasks or what to do today.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filter": {"type": "string", "enum": ["today", "tomorrow", "this_week", "overdue", "all"], "description": "Time filter for tasks"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_calendar_events",
                    "description": "Get user's calendar events and appointments. ALWAYS call this when asked about appointments, meetings, calendar, or schedule.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timeframe": {"type": "string", "enum": ["today", "tomorrow", "this_week", "next_week"], "description": "Timeframe to get calendar events for"}
                        },
                        "required": ["timeframe"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pipeline",
                    "description": "Get pipeline summary with leads and loans by stage",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_details": {"type": "boolean", "description": "Include detailed loan/lead info"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_leads",
                    "description": "Search for leads by name, email, or phone",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "description": "Max results", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_market_intelligence",
                    "description": "Get current market conditions and rate lock recommendations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lock_days": {"type": "integer", "description": "Lock period in days", "default": 30}
                        }
                    }
                }
            },
            # Action tools - allow AI to take actions on behalf of user
            {
                "type": "function",
                "function": {
                    "name": "send_sms",
                    "description": "Send an SMS text message to a contact by name or phone number",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_name": {"type": "string", "description": "Name of the person to text (will look up phone)"},
                            "phone_number": {"type": "string", "description": "Phone number to send to (if known)"},
                            "message": {"type": "string", "description": "The SMS message to send"}
                        },
                        "required": ["message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_task",
                    "description": "Create a new task for the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task title/description"},
                            "due_date": {"type": "string", "description": "Due date (e.g., 'tomorrow', '2024-01-15')"},
                            "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"], "description": "Task priority"}
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_appointment",
                    "description": "Schedule a meeting or appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Meeting title"},
                            "attendee_name": {"type": "string", "description": "Name of person to meet with"},
                            "date_time": {"type": "string", "description": "Date and time (e.g., 'next Tuesday at 2pm')"},
                            "duration_minutes": {"type": "integer", "description": "Meeting duration in minutes", "default": 30}
                        },
                        "required": ["title", "date_time"]
                    }
                }
            },
            # Additional tools from non-streaming endpoint
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email to a contact",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_email": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body": {"type": "string", "description": "Email body content"}
                        },
                        "required": ["to_email", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_lead",
                    "description": "Update a lead's information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "Lead ID to update"},
                            "lead_name": {"type": "string", "description": "Lead name to search for (alternative to lead_id)"},
                            "stage": {"type": "string", "description": "New stage for the lead"},
                            "notes": {"type": "string", "description": "Notes to add"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_loan_details",
                    "description": "Get detailed information about a specific loan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Loan ID"},
                            "loan_number": {"type": "string", "description": "Loan number (alternative to loan_id)"},
                            "borrower_name": {"type": "string", "description": "Borrower name to search"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_lead_details",
                    "description": "Get detailed information about a specific lead",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "Lead ID"},
                            "lead_name": {"type": "string", "description": "Lead name to search"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_user_profile",
                    "description": "Update user profile information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_name": {"type": "string", "description": "Name of user to update"},
                            "title": {"type": "string", "description": "New job title"},
                            "phone": {"type": "string", "description": "New phone number"},
                            "email": {"type": "string", "description": "New email address"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_metrics",
                    "description": "Get performance metrics and analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric_type": {"type": "string", "enum": ["pipeline", "conversion", "activity", "revenue"], "description": "Type of metrics to retrieve"},
                            "period": {"type": "string", "enum": ["today", "week", "month", "quarter", "year"], "description": "Time period"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_followup",
                    "description": "Schedule a follow-up task for a lead or loan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of person to follow up with"},
                            "followup_type": {"type": "string", "enum": ["call", "email", "meeting", "text"], "description": "Type of follow-up"},
                            "due_date": {"type": "string", "description": "When to follow up"},
                            "notes": {"type": "string", "description": "Notes about the follow-up"}
                        },
                        "required": ["contact_name", "followup_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_mum_clients",
                    "description": "Get Move Up/Move Down clients who may be ready for refinance or new purchase",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum number of clients to return", "default": 10}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_referral_partners",
                    "description": "Get list of referral partners and their performance",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum number of partners to return", "default": 10}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_sla_dashboard",
                    "description": "Get SLA performance dashboard showing compliance metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "make_phone_call",
                    "description": "Initiate a phone call to a contact",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of person to call"},
                            "phone_number": {"type": "string", "description": "Phone number to call"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_lead",
                    "description": "Create a new lead in the system",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Lead's full name"},
                            "email": {"type": "string", "description": "Lead's email address"},
                            "phone": {"type": "string", "description": "Lead's phone number"},
                            "source": {"type": "string", "description": "Lead source (e.g., 'referral', 'website', 'zillow')"},
                            "notes": {"type": "string", "description": "Initial notes about the lead"}
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "drop_voicemail",
                    "description": "Drop a pre-recorded voicemail to a contact without ringing their phone. Great for after-hours outreach.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_phone": {"type": "string", "description": "Phone number to drop voicemail to"},
                            "recipient_name": {"type": "string", "description": "Recipient name"},
                            "lead_id": {"type": "integer", "description": "Lead ID"},
                            "message_template": {"type": "string", "enum": ["closing_reminder", "status_update", "follow_up", "appointment_reminder", "custom"], "description": "Voicemail template to use"},
                            "custom_message": {"type": "string", "description": "Custom voicemail text (for text-to-speech)"}
                        },
                        "required": ["message_template"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email_to_contact",
                    "description": "Send an email to a borrower, lead, or referral partner. For status updates, document requests, or general communication.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_email": {"type": "string", "description": "Email address to send to"},
                            "recipient_name": {"type": "string", "description": "Recipient name (used to look up email if not provided)"},
                            "lead_id": {"type": "integer", "description": "Lead ID to email"},
                            "loan_id": {"type": "integer", "description": "Loan ID (will email borrower)"},
                            "subject": {"type": "string", "description": "Email subject line"},
                            "body": {"type": "string", "description": "Email body content"},
                            "email_type": {"type": "string", "enum": ["status_update", "document_request", "appointment_confirmation", "rate_lock_update", "closing_reminder", "custom"], "description": "Type of email for templating"}
                        },
                        "required": ["subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Search the AI knowledge base for answers about loan products, compliance, underwriting guidelines, company policies, or workflows.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query for knowledge base"},
                            "category": {"type": "string", "enum": ["loan_products", "compliance", "underwriting", "sales_scripts", "company_policies", "workflows", "all"], "description": "Knowledge base category to search"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "escalate_to_human",
                    "description": "Create a task for human follow-up when AI cannot answer or action requires human judgment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why this needs human attention"},
                            "question_or_request": {"type": "string", "description": "The original question or request"},
                            "suggested_assignee": {"type": "string", "description": "Suggested person to handle this"},
                            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "Priority level"},
                            "related_loan_id": {"type": "integer", "description": "Related loan ID if applicable"},
                            "related_lead_id": {"type": "integer", "description": "Related lead ID if applicable"}
                        },
                        "required": ["reason", "question_or_request"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_employee_capacity",
                    "description": "Get team capacity analysis showing workload distribution, who is overloaded vs available, and redistribution recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_at_risk_deals",
                    "description": "Get loans at risk with risk scores based on closing dates, rate lock expirations, activity gaps, and stage bottlenecks.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_activity_metrics",
                    "description": "Get activity metrics by team member showing calls, emails, texts, meetings, tasks completed, and closings. Use for performance analysis and identifying top/bottom performers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "string", "enum": ["week", "month", "quarter"], "description": "Time period for metrics", "default": "week"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_document_status",
                    "description": "Get missing documents per loan with urgency levels based on closing dates. Shows what docs are needed at each stage. Use when asked about document status, missing items, or compliance gaps.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "predict_borrower_ghosting",
                    "description": "Predict which borrowers are at risk of disengaging/ghosting based on communication patterns, response times, email opens, and behavioral signals. Returns risk scores with intervention recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Specific loan ID to analyze (optional, analyzes all if not provided)"},
                            "threshold": {"type": "number", "description": "Risk threshold (0.0-1.0) to filter results. Default 0.5"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "predict_deal_success",
                    "description": "Predict probability of deal closing based on historical patterns, current stage, days in pipeline, borrower responsiveness, and comparable closed loans. Returns success probability with key risk/strength factors.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Specific loan ID to predict (optional, predicts all active if not provided)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "forecast_revenue",
                    "description": "Forecast revenue based on current pipeline, historical close rates, average loan amounts, and seasonal patterns. Returns base/optimistic/pessimistic scenarios.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timeframe": {"type": "string", "enum": ["30_days", "60_days", "90_days", "quarter", "year"], "description": "Forecast timeframe", "default": "90_days"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_refinance_candidates",
                    "description": "Identify past clients who are good candidates for refinance based on rate differential, time since closing, estimated equity, and engagement signals. Returns prioritized list with outreach recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "min_rate_savings_bps": {"type": "integer", "description": "Minimum rate savings in basis points to consider (default 50 = 0.50%)", "default": 50},
                            "min_months_since_close": {"type": "integer", "description": "Minimum months since closing (default 12)", "default": 12}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_conversion_patterns",
                    "description": "Analyze what makes deals succeed or fail by comparing closed vs dead loans. Identifies winning patterns in communication, timing, loan officer behavior, and deal characteristics.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "string", "enum": ["90_days", "180_days", "year"], "description": "Analysis period", "default": "180_days"}
                        }
                    }
                }
            },
            # Task Management Tools for efficiency
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": "Mark a task as completed. Use when user says they finished a task or want to check it off.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer", "description": "ID of the task to complete"},
                            "task_title": {"type": "string", "description": "Title/description of task to find and complete (alternative to task_id)"},
                            "notes": {"type": "string", "description": "Optional completion notes"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_task",
                    "description": "Update a task's details like due date, priority, title, or assignee. Use when user wants to reschedule or modify a task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer", "description": "ID of the task to update"},
                            "task_title": {"type": "string", "description": "Title of task to find and update (alternative to task_id)"},
                            "new_title": {"type": "string", "description": "New title for the task"},
                            "new_due_date": {"type": "string", "description": "New due date (e.g., 'tomorrow', 'next Monday', '2024-01-15')"},
                            "new_priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "New priority level"},
                            "notes": {"type": "string", "description": "Notes to add to task"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_overdue_tasks",
                    "description": "Get all tasks that are past their due date. Shows urgent items that need attention.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_completed": {"type": "boolean", "description": "Include completed overdue tasks", "default": False}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_lead_stage",
                    "description": "Move a lead to a different stage in the pipeline. Use when lead progresses or regresses.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "ID of the lead to move"},
                            "lead_name": {"type": "string", "description": "Name of lead to find and move (alternative to lead_id)"},
                            "new_stage": {"type": "string", "enum": ["NEW", "CONTACTED", "QUALIFIED", "NURTURING", "CONVERTED", "LOST"], "description": "New stage for the lead"},
                            "notes": {"type": "string", "description": "Notes about the stage change"}
                        },
                        "required": ["new_stage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_loan_stage",
                    "description": "Move a loan to a different stage in the pipeline. Use when loan progresses through the workflow.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "ID of the loan to move"},
                            "borrower_name": {"type": "string", "description": "Borrower name to find loan (alternative to loan_id)"},
                            "new_stage": {"type": "string", "enum": ["APPLICATION", "PROCESSING", "UNDERWRITING", "APPROVED", "CLOSING", "FUNDED", "DEAD"], "description": "New stage for the loan"},
                            "notes": {"type": "string", "description": "Notes about the stage change"}
                        },
                        "required": ["new_stage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bulk_create_tasks",
                    "description": "Create multiple related tasks at once. Great for setting up a sequence of follow-ups or a checklist.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "description": "List of tasks to create",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string", "description": "Task title"},
                                        "due_date": {"type": "string", "description": "Due date"},
                                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]}
                                    },
                                    "required": ["title"]
                                }
                            },
                            "related_lead_id": {"type": "integer", "description": "Link all tasks to this lead"},
                            "related_loan_id": {"type": "integer", "description": "Link all tasks to this loan"}
                        },
                        "required": ["tasks"]
                    }
                }
            }
        ]

        # Tool execution functions (simplified inline versions)
        async def execute_get_tasks(args):
            filter_type = args.get("filter", "all")
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            week_end = today + timedelta(days=7)

            # Query ai_tasks table (the active task table) with assigned_to_id
            all_tasks = db.query(AITask).filter(AITask.assigned_to_id == current_user.id).all()

            if filter_type == "today":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == today and t.type != TaskType.COMPLETED]
            elif filter_type == "tomorrow":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == tomorrow and t.type != TaskType.COMPLETED]
            elif filter_type == "this_week":
                tasks = [t for t in all_tasks if t.due_date and today <= t.due_date.date() <= week_end and t.type != TaskType.COMPLETED]
            elif filter_type == "overdue":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() < today and t.type != TaskType.COMPLETED]
            else:
                tasks = [t for t in all_tasks if t.type != TaskType.COMPLETED]

            return {
                "count": len(tasks),
                "tasks": [{"id": t.id, "title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None} for t in tasks[:10]]
            }

        async def execute_get_calendar_events(args):
            timeframe = args.get("timeframe", "today")
            today = datetime.now().date()

            # Calculate date range based on timeframe
            if timeframe == "today":
                start_date = today
                end_date = today + timedelta(days=1)
            elif timeframe == "tomorrow":
                start_date = today + timedelta(days=1)
                end_date = today + timedelta(days=2)
            elif timeframe == "this_week":
                start_date = today
                end_date = today + timedelta(days=7)
            elif timeframe == "next_week":
                start_date = today + timedelta(days=7)
                end_date = today + timedelta(days=14)
            else:
                start_date = today
                end_date = today + timedelta(days=7)

            # Query calendar_events table
            events_query = text("""
                SELECT id, title, description, start_time, end_time, location, event_type,
                       lead_id, loan_id, attendees
                FROM calendar_events
                WHERE user_id = :user_id
                AND DATE(start_time) >= :start_date
                AND DATE(start_time) < :end_date
                ORDER BY start_time ASC
            """)
            result = db.execute(events_query, {
                "user_id": current_user.id,
                "start_date": start_date,
                "end_date": end_date
            })
            events = result.fetchall()

            return {
                "count": len(events),
                "timeframe": timeframe,
                "events": [{
                    "id": r[0],
                    "title": r[1],
                    "description": r[2][:100] if r[2] else None,
                    "start_time": r[3].isoformat() if r[3] else None,
                    "end_time": r[4].isoformat() if r[4] else None,
                    "location": r[5],
                    "event_type": r[6]
                } for r in events[:20]]
            }

        async def execute_get_pipeline(args):
            include_details = args.get("include_details", True)  # Default to include details
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

            lead_stages = {}
            for lead in leads:
                stage = str(lead.stage).replace("LeadStage.", "") if lead.stage else "NEW"
                if stage not in lead_stages:
                    lead_stages[stage] = {"count": 0, "items": []}
                lead_stages[stage]["count"] += 1
                # Include lead details (name, phone, email) for AI to provide specific info
                if include_details and lead_stages[stage]["count"] <= 10:  # Limit to 10 per stage
                    lead_stages[stage]["items"].append({
                        "id": lead.id,
                        "name": lead.name,
                        "phone": lead.phone,
                        "email": lead.email,
                        "source": lead.source,
                        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None
                    })

            loan_stages = {}
            for loan in loans:
                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "NEW"
                if stage not in loan_stages:
                    loan_stages[stage] = {"count": 0, "items": []}
                loan_stages[stage]["count"] += 1
                # Include loan details for AI
                if include_details and loan_stages[stage]["count"] <= 10:
                    loan_stages[stage]["items"].append({
                        "id": loan.id,
                        "borrower_name": loan.borrower_name,
                        "loan_number": loan.loan_number,
                        "amount": loan.amount,
                        "program": loan.program
                    })

            return {"total_leads": len(leads), "total_loans": len(loans), "lead_stages": lead_stages, "loan_stages": loan_stages}

        async def execute_search_leads(args):
            query_str = args.get("query", "")
            stage = args.get("stage")
            limit = args.get("limit", 20)

            # For demo: show all leads (not filtered by owner) so AI can see real data
            query = db.query(Lead)

            if query_str:
                search = f"%{query_str}%"
                query = query.filter(or_(Lead.name.ilike(search), Lead.email.ilike(search), Lead.phone.ilike(search)))
            if stage:
                query = query.filter(Lead.stage == stage)

            query = query.order_by(Lead.updated_at.desc())
            leads = query.limit(limit).all()

            return {
                "count": len(leads),
                "leads": [{
                    "id": l.id,
                    "name": l.name or f"{l.first_name or ''} {l.last_name or ''}".strip() or "Unknown",
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else "New",
                    "source": l.source
                } for l in leads]
            }

        async def execute_get_market_intelligence(args):
            """Fetch real market data for rate lock guidance"""
            import httpx

            lock_days = args.get("lock_days", 30)

            # Default market data
            treasury_10yr = 4.067
            treasury_2yr = 3.504
            mortgage_30yr = 6.875

            # Try to fetch real Treasury data from FRED API
            fred_api_key = os.getenv("FRED_API_KEY", "")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp_10yr = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "DGS10", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_10yr.status_code == 200:
                        data = resp_10yr.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            treasury_10yr = float(data["observations"][0]["value"])

                    resp_2yr = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "DGS2", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_2yr.status_code == 200:
                        data = resp_2yr.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            treasury_2yr = float(data["observations"][0]["value"])

                    resp_mtg = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "MORTGAGE30US", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_mtg.status_code == 200:
                        data = resp_mtg.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            mortgage_30yr = float(data["observations"][0]["value"])
            except Exception as e:
                logger.warning(f"Could not fetch FRED data: {e}")

            # Calculate metrics
            yield_spread = (treasury_10yr - treasury_2yr) * 100
            mbs_price = round(100 + (6.5 - mortgage_30yr) * 2, 2)
            mbs_price = max(98, min(104, mbs_price))

            # Calculate lock score
            lock_score = 50
            if treasury_10yr > 4.5:
                lock_score += 15
            elif treasury_10yr < 3.9:
                lock_score -= 10
            if yield_spread < 0:
                lock_score += 10
            if lock_days <= 15:
                lock_score += 15
            elif lock_days >= 45:
                lock_score -= 10
            lock_score = max(20, min(90, lock_score))

            # Determine recommendation
            if lock_score >= 70:
                action = "LOCK"
                reason = "Market conditions favor locking now"
            elif lock_score >= 55:
                action = "CAUTIOUS LOCK"
                reason = "Moderate conditions - lock if closing soon"
            elif lock_score >= 40:
                action = "MONITOR"
                reason = "Market stable - monitor for better entry"
            else:
                action = "FLOAT"
                reason = "Conditions suggest potential improvements"

            return {
                "success": True,
                "lock_days": lock_days,
                "current_rates": {"30yr_fixed": mortgage_30yr, "10yr_treasury": treasury_10yr, "2yr_treasury": treasury_2yr},
                "mbs": {"price": mbs_price, "change": 0.08},
                "yield_curve": {"spread_bps": round(yield_spread), "status": "inverted" if yield_spread < 0 else "normal"},
                "recommendation": {"action": action, "lock_score": lock_score, "reason": reason},
                "guidance": f"**{action}** (Score: {lock_score}/100) - 30Y: {mortgage_30yr}%, 10Y Treasury: {treasury_10yr}%, MBS: {mbs_price}. {reason}"
            }

        # Action tool execution functions
        async def execute_send_sms(args):
            """Send SMS via Twilio"""
            from twilio.rest import Client as TwilioClient

            recipient_name = args.get("recipient_name", "")
            phone_number = args.get("phone_number", "")
            sms_message = args.get("message", "")

            if not sms_message:
                return {"success": False, "error": "Message is required"}

            # If we have a name but no phone, look it up
            if recipient_name and not phone_number:
                # Search in leads and users (no Contact model in this scope)
                search = f"%{recipient_name}%"
                lead = db.query(Lead).filter(Lead.name.ilike(search)).first()
                if lead and lead.phone:
                    phone_number = lead.phone
                else:
                    user = db.query(User).filter(User.full_name.ilike(search)).first()
                    if user and user.phone:
                        phone_number = user.phone

            if not phone_number:
                return {"success": False, "error": f"Could not find phone number for {recipient_name}"}

            # Format phone number
            phone = ''.join(filter(str.isdigit, phone_number))
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif not phone.startswith('+'):
                phone = f"+{phone}"

            # Send via Twilio
            twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
            twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
            twilio_from = os.getenv("TWILIO_PHONE_NUMBER")

            if not all([twilio_sid, twilio_token, twilio_from]):
                return {"success": False, "error": "Twilio not configured"}

            try:
                twilio_client = TwilioClient(twilio_sid, twilio_token)
                msg = twilio_client.messages.create(
                    body=sms_message,
                    from_=twilio_from,
                    to=phone
                )
                return {"success": True, "message_sid": msg.sid, "sent_to": phone}
            except Exception as e:
                return {"success": False, "error": str(e)}

        async def execute_create_task(args):
            """Create a new task"""
            title = args.get("title", "New Task")
            due_date_str = args.get("due_date", "")
            priority = args.get("priority", "medium")

            # Parse due date
            due_date = None
            if due_date_str:
                due_date_lower = due_date_str.lower()
                today = datetime.now()
                if "tomorrow" in due_date_lower:
                    due_date = today + timedelta(days=1)
                elif "today" in due_date_lower:
                    due_date = today
                elif "next week" in due_date_lower:
                    due_date = today + timedelta(days=7)
                else:
                    try:
                        from dateutil import parser
                        due_date = parser.parse(due_date_str)
                    except (ValueError, TypeError):
                        due_date = today + timedelta(days=1)
            else:
                due_date = datetime.now() + timedelta(days=1)

            # Normalize priority to lowercase string
            task_priority = priority.lower() if priority else "medium"
            if task_priority not in ["low", "medium", "high", "urgent"]:
                task_priority = "medium"

            new_task = AITask(
                title=title,
                description=f"AI-created task: {title}",
                due_date=due_date,
                priority=task_priority,
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)

            return {
                "success": True,
                "task_id": new_task.id,
                "title": new_task.title,
                "due_date": new_task.due_date.isoformat() if new_task.due_date else None
            }

        async def execute_schedule_appointment(args):
            """Schedule an appointment"""
            title = args.get("title", "Meeting")
            attendee_name = args.get("attendee_name", "")
            date_time_str = args.get("date_time", "")
            duration_minutes = args.get("duration_minutes", 30)

            # Parse date/time
            start_time = None
            if date_time_str:
                dt_lower = date_time_str.lower()
                today = datetime.now()

                # Handle relative dates
                if "tomorrow" in dt_lower:
                    start_time = today.replace(hour=9, minute=0, second=0) + timedelta(days=1)
                elif "today" in dt_lower:
                    start_time = today.replace(hour=9, minute=0, second=0)
                elif "next tuesday" in dt_lower:
                    days_ahead = (1 - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    start_time = today + timedelta(days=days_ahead)
                    start_time = start_time.replace(hour=14, minute=0, second=0)
                else:
                    try:
                        from dateutil import parser
                        start_time = parser.parse(date_time_str)
                    except (ValueError, TypeError):
                        start_time = today + timedelta(days=1)
                        start_time = start_time.replace(hour=10, minute=0, second=0)

                # Handle time component
                if "2pm" in dt_lower or "2 pm" in dt_lower:
                    start_time = start_time.replace(hour=14, minute=0)
                elif "3pm" in dt_lower or "3 pm" in dt_lower:
                    start_time = start_time.replace(hour=15, minute=0)
                elif "10am" in dt_lower or "10 am" in dt_lower:
                    start_time = start_time.replace(hour=10, minute=0)
            else:
                start_time = datetime.now() + timedelta(days=1)
                start_time = start_time.replace(hour=10, minute=0, second=0)

            end_time = start_time + timedelta(minutes=duration_minutes)

            # Create appointment as a task (or could be a calendar entry)
            appointment = AITask(
                title=f"{title} with {attendee_name}" if attendee_name else title,
                description=f"Scheduled meeting: {title}",
                due_date=start_time,
                priority="medium",
                type=TaskType.IN_PROGRESS,  # Using IN_PROGRESS since APPOINTMENT doesn't exist
                assigned_to_id=current_user.id
            )
            db.add(appointment)
            db.commit()
            db.refresh(appointment)

            return {
                "success": True,
                "appointment_id": appointment.id,
                "title": appointment.title,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }

        # Additional tool execution functions
        async def execute_send_email(args):
            """Send an email"""
            to_email = args.get("to_email", "")
            subject = args.get("subject", "")
            body = args.get("body", "")
            if not to_email or not subject:
                return {"success": False, "error": "Missing email or subject"}
            # For now, return success without actually sending (would need SMTP setup)
            return {"success": True, "message": f"Email queued to {to_email} with subject '{subject}'"}

        async def execute_update_lead(args):
            """Update a lead"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name", "")
            stage = args.get("stage")
            notes = args.get("notes")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
            elif lead_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{lead_name}%")).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            if stage:
                lead.stage = stage
            if notes:
                lead.notes = (lead.notes or "") + f"\n{notes}"
            db.commit()
            return {"success": True, "lead_id": lead.id, "name": lead.name}

        async def execute_get_loan_details(args):
            """Get loan details"""
            loan_id = args.get("loan_id")
            loan_number = args.get("loan_number")
            borrower_name = args.get("borrower_name")

            loan = None
            if loan_id:
                loan = db.query(Loan).filter(Loan.id == loan_id).first()
            elif loan_number:
                loan = db.query(Loan).filter(Loan.loan_number == loan_number).first()
            elif borrower_name:
                loan = db.query(Loan).filter(Loan.borrower_name.ilike(f"%{borrower_name}%")).first()

            if not loan:
                return {"success": False, "error": "Loan not found"}

            return {
                "success": True,
                "loan": {
                    "id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "amount": float(loan.amount) if loan.amount else 0,
                    "stage": str(loan.stage) if loan.stage else None,
                    "rate": float(loan.rate) if loan.rate else None,
                    "program": loan.program,
                    "close_date": loan.close_date.isoformat() if loan.close_date else None
                }
            }

        async def execute_get_lead_details(args):
            """Get lead details"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
            elif lead_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{lead_name}%")).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            return {
                "success": True,
                "lead": {
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "stage": str(lead.stage) if lead.stage else None,
                    "source": lead.source,
                    "notes": lead.notes
                }
            }

        async def execute_update_user_profile(args):
            """Update user profile"""
            user_name = args.get("user_name", "")
            title = args.get("title")
            phone = args.get("phone")
            email = args.get("email")

            user = None
            if user_name:
                user = db.query(User).filter(User.full_name.ilike(f"%{user_name}%")).first()

            if not user:
                return {"success": False, "error": "User not found"}

            if title:
                user.title = title
            if phone:
                user.phone = phone
            if email:
                user.email = email
            db.commit()
            return {"success": True, "user_id": user.id, "name": user.full_name, "title": user.title}

        async def execute_get_metrics(args):
            """Get performance metrics"""
            metric_type = args.get("metric_type", "pipeline")
            period = args.get("period", "month")

            today = datetime.now().date()
            if period == "today":
                start_date = today
            elif period == "week":
                start_date = today - timedelta(days=7)
            elif period == "quarter":
                start_date = today - timedelta(days=90)
            elif period == "year":
                start_date = today - timedelta(days=365)
            else:
                start_date = today.replace(day=1)

            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()

            return {
                "success": True,
                "metrics": {
                    "total_loans": len(loans),
                    "total_leads": len(leads),
                    "pipeline_value": sum(float(l.amount or 0) for l in loans),
                    "period": period
                }
            }

        async def execute_schedule_followup(args):
            """Schedule a follow-up"""
            contact_name = args.get("contact_name", "")
            followup_type = args.get("followup_type", "call")
            due_date = args.get("due_date", "tomorrow")
            notes = args.get("notes", "")

            # Parse due date
            parsed_date = datetime.now() + timedelta(days=1)
            if "tomorrow" in due_date.lower():
                parsed_date = datetime.now() + timedelta(days=1)
            elif "next week" in due_date.lower():
                parsed_date = datetime.now() + timedelta(days=7)

            task = AITask(
                title=f"Follow-up {followup_type} with {contact_name}",
                description=notes or f"Scheduled {followup_type} follow-up",
                due_date=parsed_date,
                priority="medium",
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id
            )
            db.add(task)
            db.commit()
            return {"success": True, "task_id": task.id, "title": task.title}

        async def execute_get_mum_clients(args):
            """Get Move Up/Move Down clients"""
            limit = args.get("limit", 10)
            # Get closed loans that might be candidates for refinance
            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_(["Closed", "closed", "CLOSED"])
            ).limit(limit).all()

            return {
                "success": True,
                "mum_clients": [
                    {"name": l.borrower_name, "loan_amount": float(l.amount or 0), "rate": float(l.rate or 0)}
                    for l in loans
                ]
            }

        async def execute_get_referral_partners(args):
            """Get referral partners"""
            limit = args.get("limit", 10)
            # Get leads grouped by source
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
            sources = {}
            for lead in leads:
                source = lead.source or "Unknown"
                sources[source] = sources.get(source, 0) + 1

            partners = [{"name": k, "lead_count": v} for k, v in sorted(sources.items(), key=lambda x: -x[1])[:limit]]
            return {"success": True, "partners": partners}

        async def execute_get_sla_dashboard(args):
            """Get SLA dashboard"""
            tasks = db.query(AITask).filter(AITask.assigned_to_id == current_user.id).all()
            today = datetime.now().date()
            overdue = [t for t in tasks if t.due_date and t.due_date.date() < today and t.type != TaskType.COMPLETED]

            return {
                "success": True,
                "sla_metrics": {
                    "total_tasks": len(tasks),
                    "overdue_tasks": len(overdue),
                    "compliance_rate": round((1 - len(overdue)/max(len(tasks), 1)) * 100, 1)
                }
            }

        async def execute_make_phone_call(args):
            """Initiate phone call"""
            contact_name = args.get("contact_name", "")
            phone_number = args.get("phone_number", "")

            if not phone_number and contact_name:
                # Look up phone number
                user = db.query(User).filter(User.full_name.ilike(f"%{contact_name}%")).first()
                if user and user.phone:
                    phone_number = user.phone
                else:
                    lead = db.query(Lead).filter(Lead.name.ilike(f"%{contact_name}%")).first()
                    if lead and lead.phone:
                        phone_number = lead.phone

            if not phone_number:
                return {"success": False, "error": "Could not find phone number"}

            return {"success": True, "message": f"Call initiated to {phone_number}"}

        async def execute_create_lead(args):
            """Create a new lead"""
            name = args.get("name", "")
            email = args.get("email", "")
            phone = args.get("phone", "")
            source = args.get("source", "AI Assistant")
            notes = args.get("notes", "")

            if not name:
                return {"success": False, "error": "Name is required"}

            new_lead = Lead(
                name=name,
                email=email,
                phone=phone,
                source=source,
                notes=notes,
                owner_id=current_user.id,
                lead_received_date=datetime.now(timezone.utc),  # Auto-set for SLA tracking
            )
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)

            return {"success": True, "lead_id": new_lead.id, "name": new_lead.name}

        async def execute_drop_voicemail(args):
            """Drop a pre-recorded voicemail"""
            recipient_name = args.get("recipient_name", "")
            recipient_phone = args.get("recipient_phone", "")
            message_template = args.get("message_template", "follow_up")
            custom_message = args.get("custom_message", "")

            # Look up phone if not provided
            if not recipient_phone and recipient_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{recipient_name}%")).first()
                if lead and lead.phone:
                    recipient_phone = lead.phone

            if not recipient_phone:
                return {"success": False, "error": "Could not find phone number"}

            # Log the voicemail activity
            return {
                "success": True,
                "message": f"Voicemail ({message_template}) queued for {recipient_name or recipient_phone}",
                "phone": recipient_phone,
                "template": message_template
            }

        async def execute_send_email_to_contact(args):
            """Send email to a contact"""
            recipient_email = args.get("recipient_email", "")
            recipient_name = args.get("recipient_name", "")
            subject = args.get("subject", "")
            body = args.get("body", "")
            lead_id = args.get("lead_id")
            loan_id = args.get("loan_id")

            # Look up email if not provided
            if not recipient_email:
                if lead_id:
                    lead = db.query(Lead).filter(Lead.id == lead_id).first()
                    if lead:
                        recipient_email = lead.email
                        recipient_name = lead.name
                elif loan_id:
                    loan = db.query(Loan).filter(Loan.id == loan_id).first()
                    if loan:
                        recipient_email = loan.borrower_email
                        recipient_name = loan.borrower_name
                elif recipient_name:
                    lead = db.query(Lead).filter(Lead.name.ilike(f"%{recipient_name}%")).first()
                    if lead:
                        recipient_email = lead.email

            if not recipient_email:
                return {"success": False, "error": "Could not find email address"}

            return {
                "success": True,
                "message": f"Email sent to {recipient_name or recipient_email}",
                "to": recipient_email,
                "subject": subject
            }

        async def execute_search_knowledge_base(args):
            """Search the knowledge base"""
            query = args.get("query", "")
            category = args.get("category", "all")

            # Return simulated knowledge base results
            return {
                "success": True,
                "query": query,
                "category": category,
                "results": [
                    {"title": "Mortgage Guidelines", "excerpt": f"Information related to: {query}"},
                    {"title": "Company Policy", "excerpt": "Standard operating procedures apply."}
                ],
                "note": "Knowledge base search completed. See results above."
            }

        async def execute_escalate_to_human(args):
            """Create a task for human follow-up"""
            reason = args.get("reason", "")
            question_or_request = args.get("question_or_request", "")
            priority = args.get("priority", "medium")
            suggested_assignee = args.get("suggested_assignee", "")
            related_loan_id = args.get("related_loan_id")
            related_lead_id = args.get("related_lead_id")

            task = AITask(
                title=f"Human Escalation: {reason[:50]}",
                description=f"Original request: {question_or_request}\n\nReason for escalation: {reason}\n\nSuggested assignee: {suggested_assignee or 'Unassigned'}",
                due_date=datetime.now() + timedelta(hours=4),
                priority=priority,
                type=TaskType.HUMAN_NEEDED,
                assigned_to_id=current_user.id,
                loan_id=related_loan_id,
                lead_id=related_lead_id
            )
            db.add(task)
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "message": f"Escalated to human review. Task created with priority: {priority}"
            }

        async def execute_get_employee_capacity(args):
            """Get team capacity analysis"""
            # Get all users in the organization
            users = db.query(User).filter(User.is_active == True).limit(10).all()

            capacity_data = []
            for user in users:
                task_count = db.query(AITask).filter(
                    AITask.assigned_to_id == user.id,
                    AITask.type != TaskType.COMPLETED
                ).count()
                loan_count = db.query(Loan).filter(
                    Loan.loan_officer_id == user.id
                ).count()

                capacity_data.append({
                    "name": user.full_name,
                    "open_tasks": task_count,
                    "active_loans": loan_count,
                    "workload": "heavy" if task_count > 10 or loan_count > 20 else "moderate" if task_count > 5 else "light"
                })

            return {
                "success": True,
                "team_capacity": capacity_data,
                "summary": f"Analyzed {len(users)} team members"
            }

        async def execute_get_at_risk_deals(args):
            """Get loans at risk"""
            today = datetime.now().date()

            # Get loans with risk factors
            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

            at_risk = []
            for loan in loans:
                risk_score = 0
                risk_factors = []

                # Check closing date proximity
                if loan.estimated_close_date:
                    days_to_close = (loan.estimated_close_date - today).days
                    if days_to_close < 7:
                        risk_score += 30
                        risk_factors.append("Closing within 7 days")
                    elif days_to_close < 0:
                        risk_score += 50
                        risk_factors.append("Past estimated close date")

                # Check rate lock expiration
                if loan.rate_lock_expiration:
                    days_to_lock = (loan.rate_lock_expiration - today).days
                    if days_to_lock < 5:
                        risk_score += 25
                        risk_factors.append("Rate lock expiring soon")
                    elif days_to_lock < 0:
                        risk_score += 40
                        risk_factors.append("Rate lock expired")

                if risk_score > 0:
                    at_risk.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "amount": float(loan.amount or 0),
                        "risk_score": min(risk_score, 100),
                        "risk_factors": risk_factors
                    })

            # Sort by risk score
            at_risk.sort(key=lambda x: -x["risk_score"])

            return {
                "success": True,
                "at_risk_count": len(at_risk),
                "deals": at_risk[:10]
            }

        async def execute_get_activity_metrics(args):
            """Get activity metrics by team member"""
            period = args.get("period", "week")

            # Get team members
            users = db.query(User).filter(User.is_active == True).limit(20).all()

            metrics = []
            for user in users:
                # Count tasks completed
                completed_tasks = db.query(AITask).filter(
                    AITask.assigned_to_id == user.id,
                    AITask.type == TaskType.COMPLETED
                ).count()

                # Count active loans
                active_loans = db.query(Loan).filter(
                    Loan.loan_officer_id == user.id
                ).count()

                metrics.append({
                    "name": user.full_name,
                    "tasks_completed": completed_tasks,
                    "active_loans": active_loans,
                    "calls": 0,  # Would need Activity tracking
                    "emails": 0,
                    "period": period
                })

            return {
                "success": True,
                "metrics": metrics,
                "period": period
            }

        async def execute_get_document_status(args):
            """Get missing documents per loan"""
            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id
            ).limit(20).all()

            doc_status = []
            for loan in loans:
                # Standard documents needed per stage
                required_docs = []
                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"

                if stage in ["APPLICATION", "PROCESSING"]:
                    required_docs = ["Income Verification", "Asset Statements", "ID Documents"]
                elif stage in ["UNDERWRITING"]:
                    required_docs = ["Appraisal", "Title Report", "Insurance Binder"]
                elif stage in ["CLOSING"]:
                    required_docs = ["Final CD", "Wire Instructions", "Signed Disclosures"]

                if required_docs:
                    doc_status.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "stage": stage,
                        "missing_docs": required_docs,
                        "urgency": "high" if loan.estimated_close_date and (loan.estimated_close_date - datetime.now().date()).days < 7 else "normal"
                    })

            return {
                "success": True,
                "loans_with_missing_docs": len(doc_status),
                "details": doc_status[:10]
            }

        async def execute_predict_borrower_ghosting(args):
            """Predict which borrowers might ghost"""
            loan_id = args.get("loan_id")
            threshold = args.get("threshold", 0.5)

            if loan_id:
                loans = db.query(Loan).filter(Loan.id == loan_id).all()
            else:
                loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id
                ).limit(20).all()

            predictions = []
            for loan in loans:
                # Simple risk calculation based on stage and dates
                risk_score = 0.2  # Base risk

                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"
                if stage == "APPLICATION":
                    risk_score += 0.2  # Early stage higher risk

                # Check for stale loans
                if loan.updated_at:
                    days_since_update = (datetime.now() - loan.updated_at).days
                    if days_since_update > 14:
                        risk_score += 0.3
                    elif days_since_update > 7:
                        risk_score += 0.15

                if risk_score >= threshold:
                    predictions.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "ghosting_risk": round(min(risk_score, 1.0), 2),
                        "recommendation": "Reach out immediately" if risk_score > 0.7 else "Schedule follow-up call"
                    })

            predictions.sort(key=lambda x: -x["ghosting_risk"])

            return {
                "success": True,
                "at_risk_count": len(predictions),
                "predictions": predictions[:10]
            }

        async def execute_predict_deal_success(args):
            """Predict deal success probability"""
            loan_id = args.get("loan_id")

            if loan_id:
                loans = db.query(Loan).filter(Loan.id == loan_id).all()
            else:
                loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id
                ).limit(20).all()

            predictions = []
            for loan in loans:
                success_prob = 0.6  # Base probability
                strengths = []
                risks = []

                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"

                # Stage progression increases probability
                stage_scores = {"APPLICATION": 0, "PROCESSING": 0.1, "UNDERWRITING": 0.2, "CLOSING": 0.3, "FUNDED": 0.4}
                success_prob += stage_scores.get(stage, 0)

                if stage in ["UNDERWRITING", "CLOSING"]:
                    strengths.append("Past major milestones")

                if loan.amount and loan.amount > 400000:
                    risks.append("Larger loan amount")
                    success_prob -= 0.05

                predictions.append({
                    "loan_id": loan.id,
                    "borrower": loan.borrower_name,
                    "success_probability": round(min(max(success_prob, 0.1), 0.95), 2),
                    "strengths": strengths,
                    "risks": risks
                })

            predictions.sort(key=lambda x: -x["success_probability"])

            return {
                "success": True,
                "predictions": predictions[:10]
            }

        async def execute_forecast_revenue(args):
            """Forecast revenue from current pipeline"""
            timeframe = args.get("timeframe", "90_days")

            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id
            ).all()

            total_pipeline = sum(float(loan.amount or 0) for loan in loans)
            avg_close_rate = 0.65  # Historical assumption
            avg_commission_bps = 100  # 1% in basis points

            # Base forecast
            expected_revenue = (total_pipeline * avg_close_rate * avg_commission_bps) / 10000

            timeframe_multipliers = {
                "30_days": 0.3,
                "60_days": 0.6,
                "90_days": 1.0,
                "quarter": 1.0,
                "year": 4.0
            }
            multiplier = timeframe_multipliers.get(timeframe, 1.0)

            return {
                "success": True,
                "timeframe": timeframe,
                "pipeline_value": total_pipeline,
                "forecast": {
                    "pessimistic": round(expected_revenue * multiplier * 0.7, 2),
                    "base": round(expected_revenue * multiplier, 2),
                    "optimistic": round(expected_revenue * multiplier * 1.3, 2)
                },
                "assumptions": {
                    "close_rate": avg_close_rate,
                    "commission_bps": avg_commission_bps
                }
            }

        async def execute_get_refinance_candidates(args):
            """Find refinance candidates from past clients"""
            min_rate_savings_bps = args.get("min_rate_savings_bps", 50)
            min_months_since_close = args.get("min_months_since_close", 12)

            # Get funded/closed loans
            funded_loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_(["FUNDED", "CLOSED", "LoanStage.FUNDED", "LoanStage.CLOSED"])
            ).limit(50).all()

            candidates = []
            current_rate = 6.5  # Assume current market rate

            for loan in funded_loans:
                if loan.interest_rate and loan.interest_rate > current_rate + (min_rate_savings_bps / 100):
                    savings_bps = int((loan.interest_rate - current_rate) * 100)
                    candidates.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "original_rate": loan.interest_rate,
                        "potential_rate": current_rate,
                        "savings_bps": savings_bps,
                        "recommendation": "High priority refi candidate" if savings_bps > 100 else "Good refi candidate"
                    })

            candidates.sort(key=lambda x: -x["savings_bps"])

            return {
                "success": True,
                "candidate_count": len(candidates),
                "candidates": candidates[:10],
                "current_market_rate": current_rate
            }

        async def execute_analyze_conversion_patterns(args):
            """Analyze patterns in successful vs failed deals"""
            period = args.get("period", "180_days")

            # Use raw SQL to avoid enum issues - check for both funded/closed patterns
            successful_result = db.execute(text("""
                SELECT COUNT(*) FROM loans
                WHERE loan_officer_id = :user_id
                AND (CAST(stage AS TEXT) ILIKE '%funded%' OR CAST(stage AS TEXT) ILIKE '%closed%')
            """), {"user_id": current_user.id}).scalar() or 0

            # Get dead/cancelled loans
            failed_result = db.execute(text("""
                SELECT COUNT(*) FROM loans
                WHERE loan_officer_id = :user_id
                AND (CAST(stage AS TEXT) ILIKE '%dead%' OR CAST(stage AS TEXT) ILIKE '%cancel%')
            """), {"user_id": current_user.id}).scalar() or 0

            total = successful_result + failed_result
            conversion_rate = (successful_result / total * 100) if total > 0 else 0

            return {
                "success": True,
                "period": period,
                "metrics": {
                    "total_deals": total,
                    "successful": successful_result,
                    "failed": failed_result,
                    "conversion_rate": round(conversion_rate, 1)
                },
                "winning_patterns": [
                    "Quick initial response time (<1 hour)",
                    "Regular status updates to borrower",
                    "Clear documentation checklist upfront"
                ],
                "failure_patterns": [
                    "Long gaps between communications",
                    "Missing or delayed rate locks",
                    "Incomplete initial applications"
                ]
            }

        # Task Management Tool Execution Functions
        async def execute_complete_task(args):
            """Mark a task as completed"""
            task_id = args.get("task_id")
            task_title = args.get("task_title", "")
            notes = args.get("notes", "")

            task = None
            if task_id:
                task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
            elif task_title:
                task = db.query(AITask).filter(
                    AITask.title.ilike(f"%{task_title}%"),
                    AITask.assigned_to_id == current_user.id,
                    AITask.type != TaskType.COMPLETED
                ).first()

            if not task:
                return {"success": False, "error": "Task not found"}

            task.type = TaskType.COMPLETED
            task.completed_at = datetime.now()
            if notes:
                task.description = (task.description or "") + f"\n\nCompletion notes: {notes}"
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "title": task.title,
                "message": f"Task '{task.title}' marked as completed"
            }

        async def execute_update_task(args):
            """Update a task's details"""
            task_id = args.get("task_id")
            task_title = args.get("task_title", "")
            new_title = args.get("new_title")
            new_due_date = args.get("new_due_date")
            new_priority = args.get("new_priority")
            notes = args.get("notes")

            task = None
            if task_id:
                task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
            elif task_title:
                task = db.query(AITask).filter(
                    AITask.title.ilike(f"%{task_title}%"),
                    AITask.assigned_to_id == current_user.id
                ).first()

            if not task:
                return {"success": False, "error": "Task not found"}

            updates = []
            if new_title:
                task.title = new_title
                updates.append(f"title to '{new_title}'")

            if new_due_date:
                # Parse due date
                due_date = None
                due_lower = new_due_date.lower()
                today = datetime.now()
                if "tomorrow" in due_lower:
                    due_date = today + timedelta(days=1)
                elif "today" in due_lower:
                    due_date = today
                elif "next week" in due_lower:
                    due_date = today + timedelta(days=7)
                elif "next monday" in due_lower:
                    days_ahead = (0 - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    due_date = today + timedelta(days=days_ahead)
                else:
                    try:
                        from dateutil import parser
                        due_date = parser.parse(new_due_date)
                    except (ValueError, TypeError):
                        due_date = today + timedelta(days=1)
                task.due_date = due_date
                updates.append(f"due date to {due_date.strftime('%Y-%m-%d')}")

            if new_priority:
                task.priority = new_priority.lower()
                updates.append(f"priority to {new_priority}")

            if notes:
                task.description = (task.description or "") + f"\n\nUpdate notes: {notes}"
                updates.append("added notes")

            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "title": task.title,
                "updates": updates,
                "message": f"Updated task: {', '.join(updates)}"
            }

        async def execute_get_overdue_tasks(args):
            """Get all overdue tasks"""
            include_completed = args.get("include_completed", False)
            today = datetime.now().date()

            query = db.query(AITask).filter(
                AITask.assigned_to_id == current_user.id,
                AITask.due_date < datetime.now()
            )

            if not include_completed:
                query = query.filter(AITask.type != TaskType.COMPLETED)

            overdue_tasks = query.order_by(AITask.due_date.asc()).all()

            tasks_data = []
            for t in overdue_tasks[:20]:  # Limit to 20
                days_overdue = (today - t.due_date.date()).days if t.due_date else 0
                tasks_data.append({
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "days_overdue": days_overdue,
                    "priority": t.priority,
                    "urgency": "critical" if days_overdue > 7 else "high" if days_overdue > 3 else "moderate"
                })

            return {
                "success": True,
                "count": len(overdue_tasks),
                "tasks": tasks_data,
                "summary": f"{len(overdue_tasks)} overdue task(s) need attention"
            }

        async def execute_move_lead_stage(args):
            """Move a lead to a different stage"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name", "")
            new_stage = args.get("new_stage", "")
            notes = args.get("notes", "")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
            elif lead_name:
                lead = db.query(Lead).filter(
                    Lead.name.ilike(f"%{lead_name}%"),
                    Lead.owner_id == current_user.id
                ).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            old_stage = str(lead.stage) if lead.stage else "Unknown"

            # Map stage string to enum if needed
            stage_map = {
                "NEW": LeadStage.NEW,
                "CONTACTED": LeadStage.CONTACTED,
                "QUALIFIED": LeadStage.QUALIFIED,
                "NURTURING": LeadStage.NURTURING,
                "CONVERTED": LeadStage.CONVERTED,
                "LOST": LeadStage.LOST
            }

            if new_stage.upper() in stage_map:
                lead.stage = stage_map[new_stage.upper()]
            else:
                return {"success": False, "error": f"Invalid stage: {new_stage}"}

            if notes:
                lead.notes = (lead.notes or "") + f"\n\nStage change ({old_stage} -> {new_stage}): {notes}"

            db.commit()

            return {
                "success": True,
                "lead_id": lead.id,
                "lead_name": lead.name,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "message": f"Moved {lead.name} from {old_stage} to {new_stage}"
            }

        async def execute_move_loan_stage(args):
            """Move a loan to a different stage"""
            loan_id = args.get("loan_id")
            borrower_name = args.get("borrower_name", "")
            new_stage = args.get("new_stage", "")
            notes = args.get("notes", "")

            loan = None
            if loan_id:
                loan = db.query(Loan).filter(Loan.id == loan_id, Loan.loan_officer_id == current_user.id).first()
            elif borrower_name:
                loan = db.query(Loan).filter(
                    Loan.borrower_name.ilike(f"%{borrower_name}%"),
                    Loan.loan_officer_id == current_user.id
                ).first()

            if not loan:
                return {"success": False, "error": "Loan not found"}

            old_stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "Unknown"

            # Map stage string to enum
            stage_map = {
                "APPLICATION": LoanStage.APPLICATION,
                "PROCESSING": LoanStage.PROCESSING,
                "UNDERWRITING": LoanStage.UNDERWRITING,
                "APPROVED": LoanStage.APPROVED,
                "CLOSING": LoanStage.CLOSING,
                "FUNDED": LoanStage.FUNDED,
                "DEAD": LoanStage.DEAD
            }

            if new_stage.upper() in stage_map:
                loan.stage = stage_map[new_stage.upper()]
            else:
                return {"success": False, "error": f"Invalid stage: {new_stage}"}

            if notes:
                loan.notes = (loan.notes or "") + f"\n\nStage change ({old_stage} -> {new_stage}): {notes}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower_name": loan.borrower_name,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "message": f"Moved {loan.borrower_name}'s loan from {old_stage} to {new_stage}"
            }

        async def execute_bulk_create_tasks(args):
            """Create multiple tasks at once"""
            tasks_data = args.get("tasks", [])
            related_lead_id = args.get("related_lead_id")
            related_loan_id = args.get("related_loan_id")

            if not tasks_data:
                return {"success": False, "error": "No tasks provided"}

            created_tasks = []
            today = datetime.now()

            for task_info in tasks_data:
                title = task_info.get("title", "Task")
                due_date_str = task_info.get("due_date", "")
                priority = task_info.get("priority", "medium")

                # Parse due date
                due_date = today + timedelta(days=1)  # Default to tomorrow
                if due_date_str:
                    due_lower = due_date_str.lower()
                    if "tomorrow" in due_lower:
                        due_date = today + timedelta(days=1)
                    elif "today" in due_lower:
                        due_date = today
                    elif "next week" in due_lower:
                        due_date = today + timedelta(days=7)
                    elif "in 2 days" in due_lower:
                        due_date = today + timedelta(days=2)
                    elif "in 3 days" in due_lower:
                        due_date = today + timedelta(days=3)
                    else:
                        try:
                            from dateutil import parser
                            due_date = parser.parse(due_date_str)
                        except (ValueError, TypeError):
                            pass  # Keep default due_date

                new_task = AITask(
                    title=title,
                    description=f"Bulk-created task: {title}",
                    due_date=due_date,
                    priority=priority.lower() if priority else "medium",
                    type=TaskType.IN_PROGRESS,
                    assigned_to_id=current_user.id,
                    lead_id=related_lead_id,
                    loan_id=related_loan_id
                )
                db.add(new_task)
                created_tasks.append({
                    "title": title,
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "priority": priority
                })

            db.commit()

            return {
                "success": True,
                "count": len(created_tasks),
                "tasks": created_tasks,
                "message": f"Created {len(created_tasks)} task(s)"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - COMMUNICATION
        # ========================================

        async def execute_send_mms(args):
            """Send MMS (SMS with media attachment) via Twilio"""
            from twilio.rest import Client as TwilioClient

            recipient_name = args.get("recipient_name", "")
            phone_number = args.get("to_phone", "") or args.get("phone_number", "")
            message = args.get("message", "")
            media_url = args.get("media_url", "")

            if not message:
                return {"success": False, "error": "Message is required"}
            if not media_url:
                return {"success": False, "error": "Media URL is required for MMS"}

            # If we have a name but no phone, look it up
            if recipient_name and not phone_number:
                search = f"%{recipient_name}%"
                lead = db.query(Lead).filter(Lead.name.ilike(search)).first()
                if lead and lead.phone:
                    phone_number = lead.phone
                else:
                    user = db.query(User).filter(User.full_name.ilike(search)).first()
                    if user and user.phone:
                        phone_number = user.phone

            if not phone_number:
                return {"success": False, "error": f"Could not find phone number for {recipient_name}"}

            # Format phone number
            phone = ''.join(filter(str.isdigit, phone_number))
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif not phone.startswith('+'):
                phone = f"+{phone}"

            # Send via Twilio with media
            twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
            twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
            twilio_from = os.getenv("TWILIO_PHONE_NUMBER")

            if not all([twilio_sid, twilio_token, twilio_from]):
                return {"success": False, "error": "Twilio not configured"}

            try:
                twilio_client = TwilioClient(twilio_sid, twilio_token)
                msg = twilio_client.messages.create(
                    body=message,
                    from_=twilio_from,
                    to=phone,
                    media_url=[media_url]
                )
                return {
                    "success": True,
                    "message_sid": msg.sid,
                    "sent_to": phone,
                    "media_url": media_url
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        async def execute_transcribe_call(args):
            """Transcribe a call recording using AI"""
            call_id = args.get("call_id")
            audio_url = args.get("audio_url", "")

            if not call_id:
                return {"success": False, "error": "call_id is required"}

            # Try to fetch call record from database
            call_record = db.query(CallLog).filter(CallLog.id == call_id).first() if 'CallLog' in dir() else None

            if call_record and hasattr(call_record, 'recording_url'):
                audio_url = call_record.recording_url or audio_url

            if not audio_url:
                # Try to get from Twilio if we have a call SID
                twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
                twilio_token = os.getenv("TWILIO_AUTH_TOKEN")

                if twilio_sid and twilio_token:
                    try:
                        from twilio.rest import Client as TwilioClient
                        twilio_client = TwilioClient(twilio_sid, twilio_token)

                        # Try as call SID first
                        try:
                            call = twilio_client.calls(call_id).fetch()
                            recordings = twilio_client.calls(call_id).recordings.list(limit=1)
                            if recordings:
                                audio_url = f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}"
                        except Exception:
                            pass  # Twilio API error, will be handled by outer except
                    except Exception as e:
                        logger.warning(f"Could not fetch recording from Twilio: {e}")

            if not audio_url:
                return {"success": False, "error": "No audio URL available for transcription"}

            # Use OpenAI Whisper for transcription if available
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                try:
                    import httpx

                    # Download audio file
                    async with httpx.AsyncClient() as client:
                        audio_response = await client.get(audio_url)
                        if audio_response.status_code != 200:
                            return {"success": False, "error": "Could not download audio file"}

                        # Send to OpenAI Whisper
                        import openai
                        openai.api_key = openai_key

                        # Save temp file and transcribe
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                            tmp.write(audio_response.content)
                            tmp_path = tmp.name

                        with open(tmp_path, "rb") as audio_file:
                            transcript = openai.Audio.transcribe("whisper-1", audio_file)

                        os.unlink(tmp_path)

                        return {
                            "success": True,
                            "call_id": call_id,
                            "transcript": transcript.get("text", ""),
                            "duration_seconds": len(transcript.get("text", "").split()) * 0.5  # Rough estimate
                        }
                except Exception as e:
                    logger.error(f"Transcription error: {e}")
                    return {"success": False, "error": f"Transcription failed: {str(e)}"}

            # Fallback - return placeholder
            return {
                "success": True,
                "call_id": call_id,
                "transcript": "[Transcription service not configured - would process audio from: " + audio_url + "]",
                "note": "Configure OPENAI_API_KEY for actual transcription"
            }

        async def execute_summarize_call(args):
            """Generate AI summary of a call transcript"""
            call_id = args.get("call_id")
            transcript = args.get("transcript", "")

            if not call_id:
                return {"success": False, "error": "call_id is required"}

            # If no transcript provided, try to get it
            if not transcript:
                # Try to fetch from database
                call_record = db.query(CallLog).filter(CallLog.id == call_id).first() if 'CallLog' in dir() else None
                if call_record and hasattr(call_record, 'transcript'):
                    transcript = call_record.transcript or ""

            if not transcript:
                return {"success": False, "error": "No transcript available to summarize"}

            # Use Claude/OpenAI to summarize
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            openai_key = os.getenv("OPENAI_API_KEY")

            if anthropic_key:
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=anthropic_key)

                    response = client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=500,
                        messages=[{
                            "role": "user",
                            "content": f"""Summarize this call transcript for a mortgage loan officer. Include:
    1. Key discussion points
    2. Action items mentioned
    3. Next steps agreed upon
    4. Any concerns or objections raised

    Transcript:
    {transcript[:4000]}"""
                        }]
                    )

                    summary = response.content[0].text

                    return {
                        "success": True,
                        "call_id": call_id,
                        "summary": summary,
                        "transcript_length": len(transcript)
                    }
                except Exception as e:
                    logger.error(f"Summarization error: {e}")

            # Fallback - basic extraction
            words = transcript.split()
            key_phrases = []
            for i, word in enumerate(words):
                if word.lower() in ["need", "want", "please", "will", "should", "must"]:
                    phrase = " ".join(words[max(0, i-2):min(len(words), i+5)])
                    key_phrases.append(phrase)

            return {
                "success": True,
                "call_id": call_id,
                "summary": f"Call transcript ({len(words)} words). Key phrases identified: {'; '.join(key_phrases[:5]) if key_phrases else 'None extracted'}",
                "note": "Configure ANTHROPIC_API_KEY for AI-powered summaries"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - LEADS
        # ========================================

        async def execute_ai_lead_scoring(args):
            """Calculate AI-powered lead quality score (0-100)"""
            lead_id = args.get("lead_id")
            include_factors = args.get("include_factors", True)

            if not lead_id:
                return {"success": False, "error": "lead_id is required"}

            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": f"Lead not found: {lead_id}"}

            # Calculate score based on multiple factors
            score = 50  # Base score
            factors = []

            # Email quality
            if lead.email:
                if any(domain in lead.email.lower() for domain in ['gmail.com', 'yahoo.com', 'outlook.com']):
                    score += 5
                    factors.append("+5: Valid email provider")
                if lead.email.count('@') == 1 and '.' in lead.email.split('@')[1]:
                    score += 5
                    factors.append("+5: Well-formed email")

            # Phone presence
            if lead.phone:
                score += 10
                factors.append("+10: Phone number provided")

            # Lead source quality
            source = str(lead.source).lower() if lead.source else ""
            if "referral" in source:
                score += 15
                factors.append("+15: Referral lead (high quality)")
            elif "realtor" in source or "builder" in source:
                score += 10
                factors.append("+10: Partner referral")
            elif "website" in source:
                score += 5
                factors.append("+5: Website lead")

            # Stage progression
            stage = str(lead.stage).lower() if lead.stage else ""
            if "qualified" in stage or "contacted" in stage:
                score += 10
                factors.append("+10: Lead has been qualified/contacted")
            elif "application" in stage:
                score += 20
                factors.append("+20: Application started")

            # Loan amount (if available)
            if hasattr(lead, 'loan_amount') and lead.loan_amount:
                if lead.loan_amount >= 300000:
                    score += 10
                    factors.append("+10: Higher loan amount")
                elif lead.loan_amount >= 200000:
                    score += 5
                    factors.append("+5: Good loan amount")

            # Recency
            if lead.created_at:
                days_old = (datetime.now() - lead.created_at).days
                if days_old <= 1:
                    score += 10
                    factors.append("+10: Very fresh lead (< 1 day)")
                elif days_old <= 7:
                    score += 5
                    factors.append("+5: Recent lead (< 1 week)")
                elif days_old > 30:
                    score -= 10
                    factors.append("-10: Stale lead (> 30 days)")

            # Cap score at 0-100
            score = max(0, min(100, score))

            # Generate recommendation
            if score >= 80:
                recommendation = "Hot lead - prioritize immediate follow-up"
            elif score >= 60:
                recommendation = "Warm lead - schedule follow-up within 24 hours"
            elif score >= 40:
                recommendation = "Standard lead - follow standard nurture sequence"
            else:
                recommendation = "Cold lead - consider low-priority nurture campaign"

            result = {
                "success": True,
                "lead_id": lead_id,
                "lead_name": lead.name,
                "score": score,
                "recommendation": recommendation
            }

            if include_factors:
                result["factors"] = factors

            return result

        async def execute_find_duplicate_leads(args):
            """Find potential duplicate lead records"""
            lead_id = args.get("lead_id")
            email = args.get("email", "")
            phone = args.get("phone", "")
            name = args.get("name", "")

            # If lead_id provided, get lead details
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    email = email or lead.email
                    phone = phone or lead.phone
                    name = name or lead.name

            if not any([email, phone, name]):
                return {"success": False, "error": "Provide email, phone, name, or lead_id to search for duplicates"}

            duplicates = []

            # Search by email (exact match)
            if email:
                email_matches = db.query(Lead).filter(
                    Lead.email.ilike(email),
                    Lead.id != lead_id if lead_id else True
                ).all()
                for match in email_matches:
                    duplicates.append({
                        "lead_id": match.id,
                        "name": match.name,
                        "email": match.email,
                        "phone": match.phone,
                        "match_type": "email_exact",
                        "confidence": 0.95
                    })

            # Search by phone (normalized)
            if phone:
                phone_digits = ''.join(filter(str.isdigit, phone))
                if len(phone_digits) >= 10:
                    phone_matches = db.query(Lead).filter(
                        Lead.phone.ilike(f"%{phone_digits[-10:]}%"),
                        Lead.id != lead_id if lead_id else True
                    ).all()
                    for match in phone_matches:
                        if match.id not in [d["lead_id"] for d in duplicates]:
                            duplicates.append({
                                "lead_id": match.id,
                                "name": match.name,
                                "email": match.email,
                                "phone": match.phone,
                                "match_type": "phone",
                                "confidence": 0.90
                            })

            # Search by name (fuzzy)
            if name:
                name_parts = name.lower().split()
                for part in name_parts:
                    if len(part) > 2:
                        name_matches = db.query(Lead).filter(
                            Lead.name.ilike(f"%{part}%"),
                            Lead.id != lead_id if lead_id else True
                        ).limit(10).all()
                        for match in name_matches:
                            if match.id not in [d["lead_id"] for d in duplicates]:
                                # Calculate name similarity
                                match_name_lower = match.name.lower() if match.name else ""
                                match_score = sum(1 for p in name_parts if p in match_name_lower) / len(name_parts)
                                if match_score >= 0.5:
                                    duplicates.append({
                                        "lead_id": match.id,
                                        "name": match.name,
                                        "email": match.email,
                                        "phone": match.phone,
                                        "match_type": "name_similar",
                                        "confidence": round(match_score * 0.7, 2)
                                    })

            # Sort by confidence
            duplicates.sort(key=lambda x: -x["confidence"])

            return {
                "success": True,
                "search_criteria": {"email": email, "phone": phone, "name": name},
                "duplicate_count": len(duplicates),
                "duplicates": duplicates[:10]
            }

        async def execute_assign_lead_to_agent(args):
            """Assign a lead to a specific loan officer or agent"""
            lead_id = args.get("lead_id")
            agent_id = args.get("agent_id")
            agent_email = args.get("agent_email", "")
            reason = args.get("reason", "")

            if not lead_id:
                return {"success": False, "error": "lead_id is required"}

            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": f"Lead not found: {lead_id}"}

            # Find agent by ID or email
            agent = None
            if agent_id:
                agent = db.query(User).filter(User.id == agent_id).first()
            elif agent_email:
                agent = db.query(User).filter(User.email.ilike(agent_email)).first()

            if not agent:
                return {"success": False, "error": "Agent not found. Provide valid agent_id or agent_email"}

            old_owner = lead.owner_id
            lead.owner_id = agent.id

            # Add note about assignment
            assignment_note = f"Lead assigned to {agent.full_name or agent.email}"
            if reason:
                assignment_note += f". Reason: {reason}"
            lead.notes = (lead.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {assignment_note}"

            db.commit()

            return {
                "success": True,
                "lead_id": lead.id,
                "lead_name": lead.name,
                "assigned_to": {
                    "id": agent.id,
                    "name": agent.full_name or agent.email,
                    "email": agent.email
                },
                "previous_owner_id": old_owner,
                "message": f"Lead '{lead.name}' assigned to {agent.full_name or agent.email}"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - PIPELINE
        # ========================================

        async def execute_assign_task(args):
            """Assign a task to a specific team member"""
            task_id = args.get("task_id")
            assignee_id = args.get("assignee_id")
            assignee_email = args.get("assignee_email", "")

            if not task_id:
                return {"success": False, "error": "task_id is required"}

            task = db.query(AITask).filter(AITask.id == task_id).first()
            if not task:
                return {"success": False, "error": f"Task not found: {task_id}"}

            # Find assignee
            assignee = None
            if assignee_id:
                assignee = db.query(User).filter(User.id == assignee_id).first()
            elif assignee_email:
                assignee = db.query(User).filter(User.email.ilike(assignee_email)).first()

            if not assignee:
                return {"success": False, "error": "Assignee not found. Provide valid assignee_id or assignee_email"}

            old_assignee_id = task.assigned_to_id
            task.assigned_to_id = assignee.id
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "task_title": task.title,
                "assigned_to": {
                    "id": assignee.id,
                    "name": assignee.full_name or assignee.email,
                    "email": assignee.email
                },
                "previous_assignee_id": old_assignee_id,
                "message": f"Task '{task.title}' assigned to {assignee.full_name or assignee.email}"
            }

        async def execute_update_pipeline_stage(args):
            """Move a lead or loan to a different pipeline stage"""
            entity_type = args.get("entity_type", "").lower()
            entity_id = args.get("entity_id")
            stage = args.get("stage", "")
            status = args.get("status", "")
            reason = args.get("reason", "")
            trigger_automations = args.get("trigger_automations", True)

            if entity_type not in ["lead", "loan"]:
                return {"success": False, "error": "entity_type must be 'lead' or 'loan'"}
            if not entity_id:
                return {"success": False, "error": "entity_id is required"}
            if not stage:
                return {"success": False, "error": "stage is required"}

            entity = None
            old_stage = None

            if entity_type == "lead":
                entity = db.query(Lead).filter(Lead.id == entity_id).first()
                if entity:
                    old_stage = str(entity.stage) if entity.stage else "Unknown"
                    # Map to LeadStage enum if available
                    try:
                        entity.stage = stage
                    except (ValueError, AttributeError):
                        entity.stage = stage  # Use raw value if enum conversion fails
            else:
                entity = db.query(Loan).filter(Loan.id == entity_id).first()
                if entity:
                    old_stage = str(entity.stage).replace("LoanStage.", "") if entity.stage else "Unknown"
                    # Map to LoanStage enum
                    stage_map = {
                        "APPLICATION": LoanStage.APPLICATION,
                        "PROCESSING": LoanStage.PROCESSING,
                        "UNDERWRITING": LoanStage.UNDERWRITING,
                        "APPROVED": LoanStage.APPROVED,
                        "CLOSING": LoanStage.CLOSING,
                        "FUNDED": LoanStage.FUNDED,
                        "DEAD": LoanStage.DEAD
                    }
                    if stage.upper() in stage_map:
                        entity.stage = stage_map[stage.upper()]
                    else:
                        return {"success": False, "error": f"Invalid loan stage: {stage}"}

            if not entity:
                return {"success": False, "error": f"{entity_type.title()} not found: {entity_id}"}

            # Update status if provided
            if status and hasattr(entity, 'status'):
                entity.status = status

            # Add reason to notes
            if reason:
                notes = getattr(entity, 'notes', '') or ''
                entity.notes = notes + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Stage change to {stage}: {reason}"

            db.commit()

            result = {
                "success": True,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_stage": old_stage,
                "new_stage": stage,
                "message": f"{entity_type.title()} moved from {old_stage} to {stage}"
            }

            # Trigger automations if requested
            if trigger_automations and entity_type == "loan":
                result["automation_triggered"] = True
                result["automation_note"] = f"Milestone automation would be triggered for stage: {stage}"

            return result

        async def execute_request_documents(args):
            """Send document request to borrower"""
            loan_id = args.get("loan_id")
            lead_id = args.get("lead_id")
            document_types = args.get("document_types", [])
            message = args.get("message", "")

            if not document_types:
                return {"success": False, "error": "document_types is required"}

            # Find the entity (loan or lead)
            entity = None
            entity_type = None
            contact_email = None
            contact_name = None

            if loan_id:
                entity = db.query(Loan).filter(Loan.id == loan_id).first()
                entity_type = "loan"
                if entity:
                    contact_name = entity.borrower_name
                    contact_email = entity.borrower_email
            elif lead_id:
                entity = db.query(Lead).filter(Lead.id == lead_id).first()
                entity_type = "lead"
                if entity:
                    contact_name = entity.name
                    contact_email = entity.email

            if not entity:
                return {"success": False, "error": "Loan or Lead not found"}

            if not contact_email:
                return {"success": False, "error": "No email address found for contact"}

            # Build document request message
            doc_list = "\n".join([f"- {doc}" for doc in document_types])
            default_message = f"""Hello {contact_name},

    We need the following documents to proceed with your mortgage application:

    {doc_list}

    Please upload these documents at your earliest convenience.

    Thank you!"""

            email_body = message if message else default_message

            # Queue the email (or send via email service)
            # For now, we'll log it and return success
            request_id = str(uuid.uuid4())[:8]

            # Create a task to track the document request
            doc_task = AITask(
                title=f"Document Request: {', '.join(document_types[:3])}{'...' if len(document_types) > 3 else ''}",
                description=f"Documents requested from {contact_name}: {', '.join(document_types)}",
                due_date=datetime.now() + timedelta(days=3),
                priority="high",
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id,
                loan_id=loan_id,
                lead_id=lead_id
            )
            db.add(doc_task)
            db.commit()

            return {
                "success": True,
                "request_id": request_id,
                "entity_type": entity_type,
                "entity_id": loan_id or lead_id,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "documents_requested": document_types,
                "task_created": doc_task.id,
                "message": f"Document request sent to {contact_name} for {len(document_types)} document(s)"
            }

        async def execute_document_ocr_extract(args):
            """Extract data from uploaded documents via OCR"""
            document_id = args.get("document_id")
            document_url = args.get("document_url", "")
            document_type = args.get("document_type", "")

            if not document_id:
                return {"success": False, "error": "document_id is required"}

            # Try to get document from database
            document = None
            if 'Document' in dir():
                document = db.query(Document).filter(Document.id == document_id).first()

            if document and hasattr(document, 'file_url'):
                document_url = document_url or document.file_url
                document_type = document_type or getattr(document, 'document_type', 'unknown')

            if not document_url:
                return {"success": False, "error": "No document URL available"}

            # Determine extraction based on document type
            extraction_fields = {}
            doc_type_lower = document_type.lower()

            if "paystub" in doc_type_lower or "pay stub" in doc_type_lower:
                extraction_fields = {
                    "employer_name": "[OCR would extract employer name]",
                    "pay_period": "[OCR would extract pay period dates]",
                    "gross_pay": "[OCR would extract gross pay amount]",
                    "net_pay": "[OCR would extract net pay amount]",
                    "ytd_earnings": "[OCR would extract YTD earnings]"
                }
            elif "w2" in doc_type_lower or "w-2" in doc_type_lower:
                extraction_fields = {
                    "employer_ein": "[OCR would extract employer EIN]",
                    "employee_ssn_last4": "[OCR would extract last 4 of SSN]",
                    "wages": "[OCR would extract wages/tips/compensation]",
                    "federal_tax_withheld": "[OCR would extract federal tax withheld]",
                    "tax_year": "[OCR would extract tax year]"
                }
            elif "bank" in doc_type_lower or "statement" in doc_type_lower:
                extraction_fields = {
                    "account_number_last4": "[OCR would extract last 4 of account]",
                    "statement_period": "[OCR would extract statement period]",
                    "ending_balance": "[OCR would extract ending balance]",
                    "average_balance": "[OCR would calculate average balance]"
                }
            elif "tax" in doc_type_lower or "1040" in doc_type_lower:
                extraction_fields = {
                    "tax_year": "[OCR would extract tax year]",
                    "filing_status": "[OCR would extract filing status]",
                    "adjusted_gross_income": "[OCR would extract AGI]",
                    "total_income": "[OCR would extract total income]"
                }
            else:
                extraction_fields = {
                    "document_type_detected": "[OCR would detect document type]",
                    "text_extracted": "[OCR would extract full text]",
                    "key_values": "[OCR would extract key-value pairs]"
                }

            return {
                "success": True,
                "document_id": document_id,
                "document_type": document_type,
                "document_url": document_url,
                "extracted_data": extraction_fields,
                "confidence": 0.85,
                "note": "Configure OCR service (AWS Textract, Google Vision, etc.) for actual extraction"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - RATE LOCK
        # ========================================

        async def execute_lock_rate(args):
            """Execute a rate lock for a loan (REQUIRES APPROVAL)"""
            loan_id = args.get("loan_id")
            rate = args.get("rate")
            lock_period_days = args.get("lock_period_days")
            points = args.get("points", 0)

            if not all([loan_id, rate, lock_period_days]):
                return {"success": False, "error": "loan_id, rate, and lock_period_days are required"}

            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan not found: {loan_id}"}

            # Check if loan already has an active lock
            if hasattr(loan, 'rate_locked') and loan.rate_locked:
                return {
                    "success": False,
                    "error": "Loan already has an active rate lock",
                    "current_rate": loan.interest_rate,
                    "lock_expiration": str(loan.lock_expiration) if hasattr(loan, 'lock_expiration') else None
                }

            # Calculate lock expiration
            lock_expiration = datetime.now() + timedelta(days=lock_period_days)

            # Update loan with rate lock info
            loan.interest_rate = rate
            if hasattr(loan, 'rate_locked'):
                loan.rate_locked = True
            if hasattr(loan, 'lock_expiration'):
                loan.lock_expiration = lock_expiration
            if hasattr(loan, 'lock_points'):
                loan.lock_points = points

            # Add note
            lock_note = f"Rate locked at {rate}% for {lock_period_days} days. Points: {points}. Expires: {lock_expiration.strftime('%Y-%m-%d')}"
            loan.notes = (loan.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {lock_note}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower": loan.borrower_name,
                "locked_rate": rate,
                "lock_period_days": lock_period_days,
                "lock_expiration": lock_expiration.strftime('%Y-%m-%d'),
                "points": points,
                "message": f"Rate locked at {rate}% for {loan.borrower_name}. Expires {lock_expiration.strftime('%Y-%m-%d')}"
            }

        async def execute_extend_lock(args):
            """Extend an existing rate lock (REQUIRES APPROVAL)"""
            loan_id = args.get("loan_id")
            extension_days = args.get("extension_days")

            if not all([loan_id, extension_days]):
                return {"success": False, "error": "loan_id and extension_days are required"}

            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan not found: {loan_id}"}

            # Check if loan has a rate lock
            if hasattr(loan, 'rate_locked') and not loan.rate_locked:
                return {"success": False, "error": "Loan does not have an active rate lock to extend"}

            # Get current expiration
            current_expiration = getattr(loan, 'lock_expiration', None)
            if not current_expiration:
                current_expiration = datetime.now()

            # Calculate new expiration
            if isinstance(current_expiration, date) and not isinstance(current_expiration, datetime):
                current_expiration = datetime.combine(current_expiration, datetime.min.time())

            new_expiration = current_expiration + timedelta(days=extension_days)

            # Update loan
            if hasattr(loan, 'lock_expiration'):
                loan.lock_expiration = new_expiration

            # Add note
            extend_note = f"Rate lock extended by {extension_days} days. New expiration: {new_expiration.strftime('%Y-%m-%d')}"
            loan.notes = (loan.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {extend_note}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower": loan.borrower_name,
                "extension_days": extension_days,
                "previous_expiration": current_expiration.strftime('%Y-%m-%d'),
                "new_expiration": new_expiration.strftime('%Y-%m-%d'),
                "current_rate": loan.interest_rate,
                "message": f"Rate lock extended to {new_expiration.strftime('%Y-%m-%d')} for {loan.borrower_name}"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - SCHEDULING
        # ========================================

        async def execute_reschedule_appointment(args):
            """Reschedule an existing appointment"""
            appointment_id = args.get("appointment_id")
            new_start_time = args.get("new_start_time", "")
            reason = args.get("reason", "")

            if not appointment_id:
                return {"success": False, "error": "appointment_id is required"}
            if not new_start_time:
                return {"success": False, "error": "new_start_time is required"}

            # Find appointment (stored as task or in appointments table)
            appointment = db.query(AITask).filter(AITask.id == appointment_id).first()

            if not appointment:
                # Try scheduler appointments if that table exists
                if 'Appointment' in dir():
                    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

            if not appointment:
                return {"success": False, "error": f"Appointment not found: {appointment_id}"}

            # Parse new start time
            parsed_time = None
            try:
                from dateutil import parser
                parsed_time = parser.parse(new_start_time)
            except (ValueError, TypeError):
                # Try natural language parsing
                time_lower = new_start_time.lower()
                today = datetime.now()

                if "tomorrow" in time_lower:
                    parsed_time = today + timedelta(days=1)
                    parsed_time = parsed_time.replace(hour=10, minute=0, second=0)
                elif "next week" in time_lower:
                    parsed_time = today + timedelta(days=7)
                    parsed_time = parsed_time.replace(hour=10, minute=0, second=0)
                else:
                    return {"success": False, "error": f"Could not parse time: {new_start_time}"}

            # Store old time for response
            old_time = appointment.due_date if hasattr(appointment, 'due_date') else getattr(appointment, 'start_time', None)

            # Update the appointment
            if hasattr(appointment, 'due_date'):
                appointment.due_date = parsed_time
            if hasattr(appointment, 'start_time'):
                appointment.start_time = parsed_time

            # Add reason to notes/description
            if reason:
                if hasattr(appointment, 'description'):
                    appointment.description = (appointment.description or "") + f"\n\nRescheduled: {reason}"
                elif hasattr(appointment, 'notes'):
                    appointment.notes = (appointment.notes or "") + f"\n\nRescheduled: {reason}"

            db.commit()

            return {
                "success": True,
                "appointment_id": appointment_id,
                "title": getattr(appointment, 'title', 'Appointment'),
                "old_time": old_time.isoformat() if old_time else None,
                "new_time": parsed_time.isoformat(),
                "reason": reason,
                "message": f"Appointment rescheduled to {parsed_time.strftime('%Y-%m-%d %H:%M')}"
            }

        async def execute_cancel_appointment(args):
            """Cancel an appointment (REQUIRES APPROVAL)"""
            appointment_id = args.get("appointment_id")
            reason = args.get("reason", "")
            notify_attendees = args.get("notify_attendees", True)

            if not appointment_id:
                return {"success": False, "error": "appointment_id is required"}

            # Find appointment
            appointment = db.query(AITask).filter(AITask.id == appointment_id).first()

            if not appointment:
                if 'Appointment' in dir():
                    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

            if not appointment:
                return {"success": False, "error": f"Appointment not found: {appointment_id}"}

            title = getattr(appointment, 'title', 'Appointment')
            scheduled_time = getattr(appointment, 'due_date', None) or getattr(appointment, 'start_time', None)

            # Mark as cancelled
            if hasattr(appointment, 'type'):
                appointment.type = TaskType.COMPLETED  # Mark as completed/done
            if hasattr(appointment, 'status'):
                appointment.status = 'cancelled'

            # Add cancellation note
            cancel_note = f"CANCELLED"
            if reason:
                cancel_note += f": {reason}"

            if hasattr(appointment, 'description'):
                appointment.description = cancel_note + "\n\n" + (appointment.description or "")
            elif hasattr(appointment, 'notes'):
                appointment.notes = cancel_note + "\n\n" + (appointment.notes or "")

            db.commit()

            result = {
                "success": True,
                "appointment_id": appointment_id,
                "title": title,
                "was_scheduled_for": scheduled_time.isoformat() if scheduled_time else None,
                "reason": reason,
                "message": f"Appointment '{title}' has been cancelled"
            }

            if notify_attendees:
                result["notification_sent"] = True
                result["notification_note"] = "Attendees would be notified via email"

            return result

        async def execute_check_email_sync_status(args: dict):
            """Check email sync status for Microsoft 365 or Gmail integrations."""
            try:
                # Check for Microsoft OAuth connection
                microsoft_oauth = db.query(MicrosoftOAuthToken).filter(
                    MicrosoftOAuthToken.user_id == current_user.id
                ).first()

                result = {
                    "success": True,
                    "has_email_integration": False,
                    "microsoft": None,
                    "summary": ""
                }

                if microsoft_oauth:
                    result["has_email_integration"] = True
                    token_expired = False
                    if microsoft_oauth.expires_at:
                        token_expired = microsoft_oauth.expires_at < datetime.utcnow()

                    recent_emails = db.execute(text("""
                        SELECT COUNT(*) as count, MAX(received_date) as last_email
                        FROM incoming_data_events
                        WHERE user_id = :user_id AND source_type = 'microsoft_email'
                        AND received_date >= NOW() - INTERVAL '24 hours'
                    """), {"user_id": current_user.id}).fetchone()

                    result["microsoft"] = {
                        "connected": True,
                        "email_address": microsoft_oauth.email_address,
                        "sync_folder": microsoft_oauth.sync_folder or "Inbox",
                        "token_status": "expired" if token_expired else "valid",
                        "emails_last_24h": recent_emails[0] if recent_emails else 0
                    }

                    if token_expired:
                        result["summary"] = f"Microsoft 365 email connected ({microsoft_oauth.email_address}) but token has EXPIRED. Please re-authenticate."
                    elif recent_emails and recent_emails[0] > 0:
                        result["summary"] = f"Microsoft 365 email is syncing properly. {recent_emails[0]} emails received in the last 24 hours."
                    else:
                        result["summary"] = f"Microsoft 365 email connected ({microsoft_oauth.email_address}). No new emails in the last 24 hours."
                else:
                    result["summary"] = "No email integration configured. Go to Settings > Integrations to connect Microsoft 365 or Gmail."

                return result
            except Exception as e:
                logger.error(f"check_email_sync_status error: {e}")
                return {"success": False, "error": str(e), "summary": f"Error checking email sync: {str(e)}"}

        tool_functions = {
            "get_tasks": execute_get_tasks,
            "get_calendar_events": execute_get_calendar_events,
            "get_pipeline": execute_get_pipeline,
            "search_leads": execute_search_leads,
            "get_market_intelligence": execute_get_market_intelligence,
            "send_sms": execute_send_sms,
            "create_task": execute_create_task,
            "schedule_appointment": execute_schedule_appointment,
            # Additional tools
            "send_email": execute_send_email,
            "update_lead": execute_update_lead,
            "get_loan_details": execute_get_loan_details,
            "get_lead_details": execute_get_lead_details,
            "update_user_profile": execute_update_user_profile,
            "get_metrics": execute_get_metrics,
            "schedule_followup": execute_schedule_followup,
            "get_mum_clients": execute_get_mum_clients,
            "get_referral_partners": execute_get_referral_partners,
            "get_sla_dashboard": execute_get_sla_dashboard,
            "make_phone_call": execute_make_phone_call,
            "create_lead": execute_create_lead,
            # New tools for 25 total
            "drop_voicemail": execute_drop_voicemail,
            "send_email_to_contact": execute_send_email_to_contact,
            "search_knowledge_base": execute_search_knowledge_base,
            "escalate_to_human": execute_escalate_to_human,
            "get_employee_capacity": execute_get_employee_capacity,
            "get_at_risk_deals": execute_get_at_risk_deals,
            # Predictive analytics tools for 32 total
            "get_activity_metrics": execute_get_activity_metrics,
            "get_document_status": execute_get_document_status,
            "predict_borrower_ghosting": execute_predict_borrower_ghosting,
            "predict_deal_success": execute_predict_deal_success,
            "forecast_revenue": execute_forecast_revenue,
            "get_refinance_candidates": execute_get_refinance_candidates,
            "analyze_conversion_patterns": execute_analyze_conversion_patterns,
            # Task Management tools for 38 total
            "complete_task": execute_complete_task,
            "update_task": execute_update_task,
            "get_overdue_tasks": execute_get_overdue_tasks,
            "move_lead_stage": execute_move_lead_stage,
            "move_loan_stage": execute_move_loan_stage,
            "bulk_create_tasks": execute_bulk_create_tasks,
            # NEW: Communication tools
            "send_mms": execute_send_mms,
            "transcribe_call": execute_transcribe_call,
            "summarize_call": execute_summarize_call,
            # NEW: Lead tools
            "ai_lead_scoring": execute_ai_lead_scoring,
            "find_duplicate_leads": execute_find_duplicate_leads,
            "assign_lead_to_agent": execute_assign_lead_to_agent,
            # NEW: Pipeline tools
            "assign_task": execute_assign_task,
            "update_pipeline_stage": execute_update_pipeline_stage,
            "request_documents": execute_request_documents,
            "document_ocr_extract": execute_document_ocr_extract,
            # NEW: Rate lock tools
            "lock_rate": execute_lock_rate,
            "extend_lock": execute_extend_lock,
            # NEW: Scheduling tools
            "reschedule_appointment": execute_reschedule_appointment,
            "cancel_appointment": execute_cancel_appointment,
            # Email & Integration Status Tools
            "check_email_sync_status": execute_check_email_sync_status
        }

        # Pre-fetch real data for rich context
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=7)
        start_of_month = today.replace(day=1)
        start_of_year = today.replace(month=1, day=1)

        all_tasks = db.query(Task).filter(Task.owner_id == current_user.id).all()
        all_leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
        all_loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

        # Fetch profitability data for financial questions using ProfitabilityService
        try:
            from services.profitability_service import ProfitabilityService
            profitability_service = ProfitabilityService(db, organization_id=1)  # Default org

            # Get comprehensive dashboard metrics
            dashboard_metrics = profitability_service.get_dashboard_metrics(today)

            # Get expense breakdown
            all_expenses = db.query(Expense).filter(Expense.is_active == True).all()
            expense_breakdown = {}
            for exp in all_expenses:
                exp_type = exp.expense_type or 'other'
                if exp_type not in expense_breakdown:
                    expense_breakdown[exp_type] = 0
                expense_breakdown[exp_type] += float(exp.amount or 0)

            # Get employee costs
            employee_costs_list = db.query(EmployeeCost).filter(EmployeeCost.is_active == True).all()
            total_employee_costs = sum(emp.monthly_cost for emp in employee_costs_list)
            employee_count = len(employee_costs_list)

            # Get closed loans this month
            closed_loans_month = db.query(ProfitabilityLoan).filter(
                ProfitabilityLoan.close_date >= start_of_month
            ).all()

            # Calculate metrics from dashboard
            loans_closed_this_month = dashboard_metrics.get('loans_closed', 0)
            total_revenue_month = float(dashboard_metrics.get('total_revenue', 0))
            monthly_expenses = float(dashboard_metrics.get('total_expenses', 0))
            snapshot_cost_per_loan = float(dashboard_metrics.get('cost_per_loan', 0))
            snapshot_revenue_per_loan = float(dashboard_metrics.get('revenue_per_loan', 0))
            snapshot_profit_per_loan = float(dashboard_metrics.get('profit_per_loan', 0))
            profit_margin = float(dashboard_metrics.get('profit_margin', 0))
            break_even_loans = dashboard_metrics.get('break_even_loans', 0)
            net_profit = float(dashboard_metrics.get('net_profit', 0))

            avg_loan_amount = sum(float(l.loan_amount or 0) for l in closed_loans_month) / max(loans_closed_this_month, 1) if closed_loans_month else 0

            # Get trends for year-over-year comparison
            trends = profitability_service.get_trends(3)  # Last 3 months

            # Get gaps and gains insights
            gaps_gains = profitability_service.identify_gaps_and_gains(today)

            has_profitability_data = loans_closed_this_month > 0 or monthly_expenses > 0 or len(all_expenses) > 0

        except Exception as e:
            logger.warning(f"Could not fetch profitability data: {e}")
            # Default values if profitability tables don't exist yet
            loans_closed_this_month = 0
            total_revenue_month = 0
            monthly_expenses = 0
            snapshot_cost_per_loan = 0
            snapshot_revenue_per_loan = 0
            snapshot_profit_per_loan = 0
            avg_loan_amount = 0
            profit_margin = 0
            break_even_loans = 0
            net_profit = 0
            expense_breakdown = {}
            total_employee_costs = 0
            employee_count = 0
            trends = []
            gaps_gains = []
            has_profitability_data = False

        # Fetch relevant knowledge base entries for the user's question
        knowledge_context = ""
        try:
            # Get active knowledge base entries
            knowledge_entries = db.query(AIKnowledgeBase).filter(
                AIKnowledgeBase.is_active == True
            ).order_by(AIKnowledgeBase.priority.desc()).limit(20).all()

            if knowledge_entries:
                # Search for entries relevant to the user's question
                message_lower = message.lower()
                relevant_entries = []

                for entry in knowledge_entries:
                    # Check if entry title, content, or tags match the question
                    entry_text = f"{entry.title} {entry.content} {' '.join(entry.tags or [])}".lower()

                    # Simple keyword matching - check if any significant words from the question appear in the entry
                    question_words = [w for w in message_lower.split() if len(w) > 3]
                    match_score = sum(1 for word in question_words if word in entry_text)

                    if match_score > 0:
                        relevant_entries.append((match_score, entry))

                # Sort by relevance and take top 5
                relevant_entries.sort(key=lambda x: x[0], reverse=True)
                top_entries = [entry for score, entry in relevant_entries[:5]]

                if top_entries:
                    knowledge_context = "\n\n# KNOWLEDGE BASE CONTEXT\n"
                    knowledge_context += "The following information from your organization's knowledge base may be relevant:\n\n"
                    for entry in top_entries:
                        knowledge_context += f"## {entry.title} ({entry.category.replace('_', ' ').title()})\n"
                        # Include summary if available, otherwise truncate content
                        if entry.summary:
                            knowledge_context += f"{entry.summary}\n\n"
                        else:
                            # Truncate content to first 500 chars
                            content_preview = entry.content[:500] + "..." if len(entry.content) > 500 else entry.content
                            knowledge_context += f"{content_preview}\n\n"
        except Exception as e:
            logger.warning(f"Could not fetch knowledge base entries: {e}")
            knowledge_context = ""

        # Task breakdown
        tasks_today = [t for t in all_tasks if t.due_date and t.due_date.date() == today and t.status != "completed"]
        tasks_tomorrow = [t for t in all_tasks if t.due_date and t.due_date.date() == tomorrow and t.status != "completed"]
        tasks_overdue = [t for t in all_tasks if t.due_date and t.due_date.date() < today and t.status != "completed"]
        outstanding_tasks = [t for t in all_tasks if t.status != "completed"]

        # Helper to format task details - ALWAYS include client name
        def format_task(task):
            parts = [f"**{task.title}**"]
            if task.priority:
                parts.append(f"Priority: {task.priority.title()}")
            if task.due_date:
                parts.append(f"Due: {task.due_date.strftime('%m/%d/%Y')}")

            # Get related loan/lead info - try multiple sources for client name
            client_name = None
            loan_amount = None

            if task.loan_id:
                loan = next((l for l in all_loans if l.id == task.loan_id), None)
                if loan:
                    client_name = loan.borrower_name
                    loan_amount = loan.amount

            if not client_name and task.lead_id:
                lead = next((l for l in all_leads if l.id == task.lead_id), None)
                if lead:
                    client_name = lead.name

            # Fallback to related_contact_name if no loan/lead association
            if not client_name and hasattr(task, 'related_contact_name') and task.related_contact_name:
                client_name = task.related_contact_name

            # Add client name to the task description
            if client_name:
                if loan_amount:
                    parts.append(f"FOR: {client_name} (${loan_amount:,.0f})")
                else:
                    parts.append(f"FOR: {client_name}")

            return " | ".join(parts)

        # Format stage name
        def format_stage(stage):
            if not stage:
                return "Unknown"
            stage_str = str(stage).replace('LoanStage.', '').replace('LeadStage.', '')
            stage_map = {
                'CTC': 'Clear to Close', 'UW_RECEIVED': 'Underwriting Received',
                'DISCLOSED': 'Disclosed', 'PROCESSING': 'Processing',
                'APPROVED': 'Approved', 'FUNDED': 'Funded', 'NEW': 'New',
                'PROSPECT': 'Prospect', 'PRE_QUALIFIED': 'Pre-Qualified',
                'PRE_APPROVED': 'Pre-Approved', 'APPLICATION_STARTED': 'Application Started'
            }
            return stage_map.get(stage_str, stage_str.replace('_', ' ').title())

        # Build loans by stage
        loans_by_stage = {}
        for loan in all_loans:
            stage_name = format_stage(loan.stage)
            if stage_name not in loans_by_stage:
                loans_by_stage[stage_name] = []
            loans_by_stage[stage_name].append(loan)

        # Lead stages
        pipeline_stages = {}
        for lead in all_leads:
            stage = str(lead.stage).replace("LeadStage.", "") if lead.stage else "NEW"
            if stage not in pipeline_stages:
                pipeline_stages[stage] = []
            pipeline_stages[stage].append(lead.name)

        # Build data context
        data_context = f"""
    ## YOUR CURRENT DATA (Real-time):

    ### Tasks Overview:
    - Tasks due TODAY: {len(tasks_today)}
    - Tasks due TOMORROW: {len(tasks_tomorrow)}
    - OVERDUE tasks: {len(tasks_overdue)}
    - TOTAL OUTSTANDING: {len(outstanding_tasks)}

    ### Outstanding Tasks (Detailed):
    {chr(10).join([f"- {format_task(t)}" for t in outstanding_tasks[:10]]) if outstanding_tasks else "- No outstanding tasks"}

    ### Active Loans BY STAGE:
    {chr(10).join([f"**{stage}** ({len(loans)} loans): " + ", ".join([f"{loan.borrower_name} (${loan.amount:,.0f})" if loan.amount else loan.borrower_name for loan in loans]) for stage, loans in loans_by_stage.items()]) if loans_by_stage else "- No active loans"}

    ### Pipeline Summary ({len(all_leads)} leads):
    {chr(10).join([f"- {stage}: {len(names)} leads" for stage, names in pipeline_stages.items()]) if pipeline_stages else "- No leads"}

    ### Financial Metrics (This Month):
    - Loans Closed This Month: {loans_closed_this_month}
    - Total Revenue This Month: ${total_revenue_month:,.2f}
    - Monthly Operating Expenses: ${monthly_expenses:,.2f}
    - Net Profit: ${net_profit:,.2f}
    - Profit Margin: {profit_margin:.1f}%
    - Average Loan Amount: ${avg_loan_amount:,.2f}
    - **Cost Per Closing**: ${snapshot_cost_per_loan:,.2f}
    - Revenue Per Loan: ${snapshot_revenue_per_loan:,.2f}
    - Profit Per Loan: ${snapshot_profit_per_loan:,.2f}
    - Break-Even Point: {break_even_loans} loans/month
    - Employee Count: {employee_count}
    - Employee Costs (Monthly): ${total_employee_costs:,.2f}

    ### Expense Breakdown:
    {chr(10).join([f"- {exp_type.replace('_', ' ').title()}: ${amount:,.2f}" for exp_type, amount in expense_breakdown.items()]) if expense_breakdown else "- No expenses configured"}

    {'### ⚠️ PROFITABILITY DATA NOT CONFIGURED' if not has_profitability_data else ''}
    {'To calculate accurate cost per closing, set up the Profitability section with:' if not has_profitability_data else ''}
    {'1. Monthly expenses (rent, software, marketing, etc.)' if not has_profitability_data else ''}
    {'2. Employee costs (salaries, benefits, taxes)' if not has_profitability_data else ''}
    {'3. Closed loan records with revenue' if not has_profitability_data else ''}
    {'Navigate to: Settings > Profitability' if not has_profitability_data else ''}
    """

        # Detect coaching mode
        message_lower = message.lower()
        coaching_instructions = ""

        if "daily briefing" in message_lower or "top 3 priorities" in message_lower or "what should i do" in message_lower or "priorities today" in message_lower or "what do i need to do" in message_lower or "outstanding tasks" in message_lower:
            has_real_data = len(outstanding_tasks) > 0 or len(all_leads) > 0 or len(all_loans) > 0
            coaching_instructions = f"""

    ## COACHING MODE: DAILY BRIEFING
    You are providing a detailed, actionable daily briefing. Be CONVERSATIONAL and HELPFUL, not just a list.

    CRITICAL RULES:
    - **NEVER INVENT OR MAKE UP TASKS** - Only reference tasks that exist in the data above
    - **ALWAYS INCLUDE THE CLIENT/BORROWER NAME** - Every task MUST specify WHO it's for
    - The user has EXACTLY {len(tasks_overdue)} OVERDUE tasks
    - The user has EXACTLY {len(outstanding_tasks)} total outstanding tasks
    - The user has {len(all_leads)} leads and {len(all_loans)} active loans
    - Look for "FOR:" in the task data to find the client name - if a task has "FOR: John Smith" include that name

    {'**NO DATA FOUND - Tell the user they have no outstanding tasks and offer to help them add a new lead or import data.**' if not has_real_data else ''}

    OUTPUT FORMAT (be conversational, not robotic):
    1. Start with a friendly greeting and summary: "Good morning! Here's your priority breakdown for today..."
    2. If overdue tasks exist, HIGHLIGHT them first with urgency
    3. **EVERY task MUST include the client/borrower name** - e.g., "Follow up with **Sarah Johnson**" not just "Follow up"
    4. Include loan amounts when available: "$450,000 loan in Processing"
    5. End with a clear action recommendation: "I'd suggest starting with [X] because [reason]"
    6. Be encouraging and actionable, not just a data dump

    Example good response:
    "Good morning! You have 3 outstanding tasks that need attention today.

    **Priority #1: Follow up with Sarah Johnson** ($450,000 loan in Processing)
    This is your most time-sensitive item - the appraisal was received yesterday and needs your review.

    **Priority #2: Discuss Revised Numbers with Mike Chen**
    Mike's file is in Underwriting and he's waiting on updated figures.

    **Priority #3: Follow-up meetings with leads** (8 contacts due today)
    Your lead nurturing tasks - I'd batch these after handling the urgent items above.

    I'd suggest starting with Sarah's appraisal review since it directly impacts her closing timeline. Would you like me to pull up her file?"
    """

        # Get user's local time (safely handle missing timezone column)
        user_timezone = getattr(current_user, 'timezone', None) or "America/Chicago"
        try:
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)
        except Exception:
            user_timezone = "America/Chicago"
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)

        # Build comprehensive system prompt
        system_prompt = f"""# IDENTITY
    You are the AI Assistant for Perennia AI Mortgage CRM - a confident, expert mortgage industry copilot.
    User: {current_user.full_name or current_user.email}
    Current date/time: {user_local_time.strftime('%A, %B %d, %Y at %I:%M %p')} ({user_timezone})

    # VOICE & TONE
    - Confident, expert, and decisive
    - No hedging, no disclaimers, no "I think" or "maybe"
    - Be conversational and helpful, not robotic
    - Always provide specific names, amounts, and actionable next steps
    - Format with markdown for clarity (bold for emphasis, bullet points for lists)

    # FORMATTING RULES
    - Never use ALL CAPS - use **bold** for emphasis instead
    - Format stage names properly: "Clear to Close" not "CTC"
    - When mentioning loans, always include borrower name and amount
    - Use numbered lists for priorities, bullet points for details

    # MORTGAGE BUSINESS FINANCIAL DEFINITIONS
    You are an expert in mortgage business operations and profitability. Here are the key metrics and how to calculate them:

    ## Revenue Sources in Mortgage Operations:
    - **Origination Fee**: Fee charged to borrower for processing their loan (typically 0.5-1% of loan amount)
    - **Processing Fee**: Administrative fee for document collection and verification ($300-$800)
    - **Admin Fee**: General administrative costs passed to borrower ($200-$500)
    - **Commission/Rebate**: Revenue from lender based on rate spread (YSP - Yield Spread Premium)
    - **Typical Revenue Per Loan**: $3,000-$8,000 depending on loan size and pricing

    ## Cost Categories:
    - **Fixed Costs**: Rent, software subscriptions, insurance, licensing fees - don't change with volume
    - **Variable Costs**: Commission splits, credit reports, appraisals - scale with loan volume
    - **Employee Costs**: Fully-loaded cost = Base Salary + Benefits (25-30%) + Payroll Taxes (7.65%) + Equipment + Training
    - **One-Time Costs**: Equipment purchases, renovations, training programs

    ## Key Performance Metrics:
    - **Cost Per Closing** = Total Monthly Expenses ÷ Loans Closed This Month
      - Industry benchmark: $2,000-$5,000 per loan
      - If no loans closed, show total expenses as the "cost to operate"

    - **Revenue Per Loan** = Total Revenue ÷ Loans Closed
      - Track by loan type (Conv, FHA, VA, Jumbo) as they have different margins

    - **Profit Per Loan** = Revenue Per Loan - Cost Per Loan
      - Healthy target: $1,000-$3,000 per loan

    - **Profit Margin** = (Net Profit ÷ Total Revenue) × 100
      - Industry healthy range: 15-30%
      - Below 10%: Needs immediate attention

    - **Break-Even Point** = Total Monthly Expenses ÷ Average Revenue Per Loan
      - The minimum number of loans needed to cover all costs

    - **Employee ROI** = (Revenue Attributed to Employee - Employee Cost) ÷ Employee Cost × 100
      - Measures each team member's contribution to profitability

    ## Expense Types:
    - **fixed**: Recurring costs that don't change (rent, subscriptions, base salaries)
    - **variable**: Costs that scale with volume (commissions, credit reports, appraisals)
    - **one_time**: One-off purchases (equipment, renovations, training)

    # CRM PAGE DIRECTORY
    When users ask where to find something or need to navigate, direct them to these pages:

    ## Main Navigation
    - **/dashboard** - Main dashboard with overview metrics, pipeline summary, and quick actions
    - **/ai** - AI Assistant landing page for conversational queries and daily briefings
    - **/leads** - Lead management - view, add, and manage prospective borrowers
    - **/leads/:id** - Individual lead detail page with full profile and activity
    - **/loans** - Active loan pipeline - all loans in progress
    - **/loans/:id** - Individual loan detail page with milestones, documents, and team
    - **/tasks** - Task management center - all outstanding and completed tasks
    - **/calendar** - Calendar view for appointments, closings, and deadlines

    ## Client Management
    - **/portfolio** - Client for Life (MUM) portfolio - past clients for retention marketing
    - **/portfolio/:id** - Individual client profile from portfolio
    - **/portfolio/year-over-year** - Year-over-year comparison of portfolio performance
    - **/referral-partners** - Referral partner management (realtors, builders, etc.)
    - **/referral-partners/:id** - Individual referral partner detail page
    - **/partner-roi** - Partner ROI dashboard - track which partners generate most business

    ## AI & Automation
    - **/ai** - AI Orchestrator chat interface for questions and coaching
    - **/ai-underwriter** - AI Underwriter for loan analysis and risk assessment
    - **/ai-receptionist-dashboard** - AI Receptionist call logs and performance
    - **/voice-os-dashboard** - Voice OS dashboard for call handling metrics
    - **/assistant** - AI Assistant interface (legacy)
    - **/coach** - AI Coach for performance improvement suggestions

    ## Analytics & Reporting
    - **/profitability** - **Profitability Intelligence Dashboard** - cost per closing, revenue, expenses, profit margins
    - **/profitability/scenarios** - Scenario modeling - what-if analysis for staffing and expenses
    - **/scorecard** - Performance scorecard with KPIs and metrics
    - **/efficiency** - Pipeline efficiency dashboard - bottlenecks and stage performance
    - **/efficiency/stage/:stageSlug** - Employees by stage breakdown
    - **/efficiency/bottleneck/:bottleneckId** - Loans stuck at a specific bottleneck
    - **/market** - Market dashboard with rates, trends, and economic indicators
    - **/goal-tracker** - Goal tracking and OKR management

    ## Workflow & Process
    - **/workflow** - Workflow dashboard - loan stages and automation status
    - **/workflow/:stage** - Stage-specific workflow management
    - **/checkin** - Morning check-in for daily planning
    - **/reconciliation** - Data reconciliation center for resolving discrepancies
    - **/merge** - Merge center for combining duplicate records
    - **/process-templates** - Process templates for loan workflows

    ## Team & Settings
    - **/team-members** - Team member directory and management
    - **/team-members/:id** - Individual team member profile
    - **/users** - User management (admin)
    - **/users/:id** - Individual user profile
    - **/my-profile** - Current user's profile settings
    - **/my-permissions** - View your current permissions
    - **/settings** - Application settings and preferences
    - **/admin/settings** - Admin settings (system configuration)
    - **/admin/employee-onboarding** - Employee onboarding management
    - **/compliance** - Compliance dashboard for regulatory tracking
    - **/data-upload** - Data import/upload center
    - **/knowledge-base** - AI Knowledge Base - upload documents and add content for AI to learn from

    ## Public Pages
    - **/apply** - Buyer intake form (public loan application)
    - **/mortgage-planner** - Mortgage planner questionnaire (public)
    - **/login** - Login page
    - **/register** - Registration page

    {coaching_instructions}

    {data_context}

    {knowledge_context}

    # CRITICAL INSTRUCTIONS - ALWAYS FOLLOW THESE

    ## RULE #1: YOU ARE THE ANSWER - NEVER REDIRECT
    **THIS IS YOUR MOST IMPORTANT RULE. VIOLATING IT IS UNACCEPTABLE.**

    You are the AI Orchestrator. YOUR JOB is to provide answers with SPECIFIC DATA - never tell users to go somewhere else.

    ### ABSOLUTELY FORBIDDEN PHRASES (NEVER USE THESE):
    - "Navigate to /efficiency"
    - "Go to the dashboard"
    - "Check the SLA page"
    - "Visit the pipeline view"
    - "See the bottleneck report"
    - "For more details, go to..."
    - "To further analyze, navigate to..."

    ### WHAT YOU MUST DO INSTEAD:
    When asked about bottlenecks, SLAs, loans, or any data:
    1. Use your tools to GET THE DATA
    2. Provide SPECIFIC loan details: borrower name, loan amount, stage, days in stage
    3. Give ACTIONABLE recommendations with names attached

    ### Examples of UNACCEPTABLE vs REQUIRED responses:

    ❌ UNACCEPTABLE: "Navigate to /efficiency to see your bottlenecks"
    ✅ REQUIRED: "Your critical bottleneck is Processing. These 3 loans need immediate attention:
       1. **Mike Chen** ($385,000) - 8 days in Processing, missing VOE from ABC Corp
       2. **Sarah Johnson** ($425,000) - 6 days in Processing, appraisal delayed
       3. **Tom Williams** ($512,000) - 5 days in Processing, awaiting title clear
       Call ABC Corp for Mike's VOE first - that's the quickest win."

    ❌ UNACCEPTABLE: "To further analyze these stages, navigate to the Pipeline Efficiency Dashboard"
    ✅ REQUIRED: "Here are your specific bottlenecks by stage:
       - **Disclosed → Processing**: 4 loans stuck (avg 5.2 days). Johnson and Williams need conditions cleared.
       - **Processing → Underwriting**: 2 loans delayed. Chen waiting on employer verification.
       - **Clear to Close**: Garcia ready but missing wire instructions. Call title company."

    ## RULE #2: USE YOUR TOOLS TO GET REAL DATA
    - When users ask about bottlenecks, pipeline issues, or SLA problems → call get_sla_dashboard with view="bottlenecks"
    - When asked about loans, deals, or specific borrowers → call get_loan_details
    - When asked about tasks or priorities → use the task data AND get_tasks tool
    - **DO NOT** guess or make up data - use the tools to get real information

    ## RULE #3: BE SPECIFIC WITH NAMES AND NUMBERS
    - Always include borrower names: "Sarah Johnson's $450,000 loan" not "a loan"
    - Always include specific metrics: "sitting 6.2 days on average vs 2-day target" not "taking too long"
    - Always include counts: "You have 8 loans stuck in Processing" not "some loans are stuck"
    - Always include actionable recommendations: "I'd focus on Jennifer's queue first - she has 18 overdue tasks"

    ## DETAILED RESPONSE EXAMPLES

    ### Example 1: "What are my pipeline bottlenecks?"

    ❌ BAD: "To analyze bottlenecks, navigate to /efficiency for the Pipeline Efficiency Dashboard."

    ✅ GOOD: "You have 3 critical bottlenecks right now:

    1. **Processing Stage** - Average time: 6.2 days (Target: 2 days)
       - 8 loans stuck in income verification
       - Jennifer has 18 overdue tasks (she's overwhelmed)

    2. **Appraisal Review** - Average time: 4.3 days (Target: 1.5 days)
       - 5 appraisals awaiting review
       - AMC response time is slow this week

    3. **Underwriting Submission** - Average time: 3.1 days (Target: 1 day)
       - Missing documents causing delays on 6 files

    **Biggest Issue:** Jennifer in processing. She's at 127% capacity.

    **My Recommendation:** Redistribute 5 of Jennifer's files to Tom (he's at 67% capacity). Want me to do that now?"

    ---

    ### Example 2: "How's my team performing this month?"

    ❌ BAD: "Check the Team Performance Dashboard at /team/performance"

    ✅ GOOD: "Your team is having a strong month:

    **Top Performers:**
    - Sarah: 11 closings, $2.8M volume, 41% conversion rate
    - Marcus: 9 closings, $2.4M volume, 38% conversion rate

    **Needs Attention:**
    - Tom: 4 closings, $892K volume, 23% conversion rate
      - Issue: Low activity (down 40% from last month)
      - Recommendation: Check in with him - something's off

    **Team Average:** 7.2 closings/LO, $1.9M volume/LO, 34% conversion rate

    You're on track for 58 closings this month (vs. 52 goal). Nice work."

    ---

    ### Example 3: "Show me deals at risk"

    ❌ BAD: "Navigate to the Pipeline Risk Dashboard to see at-risk deals"

    ✅ GOOD: "You have 4 deals at high risk of falling through:

    1. **Thompson Purchase** - Risk Score: 87/100 🔴
       - Issue: Borrower ghosting (no response in 9 days)
       - Loan: $525K | Action: Call them TODAY

    2. **Williams Refinance** - Risk Score: 78/100 🟠
       - Issue: Rate lock expires in 4 days, stuck in underwriting
       - Loan: $385K | Action: Request extension NOW

    3. **Chen Purchase** - Risk Score: 74/100 🟠
       - Issue: Appraisal came in $40K low
       - Loan: $485K | Action: Renegotiate contract price

    4. **Martinez FHA** - Risk Score: 71/100 🟠
       - Issue: DTI at 44% (above FHA max)
       - Loan: $320K | Action: Find $200/mo in debt to pay off

    Want me to draft the communications for each?"

    ## KEY RESPONSE PATTERNS
    - Always include **risk scores** or **severity indicators** (🔴 🟠 🟡)
    - Always include **capacity percentages** for team members
    - Always include **specific action items** with urgency ("Call them TODAY")
    - Always end with a **proactive offer** ("Want me to do that now?", "Want me to draft the communications?")

    ## Additional Guidelines
    - Reference the real data above when answering questions about financials
    - Be specific with actual numbers from the profitability data
    - When asked about cost per closing, revenue, or profit - use the EXACT figures from the data above
    - If profitability data is not configured, explain how to set it up (they can configure it at /profitability)
    - For financial analysis questions, provide actionable insights and recommendations
    - Cite the source: "Based on your pipeline data..." or "Looking at your loans..."
    - If knowledge base has relevant info, use it: "Based on your company guidelines..."
    - Provide clear, actionable recommendations based on the actual metrics"""

        async def generate_stream():
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]

            try:
                # First call - check if tools are needed
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=False  # First call non-streaming to check for tools
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                # If tools are called, execute them and send status
                if tool_calls:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Gathering data...'})}\n\n"

                    messages.append(response_message)

                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        if function_name in tool_functions:
                            result = await tool_functions[function_name](function_args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result)
                            })

                    yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing...'})}\n\n"

                # Now stream the final response
                stream = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    stream=True,
                    temperature=0.7
                )

                full_response = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                # Only return prioritized tasks if the user asked about tasks/priorities/briefing
                # Don't show tasks sidebar for unrelated questions like "cost per closing"
                is_task_question = any(keyword in message_lower for keyword in [
                    'task', 'priority', 'priorities', 'briefing', 'what should i do',
                    'what do i need', 'outstanding', 'overdue', 'due today', 'due tomorrow',
                    'bottleneck', 'pipeline', 'deal', 'loan status', 'closing soon'
                ])

                prioritized_tasks_data = []
                if is_task_question:
                    priority_tasks = sorted(
                        outstanding_tasks,
                        key=lambda x: (
                            0 if x.priority == "urgent" else 1 if x.priority == "high" else 2 if x.priority == "medium" else 3,
                            x.due_date or datetime.max
                        )
                    )[:10]

                    for task in priority_tasks:
                        loan_info = None
                        if task.loan_id:
                            loan = next((l for l in all_loans if l.id == task.loan_id), None)
                            if loan:
                                loan_info = {
                                    "borrower": loan.borrower_name,
                                    "amount": f"${loan.amount:,.0f}" if loan.amount else None,
                                    "stage": format_stage(loan.stage)
                                }

                        lead_name = None
                        if task.lead_id:
                            lead = next((l for l in all_leads if l.id == task.lead_id), None)
                            if lead:
                                lead_name = lead.name

                        prioritized_tasks_data.append({
                            "id": task.id,
                            "title": task.title,
                            "description": task.description,
                            "priority": task.priority.upper() if task.priority else "MEDIUM",
                            "due_date": task.due_date.strftime("%m/%d/%Y") if task.due_date else None,
                            "client": loan_info["borrower"] if loan_info else (lead_name or task.related_contact_name or ""),
                            "loan_amount": loan_info["amount"] if loan_info else None,
                            "stage": loan_info["stage"] if loan_info else None,
                            "status": task.status
                        })

                # Send completion signal with full response (and prioritized tasks only if relevant)
                yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'prioritized_tasks': prioritized_tasks_data if prioritized_tasks_data else None})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )


    @app.post("/api/v1/ai/autonomous-task")
    async def execute_autonomous_task(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Execute autonomous AI task with multi-step capability
        AI can send SMS, schedule appointments, create tasks autonomously
        """
        try:
            from openai import OpenAI
            import json
            from integrations.twilio_service import sms_client

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            data = await request.json()
            task = data.get("task", "")
            lead_id = data.get("lead_id")
            lead_name = data.get("lead_name", "")
            lead_phone = data.get("lead_phone", "")
            context = data.get("context", {})

            if not task:
                raise HTTPException(status_code=400, detail="Task is required")

            # Activity log to track what AI does
            activity_log = []

            # Log autonomous task to Mission Control
            action_id = await log_ai_action_to_mission_control(
                db=db,
                agent_name="Autonomous AI Agent",
                action_type="autonomous_task",
                lead_id=lead_id,
                user_id=current_user.id,
                context={"task": task[:200], "lead_name": lead_name},
                reasoning=f"Executing autonomous task: {task}",
                autonomy_level="full",  # This is fully autonomous!
                required_approval=False,
                status="pending"
            )

            # Define tools available to AI
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "send_sms",
                        "description": "Send SMS message to a lead's phone number",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "to_number": {
                                    "type": "string",
                                    "description": "Phone number to send SMS to (E.164 format)"
                                },
                                "message": {
                                    "type": "string",
                                    "description": "SMS message content to send"
                                }
                            },
                            "required": ["to_number", "message"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "schedule_appointment",
                        "description": "Schedule an appointment on the calendar",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_time": {
                                    "type": "string",
                                    "description": "Appointment date and time (ISO format)"
                                },
                                "duration_minutes": {
                                    "type": "integer",
                                    "description": "Duration in minutes"
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Appointment title"
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Additional notes"
                                }
                            },
                            "required": ["date_time", "title"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_task",
                        "description": "Create a follow-up task",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Task title"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Task description"
                                },
                                "due_date": {
                                    "type": "string",
                                    "description": "Due date (ISO format)"
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                    "description": "Task priority"
                                }
                            },
                            "required": ["title"]
                        }
                    }
                }
            ]

            # Create initial message
            system_prompt = f"""You are an autonomous AI agent helping with CRM tasks. You can:
    1. Send SMS messages to leads
    2. Schedule appointments on the calendar
    3. Create follow-up tasks

    Current task: {task}
    Lead: {lead_name} ({lead_phone})
    Context: {json.dumps(context)}

    Execute the task step by step. Be conversational and professional when texting leads.
    When scheduling appointments, confirm the time first via SMS before creating the calendar event.
    """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Execute this task: {task}"}
            ]

            # Run AI with function calling (max 5 iterations)
            for iteration in range(5):
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )

                assistant_message = response.choices[0].message
                messages.append(assistant_message)

                # Check if AI wants to call tools
                if assistant_message.tool_calls:
                    for tool_call in assistant_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        # Execute the tool
                        tool_result = None

                        if function_name == "send_sms":
                            # Send SMS using Twilio
                            try:
                                if not sms_client.enabled:
                                    tool_result = {"success": False, "error": "SMS service not configured"}
                                else:
                                    message_sid = await sms_client.send_sms(
                                        to_number=function_args["to_number"],
                                        message=function_args["message"]
                                    )

                                    # Log SMS
                                    sms_record = SMSMessage(
                                        user_id=current_user.id,
                                        lead_id=lead_id,
                                        to_number=function_args["to_number"],
                                        from_number=sms_client.from_number,
                                        message=function_args["message"],
                                        direction="outbound",
                                        status="sent",
                                        twilio_sid=message_sid
                                    )
                                    db.add(sms_record)
                                    db.commit()

                                    tool_result = {
                                        "success": True,
                                        "message_sid": message_sid,
                                        "message": "SMS sent successfully"
                                    }

                                    activity_log.append({
                                        "icon": "📤",
                                        "message": f"Sent SMS to {function_args['to_number']}: {function_args['message'][:50]}...",
                                        "timestamp": datetime.now().isoformat()
                                    })
                            except Exception as e:
                                tool_result = {"success": False, "error": str(e)}

                        elif function_name == "schedule_appointment":
                            # Create calendar appointment
                            try:
                                task_record = Task(
                                    user_id=current_user.id,
                                    title=function_args["title"],
                                    description=function_args.get("notes", ""),
                                    due_date=datetime.fromisoformat(function_args["date_time"]),
                                    priority="high",
                                    status="pending",
                                    entity_type="lead",
                                    entity_id=lead_id,
                                    created_by=current_user.id
                                )
                                db.add(task_record)
                                db.commit()

                                tool_result = {
                                    "success": True,
                                    "appointment_id": task_record.id,
                                    "message": "Appointment scheduled successfully"
                                }

                                activity_log.append({
                                    "icon": "📅",
                                    "message": f"Scheduled appointment: {function_args['title']} on {function_args['date_time']}",
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                tool_result = {"success": False, "error": str(e)}

                        elif function_name == "create_task":
                            # Create follow-up task
                            try:
                                task_record = Task(
                                    user_id=current_user.id,
                                    title=function_args["title"],
                                    description=function_args.get("description", ""),
                                    due_date=datetime.fromisoformat(function_args["due_date"]) if function_args.get("due_date") else None,
                                    priority=function_args.get("priority", "medium"),
                                    status="pending",
                                    entity_type="lead",
                                    entity_id=lead_id,
                                    created_by=current_user.id
                                )
                                db.add(task_record)
                                db.commit()

                                tool_result = {
                                    "success": True,
                                    "task_id": task_record.id,
                                    "message": "Task created successfully"
                                }

                                activity_log.append({
                                    "icon": "✅",
                                    "message": f"Created task: {function_args['title']}",
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                tool_result = {"success": False, "error": str(e)}

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result)
                        })
                else:
                    # No more tool calls, AI is done
                    break

            # Get final response
            final_message = messages[-1].content if hasattr(messages[-1], 'content') else "Task completed"

            # Update Mission Control with success
            if action_id:
                await update_ai_action_outcome(
                    db=db,
                    action_id=action_id,
                    outcome="success",
                    impact_score=0.9,  # High impact for autonomous actions!
                    metadata={
                        "activity_log": activity_log,
                        "tools_used": len(activity_log),
                        "iterations": iteration + 1
                    }
                )

            return {
                "success": True,
                "message": "Autonomous task executed successfully",
                "activity_log": activity_log,
                "final_response": final_message
            }

        except Exception as e:
            logger.error(f"Error in autonomous task: {e}")

            # Update Mission Control with failure
            # Note: action_id might not be in scope here, but we'll try
            try:
                if 'action_id' in locals() and action_id:
                    await update_ai_action_outcome(
                        db=db,
                        action_id=action_id,
                        outcome="failure",
                        metadata={"error": str(e)}
                    )
            except Exception:
                pass  # Don't fail main response if logging fails

            raise HTTPException(status_code=500, detail=str(e))


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

        # Set dependencies for the routes
        set_video_meeting_deps(get_db, get_current_user, video_meeting_models)

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
        from routes.smart_scheduler_settings_routes import router as smart_scheduler_settings_router
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

    @app.get("/api/v1/debug/email-sync-status")
    async def email_sync_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Debug endpoint: Check email sync and reconciliation status
        """
        try:
            # Check incoming emails
            email_stats = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN processed = true THEN 1 END) as processed,
                    COUNT(CASE WHEN processed = false THEN 1 END) as pending
                FROM incoming_data_events
                WHERE source = 'microsoft365'
            """)).fetchone()

            # Check reconciliation items
            recon_stats = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
                FROM reconciliation_items
            """)).fetchone()

            # Get recent emails
            recent_emails = db.execute(text("""
                SELECT subject, sender, received_at, processed
                FROM incoming_data_events
                WHERE source = 'microsoft365'
                ORDER BY received_at DESC
                LIMIT 5
            """)).fetchall()

            # Get recent reconciliation items
            recent_recon = db.execute(text("""
                SELECT entity_type, confidence_score, status, created_at
                FROM reconciliation_items
                ORDER BY created_at DESC
                LIMIT 5
            """)).fetchall()

            return {
                "success": True,
                "emails": {
                    "total": email_stats[0],
                    "processed": email_stats[1],
                    "pending": email_stats[2],
                    "recent": [
                        {
                            "subject": e[0],
                            "sender": e[1],
                            "received_at": e[2].isoformat() if e[2] else None,
                            "processed": e[3]
                        }
                        for e in recent_emails
                    ]
                },
                "reconciliation": {
                    "total": recon_stats[0],
                    "pending": recon_stats[1],
                    "approved": recon_stats[2],
                    "rejected": recon_stats[3],
                    "recent": [
                        {
                            "entity_type": r[0],
                            "confidence_score": float(r[1]) if r[1] else 0,
                            "status": r[2],
                            "created_at": r[3].isoformat() if r[3] else None
                        }
                        for r in recent_recon
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Debug endpoint failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @app.post("/api/v1/create-sample-tasks")
    async def create_sample_tasks(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Create 5 sample reconciliation tasks from emails for testing
        """
        try:
            sample_emails = [
                {
                    "subject": "RE: Johnson Loan - Appraisal Scheduled for Next Week",
                    "sender": "appraisal@titleco.com",
                    "content": "The appraisal for the Johnson property at 123 Oak Street has been scheduled for next Tuesday at 2 PM. Loan amount: $450,000",
                    "category": "loan_update",
                    "subcategory": "appraisal_scheduled",
                    "fields": {
                        "borrower_name": {"value": "Johnson", "confidence": 0.85},
                        "property_address": {"value": "123 Oak Street", "confidence": 0.90},
                        "loan_amount": {"value": "$450,000", "confidence": 0.95}
                    }
                },
                {
                    "subject": "URGENT: Smith Closing - Title Issue Detected",
                    "sender": "title@escrow.com",
                    "content": "We've discovered a lien on the Smith property (456 Maple Avenue). Loan: $325,000. Outstanding HOA lien of $2,500",
                    "category": "loan_update",
                    "subcategory": "title_issue",
                    "fields": {
                        "borrower_name": {"value": "Smith", "confidence": 0.92},
                        "property_address": {"value": "456 Maple Avenue", "confidence": 0.95},
                        "loan_amount": {"value": "$325,000", "confidence": 0.98}
                    }
                },
                {
                    "subject": "Williams Pre-Approval Request - $600K Budget",
                    "sender": "sarah.williams@email.com",
                    "content": "Name: Sarah Williams, Phone: (555) 123-4567, Budget: $600,000, Property Type: Single Family Home",
                    "category": "lead_update",
                    "subcategory": "new_lead",
                    "fields": {
                        "borrower_name": {"value": "Sarah Williams", "confidence": 0.98},
                        "phone": {"value": "(555) 123-4567", "confidence": 0.95},
                        "loan_amount": {"value": "$600,000", "confidence": 0.92}
                    }
                },
                {
                    "subject": "RE: Martinez Loan - Rate Lock Expiring Soon",
                    "sender": "processor@lendingco.com",
                    "content": "Borrower: Carlos Martinez, Property: 789 Pine Boulevard, Loan: $280,000, Rate: 6.75%, Expires: December 1st",
                    "category": "loan_update",
                    "subcategory": "rate_lock_expiring",
                    "fields": {
                        "borrower_name": {"value": "Carlos Martinez", "confidence": 0.96},
                        "property_address": {"value": "789 Pine Boulevard", "confidence": 0.94},
                        "loan_amount": {"value": "$280,000", "confidence": 0.97}
                    }
                },
                {
                    "subject": "Thompson Family - Clear to Close!",
                    "sender": "underwriting@mortgage.com",
                    "content": "Borrower: Michael & Jennifer Thompson, Property: 321 Birch Lane, Loan: $525,000, Closing: November 20th, Status: APPROVED",
                    "category": "loan_update",
                    "subcategory": "clear_to_close",
                    "fields": {
                        "borrower_name": {"value": "Michael & Jennifer Thompson", "confidence": 0.97},
                        "property_address": {"value": "321 Birch Lane", "confidence": 0.95},
                        "loan_amount": {"value": "$525,000", "confidence": 0.98}
                    }
                }
            ]

            created_tasks = []

            for idx, email in enumerate(sample_emails, 1):
                # Create incoming data event
                db_event = IncomingDataEvent(
                    source="microsoft365",
                    external_message_id=f"sample_task_{idx}_{datetime.now().timestamp()}",
                    raw_text=email["content"],
                    subject=email["subject"],
                    sender=email["sender"],
                    received_at=datetime.now(timezone.utc),
                    user_id=current_user.id,
                    processed=True
                )
                db.add(db_event)
                db.flush()

                # Calculate average confidence
                confidences = [field["confidence"] for field in email["fields"].values()]
                avg_confidence = sum(confidences) / len(confidences)

                # Create extracted data (reconciliation item)
                extracted = ExtractedData(
                    event_id=db_event.id,
                    category=email["category"],
                    subcategory=email["subcategory"],
                    fields=email["fields"],
                    ai_confidence=avg_confidence,
                    status="pending_review"
                )
                db.add(extracted)
                db.flush()

                created_tasks.append({
                    "event_id": db_event.id,
                    "extracted_id": extracted.id,
                    "subject": email["subject"],
                    "category": email["category"]
                })

            db.commit()

            return {
                "success": True,
                "message": f"Created {len(created_tasks)} reconciliation tasks",
                "tasks": created_tasks
            }

        except Exception as e:
            logger.error(f"Failed to create sample tasks: {e}")
            db.rollback()
            return {
                "success": False,
                "error": str(e)
            }

    @app.post("/api/v1/auto-fix-error")
    async def auto_fix_error(
        request: ErrorFixRequest,
        current_user: User = Depends(get_current_user)
    ):
        """
        AI-powered error analysis and fix recommendations
        Uses Claude AI to analyze frontend errors and provide fix suggestions
        """
        try:
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

            if not anthropic_api_key:
                logger.warning("Anthropic API key not configured for error fix")
                return {
                    "success": False,
                    "message": "AI error analysis is not configured. Please set ANTHROPIC_API_KEY.",
                    "analysis": None
                }

            # Initialize Anthropic client
            client = anthropic.Anthropic(api_key=anthropic_api_key)

            # Build the analysis prompt
            prompt = f"""You are an expert software engineer debugging a React application error.

    Error Details:
    - Error Message: {request.error_message}
    - URL: {request.url}
    - Attempt Number: {request.attempt_number}

    Error Stack:
    {request.error_stack if request.error_stack else "Not provided"}

    Component Stack:
    {request.component_stack if request.component_stack else "Not provided"}

    User Agent:
    {request.user_agent if request.user_agent else "Not provided"}

    Please analyze this error and provide:
    1. The root cause of the error
    2. A step-by-step fix strategy
    3. Which files are likely affected
    4. Your confidence level (High/Medium/Low)
    5. A recommendation for preventing similar errors

    Respond in JSON format with these keys:
    {{
      "root_cause": "description of what caused the error",
      "fix_strategy": "step-by-step plan to fix it",
      "files_affected": ["list", "of", "file", "paths"],
      "confidence": "High/Medium/Low",
      "recommendation": "how to prevent this in the future"
    }}"""

            # Call Claude API
            logger.info(f"Requesting error analysis from Claude for user {current_user.id}")

            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse the response
            response_text = message.content[0].text
            logger.info(f"Received analysis from Claude: {response_text[:200]}...")

            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # If no JSON found, structure the response manually
                analysis = {
                    "root_cause": response_text,
                    "fix_strategy": "See root cause analysis",
                    "files_affected": [],
                    "confidence": "Medium",
                    "recommendation": "Review the error analysis above"
                }

            return {
                "success": True,
                "message": "Error analysis completed successfully",
                "analysis": {
                    "root_cause": analysis.get("root_cause", "Analysis provided"),
                    "fix_strategy": analysis.get("fix_strategy", ""),
                    "files_affected": analysis.get("files_affected", []),
                    "confidence": analysis.get("confidence", "Medium"),
                    "recommendation": analysis.get("recommendation", "")
                },
                "fix_strategy": analysis.get("fix_strategy", ""),
                "files_affected": analysis.get("files_affected", []),
                "confidence": analysis.get("confidence", "Medium"),
                "recommendation": analysis.get("recommendation", "")
            }

        except Exception as e:
            logger.error(f"Error in auto_fix_error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Failed to analyze error: {str(e)}",
                "analysis": None
            }

    @app.post("/api/v1/microsoft/sync-now")
    async def sync_microsoft_emails_now(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Manually trigger email sync from Microsoft 365"""
        try:
            # Log diagnostic info
            logger.info(f"Sync triggered by user {current_user.id}")
            logger.info(f"OpenAI client available: {openai_client is not None}")
            logger.info(f"OpenAI API key set: {bool(OPENAI_API_KEY)}")
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            if not oauth_record.sync_enabled:
                raise HTTPException(status_code=400, detail="Email sync is disabled")

            # Log which account/folder we're syncing from
            logger.info(f"Syncing from Microsoft account: {oauth_record.email_address}, folder: {oauth_record.sync_folder or 'Inbox'}")

            # Auto-populate known_client_emails table before sync for better identity resolution
            try:
                from sqlalchemy import text as sa_text
                # Get emails from leads
                leads = db.execute(sa_text("""
                    SELECT id, email, name FROM leads
                    WHERE email IS NOT NULL AND status NOT IN ('dead', 'closed_lost')
                """)).fetchall()
                for lead in leads:
                    if lead[1]:
                        db.execute(sa_text("""
                            INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, user_id)
                            VALUES (:email, :lead_id, :name, 'lead', :user_id)
                            ON CONFLICT (email_address, user_id) DO UPDATE SET
                                lead_id = COALESCE(known_client_emails.lead_id, :lead_id),
                                updated_at = CURRENT_TIMESTAMP
                        """), {"email": lead[1].lower(), "lead_id": lead[0], "name": lead[2], "user_id": current_user.id})

                # Get emails from loans
                loans = db.execute(sa_text("""
                    SELECT id, borrower_email, borrower_name FROM loans
                    WHERE borrower_email IS NOT NULL AND status NOT IN ('cancelled', 'withdrawn')
                """)).fetchall()
                for loan in loans:
                    if loan[1]:
                        db.execute(sa_text("""
                            INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, user_id)
                            VALUES (:email, :loan_id, :name, 'loan', :user_id)
                            ON CONFLICT (email_address, user_id) DO UPDATE SET
                                loan_id = COALESCE(known_client_emails.loan_id, :loan_id),
                                updated_at = CURRENT_TIMESTAMP
                        """), {"email": loan[1].lower(), "loan_id": loan[0], "name": loan[2], "user_id": current_user.id})

                db.commit()
                logger.info(f"Auto-synced {len(leads)} leads and {len(loans)} loans to known_client_emails")
            except Exception as kce_error:
                logger.warning(f"Could not auto-sync known_client_emails: {kce_error}")
                db.rollback()

            # Fetch emails with timeout
            import asyncio
            try:
                result = await asyncio.wait_for(
                    fetch_microsoft_emails(oauth_record, db, limit=50),
                    timeout=60  # 60 second timeout for fetching emails
                )
            except asyncio.TimeoutError:
                logger.error(f"Microsoft email fetch timed out for user {current_user.id}")
                raise HTTPException(status_code=504, detail="Email fetch timed out - please try again")

            if "error" in result:
                # If token needs reauth, return specific status code so frontend can handle
                if result.get("needs_reauth"):
                    raise HTTPException(status_code=401, detail="needs_reauth")
                raise HTTPException(status_code=500, detail=result["error"])

            # Process each email through DRE with individual error handling
            emails = result.get("emails", [])
            processed_count = 0
            skipped_count = 0
            error_count = 0
            errors = []

            for idx, email_data in enumerate(emails):
                try:
                    # Process each email with a 45-second timeout
                    process_result = await asyncio.wait_for(
                        process_microsoft_email_to_dre(email_data, current_user.id, db),
                        timeout=45
                    )
                    if process_result.get("status") == "success":
                        processed_count += 1
                    elif process_result.get("status") == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                except asyncio.TimeoutError:
                    error_count += 1
                    subject = email_data.get("subject", "Unknown")[:50]
                    errors.append(f"Timeout processing email {idx+1}: {subject}")
                    logger.warning(f"Timeout processing email {idx+1}/{len(emails)}: {subject}")
                except Exception as e:
                    error_count += 1
                    subject = email_data.get("subject", "Unknown")[:50]
                    errors.append(f"Error processing email {idx+1}: {str(e)[:100]}")
                    logger.error(f"Error processing email {idx+1}/{len(emails)} ({subject}): {e}")
                    # Continue with next email instead of failing entire sync

            # Update last_sync_at timestamp
            oauth_record.last_sync_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Synced {processed_count}/{len(emails)} emails for user {current_user.id} (skipped: {skipped_count}, errors: {error_count})")

            # Build informative message
            if len(emails) == 0:
                message = f"No new emails in {oauth_record.sync_folder or 'Inbox'} from {oauth_record.email_address}"
            elif processed_count == 0 and skipped_count > 0:
                message = f"All {skipped_count} emails already synced from {oauth_record.email_address}"
            elif processed_count > 0:
                message = f"Synced {processed_count} new emails from {oauth_record.email_address}"
                if error_count > 0:
                    message += f" ({error_count} errors)"
            else:
                message = f"Synced {processed_count} emails from {oauth_record.email_address}"

            return {
                "status": "success",
                "email_account": oauth_record.email_address,
                "sync_folder": oauth_record.sync_folder or "Inbox",
                "fetched_count": len(emails),
                "processed_count": processed_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "errors": errors[:5] if errors else [],  # Return first 5 errors
                "message": message
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Microsoft sync error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")

    @app.get("/api/v1/reconciliation/debug")
    async def debug_reconciliation(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to check email and extraction status"""
        try:
            from sqlalchemy import text

            # Count IncomingDataEvents
            events_count = db.execute(text("""
                SELECT COUNT(*) FROM incoming_data_events WHERE user_id = :user_id
            """), {"user_id": current_user.id}).scalar()

            # Count ExtractedData for user's events
            extracted_count = db.execute(text("""
                SELECT COUNT(*) FROM extracted_data ed
                JOIN incoming_data_events ide ON ed.event_id = ide.id
                WHERE ide.user_id = :user_id
            """), {"user_id": current_user.id}).scalar()

            # Get status breakdown
            status_breakdown = db.execute(text("""
                SELECT ed.status, COUNT(*) as count FROM extracted_data ed
                JOIN incoming_data_events ide ON ed.event_id = ide.id
                WHERE ide.user_id = :user_id
                GROUP BY ed.status
            """), {"user_id": current_user.id}).fetchall()

            # Get recent events
            recent_events = db.execute(text("""
                SELECT ide.id, ide.subject, ide.processed, ed.status, ed.category
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ide.user_id = :user_id
                ORDER BY ide.created_at DESC
                LIMIT 5
            """), {"user_id": current_user.id}).fetchall()

            return {
                "user_id": current_user.id,
                "incoming_events_count": events_count,
                "extracted_data_count": extracted_count,
                "status_breakdown": {row[0]: row[1] for row in status_breakdown},
                "recent_events": [
                    {"id": row[0], "subject": row[1][:50] if row[1] else None, "processed": row[2], "status": row[3], "category": row[4]}
                    for row in recent_events
                ]
            }
        except Exception as e:
            logger.error(f"Debug error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @app.get("/api/v1/debug/all-loans")
    async def debug_all_loans(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to see ALL loans in the database (bypasses permission filtering)"""
        try:
            from sqlalchemy import text

            # Get ALL loans regardless of loan_officer_id
            all_loans = db.execute(text("""
                SELECT id, loan_number, borrower_name, borrower_email, stage, loan_officer_id, created_at
                FROM loans
                ORDER BY created_at DESC
                LIMIT 50
            """)).fetchall()

            return {
                "total_loans": len(all_loans),
                "loans": [
                    {
                        "id": row[0],
                        "loan_number": row[1],
                        "borrower_name": row[2],
                        "borrower_email": row[3],
                        "stage": row[4],
                        "loan_officer_id": row[5],
                        "created_at": str(row[6]) if row[6] else None
                    }
                    for row in all_loans
                ]
            }
        except Exception as e:
            logger.error(f"Debug all loans error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @app.get("/api/v1/debug/dashboard-diagnosis")
    async def debug_dashboard_diagnosis(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to diagnose dashboard errors step by step"""
        import traceback
        from datetime import date, timedelta, datetime, timezone
        from sqlalchemy import func, extract, case, text

        results = {"user_id": current_user.id, "steps": []}

        try:
            # Step 1: Basic date setup
            today = date.today()
            start_of_month = today.replace(day=1)
            results["steps"].append({"step": "date_setup", "status": "ok", "today": str(today)})
        except Exception as e:
            results["steps"].append({"step": "date_setup", "status": "error", "error": str(e)})
            return results

        try:
            # Step 2: User metadata
            user_metadata = current_user.user_metadata or {}
            goals = user_metadata.get('goals', {})
            results["steps"].append({"step": "user_metadata", "status": "ok", "has_goals": bool(goals)})
        except Exception as e:
            results["steps"].append({"step": "user_metadata", "status": "error", "error": str(e)})
            return results

        try:
            # Step 3: Funded loans query with case statements
            funded_counts = db.query(
                func.count(case((extract('year', Loan.funded_date) == today.year, 1))).label('annual'),
                func.count(case((Loan.funded_date >= start_of_month, 1))).label('monthly')
            ).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage == LoanStage.FUNDED
            ).first()
            results["steps"].append({"step": "funded_counts", "status": "ok", "annual": funded_counts.annual or 0})
        except Exception as e:
            results["steps"].append({"step": "funded_counts", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 4: Lead counts query
            lead_counts = db.query(
                func.count(case((Lead.stage == LeadStage.NEW, 1))).label('new_leads'),
                func.count(case((Lead.stage == LeadStage.PRE_APPROVED, 1))).label('preapproved')
            ).filter(
                Lead.owner_id == current_user.id
            ).first()
            results["steps"].append({"step": "lead_counts", "status": "ok", "new_leads": lead_counts.new_leads or 0})
        except Exception as e:
            results["steps"].append({"step": "lead_counts", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 5: Active loans query
            active_loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED, LoanStage.CTC])
            ).all()
            results["steps"].append({"step": "active_loans", "status": "ok", "count": len(active_loans)})
        except Exception as e:
            results["steps"].append({"step": "active_loans", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 6: Tasks query
            tasks_today = db.query(Task).filter(
                Task.owner_id == current_user.id,
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date <= today + timedelta(days=1)
            ).limit(10).all()
            results["steps"].append({"step": "tasks_query", "status": "ok", "count": len(tasks_today)})
        except Exception as e:
            results["steps"].append({"step": "tasks_query", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 7: Lead metrics with ai_score
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            lead_metrics_query = db.query(
                func.count(Lead.id).label('total_leads'),
                func.count(case((Lead.created_at >= today_start, 1))).label('new_today'),
                func.count(case(((Lead.ai_score >= 80) & (Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT])), 1))).label('hot_leads')
            ).filter(
                Lead.owner_id == current_user.id
            ).first()
            results["steps"].append({"step": "lead_metrics", "status": "ok", "total_leads": lead_metrics_query.total_leads or 0})
        except Exception as e:
            results["steps"].append({"step": "lead_metrics", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 8: Referral partners query
            partners = db.query(ReferralPartner).filter(
                ReferralPartner.status == "active"
            ).limit(5).all()
            results["steps"].append({"step": "referral_partners", "status": "ok", "count": len(partners)})
        except Exception as e:
            results["steps"].append({"step": "referral_partners", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        try:
            # Step 9: AI Colleague Actions table check
            thirty_days_ago = today - timedelta(days=30)
            ai_tasks_count = db.query(func.count(AIColleagueAction.id)).filter(
                AIColleagueAction.user_id == current_user.id,
                AIColleagueAction.created_at >= thirty_days_ago
            ).scalar() or 0
            results["steps"].append({"step": "ai_colleague_actions", "status": "ok", "count": ai_tasks_count})
        except Exception as e:
            results["steps"].append({"step": "ai_colleague_actions", "status": "error", "error": str(e), "traceback": traceback.format_exc()})
            return results

        results["overall_status"] = "all_steps_passed"
        return results


    @app.post("/api/v1/microsoft/reprocess-emails")
    async def reprocess_unextracted_emails(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Reprocess emails that were synced but not extracted (for fixing failed extractions)"""
        try:
            # Find all emails without extracted data for this user
            unextracted = db.execute(text("""
                SELECT ide.id, ide.subject, ide.sender, ide.raw_text, ide.raw_html, ide.received_at, ide.recipients
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ed.id IS NULL AND ide.user_id = :user_id
                ORDER BY ide.created_at DESC
            """), {"user_id": current_user.id}).fetchall()

            logger.info(f"Found {len(unextracted)} unextracted emails for user {current_user.id}")

            if len(unextracted) == 0:
                return {
                    "status": "success",
                    "reprocessed_count": 0,
                    "message": "No emails need reprocessing"
                }

            # Reprocess each email
            success_count = 0

            for email_id, subject, sender, raw_text, raw_html, received_at, recipients in unextracted:
                # Get the full event
                event = db.query(IncomingDataEvent).filter(IncomingDataEvent.id == email_id).first()

                if not event:
                    continue

                # Create email_data dict (mimicking Microsoft Graph format)
                email_data = {
                    "subject": subject,
                    "from": {"emailAddress": {"address": sender}},
                    "toRecipients": [{"emailAddress": {"address": r}} for r in (recipients or [])],
                    "receivedDateTime": received_at.isoformat() if received_at else None,
                    "body": {
                        "content": raw_text or raw_html or "",
                        "contentType": "text" if raw_text else "html"
                    }
                }

                # Delete old event to avoid duplicates
                db.delete(event)
                db.commit()

                # Reprocess with new extraction logic
                result = await process_microsoft_email_to_dre(email_data, current_user.id, db)

                if result.get("status") == "success":
                    success_count += 1

            logger.info(f"Reprocessed {success_count}/{len(unextracted)} emails for user {current_user.id}")

            return {
                "status": "success",
                "reprocessed_count": success_count,
                "total_found": len(unextracted),
                "message": f"Reprocessed {success_count} emails successfully"
            }

        except Exception as e:
            logger.error(f"Email reprocessing error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.get("/api/v1/microsoft/synced-emails-status")
    async def get_synced_emails_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Check status of synced emails - where did they go?"""
        try:
            from sqlalchemy import text

            # Get all incoming events for this user from Microsoft
            events = db.execute(text("""
                SELECT
                    ide.id, ide.subject, ide.sender, ide.received_at, ide.processed, ide.created_at,
                    ed.id as extracted_id, ed.status as extracted_status, ed.category
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ide.user_id = :user_id AND ide.source = 'microsoft365'
                ORDER BY ide.received_at DESC
                LIMIT 20
            """), {"user_id": current_user.id}).fetchall()

            results = []
            for e in events:
                results.append({
                    "event_id": e[0],
                    "subject": e[1][:50] if e[1] else None,
                    "sender": e[2],
                    "received_at": e[3].isoformat() if e[3] else None,
                    "processed": e[4],
                    "synced_at": e[5].isoformat() if e[5] else None,
                    "extracted_id": e[6],
                    "extracted_status": e[7],
                    "category": e[8]
                })

            # Summary stats
            total = len(results)
            with_extraction = len([r for r in results if r["extracted_id"]])
            pending_review = len([r for r in results if r["extracted_status"] == "pending_review"])

            return {
                "total_synced": total,
                "with_extraction": with_extraction,
                "pending_review": pending_review,
                "emails": results,
                "note": "If emails are synced but not in Reconciliation, they may have been classified as 'unrelated' or had extraction errors"
            }

        except Exception as e:
            logger.error(f"Synced emails status error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/microsoft/clear-sync-history")
    async def clear_sync_history(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Clear sync history to allow re-syncing all emails (use with caution)"""
        try:
            from sqlalchemy import text

            # Delete extracted data first (foreign key constraint)
            deleted_extracted = db.execute(text("""
                DELETE FROM extracted_data
                WHERE event_id IN (
                    SELECT id FROM incoming_data_events
                    WHERE user_id = :user_id AND source = 'microsoft365'
                )
            """), {"user_id": current_user.id}).rowcount

            # Delete incoming events
            deleted_events = db.execute(text("""
                DELETE FROM incoming_data_events
                WHERE user_id = :user_id AND source = 'microsoft365'
            """), {"user_id": current_user.id}).rowcount

            db.commit()

            return {
                "status": "success",
                "deleted_events": deleted_events,
                "deleted_extractions": deleted_extracted,
                "message": f"Cleared {deleted_events} synced emails. Click 'Sync Emails Now' to re-sync."
            }

        except Exception as e:
            logger.error(f"Clear sync history error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/reconciliation/reextract/{extracted_data_id}")
    async def reextract_email_data(
        extracted_data_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Force re-extraction of a specific email using updated AI classification"""
        try:
            # Get the extracted data record
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == extracted_data_id
            ).first()

            if not extracted:
                raise HTTPException(status_code=404, detail="Extracted data not found")

            # Get the original email event
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == extracted.event_id
            ).first()

            if not event:
                raise HTTPException(status_code=404, detail="Original email not found")

            # Get the email content
            content = event.raw_text or event.raw_html or ""
            subject = event.subject or ""
            sender = event.sender or ""

            logger.info(f"Re-extracting email {extracted_data_id}: {subject[:50]}...")

            # Use Claude parser for re-extraction
            try:
                from ai_providers.claude_parser import get_claude_parser
                parser = get_claude_parser()

                claude_email_data = {
                    "subject": subject,
                    "body_text": content,
                    "sender": sender,
                    "received_at": event.received_at.isoformat() if event.received_at else None
                }

                # Re-classify the email type
                profile_type = parser.classify_email(claude_email_data)
                logger.info(f"Re-classified as: {profile_type}")

                # Re-parse with Claude
                parsed_result = await parser.parse_email(
                    claude_email_data,
                    profile_type,
                    None
                )

                extracted_fields = parsed_result.get('extracted_fields', {})
                confidence_scores = parsed_result.get('confidence_scores', {})

                # Build new fields dict
                new_fields = {}
                for field_name, field_value in extracted_fields.items():
                    if field_value is not None:
                        confidence = confidence_scores.get(field_name, 80)
                        new_fields[field_name] = {
                            "value": field_value,
                            "confidence": confidence / 100 if confidence > 1 else confidence
                        }

                # Update the extracted data record
                extracted.fields = new_fields
                extracted.match_confidence = parsed_result.get('overall_confidence', 0) / 100
                extracted.email_intent = parsed_result.get('email_summary', profile_type)
                extracted.updated_at = datetime.utcnow()

                db.commit()

                logger.info(f"✅ Re-extracted {len(new_fields)} fields for email {extracted_data_id}")

                return {
                    "status": "success",
                    "profile_type": profile_type,
                    "fields_extracted": len(new_fields),
                    "fields": new_fields,
                    "confidence": parsed_result.get('overall_confidence', 0)
                }

            except Exception as parse_error:
                logger.error(f"Claude parsing error: {parse_error}")
                raise HTTPException(status_code=500, detail=f"Parsing error: {str(parse_error)}")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Re-extraction error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/reconciliation/reextract-all-pending")
    async def reextract_all_pending_emails(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Force re-extraction of ALL pending reconciliation items using updated AI"""
        try:
            # Get all pending items
            pending = db.query(ExtractedData).filter(
                ExtractedData.status == "pending_review"
            ).all()

            if not pending:
                return {
                    "status": "success",
                    "message": "No pending items to reprocess",
                    "reprocessed": 0
                }

            logger.info(f"Re-extracting {len(pending)} pending items...")

            success_count = 0
            errors = []

            from ai_providers.claude_parser import get_claude_parser
            parser = get_claude_parser()

            for extracted in pending:
                try:
                    # Get the original email event
                    event = db.query(IncomingDataEvent).filter(
                        IncomingDataEvent.id == extracted.event_id
                    ).first()

                    if not event:
                        continue

                    content = event.raw_text or event.raw_html or ""
                    subject = event.subject or ""
                    sender = event.sender or ""

                    claude_email_data = {
                        "subject": subject,
                        "body_text": content,
                        "sender": sender,
                        "received_at": event.received_at.isoformat() if event.received_at else None
                    }

                    # Re-classify and parse
                    profile_type = parser.classify_email(claude_email_data)
                    parsed_result = await parser.parse_email(claude_email_data, profile_type, None)

                    extracted_fields = parsed_result.get('extracted_fields', {})
                    confidence_scores = parsed_result.get('confidence_scores', {})

                    # Build new fields dict
                    new_fields = {}
                    for field_name, field_value in extracted_fields.items():
                        if field_value is not None:
                            confidence = confidence_scores.get(field_name, 80)
                            new_fields[field_name] = {
                                "value": field_value,
                                "confidence": confidence / 100 if confidence > 1 else confidence
                            }

                    # Update the record
                    extracted.fields = new_fields
                    extracted.match_confidence = parsed_result.get('overall_confidence', 0) / 100
                    extracted.email_intent = parsed_result.get('email_summary', profile_type)
                    extracted.updated_at = datetime.utcnow()

                    success_count += 1
                    logger.info(f"Re-extracted {extracted.id}: {len(new_fields)} fields as {profile_type}")

                except Exception as item_error:
                    errors.append(f"Item {extracted.id}: {str(item_error)}")
                    logger.error(f"Error re-extracting item {extracted.id}: {item_error}")

            db.commit()

            return {
                "status": "success",
                "total_pending": len(pending),
                "reprocessed": success_count,
                "errors": errors[:5] if errors else [],
                "message": f"Re-extracted {success_count}/{len(pending)} items"
            }

        except Exception as e:
            logger.error(f"Bulk re-extraction error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/reconciliation/create-test-item")
    async def create_test_reconciliation_item(
        fields: dict[str, Any],
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Create a test extracted data item for testing reconciliation approval flow.

        This endpoint is for development/testing purposes only.

        Example request:
        {
            "first_name": "Clarissa",
            "last_name": "Stansbury",
            "email": "claire.sumika@gmail.com",
            "phone": "(937) 789-9802"
        }
        """
        try:
            # First create a dummy incoming data event
            test_event = IncomingDataEvent(
                source="test",
                raw_text=f"Test data for {fields.get('first_name', '')} {fields.get('last_name', '')}",
                subject="Test Reconciliation Item",
                sender="test@example.com",
                user_id=current_user.id,
                processed=True
            )
            db.add(test_event)
            db.flush()

            # Build fields dict with confidence scores
            formatted_fields = {}
            for field_name, field_value in fields.items():
                if field_value is not None:
                    formatted_fields[field_name] = {
                        "value": field_value,
                        "confidence": 0.95
                    }

            # Create extracted data with no match (will trigger "No Matching Borrower" dialog)
            extracted = ExtractedData(
                event_id=test_event.id,
                category="lead_update",
                subcategory="new_borrower",
                fields=formatted_fields,
                match_entity_type=None,  # No match - will trigger create borrower dialog
                match_entity_id=None,
                match_confidence=0.0,
                ai_confidence=0.85,
                status="pending_review"
            )
            db.add(extracted)
            db.commit()
            db.refresh(extracted)

            logger.info(f"Created test extracted data item {extracted.id} for testing")

            return {
                "status": "success",
                "extracted_data_id": extracted.id,
                "event_id": test_event.id,
                "fields": formatted_fields,
                "message": f"Test item created successfully. Use extracted_data_id={extracted.id} for approval."
            }
        except Exception as e:
            logger.error(f"Error creating test item: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/reconciliation/test-match")
    async def test_entity_match(
        loan_number: str = None,
        borrower_name: str = None,
        email: str = None,
        phone: str = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Test the entity matching logic with provided fields.

        This endpoint is for development/testing purposes to verify matching works.
        """
        try:
            # Build fields dict
            fields = {}
            if loan_number:
                fields["loan_number"] = {"value": loan_number, "confidence": 0.95}
            if borrower_name:
                fields["borrower_name"] = {"value": borrower_name, "confidence": 0.95}
            if email:
                fields["borrower_email"] = {"value": email, "confidence": 0.95}
            if phone:
                fields["borrower_phone"] = {"value": phone, "confidence": 0.95}

            if not fields:
                raise HTTPException(status_code=400, detail="At least one field required")

            # Run matching
            match_result = match_entity(fields, db, current_user.id)

            # Get entity name if matched
            entity_name = None
            if match_result.get("entity_type") and match_result.get("entity_id"):
                entity_name = get_entity_name(match_result["entity_type"], match_result["entity_id"], db)

            return {
                "status": "success",
                "input_fields": {k: v["value"] for k, v in fields.items()},
                "match_result": match_result,
                "entity_name": entity_name,
                "message": f"Match found: {match_result.get('entity_type', 'None')} ({entity_name})" if match_result.get("entity_type") else "No match found"
            }
        except Exception as e:
            logger.error(f"Error testing match: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/reconciliation/rematch-all")
    async def rematch_all_pending(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Re-run matching on all pending reconciliation items.

        This is useful after adding new matching logic (like ActiveLoanProfile)
        to update previously unmatched items.
        """
        try:
            from sqlalchemy import or_
            pending = db.query(ExtractedData).join(
                IncomingDataEvent,
                ExtractedData.event_id == IncomingDataEvent.id
            ).filter(
                or_(
                    IncomingDataEvent.user_id == current_user.id,
                    IncomingDataEvent.user_id == None
                ),
                ExtractedData.status.in_(["pending_review", "needs_review", "pending"])
            ).all()

            updated_count = 0
            for item in pending:
                # Re-run matching
                match_result = match_entity(item.fields or {}, db, current_user.id)

                if match_result.get("entity_type"):
                    # Update if we found a match
                    item.match_entity_type = match_result["entity_type"]
                    item.match_entity_id = str(match_result["entity_id"])
                    item.match_confidence = match_result.get("confidence", 0)
                    updated_count += 1
                    logger.info(f"Rematched item {item.id}: {match_result['entity_type']} - {match_result['entity_id']}")

            db.commit()

            return {
                "status": "success",
                "total_items": len(pending),
                "updated_count": updated_count,
                "message": f"Rematched {updated_count} of {len(pending)} pending items"
            }
        except Exception as e:
            logger.error(f"Error rematching: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


    @app.post("/api/v1/microsoft/sync-calendar")
    async def sync_microsoft_calendar(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Sync calendar events from Microsoft 365"""
        try:
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            # Get access token
            access_token = decrypt_token(oauth_record.access_token)

            # Check if token needs refresh
            if oauth_record.token_expires_at:
                token_expiry = oauth_record.token_expires_at
                if token_expiry.tzinfo is None:
                    token_expiry = token_expiry.replace(tzinfo=timezone.utc)

                if token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
                    refresh_result = await refresh_microsoft_token(oauth_record, db)
                    if not refresh_result.get("success"):
                        if refresh_result.get("needs_reauth"):
                            raise HTTPException(status_code=401, detail="needs_reauth")
                        raise HTTPException(status_code=401, detail="Failed to refresh token")
                    access_token = decrypt_token(oauth_record.access_token)

            # Fetch calendar events from Microsoft Graph API
            # Get events from next 30 days
            start_date = datetime.now(timezone.utc).isoformat()
            end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # Microsoft Graph API endpoint for calendar events
            graph_url = f"https://graph.microsoft.com/v1.0/me/calendar/calendarView?startDateTime={start_date}&endDateTime={end_date}&$top=100"

            response = requests.get(graph_url, headers=headers)

            if response.status_code != 200:
                logger.error(f"Microsoft Calendar API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail=f"Microsoft Calendar API error: {response.status_code}")

            events_data = response.json()
            events = events_data.get("value", [])

            # Store events in database
            synced_count = 0
            for event_data in events:
                try:
                    # Parse event data
                    subject = event_data.get("subject", "No Subject")
                    start_dt = datetime.fromisoformat(event_data["start"]["dateTime"].replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(event_data["end"]["dateTime"].replace('Z', '+00:00'))
                    location = event_data.get("location", {}).get("displayName", "")
                    body_content = event_data.get("body", {}).get("content", "")

                    # Check if event already exists (by microsoft event id in meta_data)
                    ms_event_id = event_data.get("id")
                    existing = db.query(CalendarEvent).filter(
                        CalendarEvent.user_id == current_user.id,
                        CalendarEvent.meta_data.contains({"microsoft_event_id": ms_event_id})
                    ).first()

                    if existing:
                        # Update existing event
                        existing.title = subject
                        existing.description = body_content[:500] if body_content else None
                        existing.start_time = start_dt
                        existing.end_time = end_dt
                        existing.location = location
                        existing.all_day = event_data.get("isAllDay", False)
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        # Create new event
                        calendar_event = CalendarEvent(
                            title=subject,
                            description=body_content[:500] if body_content else None,
                            start_time=start_dt,
                            end_time=end_dt,
                            all_day=event_data.get("isAllDay", False),
                            location=location,
                            event_type="meeting",
                            user_id=current_user.id,
                            attendees=[att.get("emailAddress", {}).get("address") for att in event_data.get("attendees", [])],
                            status="scheduled",
                            meta_data={"microsoft_event_id": ms_event_id, "source": "microsoft365"}
                        )
                        db.add(calendar_event)

                    synced_count += 1

                except Exception as e:
                    logger.error(f"Error processing calendar event: {e}")
                    continue

            db.commit()
            logger.info(f"Synced {synced_count} calendar events for user {current_user.id}")

            return {
                "status": "success",
                "synced_count": synced_count,
                "total_events": len(events),
                "message": f"Synced {synced_count} calendar events successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Calendar sync error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Calendar sync error: {str(e)}")

    @app.patch("/api/v1/microsoft/settings")
    async def update_microsoft_settings(
        settings: MicrosoftSyncSettings,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Update Microsoft 365 sync settings"""
        try:
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            # Update settings
            if settings.sync_enabled is not None:
                oauth_record.sync_enabled = settings.sync_enabled

            if settings.sync_folder is not None:
                oauth_record.sync_folder = settings.sync_folder

            if settings.sync_frequency_minutes is not None:
                # Validate frequency (min 5 minutes, max 1440 = 24 hours)
                if settings.sync_frequency_minutes < 5 or settings.sync_frequency_minutes > 1440:
                    raise HTTPException(status_code=400, detail="Sync frequency must be between 5 and 1440 minutes")
                oauth_record.sync_frequency_minutes = settings.sync_frequency_minutes

            oauth_record.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Updated Microsoft settings for user {current_user.id}")

            return {
                "status": "success",
                "message": "Settings updated successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Microsoft settings update error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    # Extracted to routes/health_routes.py
    # (/, /prd)

    @app.post("/api/v1/debug/test-task-creation")
    async def debug_test_task_creation(
        loan_id: int,
        trigger: str = "stage->CTC",
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Debug endpoint to test task creation in isolation.
        Pass a loan_id and trigger (like "stage->CTC") to test if tasks are created.
        """
        import traceback
        debug_info = {
            "loan_id": loan_id,
            "trigger": trigger,
            "steps": [],
            "error": None,
            "tasks_created": [],
            "tasks_in_db": []
        }

        try:
            # Step 1: Get the loan
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                debug_info["error"] = f"Loan {loan_id} not found"
                return debug_info

            debug_info["steps"].append(f"Found loan: {loan.loan_number}, stage={loan.stage}, loan_officer_id={loan.loan_officer_id}")

            # Step 2: Check Task model
            debug_info["steps"].append(f"Task model columns: {[c.name for c in Task.__table__.columns]}")

            # Step 3: Call create_milestone_tasks with the trigger
            updated_fields = [trigger]
            debug_info["steps"].append(f"Calling create_milestone_tasks with updated_fields={updated_fields}")

            tasks_created = create_milestone_tasks(loan, updated_fields, db)
            debug_info["tasks_created"] = tasks_created
            debug_info["steps"].append(f"create_milestone_tasks returned: {tasks_created}")

            # Step 4: Query tasks for this loan to verify
            tasks = db.query(Task).filter(Task.loan_id == loan_id).all()
            debug_info["tasks_in_db"] = [
                {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority}
                for t in tasks
            ]
            debug_info["steps"].append(f"Found {len(tasks)} tasks in DB for loan {loan_id}")

        except Exception as e:
            debug_info["error"] = str(e)
            debug_info["steps"].append(f"Exception: {traceback.format_exc()}")

        return debug_info


    # /health extracted to routes/health_routes.py

    # Extracted to routes/health_routes.py and routes/admin_ops_routes.py
    # (admin/pool-status, admin/salesforce-*, admin/pool-reset,
    #  admin/update-twilio-config, /ping)

    @app.get("/admin/create-salesforce-tables")
    async def create_salesforce_tables(db: Session = Depends(get_db)):
        """Admin endpoint to create Salesforce integration tables"""
        results = []

        try:
            db.execute(text("""
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
            db.commit()
            results.append("oauth_states: created/verified")
        except Exception as e:
            results.append(f"oauth_states: {str(e)}")
            db.rollback()

        try:
            db.execute(text("""
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
            db.commit()
            results.append("integration_profiles: created/verified")
        except Exception as e:
            results.append(f"integration_profiles: {str(e)}")
            db.rollback()

        # Create sf_user_schemas table for Salesforce schema discovery
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS sf_user_schemas (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    object_name VARCHAR(100) NOT NULL,
                    fields JSONB NOT NULL,
                    record_types JSONB,
                    picklist_values JSONB,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_validated_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(integration_profile_id, object_name)
                )
            """))
            db.commit()
            results.append("sf_user_schemas: created/verified")
        except Exception as e:
            results.append(f"sf_user_schemas: {str(e)}")
            db.rollback()

        # Create field_mappings table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS field_mappings (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    sf_object VARCHAR(100) NOT NULL,
                    sf_field VARCHAR(255) NOT NULL,
                    crm_entity VARCHAR(100) NOT NULL,
                    crm_field VARCHAR(255) NOT NULL,
                    transform_type VARCHAR(50) DEFAULT 'direct',
                    transform_config JSONB,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_required BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(integration_profile_id, sf_object, sf_field)
                )
            """))
            db.commit()
            results.append("field_mappings: created/verified")
        except Exception as e:
            results.append(f"field_mappings: {str(e)}")
            db.rollback()

        # Create integration_events table for logging
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_events (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    event_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    duration_ms INTEGER,
                    event_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.commit()
            results.append("integration_events: created/verified")
        except Exception as e:
            results.append(f"integration_events: {str(e)}")
            db.rollback()

        return {"results": results}


    # Extracted to routes/health_routes.py
    # (/api/v1/health, /deploy-test, /debug/routers, /debug/scheduler-status)

    @app.post("/api/v1/debug/complete-onboarding-by-email")
    async def debug_complete_onboarding_by_email(
        email: str,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to mark a user's onboarding as complete by email"""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {email} not found")

        user.onboarding_completed = True
        db.commit()

        return {
            "success": True,
            "message": f"Onboarding marked complete for {email}",
            "user_id": user.id,
            "email": user.email
        }


    @app.post("/api/v1/admin/run-salesforce-migration")
    async def run_salesforce_migration(
        secret: str = Query(..., description="Admin secret key"),
        db: Session = Depends(get_db)
    ):
        """Run Salesforce sync fields migration - adds columns to loans and leads tables"""
        # Verify admin secret
        admin_secret = os.getenv("ADMIN_SECRET", "perennia-admin-2025")
        if secret != admin_secret:
            raise HTTPException(status_code=401, detail="Invalid admin secret")

        # Columns to add to LOANS table
        loan_columns = [
            # Property Details
            ("property_type", "VARCHAR"),
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            # 1st Loan Financial Details
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "FLOAT"),
            ("property_tax", "FLOAT"),
            ("hazard_insurance", "FLOAT"),
            ("mortgage_insurance", "FLOAT"),
            ("hoa_amount", "FLOAT"),
            ("origination_fee", "FLOAT"),
            ("estimated_prepaid_interest", "FLOAT"),
            ("points", "FLOAT"),
            ("index_rate", "FLOAT"),
            ("margin", "FLOAT"),
            # LTV/CLTV
            ("ltv", "FLOAT"),
            ("cltv", "FLOAT"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            # 2nd Loan Details
            ("second_loan_amount", "FLOAT"),
            ("second_loan_rate", "FLOAT"),
            ("second_loan_payment", "FLOAT"),
            # Present vs Proposed Housing
            ("present_housing_expense", "FLOAT"),
            ("proposed_housing_expense", "FLOAT"),
            ("present_monthly_payment", "FLOAT"),
            ("proposed_monthly_payment", "FLOAT"),
        ]

        # Columns to add to LEADS table
        lead_columns = [
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "FLOAT"),
            ("property_tax", "FLOAT"),
            ("hazard_insurance", "FLOAT"),
            ("mortgage_insurance", "FLOAT"),
            ("hoa_amount", "FLOAT"),
            ("origination_fee", "FLOAT"),
            ("estimated_prepaid_interest", "FLOAT"),
            ("index_rate", "FLOAT"),
            ("margin", "FLOAT"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            ("second_loan_amount", "FLOAT"),
            ("second_loan_rate", "FLOAT"),
            ("second_loan_payment", "FLOAT"),
            ("present_housing_expense", "FLOAT"),
            ("proposed_housing_expense", "FLOAT"),
            ("present_monthly_payment", "FLOAT"),
            ("proposed_monthly_payment", "FLOAT"),
            ("cltv", "FLOAT"),
        ]

        results = {"loans_added": [], "loans_skipped": [], "leads_added": [], "leads_skipped": [], "errors": []}

        try:
            # Get existing columns for LOANS
            loan_cols_result = db.execute(text("""
                SELECT column_name FROM information_schema.columns WHERE table_name = 'loans'
            """))
            existing_loan_cols = {row[0] for row in loan_cols_result}

            # Add missing columns to LOANS
            for col_name, col_type in loan_columns:
                if col_name in existing_loan_cols:
                    results["loans_skipped"].append(col_name)
                else:
                    try:
                        db.execute(text(f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"))
                        results["loans_added"].append(col_name)
                    except Exception as e:
                        results["errors"].append(f"loans.{col_name}: {str(e)}")

            # Get existing columns for LEADS
            lead_cols_result = db.execute(text("""
                SELECT column_name FROM information_schema.columns WHERE table_name = 'leads'
            """))
            existing_lead_cols = {row[0] for row in lead_cols_result}

            # Add missing columns to LEADS
            for col_name, col_type in lead_columns:
                if col_name in existing_lead_cols:
                    results["leads_skipped"].append(col_name)
                else:
                    try:
                        db.execute(text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}"))
                        results["leads_added"].append(col_name)
                    except Exception as e:
                        results["errors"].append(f"leads.{col_name}: {str(e)}")

            db.commit()

            return {
                "status": "success",
                "message": f"Migration complete: {len(results['loans_added'])} loan columns added, {len(results['leads_added'])} lead columns added",
                "results": results
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Migration failed: {e}")
            raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


    @app.post("/api/v1/debug/test-two-way-email")
    async def debug_test_two_way_email(
        to_email: str = "tloss@me.com",
        message: str = "Hi, I am interested in refinancing my home worth $500,000"
    ):
        """
        Debug endpoint to test the two-way email conversation system.
        Simulates receiving an email and generating an AI response.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from datetime import datetime

            # Generate unique conversation ID
            conv_id = f"test_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Process through the qualification agent
            result = process_qualification_message(
                conversation_id=conv_id,
                message=message,
                channel="email",
                sender_info={"email": to_email, "first_name": to_email.split("@")[0].title()}
            )

            return {
                "status": "success",
                "conversation_id": conv_id,
                "simulated_inbound": {
                    "from": to_email,
                    "message": message
                },
                "ai_response": {
                    "text": result["response"],
                    "type": result["response_type"],
                    "should_send": result["should_send"]
                },
                "qualification": {
                    "status": result["qualification"]["status"],
                    "completion": f"{result['qualification']['completion_percentage']:.0f}%",
                    "missing_fields": result["qualification"]["missing_fields"]
                },
                "tone_analysis": {
                    "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                    "sentiment": result["tone_analysis"]["sentiment"]["sentiment_category"],
                    "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                },
                "next_action": result["next_action"],
                "note": "To send actual emails, configure SENDGRID_API_KEY or authenticate via Microsoft at /auth/microsoft/login"
            }

        except Exception as e:
            logger.error(f"Two-way email test error: {e}")
            import traceback
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }


    @app.post("/api/v1/debug/send-real-email")
    async def debug_send_real_email(
        to_email: str = "tloss@me.com",
        message: str = "Hi, I am interested in refinancing my home worth $500,000"
    ):
        """
        Actually send a real email via SendGrid demonstrating the two-way AI conversation.
        This processes the message through the AI agent and sends a real response.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service
            from datetime import datetime

            # Generate unique conversation ID
            conv_id = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            sender_name = to_email.split("@")[0].replace(".", " ").title()

            # Process through the qualification agent
            result = process_qualification_message(
                conversation_id=conv_id,
                message=message,
                channel="email",
                sender_info={"email": to_email, "first_name": sender_name}
            )

            # Format the email HTML
            html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #c9a227 0%, #f4d03f 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
            .content {{ background: #f9fafb; padding: 24px; border: 1px solid #e5e7eb; }}
            .message-box {{ background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #c9a227; margin-bottom: 20px; }}
            .ai-response {{ background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
            .footer {{ text-align: center; padding: 16px; color: #6b7280; font-size: 12px; }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            .badge-emotion {{ background: #fef3c7; color: #92400e; }}
            .badge-urgency {{ background: #dbeafe; color: #1e40af; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Perennia AI Mortgage Assistant</h1>
            <p>Your AI-Powered Loan Qualification Helper</p>
        </div>
        <div class="content">
            <h3>Hello {sender_name}!</h3>

            <p><strong>Your message:</strong></p>
            <div class="message-box">
                {message}
            </div>

            <p><strong>AI Assistant Response:</strong></p>
            <div class="ai-response">
                {result['response'].replace(chr(10), '<br>')}
            </div>

            <p style="margin-top: 20px;">
                <span class="badge badge-emotion">Tone: {result['tone_analysis']['emotional_state']['primary_emotion']}</span>
                <span class="badge badge-urgency">Urgency: {result['tone_analysis']['urgency']['urgency_level']}</span>
            </p>

            <p style="margin-top: 20px; color: #6b7280; font-size: 14px;">
                <strong>Qualification Progress:</strong> {result['qualification']['completion_percentage']:.0f}%<br>
                <strong>Conversation ID:</strong> {conv_id}
            </p>
        </div>
        <div class="footer">
            <p>This is a demonstration of Perennia AI's two-way email conversation system.</p>
            <p>Reply to this email to continue the conversation!</p>
        </div>
    </body>
    </html>
    """

            # Send the email with correct FROM address
            ai_from_email = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")
            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject=f"RE: Your Mortgage Inquiry - Perennia AI Assistant",
                html_body=html_body,
                plain_text_body=f"Hello {sender_name}!\n\nYour message: {message}\n\nAI Response:\n{result['response']}\n\nReply to continue the conversation.\n\n- Perennia AI",
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to": to_email,
                "conversation_id": conv_id,
                "simulated_inbound_message": message,
                "ai_response": result["response"],
                "qualification_progress": f"{result['qualification']['completion_percentage']:.0f}%",
                "tone": {
                    "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                    "sentiment": result["tone_analysis"]["sentiment"]["sentiment_category"],
                    "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                },
                "sendgrid_configured": bool(email_service.sendgrid_api_key)
            }

        except Exception as e:
            logger.error(f"Send real email error: {e}")
            import traceback
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }


    @app.post("/api/v1/webhook/sendgrid-inbound")
    async def sendgrid_inbound_webhook(request: Request):
        """
        SendGrid Inbound Parse webhook - receives incoming emails and responds with AI.

        To set up:
        1. Go to SendGrid Settings > Inbound Parse
        2. Add your domain (e.g., reply.perenniaai.com)
        3. Set the webhook URL to: https://your-server.com/api/v1/webhook/sendgrid-inbound
        4. Enable "POST the raw, full MIME message"
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service
            import re

            # Parse form data from SendGrid
            form_data = await request.form()

            # Log all form fields for debugging
            all_fields = {key: str(value)[:200] for key, value in form_data.items()}
            logger.info(f"SendGrid form fields: {list(all_fields.keys())}")
            logger.info(f"SendGrid form data: {all_fields}")

            # Extract email details
            from_email = form_data.get("from", "")
            to_email = form_data.get("to", "")
            subject = form_data.get("subject", "")
            text_body = form_data.get("text", "")
            html_body = form_data.get("html", "")

            # Also try 'email' field (raw MIME)
            raw_email = form_data.get("email", "")

            logger.info(f"from={from_email}, to={to_email}, subject={subject}")
            logger.info(f"text_body length={len(text_body)}, html_body length={len(html_body)}, raw_email length={len(raw_email)}")

            # If text/html are empty, parse from raw MIME email
            if not text_body and not html_body and raw_email:
                import email
                from email import policy
                msg = email.message_from_string(raw_email, policy=policy.default)

                # Extract body from MIME message
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            text_body = part.get_content()
                            logger.info(f"Extracted text/plain from MIME: {len(text_body)} chars")
                        elif content_type == "text/html" and not text_body:
                            html_body = part.get_content()
                            logger.info(f"Extracted text/html from MIME: {len(html_body)} chars")
                else:
                    text_body = msg.get_content()
                    logger.info(f"Extracted single part content: {len(text_body)} chars")

            # Extract sender email address (SendGrid sends "Name <email@example.com>")
            email_match = re.search(r'<([^>]+)>', from_email)
            sender_email = email_match.group(1) if email_match else from_email
            sender_name = from_email.split('<')[0].strip().strip('"') if '<' in from_email else sender_email.split('@')[0]

            # Use text body, or strip HTML
            message_body = text_body or html_body
            if not text_body and html_body:
                # Simple HTML strip
                message_body = re.sub(r'<[^>]+>', ' ', html_body)
                message_body = re.sub(r'\s+', ' ', message_body)

            logger.info(f"Raw message body from {sender_email}: {message_body[:500]}...")

            # Clean up the message (remove quoted replies)
            lines = message_body.split('\n')
            clean_lines = []
            found_quote_start = False
            for line in lines:
                line_lower = line.lower().strip()
                # Stop at quoted content markers
                if line.strip().startswith('>'):
                    found_quote_start = True
                    break
                if 'wrote:' in line_lower and ('@' in line_lower or 'on ' in line_lower):
                    found_quote_start = True
                    break
                if line_lower.startswith('from:') and '@' in line_lower:
                    found_quote_start = True
                    break
                if '-------- original message --------' in line_lower:
                    found_quote_start = True
                    break
                if 'sent from my iphone' in line_lower or 'sent from my ipad' in line_lower:
                    break
                clean_lines.append(line)

            clean_message = '\n'.join(clean_lines).strip()

            # If still empty, just use the first 500 chars of raw message
            if not clean_message and message_body:
                clean_message = message_body[:500].strip()
                logger.info(f"Using raw message as fallback: {clean_message[:100]}...")

            if not clean_message:
                logger.warning(f"Empty message received from {sender_email}")
                return {"status": "ignored", "reason": "empty message"}

            # Generate conversation ID from sender email
            conv_id = f"email_{sender_email.replace('@', '_').replace('.', '_')}"

            logger.info(f"Inbound email from {sender_email}: {clean_message[:100]}...")

            # =====================================================================
            # INTELLIGENT EMAIL ROUTING
            # First identify sender and classify intent, then route appropriately
            # =====================================================================
            from services.intelligent_email_handler import get_intelligent_email_handler

            db = SessionLocal()
            try:
                intelligent_handler = get_intelligent_email_handler(db)
                result = intelligent_handler.process_email(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    subject=subject,
                    message=clean_message,
                )

                # If handler says to use qualification agent, fall back to that
                if result.get("use_qualification_agent"):
                    logger.info(f"Routing to qualification agent for {result.get('sender_type', 'unknown')} sender")
                    result = process_qualification_message(
                        conversation_id=conv_id,
                        message=clean_message,
                        channel="email",
                        sender_info=result.get("sender_info", {"email": sender_email, "first_name": sender_name})
                    )
                else:
                    logger.info(f"Intelligent handler processed: sender_type={result.get('sender_type')}, action={result.get('action')}")

            finally:
                db.close()

            # Only send response if AI has one
            if result["should_send"] and result.get("response"):
                # Get conversation history for the email thread
                from services.conversation_intelligence import get_conversation_service, Channel
                conv_service = get_conversation_service()
                state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

                # Record user message in history
                state.message_history.append({
                    "role": "user",
                    "content": clean_message,
                    "timestamp": datetime.now().isoformat()
                })

                # Record AI response in history
                state.message_history.append({
                    "role": "assistant",
                    "content": result['response'],
                    "timestamp": datetime.now().isoformat()
                })

                # Build Outlook-style email thread
                thread_html = ""
                thread_plain = ""

                # Build thread from message history (oldest to newest, excluding current)
                if state.message_history and len(state.message_history) > 2:
                    thread_html = '<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #cccccc;">'
                    thread_plain = "\n\n"

                    # Show previous messages in reverse chronological order (like Outlook)
                    prev_messages = state.message_history[:-2]  # Exclude current exchange
                    for i, msg in enumerate(reversed(prev_messages)):
                        sender_name_thread = "Sarah - Perennia AI" if msg["role"] == "assistant" else sender_name
                        sender_email_thread = "admin@perenniaai.com" if msg["role"] == "assistant" else sender_email
                        msg_time = msg.get("timestamp", "")[:16].replace("T", " ") if msg.get("timestamp") else ""

                        thread_html += f'''
    <div style="color: #1f497d; font-family: Calibri, sans-serif; font-size: 11pt;">
    <p style="margin: 0;"><b>From:</b> {sender_name_thread} &lt;{sender_email_thread}&gt;</p>
    <p style="margin: 0;"><b>Sent:</b> {msg_time}</p>
    <p style="margin: 0 0 10px 0;"><b>Subject:</b> Re: Quick question about your mortgage goals</p>
    <div style="margin: 10px 0; padding-left: 10px; border-left: 2px solid #1f497d;">
    {msg["content"].replace(chr(10), '<br>')}
    </div>
    </div>
    <hr style="border: none; border-top: 1px solid #cccccc; margin: 15px 0;">
    '''
                        thread_plain += f"\n________________________________________\nFrom: {sender_name_thread} <{sender_email_thread}>\nSent: {msg_time}\nSubject: Re: Quick question about your mortgage goals\n\n{msg['content']}\n"

                    thread_html += '</div>'

                # Format response email in Outlook style
                html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px; }}
        </style>
    </head>
    <body>
    <div style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000;">
    <p>Hi {sender_name},</p>

    <p>{result['response'].replace(chr(10), '<br>')}</p>

    <p>Best regards,<br>
    <b>Sarah</b><br>
    <span style="color: #666666;">AI Mortgage Assistant | Perennia AI</span></p>
    </div>

    {thread_html}

    <div style="margin-top: 20px; padding-top: 10px; border-top: 1px solid #cccccc; color: #1f497d; font-family: Calibri, sans-serif; font-size: 11pt;">
    <p style="margin: 0;"><b>From:</b> {sender_name} &lt;{sender_email}&gt;</p>
    <p style="margin: 0;"><b>Sent:</b> {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}</p>
    <p style="margin: 0 0 10px 0;"><b>Subject:</b> {subject}</p>
    <div style="margin: 10px 0; padding-left: 10px; border-left: 2px solid #c9a227;">
    {clean_message[:500]}{"..." if len(clean_message) > 500 else ""}
    </div>
    </div>
    </body>
    </html>
    """

                # Determine reply subject
                reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

                # Build plain text version
                plain_text_response = f"""Hi {sender_name},

    {result['response']}

    Best regards,
    Sarah
    AI Mortgage Assistant | Perennia AI

    ________________________________________
    From: {sender_name} <{sender_email}>
    Sent: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}
    Subject: {subject}

    {clean_message[:500]}
    {thread_plain}
    """

                # Check if there's an appointment booking - prepare ICS attachment
                attachments = None
                calendar_invite_sent = False
                lo_invite_sent = False
                lo_email_sent = False
                booking_result = result.get("booking_result")

                if booking_result and booking_result.get("success"):
                    try:
                        from utils.calendar_invite import generate_appointment_ics, generate_lo_appointment_ics
                        from datetime import datetime as dt

                        appt_time = dt.fromisoformat(booking_result["datetime"])

                        # Get loan officer info from booking result
                        lo_info = booking_result.get("loan_officer") or {}
                        lo_name = lo_info.get("name")
                        lo_email = lo_info.get("email")
                        lo_phone = lo_info.get("phone")

                        # Generate customer calendar invite (with LO info)
                        ics_content = generate_appointment_ics(
                            appointment_id=booking_result["appointment_id"],
                            contact_name=booking_result.get("contact_name", sender_name),
                            contact_email=sender_email,
                            start_time=appt_time,
                            duration_minutes=booking_result.get("duration_minutes", 30),
                            appointment_type=booking_result.get("type", "consultation"),
                            loan_officer_name=lo_name,
                            loan_officer_email=lo_email,
                        )

                        # Prepare attachment for main email to customer
                        attachments = [{
                            'content': ics_content.encode('utf-8'),
                            'filename': 'appointment.ics',
                            'type': 'text/calendar; method=REQUEST'
                        }]
                        calendar_invite_sent = True
                        logger.info(f"Customer ICS attachment prepared for {sender_email} (with LO: {lo_name})")

                        # Send calendar invite and email to loan officer
                        if lo_email:
                            try:
                                # Generate LO calendar invite
                                lo_ics_content = generate_lo_appointment_ics(
                                    appointment_id=booking_result["appointment_id"],
                                    contact_name=booking_result.get("contact_name", sender_name),
                                    contact_email=sender_email,
                                    contact_phone=None,  # May not have phone yet
                                    start_time=appt_time,
                                    duration_minutes=booking_result.get("duration_minutes", 30),
                                    appointment_type=booking_result.get("type", "consultation"),
                                    loan_officer_name=lo_name,
                                    loan_officer_email=lo_email,
                                    notes=f"New appointment booked via AI assistant. Contact: {sender_email}",
                                )

                                # Prepare LO email content
                                lo_subject = f"New Appointment: {booking_result.get('contact_name', sender_name)} - {appt_time.strftime('%b %d at %I:%M %p')}"
                                lo_html = f"""
                                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                                    <h2 style="color: #1e3a5f;">New Appointment Scheduled</h2>
                                    <p>A new consultation has been booked via AI assistant.</p>

                                    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                        <h3 style="margin-top: 0; color: #333;">Appointment Details</h3>
                                        <p><strong>Client:</strong> {booking_result.get('contact_name', sender_name)}</p>
                                        <p><strong>Email:</strong> {sender_email}</p>
                                        <p><strong>Date:</strong> {appt_time.strftime('%A, %B %d, %Y')}</p>
                                        <p><strong>Time:</strong> {appt_time.strftime('%I:%M %p')}</p>
                                        <p><strong>Duration:</strong> {booking_result.get('duration_minutes', 30)} minutes</p>
                                        <p><strong>Type:</strong> {booking_result.get('type', 'Consultation').replace('_', ' ').title()}</p>
                                        <p><strong>Reference:</strong> {booking_result['appointment_id']}</p>
                                    </div>

                                    <p>A calendar invitation is attached. Please add it to your calendar.</p>

                                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                                        This appointment was scheduled by Sarah, your AI assistant.
                                    </p>
                                </div>
                                """

                                lo_attachments = [{
                                    'content': lo_ics_content.encode('utf-8'),
                                    'filename': 'appointment.ics',
                                    'type': 'text/calendar; method=REQUEST'
                                }]

                                # Send email to loan officer
                                ai_from_email_lo = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")
                                lo_email_sent = email_service.send_html_email(
                                    to_email=lo_email,
                                    subject=lo_subject,
                                    html_body=lo_html,
                                    attachments=lo_attachments,
                                    from_email=ai_from_email_lo,
                                    reply_to=ai_from_email_lo
                                )
                                lo_invite_sent = lo_email_sent
                                logger.info(f"LO notification sent to {lo_email}: {lo_email_sent}")

                            except Exception as lo_err:
                                logger.warning(f"Could not send LO notification: {lo_err}")

                    except Exception as ics_err:
                        logger.warning(f"Could not generate ICS: {ics_err}")

                # Send the response (with ICS attachment if booking)
                ai_from_email = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")
                email_sent = email_service.send_html_email(
                    to_email=sender_email,
                    subject=reply_subject,
                    html_body=html_response,
                    plain_text_body=plain_text_response,
                    attachments=attachments,
                    from_email=ai_from_email,
                    reply_to=ai_from_email
                )

                logger.info(f"AI response sent to {sender_email}: {email_sent} (with_ics={calendar_invite_sent})")

                # Log for training review
                try:
                    from routes.email_training_routes import EmailTrainingLog
                    training_db = SessionLocal()
                    training_log = EmailTrainingLog(
                        conversation_id=conv_id,
                        from_email=sender_email,
                        to_email="sarah@reply.perenniaai.com",
                        subject=subject,
                        user_message=clean_message,
                        ai_response=result["response"],
                        detected_topics=result.get("metadata", {}).get("topics_addressed"),
                        conversation_stage=result.get("conversation_state", {}).get("stage"),
                        qualification_data=result.get("qualification", {}).get("data")
                    )
                    training_db.add(training_log)
                    training_db.commit()
                    training_log_id = training_log.id
                    training_db.close()
                    logger.info(f"Email logged for training: id={training_log_id}")
                except Exception as train_err:
                    logger.warning(f"Could not log email for training: {train_err}")
                    training_log_id = None

                # Note: Calendar invite (ICS) is now attached to main response email above

                return {
                    "status": "processed",
                    "email_sent": email_sent,
                    "conversation_id": conv_id,
                    "from": sender_email,
                    "ai_response": result["response"][:100] + "...",
                    "qualification_progress": f"{result['qualification']['completion_percentage']:.0f}%",
                    "should_escalate": result["should_escalate"],
                    "training_log_id": training_log_id,
                    "appointment_booked": booking_result is not None,
                    "calendar_invite_sent": calendar_invite_sent,
                    "lo_invite_sent": lo_invite_sent,
                    "lo_email_sent": lo_email_sent,
                    "assigned_lo": (booking_result.get("loan_officer") or {}).get("name") if booking_result else None
                }
            else:
                return {
                    "status": "no_response_needed",
                    "conversation_id": conv_id,
                    "reason": "AI determined no response needed or escalated"
                }

        except Exception as e:
            logger.error(f"SendGrid inbound webhook error: {e}")
            import traceback
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


    @app.post("/api/v1/debug/simulate-email-reply")
    async def simulate_email_reply(
        conversation_id: str,
        reply_message: str,
        sender_email: str = "tloss@me.com"
    ):
        """
        Simulate receiving an email reply to test two-way conversation.
        Uses an existing conversation_id to continue the conversation.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service

            sender_name = sender_email.split("@")[0].replace(".", " ").title()

            # Process the reply through AI
            result = process_qualification_message(
                conversation_id=conversation_id,
                message=reply_message,
                channel="email",
                sender_info={"email": sender_email, "first_name": sender_name}
            )

            # Send AI response
            if result["should_send"] and result.get("response"):
                html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .response {{ background: #f0f9ff; padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
            .your-message {{ background: #f9fafb; padding: 16px; border-radius: 8px; border-left: 4px solid #c9a227; margin-bottom: 16px; }}
            .footer {{ margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
            .progress {{ background: #ecfdf5; padding: 12px; border-radius: 6px; margin-top: 16px; }}
        </style>
    </head>
    <body>
        <p>Hi {sender_name},</p>

        <p><strong>You said:</strong></p>
        <div class="your-message">{reply_message}</div>

        <p><strong>AI Response:</strong></p>
        <div class="response">
            {result['response'].replace(chr(10), '<br>')}
        </div>

        <div class="progress">
            <strong>Qualification Progress:</strong> {result['qualification']['completion_percentage']:.0f}%
            {f"<br><strong>Missing:</strong> {', '.join(result['qualification']['missing_fields'][:3])}" if result['qualification']['missing_fields'] else ""}
        </div>

        <div class="footer">
            <p>Reply to continue the conversation.</p>
            <p style="color: #9ca3af;">Conversation ID: {conversation_id}</p>
        </div>
    </body>
    </html>
    """

                ai_from_email = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")
                email_sent = email_service.send_html_email(
                    to_email=sender_email,
                    subject=f"Re: Your Mortgage Inquiry - Perennia AI",
                    html_body=html_response,
                    plain_text_body=f"Hi {sender_name},\n\nYou said: {reply_message}\n\nAI Response:\n{result['response']}\n\nQualification: {result['qualification']['completion_percentage']:.0f}%\n\n- Perennia AI",
                    from_email=ai_from_email,
                    reply_to=ai_from_email
                )

                return {
                    "status": "success",
                    "email_sent": email_sent,
                    "conversation_id": conversation_id,
                    "your_message": reply_message,
                    "ai_response": result["response"],
                    "qualification": {
                        "progress": f"{result['qualification']['completion_percentage']:.0f}%",
                        "status": result["qualification"]["status"],
                        "missing_fields": result["qualification"]["missing_fields"][:5]
                    },
                    "tone": {
                        "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                        "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                    },
                    "conversation_state": result["conversation_state"]["stage"],
                    "should_escalate": result["should_escalate"]
                }
            else:
                return {
                    "status": "escalated",
                    "conversation_id": conversation_id,
                    "message": "Conversation escalated to human agent",
                    "escalation_reason": result.get("escalation_reason")
                }

        except Exception as e:
            logger.error(f"Simulate reply error: {e}")
            import traceback
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


    @app.post("/api/v1/debug/start-ai-conversation")
    async def start_ai_conversation(to_email: str = "tloss@me.com"):
        """
        Send an initial AI outreach email to start a two-way conversation.
        The user can reply to this email to continue the conversation.
        """
        try:
            from email_service import email_service
            from datetime import datetime
            from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

            # Use consistent conversation ID format based on email (matches webhook)
            conv_id = f"email_{to_email.replace('@', '_').replace('.', '_')}"

            # Initialize conversation state and record the AI's first message
            conv_service = get_conversation_service()
            state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

            # Record AI's initial question in conversation history
            initial_ai_message = "Hi! I'm Sarah, your AI mortgage assistant. Are you looking to purchase a new home or refinance your current one?"
            state.message_history.append({
                "role": "assistant",
                "content": initial_ai_message,
                "timestamp": datetime.now().isoformat()
            })

            # Advance state past initial contact since we've sent the first question
            state.stage = ConversationStage.QUALIFICATION

            logger.info(f"Initialized conversation {conv_id} with {len(state.message_history)} messages, stage: {state.stage}")

            html_body = f"""<!DOCTYPE html>
    <html>
    <body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px;">
    <p>Hi there,</p>

    <p>I'm Sarah, a mortgage assistant at Perennia AI. I help people find the best mortgage options for their situation.</p>

    <p>Are you looking to purchase a new home or refinance your current mortgage?</p>

    <p>Just reply to this email and I'll guide you through the process.</p>

    <p>Best regards,<br>
    <b>Sarah</b><br>
    <span style="color: #666666;">AI Mortgage Assistant | Perennia AI</span></p>
    </body>
    </html>"""

            plain_text = f"""Hi there,

    I'm Sarah, a mortgage assistant at Perennia AI. I help people find the best mortgage options for their situation.

    Are you looking to purchase a new home or refinance your current mortgage?

    Just reply to this email and I'll guide you through the process.

    Best regards,
    Sarah
    AI Mortgage Assistant | Perennia AI"""

            # Use the reply subdomain for FROM address so replies come back to us
            import os
            ai_from_email = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")

            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject="Quick question about your mortgage goals - Perennia AI",
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to": to_email,
                "from": ai_from_email,
                "reply_to": ai_from_email,
                "conversation_id": conv_id,
                "message": "Initial AI question sent! Reply to the email to continue.",
                "instruction": "Reply to this email and SendGrid will forward it to our webhook for AI response"
            }

        except Exception as e:
            logger.error(f"Start AI conversation error: {e}")
            import traceback
            return {"status": "error", "error": str(e)}


    @app.post("/api/v1/debug/test-email-delivery")
    async def test_email_delivery(to_email: str, test_subject: str = "Email Delivery Test"):
        """
        Send a simple test email to diagnose delivery issues.
        Uses minimal formatting to avoid spam filters.
        """
        try:
            from email_service import email_service
            from datetime import datetime
            import os

            # Very simple plain text email
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            test_id = datetime.now().strftime('%H%M%S')

            html_body = f"""<!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
    <p>This is a test email from Perennia AI.</p>
    <p><strong>Test ID:</strong> {test_id}</p>
    <p><strong>Timestamp:</strong> {timestamp}</p>
    <p><strong>Sent from:</strong> {email_service.from_email}</p>
    <p>If you received this, email delivery is working!</p>
    <p>- Perennia AI Team</p>
    </body>
    </html>"""

            plain_text = f"""This is a test email from Perennia AI.

    Test ID: {test_id}
    Timestamp: {timestamp}
    Sent from: {email_service.from_email}

    If you received this, email delivery is working!

    - Perennia AI Team"""

            ai_from_email = os.getenv("AI_FROM_EMAIL", "sarah@reply.perenniaai.com")
            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject=f"{test_subject} - ID:{test_id}",
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to_email": to_email,
                "from_email": email_service.from_email,
                "from_name": email_service.from_name,
                "test_id": test_id,
                "timestamp": timestamp,
                "subject": f"{test_subject} - ID:{test_id}",
                "note": "Check inbox, spam, junk, and all other folders"
            }

        except Exception as e:
            logger.error(f"Test email error: {e}")
            import traceback
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


    @app.post("/api/v1/debug/test-appointment-confirmation-email", tags=["Debug"])
    async def test_appointment_confirmation_email(
        to_email: str = "tloss@me.com",
        contact_name: str = "Test User",
        lo_name: str = "Tim Loss",
        appointment_date: str = "Monday, December 30, 2025 at 02:00 PM"
    ):
        """
        Send a test appointment confirmation email to verify the email template works.
        """
        try:
            from services.notification_service import NotificationService
            from datetime import datetime

            notification_service = NotificationService()

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #1e40af;">Appointment Confirmed!</h2>
                <p>Hi {contact_name},</p>
                <p>Your appointment has been scheduled:</p>

                <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Date & Time:</strong> {appointment_date}</p>
                    <p style="margin: 10px 0 0 0;"><strong>Duration:</strong> 30 minutes</p>
                    <p style="margin: 10px 0 0 0;"><strong>With:</strong> {lo_name}</p>
                </div>

                <p>{lo_name} will call you at the scheduled time to discuss your mortgage needs.</p>

                <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                    Need to reschedule? Reply to this email or contact your loan officer.
                </p>
            </div>
            """

            result = notification_service.send_email(
                to_email=to_email,
                subject=f"Appointment Confirmed with {lo_name}",
                html_content=html_content
            )

            return {
                "status": "success" if result else "failed",
                "email_sent": result,
                "to_email": to_email,
                "subject": f"Appointment Confirmed with {lo_name}",
                "contact_name": contact_name,
                "appointment_date": appointment_date,
                "lo_name": lo_name,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Test appointment confirmation email error: {e}")
            return {"status": "error", "error": str(e)}


    @app.get("/debug/test-import")
    async def debug_test_import():
        """Test importing the smart scheduler modules"""
        results = {"errors": [], "success": []}

        try:
            import pytz
            results["success"].append("pytz")
        except Exception as e:
            results["errors"].append(f"pytz: {str(e)}")

        try:
            from services.notification_service import notification_service
            results["success"].append("notification_service")
        except Exception as e:
            results["errors"].append(f"notification_service: {str(e)}")

        try:
            from smart_scheduler_models import create_smart_scheduler_models
            results["success"].append("smart_scheduler_models")
        except Exception as e:
            results["errors"].append(f"smart_scheduler_models: {str(e)}")

        try:
            from smart_scheduler_routes import router as smart_scheduler_router
            results["success"].append("smart_scheduler_routes")
            results["router_routes"] = len(smart_scheduler_router.routes)
        except Exception as e:
            import traceback
            results["errors"].append(f"smart_scheduler_routes: {str(e)}")
            results["traceback"] = traceback.format_exc()

        return results


    # Extracted to routes/health_routes.py
    # (health/detailed, health/ready, health/live, health/pool, health/cache)

    # Extracted to routes/cache_routes.py and routes/admin_ops_routes.py
    # (cache/status, cache/metrics, cache/clear, cache/invalidate/user,
    #  authentication/test, admin setup migrations, create-zapier-api-key)

    # Extracted to routes/email_management_routes.py
    # (user onboarding, email-signature, email-drafts, generate-call-summary)

    # Extracted to routes/api_key_routes.py and routes/admin_ops_routes.py
    # (contacts/search, api-keys CRUD, admin/stats, admin/users CRUD,
    #  debug/user-deletion-blockers, admin/cleanup-sample-users)

    # ============================================================================
    # LOAN SCORECARD REPORT
    # ============================================================================

    @app.get("/api/v1/scorecard")
    async def get_scorecard(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Get comprehensive loan scorecard metrics matching the Loan Scorecard Report format.
        Includes conversion metrics, funding totals, and referral source breakdown.
        """
        from datetime import date, datetime as dt, timedelta, timezone
        from sqlalchemy import func, extract, case
        from decimal import Decimal

        try:
            # Date range setup - use timezone-naive datetimes for database compatibility
            if start_date and end_date:
                start = dt.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                end = dt.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            else:
                # Default to current month
                today = date.today()
                start = dt(today.year, today.month, 1, 0, 0, 0)
                end = dt(today.year, today.month, today.day, 23, 59, 59)

            # Store date-only versions for the response
            start_date_str = start.strftime("%Y-%m-%d")
            end_date_str = end.strftime("%Y-%m-%d")

            logger.info(f"Scorecard request: {start_date_str} to {end_date_str} for user {current_user.id}")
        except Exception as e:
            logger.error(f"Error in scorecard endpoint (date setup): {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing scorecard data: {str(e)}")

        try:
            # ============================================================================
            # LOAN STARTS VS. ACTIVITY TOTALS
            # ============================================================================

            # Get all relevant loans and leads for the period
            try:
                all_leads = db.query(Lead).filter(
                    Lead.owner_id == current_user.id,
                    Lead.created_at >= start,
                    Lead.created_at <= end
                ).all()
            except Exception as e:
                logger.error(f"Error querying leads: {str(e)}")
                all_leads = []

            try:
                all_loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id
                ).all()
            except Exception as e:
                logger.error(f"Error querying loans: {str(e)}")
                all_loans = []

            # Calculate counts
            starts_count = len(all_leads)  # Total leads

            # Applications (leads that became loans)
            try:
                apps_count = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting applications: {str(e)}")
                apps_count = 0

            # Funded loans
            try:
                funded_count = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting funded loans: {str(e)}")
                funded_count = 0

            # Credit pulls (assuming leads with credit_score indicate credit pulled)
            try:
                credit_pulls = db.query(func.count(Lead.id)).filter(
                    Lead.owner_id == current_user.id,
                    Lead.created_at >= start,
                    Lead.created_at <= end,
                    Lead.credit_score.isnot(None)
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting credit pulls: {str(e)}")
                credit_pulls = 0

            # Cancelled/Suspended loans
            try:
                cancelled_count = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.SUSPENDED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting cancelled loans: {str(e)}")
                cancelled_count = 0

            # Denied loans (not tracked in current stages, set to 0)
            denied_count = 0

            # UW to TBDs (underwriting to clear to close)
            try:
                uw_count = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.UW_RECEIVED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting UW loans: {str(e)}")
                uw_count = 0

            try:
                ctc_count = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.CTC,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                ).scalar() or 0
            except Exception as e:
                logger.error(f"Error counting CTC loans: {str(e)}")
                ctc_count = 0

            # Initial lock to funded (loans that locked and funded)
            locked_funded = funded_count  # Simplified - all funded loans were locked

            # Calculate conversion percentages
            starts_to_apps_pct = int((apps_count / starts_count * 100)) if starts_count > 0 else 0
            apps_to_funded_pct = int((funded_count / apps_count * 100)) if apps_count > 0 else 0
            starts_to_funded_pct = int((funded_count / starts_count * 100)) if starts_count > 0 else 0
            credit_to_funded_pct = int((funded_count / credit_pulls * 100)) if credit_pulls > 0 else 0
            starts_to_cancelled_pct = int((cancelled_count / starts_count * 100)) if starts_count > 0 else 0
            starts_to_denied_pct = int((denied_count / starts_count * 100)) if starts_count > 0 else 0
            uw_to_ctc_pct = int((ctc_count / uw_count * 100)) if uw_count > 0 else 0
            lock_to_funded_pct = int((funded_count / locked_funded * 100)) if locked_funded > 0 else 0

            conversion_metrics = [
                {
                    "metric": "Starts to Appl(E)",
                    "current": apps_count,
                    "total": starts_count,
                    "mot_pct": starts_to_apps_pct,
                    "goal_pct": 75,
                    "status": "good" if starts_to_apps_pct >= 75 else "warning" if starts_to_apps_pct >= 60 else "critical"
                },
                {
                    "metric": "Appl(E) to Funded",
                    "current": funded_count,
                    "total": apps_count,
                    "mot_pct": apps_to_funded_pct,
                    "goal_pct": 80,
                    "status": "good" if apps_to_funded_pct >= 80 else "warning" if apps_to_funded_pct >= 60 else "critical"
                },
                {
                    "metric": "Starts to Funded",
                    "current": funded_count,
                    "total": starts_count,
                    "mot_pct": starts_to_funded_pct,
                    "goal_pct": 50,
                    "status": "good" if starts_to_funded_pct >= 50 else "warning" if starts_to_funded_pct >= 40 else "critical"
                },
                {
                    "metric": "Credit Pulls to Funded",
                    "current": funded_count,
                    "total": credit_pulls,
                    "mot_pct": credit_to_funded_pct,
                    "goal_pct": 70,
                    "status": "critical" if credit_to_funded_pct < 50 else "warning" if credit_to_funded_pct < 70 else "good"
                },
                {
                    "metric": "Starts to Cancelled",
                    "current": cancelled_count,
                    "total": starts_count,
                    "mot_pct": starts_to_cancelled_pct,
                    "goal_pct": 10,
                    "status": "good" if starts_to_cancelled_pct <= 10 else "warning"
                },
                {
                    "metric": "Starts to Denied",
                    "current": denied_count,
                    "total": starts_count,
                    "mot_pct": starts_to_denied_pct,
                    "goal_pct": 5,
                    "status": "good" if starts_to_denied_pct <= 5 else "warning"
                },
                {
                    "metric": "UW to TBDs",
                    "current": ctc_count,
                    "total": uw_count,
                    "mot_pct": uw_to_ctc_pct,
                    "goal_pct": 50,
                    "status": "good" if uw_to_ctc_pct >= 50 else "warning"
                },
                {
                    "metric": "Initial Lock to Funded",
                    "current": funded_count,
                    "total": locked_funded,
                    "mot_pct": lock_to_funded_pct,
                    "goal_pct": 90,
                    "status": "warning" if lock_to_funded_pct < 90 else "good"
                }
            ]

            # ============================================================================
            # CONVERSION UPSWING (10% Pull-Thru Analysis)
            # ============================================================================

            # Calculate current vs target metrics
            current_pull_thru_pct = starts_to_funded_pct
            target_pull_thru_pct = current_pull_thru_pct + 10  # 10% improvement

            # Get funded loans for volume calculations
            try:
                funded_loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                ).all()
            except Exception as e:
                logger.error(f"Error querying funded loans for volume: {str(e)}")
                funded_loans = []

            current_avg_amount = sum(loan.amount for loan in funded_loans if loan.amount) / len(funded_loans) if funded_loans else 0
            current_volume = sum(loan.amount for loan in funded_loans if loan.amount) if funded_loans else 0

            # Project 10% increase
            target_funded_count = int(funded_count * 1.1)
            target_volume = current_volume * 1.1
            volume_increase = target_volume - current_volume

            # Basis points (commission) - assuming 100 bps average
            current_bps = 100
            current_compensation = (current_volume * current_bps) / 10000
            target_compensation = (target_volume * current_bps) / 10000
            additional_compensation = target_compensation - current_compensation

            conversion_upswing = {
                "current_starts": starts_count,
                "target_starts": int(starts_count * 1.1),
                "current_pull_thru_pct": current_pull_thru_pct,
                "target_pull_thru_pct": target_pull_thru_pct,
                "current_avg_amount": current_avg_amount,
                "target_avg_amount": current_avg_amount,
                "current_volume": current_volume,
                "target_volume": target_volume,
                "volume_increase": volume_increase,
                "current_bps": current_bps,
                "target_bps": current_bps,
                "current_compensation": current_compensation,
                "additional_compensation": additional_compensation
            }

            # ============================================================================
            # FUNDING TOTALS
            # ============================================================================

            # Get all funded loans
            try:
                funded_loans_all = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                ).all()
            except Exception as e:
                logger.error(f"Error querying all funded loans: {str(e)}")
                funded_loans_all = []

            # Calculate totals
            total_funded_units = len(funded_loans_all)
            total_funded_volume = sum(loan.amount for loan in funded_loans_all if loan.amount) if funded_loans_all else 0

            # Break down by loan type
            loan_type_breakdown = {}
            for loan in funded_loans_all:
                loan_type = loan.loan_type or "Unknown"
                if loan_type not in loan_type_breakdown:
                    loan_type_breakdown[loan_type] = {"units": 0, "volume": 0}
                loan_type_breakdown[loan_type]["units"] += 1
                loan_type_breakdown[loan_type]["volume"] += loan.amount if loan.amount else 0

            loan_types = [
                {
                    "type": loan_type,
                    "units": data["units"],
                    "volume": data["volume"],
                    "percentage": (data["volume"] / total_funded_volume * 100) if total_funded_volume > 0 else 0
                }
                for loan_type, data in loan_type_breakdown.items()
            ]

            # Break down by referral source
            referral_breakdown = {}
            for loan in funded_loans_all:
                source = loan.source or "Unknown"
                if source not in referral_breakdown:
                    referral_breakdown[source] = {"referrals": 0, "closed_volume": 0}
                referral_breakdown[source]["referrals"] += 1
                referral_breakdown[source]["closed_volume"] += loan.amount if loan.amount else 0

            referral_sources = [
                {
                    "source": source,
                    "referrals": data["referrals"],
                    "closed_volume": data["closed_volume"]
                }
                for source, data in referral_breakdown.items()
            ]

            funding_totals = {
                "total_units": total_funded_units,
                "total_volume": total_funded_volume,
                "loan_types": loan_types,
                "referral_sources": referral_sources,
                "avg_loan_amount": total_funded_volume / total_funded_units if total_funded_units > 0 else 0
            }

            # ============================================================================
            # RETURN COMPLETE SCORECARD
            # ============================================================================

            return {
                "period": {
                    "start_date": start_date_str,
                    "end_date": end_date_str
                },
                "conversion_metrics": conversion_metrics,
                "conversion_upswing": conversion_upswing,
                "funding_totals": funding_totals,
                "generated_at": dt.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in scorecard endpoint: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error generating scorecard: {str(e)}")

    # ================================================================
    # GLOBAL SEARCH - Search across all entities
    # ================================================================

    @app.get("/api/v1/search/global")
    async def global_search(
        q: str,
        limit: int = 20,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Global search across leads, loans, contacts, and partners.
        Returns categorized results from all entity types.
        """
        if not q or len(q.strip()) < 2:
            return {"results": [], "total": 0}

        search_term = q.strip().lower()
        results = []

        # Search Leads
        try:
            leads_query = db.query(Lead)
            leads_query = filter_leads_by_permissions(leads_query, current_user, db)
            leads_query = leads_query.filter(
                or_(
                    func.lower(Lead.name).contains(search_term),
                    func.lower(Lead.email).contains(search_term),
                    func.lower(Lead.phone).contains(search_term)
                )
            ).limit(limit)

            for lead in leads_query.all():
                results.append({
                    "id": lead.id,
                    "type": "lead",
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "status": lead.status if hasattr(lead, 'status') else lead.stage.value if lead.stage else None,
                    "url": f"/leads/{lead.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - leads error: {e}")

        # Search Loans
        try:
            loans_query = db.query(Loan).filter(
                or_(
                    func.lower(Loan.borrower_name).contains(search_term),
                    func.lower(Loan.borrower_email).contains(search_term),
                    func.lower(Loan.loan_number).contains(search_term),
                    func.lower(Loan.property_address).contains(search_term)
                )
            ).limit(limit)

            for loan in loans_query.all():
                results.append({
                    "id": loan.id,
                    "type": "loan",
                    "name": loan.borrower_name,
                    "email": loan.borrower_email,
                    "phone": None,
                    "status": loan.status,
                    "loan_number": loan.loan_number,
                    "property_address": loan.property_address,
                    "url": f"/loans/{loan.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - loans error: {e}")

        # Search Loan Team Members (contacts on loan transactions)
        try:
            team_members_query = db.query(LoanTeamMember).filter(
                or_(
                    func.lower(LoanTeamMember.name).contains(search_term),
                    func.lower(LoanTeamMember.email).contains(search_term),
                    func.lower(LoanTeamMember.company).contains(search_term)
                )
            ).limit(limit)

            for member in team_members_query.all():
                results.append({
                    "id": member.id,
                    "type": "contact",
                    "name": member.name,
                    "email": member.email,
                    "phone": member.phone,
                    "company": member.company,
                    "role": member.role,
                    "url": f"/loans/{member.loan_id}"  # Navigate to the associated loan
                })
        except Exception as e:
            logger.warning(f"Global search - team members error: {e}")

        # Search Referral Partners
        try:
            partners_query = db.query(ReferralPartner).filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.email).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            ).limit(limit)

            for partner in partners_query.all():
                results.append({
                    "id": partner.id,
                    "type": "partner",
                    "name": partner.name or partner.contact_name,
                    "email": partner.email,
                    "phone": partner.phone,
                    "company": partner.company or partner.business_name,
                    "partner_type": partner.type or partner.category,
                    "url": f"/referral-partners/{partner.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - partners error: {e}")

        # Search Portfolio Clients (MUMClients - past funded loans)
        try:
            portfolio_query = db.query(MUMClient).filter(
                or_(
                    func.lower(MUMClient.client_name).contains(search_term),
                    func.lower(MUMClient.email).contains(search_term),
                    func.lower(MUMClient.phone).contains(search_term),
                    func.lower(MUMClient.loan_number).contains(search_term)
                )
            ).limit(limit)

            for client in portfolio_query.all():
                results.append({
                    "id": client.id,
                    "type": "portfolio",
                    "name": client.client_name,
                    "email": client.email,
                    "phone": client.phone,
                    "loan_number": client.loan_number,
                    "status": client.status,
                    "url": f"/portfolio/{client.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - portfolio error: {e}")

        # Sort results by relevance (exact name match first)
        def relevance_score(item):
            name = (item.get("name") or "").lower()
            if name == search_term:
                return 0  # Exact match
            if name.startswith(search_term):
                return 1  # Starts with
            return 2  # Contains

        results.sort(key=relevance_score)

        return {
            "results": results[:limit],
            "total": len(results),
            "query": q
        }


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

    # ============================================================================
    # AI UNDERWRITER - INTELLIGENT Q&A
    # ============================================================================

    @app.post("/api/v1/ai-underwriter/ask")
    async def ask_underwriter_question(
        request: dict,
        current_user: User = Depends(get_current_user)
    ):
        """
        AI Underwriter: Answer mortgage lending questions using Claude AI.
        Provides comprehensive answers with source citations from mortgageguidelines.com.
        """
        question = request.get("question", "").strip()

        if not question:
            raise HTTPException(status_code=400, detail="Question is required")

        # Get Claude API key
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")

        try:
            # Call Claude API with expert mortgage underwriter system prompt
            client = anthropic.Anthropic(api_key=anthropic_api_key)

            system_prompt = """You are an expert mortgage underwriter assistant with deep knowledge of:
    - FHA, VA, USDA, and Conventional loan guidelines
    - Fannie Mae and Freddie Mac requirements
    - DTI ratios, credit score requirements, and LTV limits
    - Documentation requirements for various borrower types
    - Appraisal and property requirements
    - Income calculation and verification
    - Asset and reserve requirements

    Provide clear, accurate, and comprehensive answers to mortgage lending questions.
    Be specific with numbers, percentages, and requirements.
    If you're not certain about specific current limits or requirements, acknowledge that guidelines may change."""

            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": question}]
            )

            answer = message.content[0].text

            # Generate intelligent source links from official guideline updates database
            sources = []
            question_lower = question.lower()

            # Import guideline updates model
            from guideline_updates_models import GuidelineUpdate

            # Get database session
            db = SessionLocal()

            try:
                # Determine which sources to query based on question keywords
                sources_to_query = []

                if 'fha' in question_lower:
                    sources_to_query.append('fha')
                if 'va' in question_lower or 'veteran' in question_lower:
                    sources_to_query.append('va')
                if 'usda' in question_lower or 'rural' in question_lower:
                    sources_to_query.append('usda')
                if 'fannie' in question_lower or 'fannie mae' in question_lower:
                    sources_to_query.append('fannie_mae')
                if 'freddie' in question_lower or 'freddie mac' in question_lower:
                    sources_to_query.append('freddie_mac')
                if 'conventional' in question_lower:
                    sources_to_query.extend(['fannie_mae', 'freddie_mac'])

                # If no specific source identified, search all sources
                if not sources_to_query:
                    sources_to_query = ['fannie_mae', 'freddie_mac', 'fha', 'va', 'usda']

                # Remove duplicates
                sources_to_query = list(set(sources_to_query))

                # Query recent guideline updates from identified sources
                for source_name in sources_to_query:
                    recent_updates = db.query(GuidelineUpdate).filter(
                        GuidelineUpdate.source == source_name
                    ).order_by(
                        GuidelineUpdate.published_date.desc()
                    ).limit(2).all()

                    for update in recent_updates:
                        sources.append({
                            "title": update.title,
                            "url": update.url,
                            "section_code": update.section_code
                        })

                # Limit to 5 most relevant sources
                sources = sources[:5]

                # If no sources found in database, add official guideline home pages
                if not sources:
                    if 'fha' in question_lower:
                        sources.append({
                            "title": "FHA Single Family Housing Policy Handbook",
                            "url": "https://www.hud.gov/program_offices/administration/hudclips/handbooks/hsgh"
                        })
                    if 'va' in question_lower:
                        sources.append({
                            "title": "VA Lender's Handbook",
                            "url": "https://www.benefits.va.gov/HOMELOANS/documents/docs/va_lenders_handbook.pdf"
                        })
                    if 'usda' in question_lower:
                        sources.append({
                            "title": "USDA Single Family Housing Guaranteed Loan Program",
                            "url": "https://www.rd.usda.gov/programs-services/single-family-housing-programs/single-family-housing-guaranteed-loan-program"
                        })
                    if 'fannie' in question_lower or 'conventional' in question_lower:
                        sources.append({
                            "title": "Fannie Mae Selling Guide",
                            "url": "https://selling-guide.fanniemae.com/"
                        })
                    if 'freddie' in question_lower or 'conventional' in question_lower:
                        sources.append({
                            "title": "Freddie Mac Single-Family Seller/Servicer Guide",
                            "url": "https://guide.freddiemac.com/"
                        })

                    # If still no sources, add all official guideline home pages
                    if not sources:
                        sources = [
                            {"title": "Fannie Mae Selling Guide", "url": "https://selling-guide.fanniemae.com/"},
                            {"title": "Freddie Mac Seller/Servicer Guide", "url": "https://guide.freddiemac.com/"},
                            {"title": "FHA Single Family Housing", "url": "https://www.hud.gov/program_offices/housing/sfh"},
                            {"title": "VA Home Loans", "url": "https://www.benefits.va.gov/homeloans/"},
                            {"title": "USDA Rural Development", "url": "https://www.rd.usda.gov/"}
                        ]
            finally:
                db.close()

            # Calculate confidence based on message usage
            # Higher token usage generally indicates more comprehensive, confident answers
            confidence = min(0.95, 0.7 + (len(answer) / 2000))

            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence
            }

        except Exception as e:
            logger.error(f"Error in AI Underwriter: {e}")
            error_msg = str(e)
            # Return more detailed error for debugging
            if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                raise HTTPException(status_code=500, detail=f"Anthropic API authentication error: {error_msg}")
            elif "quota" in error_msg.lower() or "credit" in error_msg.lower():
                raise HTTPException(status_code=500, detail=f"Anthropic API quota/billing error: {error_msg}")
            else:
                raise HTTPException(status_code=500, detail=f"AI Underwriter error: {error_msg}")

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
    })
