"""
Smart Docs V2 Feature Flag Service

Granular feature flag control for Smart Docs features, integrating with the
platform-level FeatureTier system (feature_tiers.py) and the per-org feature
access model (CompanyFeatureAccess).

Provides:
- Granular Smart Docs feature flags with tier-based defaults
- Per-org overrides (enable enterprise features for trial orgs, disable for orgs with issues)
- In-memory cache with 5-minute TTL to minimize DB queries
- Percentage-based rollout for gradual feature launches
- Global kill switches for emergency disable
- Usage tracking for upsell analytics and gate denial logging
- FastAPI decorator for endpoint-level feature gating

Usage:
    from services.smart_docs.feature_flag_service import (
        SmartDocsFeatureFlagService,
        require_smart_docs_feature,
        get_feature_flag_service,
    )

    # In a route handler:
    @router.post("/api/smart-docs/income/calculate")
    @require_smart_docs_feature("smart_docs.income_calculation")
    async def calculate_income(...):
        ...

    # Programmatic check:
    service = get_feature_flag_service(db)
    if await service.is_feature_enabled(org_id, "smart_docs.fraud_detection"):
        result = await run_fraud_check(...)

    # Admin: set per-org override
    await service.set_feature_override(org_id, "smart_docs.plaid_integration", enabled=True)
"""

from __future__ import annotations

import functools
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from feature_tiers import FeatureTier

logger = logging.getLogger(__name__)


# =============================================================================
# TIER ENUM (extends platform FeatureTier with ENTERPRISE)
# =============================================================================

class SmartDocsTier(str, Enum):
    """Smart Docs feature tiers.

    Extends the platform FeatureTier with an ENTERPRISE level between
    PREMIUM and EXPERIMENTAL. The hierarchy for access checks is:

        CORE (0) < PREMIUM (1) < ENTERPRISE (2) < EXPERIMENTAL (3)

    An org with tier=ENTERPRISE can access CORE, PREMIUM, and ENTERPRISE
    features but not EXPERIMENTAL ones.
    """
    CORE = "CORE"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"
    EXPERIMENTAL = "EXPERIMENTAL"


TIER_HIERARCHY: Dict[SmartDocsTier, int] = {
    SmartDocsTier.CORE: 0,
    SmartDocsTier.PREMIUM: 1,
    SmartDocsTier.ENTERPRISE: 2,
    SmartDocsTier.EXPERIMENTAL: 3,
}

# Map platform FeatureTier to SmartDocsTier for org subscription comparison
_PLATFORM_TIER_MAP: Dict[str, int] = {
    "core": 0,
    "premium": 1,
    "enterprise": 2,
    "experimental": 3,
}


# =============================================================================
# FEATURE DEFINITIONS
# =============================================================================

@dataclass(frozen=True)
class SmartDocsFeatureDef:
    """Definition of a single Smart Docs feature flag."""
    key: str
    tier: SmartDocsTier
    default: bool
    description: str = ""
    rollout_percentage: int = 100  # 0-100, default fully rolled out


SMART_DOCS_FEATURES: Dict[str, SmartDocsFeatureDef] = {}

def _register(key: str, tier: str, default: bool, description: str = "") -> None:
    """Helper to register a feature definition."""
    SMART_DOCS_FEATURES[key] = SmartDocsFeatureDef(
        key=key,
        tier=SmartDocsTier(tier),
        default=default,
        description=description,
    )

# --- Core features (always available when Smart Docs module is enabled) ---
_register("smart_docs.upload", "CORE", True, "Document upload and storage")
_register("smart_docs.classification", "CORE", True, "AI document classification")
_register("smart_docs.needs_list", "CORE", True, "Needs list generation from templates")
_register("smart_docs.document_review", "CORE", True, "Document review pipeline")
_register("smart_docs.basic_search", "CORE", True, "Basic document search")

# --- Premium features ---
_register("smart_docs.income_calculation", "PREMIUM", True, "Income calculation engine")
_register("smart_docs.esignature", "PREMIUM", True, "E-signature envelope service")
_register("smart_docs.bank_analysis", "PREMIUM", True, "Bank statement analysis")
_register("smart_docs.fraud_detection", "PREMIUM", True, "Document fraud detection")
_register("smart_docs.borrower_portal", "PREMIUM", True, "Borrower document portal")
_register("smart_docs.document_intelligence", "PREMIUM", True, "AI document intelligence")
_register("smart_docs.followup_automation", "PREMIUM", True, "Automated follow-up campaigns")

