"""
Lead Assignment Service

Core business logic for distributing leads to loan officers.
Supports 6 strategies: round_robin, weighted, geographic, load_balanced,
rule_based, and manual. Includes capacity management, PTO exceptions,
deduplication, and full audit logging.

Usage:
    from services.lead_assignment_service import assign_lead, get_or_create_config

    assigned_user_id = assign_lead(db, lead, org_id, assigned_by=current_user.id)
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import text, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


# =============================================================================
# CONFIG
# =============================================================================

def get_or_create_config(db: Session, org_id: int):
    """Get assignment config for org, creating default if none exists."""
    from database.models.lead_assignment import LeadAssignmentConfig

    config = db.query(LeadAssignmentConfig).filter(
        LeadAssignmentConfig.organization_id == org_id,
    ).first()

    if config is None:
        config = LeadAssignmentConfig(
            organization_id=org_id,
            strategy="round_robin",
        )
        db.add(config)
        db.flush()

    return config


# =============================================================================
# MAIN ASSIGNMENT FUNCTION
# =============================================================================

def assign_lead(
    db: Session,
    lead,
    org_id: int,
    force_user_id: Optional[int] = None,
    assigned_by: Optional[int] = None,
    is_dry_run: bool = False,
) -> Optional[int]:
    """
    Assign a lead to a loan officer based on org configuration.

    Args:
        db: Database session
        lead: Lead SQLAlchemy object (or dict-like with lead attributes)
        org_id: Organization ID for tenant isolation
        force_user_id: Override auto-assignment with specific user
        assigned_by: User who triggered the assignment (for audit)
        is_dry_run: If True, don't actually assign — just return who would get it

    Returns:
        user_id of assigned LO, or None if no one available
    """
    config = get_or_create_config(db, org_id)

    # Manual override
    if force_user_id:
        if not is_dry_run:
            _apply_assignment(db, lead, force_user_id)
            _log_assignment(
                db, org_id, lead, "MANUAL_OVERRIDE",
                to_user_id=force_user_id,
                strategy="manual",
                reason=f"Manually assigned by user {assigned_by}",
                created_by=assigned_by,
            )
        return force_user_id

    # Manual strategy = no auto-assignment
    if config.strategy == "manual":
        if not is_dry_run:
            _log_assignment(
                db, org_id, lead, "UNASSIGNED",
                strategy="manual",
                reason="Manual strategy — lead awaits manual assignment",
                created_by=assigned_by,
            )
        return None

    # Get candidate pool (excludes PTO, blocked users)
    candidates = _get_eligible_candidates(db, org_id, config)
    if not candidates:
        # Fall back to fallback user
        if config.fallback_user_id:
            if not is_dry_run:
                _apply_assignment(db, lead, config.fallback_user_id)
                _log_assignment(
                    db, org_id, lead, "FALLBACK",
                    to_user_id=config.fallback_user_id,
                    strategy=config.strategy,
                    reason="No eligible candidates — assigned to fallback user",
                    created_by=assigned_by,
                )
            return config.fallback_user_id
        logger.warning(f"No eligible LOs for org {org_id}, lead unassigned")
        return None

    # Apply capacity filter
    if config.respect_capacity:
        candidates = _filter_by_capacity(db, org_id, candidates, config)
        if not candidates:
            if config.fallback_user_id:
                if not is_dry_run:
                    _apply_assignment(db, lead, config.fallback_user_id)
                    _log_assignment(
                        db, org_id, lead, "FALLBACK",
                        to_user_id=config.fallback_user_id,
                        strategy=config.strategy,
                        reason="All candidates at capacity — assigned to fallback user",
                        created_by=assigned_by,
                    )
                return config.fallback_user_id
            return None

    # Dispatch to strategy
    lead_data = _extract_lead_data(lead)

    strategy_map = {
        "round_robin": lambda: _assign_round_robin(db, org_id, config, candidates),
        "weighted": lambda: _assign_weighted(candidates),
        "geographic": lambda: _assign_geographic(db, org_id, candidates, lead_data),
        "load_balanced": lambda: _assign_load_balanced(db, org_id, candidates),
        "rule_based": lambda: _assign_rule_based(db, org_id, candidates, lead_data, config),
    }

    strategy_fn = strategy_map.get(config.strategy)
    if not strategy_fn:
        logger.warning(f"Unknown strategy '{config.strategy}', falling back to round_robin")
        strategy_fn = lambda: _assign_round_robin(db, org_id, config, candidates)

    result_user_id, reason, rule_name = strategy_fn()

    # Final fallback
    if result_user_id is None:
        result_user_id = config.fallback_user_id or (candidates[0]["user_id"] if candidates else None)
        reason = reason or "Strategy returned no match — using fallback"

    if result_user_id and not is_dry_run:
        _apply_assignment(db, lead, result_user_id)
        _log_assignment(
            db, org_id, lead, "AUTO_ASSIGNED",
            to_user_id=result_user_id,
            strategy=config.strategy,
            rule_name=rule_name,
            reason=reason or f"Assigned via {config.strategy}",
            event_data={"candidates_count": len(candidates), "lead_data": lead_data},
            created_by=assigned_by,
        )

    return result_user_id


def reassign_lead(
    db: Session,
    lead,
    org_id: int,
    to_user_id: int,
    reassigned_by: int,
    reason: Optional[str] = None,
) -> int:
    """Reassign a lead from current owner to a new user."""
    from_user_id = getattr(lead, "owner_id", None)
    _apply_assignment(db, lead, to_user_id)
    _log_assignment(
        db, org_id, lead, "REASSIGNED",
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        strategy="manual",
        reason=reason or f"Reassigned by user {reassigned_by}",
        created_by=reassigned_by,
    )
    return to_user_id


# =============================================================================
# STRATEGIES
# =============================================================================

def _assign_round_robin(
    db: Session, org_id: int, config, candidates: List[Dict],
) -> Tuple[Optional[int], str, Optional[str]]:
    """Round-robin: rotate through candidates.

    Uses SELECT...FOR UPDATE on the config row to serialize concurrent assignments.
    """
    try:
        # Lock the config row for serialization
        db.execute(text(
            "SELECT id FROM lead_assignment_configs "
            "WHERE organization_id = :org_id FOR UPDATE"
        ), {"org_id": org_id})

        idx = config.round_robin_index or 0
        next_idx = idx % len(candidates)
        assigned = candidates[next_idx]

        config.round_robin_index = (next_idx + 1) % len(candidates)

        return (
            assigned["user_id"],
            f"Round-robin index {next_idx} → user {assigned['user_id']}",
            None,
        )
    except Exception as e:
        logger.error(f"Round-robin failed: {e}")
        return (candidates[0]["user_id"] if candidates else None, "Round-robin fallback", None)


def _assign_weighted(
    candidates: List[Dict],
) -> Tuple[Optional[int], str, Optional[str]]:
    """Weighted: distribute based on weight values using weighted random selection."""
    if not candidates:
        return (None, "No candidates", None)

    weights = [c.get("weight", 100) for c in candidates]
    total = sum(weights)
    if total == 0:
        selected = random.choice(candidates)
    else:
        selected = random.choices(candidates, weights=weights, k=1)[0]

    pct = round((selected.get("weight", 100) / total) * 100, 1) if total > 0 else 0
    return (
        selected["user_id"],
        f"Weighted selection: user {selected['user_id']} (weight {selected.get('weight', 100)}, {pct}%)",
        None,
    )


def _assign_geographic(
    db: Session, org_id: int, candidates: List[Dict], lead_data: Dict,
) -> Tuple[Optional[int], str, Optional[str]]:
    """Geographic: match lead state to LO geographic_states list."""
    lead_state = (lead_data.get("state") or "").upper().strip()
    if not lead_state:
        return _assign_round_robin_simple(candidates)

    # Find candidates with matching geographic_states
    for c in candidates:
        states = c.get("geographic_states") or []
        if lead_state in [s.upper() for s in states]:
            return (
                c["user_id"],
                f"Geographic match: {lead_state} → user {c['user_id']}",
                None,
            )

    # No geographic match — fall back to candidates without state restrictions
    unrestricted = [c for c in candidates if not c.get("geographic_states")]
    if unrestricted:
        return (
            unrestricted[0]["user_id"],
            f"No geographic match for {lead_state} — using unrestricted LO",
            None,
        )

    return (candidates[0]["user_id"] if candidates else None, "Geographic fallback", None)


def _assign_load_balanced(
    db: Session, org_id: int, candidates: List[Dict],
) -> Tuple[Optional[int], str, Optional[str]]:
    """Load-balanced: assign to LO with fewest active leads."""
    try:
        user_ids = [c["user_id"] for c in candidates]

        rows = db.execute(text(
            "SELECT owner_id, COUNT(*) as cnt "
            "FROM leads "
            "WHERE owner_id = ANY(:ids) AND organization_id = :org_id "
            "AND stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call') "
            "GROUP BY owner_id"
        ), {"ids": user_ids, "org_id": org_id}).fetchall()

        count_map = {row[0]: row[1] for row in rows}
        counts = [(uid, count_map.get(uid, 0)) for uid in user_ids]
        counts.sort(key=lambda x: x[1])

        chosen_id = counts[0][0]
        chosen_count = counts[0][1]

        return (
            chosen_id,
            f"Load-balanced: user {chosen_id} has fewest active leads ({chosen_count})",
            None,
        )
    except Exception as e:
        logger.error(f"Load-balanced failed: {e}")
        return (candidates[0]["user_id"] if candidates else None, "Load-balanced fallback", None)


def _assign_rule_based(
    db: Session, org_id: int, candidates: List[Dict], lead_data: Dict, config,
) -> Tuple[Optional[int], str, Optional[str]]:
    """Rule-based: evaluate rules in priority order, first match wins."""
    from database.models.lead_assignment import LeadAssignmentRule

    rules = db.query(LeadAssignmentRule).filter(
        LeadAssignmentRule.organization_id == org_id,
        LeadAssignmentRule.is_active == True,
    ).order_by(LeadAssignmentRule.priority.asc()).all()

    if not rules:
        # No rules defined — fall back to round-robin
        return _assign_round_robin(db, org_id, config, candidates)

    for rule in rules:
        if _evaluate_conditions(rule.conditions, rule.match_type, lead_data):
            target_user = _resolve_rule_target(
                db, org_id, rule.target_type, rule.target_config, candidates, config,
            )
            if target_user:
                return (
                    target_user,
                    f"Rule '{rule.rule_name}' matched (priority {rule.priority})",
                    rule.rule_name,
                )

    # No rule matched — fall back to round-robin
    result = _assign_round_robin(db, org_id, config, candidates)
    return (result[0], "No rules matched — round-robin fallback", None)


def _assign_round_robin_simple(
    candidates: List[Dict],
) -> Tuple[Optional[int], str, Optional[str]]:
    """Simple round-robin without DB state (for fallback scenarios)."""
    if not candidates:
        return (None, "No candidates", None)
    return (candidates[0]["user_id"], "Simple round-robin fallback", None)


# =============================================================================
# RULE EVALUATION
# =============================================================================

def _evaluate_conditions(
    conditions: List[Dict], match_type: str, lead_data: Dict,
) -> bool:
    """Evaluate a list of conditions against lead data."""
    if not conditions:
        return True

    results = [_evaluate_single_condition(c, lead_data) for c in conditions]

    if match_type == "ANY":
        return any(results)
    return all(results)  # ALL


def _evaluate_single_condition(condition: Dict, lead_data: Dict) -> bool:
    """Evaluate a single condition against lead data."""
    field = condition.get("field", "")
    op = condition.get("op", "eq")
    expected = condition.get("value")
    actual = lead_data.get(field)

    if actual is None:
        return op in ("neq", "not_in")

    try:
        if op == "eq":
            return str(actual).lower() == str(expected).lower()
        elif op == "neq":
            return str(actual).lower() != str(expected).lower()
        elif op == "in":
            if isinstance(expected, list):
                return str(actual).lower() in [str(v).lower() for v in expected]
            return str(actual).lower() in str(expected).lower()
        elif op == "not_in":
            if isinstance(expected, list):
                return str(actual).lower() not in [str(v).lower() for v in expected]
            return str(actual).lower() not in str(expected).lower()
        elif op == "gt":
            return float(actual) > float(expected)
        elif op == "gte":
            return float(actual) >= float(expected)
        elif op == "lt":
            return float(actual) < float(expected)
        elif op == "lte":
            return float(actual) <= float(expected)
        elif op == "contains":
            return str(expected).lower() in str(actual).lower()
    except (ValueError, TypeError):
        return False

    return False


def _resolve_rule_target(
    db: Session, org_id: int, target_type: str,
    target_config: Dict, candidates: List[Dict], config,
) -> Optional[int]:
    """Resolve a rule's target to a specific user_id."""
    if target_type == "USER":
        user_id = target_config.get("user_id")
        # Verify user is in candidate pool
        if any(c["user_id"] == user_id for c in candidates):
            return user_id
        return user_id  # Allow direct assignment even outside pool

    elif target_type == "POOL":
        # Subset candidates to the specified pool
        pool_user_ids = target_config.get("user_ids", [])
        pool_candidates = [c for c in candidates if c["user_id"] in pool_user_ids]
        if pool_candidates:
            result = _assign_round_robin(db, org_id, config, pool_candidates)
            return result[0]

    elif target_type == "ROUND_ROBIN":
        rr_user_ids = target_config.get("user_ids", [])
        rr_candidates = [c for c in candidates if c["user_id"] in rr_user_ids]
        if rr_candidates:
            result = _assign_round_robin(db, org_id, config, rr_candidates)
            return result[0]

    elif target_type == "ROLE":
        role = target_config.get("role")
        if role:
            try:
                row = db.execute(text(
                    "SELECT id FROM users WHERE organization_id = :org_id "
                    "AND role = :role AND is_active = true LIMIT 1"
                ), {"org_id": org_id, "role": role}).first()
                if row:
                    return row[0]
            except Exception as e:
                logger.error(f"Role resolution failed: {e}")

    return None


