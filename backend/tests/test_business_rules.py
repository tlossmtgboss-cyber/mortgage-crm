"""
Tests for Business Rules Configuration System

Tests the database-backed business rules service including:
- Default fallback behavior
- Org override precedence
- Effective date filtering
- Expiration handling
- Cache behavior and invalidation
- Rule history tracking
- Seed defaults
"""

import time
import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a test database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the business rules cache before each test."""
    from services.smart_docs.business_rules_service import _cache, _cache_timestamps, _cache_lock
    with _cache_lock:
        _cache.clear()
        _cache_timestamps.clear()
    yield
    with _cache_lock:
        _cache.clear()
        _cache_timestamps.clear()


@pytest.fixture
def service(db_session):
    """Create a BusinessRulesService instance."""
    from services.smart_docs.business_rules_service import BusinessRulesService
    return BusinessRulesService(db_session)


@pytest.fixture
def rule_model():
    """Import and return the BusinessRuleConfig model."""
    from database.models.business_rules import BusinessRuleConfig
    return BusinessRuleConfig


# =============================================================================
# TEST: DEFAULT FALLBACK
# =============================================================================

class TestDefaultFallback:
    """Test that hardcoded defaults are returned when no DB rows exist."""

    def test_get_rule_returns_hardcoded_default(self, service):
        """When no DB row exists, get_rule returns the RULE_DEFAULTS value."""
        value = service.get_rule("large_deposit_threshold")
        assert value == 5000

    def test_get_rule_returns_correct_type_integer(self, service):
        """Integer defaults are returned as int."""
        value = service.get_rule("ss_wage_base")
        assert value == 176100
        assert isinstance(value, int)

    def test_get_rule_returns_correct_type_decimal(self, service):
        """Decimal defaults are returned as float."""
        value = service.get_rule("income_variance_tolerance_pct")
        assert value == 5.0
        assert isinstance(value, float)

    def test_get_rule_unknown_key_returns_none(self, service):
        """Unknown rule keys return None."""
        value = service.get_rule("nonexistent_rule_key")
        assert value is None

    def test_get_rules_by_category_fraud(self, service):
        """get_rules_by_category returns all defaults for 'fraud' category."""
        rules = service.get_rules_by_category("fraud")
        assert "large_deposit_threshold" in rules
        assert "nsf_max_count_6months" in rules
        assert "fraud_score_auto_flag_threshold" in rules
        assert rules["large_deposit_threshold"] == 5000
        assert rules["nsf_max_count_6months"] == 3
        assert rules["fraud_score_auto_flag_threshold"] == 70

    def test_get_rules_by_category_income(self, service):
        """get_rules_by_category returns all defaults for 'income' category."""
        rules = service.get_rules_by_category("income")
        assert "ss_wage_base" in rules
        assert "income_variance_tolerance_pct" in rules
        assert "declining_income_threshold_pct" in rules

    def test_get_rules_by_category_empty(self, service):
        """get_rules_by_category returns empty dict for unknown category."""
        rules = service.get_rules_by_category("nonexistent_category")
        assert rules == {}


# =============================================================================
# TEST: ORG OVERRIDE PRECEDENCE
# =============================================================================

class TestOrgOverride:
    """Test that org-specific rules take precedence over system defaults."""

    def test_org_override_takes_precedence(self, service, db_session, rule_model):
        """Org-specific rule overrides system default."""
        # Create a system default
        system_rule = rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=5000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        )
        db_session.add(system_rule)

        # Create an org-specific override
        org_rule = rule_model(
            organization_id=42,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=10000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        )
        db_session.add(org_rule)
        db_session.flush()

        value = service.get_rule("large_deposit_threshold", org_id=42)
        assert value == 10000

    def test_system_default_used_when_no_org_override(self, service, db_session, rule_model):
        """System default is used when no org-specific override exists."""
        system_rule = rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=7500,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        )
        db_session.add(system_rule)
        db_session.flush()

        value = service.get_rule("large_deposit_threshold", org_id=99)
        assert value == 7500

    def test_org_override_in_category_query(self, service, db_session, rule_model):
        """get_rules_by_category applies org overrides correctly."""
        # System default
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=5000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        # Org override
        db_session.add(rule_model(
            organization_id=42,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=15000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        rules = service.get_rules_by_category("fraud", org_id=42)
        assert rules["large_deposit_threshold"] == 15000


# =============================================================================
# TEST: EFFECTIVE DATE FILTERING
# =============================================================================

class TestEffectiveDateFiltering:
    """Test that rules are filtered by effective_date."""

    def test_future_rule_not_returned(self, service, db_session, rule_model):
        """A rule with a future effective_date is not returned for today."""
        future_date = date.today() + timedelta(days=30)
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=200000,
            value_type="integer",
            effective_date=future_date,
            is_active=True,
        ))
        db_session.flush()

        # Should fall back to hardcoded default since DB rule is in future
        value = service.get_rule("ss_wage_base")
        assert value == 176100  # hardcoded fallback

    def test_most_recent_effective_rule_wins(self, service, db_session, rule_model):
        """When multiple rules are effective, the most recently effective wins."""
        # Older rule
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=160200,
            value_type="integer",
            effective_date=date(2023, 1, 1),
            is_active=True,
        ))
        # Newer rule
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=168600,
            value_type="integer",
            effective_date=date(2024, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        value = service.get_rule("ss_wage_base", as_of_date=date(2024, 6, 1))
        assert value == 168600

    def test_as_of_date_returns_correct_version(self, service, db_session, rule_model):
        """Querying with as_of_date in 2023 returns the 2023 version."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=160200,
            value_type="integer",
            effective_date=date(2023, 1, 1),
            is_active=True,
        ))
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=168600,
            value_type="integer",
            effective_date=date(2024, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        value = service.get_rule("ss_wage_base", as_of_date=date(2023, 6, 15))
        assert value == 160200


# =============================================================================
# TEST: EXPIRATION HANDLING
# =============================================================================

class TestExpirationHandling:
    """Test that expired rules are not returned."""

    def test_expired_rule_not_returned(self, service, db_session, rule_model):
        """A rule with an expiration_date in the past is not returned."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=160200,
            value_type="integer",
            effective_date=date(2023, 1, 1),
            expiration_date=date(2024, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        # Query for a date after expiration should fall back to hardcoded
        value = service.get_rule("ss_wage_base", as_of_date=date(2024, 6, 1))
        assert value == 176100  # hardcoded fallback

    def test_not_yet_expired_rule_returned(self, service, db_session, rule_model):
        """A rule with a future expiration_date is returned."""
        future_expiry = date.today() + timedelta(days=365)
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=8000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            expiration_date=future_expiry,
            is_active=True,
        ))
        db_session.flush()

        value = service.get_rule("large_deposit_threshold")
        assert value == 8000

    def test_null_expiration_means_no_expiry(self, service, db_session, rule_model):
        """A rule with expiration_date=None never expires."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="nsf_max_count_6months",
            rule_value=5,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            expiration_date=None,
            is_active=True,
        ))
        db_session.flush()

        far_future = date(2099, 12, 31)
        value = service.get_rule("nsf_max_count_6months", as_of_date=far_future)
        assert value == 5


