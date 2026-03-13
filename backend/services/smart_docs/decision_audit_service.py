"""
Decision Audit Service

Provides the business logic for creating, querying, and managing decision
audit records. Enforces:
    - Append-only writes (no update/delete on DecisionAuditLog)
    - Organization-scoped queries (tenant isolation)
    - Retention configuration with regulatory minimums (3-year TRID floor)
    - Archive-based expiration (move to archive table, never hard-delete)

All public methods require an organization_id parameter to ensure tenant
isolation is enforced at the service layer, independent of any middleware.

Usage:
    from services.smart_docs.decision_audit_service import (
        log_decision,
        get_decision_history,
        get_loan_decisions,
        get_retention_config,
        update_retention_config,
        archive_expired_records,
    )
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Regulatory minimum: TRID requires 3 years (12 CFR 1026.25)
TRID_MINIMUM_RETENTION_DAYS = 1095  # 3 * 365

# Default retention: 7 years (IRS guidance for mortgage lenders)
DEFAULT_RETENTION_DAYS = 2555  # 7 * 365

# Valid decision types
VALID_DECISION_TYPES = {
    "document_review",
    "income_calculation",
    "income_approval",
    "fraud_alert",
    "followup_escalation",
    "auto_classification",
    "esign_action",
}

# Valid decision values
VALID_DECISIONS = {
    "approved",
    "rejected",
    "needs_review",
    "escalated",
    "auto_approved",
    "auto_rejected",
}

# Valid decision maker types
VALID_MAKER_TYPES = {
    "user",
    "system",
    "ai_agent",
}


def _get_models():
    """Lazy import to avoid circular dependencies at module load time."""
    from database.models.decision_audit import (
        DecisionAuditLog,
        AuditRetentionConfig,
        ArchivedDecisionAuditLog,
    )
    return DecisionAuditLog, AuditRetentionConfig, ArchivedDecisionAuditLog


# =============================================================================
# LOG DECISION — append-only write
# =============================================================================

def log_decision(
    db: Session,
    organization_id: int,
    loan_id: Optional[int],
    decision_type: str,
    entity_type: str,
    entity_id: int,
    decision: str,
    reasoning: str,
    supporting_data: Optional[Dict[str, Any]] = None,
    maker_type: str = "system",
    maker_id: Optional[int] = None,
    maker_name: Optional[str] = None,
    previous_state: Optional[str] = None,
    new_state: Optional[str] = None,
    document_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> "DecisionAuditLog":
    """Create an immutable audit log entry for a decision.

    Args:
        db: Database session
        organization_id: Tenant organization ID (required, enforces isolation)
        loan_id: Related loan ID (nullable for org-level decisions)
        decision_type: Category of decision (must be in VALID_DECISION_TYPES)
        entity_type: Model type being decided on (e.g. "smart_document")
        entity_id: ID of the entity being decided on
        decision: The decision made (must be in VALID_DECISIONS)
        reasoning: Narrative explanation of why (mandatory for compliance)
        supporting_data: JSON-serializable evidence dict
        maker_type: Who made the decision — "user", "system", or "ai_agent"
        maker_id: User ID for human decisions (nullable for system/AI)
        maker_name: Display name (captures AI agent name for system decisions)
        previous_state: Entity state before the decision
        new_state: Entity state after the decision
        document_id: Related document ID if applicable
        ip_address: Client IP for human decisions
        user_agent: Client user-agent for human decisions

    Returns:
        The created DecisionAuditLog record

    Raises:
        ValueError: If required fields are missing or invalid
    """
    DecisionAuditLog, _, _ = _get_models()

    # Validate required fields
    if not organization_id:
        raise ValueError("organization_id is required for audit trail")
    if not reasoning or not reasoning.strip():
        raise ValueError("reasoning is required — audit records must explain the decision")
    if not entity_type or not entity_type.strip():
        raise ValueError("entity_type is required")
    if not new_state:
        raise ValueError("new_state is required — must capture what the entity became")

    # Validate enums
    if decision_type not in VALID_DECISION_TYPES:
        raise ValueError(
            f"Invalid decision_type '{decision_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_DECISION_TYPES))}"
        )
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. "
            f"Must be one of: {', '.join(sorted(VALID_DECISIONS))}"
        )
    if maker_type not in VALID_MAKER_TYPES:
        raise ValueError(
            f"Invalid maker_type '{maker_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_MAKER_TYPES))}"
        )

    entry = DecisionAuditLog(
        organization_id=organization_id,
        loan_id=loan_id,
        document_id=document_id,
        decision_type=decision_type,
        entity_type=entity_type,
        entity_id=entity_id,
        decision=decision,
        decision_maker_type=maker_type,
        decision_maker_id=maker_id,
        decision_maker_name=maker_name,
        reasoning=reasoning,
        supporting_data=supporting_data,
        previous_state=previous_state,
        new_state=new_state,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )

    db.add(entry)
    db.flush()  # Assign ID without committing — caller controls transaction

    logger.info(
        f"Decision audit logged: type={decision_type} decision={decision} "
        f"entity={entity_type}:{entity_id} org={organization_id} "
        f"maker={maker_type}:{maker_id or maker_name}"
    )

    return entry


# =============================================================================
# QUERY — decision history for an entity
# =============================================================================

def get_decision_history(
    db: Session,
    organization_id: int,
    entity_type: str,
    entity_id: int,
) -> List["DecisionAuditLog"]:
    """Get all decisions for a specific entity, ordered by creation time.

    Args:
        db: Database session
        organization_id: Tenant organization ID (enforces isolation)
        entity_type: The model type (e.g. "smart_document")
        entity_id: The ID of the entity

    Returns:
        List of DecisionAuditLog records, newest first
    """
    DecisionAuditLog, _, _ = _get_models()

    return (
        db.query(DecisionAuditLog)
        .filter(
            DecisionAuditLog.organization_id == organization_id,
            DecisionAuditLog.entity_type == entity_type,
            DecisionAuditLog.entity_id == entity_id,
        )
        .order_by(DecisionAuditLog.created_at.desc())
        .all()
    )


# =============================================================================
# QUERY — all decisions for a loan
# =============================================================================

def get_loan_decisions(
    db: Session,
    organization_id: int,
    loan_id: int,
    decision_type: Optional[str] = None,
    limit: int = 100,
) -> List["DecisionAuditLog"]:
    """Get all decisions for a loan, optionally filtered by decision type.

    Args:
        db: Database session
        organization_id: Tenant organization ID (enforces isolation)
        loan_id: The loan ID to query
        decision_type: Optional filter by decision type
        limit: Maximum records to return (default 100)

    Returns:
        List of DecisionAuditLog records, newest first
    """
    DecisionAuditLog, _, _ = _get_models()

    query = (
        db.query(DecisionAuditLog)
        .filter(
            DecisionAuditLog.organization_id == organization_id,
            DecisionAuditLog.loan_id == loan_id,
        )
    )

    if decision_type:
        if decision_type not in VALID_DECISION_TYPES:
            raise ValueError(f"Invalid decision_type '{decision_type}'")
        query = query.filter(DecisionAuditLog.decision_type == decision_type)

    return (
        query
        .order_by(DecisionAuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


# =============================================================================
# RETENTION CONFIG — get or create default
# =============================================================================

def get_retention_config(
    db: Session,
    organization_id: int,
) -> "AuditRetentionConfig":
    """Get retention config for an organization, creating default if missing.

    The default configuration uses 7-year retention with a 3-year minimum
    floor and cold storage archival enabled.

    Args:
        db: Database session
        organization_id: Tenant organization ID

    Returns:
        AuditRetentionConfig record
    """
    _, AuditRetentionConfig, _ = _get_models()

    config = (
        db.query(AuditRetentionConfig)
        .filter(AuditRetentionConfig.organization_id == organization_id)
        .first()
    )

    if config is None:
        config = AuditRetentionConfig(
            organization_id=organization_id,
            default_retention_days=DEFAULT_RETENTION_DAYS,
            document_retention_days=DEFAULT_RETENTION_DAYS,
            esign_retention_days=DEFAULT_RETENTION_DAYS,
            followup_retention_days=DEFAULT_RETENTION_DAYS,
            min_retention_days=TRID_MINIMUM_RETENTION_DAYS,
            archive_to_cold_storage=True,
        )
        db.add(config)
        db.flush()
        logger.info(
            f"Created default retention config for org {organization_id}: "
            f"{DEFAULT_RETENTION_DAYS} days ({DEFAULT_RETENTION_DAYS // 365} years)"
        )

    return config


# =============================================================================
# RETENTION CONFIG — update with validation
# =============================================================================

def update_retention_config(
    db: Session,
    organization_id: int,
    config_data: Dict[str, Any],
) -> "AuditRetentionConfig":
    """Update retention config with regulatory minimum enforcement.

    No retention period can be set below the min_retention_days floor
    (default 1095 days = 3 years, per TRID 12 CFR 1026.25).

    Args:
        db: Database session
        organization_id: Tenant organization ID
        config_data: Dict of fields to update. Allowed keys:
            default_retention_days, document_retention_days,
            esign_retention_days, followup_retention_days,
            archive_to_cold_storage

    Returns:
        Updated AuditRetentionConfig record

    Raises:
        ValueError: If any retention period is below the regulatory minimum
    """
    config = get_retention_config(db, organization_id)
    min_days = config.min_retention_days

    # Retention fields that have regulatory minimums
    retention_fields = {
        "default_retention_days",
        "document_retention_days",
        "esign_retention_days",
        "followup_retention_days",
    }

    for key, value in config_data.items():
        if key in retention_fields:
            if not isinstance(value, int) or value < min_days:
                raise ValueError(
                    f"Cannot set {key} to {value} days. "
                    f"Minimum retention is {min_days} days "
                    f"({min_days // 365} years) per TRID 12 CFR 1026.25."
                )
            setattr(config, key, value)
        elif key == "archive_to_cold_storage":
            setattr(config, key, bool(value))
        # Silently ignore unknown keys

    config.updated_at = datetime.now(timezone.utc)
    db.flush()

    logger.info(
        f"Updated retention config for org {organization_id}: "
        f"default={config.default_retention_days}d, "
        f"document={config.document_retention_days}d, "
        f"esign={config.esign_retention_days}d, "
        f"followup={config.followup_retention_days}d"
    )

    return config


# =============================================================================
# ARCHIVE — move expired records (never delete)
# =============================================================================

def archive_expired_records(
    db: Session,
    organization_id: int,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Move expired audit records from decision_audit_logs to archived_decision_audit_logs.

    Records are MOVED (insert into archive, then delete from source), never
    hard-deleted without archiving first. This preserves the complete audit
    trail while keeping the active table performant.

    The retention period for each record is determined by the decision_type:
        - document_review, auto_classification -> document_retention_days
        - esign_action -> esign_retention_days
        - followup_escalation -> followup_retention_days
        - All others -> default_retention_days

    Args:
        db: Database session
        organization_id: Tenant organization ID
        batch_size: Maximum records to archive per invocation

    Returns:
        Dict with archived_count and details
    """
    DecisionAuditLog, _, ArchivedDecisionAuditLog = _get_models()

    config = get_retention_config(db, organization_id)
    now = datetime.now(timezone.utc)

    # Map decision types to their retention periods
    type_retention = {
        "document_review": config.document_retention_days,
        "auto_classification": config.document_retention_days,
        "income_calculation": config.document_retention_days,
        "income_approval": config.document_retention_days,
        "fraud_alert": config.default_retention_days,
        "esign_action": config.esign_retention_days,
        "followup_escalation": config.followup_retention_days,
    }

    archived_count = 0
    archived_by_type = {}

    for decision_type, retention_days in type_retention.items():
        cutoff = now - timedelta(days=retention_days)

        # Find expired records for this type
        expired = (
            db.query(DecisionAuditLog)
            .filter(
                DecisionAuditLog.organization_id == organization_id,
                DecisionAuditLog.decision_type == decision_type,
                DecisionAuditLog.created_at < cutoff,
            )
            .limit(batch_size - archived_count)
            .all()
        )

        if not expired:
            continue

        for record in expired:
            # Insert into archive table
            archived = ArchivedDecisionAuditLog(
                organization_id=record.organization_id,
                loan_id=record.loan_id,
                document_id=record.document_id,
                decision_type=record.decision_type,
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                decision=record.decision,
                decision_maker_type=record.decision_maker_type,
                decision_maker_id=record.decision_maker_id,
                decision_maker_name=record.decision_maker_name,
                reasoning=record.reasoning,
                supporting_data=record.supporting_data,
                previous_state=record.previous_state,
                new_state=record.new_state,
                ip_address=record.ip_address,
                user_agent=record.user_agent,
                created_at=record.created_at,
                archived_at=now,
                original_audit_id=record.id,
            )
            db.add(archived)

            # Delete from active table (after archiving)
            db.delete(record)
            archived_count += 1

        archived_by_type[decision_type] = len(expired)

        if archived_count >= batch_size:
            break

    db.flush()

    result = {
        "organization_id": organization_id,
        "archived_count": archived_count,
        "archived_by_type": archived_by_type,
        "retention_config": {
            "default_days": config.default_retention_days,
            "document_days": config.document_retention_days,
            "esign_days": config.esign_retention_days,
            "followup_days": config.followup_retention_days,
        },
        "archived_at": now.isoformat(),
    }

    if archived_count > 0:
        logger.info(
            f"Archived {archived_count} expired audit records for org {organization_id}: "
            f"{archived_by_type}"
        )

    return result
