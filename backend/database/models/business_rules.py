"""
Business Rule Configuration Model

Database-backed configuration for business rules that change with regulations,
eliminating the need for code deploys when thresholds or limits change.

Each rule has:
- A unique key (e.g., "large_deposit_threshold", "ss_wage_base")
- A JSON value (number, string, boolean, or complex object)
- An effective date (for time-versioned rules like SS wage base)
- An optional expiration date (for annual values)
- Organization-level overrides (null org_id = system default)

Lookup precedence:
1. Org-specific rule for the given date
2. System default rule for the given date
3. Hardcoded fallback in BusinessRulesService.RULE_DEFAULTS

Usage:
    from database.models.business_rules import BusinessRuleConfig

    rule = db.query(BusinessRuleConfig).filter(
        BusinessRuleConfig.rule_key == "large_deposit_threshold",
        BusinessRuleConfig.organization_id == org_id,
        BusinessRuleConfig.is_active == True,
    ).first()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship

from db import Base


class BusinessRuleConfig(Base):
    """Configurable business rule stored in the database.

    Rules are keyed by (organization_id, rule_key, effective_date).
    A null organization_id indicates a system-wide default.
    Organization-specific rules take precedence over system defaults.

    The rule_value column stores arbitrary JSON: numbers, strings, booleans,
    arrays, or nested objects. The value_type column indicates how to
    interpret/cast the value in application code.

    Time-versioned rules (e.g., IRS SS wage base that changes annually)
    use effective_date and expiration_date to define their validity window.
    """

    __tablename__ = "business_rule_configs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "rule_key",
            "effective_date",
            name="uq_business_rule_org_key_date",
        ),
        Index(
            "ix_business_rule_key_active",
            "rule_key",
            "is_active",
        ),
        Index(
            "ix_business_rule_org_category",
            "organization_id",
            "rule_category",
        ),
        Index(
            "ix_business_rule_effective",
            "rule_key",
            "effective_date",
            "expiration_date",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Tenant scoping: null = system-wide default, non-null = org override
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )

    # Rule identification
    rule_category = Column(
        String(50),
        nullable=False,
        comment="Category: income, fraud, document, followup, esign, compliance, ai",
    )
    rule_key = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Unique identifier like 'large_deposit_threshold' or 'ss_wage_base'",
    )

    # Rule value (stored as JSON for flexibility)
    rule_value = Column(
        JSON,
        nullable=False,
        comment="The rule value — number, string, boolean, array, or object",
    )
    value_type = Column(
        String(20),
        nullable=False,
        default="integer",
        comment="How to interpret the value: integer, decimal, string, boolean, json",
    )

    # Human-readable description
    description = Column(
        Text,
        nullable=True,
        comment="Human-readable description of what this rule controls",
    )

    # Time-versioning
    effective_date = Column(
        Date,
        nullable=False,
        comment="When this rule value takes effect",
    )
    expiration_date = Column(
        Date,
        nullable=True,
        comment="When this rule value expires (null = no expiration)",
    )

    # Provenance
    source = Column(
        String(100),
        nullable=True,
        comment="Regulatory source: fannie_mae_b3_3_1, irs_2025, cfpb_trid, custom",
    )

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit fields
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        comment="User who last updated this rule",
    )

    # Relationships
    organization = relationship("Organization", backref="business_rules")
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])

    def get_typed_value(self):
        """Return the rule_value cast to the appropriate Python type.

        Returns:
            The value cast according to value_type:
            - "integer" -> int
            - "decimal" -> float
            - "string" -> str
            - "boolean" -> bool
            - "json" -> as-is (dict, list, etc.)
        """
        if self.rule_value is None:
            return None

        try:
            if self.value_type == "integer":
                return int(self.rule_value)
            elif self.value_type == "decimal":
                return float(self.rule_value)
            elif self.value_type == "string":
                return str(self.rule_value)
            elif self.value_type == "boolean":
                if isinstance(self.rule_value, bool):
                    return self.rule_value
                return str(self.rule_value).lower() in ("true", "1", "yes")
            else:
                # "json" or unknown — return as-is
                return self.rule_value
        except (ValueError, TypeError):
            return self.rule_value

    def __repr__(self):
        return (
            f"<BusinessRuleConfig("
            f"key='{self.rule_key}', "
            f"org={self.organization_id}, "
            f"value={self.rule_value}, "
            f"effective={self.effective_date}"
            f")>"
        )


__all__ = [
    "BusinessRuleConfig",
]
