"""
White-Label & Multi-Tenant Service

Provides comprehensive multi-tenancy and white-labeling capabilities:
- Tenant isolation and management
- Custom branding (voice, scripts, visual)
- Per-tenant configuration
- Usage tracking and billing
- Enterprise SLA features
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib
import hmac

logger = logging.getLogger(__name__)


class TenantTier(str, Enum):
    """Tenant subscription tiers."""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class TenantStatus(str, Enum):
    """Tenant account status."""
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    PENDING_SETUP = "pending_setup"


class BrandingType(str, Enum):
    """Types of white-label branding."""
    VOICE = "voice"
    SCRIPT = "script"
    VISUAL = "visual"
    EMAIL = "email"
    SMS = "sms"


@dataclass
class TenantLimits:
    """Resource limits for a tenant."""
    max_monthly_calls: int = 1000
    max_concurrent_calls: int = 5
    max_users: int = 10
    max_phone_numbers: int = 3
    max_custom_voices: int = 1
    max_integrations: int = 5
    recording_retention_days: int = 30
    analytics_retention_days: int = 90
    api_rate_limit_per_minute: int = 60

    @classmethod
    def for_tier(cls, tier: TenantTier) -> "TenantLimits":
        """Get default limits for a tier."""
        tier_limits = {
            TenantTier.STARTER: cls(
                max_monthly_calls=500,
                max_concurrent_calls=2,
                max_users=5,
                max_phone_numbers=1,
                max_custom_voices=0,
                max_integrations=2,
                recording_retention_days=14,
                analytics_retention_days=30,
                api_rate_limit_per_minute=30
            ),
            TenantTier.PROFESSIONAL: cls(
                max_monthly_calls=5000,
                max_concurrent_calls=10,
                max_users=25,
                max_phone_numbers=5,
                max_custom_voices=2,
                max_integrations=10,
                recording_retention_days=60,
                analytics_retention_days=180,
                api_rate_limit_per_minute=120
            ),
            TenantTier.ENTERPRISE: cls(
                max_monthly_calls=50000,
                max_concurrent_calls=50,
                max_users=100,
                max_phone_numbers=20,
                max_custom_voices=10,
                max_integrations=50,
                recording_retention_days=365,
                analytics_retention_days=730,
                api_rate_limit_per_minute=600
            ),
            TenantTier.CUSTOM: cls(
                max_monthly_calls=999999,
                max_concurrent_calls=100,
                max_users=500,
                max_phone_numbers=100,
                max_custom_voices=50,
                max_integrations=100,
                recording_retention_days=730,
                analytics_retention_days=1095,
                api_rate_limit_per_minute=1000
            ),
        }
        return tier_limits.get(tier, tier_limits[TenantTier.STARTER])


@dataclass
class BrandingConfig:
    """White-label branding configuration."""
    company_name: str = ""
    company_logo_url: Optional[str] = None
    primary_color: str = "#1976D2"
    secondary_color: str = "#424242"
    accent_color: str = "#FF9800"

    # Voice branding
    default_voice_id: Optional[str] = None
    custom_voice_ids: List[str] = field(default_factory=list)
    greeting_template: str = "Thank you for calling {company_name}. How may I assist you today?"
    hold_music_url: Optional[str] = None

    # Script branding
    script_templates: Dict[str, str] = field(default_factory=dict)
    fallback_messages: Dict[str, str] = field(default_factory=dict)

    # Email branding
    email_from_name: str = ""
    email_from_address: str = ""
    email_footer_html: str = ""
    email_logo_url: Optional[str] = None

    # SMS branding
    sms_sender_id: Optional[str] = None
    sms_signature: str = ""

    # Domain/URL branding
    custom_domain: Optional[str] = None
    subdomain: Optional[str] = None
    favicon_url: Optional[str] = None


@dataclass
class Tenant:
    """Represents a tenant/customer in the multi-tenant system."""
    id: str
    name: str
    slug: str  # URL-friendly identifier
    tier: TenantTier
    status: TenantStatus
    created_at: datetime

    # Contact info
    primary_contact_name: str = ""
    primary_contact_email: str = ""
    primary_contact_phone: str = ""
    billing_email: str = ""

    # Configuration
    limits: TenantLimits = field(default_factory=TenantLimits)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    features: Dict[str, bool] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)

    # SLA
    sla_tier: str = "standard"
    sla_response_time_hours: int = 24
    sla_uptime_percentage: float = 99.5

    # Metadata
    trial_ends_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    api_key_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantUsage:
    """Usage metrics for a tenant."""
    tenant_id: str
    period_start: datetime
    period_end: datetime

    # Call metrics
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_call_minutes: float = 0.0

    # Concurrent usage
    peak_concurrent_calls: int = 0

    # API usage
    api_requests: int = 0
    api_errors: int = 0

    # Storage
    recording_storage_mb: float = 0.0
    document_storage_mb: float = 0.0

    # Feature usage
    sms_sent: int = 0
    emails_sent: int = 0
    escalations: int = 0
    voiceprint_verifications: int = 0


class WhiteLabelMultiTenantService:
    """
    Comprehensive multi-tenant and white-labeling service.

    Features:
    - Full tenant isolation
    - Customizable branding
    - Tier-based feature access
    - Usage tracking and limits
    - Enterprise SLA support
    """

    def __init__(self, db_session=None):
        self.db = db_session

        # In-memory cache for tenant configs (in production, use Redis)
        self._tenant_cache: Dict[str, Tenant] = {}
        self._usage_cache: Dict[str, TenantUsage] = {}

        # Feature flags by tier
        self.tier_features = {
            TenantTier.STARTER: {
                "ai_receptionist": True,
                "basic_analytics": True,
                "email_notifications": True,
                "basic_integrations": True,
                "call_recording": True,
                # Premium features disabled
                "advanced_analytics": False,
                "custom_voice": False,
                "live_escalation": False,
                "voice_biometrics": False,
                "ab_testing": False,
                "api_access": False,
                "white_label": False,
                "sla_support": False,
            },
            TenantTier.PROFESSIONAL: {
                "ai_receptionist": True,
                "basic_analytics": True,
                "advanced_analytics": True,
                "email_notifications": True,
                "sms_notifications": True,
                "basic_integrations": True,
                "advanced_integrations": True,
                "call_recording": True,
                "custom_voice": True,
                "live_escalation": True,
                "ab_testing": True,
                "api_access": True,
                # Enterprise features disabled
                "voice_biometrics": False,
                "white_label": False,
                "sla_support": False,
                "dedicated_support": False,
            },
            TenantTier.ENTERPRISE: {
                "ai_receptionist": True,
                "basic_analytics": True,
                "advanced_analytics": True,
                "predictive_analytics": True,
                "email_notifications": True,
                "sms_notifications": True,
                "basic_integrations": True,
                "advanced_integrations": True,
                "custom_integrations": True,
                "call_recording": True,
                "custom_voice": True,
                "live_escalation": True,
                "voice_biometrics": True,
                "ab_testing": True,
                "ai_learning": True,
                "api_access": True,
                "white_label": True,
                "custom_domain": True,
                "sla_support": True,
                "dedicated_support": True,
                "priority_support": True,
            },
        }

        logger.info("WhiteLabelMultiTenantService initialized")

    # =========================================================================
    # Tenant Management
    # =========================================================================

    def create_tenant(
        self,
        name: str,
        tier: TenantTier,
        primary_contact_email: str,
        primary_contact_name: str = "",
        primary_contact_phone: str = "",
        trial_days: int = 14,
        custom_limits: Optional[Dict] = None,
        initial_branding: Optional[Dict] = None
    ) -> Tuple[bool, Tenant]:
        """
        Create a new tenant account.

        Returns:
            Tuple of (success, tenant)
        """
        try:
            # Generate tenant ID and slug
            import uuid
            tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
            slug = self._generate_slug(name)

            # Check for duplicate slug
            if self._slug_exists(slug):
                slug = f"{slug}-{uuid.uuid4().hex[:4]}"

            # Create tenant with appropriate limits
            limits = TenantLimits.for_tier(tier)
            if custom_limits:
                for key, value in custom_limits.items():
                    if hasattr(limits, key):
                        setattr(limits, key, value)

            # Initialize branding
            branding = BrandingConfig(
                company_name=name,
                greeting_template=f"Thank you for calling {name}. How may I assist you today?"
            )
            if initial_branding:
                for key, value in initial_branding.items():
                    if hasattr(branding, key):
                        setattr(branding, key, value)

            # Get features for tier
            features = self.tier_features.get(tier, self.tier_features[TenantTier.STARTER]).copy()

            # Generate API key
            api_key = self._generate_api_key(tenant_id)
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Create tenant object
            now = datetime.now(timezone.utc)
            tenant = Tenant(
                id=tenant_id,
                name=name,
                slug=slug,
                tier=tier,
                status=TenantStatus.TRIAL if trial_days > 0 else TenantStatus.ACTIVE,
                created_at=now,
                primary_contact_name=primary_contact_name,
                primary_contact_email=primary_contact_email,
                primary_contact_phone=primary_contact_phone,
                billing_email=primary_contact_email,
                limits=limits,
                branding=branding,
                features=features,
                trial_ends_at=now + timedelta(days=trial_days) if trial_days > 0 else None,
                api_key_hash=api_key_hash,
                sla_tier="enterprise" if tier == TenantTier.ENTERPRISE else "standard"
            )

            # Cache tenant
            self._tenant_cache[tenant_id] = tenant

            # Store in database
            if self.db:
                self._store_tenant(tenant)

            logger.info(f"Created tenant: {tenant_id} ({name}) - tier: {tier.value}")

            # Return tenant with the unhashed API key (only returned once)
            tenant_response = tenant
            tenant_response.metadata["api_key"] = api_key  # Only on creation

            return True, tenant_response

        except Exception as e:
            logger.error(f"Failed to create tenant: {e}")
            return False, None

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        # Check cache first
        if tenant_id in self._tenant_cache:
            return self._tenant_cache[tenant_id]

        # Load from database
        if self.db:
            tenant = self._load_tenant(tenant_id)
            if tenant:
                self._tenant_cache[tenant_id] = tenant
            return tenant

        return None

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by URL slug."""
        # Search cache
        for tenant in self._tenant_cache.values():
            if tenant.slug == slug:
                return tenant

        # Search database
        if self.db:
            return self._load_tenant_by_slug(slug)

        return None

    def update_tenant(
        self,
        tenant_id: str,
        updates: Dict[str, Any]
    ) -> Tuple[bool, Optional[Tenant]]:
        """Update tenant configuration."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False, None

        try:
            # Update allowed fields
            allowed_fields = [
                "name", "primary_contact_name", "primary_contact_email",
                "primary_contact_phone", "billing_email", "settings"
            ]

            for field in allowed_fields:
                if field in updates:
                    setattr(tenant, field, updates[field])

            # Update cache
            self._tenant_cache[tenant_id] = tenant

            # Persist to database
            if self.db:
                self._update_tenant(tenant)

            logger.info(f"Updated tenant: {tenant_id}")
            return True, tenant

        except Exception as e:
            logger.error(f"Failed to update tenant {tenant_id}: {e}")
            return False, None

    def upgrade_tenant_tier(
        self,
        tenant_id: str,
        new_tier: TenantTier,
        custom_limits: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Tenant]]:
        """Upgrade tenant to a higher tier."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False, None

        try:
            # Update tier and limits
            tenant.tier = new_tier
            tenant.limits = TenantLimits.for_tier(new_tier)

            if custom_limits:
                for key, value in custom_limits.items():
                    if hasattr(tenant.limits, key):
                        setattr(tenant.limits, key, value)

            # Update features for new tier
            tenant.features = self.tier_features.get(
                new_tier,
                self.tier_features[TenantTier.STARTER]
            ).copy()

            # Update SLA if enterprise
            if new_tier == TenantTier.ENTERPRISE:
                tenant.sla_tier = "enterprise"
                tenant.sla_response_time_hours = 4
                tenant.sla_uptime_percentage = 99.9

            # If upgrading from trial, activate
            if tenant.status == TenantStatus.TRIAL:
                tenant.status = TenantStatus.ACTIVE
                tenant.trial_ends_at = None

            # Update cache and database
            self._tenant_cache[tenant_id] = tenant
            if self.db:
                self._update_tenant(tenant)

            logger.info(f"Upgraded tenant {tenant_id} to tier: {new_tier.value}")
            return True, tenant

        except Exception as e:
            logger.error(f"Failed to upgrade tenant {tenant_id}: {e}")
            return False, None

    def suspend_tenant(self, tenant_id: str, reason: str = "") -> bool:
        """Suspend a tenant account."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False

        tenant.status = TenantStatus.SUSPENDED
        tenant.metadata["suspension_reason"] = reason
        tenant.metadata["suspended_at"] = datetime.now(timezone.utc).isoformat()

        self._tenant_cache[tenant_id] = tenant
        if self.db:
            self._update_tenant(tenant)

        logger.warning(f"Suspended tenant: {tenant_id} - Reason: {reason}")
        return True

    def reactivate_tenant(self, tenant_id: str) -> bool:
        """Reactivate a suspended tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False

        if tenant.status != TenantStatus.SUSPENDED:
            return False

        tenant.status = TenantStatus.ACTIVE
        tenant.metadata.pop("suspension_reason", None)
        tenant.metadata["reactivated_at"] = datetime.now(timezone.utc).isoformat()

        self._tenant_cache[tenant_id] = tenant
        if self.db:
            self._update_tenant(tenant)

        logger.info(f"Reactivated tenant: {tenant_id}")
        return True

    # =========================================================================
    # Branding Management
    # =========================================================================

    def update_branding(
        self,
        tenant_id: str,
        branding_type: BrandingType,
        config: Dict[str, Any]
    ) -> Tuple[bool, Optional[BrandingConfig]]:
        """Update specific branding configuration."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False, None

        # Check if tenant has white-label feature
        if not tenant.features.get("white_label", False):
            # Allow basic branding for all tiers
            if branding_type not in [BrandingType.VOICE]:
                logger.warning(f"Tenant {tenant_id} doesn't have white-label feature")
                # Still allow basic updates

        try:
            branding = tenant.branding

            if branding_type == BrandingType.VOICE:
                if "default_voice_id" in config:
                    branding.default_voice_id = config["default_voice_id"]
                if "greeting_template" in config:
                    branding.greeting_template = config["greeting_template"]
                if "hold_music_url" in config:
                    branding.hold_music_url = config["hold_music_url"]
                if "custom_voice_ids" in config:
                    # Respect custom voice limit
                    max_voices = tenant.limits.max_custom_voices
                    branding.custom_voice_ids = config["custom_voice_ids"][:max_voices]

            elif branding_type == BrandingType.SCRIPT:
                if "script_templates" in config:
                    branding.script_templates.update(config["script_templates"])
                if "fallback_messages" in config:
                    branding.fallback_messages.update(config["fallback_messages"])

            elif branding_type == BrandingType.VISUAL:
                if "company_name" in config:
                    branding.company_name = config["company_name"]
                if "company_logo_url" in config:
                    branding.company_logo_url = config["company_logo_url"]
                if "primary_color" in config:
                    branding.primary_color = config["primary_color"]
                if "secondary_color" in config:
                    branding.secondary_color = config["secondary_color"]
                if "accent_color" in config:
                    branding.accent_color = config["accent_color"]
                if "favicon_url" in config:
                    branding.favicon_url = config["favicon_url"]
                if "custom_domain" in config and tenant.features.get("custom_domain"):
                    branding.custom_domain = config["custom_domain"]
                if "subdomain" in config:
                    branding.subdomain = config["subdomain"]

            elif branding_type == BrandingType.EMAIL:
                if "email_from_name" in config:
                    branding.email_from_name = config["email_from_name"]
                if "email_from_address" in config:
                    branding.email_from_address = config["email_from_address"]
                if "email_footer_html" in config:
                    branding.email_footer_html = config["email_footer_html"]
                if "email_logo_url" in config:
                    branding.email_logo_url = config["email_logo_url"]

            elif branding_type == BrandingType.SMS:
                if "sms_sender_id" in config:
                    branding.sms_sender_id = config["sms_sender_id"]
                if "sms_signature" in config:
                    branding.sms_signature = config["sms_signature"]

            tenant.branding = branding
            self._tenant_cache[tenant_id] = tenant

            if self.db:
                self._update_tenant(tenant)

            logger.info(f"Updated {branding_type.value} branding for tenant: {tenant_id}")
            return True, branding

        except Exception as e:
            logger.error(f"Failed to update branding for {tenant_id}: {e}")
            return False, None

    def get_branding(self, tenant_id: str) -> Optional[BrandingConfig]:
        """Get full branding configuration for a tenant."""
        tenant = self.get_tenant(tenant_id)
        return tenant.branding if tenant else None

    def get_greeting(self, tenant_id: str, context: Dict = None) -> str:
        """Get personalized greeting for a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return "Thank you for calling. How may I assist you?"

        greeting = tenant.branding.greeting_template

        # Substitute variables
        variables = {
            "company_name": tenant.branding.company_name or tenant.name,
            "time_of_day": self._get_time_of_day(),
        }

        if context:
            variables.update(context)

        for key, value in variables.items():
            greeting = greeting.replace(f"{{{key}}}", str(value))

        return greeting

    # =========================================================================
    # Feature & Limit Management
    # =========================================================================

    def check_feature_access(self, tenant_id: str, feature: str) -> bool:
        """Check if tenant has access to a specific feature."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False

        # Check status
        if tenant.status not in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
            return False

        # Check trial expiration
        if tenant.status == TenantStatus.TRIAL:
            if tenant.trial_ends_at and datetime.now(timezone.utc) > tenant.trial_ends_at:
                return False

        return tenant.features.get(feature, False)

    def check_limit(
        self,
        tenant_id: str,
        limit_type: str,
        current_value: int
    ) -> Tuple[bool, int]:
        """
        Check if tenant is within a specific limit.

        Returns:
            Tuple of (within_limit, remaining)
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False, 0

        limit_map = {
            "monthly_calls": tenant.limits.max_monthly_calls,
            "concurrent_calls": tenant.limits.max_concurrent_calls,
            "users": tenant.limits.max_users,
            "phone_numbers": tenant.limits.max_phone_numbers,
            "custom_voices": tenant.limits.max_custom_voices,
            "integrations": tenant.limits.max_integrations,
            "api_rate": tenant.limits.api_rate_limit_per_minute,
        }

        max_value = limit_map.get(limit_type, 0)
        remaining = max_value - current_value
        within_limit = current_value < max_value

        return within_limit, max(0, remaining)

    def get_feature_matrix(self, tenant_id: str) -> Dict[str, Any]:
        """Get complete feature access matrix for a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {}

        return {
            "tenant_id": tenant_id,
            "tier": tenant.tier.value,
            "status": tenant.status.value,
            "features": tenant.features,
            "limits": {
                "max_monthly_calls": tenant.limits.max_monthly_calls,
                "max_concurrent_calls": tenant.limits.max_concurrent_calls,
                "max_users": tenant.limits.max_users,
                "max_phone_numbers": tenant.limits.max_phone_numbers,
                "max_custom_voices": tenant.limits.max_custom_voices,
                "max_integrations": tenant.limits.max_integrations,
                "recording_retention_days": tenant.limits.recording_retention_days,
                "analytics_retention_days": tenant.limits.analytics_retention_days,
                "api_rate_limit_per_minute": tenant.limits.api_rate_limit_per_minute,
            },
            "sla": {
                "tier": tenant.sla_tier,
                "response_time_hours": tenant.sla_response_time_hours,
                "uptime_percentage": tenant.sla_uptime_percentage,
            }
        }

    # =========================================================================
    # Usage Tracking
    # =========================================================================

    def record_usage(
        self,
        tenant_id: str,
        usage_type: str,
        quantity: int = 1,
        metadata: Dict = None
    ) -> bool:
        """Record usage for a tenant."""
        try:
            # Get or create current period usage
            usage = self._get_current_usage(tenant_id)

            # Update appropriate metric
            if usage_type == "call":
                usage.total_calls += quantity
            elif usage_type == "successful_call":
                usage.successful_calls += quantity
            elif usage_type == "failed_call":
                usage.failed_calls += quantity
            elif usage_type == "call_minutes":
                usage.total_call_minutes += quantity
            elif usage_type == "concurrent_call":
                usage.peak_concurrent_calls = max(
                    usage.peak_concurrent_calls,
                    quantity
                )
            elif usage_type == "api_request":
                usage.api_requests += quantity
            elif usage_type == "api_error":
                usage.api_errors += quantity
            elif usage_type == "sms":
                usage.sms_sent += quantity
            elif usage_type == "email":
                usage.emails_sent += quantity
            elif usage_type == "escalation":
                usage.escalations += quantity
            elif usage_type == "voiceprint_verification":
                usage.voiceprint_verifications += quantity
            elif usage_type == "recording_storage_mb":
                usage.recording_storage_mb += quantity
            elif usage_type == "document_storage_mb":
                usage.document_storage_mb += quantity

            # Update cache
            self._usage_cache[tenant_id] = usage

            return True

        except Exception as e:
            logger.error(f"Failed to record usage for {tenant_id}: {e}")
            return False

    def get_usage_summary(
        self,
        tenant_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get usage summary for a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {}

        usage = self._get_current_usage(tenant_id)

        # Calculate percentages of limits
        limits = tenant.limits

        return {
            "tenant_id": tenant_id,
            "period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat(),
            },
            "calls": {
                "total": usage.total_calls,
                "successful": usage.successful_calls,
                "failed": usage.failed_calls,
                "minutes": round(usage.total_call_minutes, 2),
                "limit": limits.max_monthly_calls,
                "usage_percent": round(
                    (usage.total_calls / limits.max_monthly_calls) * 100, 1
                ) if limits.max_monthly_calls > 0 else 0,
            },
            "concurrency": {
                "peak": usage.peak_concurrent_calls,
                "limit": limits.max_concurrent_calls,
            },
            "api": {
                "requests": usage.api_requests,
                "errors": usage.api_errors,
                "error_rate": round(
                    (usage.api_errors / usage.api_requests) * 100, 2
                ) if usage.api_requests > 0 else 0,
            },
            "messaging": {
                "sms_sent": usage.sms_sent,
                "emails_sent": usage.emails_sent,
            },
            "features": {
                "escalations": usage.escalations,
                "voiceprint_verifications": usage.voiceprint_verifications,
            },
            "storage": {
                "recordings_mb": round(usage.recording_storage_mb, 2),
                "documents_mb": round(usage.document_storage_mb, 2),
                "total_mb": round(
                    usage.recording_storage_mb + usage.document_storage_mb, 2
                ),
            }
        }

    def check_usage_limits(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant is approaching or exceeding usage limits."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {}

        usage = self._get_current_usage(tenant_id)
        limits = tenant.limits

        warnings = []
        violations = []

        # Check call limit
        call_percent = (usage.total_calls / limits.max_monthly_calls * 100) if limits.max_monthly_calls > 0 else 0
        if call_percent >= 100:
            violations.append({
                "type": "monthly_calls",
                "current": usage.total_calls,
                "limit": limits.max_monthly_calls,
                "percent": round(call_percent, 1)
            })
        elif call_percent >= 80:
            warnings.append({
                "type": "monthly_calls",
                "current": usage.total_calls,
                "limit": limits.max_monthly_calls,
                "percent": round(call_percent, 1)
            })

        return {
            "tenant_id": tenant_id,
            "warnings": warnings,
            "violations": violations,
            "has_warnings": len(warnings) > 0,
            "has_violations": len(violations) > 0,
        }

    # =========================================================================
    # Multi-Tenant Context
    # =========================================================================

    def get_tenant_context(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get complete tenant context for request processing.
        Used to scope all operations to the tenant.
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {}

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tier": tenant.tier.value,
            "status": tenant.status.value,
            "is_active": tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL],
            "features": tenant.features,
            "limits": {
                "concurrent_calls": tenant.limits.max_concurrent_calls,
                "api_rate_limit": tenant.limits.api_rate_limit_per_minute,
            },
            "branding": {
                "company_name": tenant.branding.company_name,
                "voice_id": tenant.branding.default_voice_id,
                "greeting": tenant.branding.greeting_template,
            },
            "settings": tenant.settings,
        }

    def validate_api_key(self, api_key: str) -> Optional[str]:
        """
        Validate API key and return tenant ID if valid.
        """
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Search cached tenants
        for tenant in self._tenant_cache.values():
            if hmac.compare_digest(tenant.api_key_hash or "", api_key_hash):
                if tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
                    return tenant.id
                return None

        # Search database if not in cache
        if self.db:
            tenant_id = self._find_tenant_by_api_key(api_key_hash)
            if tenant_id:
                tenant = self.get_tenant(tenant_id)
                if tenant and tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
                    return tenant_id

        return None

    def regenerate_api_key(self, tenant_id: str) -> Optional[str]:
        """Regenerate API key for a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None

        new_api_key = self._generate_api_key(tenant_id)
        tenant.api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()

        self._tenant_cache[tenant_id] = tenant
        if self.db:
            self._update_tenant(tenant)

        logger.info(f"Regenerated API key for tenant: {tenant_id}")
        return new_api_key

    # =========================================================================
    # Admin Dashboard
    # =========================================================================

    def get_admin_dashboard(self) -> Dict[str, Any]:
        """Get admin overview of all tenants."""
        all_tenants = list(self._tenant_cache.values())

        # Count by status
        by_status = {}
        for tenant in all_tenants:
            status = tenant.status.value
            by_status[status] = by_status.get(status, 0) + 1

        # Count by tier
        by_tier = {}
        for tenant in all_tenants:
            tier = tenant.tier.value
            by_tier[tier] = by_tier.get(tier, 0) + 1

        # Trials expiring soon
        now = datetime.now(timezone.utc)
        expiring_trials = [
            {
                "id": t.id,
                "name": t.name,
                "expires": t.trial_ends_at.isoformat() if t.trial_ends_at else None,
                "days_remaining": (t.trial_ends_at - now).days if t.trial_ends_at else 0
            }
            for t in all_tenants
            if t.status == TenantStatus.TRIAL
            and t.trial_ends_at
            and t.trial_ends_at < now + timedelta(days=7)
        ]

        # Usage warnings
        usage_warnings = []
        for tenant in all_tenants:
            limits_check = self.check_usage_limits(tenant.id)
            if limits_check.get("has_warnings") or limits_check.get("has_violations"):
                usage_warnings.append({
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "warnings": limits_check.get("warnings", []),
                    "violations": limits_check.get("violations", []),
                })

        return {
            "total_tenants": len(all_tenants),
            "by_status": by_status,
            "by_tier": by_tier,
            "expiring_trials": expiring_trials,
            "usage_warnings": usage_warnings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from name."""
        import re
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')[:50]

    def _slug_exists(self, slug: str) -> bool:
        """Check if slug already exists."""
        for tenant in self._tenant_cache.values():
            if tenant.slug == slug:
                return True
        return False

    def _generate_api_key(self, tenant_id: str) -> str:
        """Generate a new API key."""
        import secrets
        return f"pk_{tenant_id}_{secrets.token_urlsafe(32)}"

    def _get_time_of_day(self) -> str:
        """Get time of day greeting."""
        hour = datetime.now().hour
        if hour < 12:
            return "morning"
        elif hour < 17:
            return "afternoon"
        else:
            return "evening"

    def _get_current_usage(self, tenant_id: str) -> TenantUsage:
        """Get or create current period usage record."""
        if tenant_id in self._usage_cache:
            usage = self._usage_cache[tenant_id]
            # Check if still in current period
            now = datetime.now(timezone.utc)
            if usage.period_start <= now <= usage.period_end:
                return usage

        # Create new period
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = period_start.month + 1 if period_start.month < 12 else 1
        next_year = period_start.year if period_start.month < 12 else period_start.year + 1
        period_end = period_start.replace(month=next_month, year=next_year) - timedelta(seconds=1)

        usage = TenantUsage(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end
        )
        self._usage_cache[tenant_id] = usage
        return usage

    def _store_tenant(self, tenant: Tenant):
        """Store tenant in database."""
        pass  # Implement with actual database

    def _load_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Load tenant from database."""
        pass  # Implement with actual database

    def _load_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Load tenant by slug from database."""
        pass  # Implement with actual database

    def _update_tenant(self, tenant: Tenant):
        """Update tenant in database."""
        pass  # Implement with actual database

    def _find_tenant_by_api_key(self, api_key_hash: str) -> Optional[str]:
        """Find tenant ID by API key hash."""
        pass  # Implement with actual database


# Convenience function to get tenant-scoped service
def get_tenant_service(tenant_id: str, service_class: type, db_session=None):
    """
    Factory function to create tenant-scoped service instances.
    Ensures all operations are isolated to the tenant.
    """
    mt_service = WhiteLabelMultiTenantService(db_session)
    tenant = mt_service.get_tenant(tenant_id)

    if not tenant or tenant.status not in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
        raise ValueError(f"Invalid or inactive tenant: {tenant_id}")

    # Create service with tenant context
    service = service_class(db_session)
    service._tenant_id = tenant_id
    service._tenant_context = mt_service.get_tenant_context(tenant_id)

    return service