# --- Enterprise features ---
_register("smart_docs.plaid_integration", "ENTERPRISE", False, "Plaid asset verification")
_register("smart_docs.aus_integration", "ENTERPRISE", False, "AUS integration")
_register("smart_docs.mismo_export", "ENTERPRISE", False, "MISMO XML export")
_register("smart_docs.eclosing", "ENTERPRISE", False, "eClosing integration")
_register("smart_docs.irs_transcript", "ENTERPRISE", False, "IRS transcript ordering")
_register("smart_docs.workflow_automation", "ENTERPRISE", False, "Workflow automation engine")
_register("smart_docs.custom_routing", "ENTERPRISE", False, "Custom document routing rules")
_register("smart_docs.approval_chains", "ENTERPRISE", False, "Multi-level approval chains")
_register("smart_docs.sla_enforcement", "ENTERPRISE", False, "SLA enforcement engine")
_register("smart_docs.white_label", "ENTERPRISE", False, "White-label branding")
_register("smart_docs.multi_org", "ENTERPRISE", False, "Multi-organization support")
_register("smart_docs.advanced_reporting", "ENTERPRISE", False, "Advanced analytics/reporting")

# --- Experimental features ---
_register("smart_docs.document_chat", "EXPERIMENTAL", False, "Chat with documents via AI")
_register("smart_docs.ocr_enhancement", "EXPERIMENTAL", False, "Enhanced OCR pipeline")
_register("smart_docs.pdf_forensics", "EXPERIMENTAL", False, "PDF forensic analysis")


# =============================================================================
# CACHE
# =============================================================================

@dataclass
class _CacheEntry:
    """Single cache entry with TTL."""
    value: Any
    expires_at: float  # time.monotonic() based


class _FeatureFlagCache:
    """Thread-safe in-memory cache with per-key TTL.

    Used to avoid hitting the database on every feature check.
    Default TTL is 300 seconds (5 minutes).
    """

    def __init__(self, ttl_seconds: float = 300.0):
        self._ttl = ttl_seconds
        self._store: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._store[key] = _CacheEntry(
                value=value,
                expires_at=time.monotonic() + (ttl if ttl is not None else self._ttl),
            )

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_org(self, org_id: int) -> None:
        """Remove all cached entries for a specific org."""
        prefix = f"org:{org_id}:"
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level cache singleton
_cache = _FeatureFlagCache(ttl_seconds=300.0)

# Global kill switches: set of feature keys that are force-disabled for all orgs.
# Modified via set_global_kill_switch / remove_global_kill_switch.
_global_kill_switches: Set[str] = set()
_kill_switch_lock = threading.Lock()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FeatureCheckResult:
    """Result of a feature flag check."""
    feature_key: str
    enabled: bool
    reason: str  # e.g. "tier_allowed", "override_enabled", "kill_switch", "rollout_excluded"
    org_id: int
    tier_required: str
    org_tier: str


@dataclass
class FeatureUsageRecord:
    """Aggregated feature usage data."""
    feature_key: str
    org_id: int
    access_count: int
    denial_count: int
    first_used: Optional[datetime]
    last_used: Optional[datetime]


@dataclass
class FeatureUsageSummary:
    """Usage summary across features for an org."""
    org_id: int
    period_start: datetime
    period_end: datetime
    records: List[FeatureUsageRecord]
    total_accesses: int
    total_denials: int
    upsell_candidates: List[str]  # features the org tried but was denied


# =============================================================================
# SERVICE
# =============================================================================

