"""
Database Module

Provides database configuration, models, and tenant isolation utilities.

Structure:
    database/
    ├── __init__.py        # This file - exports and configuration
    ├── tenant_mixin.py    # Multi-tenant model mixin
    └── models/            # SQLAlchemy model definitions (future)

Usage:
    from database import Base, SessionLocal, get_db
    from database.tenant_mixin import TenantMixin, TenantSession

    # Create a tenant-aware model
    class Lead(Base, TenantMixin):
        __tablename__ = "leads"
        id = Column(Integer, primary_key=True)
        name = Column(String(255))

    # Query with tenant filtering
    with TenantSession(db, organization_id=1) as tenant_db:
        leads = tenant_db.query(Lead).all()
"""

# Re-export from db.py (renamed from database.py to avoid package conflict)
# This allows: from database import Base, SessionLocal
from db import (
    Base,
    SessionLocal,
    engine,
    get_db,
    get_db_with_tenant,
    get_db_url,
    get_pool_status,
    get_pool_stats,
    # Async additions (Wave-2 pool/async migration)
    async_engine,
    AsyncSessionLocal,
    get_async_db,
)

# Export tenant utilities
from .tenant_mixin import (
    TenantMixin,
    TenantSession,
    tenant_context,
    set_tenant_context,
    clear_tenant_context,
    create_rls_policy,
    register_tenant_validation,
)

# Export enums (extracted from main.py)
from .enums import (
    LeadStage,
    LoanStage,
    RateLockStatus,
    RateLockRecommendation,
    BuyingTimelineCategory,
    BorrowerRiskProfile,
    TaskType,
    ActivityType,
    EmailIntakeMatchStatus,
    AttachmentClassificationStatus,
    DocumentType,
    DocumentCategory,
    InviteStatus,
    PermissionLevel,
    DialerSessionStatus,
    DialerTaskStatus,
    CallOutcome,
    SocialProvider,
    ApplicationStatus,
    ApplicationStep,
    CoachMode,
)

__all__ = [
    # Database core
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "get_db_with_tenant",
    "get_db_url",
    "get_pool_status",
    "get_pool_stats",
    "async_engine",
    "AsyncSessionLocal",
    "get_async_db",
    # Tenant isolation
    "TenantMixin",
    "TenantSession",
    "tenant_context",
    "set_tenant_context",
    "clear_tenant_context",
    "create_rls_policy",
    "register_tenant_validation",
    # Enums - Pipeline
    "LeadStage",
    "LoanStage",
    # Enums - Rate Lock
    "RateLockStatus",
    "RateLockRecommendation",
    "BuyingTimelineCategory",
    "BorrowerRiskProfile",
    # Enums - Tasks & Activities
    "TaskType",
    "ActivityType",
    # Enums - Documents
    "EmailIntakeMatchStatus",
    "AttachmentClassificationStatus",
    "DocumentType",
    "DocumentCategory",
    # Enums - Permissions
    "InviteStatus",
    "PermissionLevel",
    # Enums - Dialer
    "DialerSessionStatus",
    "DialerTaskStatus",
    "CallOutcome",
    # Enums - Borrower Application
    "SocialProvider",
    "ApplicationStatus",
    "ApplicationStep",
    # Enums - AI
    "CoachMode",
]