# =============================================================================
# TEST: CACHE BEHAVIOR
# =============================================================================

class TestCacheBehavior:
    """Test in-memory cache with TTL."""

    def test_cache_returns_cached_value(self, service, db_session, rule_model):
        """Second call to get_rule returns cached value without DB query."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=9999,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        # First call populates cache
        val1 = service.get_rule("large_deposit_threshold")
        assert val1 == 9999

        # Directly change the DB value (bypass service)
        rule = db_session.query(rule_model).filter_by(rule_key="large_deposit_threshold").first()
        rule.rule_value = 1234
        db_session.flush()

        # Second call returns cached value
        val2 = service.get_rule("large_deposit_threshold")
        assert val2 == 9999  # still cached

    def test_cache_invalidation_clears_values(self, service, db_session, rule_model):
        """invalidate_cache() forces the next get_rule to re-query."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=9999,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        val1 = service.get_rule("large_deposit_threshold")
        assert val1 == 9999

        # Update DB directly
        rule = db_session.query(rule_model).filter_by(rule_key="large_deposit_threshold").first()
        rule.rule_value = 1234
        db_session.flush()

        # Invalidate cache
        service.invalidate_cache()

        # Now should get updated value
        val2 = service.get_rule("large_deposit_threshold")
        assert val2 == 1234

    def test_cache_ttl_expiry(self, service, db_session, rule_model):
        """Cache entries expire after TTL seconds."""
        from services.smart_docs import business_rules_service

        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=9999,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        # First call
        val1 = service.get_rule("large_deposit_threshold")
        assert val1 == 9999

        # Manually expire the cache entry by backdating the timestamp
        ck = business_rules_service._cache_key(
            "large_deposit_threshold", None, date.today()
        )
        with business_rules_service._cache_lock:
            business_rules_service._cache_timestamps[ck] = time.time() - 301  # past TTL

        # Update DB
        rule = db_session.query(rule_model).filter_by(rule_key="large_deposit_threshold").first()
        rule.rule_value = 7777
        db_session.flush()

        # Now should re-query because cache entry expired
        val2 = service.get_rule("large_deposit_threshold")
        assert val2 == 7777