# =============================================================================
# HELPERS
# =============================================================================

def _get_eligible_candidates(
    db: Session, org_id: int, config,
) -> List[Dict]:
    """Get pool members who are eligible for assignment right now."""
    from database.models.lead_assignment import LeadAssignmentPool, LeadAssignmentException

    pool_members = db.query(LeadAssignmentPool).filter(
        LeadAssignmentPool.organization_id == org_id,
        LeadAssignmentPool.is_active == True,
    ).all()

    if not pool_members:
        # No pool configured — fall back to active LOs in org
        try:
            rows = db.execute(text(
                "SELECT id FROM users "
                "WHERE organization_id = :org_id AND is_active = true "
                "AND role IN ('loan_officer', 'sales', 'admin') "
                "ORDER BY id"
            ), {"org_id": org_id}).fetchall()
            return [{"user_id": r[0], "weight": 100, "max_daily_leads": config.max_daily_leads_per_user} for r in rows]
        except Exception as e:
            logger.error(f"Failed to get fallback LOs: {e}")
            return []

    # Filter out users with active exceptions (PTO, blocked)
    now = utcnow()
    active_exceptions = db.query(LeadAssignmentException.user_id).filter(
        LeadAssignmentException.organization_id == org_id,
        LeadAssignmentException.is_active == True,
        LeadAssignmentException.starts_at <= now,
        (LeadAssignmentException.ends_at == None) | (LeadAssignmentException.ends_at > now),
    ).all()
    excluded_ids = {exc[0] for exc in active_exceptions}

    candidates = []
    for member in pool_members:
        if member.user_id not in excluded_ids:
            candidates.append({
                "user_id": member.user_id,
                "weight": member.weight or 100,
                "max_daily_leads": member.max_daily_leads or config.max_daily_leads_per_user,
                "geographic_states": member.geographic_states,
                "specialties": member.specialties,
            })

    return candidates