class SmartDocsFeatureFlagService:
    """Async service for Smart Docs feature flag management.

    Integrates with:
    - feature_tiers.py (platform-level tier for the "smart_docs" module)
    - CompanyFeatureAccess table (per-org overrides via feature_flags_routes.py)
    - In-memory cache (5-minute TTL)
    - Global kill switches (emergency disable)
    - Percentage-based rollout

    Thread safety: the service itself is stateless except for the module-level
    cache and kill-switch set, both of which are protected by locks.
    """

    def __init__(self, db: Session):
        self._db = db

    # -----------------------------------------------------------------
    # Core API
    # -----------------------------------------------------------------

    async def is_feature_enabled(self, org_id: int, feature_key: str) -> bool:
        """Check whether a feature is enabled for an organization.

        Resolution order:
        1. Unknown feature key -> False
        2. Global kill switch -> False
        3. Cached result -> return cached value
        4. Per-org override in DB -> use override
        5. Percentage-based rollout check -> False if excluded
        6. Tier comparison (org subscription tier vs feature tier) -> bool
        7. Feature default value

        Results are cached for 5 minutes per (org_id, feature_key).
        """
        result = await self._check_feature(org_id, feature_key)
        return result.enabled

    async def check_feature(self, org_id: int, feature_key: str) -> FeatureCheckResult:
        """Like is_feature_enabled but returns the full check result with reason."""
        return await self._check_feature(org_id, feature_key)

    async def get_enabled_features(self, org_id: int) -> List[str]:
        """Return all feature keys that are enabled for the given org.

        Checks every registered Smart Docs feature and returns those that pass
        the feature gate. Results are cached as a batch.
        """
        cache_key = f"org:{org_id}:all_enabled"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        enabled = []
        for feature_key in SMART_DOCS_FEATURES:
            if await self.is_feature_enabled(org_id, feature_key):
                enabled.append(feature_key)

        _cache.set(cache_key, enabled)
        return enabled

    async def get_feature_manifest(self, org_id: int) -> List[Dict[str, Any]]:
        """Return full manifest of all Smart Docs features with enabled status.

        Useful for frontend to render feature availability UI.
        """
        manifest = []
        for key, fdef in SMART_DOCS_FEATURES.items():
            result = await self._check_feature(org_id, key)
            manifest.append({
                "key": key,
                "tier": fdef.tier.value,
                "enabled": result.enabled,
                "reason": result.reason,
                "description": fdef.description,
                "default": fdef.default,
            })
        return manifest

    # -----------------------------------------------------------------
    # Per-org overrides
    # -----------------------------------------------------------------

    async def set_feature_override(
        self,
        org_id: int,
        feature_key: str,
        enabled: bool,
        *,
        is_trial: bool = False,
        trial_days: Optional[int] = None,
        set_by_user_id: Optional[int] = None,
    ) -> None:
        """Set a per-org feature override.

        This writes to the company_feature_access table (same table used by
        feature_flags_routes.py) so that overrides are consistent across systems.

        Args:
            org_id: Organization/company ID.
            feature_key: The smart_docs.* feature key.
            enabled: Whether to enable or disable.
            is_trial: Mark as trial access.
            trial_days: If trial, number of days until expiry.
            set_by_user_id: User who set the override (for audit).
        """
        if feature_key not in SMART_DOCS_FEATURES:
            raise ValueError(f"Unknown Smart Docs feature: {feature_key}")

        now = datetime.now(timezone.utc)

        # Check if override row already exists
        existing = self._db.execute(
            text("""
                SELECT id FROM company_feature_access
                WHERE company_id = :org_id AND feature_key = :feature_key
            """),
            {"org_id": org_id, "feature_key": feature_key},
        ).fetchone()

        if existing:
            update_params: Dict[str, Any] = {
                "org_id": org_id,
                "feature_key": feature_key,
                "is_enabled": enabled,
                "is_trial": is_trial,
                "updated_at": now,
            }
            trial_cols = ""
            if is_trial and trial_days:
                from datetime import timedelta
                update_params["trial_start"] = now
                update_params["trial_end"] = now + timedelta(days=trial_days)
                trial_cols = ", trial_start = :trial_start, trial_end = :trial_end"
            if set_by_user_id:
                update_params["enabled_by"] = set_by_user_id
                trial_cols += ", enabled_by = :enabled_by"
            if enabled:
                update_params["enabled_at"] = now
                trial_cols += ", enabled_at = :enabled_at"

            self._db.execute(
                text(f"""
                    UPDATE company_feature_access
                    SET is_enabled = :is_enabled,
                        is_trial = :is_trial,
                        updated_at = :updated_at
                        {trial_cols}
                    WHERE company_id = :org_id AND feature_key = :feature_key
                """),
                update_params,
            )
        else:
            insert_params: Dict[str, Any] = {
                "org_id": org_id,
                "feature_key": feature_key,
                "is_enabled": enabled,
                "is_trial": is_trial,
                "created_at": now,
                "updated_at": now,
            }
            extra_cols = ""
            extra_vals = ""
            if enabled:
                insert_params["enabled_at"] = now
                extra_cols += ", enabled_at"
                extra_vals += ", :enabled_at"
            if set_by_user_id:
                insert_params["enabled_by"] = set_by_user_id
                extra_cols += ", enabled_by"
                extra_vals += ", :enabled_by"
            if is_trial and trial_days:
                from datetime import timedelta
                insert_params["trial_start"] = now
                insert_params["trial_end"] = now + timedelta(days=trial_days)
                extra_cols += ", trial_start, trial_end"
                extra_vals += ", :trial_start, :trial_end"

            self._db.execute(
                text(f"""
                    INSERT INTO company_feature_access
                        (company_id, feature_key, is_enabled, is_trial, created_at, updated_at{extra_cols})
                    VALUES
                        (:org_id, :feature_key, :is_enabled, :is_trial, :created_at, :updated_at{extra_vals})
                """),
                insert_params,
            )

        self._db.commit()

        # Invalidate cache for this org
        _cache.invalidate_org(org_id)

        # Log the override for audit
        await self._log_usage_event(
            org_id=org_id,
            feature_key=feature_key,
            event_type="override_set",
            metadata={"enabled": enabled, "is_trial": is_trial, "set_by": set_by_user_id},
        )

        logger.info(
            "Smart Docs feature override set: org=%s feature=%s enabled=%s trial=%s",
            org_id, feature_key, enabled, is_trial,
        )

    async def remove_feature_override(self, org_id: int, feature_key: str) -> None:
        """Remove a per-org override, reverting to tier-based defaults."""
        self._db.execute(
            text("""
                DELETE FROM company_feature_access
                WHERE company_id = :org_id AND feature_key = :feature_key
            """),
            {"org_id": org_id, "feature_key": feature_key},
        )
        self._db.commit()
        _cache.invalidate_org(org_id)

    # -----------------------------------------------------------------
    # Global kill switches
    # -----------------------------------------------------------------

    @staticmethod
    def set_global_kill_switch(feature_key: str) -> None:
        """Emergency disable a feature for ALL organizations.

        Takes effect immediately (bypasses cache). Use for incidents where
        a feature is causing data corruption or security issues.
        """
        if feature_key not in SMART_DOCS_FEATURES:
            raise ValueError(f"Unknown Smart Docs feature: {feature_key}")
        with _kill_switch_lock:
            _global_kill_switches.add(feature_key)
        _cache.clear()  # Force all orgs to re-evaluate
        logger.warning("KILL SWITCH ACTIVATED for feature: %s", feature_key)

    @staticmethod
    def remove_global_kill_switch(feature_key: str) -> None:
        """Re-enable a feature after a kill switch."""
        with _kill_switch_lock:
            _global_kill_switches.discard(feature_key)
        _cache.clear()
        logger.warning("KILL SWITCH REMOVED for feature: %s", feature_key)

    @staticmethod
    def get_active_kill_switches() -> List[str]:
        """Return list of currently active kill switches."""
        with _kill_switch_lock:
            return list(_global_kill_switches)

    # -----------------------------------------------------------------
    # Rollout management
    # -----------------------------------------------------------------

    @staticmethod
    def set_rollout_percentage(feature_key: str, percentage: int) -> None:
        """Set the rollout percentage for a feature (0-100).

        When percentage < 100, only a deterministic subset of orgs can access
        the feature. The subset is determined by hashing the org_id with the
        feature key, producing a consistent assignment.
        """
        if feature_key not in SMART_DOCS_FEATURES:
            raise ValueError(f"Unknown Smart Docs feature: {feature_key}")
        if not 0 <= percentage <= 100:
            raise ValueError(f"Percentage must be 0-100, got {percentage}")

        # Replace the feature def with updated rollout_percentage
        old_def = SMART_DOCS_FEATURES[feature_key]
        SMART_DOCS_FEATURES[feature_key] = SmartDocsFeatureDef(
            key=old_def.key,
            tier=old_def.tier,
            default=old_def.default,
            description=old_def.description,
            rollout_percentage=percentage,
        )
        _cache.clear()
        logger.info(
            "Rollout percentage set: feature=%s percentage=%d", feature_key, percentage
        )

    # -----------------------------------------------------------------
    # Usage tracking
    # -----------------------------------------------------------------

    async def track_feature_access(
        self,
        org_id: int,
        feature_key: str,
        *,
        granted: bool,
        user_id: Optional[int] = None,
    ) -> None:
        """Record a feature access attempt for analytics.

        Called automatically by the decorator and is_feature_enabled.
        Tracks both successful accesses and denials for upsell reporting.
        """
        event_type = "access_granted" if granted else "access_denied"
        await self._log_usage_event(
            org_id=org_id,
            feature_key=feature_key,
            event_type=event_type,
            metadata={"user_id": user_id},
        )

    async def get_feature_usage(
        self,
        org_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FeatureUsageSummary:
        """Get feature usage analytics for an organization.

        Queries the feature_usage_events table for access/denial counts
        within the specified date range.
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            from datetime import timedelta
            start_date = end_date - timedelta(days=30)

        rows = self._db.execute(
            text("""
                SELECT
                    feature_key,
                    COUNT(CASE WHEN event_type = 'access_granted' THEN 1 END) as access_count,
                    COUNT(CASE WHEN event_type = 'access_denied' THEN 1 END) as denial_count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used
                FROM smart_docs_feature_usage
                WHERE org_id = :org_id
                    AND created_at >= :start_date
                    AND created_at <= :end_date
                GROUP BY feature_key
                ORDER BY access_count DESC
            """),
            {"org_id": org_id, "start_date": start_date, "end_date": end_date},
        ).fetchall()

        records = []
        total_accesses = 0
        total_denials = 0
        upsell_candidates = []

        for row in rows:
            rec = FeatureUsageRecord(
                feature_key=row[0],
                org_id=org_id,
                access_count=row[1] or 0,
                denial_count=row[2] or 0,
                first_used=row[3],
                last_used=row[4],
            )
            records.append(rec)
            total_accesses += rec.access_count
            total_denials += rec.denial_count

            # Features with denials are upsell candidates
            if rec.denial_count > 0:
                upsell_candidates.append(rec.feature_key)

        return FeatureUsageSummary(
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            records=records,
            total_accesses=total_accesses,
            total_denials=total_denials,
            upsell_candidates=upsell_candidates,
        )

    # -----------------------------------------------------------------
    # Table creation (migration helper)
    # -----------------------------------------------------------------

    async def ensure_usage_table(self) -> None:
        """Create the smart_docs_feature_usage table if it does not exist.

        Safe to call multiple times (uses IF NOT EXISTS).
        """
        self._db.execute(text("""
            CREATE TABLE IF NOT EXISTS smart_docs_feature_usage (
                id SERIAL PRIMARY KEY,
                org_id INTEGER NOT NULL,
                feature_key VARCHAR(100) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT idx_sdf_usage_org_feature UNIQUE (id)
            )
        """))
        self._db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sdf_usage_org_date
            ON smart_docs_feature_usage (org_id, created_at)
        """))
        self._db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sdf_usage_feature
            ON smart_docs_feature_usage (feature_key, event_type)
        """))
        self._db.commit()
        logger.info("smart_docs_feature_usage table ensured")

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    async def _check_feature(self, org_id: int, feature_key: str) -> FeatureCheckResult:
        """Core feature check logic with full resolution chain."""

        # 1. Unknown feature key
        fdef = SMART_DOCS_FEATURES.get(feature_key)
        if fdef is None:
            return FeatureCheckResult(
                feature_key=feature_key,
                enabled=False,
                reason="unknown_feature",
                org_id=org_id,
                tier_required="unknown",
                org_tier="unknown",
            )

        # 2. Global kill switch
        with _kill_switch_lock:
            if feature_key in _global_kill_switches:
                return FeatureCheckResult(
                    feature_key=feature_key,
                    enabled=False,
                    reason="kill_switch",
                    org_id=org_id,
                    tier_required=fdef.tier.value,
                    org_tier="N/A",
                )

        # 3. Check cache
        cache_key = f"org:{org_id}:feature:{feature_key}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        # 4. Resolve org tier from DB
        org_tier_str = await self._get_org_tier(org_id)
        org_tier_level = _PLATFORM_TIER_MAP.get(org_tier_str, 0)
        required_level = TIER_HIERARCHY.get(fdef.tier, 0)

        # 5. Check per-org override in company_feature_access
        override = self._db.execute(
            text("""
                SELECT is_enabled, is_trial, trial_end
                FROM company_feature_access
                WHERE company_id = :org_id AND feature_key = :feature_key
            """),
            {"org_id": org_id, "feature_key": feature_key},
        ).fetchone()

        if override is not None:
            is_enabled = override[0]
            is_trial = override[1]
            trial_end = override[2]

            # Check trial expiry
            if is_trial and trial_end:
                if isinstance(trial_end, datetime) and trial_end < datetime.now(timezone.utc):
                    # Trial expired
                    result = FeatureCheckResult(
                        feature_key=feature_key,
                        enabled=False,
                        reason="trial_expired",
                        org_id=org_id,
                        tier_required=fdef.tier.value,
                        org_tier=org_tier_str,
                    )
                    _cache.set(cache_key, result)
                    return result

            reason = "override_enabled" if is_enabled else "override_disabled"
            if is_trial:
                reason = "trial_active"

            result = FeatureCheckResult(
                feature_key=feature_key,
                enabled=bool(is_enabled),
                reason=reason,
                org_id=org_id,
                tier_required=fdef.tier.value,
                org_tier=org_tier_str,
            )
            _cache.set(cache_key, result)
            return result

        # 6. Percentage-based rollout check
        if fdef.rollout_percentage < 100:
            if not _is_org_in_rollout(org_id, feature_key, fdef.rollout_percentage):
                result = FeatureCheckResult(
                    feature_key=feature_key,
                    enabled=False,
                    reason="rollout_excluded",
                    org_id=org_id,
                    tier_required=fdef.tier.value,
                    org_tier=org_tier_str,
                )
                _cache.set(cache_key, result)
                return result

        # 7. Tier comparison
        tier_allowed = org_tier_level >= required_level

        if tier_allowed and fdef.default:
            reason = "tier_allowed"
            enabled = True
        elif tier_allowed and not fdef.default:
            # Org has the right tier, but feature defaults to off (requires explicit enable)
            reason = "default_off"
            enabled = False
        else:
            reason = "tier_insufficient"
            enabled = False

        result = FeatureCheckResult(
            feature_key=feature_key,
            enabled=enabled,
            reason=reason,
            org_id=org_id,
            tier_required=fdef.tier.value,
            org_tier=org_tier_str,
        )
        _cache.set(cache_key, result)
        return result

    async def _get_org_tier(self, org_id: int) -> str:
        """Look up the organization's subscription tier.

        Checks the organizations table for a feature_tier column.
        Falls back to 'core' if not found.
        """
        cache_key = f"org:{org_id}:tier"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            row = self._db.execute(
                text("""
                    SELECT feature_tier FROM organizations
                    WHERE id = :org_id
                """),
                {"org_id": org_id},
            ).fetchone()

            tier = row[0] if row and row[0] else "core"
        except Exception as e:
            logger.warning("Failed to look up org tier for org_id=%s: %s", org_id, e)
            tier = "core"

        _cache.set(cache_key, tier, ttl=600.0)  # Cache org tier for 10 min
        return tier

    async def _log_usage_event(
        self,
        org_id: int,
        feature_key: str,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write a usage event to the tracking table.

        Non-blocking: failures are logged but do not propagate.
        """
        try:
            import json
            self._db.execute(
                text("""
                    INSERT INTO smart_docs_feature_usage
                        (org_id, feature_key, event_type, metadata, created_at)
                    VALUES
                        (:org_id, :feature_key, :event_type, :metadata, :now)
                """),
                {
                    "org_id": org_id,
                    "feature_key": feature_key,
                    "event_type": event_type,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "now": datetime.now(timezone.utc),
                },
            )
            self._db.commit()
        except Exception as e:
            logger.debug(
                "Failed to log feature usage event (non-fatal): org=%s feature=%s error=%s",
                org_id, feature_key, e,
            )