# =============================================================================
# TEST: RULE HISTORY
# =============================================================================

class TestRuleHistory:
    """Test the get_rule_history method."""

    def test_history_returns_all_versions(self, service, db_session, rule_model):
        """get_rule_history returns all versions of a rule."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=160200,
            value_type="integer",
            effective_date=date(2023, 1, 1),
            expiration_date=date(2024, 1, 1),
            source="irs_2023",
            is_active=True,
        ))
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=168600,
            value_type="integer",
            effective_date=date(2024, 1, 1),
            expiration_date=date(2025, 1, 1),
            source="irs_2024",
            is_active=True,
        ))
        db_session.add(rule_model(
            organization_id=None,
            rule_category="income",
            rule_key="ss_wage_base",
            rule_value=176100,
            value_type="integer",
            effective_date=date(2025, 1, 1),
            source="irs_2025",
            is_active=True,
        ))
        db_session.flush()

        history = service.get_rule_history("ss_wage_base")
        assert len(history) == 3
        # Most recent first
        assert history[0]["rule_value"] == 176100
        assert history[1]["rule_value"] == 168600
        assert history[2]["rule_value"] == 160200

    def test_history_scoped_to_org(self, service, db_session, rule_model):
        """get_rule_history only returns versions for the specified org."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=5000,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=True,
        ))
        db_session.add(rule_model(
            organization_id=42,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=10000,
            value_type="integer",
            effective_date=date(2024, 1, 1),
            is_active=True,
        ))
        db_session.flush()

        system_history = service.get_rule_history("large_deposit_threshold", org_id=None)
        assert len(system_history) == 1
        assert system_history[0]["rule_value"] == 5000

        org_history = service.get_rule_history("large_deposit_threshold", org_id=42)
        assert len(org_history) == 1
        assert org_history[0]["rule_value"] == 10000


# =============================================================================
# TEST: SEED DEFAULTS
# =============================================================================

class TestSeedDefaults:
    """Test the seed_defaults method."""

    def test_seed_creates_all_defaults(self, service, db_session, rule_model):
        """seed_defaults creates a DB row for every entry in RULE_DEFAULTS."""
        from services.smart_docs.business_rules_service import RULE_DEFAULTS

        created = service.seed_defaults()
        db_session.flush()

        assert created == len(RULE_DEFAULTS)

        # Verify a sample rule exists
        rule = db_session.query(rule_model).filter_by(
            rule_key="large_deposit_threshold",
            organization_id=None,
        ).first()
        assert rule is not None
        assert rule.rule_value == 5000

    def test_seed_is_idempotent(self, service, db_session):
        """Calling seed_defaults twice does not create duplicates."""
        from services.smart_docs.business_rules_service import RULE_DEFAULTS

        created1 = service.seed_defaults()
        db_session.flush()
        assert created1 == len(RULE_DEFAULTS)

        created2 = service.seed_defaults()
        db_session.flush()
        assert created2 == 0  # nothing new created

    def test_seed_per_org(self, service, db_session, rule_model):
        """seed_defaults can create org-specific copies."""
        from services.smart_docs.business_rules_service import RULE_DEFAULTS

        created = service.seed_defaults(org_id=42)
        db_session.flush()

        assert created == len(RULE_DEFAULTS)

        rule = db_session.query(rule_model).filter_by(
            rule_key="large_deposit_threshold",
            organization_id=42,
        ).first()
        assert rule is not None
        assert rule.rule_value == 5000


# =============================================================================
# TEST: SET RULE
# =============================================================================