def _filter_by_capacity(
    db: Session, org_id: int, candidates: List[Dict], config,
) -> List[Dict]:
    """Remove candidates who have hit their daily lead limit."""
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    user_ids = [c["user_id"] for c in candidates]

    try:
        rows = db.execute(text(
            "SELECT owner_id, COUNT(*) as cnt "
            "FROM leads "
            "WHERE owner_id = ANY(:ids) AND organization_id = :org_id "
            "AND created_at >= :today "
            "GROUP BY owner_id"
        ), {"ids": user_ids, "org_id": org_id, "today": today_start}).fetchall()

        daily_counts = {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.warning(f"Capacity check failed: {e}")
        return candidates  # Don't filter on failure

    filtered = []
    for c in candidates:
        current = daily_counts.get(c["user_id"], 0)
        if current < c["max_daily_leads"]:
            filtered.append(c)

    return filtered


def _extract_lead_data(lead) -> Dict[str, Any]:
    """Extract relevant attributes from a lead for condition evaluation."""
    if isinstance(lead, dict):
        return lead

    data = {}
    fields = [
        "loan_amount", "loan_purpose", "loan_type", "property_type",
        "state", "zip_code", "credit_score", "source", "ai_score",
        "first_time_buyer", "employment_status", "referral_partner_id",
    ]
    for f in fields:
        val = getattr(lead, f, None)
        if val is not None:
            data[f] = val

    return data


def _apply_assignment(db: Session, lead, user_id: int):
    """Set the lead's owner_id."""
    if hasattr(lead, "owner_id"):
        lead.owner_id = user_id
    elif isinstance(lead, dict):
        lead["owner_id"] = user_id


def _log_assignment(
    db: Session,
    org_id: int,
    lead,
    action: str,
    to_user_id: Optional[int] = None,
    from_user_id: Optional[int] = None,
    strategy: Optional[str] = None,
    rule_name: Optional[str] = None,
    reason: Optional[str] = None,
    event_data: Optional[Dict] = None,
    created_by: Optional[int] = None,
):
    """Log an assignment decision to the audit trail."""
    from database.models.lead_assignment import LeadAssignmentAuditLog

    lead_id = getattr(lead, "id", None) or (lead.get("id") if isinstance(lead, dict) else None)

    try:
        log = LeadAssignmentAuditLog(
            organization_id=org_id,
            lead_id=lead_id,
            action=action,
            strategy_used=strategy,
            rule_name=rule_name,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            decision_reason=reason,
            event_data=event_data,
            created_by_user_id=created_by,
        )
        db.add(log)
    except Exception as e:
        logger.warning(f"Failed to log assignment: {e}")


# =============================================================================
# QUERY HELPERS (for routes)
# =============================================================================

def get_assignment_stats(db: Session, org_id: int, days: int = 30) -> Dict:
    """Get assignment statistics for the organization."""
    try:
        stats = db.execute(text("""
            SELECT
                COUNT(*) as total_assignments,
                COUNT(DISTINCT to_user_id) as unique_los,
                COUNT(CASE WHEN action = 'AUTO_ASSIGNED' THEN 1 END) as auto_assigned,
                COUNT(CASE WHEN action = 'MANUAL_OVERRIDE' THEN 1 END) as manual_assigned,
                COUNT(CASE WHEN action = 'REASSIGNED' THEN 1 END) as reassigned,
                COUNT(CASE WHEN action = 'FALLBACK' THEN 1 END) as fallback_used
            FROM lead_assignment_audit_log
            WHERE organization_id = :org_id
            AND created_at >= CURRENT_DATE - :days
        """), {"org_id": org_id, "days": days}).first()

        distribution = db.execute(text("""
            SELECT to_user_id, COUNT(*) as cnt
            FROM lead_assignment_audit_log
            WHERE organization_id = :org_id
            AND created_at >= CURRENT_DATE - :days
            AND to_user_id IS NOT NULL
            GROUP BY to_user_id
            ORDER BY cnt DESC
        """), {"org_id": org_id, "days": days}).fetchall()

        return {
            "period_days": days,
            "total_assignments": stats[0] or 0,
            "unique_los": stats[1] or 0,
            "auto_assigned": stats[2] or 0,
            "manual_assigned": stats[3] or 0,
            "reassigned": stats[4] or 0,
            "fallback_used": stats[5] or 0,
            "distribution": [
                {"user_id": row[0], "count": row[1]}
                for row in distribution
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get assignment stats: {e}")
        return {"period_days": days, "total_assignments": 0}