# =============================================================================
# ROLLOUT HASHING
# =============================================================================

def _is_org_in_rollout(org_id: int, feature_key: str, percentage: int) -> bool:
    """Deterministic rollout: hash(org_id + feature_key) mod 100 < percentage.

    This produces a consistent assignment -- the same org always gets the same
    result for a given feature key, even across restarts.
    """
    if percentage >= 100:
        return True
    if percentage <= 0:
        return False
    digest = hashlib.sha256(f"{org_id}:{feature_key}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < percentage


# =============================================================================
# FASTAPI DECORATOR
# =============================================================================

def require_smart_docs_feature(feature_key: str) -> Callable:
    """FastAPI endpoint decorator that gates access on a Smart Docs feature flag.

    Returns 403 if the feature is not enabled for the requesting org.
    Logs gate hits (both grants and denials) for analytics.

    Usage:
        @router.post("/api/smart-docs/income/calculate")
        @require_smart_docs_feature("smart_docs.income_calculation")
        async def calculate_income(request: Request, ...):
            ...

    The decorator extracts org_id from request.state.organization (set by
    TenantContextMiddleware) or from the organization attribute of
    request.state.organization.

    If no organization context is found, the request is allowed through
    (same behavior as the platform feature_gate.py decorator).
    """
    fdef = SMART_DOCS_FEATURES.get(feature_key)
    if fdef is None:
        raise ValueError(f"Cannot decorate with unknown feature key: {feature_key}")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            org_id = _extract_org_id(request)

            if org_id is not None:
                # Get a DB session from kwargs (FastAPI injects as 'db')
                db: Optional[Session] = kwargs.get("db")
                if db is None:
                    # Try to find it in args
                    for arg in args:
                        if isinstance(arg, Session):
                            db = arg
                            break

                if db is not None:
                    service = SmartDocsFeatureFlagService(db)
                    result = await service.check_feature(org_id, feature_key)

                    # Track the access attempt (fire-and-forget)
                    try:
                        await service.track_feature_access(
                            org_id=org_id,
                            feature_key=feature_key,
                            granted=result.enabled,
                        )
                    except Exception as e:
                        logger.debug("Feature usage tracking failed (non-fatal): %s", e)

                    if not result.enabled:
                        logger.info(
                            "Smart Docs feature gate DENIED: org=%s feature=%s reason=%s",
                            org_id, feature_key, result.reason,
                        )
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "smart_docs_feature_required",
                                "feature": feature_key,
                                "reason": result.reason,
                                "tier_required": result.tier_required,
                                "current_tier": result.org_tier,
                                "message": (
                                    f"The '{feature_key}' feature requires the "
                                    f"'{result.tier_required}' tier. "
                                    f"Contact sales to upgrade."
                                ),
                            },
                        )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def _extract_org_id(request: Optional[Request]) -> Optional[int]:
    """Extract org_id from the FastAPI request object.

    Checks request.state.organization_id (set by TenantContextMiddleware)
    and request.state.organization.id as fallback.
    """
    if request is None:
        return None
    if not hasattr(request, "state"):
        return None

    # Direct organization_id on state (set by TenantContextMiddleware)
    org_id = getattr(request.state, "organization_id", None)
    if org_id:
        return org_id

    # Organization object on state
    org = getattr(request.state, "organization", None)
    if org is not None:
        return getattr(org, "id", None)

    return None


# =============================================================================
# MODULE-LEVEL FACTORY
# =============================================================================

def get_feature_flag_service(db: Session) -> SmartDocsFeatureFlagService:
    """Create a SmartDocsFeatureFlagService instance.

    Usage:
        from services.smart_docs.feature_flag_service import get_feature_flag_service

        service = get_feature_flag_service(db)
        enabled = await service.is_feature_enabled(org_id, "smart_docs.fraud_detection")
    """
    return SmartDocsFeatureFlagService(db)


def invalidate_feature_cache(org_id: Optional[int] = None) -> None:
    """Invalidate feature flag cache.

    Call after admin operations that change feature access.

    Args:
        org_id: If provided, only invalidate cache for this org.
                If None, clear entire cache.
    """
    if org_id is not None:
        _cache.invalidate_org(org_id)
    else:
        _cache.clear()