class TestSetRule:
    """Test creating and updating rules via set_rule."""

    def test_set_rule_creates_new(self, service, db_session, rule_model):
        """set_rule creates a new rule when none exists."""
        rule = service.set_rule(
            rule_key="large_deposit_threshold",
            value=12000,
            org_id=42,
            effective_date=date(2025, 1, 1),
            source="custom",
            description="Increased threshold for org 42",
            updated_by=1,
        )
        db_session.flush()

        assert rule.rule_value == 12000
        assert rule.organization_id == 42
        assert rule.updated_by_user_id == 1

    def test_set_rule_updates_existing(self, service, db_session, rule_model):
        """set_rule updates an existing rule with same (org, key, date)."""
        service.set_rule(
            rule_key="large_deposit_threshold",
            value=8000,
            org_id=42,
            effective_date=date(2025, 1, 1),
        )
        db_session.flush()

        service.set_rule(
            rule_key="large_deposit_threshold",
            value=15000,
            org_id=42,
            effective_date=date(2025, 1, 1),
        )
        db_session.flush()

        rules = db_session.query(rule_model).filter_by(
            rule_key="large_deposit_threshold",
            organization_id=42,
        ).all()
        assert len(rules) == 1
        assert rules[0].rule_value == 15000

    def test_set_rule_invalidates_cache(self, service, db_session, rule_model):
        """set_rule invalidates the cache so subsequent reads get fresh data."""
        # Populate cache
        val = service.get_rule("large_deposit_threshold")
        assert val == 5000  # hardcoded default

        # Set new value
        service.set_rule(
            rule_key="large_deposit_threshold",
            value=7777,
            effective_date=date(2020, 1, 1),
        )
        db_session.flush()

        # Cache should be invalidated, new value returned
        val = service.get_rule("large_deposit_threshold")
        assert val == 7777


# =============================================================================
# TEST: MODEL
# =============================================================================

class TestBusinessRuleConfigModel:
    """Test the BusinessRuleConfig model methods."""

    def test_get_typed_value_integer(self, rule_model):
        """get_typed_value returns int for integer value_type."""
        rule = rule_model(rule_value=42, value_type="integer")
        assert rule.get_typed_value() == 42
        assert isinstance(rule.get_typed_value(), int)

    def test_get_typed_value_decimal(self, rule_model):
        """get_typed_value returns float for decimal value_type."""
        rule = rule_model(rule_value=3.14, value_type="decimal")
        assert rule.get_typed_value() == 3.14
        assert isinstance(rule.get_typed_value(), float)

    def test_get_typed_value_string(self, rule_model):
        """get_typed_value returns str for string value_type."""
        rule = rule_model(rule_value="hello", value_type="string")
        assert rule.get_typed_value() == "hello"

    def test_get_typed_value_boolean(self, rule_model):
        """get_typed_value returns bool for boolean value_type."""
        rule = rule_model(rule_value=True, value_type="boolean")
        assert rule.get_typed_value() is True

    def test_get_typed_value_json(self, rule_model):
        """get_typed_value returns dict/list as-is for json value_type."""
        rule = rule_model(rule_value={"a": 1, "b": [2, 3]}, value_type="json")
        result = rule.get_typed_value()
        assert result == {"a": 1, "b": [2, 3]}

    def test_get_typed_value_none(self, rule_model):
        """get_typed_value returns None when rule_value is None."""
        rule = rule_model(rule_value=None, value_type="integer")
        assert rule.get_typed_value() is None

    def test_repr(self, rule_model):
        """__repr__ produces a readable string."""
        rule = rule_model(
            rule_key="test_key",
            organization_id=42,
            rule_value=100,
            effective_date=date(2025, 1, 1),
        )
        repr_str = repr(rule)
        assert "test_key" in repr_str
        assert "42" in repr_str


# =============================================================================
# TEST: INACTIVE RULES
# =============================================================================

class TestInactiveRules:
    """Test that inactive (is_active=False) rules are skipped."""

    def test_inactive_rule_not_returned(self, service, db_session, rule_model):
        """An inactive rule is not returned by get_rule."""
        db_session.add(rule_model(
            organization_id=None,
            rule_category="fraud",
            rule_key="large_deposit_threshold",
            rule_value=99999,
            value_type="integer",
            effective_date=date(2020, 1, 1),
            is_active=False,
        ))
        db_session.flush()

        value = service.get_rule("large_deposit_threshold")
        assert value == 5000  # hardcoded fallback, not the inactive DB value
