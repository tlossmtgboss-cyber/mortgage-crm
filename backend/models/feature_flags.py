"""
Feature Flags Models - Controls feature visibility across the platform
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum


# Will be imported from main.py's Base
def get_base():
    """Lazy import to avoid circular dependencies"""
    from database import Base
    return Base


class DevelopmentStatus(str, enum.Enum):
    """Feature development status"""
    DEVELOPMENT = "development"  # Hidden from all users
    BETA = "beta"               # Visible with BETA badge
    STABLE = "stable"           # Production ready


class FeatureCategory(str, enum.Enum):
    """Feature categories for grouping"""
    AI_TOOLS = "ai_tools"
    COMMUNICATION = "communication"
    ANALYTICS = "analytics"
    OPERATIONS = "operations"
    ADMINISTRATION = "administration"
    INTEGRATIONS = "integrations"


# Define the model class dynamically to avoid import issues
def create_feature_models(Base):
    """Create feature flag models with the provided Base class"""

    class SystemFeature(Base):
        """
        Master list of all platform features with visibility controls.
        Features with development_status='development' are completely hidden from users.
        """
        __tablename__ = "system_features"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        feature_key = Column(String(100), unique=True, nullable=False, index=True)
        feature_name = Column(String(200), nullable=False)
        description = Column(Text)
        category = Column(String(50), default="operations")
        icon = Column(String(50), default="Settings")
        route_path = Column(String(200))

        # Visibility control - THE KEY FIELD
        development_status = Column(String(20), default="stable")
        is_globally_enabled = Column(Boolean, default=True)

        # Pricing
        is_premium = Column(Boolean, default=False)
        base_price = Column(Float, default=0.0)

        # Sorting and display
        sort_order = Column(Integer, default=0)

        # Metadata
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        def to_dict(self):
            return {
                "id": self.id,
                "feature_key": self.feature_key,
                "feature_name": self.feature_name,
                "description": self.description,
                "category": self.category,
                "icon": self.icon,
                "route_path": self.route_path,
                "development_status": self.development_status,
                "is_globally_enabled": self.is_globally_enabled,
                "is_premium": self.is_premium,
                "base_price": self.base_price,
                "sort_order": self.sort_order,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None
            }


    class CompanyFeatureAccess(Base):
        """
        Tracks which features are enabled for each company/account.
        Only features that are globally available can be enabled here.
        """
        __tablename__ = "company_feature_access"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        company_id = Column(Integer, nullable=False, index=True)
        feature_key = Column(String(100), nullable=False, index=True)

        is_enabled = Column(Boolean, default=False)
        enabled_at = Column(DateTime)
        enabled_by = Column(Integer)  # User ID who enabled

        # Trial tracking
        is_trial = Column(Boolean, default=False)
        trial_start = Column(DateTime)
        trial_end = Column(DateTime)

        # Configuration overrides
        custom_config = Column(JSON)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        def to_dict(self):
            return {
                "id": self.id,
                "company_id": self.company_id,
                "feature_key": self.feature_key,
                "is_enabled": self.is_enabled,
                "enabled_at": self.enabled_at.isoformat() if self.enabled_at else None,
                "is_trial": self.is_trial,
                "trial_start": self.trial_start.isoformat() if self.trial_start else None,
                "trial_end": self.trial_end.isoformat() if self.trial_end else None,
                "custom_config": self.custom_config
            }


    class FeatureAuditLog(Base):
        """
        Audit trail for all feature access changes.
        Important for compliance and troubleshooting.
        """
        __tablename__ = "feature_audit_log"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        feature_key = Column(String(100), nullable=False, index=True)
        company_id = Column(Integer, index=True)
        user_id = Column(Integer)

        action = Column(String(50), nullable=False)  # 'enabled', 'disabled', 'trial_started', etc.
        old_value = Column(JSON)
        new_value = Column(JSON)

        ip_address = Column(String(50))
        user_agent = Column(Text)

        created_at = Column(DateTime, default=datetime.utcnow)

        def to_dict(self):
            return {
                "id": self.id,
                "feature_key": self.feature_key,
                "company_id": self.company_id,
                "user_id": self.user_id,
                "action": self.action,
                "old_value": self.old_value,
                "new_value": self.new_value,
                "created_at": self.created_at.isoformat() if self.created_at else None
            }

    return SystemFeature, CompanyFeatureAccess, FeatureAuditLog


# Default features to seed
DEFAULT_FEATURES = [
    {
        "feature_key": "ai_receptionist",
        "feature_name": "AI Receptionist",
        "description": "Intelligent call handling and scheduling with AI-powered conversations",
        "category": "ai_tools",
        "icon": "Phone",
        "route_path": "/ai-receptionist",
        "development_status": "development",  # HIDDEN - not production ready
        "is_premium": True,
        "base_price": 99.00,
        "sort_order": 1
    },
    {
        "feature_key": "power_dialer",
        "feature_name": "Power Dialer",
        "description": "Advanced auto-dialing system with call recording and analytics",
        "category": "communication",
        "icon": "PhoneCall",
        "route_path": "/power-dialer",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 49.00,
        "sort_order": 2
    },
    {
        "feature_key": "ai_underwriting",
        "feature_name": "AI Underwriting Guidance",
        "description": "AI-powered loan analysis and underwriting recommendations",
        "category": "ai_tools",
        "icon": "FileCheck",
        "route_path": "/ai-underwriter",
        "development_status": "beta",
        "is_premium": True,
        "base_price": 149.00,
        "sort_order": 3
    },
    {
        "feature_key": "partners",
        "feature_name": "Partners",
        "description": "Manage referral partners, real estate agents, and business relationships",
        "category": "operations",
        "icon": "Users",
        "route_path": "/partners",
        "development_status": "stable",
        "is_premium": False,
        "base_price": 0.00,
        "sort_order": 4
    },
    {
        "feature_key": "market",
        "feature_name": "Market",
        "description": "Real-time market data, rate tracking, and competitive analysis",
        "category": "analytics",
        "icon": "TrendingUp",
        "route_path": "/market",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 99.00,
        "sort_order": 5
    },
    {
        "feature_key": "profitability",
        "feature_name": "Profitability",
        "description": "Financial analytics, margin tracking, and profitability insights",
        "category": "analytics",
        "icon": "DollarSign",
        "route_path": "/profitability",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 149.00,
        "sort_order": 6
    },
    {
        "feature_key": "voice_os",
        "feature_name": "Voice OS",
        "description": "Voice commands and AI voice assistant for hands-free operation",
        "category": "ai_tools",
        "icon": "Mic",
        "route_path": "/voice-os",
        "development_status": "beta",
        "is_premium": True,
        "base_price": 79.00,
        "sort_order": 7
    },
    {
        "feature_key": "marketing",
        "feature_name": "Marketing",
        "description": "Email campaigns, drip sequences, and marketing automation",
        "category": "communication",
        "icon": "Mail",
        "route_path": "/marketing",
        "development_status": "beta",
        "is_premium": True,
        "base_price": 89.00,
        "sort_order": 8
    },
    {
        "feature_key": "integrations",
        "feature_name": "Integrations",
        "description": "Connect with LOS systems, CRMs, and third-party services",
        "category": "integrations",
        "icon": "Plug",
        "route_path": "/integrations",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 79.00,
        "sort_order": 9
    },
    {
        "feature_key": "api_keys",
        "feature_name": "API Keys",
        "description": "Generate and manage API keys for custom integrations",
        "category": "integrations",
        "icon": "Key",
        "route_path": "/api-keys",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 199.00,
        "sort_order": 10
    },
    {
        "feature_key": "it_help_desk",
        "feature_name": "IT Help Desk",
        "description": "Submit and track IT support tickets and system issues",
        "category": "administration",
        "icon": "HelpCircle",
        "route_path": "/help-desk",
        "development_status": "stable",
        "is_premium": False,
        "base_price": 0.00,
        "sort_order": 11
    },
    {
        "feature_key": "smart_scheduler",
        "feature_name": "Smart Scheduler",
        "description": "AI-powered appointment scheduling and calendar management",
        "category": "operations",
        "icon": "Calendar",
        "route_path": "/scheduler",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 29.00,
        "sort_order": 12
    },
    {
        "feature_key": "video_meetings",
        "feature_name": "Video Meetings",
        "description": "Built-in video conferencing with recording and transcription",
        "category": "communication",
        "icon": "Video",
        "route_path": "/meetings",
        "development_status": "stable",
        "is_premium": False,
        "base_price": 0.00,
        "sort_order": 13
    },
    {
        "feature_key": "data_management",
        "feature_name": "Data Management",
        "description": "Import, export, and manage your data with advanced tools",
        "category": "administration",
        "icon": "Database",
        "route_path": "/data-management",
        "development_status": "stable",
        "is_premium": True,
        "base_price": 39.00,
        "sort_order": 14
    },
    {
        "feature_key": "master_admin",
        "feature_name": "Master Administrator",
        "description": "Full system administration and user management capabilities",
        "category": "administration",
        "icon": "Shield",
        "route_path": "/admin",
        "development_status": "stable",
        "is_premium": False,
        "base_price": 0.00,
        "sort_order": 15
    }
]
