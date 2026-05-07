"""
Business Rules Service

Database-backed configuration service that replaces hardcoded business rules
with queryable, time-versioned, org-overridable values.

Lookup precedence for get_rule():
1. Org-specific active rule matching the requested date
2. System default (org_id IS NULL) active rule matching the requested date
3. Hardcoded fallback from RULE_DEFAULTS

Caching:
- In-memory dict cache with 5-minute TTL
- Cache key = (rule_key, org_id, as_of_date)
- invalidate_cache() clears all entries (or per-org)

Usage:
    from services.smart_docs.business_rules_service import BusinessRulesService

    service = BusinessRulesService(db)
    threshold = service.get_rule("large_deposit_threshold", org_id=42)
    # Returns 5000 (from DB or fallback)

    all_fraud_rules = service.get_rules_by_category("fraud", org_id=42)
    # Returns {"large_deposit_threshold": 5000, "nsf_max_count_6months": 3, ...}
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from database.models.business_rules import BusinessRuleConfig

logger = logging.getLogger(__name__)


# =============================================================================
# HARDCODED FALLBACK DEFAULTS
# =============================================================================
# These serve as the last-resort fallback when no DB row exists.
# They are also used by seed_defaults() to populate the DB initially.

RULE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # ---- Income thresholds ----
    "ss_wage_base": {
        "value": 176100,
        "value_type": "integer",
        "source": "irs_2025",
        "category": "income",
        "description": "Social Security wage base for the current tax year (IRS annual limit)",
    },
    "income_variance_tolerance_pct": {
        "value": 5.0,
        "value_type": "decimal",
        "source": "custom",
        "category": "income",
        "description": "Allowable variance (%) between stated and calculated income before flagging",
    },
    "declining_income_threshold_pct": {
        "value": 25.0,
        "value_type": "decimal",
        "source": "fannie_mae",
        "category": "income",
        "description": "Year-over-year income decline (%) that triggers underwriting review",
    },

    # ---- Document freshness (days) ----
    "freshness_paystub": {
        "value": 30,
        "value_type": "integer",
        "source": "fannie_mae",
        "category": "document",
        "description": "Maximum age in days for paystubs to be considered current",
    },
    "freshness_bank_statement": {
        "value": 60,
        "value_type": "integer",
        "source": "fannie_mae",
        "category": "document",
        "description": "Maximum age in days for bank statements to be considered current",
    },
    "freshness_w2": {
        "value": 365,
        "value_type": "integer",
        "source": "fannie_mae",
        "category": "document",
        "description": "Maximum age in days for W-2 forms (also subject to annual expiration logic)",
    },
    "freshness_tax_return": {
        "value": 365,
        "value_type": "integer",
        "source": "fannie_mae",
        "category": "document",
        "description": "Maximum age in days for tax returns (also subject to annual expiration logic)",
    },

    # ---- Fraud detection ----
    "large_deposit_threshold": {
        "value": 5000,
        "value_type": "integer",
        "source": "custom",
        "category": "fraud",
        "description": "Dollar amount above which a deposit requires sourcing documentation",
    },
    "nsf_max_count_6months": {
        "value": 3,
        "value_type": "integer",
        "source": "custom",
        "category": "fraud",
        "description": "Maximum NSF/overdraft occurrences in 6 months before flagging",
    },
    "fraud_score_auto_flag_threshold": {
        "value": 70,
        "value_type": "integer",
        "source": "custom",
        "category": "fraud",
        "description": "Fraud risk score (0-100) above which loans are auto-flagged for review",
    },

    # ---- AI confidence ----
    "auto_create_confidence_threshold": {
        "value": 80,
        "value_type": "integer",
        "source": "custom",
        "category": "ai",
        "description": "Minimum AI confidence (%) to auto-create records without human review",
    },
    "medium_confidence_threshold": {
        "value": 50,
        "value_type": "integer",
        "source": "custom",
        "category": "ai",
        "description": "AI confidence (%) below which results are flagged as low-confidence",
    },
    "auto_approve_min_confidence": {
        "value": 90,
        "value_type": "integer",
        "source": "custom",
        "category": "ai",
        "description": "Minimum AI confidence (%) for fully automatic approval without review",
    },

    # ---- Follow-up ----
    "max_followup_emails_per_day": {
        "value": 3,
        "value_type": "integer",
        "source": "custom",
        "category": "followup",
        "description": "Maximum automated follow-up emails per borrower per day",
    },
    "followup_escalation_day": {
        "value": 7,
        "value_type": "integer",
        "source": "custom",
        "category": "followup",
        "description": "Days without response before escalating to loan officer",
    },

    # ---- Compliance / retention ----
    "audit_retention_days": {
        "value": 2555,
        "value_type": "integer",
        "source": "trid",
        "category": "compliance",
        "description": "Number of days to retain audit trail records (~7 years per TRID)",
    },
    "document_retention_days": {
        "value": 2555,
        "value_type": "integer",
        "source": "trid",
        "category": "compliance",
        "description": "Number of days to retain loan documents (~7 years per TRID)",
    },
}


# =============================================================================
# CACHE
# =============================================================================

_CACHE_TTL_SECONDS = 300  # 5 minutes

_cache: Dict[str, Any] = {}
_cache_timestamps: Dict[str, float] = {}
_cache_lock = threading.Lock()


def _cache_key(rule_key: str, org_id: Optional[int], as_of: date) -> str:
    """Build a deterministic cache key."""
    return f"{rule_key}:{org_id}:{as_of.isoformat()}"


def _get_cached(key: str) -> Optional[Any]:
    """Get a cached value if still valid."""
    with _cache_lock:
        ts = _cache_timestamps.get(key)
        if ts is not None and (time.time() - ts) < _CACHE_TTL_SECONDS:
            return _cache.get(key)
    return None


def _set_cached(key: str, value: Any) -> None:
    """Set a cached value with current timestamp."""
    with _cache_lock:
        _cache[key] = value
        _cache_timestamps[key] = time.time()


# =============================================================================
# SERVICE
# =============================================================================

class BusinessRulesService:
    """Service for reading and writing business rule configurations.

    Provides a clean API for application code to retrieve configurable
    thresholds, limits, and settings without hardcoding values.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_rule(
        self,
        rule_key: str,
        org_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
    ) -> Any:
        """Get the effective value for a business rule.

        Lookup precedence:
        1. Org-specific rule for as_of_date
        2. System default (org_id=NULL) for as_of_date
        3. Hardcoded fallback from RULE_DEFAULTS

        Args:
            rule_key: The rule identifier (e.g., "large_deposit_threshold").
            org_id: Organization ID for org-specific overrides. None = system default only.
            as_of_date: Date for time-versioned rules. Defaults to today.

        Returns:
            The rule value, cast to the appropriate Python type.
        """
        if as_of_date is None:
            as_of_date = date.today()

        # Check cache first
        ck = _cache_key(rule_key, org_id, as_of_date)
        cached = _get_cached(ck)
        if cached is not None:
            return cached

        # Lazy import to avoid circular import at module load time
        from database.models.business_rules import BusinessRuleConfig

        value = None

        # 1. Try org-specific rule
        if org_id is not None:
            rule = self._find_effective_rule(BusinessRuleConfig, rule_key, org_id, as_of_date)
            if rule is not None:
                value = rule.get_typed_value()

        # 2. Try system default (org_id IS NULL)
        if value is None:
            rule = self._find_effective_rule(BusinessRuleConfig, rule_key, None, as_of_date)
            if rule is not None:
                value = rule.get_typed_value()

        # 3. Hardcoded fallback
        if value is None:
            default = RULE_DEFAULTS.get(rule_key)
            if default is not None:
                value = default["value"]
            else:
                logger.warning(f"No rule found for key '{rule_key}' (org={org_id}, date={as_of_date})")
                _set_cached(ck, None)
                return None

        _set_cached(ck, value)
        return value

    def _find_effective_rule(self, model, rule_key: str, org_id: Optional[int], as_of_date: date):
        """Find the most recently effective rule row for the given key/org/date.

        Matches rules where:
        - rule_key matches
        - organization_id matches (or IS NULL for system defaults)
        - is_active = True
        - effective_date <= as_of_date
        - expiration_date IS NULL OR expiration_date > as_of_date

        Orders by effective_date DESC to get the most recent applicable version.
        """
        try:
            query = self.db.query(model).filter(
                model.rule_key == rule_key,
                model.is_active == True,  # noqa: E712
                model.effective_date <= as_of_date,
                or_(
                    model.expiration_date.is_(None),
                    model.expiration_date > as_of_date,
                ),
            )

            if org_id is not None:
                query = query.filter(model.organization_id == org_id)
            else:
                query = query.filter(model.organization_id.is_(None))

            return query.order_by(model.effective_date.desc()).first()
        except Exception as e:
            logger.exception(f"Error querying business rule '{rule_key}': {e}")
            return None

    def get_rules_by_category(
        self,
        category: str,
        org_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get all rule values for a category.

        Returns a dict mapping rule_key -> value for every rule in the category.
        Uses the same precedence logic as get_rule() for each key.

        Args:
            category: Rule category (e.g., "fraud", "income", "document").
            org_id: Organization ID for overrides.
            as_of_date: Reference date. Defaults to today.

        Returns:
            Dict of {rule_key: typed_value} for all rules in the category.
        """
        if as_of_date is None:
            as_of_date = date.today()

        result = {}

        # Start with hardcoded defaults for this category
        for key, default in RULE_DEFAULTS.items():
            if default["category"] == category:
                result[key] = default["value"]

        # Override with DB values (system defaults first, then org-specific)
        from database.models.business_rules import BusinessRuleConfig

        try:
            # System defaults
            system_rules = self.db.query(BusinessRuleConfig).filter(
                BusinessRuleConfig.rule_category == category,
                BusinessRuleConfig.organization_id.is_(None),
                BusinessRuleConfig.is_active == True,  # noqa: E712
                BusinessRuleConfig.effective_date <= as_of_date,
                or_(
                    BusinessRuleConfig.expiration_date.is_(None),
                    BusinessRuleConfig.expiration_date > as_of_date,
                ),
            ).order_by(BusinessRuleConfig.effective_date.desc()).all()

            # Group by rule_key and take the most recent effective_date
            seen_keys = set()
            for rule in system_rules:
                if rule.rule_key not in seen_keys:
                    result[rule.rule_key] = rule.get_typed_value()
                    seen_keys.add(rule.rule_key)

            # Org-specific overrides
            if org_id is not None:
                org_rules = self.db.query(BusinessRuleConfig).filter(
                    BusinessRuleConfig.rule_category == category,
                    BusinessRuleConfig.organization_id == org_id,
                    BusinessRuleConfig.is_active == True,  # noqa: E712
                    BusinessRuleConfig.effective_date <= as_of_date,
                    or_(
                        BusinessRuleConfig.expiration_date.is_(None),
                        BusinessRuleConfig.expiration_date > as_of_date,
                    ),
                ).order_by(BusinessRuleConfig.effective_date.desc()).all()

                seen_keys = set()
                for rule in org_rules:
                    if rule.rule_key not in seen_keys:
                        result[rule.rule_key] = rule.get_typed_value()
                        seen_keys.add(rule.rule_key)

        except Exception as e:
            logger.exception(f"Error querying rules for category '{category}': {e}")

        return result

    def set_rule(
        self,
        rule_key: str,
        value: Any,
        org_id: Optional[int] = None,
        effective_date: Optional[date] = None,
        expiration_date: Optional[date] = None,
        source: Optional[str] = None,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> "BusinessRuleConfig":
        """Create or update a business rule configuration.

        If a rule with the same (org_id, rule_key, effective_date) exists,
        it is updated. Otherwise a new row is created.

        Args:
            rule_key: Rule identifier.
            value: The rule value (will be stored as JSON).
            org_id: Organization ID (None for system default).
            effective_date: When this value takes effect. Defaults to today.
            expiration_date: When this value expires. None = no expiration.
            source: Regulatory source reference.
            description: Human-readable description.
            updated_by: User ID who is making the change.

        Returns:
            The created or updated BusinessRuleConfig instance.
        """
        from database.models.business_rules import BusinessRuleConfig

        if effective_date is None:
            effective_date = date.today()

        # Determine category and value_type from defaults or infer
        default_info = RULE_DEFAULTS.get(rule_key, {})
        category = default_info.get("category", "custom")
        value_type = default_info.get("value_type", _infer_value_type(value))

        # Use provided description/source or fall back to defaults
        if description is None:
            description = default_info.get("description")
        if source is None:
            source = default_info.get("source", "custom")

        # Check for existing rule with same (org_id, rule_key, effective_date)
        query = self.db.query(BusinessRuleConfig).filter(
            BusinessRuleConfig.rule_key == rule_key,
            BusinessRuleConfig.effective_date == effective_date,
        )
        if org_id is not None:
            query = query.filter(BusinessRuleConfig.organization_id == org_id)
        else:
            query = query.filter(BusinessRuleConfig.organization_id.is_(None))

        existing = query.first()

        if existing:
            existing.rule_value = value
            existing.value_type = value_type
            existing.expiration_date = expiration_date
            existing.source = source
            existing.description = description
            existing.updated_by_user_id = updated_by
            existing.updated_at = datetime.now(timezone.utc)
            existing.is_active = True
            self.db.flush()
            rule = existing
        else:
            rule = BusinessRuleConfig(
                organization_id=org_id,
                rule_category=category,
                rule_key=rule_key,
                rule_value=value,
                value_type=value_type,
                description=description,
                effective_date=effective_date,
                expiration_date=expiration_date,
                source=source,
                is_active=True,
                updated_by_user_id=updated_by,
            )
            self.db.add(rule)
            self.db.flush()

        # Invalidate cache for this rule
        self.invalidate_cache(org_id=org_id)

        return rule

    def get_rule_history(
        self,
        rule_key: str,
        org_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get all versions of a rule, ordered by effective_date desc.

        Returns both active and inactive versions for audit purposes.

        Args:
            rule_key: Rule identifier.
            org_id: Organization ID (None for system defaults).

        Returns:
            List of dicts with rule version details.
        """
        from database.models.business_rules import BusinessRuleConfig

        query = self.db.query(BusinessRuleConfig).filter(
            BusinessRuleConfig.rule_key == rule_key,
        )

        if org_id is not None:
            query = query.filter(BusinessRuleConfig.organization_id == org_id)
        else:
            query = query.filter(BusinessRuleConfig.organization_id.is_(None))

        rules = query.order_by(BusinessRuleConfig.effective_date.desc()).all()

        return [
            {
                "id": r.id,
                "rule_key": r.rule_key,
                "rule_value": r.rule_value,
                "value_type": r.value_type,
                "effective_date": r.effective_date.isoformat() if r.effective_date else None,
                "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
                "source": r.source,
                "description": r.description,
                "is_active": r.is_active,
                "updated_by_user_id": r.updated_by_user_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ]

    def seed_defaults(
        self,
        org_id: Optional[int] = None,
        updated_by: Optional[int] = None,
    ) -> int:
        """Seed default rules from RULE_DEFAULTS into the database.

        Only creates rules that don't already exist for the given org.
        System defaults (org_id=None) are created with effective_date=2020-01-01
        so they cover all historical lookups.

        Args:
            org_id: Organization ID to seed for. None = system defaults.
            updated_by: User ID performing the seed.

        Returns:
            Number of rules created.
        """
        from database.models.business_rules import BusinessRuleConfig

        created = 0
        effective = date(2020, 1, 1)  # Far enough back to cover any lookup

        for rule_key, default in RULE_DEFAULTS.items():
            # Check if already exists
            query = self.db.query(BusinessRuleConfig).filter(
                BusinessRuleConfig.rule_key == rule_key,
            )
            if org_id is not None:
                query = query.filter(BusinessRuleConfig.organization_id == org_id)
            else:
                query = query.filter(BusinessRuleConfig.organization_id.is_(None))

            if query.first() is not None:
                continue

            rule = BusinessRuleConfig(
                organization_id=org_id,
                rule_category=default["category"],
                rule_key=rule_key,
                rule_value=default["value"],
                value_type=default["value_type"],
                description=default["description"],
                effective_date=effective,
                expiration_date=None,
                source=default["source"],
                is_active=True,
                updated_by_user_id=updated_by,
            )
            self.db.add(rule)
            created += 1

        if created > 0:
            self.db.flush()
            self.invalidate_cache(org_id=org_id)

        logger.info(
            f"Seeded {created} default business rules "
            f"(org_id={org_id}, skipped {len(RULE_DEFAULTS) - created} existing)"
        )
        return created

    def invalidate_cache(self, org_id: Optional[int] = None) -> None:
        """Clear the in-memory rule cache.

        Args:
            org_id: If provided, only clears cache entries for this org.
                    If None, clears the entire cache.
        """
        with _cache_lock:
            if org_id is None:
                _cache.clear()
                _cache_timestamps.clear()
            else:
                # Clear entries matching this org_id
                org_prefix = f":{org_id}:"
                keys_to_remove = [
                    k for k in _cache
                    if org_prefix in k
                ]
                for k in keys_to_remove:
                    _cache.pop(k, None)
                    _cache_timestamps.pop(k, None)


def _infer_value_type(value: Any) -> str:
    """Infer the value_type string from a Python value."""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "decimal"
    elif isinstance(value, str):
        return "string"
    else:
        return "json"


def get_business_rules_service(db: Session) -> BusinessRulesService:
    """Factory function for BusinessRulesService.

    Usage:
        service = get_business_rules_service(db)
        val = service.get_rule("large_deposit_threshold")
    """
    return BusinessRulesService(db)
